#!/usr/bin/env python3
"""
Daily cron script: convert new raw questions to EQJS-2.0.

Usage: python scripts/run_raw_to_eqjs.py [--paper PAPER_CODE] [--dry-run]

Algorithm:
1. List all paper folders in raw/
2. For each paper, list expected question numbers
3. Check eqjs/{paper}/ for existing conversions
4. For each missing question:
   a. Load working-state-capsule.md
   b. Load question text, statistics, examiner comments
   c. Detect diagram -> load protocol if needed
   d. Call Anthropic API with assembled prompt
   e. Parse and validate response
   f. Write to eqjs/ if valid
   g. Log to metadata/conversion-logs/raw-to-eqjs/

Rate limit: max 10 API calls per minute.
Retry: 3 attempts with exponential backoff on API errors.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

from validate_eqjs import validate_eqjs

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "raw"
EQJS_DIR = ROOT / "eqjs"
CONFIG_DIR = ROOT / "config"
LOG_DIR = ROOT / "metadata" / "conversion-logs" / "raw-to-eqjs"
REGISTRY_PATH = ROOT / "protocols" / "protocol-registry.json"

MODEL = "claude-sonnet-4-5-20250929"
MAX_CALLS_PER_MINUTE = 10
MAX_RETRIES = 3


def load_working_state_capsule() -> str:
    """Load the system prompt from working-state-capsule.md."""
    capsule_path = CONFIG_DIR / "working-state-capsule.md"
    with open(capsule_path) as f:
        return f.read()


def load_protocol_registry() -> dict:
    """Load the protocol registry."""
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def detect_protocol(question_text: str, registry: dict) -> str | None:
    """Match question text against protocol trigger keywords."""
    text_lower = question_text.lower()
    for proto in registry.get("protocols", []):
        for trigger in proto.get("triggers", []):
            if trigger.lower() in text_lower:
                return proto["id"]
    return None


def load_raw_question(paper_dir: Path, qno: int) -> dict | None:
    """Load a raw question from paper directory.

    Looks for Q{n}.md or Q{n}.json in the paper directory.
    Also loads statistics.json and examiner_comments.md if available.
    """
    question_data = {"qno": qno, "text": None, "statistics": None, "examiner_comment": None}

    # Try loading question text
    md_path = paper_dir / f"Q{qno}.md"
    json_path = paper_dir / f"Q{qno}.json"

    if md_path.exists():
        with open(md_path) as f:
            question_data["text"] = f.read()
    elif json_path.exists():
        with open(json_path) as f:
            question_data["text"] = json.dumps(json.load(f), indent=2)
    else:
        return None

    # Load statistics if available
    stats_path = paper_dir / "statistics.json"
    if stats_path.exists():
        with open(stats_path) as f:
            all_stats = json.load(f)
            question_data["statistics"] = all_stats.get(f"Q{qno}", all_stats.get(str(qno)))

    # Load examiner comments if available
    comments_path = paper_dir / "examiner_comments.md"
    if comments_path.exists():
        with open(comments_path) as f:
            content = f.read()
            # Try to extract comment for this specific question
            marker = f"## Q{qno}"
            if marker in content:
                start = content.index(marker)
                end = content.find("\n## Q", start + 1)
                question_data["examiner_comment"] = content[start:end].strip() if end > 0 else content[start:].strip()

    return question_data


def build_user_prompt(question_data: dict, protocol_id: str | None, paper_code: str) -> str:
    """Assemble the user prompt for the API call."""
    parts = [f"Convert the following question to EQJS-2.0 JSON format.\n"]
    parts.append(f"Paper code: {paper_code}")
    parts.append(f"Question number: {question_data['qno']}\n")
    parts.append(f"QUESTION TEXT:\n{question_data['text']}\n")

    if question_data.get("statistics"):
        parts.append(f"STATISTICS:\n{json.dumps(question_data['statistics'], indent=2)}\n")

    if question_data.get("examiner_comment"):
        parts.append(f"EXAMINER COMMENT:\n{question_data['examiner_comment']}\n")

    if protocol_id:
        parts.append(f"DIAGRAM PROTOCOL: {protocol_id}")
        parts.append("Load and follow this protocol for diagram encoding.\n")

    parts.append("Output ONLY the complete EQJS-2.0 JSON object. No markdown fences, no explanation.")

    return "\n".join(parts)


def call_api(client: anthropic.Anthropic, system_prompt: str, user_prompt: str, retry: int = 0) -> str | None:
    """Call the Anthropic API with retry logic."""
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
    except anthropic.APIError as e:
        if retry < MAX_RETRIES:
            wait = 2 ** (retry + 1)
            print(f"  API error (attempt {retry + 1}/{MAX_RETRIES}): {e}. Retrying in {wait}s...")
            time.sleep(wait)
            return call_api(client, system_prompt, user_prompt, retry + 1)
        print(f"  API error after {MAX_RETRIES} retries: {e}")
        return None


def parse_json_response(response_text: str) -> dict | None:
    """Extract JSON from the API response."""
    text = response_text.strip()
    # Remove markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  Failed to parse JSON: {e}")
        return None


def write_log(log_dir: Path, entry: dict):
    """Append a log entry to the day's JSONL log file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = log_dir / f"{date_str}_run.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_paper_question_numbers(paper_dir: Path) -> list[int]:
    """Detect question numbers from files in a paper directory."""
    numbers = set()
    for f in paper_dir.iterdir():
        name = f.stem
        if name.startswith("Q") and name[1:].isdigit():
            numbers.add(int(name[1:]))
    return sorted(numbers)


def process_paper(paper_code: str, client: anthropic.Anthropic, dry_run: bool = False):
    """Process all unconverted questions in a paper."""
    paper_dir = RAW_DIR / paper_code
    if not paper_dir.exists():
        print(f"Paper directory not found: {paper_dir}")
        return

    eqjs_paper_dir = EQJS_DIR / paper_code
    eqjs_paper_dir.mkdir(parents=True, exist_ok=True)

    system_prompt = load_working_state_capsule()
    registry = load_protocol_registry()
    question_numbers = get_paper_question_numbers(paper_dir)

    if not question_numbers:
        print(f"No questions found in {paper_dir}")
        return

    print(f"Paper {paper_code}: found questions {question_numbers}")
    call_count = 0
    minute_start = time.time()

    for qno in question_numbers:
        # Check if already converted
        eqjs_path = eqjs_paper_dir / f"Q{qno}.json"
        if eqjs_path.exists():
            print(f"  Q{qno}: already converted, skipping")
            continue

        # Rate limiting
        call_count += 1
        if call_count > MAX_CALLS_PER_MINUTE:
            elapsed = time.time() - minute_start
            if elapsed < 60:
                wait = 60 - elapsed
                print(f"  Rate limit: waiting {wait:.1f}s")
                time.sleep(wait)
            call_count = 1
            minute_start = time.time()

        # Load question
        question_data = load_raw_question(paper_dir, qno)
        if not question_data:
            print(f"  Q{qno}: no source file found, skipping")
            write_log(LOG_DIR, {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "paper_code": paper_code,
                "question": qno,
                "status": "skipped",
                "reason": "no_source_file"
            })
            continue

        # Detect protocol
        protocol_id = detect_protocol(question_data.get("text", ""), registry)
        if protocol_id:
            print(f"  Q{qno}: detected protocol {protocol_id}")

        # Build prompt
        user_prompt = build_user_prompt(question_data, protocol_id, paper_code)

        if dry_run:
            print(f"  Q{qno}: [DRY RUN] would call API with {len(user_prompt)} char prompt")
            write_log(LOG_DIR, {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "paper_code": paper_code,
                "question": qno,
                "status": "dry_run",
                "protocol_detected": protocol_id
            })
            continue

        # Call API
        print(f"  Q{qno}: calling API...")
        response_text = call_api(client, system_prompt, user_prompt)
        if not response_text:
            write_log(LOG_DIR, {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "paper_code": paper_code,
                "question": qno,
                "status": "api_error",
                "protocol_detected": protocol_id
            })
            continue

        # Parse response
        eqjs_data = parse_json_response(response_text)
        if not eqjs_data:
            write_log(LOG_DIR, {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "paper_code": paper_code,
                "question": qno,
                "status": "parse_error",
                "protocol_detected": protocol_id
            })
            continue

        # Write to temp file for validation
        temp_path = eqjs_paper_dir / f"Q{qno}_temp.json"
        with open(temp_path, "w") as f:
            json.dump(eqjs_data, f, indent=2)

        # Validate
        validation = validate_eqjs(str(temp_path))
        if not validation["valid"]:
            print(f"  Q{qno}: validation FAILED: {validation['errors']}")
            temp_path.unlink()
            write_log(LOG_DIR, {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "paper_code": paper_code,
                "question": qno,
                "status": "validation_failed",
                "errors": validation["errors"],
                "warnings": validation["warnings"],
                "protocol_detected": protocol_id
            })
            continue

        # Rename temp to final
        temp_path.rename(eqjs_path)
        print(f"  Q{qno}: SUCCESS -> {eqjs_path}")

        if validation["warnings"]:
            print(f"  Q{qno}: warnings: {validation['warnings']}")

        write_log(LOG_DIR, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "paper_code": paper_code,
            "question": qno,
            "status": "success",
            "output_file": str(eqjs_path),
            "warnings": validation["warnings"],
            "protocol_detected": protocol_id
        })


def main():
    parser = argparse.ArgumentParser(description="Convert raw questions to EQJS-2.0")
    parser.add_argument("--paper", type=str, help="Process only this paper code")
    parser.add_argument("--dry-run", action="store_true", help="Don't call API, just show what would happen")
    args = parser.parse_args()

    if not args.dry_run:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY environment variable not set")
            sys.exit(1)
        client = anthropic.Anthropic(api_key=api_key)
    else:
        client = None

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if args.paper:
        papers = [args.paper]
    else:
        papers = sorted([d.name for d in RAW_DIR.iterdir() if d.is_dir() and d.name != ".gitkeep"])

    if not papers:
        print("No papers found in raw/")
        return

    print(f"Processing papers: {papers}")
    for paper_code in papers:
        print(f"\n{'='*60}")
        print(f"Processing: {paper_code}")
        print(f"{'='*60}")
        process_paper(paper_code, client, args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
