#!/usr/bin/env python3
"""
Daily cron script: convert new EQJS items to AI-native V8 schema.

Usage: python scripts/run_eqjs_to_ainative.py [--item ITEM_ID] [--dry-run]

Algorithm:
1. List all EQJS files in eqjs/
2. Check ai-native/ for existing conversions
3. For each missing item:
   a. Run Stage 1 (Q-Matrix Extraction)
   b. Check diagram_dependent
   c. If diagram: run Stage 2-Bo2, then Stage 3 with orthogonality
   d. If not: run Stage 2-Single, then Stage 3
   e. Handle retries (max 3 on REJECTED)
   f. Write to ai-native/
   g. Log to metadata/conversion-logs/eqjs-to-ainative/
   h. If Bo2: log to metadata/bo2-generation-logs/
"""

import argparse
import json
import math
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

sys.path.insert(0, str(Path(__file__).parent))
from validate_ainative import validate_ainative

ROOT = Path(__file__).parent.parent
EQJS_DIR = ROOT / "eqjs"
AINATIVE_DIR = ROOT / "ai-native"
CONFIG_DIR = ROOT / "config"
LOG_DIR = ROOT / "metadata" / "conversion-logs" / "eqjs-to-ainative"
BO2_LOG_DIR = ROOT / "metadata" / "bo2-generation-logs"
V8_MANUAL = ROOT / "docs" / "V8-construction-manual.md"

MODEL = "claude-sonnet-4-5-20250929"
MAX_RETRIES = 3
MAX_CALLS_PER_MINUTE = 10

STAGE1_SYSTEM = ""
STAGE2_BO2_SYSTEM = ""
STAGE2_SINGLE_SYSTEM = ""
STAGE3_SYSTEM = ""


def load_v8_prompts():
    """Load frozen prompts from the V8 Construction Manual."""
    global STAGE1_SYSTEM, STAGE2_BO2_SYSTEM, STAGE2_SINGLE_SYSTEM, STAGE3_SYSTEM

    if not V8_MANUAL.exists():
        print(f"WARNING: V8 manual not found at {V8_MANUAL}. Using inline prompts.")
        _set_inline_prompts()
        return

    content = V8_MANUAL.read_text()
    STAGE1_SYSTEM = _extract_prompt(content, "§1.1 System Prompt", "[HUMAN]")
    STAGE2_BO2_SYSTEM = _extract_prompt(content, "§2A.1 System Prompt", "[HUMAN]")
    STAGE2_SINGLE_SYSTEM = _extract_prompt(content, "§2B.1 System Prompt", "[HUMAN]")
    STAGE3_SYSTEM = _extract_prompt(content, "§3.1 System Prompt", "[HUMAN]")

    if not all([STAGE1_SYSTEM, STAGE2_BO2_SYSTEM, STAGE2_SINGLE_SYSTEM, STAGE3_SYSTEM]):
        print("WARNING: Could not extract all prompts from V8 manual. Using inline fallback.")
        _set_inline_prompts()


def _extract_prompt(content: str, start_marker: str, end_marker: str) -> str:
    """Extract a prompt section from markdown between code fences."""
    idx = content.find(start_marker)
    if idx == -1:
        return ""
    fence_start = content.find("```", idx)
    if fence_start == -1:
        return ""
    line_end = content.find("\n", fence_start)
    text_start = line_end + 1
    human_idx = content.find(end_marker, text_start)
    fence_end = content.find("```", text_start)
    end = min(human_idx, fence_end) if human_idx > 0 and fence_end > 0 else max(human_idx, fence_end)
    if end <= text_start:
        return ""
    return content[text_start:end].strip()


def _set_inline_prompts():
    """Fallback inline prompts matching V8 spec."""
    global STAGE1_SYSTEM, STAGE2_BO2_SYSTEM, STAGE2_SINGLE_SYSTEM, STAGE3_SYSTEM

    STAGE1_SYSTEM = (
        "You are an expert psychometrician and cognitive scientist. Your task is to "
        "extract the Cognitive Q-Matrix from a seed multiple-choice question.\n\n"
        "You will be provided with a JSON representing a test item (EQJS schema).\n\n"
        "INSTRUCTIONS:\n"
        "1. Identify the Core Concept required to answer the question correctly.\n"
        "2. Analyze the `common_errors` array. For each incorrect option, extract the specific "
        "\"Misconception Attribute\" (M1, M2, etc.).\n"
        "3. If `frequency_percent` is missing for any option, ignore the frequency and rely "
        "entirely on the `misconception` and `pedagogical_note` text.\n"
        "4. Determine if the misconception attributes have a natural ordinal ranking. "
        "Set misconception_ordering accordingly.\n"
        "5. If the seed item contains `stimulus.diagrams[]`, parse the `structured_description` "
        "and `semantic_description` fields. The Core Concept extraction MUST incorporate the "
        "visual/spatial mechanism.\n"
        "6. Generate 3 transfer domain seeds — each must be a structurally different domain "
        "where the identical underlying mechanism applies.\n\n"
        "OUTPUT FORMAT (strict JSON):\n"
        "{\n"
        '  "core_concept": "...",\n'
        '  "mastery_logic": "...",\n'
        '  "diagram_dependent": true | false,\n'
        '  "diagram_mechanism": "... or null",\n'
        '  "misconception_ordering": "ordered" | "unordered",\n'
        '  "phase2_model": "GPCM" | "NRM",\n'
        '  "q_matrix": { "M1": { "option": "A", "description": "...", "attribute_profile": [1,0,0] } },\n'
        '  "transfer_domains": [ { "domain": "...", "seed": "...", "preserves_mechanism": "..." } ]\n'
        "}"
    )

    STAGE2_BO2_SYSTEM = (
        "You are an expert assessment developer. You will generate TWO diagnostic item "
        "candidates for T3 (Concept Probe) and T4 (Far-Transfer Check), using TWO MANDATORY "
        "ORTHOGONAL PATHWAYS.\n\n"
        "PATHWAY A: TEXT-ABSTRACTION — Strip ALL visual/spatial elements. Construct T3 and T4 "
        "as PURELY TEXTUAL items.\n"
        "PATHWAY B: SCHEMA-MUTATION — Generate a NEW diagram scenario preserving the identical "
        "mechanism but MUTATING visual elements.\n\n"
        "RULES:\n"
        "- T3 distractors MUST map to exactly the Q-matrix misconceptions.\n"
        "- T3 MUST include \"I am not sure\" tagged as routing_LoK.\n"
        "- T4 must NOT include an \"I don't know\" option.\n"
        "- Correct answer must NOT be identifiable by elimination.\n\n"
        "Output strict JSON with pathway_A_text_abstraction, pathway_B_schema_mutation, "
        "and orthogonality_check fields."
    )

    STAGE2_SINGLE_SYSTEM = (
        "You are an expert assessment developer. Using the provided Q-Matrix and Core Concept, "
        "generate T3 (Concept Probe) and T4 (Far-Transfer Check).\n\n"
        "DOMAIN CONSTRAINT: For T4, you MUST use one of the provided transfer_domains.\n\n"
        "T3 RULES:\n"
        "- De-contextualize completely from the seed item.\n"
        "- Each distractor maps to exactly one misconception in the Q-matrix.\n"
        "- Include final option: \"I am not sure\" tagged as routing_LoK.\n\n"
        "T4 RULES:\n"
        "- Use one of the provided transfer_domains.\n"
        "- Surface features must share ZERO nouns or scenarios with T1 or T3.\n"
        "- Do NOT include an \"I don't know\" option in T4.\n\n"
        "Output strict JSON with T3_probe and T4_transfer fields."
    )

    STAGE3_SYSTEM = (
        "You are a Psychometric Auditor. Audit proposed T3 and T4 diagnostic items against "
        "IRT constraints. Apply ALL FIVE criteria:\n"
        "1. DIAGNOSTIC PURITY — Does choosing Distractor X strictly require Misconception X?\n"
        "2. IRT DISCRIMINATION — Is the correct answer too obvious?\n"
        "3. TRANSFER DISTANCE (T4 only) — Is T4 context genuinely novel?\n"
        "4. CONSTRUCT PURITY — Could a student fail due to construct-irrelevant factors?\n"
        "5. PATHWAY ORTHOGONALITY (Bo2 only) — Are A and B fundamentally different?\n\n"
        "Output strict JSON with evaluation object, status (APPROVED/REJECTED), and critical_feedback."
    )


def qnorm(p: float) -> float:
    """Approximate inverse normal CDF (probit) using rational approximation."""
    if p <= 0:
        return -3.0
    if p >= 1:
        return 3.0
    if p == 0.5:
        return 0.0
    if p < 0.5:
        t = math.sqrt(-2.0 * math.log(p))
    else:
        t = math.sqrt(-2.0 * math.log(1.0 - p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    result = t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)
    return -result if p < 0.5 else result


def compute_cold_start_params(eqjs_data: dict) -> dict:
    """Compute LLTM cold-start calibration parameters from EQJS metadata."""
    pct = eqjs_data.get("classification", {}).get("asset_percent_correct", 50)
    beta = -1.0 * qnorm(pct / 100.0)
    return {
        "calibration_phase": "A_cold_start",
        "lltm_predicted_params": {
            "alpha": 1.0,
            "beta": round(beta, 4),
            "d_steps": [-0.5, 0.0, 0.5],
        },
        "n_responses": 0,
    }


def call_api(client, system_prompt: str, user_prompt: str, retry: int = 0):
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


def parse_json_response(text: str) -> dict | None:
    """Extract JSON object from API response text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return None


def write_log(log_dir: Path, entry: dict):
    """Append a JSONL log entry."""
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = log_dir / f"{date_str}_run.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def write_bo2_log(entry: dict):
    """Append a Bo2 generation log entry."""
    BO2_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = BO2_LOG_DIR / "bo2_logs.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_stage1(client, eqjs_data: dict) -> dict | None:
    """Stage 1: Q-Matrix Extraction."""
    user_prompt = f"SEED ITEM JSON:\n{json.dumps(eqjs_data, indent=2)}"
    response = call_api(client, STAGE1_SYSTEM, user_prompt)
    if not response:
        return None
    return parse_json_response(response)


def run_stage2_bo2(client, eqjs_data: dict, stage1: dict) -> dict | None:
    """Stage 2-Bo2: Generate two orthogonal candidates."""
    question_text = eqjs_data.get("content", {}).get("question_text", "")
    diagrams = eqjs_data.get("content", {}).get("stimulus", {}).get("diagrams", [])
    user_prompt = (
        f"SEED ITEM TEXT: {question_text}\n"
        f"SEED ITEM DIAGRAMS: {json.dumps(diagrams, indent=2)}\n"
        f"Q-MATRIX JSON: {json.dumps(stage1.get('q_matrix', {}), indent=2)}\n"
        f"TRANSFER DOMAINS: {json.dumps(stage1.get('transfer_domains', []), indent=2)}"
    )
    response = call_api(client, STAGE2_BO2_SYSTEM, user_prompt)
    if not response:
        return None
    return parse_json_response(response)


def run_stage2_single(client, eqjs_data: dict, stage1: dict) -> dict | None:
    """Stage 2-Single: Generate one T3/T4 candidate."""
    question_text = eqjs_data.get("content", {}).get("question_text", "")
    user_prompt = (
        f"SEED ITEM TEXT: {question_text}\n"
        f"Q-MATRIX JSON: {json.dumps(stage1.get('q_matrix', {}), indent=2)}\n"
        f"TRANSFER DOMAINS: {json.dumps(stage1.get('transfer_domains', []), indent=2)}"
    )
    response = call_api(client, STAGE2_SINGLE_SYSTEM, user_prompt)
    if not response:
        return None
    return parse_json_response(response)


def run_stage3_audit(client, eqjs_data: dict, stage1: dict, draft: dict, is_bo2: bool) -> dict | None:
    """Stage 3: Psychometric Audit."""
    question_text = eqjs_data.get("content", {}).get("question_text", "")
    user_prompt = (
        f"ORIGINAL SEED QUESTION: {question_text}\n"
        f"Q-MATRIX: {json.dumps(stage1.get('q_matrix', {}), indent=2)}\n"
        f"PROPOSED T3 AND T4 ITEMS: {json.dumps(draft, indent=2)}\n"
        f"IS_BO2: {str(is_bo2).lower()}"
    )
    response = call_api(client, STAGE3_SYSTEM, user_prompt)
    if not response:
        return None
    return parse_json_response(response)


def run_stage2_with_feedback(client, eqjs_data: dict, stage1: dict, is_bo2: bool,
                             previous_draft: dict, feedback: str) -> dict | None:
    """Re-run Stage 2 with audit feedback appended."""
    question_text = eqjs_data.get("content", {}).get("question_text", "")
    if is_bo2:
        diagrams = eqjs_data.get("content", {}).get("stimulus", {}).get("diagrams", [])
        user_prompt = (
            f"SEED ITEM TEXT: {question_text}\n"
            f"SEED ITEM DIAGRAMS: {json.dumps(diagrams, indent=2)}\n"
            f"Q-MATRIX JSON: {json.dumps(stage1.get('q_matrix', {}), indent=2)}\n"
            f"TRANSFER DOMAINS: {json.dumps(stage1.get('transfer_domains', []), indent=2)}\n\n"
            f"PREVIOUS DRAFT (REJECTED):\n{json.dumps(previous_draft, indent=2)}\n\n"
            f"AUDIT FEEDBACK:\n{feedback}\n\n"
            f"Generate an IMPROVED version addressing the feedback above."
        )
        system = STAGE2_BO2_SYSTEM
    else:
        user_prompt = (
            f"SEED ITEM TEXT: {question_text}\n"
            f"Q-MATRIX JSON: {json.dumps(stage1.get('q_matrix', {}), indent=2)}\n"
            f"TRANSFER DOMAINS: {json.dumps(stage1.get('transfer_domains', []), indent=2)}\n\n"
            f"PREVIOUS DRAFT (REJECTED):\n{json.dumps(previous_draft, indent=2)}\n\n"
            f"AUDIT FEEDBACK:\n{feedback}\n\n"
            f"Generate an IMPROVED version addressing the feedback above."
        )
        system = STAGE2_SINGLE_SYSTEM
    response = call_api(client, system, user_prompt)
    if not response:
        return None
    return parse_json_response(response)


def build_t2_rubric(stage1: dict) -> dict:
    """Build T2 rubric from Stage 1 output."""
    return {
        "scoring_model": "concept_presence_only",
        "correct_concepts": [stage1.get("core_concept", "")],
        "correct_mechanism": stage1.get("mastery_logic", ""),
        "fluency_excluded": True,
    }


def build_scoring_config(stage1: dict) -> dict:
    """Build scoring config."""
    return {
        "joint_score_scale": [0, 1, 2, 3, 4],
        "mastery_gate_threshold": 3,
        "phase2_model": stage1.get("phase2_model", "NRM"),
        "routing_lok_enabled": True,
    }


def build_ainative_output(eqjs_data, stage1, draft, audit, is_bo2, retries):
    """Assemble the full AI-native V8 JSON output."""
    eqjs_id = eqjs_data.get("metadata", {}).get("id", "unknown")
    paper_code = eqjs_data.get("assessment_metadata", {}).get("paper_code", "unknown")
    qno = eqjs_data.get("assessment_metadata", {}).get("original_qno", 0)

    if is_bo2:
        candidates = {
            "generation_type": "Bo2",
            "pathway_A": draft.get("pathway_A_text_abstraction", {}),
            "pathway_B": draft.get("pathway_B_schema_mutation", {}),
            "orthogonality_check": draft.get("orthogonality_check", ""),
        }
        approval_status = "awaiting_human_validation"
    else:
        candidates = {
            "generation_type": "Single",
            "pathway_A": {
                "T3_probe": draft.get("T3_probe", {}),
                "T4_transfer": draft.get("T4_transfer", {}),
            },
        }
        audit_status = audit.get("status", "REJECTED") if audit else "REJECTED"
        approval_status = "auto_approved" if audit_status == "APPROVED" else "failed_audit"

    return {
        "ainative_version": "V8.0",
        "source_eqjs_id": eqjs_id,
        "source_eqjs_file": f"eqjs/{paper_code}/Q{qno}.json",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "approval_status": approval_status,
        "stage1_output": stage1,
        "t2_rubric": build_t2_rubric(stage1),
        "scoring_config": build_scoring_config(stage1),
        "candidates": candidates,
        "audit_result": {
            "status": audit.get("status", "REJECTED") if audit else "REJECTED",
            "retries": retries,
            "evaluation_details": audit.get("evaluation", {}) if audit else {},
        },
        "calibration_config": compute_cold_start_params(eqjs_data),
    }


def find_eqjs_files(item_filter=None):
    """Find all EQJS files, optionally filtered by item ID."""
    files = []
    for paper_dir in sorted(EQJS_DIR.iterdir()):
        if not paper_dir.is_dir() or paper_dir.name == ".gitkeep":
            continue
        for f in sorted(paper_dir.glob("Q*.json")):
            if item_filter:
                item_id = f"{paper_dir.name}_Q{f.stem[1:]}"
                if item_id != item_filter:
                    continue
            files.append(f)
    return files


def get_ainative_path(eqjs_path: Path) -> Path:
    """Map an EQJS file path to its AI-native output path."""
    paper_code = eqjs_path.parent.name
    qno = eqjs_path.stem
    return AINATIVE_DIR / paper_code / f"{qno}_ainative.json"


def process_item(eqjs_path: Path, client, dry_run: bool = False):
    """Process a single EQJS item through the Stage 1-2-3 pipeline."""
    ainative_path = get_ainative_path(eqjs_path)
    if ainative_path.exists():
        print(f"  Already converted: {ainative_path}")
        return

    with open(eqjs_path) as f:
        eqjs_data = json.load(f)

    item_id = eqjs_data.get("metadata", {}).get("id", eqjs_path.stem)
    print(f"  Processing: {item_id}")

    if dry_run:
        print(f"  [DRY RUN] Would process {item_id}")
        write_log(LOG_DIR, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "item_id": item_id,
            "status": "dry_run",
        })
        return

    # Stage 1
    print("  Stage 1: Q-Matrix Extraction...")
    stage1 = run_stage1(client, eqjs_data)
    if not stage1:
        print("  FAILED at Stage 1")
        write_log(LOG_DIR, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "item_id": item_id, "status": "stage1_failed",
        })
        return

    is_bo2 = stage1.get("diagram_dependent", False)
    print(f"  diagram_dependent={is_bo2} -> {'Bo2' if is_bo2 else 'Single'} pathway")

    # Stage 2
    print("  Stage 2: Generating candidates...")
    draft = run_stage2_bo2(client, eqjs_data, stage1) if is_bo2 else run_stage2_single(client, eqjs_data, stage1)
    if not draft:
        print("  FAILED at Stage 2")
        write_log(LOG_DIR, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "item_id": item_id, "status": "stage2_failed",
            "diagram_dependent": is_bo2,
        })
        return

    # Stage 3 with retry loop
    retries = 0
    audit = None
    while retries <= MAX_RETRIES:
        print(f"  Stage 3: Auditing (attempt {retries + 1})...")
        audit = run_stage3_audit(client, eqjs_data, stage1, draft, is_bo2)
        if not audit:
            print("  FAILED at Stage 3 audit call")
            break
        if audit.get("status") == "APPROVED":
            print("  Audit: APPROVED")
            break
        retries += 1
        feedback = audit.get("critical_feedback", "No specific feedback.")
        print(f"  Audit: REJECTED - {feedback}")
        if retries <= MAX_RETRIES:
            print(f"  Regenerating with feedback (retry {retries})...")
            draft = run_stage2_with_feedback(client, eqjs_data, stage1, is_bo2, draft, feedback)
            if not draft:
                print("  FAILED during regeneration")
                break

    # Build and write output
    ainative = build_ainative_output(eqjs_data, stage1, draft, audit, is_bo2, retries)
    ainative_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = ainative_path.with_suffix(".tmp.json")
    with open(temp_path, "w") as f:
        json.dump(ainative, f, indent=2)

    validation = validate_ainative(str(temp_path))
    if not validation["valid"]:
        print(f"  Validation warnings (writing anyway): {validation['errors']}")
    temp_path.rename(ainative_path)
    print(f"  Written: {ainative_path}")

    # Logging
    write_log(LOG_DIR, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "item_id": item_id, "status": "success",
        "diagram_dependent": is_bo2,
        "generation_type": "Bo2" if is_bo2 else "Single",
        "audit_status": audit.get("status", "UNKNOWN") if audit else "UNKNOWN",
        "retries": retries,
        "output_file": str(ainative_path),
        "generator_model": MODEL, "audit_model": MODEL,
    })

    if is_bo2:
        write_bo2_log({
            "log_version": "V8.0", "log_type": "Bo2_generation",
            "item_id": item_id,
            "seed_concept": stage1.get("core_concept", ""),
            "diagram_dependent": True,
            "diagram_mechanism": stage1.get("diagram_mechanism"),
            "stage1_output": {
                "q_matrix": stage1.get("q_matrix", {}),
                "transfer_domains": stage1.get("transfer_domains", []),
                "phase2_model": stage1.get("phase2_model", "NRM"),
                "misconception_ordering": stage1.get("misconception_ordering", "unordered"),
            },
            "generation": {
                "generation_pathway": ["Text-Abstraction", "Schema-Mutation"],
                "candidate_A": draft.get("pathway_A_text_abstraction", {}),
                "candidate_B": draft.get("pathway_B_schema_mutation", {}),
                "orthogonality_check": draft.get("orthogonality_check", ""),
            },
            "audit": {
                "stage3_result": audit.get("status", "UNKNOWN") if audit else "UNKNOWN",
                "retries": retries,
                "evaluation_details": audit.get("evaluation", {}) if audit else {},
            },
            "human_validation": {
                "human_choice": None, "rejection_reason": None,
                "rejection_explanation": None, "q_matrix_alignment_pass": None,
                "q_matrix_alignment_notes": None, "validator_id": None,
                "validation_timestamp": None,
            },
            "rlvr_triple": None,
            "generation_timestamp": datetime.now(timezone.utc).isoformat(),
            "generator_model": MODEL, "audit_model": MODEL,
        })


def main():
    parser = argparse.ArgumentParser(description="Convert EQJS items to AI-native V8 schema")
    parser.add_argument("--item", type=str, help="Process only this item (format: paper_code_Qn)")
    parser.add_argument("--dry-run", action="store_true", help="Don't call API")
    args = parser.parse_args()

    load_v8_prompts()

    if not args.dry_run:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY environment variable not set")
            sys.exit(1)
        client = anthropic.Anthropic(api_key=api_key)
    else:
        client = None

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    eqjs_files = find_eqjs_files(args.item)
    if not eqjs_files:
        print("No EQJS files found to process.")
        return

    print(f"Found {len(eqjs_files)} EQJS file(s) to check.")
    call_count = 0
    minute_start = time.time()

    for eqjs_path in eqjs_files:
        call_count += 4
        if call_count > MAX_CALLS_PER_MINUTE:
            elapsed = time.time() - minute_start
            if elapsed < 60:
                wait = 60 - elapsed
                print(f"  Rate limit: waiting {wait:.1f}s")
                time.sleep(wait)
            call_count = 4
            minute_start = time.time()

        print(f"\n{'=' * 60}")
        process_item(eqjs_path, client, args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
