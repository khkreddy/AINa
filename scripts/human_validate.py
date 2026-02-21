#!/usr/bin/env python3
"""
CLI tool for human validation of Bo2 items.

Usage: python scripts/human_validate.py

Interactive flow:
1. Find items with approval_status == "awaiting_human_validation"
2. Display: original question, Q-matrix, candidate A, candidate B
3. Prompt for selection, Q-matrix alignment, rejection reason
4. Update ai-native JSON, copy to ai-native-ready if approved
5. Generate RLVR triple if applicable
6. Log everything to metadata/

Validator ID is MANDATORY. Prompt at session start.
"""

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
AINATIVE_DIR = ROOT / "ai-native"
READY_DIR = ROOT / "ai-native-ready"
EQJS_DIR = ROOT / "eqjs"
APPROVAL_LOG = ROOT / "metadata" / "human-approvals"
BO2_LOG_DIR = ROOT / "metadata" / "bo2-generation-logs"

REJECTION_REASONS = ["Construct_Violation", "Dependency_Failure", "Scale_Misfit", "Other"]


def find_pending_items() -> list[Path]:
    """Find all items awaiting human validation."""
    pending = []
    for paper_dir in sorted(AINATIVE_DIR.iterdir()):
        if not paper_dir.is_dir() or paper_dir.name == ".gitkeep":
            continue
        for f in sorted(paper_dir.glob("*_ainative.json")):
            with open(f) as fh:
                data = json.load(fh)
            if data.get("approval_status") == "awaiting_human_validation":
                pending.append(f)
    return pending


def load_eqjs_source(ainative_data: dict) -> dict | None:
    """Load the original EQJS source for an AI-native item."""
    source_file = ainative_data.get("source_eqjs_file", "")
    if source_file:
        path = ROOT / source_file
        if path.exists():
            with open(path) as f:
                return json.load(f)
    return None


def display_item(ainative_data: dict, eqjs_data: dict | None):
    """Display an item for review."""
    print("\n" + "=" * 70)
    print("ITEM FOR REVIEW")
    print("=" * 70)

    if eqjs_data:
        print("\n--- ORIGINAL QUESTION ---")
        print(f"ID: {eqjs_data.get('metadata', {}).get('id', 'unknown')}")
        print(f"Q: {eqjs_data.get('content', {}).get('question_text', 'N/A')}")
        options = eqjs_data.get("content", {}).get("options", {})
        for k in sorted(options.keys()):
            print(f"  {k}: {options[k]}")
        print(f"Correct: {eqjs_data.get('solution', {}).get('correct_answer', '?')}")

    stage1 = ainative_data.get("stage1_output", {})
    print("\n--- Q-MATRIX ---")
    print(f"Core Concept: {stage1.get('core_concept', 'N/A')}")
    print(f"Mastery Logic: {stage1.get('mastery_logic', 'N/A')}")
    q_matrix = stage1.get("q_matrix", {})
    for mk, mv in q_matrix.items():
        print(f"  {mk} (Option {mv.get('option', '?')}): {mv.get('description', 'N/A')}")

    candidates = ainative_data.get("candidates", {})

    print("\n--- CANDIDATE A (Text-Abstraction) ---")
    pathway_a = candidates.get("pathway_A", {})
    print(json.dumps(pathway_a, indent=2))

    if "pathway_B" in candidates:
        print("\n--- CANDIDATE B (Schema-Mutation) ---")
        pathway_b = candidates.get("pathway_B", {})
        print(json.dumps(pathway_b, indent=2))

    orth = candidates.get("orthogonality_check", "")
    if orth:
        print(f"\nOrthogonality: {orth}")
    print("=" * 70)


def prompt_decision() -> dict:
    """Prompt the validator for their decision."""
    print("\nSelect candidate:")
    print("  A - Candidate A (Text-Abstraction)")
    print("  B - Candidate B (Schema-Mutation)")
    print("  R - Reject both candidates")

    while True:
        choice = input("Your choice [A/B/R]: ").strip().upper()
        if choice in ("A", "B", "R"):
            break
        print("Invalid choice. Enter A, B, or R.")

    if choice == "R":
        return prompt_rejection()

    while True:
        align = input("Q-matrix alignment pass? [y/n]: ").strip().lower()
        if align in ("y", "n"):
            break
        print("Enter y or n.")

    align_pass = align == "y"
    align_notes = ""
    if not align_pass:
        align_notes = input("Alignment notes (explain concerns): ").strip()

    return {
        "human_choice": choice,
        "q_matrix_alignment_pass": align_pass,
        "q_matrix_alignment_notes": align_notes if align_notes else None,
        "rejection_reason": None,
        "rejection_explanation": None,
    }


def prompt_rejection() -> dict:
    """Prompt for rejection details."""
    print("\nRejection reason:")
    for i, reason in enumerate(REJECTION_REASONS, 1):
        print(f"  {i} - {reason}")

    while True:
        try:
            idx = int(input("Reason number: ").strip())
            if 1 <= idx <= len(REJECTION_REASONS):
                break
        except ValueError:
            pass
        print(f"Enter a number 1-{len(REJECTION_REASONS)}.")

    reason = REJECTION_REASONS[idx - 1]
    explanation = input("Explain the rejection: ").strip()

    return {
        "human_choice": None,
        "q_matrix_alignment_pass": False,
        "q_matrix_alignment_notes": None,
        "rejection_reason": reason,
        "rejection_explanation": explanation,
    }


def generate_rlvr_triple(ainative_data: dict, decision: dict) -> dict | None:
    """Generate an RLVR/DPO triple from the human decision."""
    if decision["human_choice"] is None:
        return None
    if not decision["q_matrix_alignment_pass"]:
        return None

    winner = decision["human_choice"]
    loser = "B" if winner == "A" else "A"
    candidates = ainative_data.get("candidates", {})

    return {
        "prompt": f"Stage 2 generation for {ainative_data.get('source_eqjs_id', 'unknown')}",
        "chosen": json.dumps(candidates.get(f"pathway_{winner}", {})),
        "rejected": json.dumps(candidates.get(f"pathway_{loser}", {})),
        "reason_category": decision.get("rejection_reason"),
        "reason_text": decision.get("rejection_explanation"),
    }


def write_approval_log(entry: dict):
    """Append to the approvals log."""
    APPROVAL_LOG.mkdir(parents=True, exist_ok=True)
    log_path = APPROVAL_LOG / "approvals.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def update_bo2_log(item_id: str, decision: dict, validator_id: str, rlvr: dict | None):
    """Update the Bo2 log with human validation results."""
    log_path = BO2_LOG_DIR / "bo2_logs.jsonl"
    if not log_path.exists():
        return

    entries = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    updated = False
    for entry in entries:
        if entry.get("item_id") == item_id:
            entry["human_validation"] = {
                "human_choice": decision["human_choice"],
                "rejection_reason": decision["rejection_reason"],
                "rejection_explanation": decision["rejection_explanation"],
                "q_matrix_alignment_pass": decision["q_matrix_alignment_pass"],
                "q_matrix_alignment_notes": decision["q_matrix_alignment_notes"],
                "validator_id": validator_id,
                "validation_timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if rlvr:
                entry["rlvr_triple"] = rlvr
            updated = True
            break

    if updated:
        with open(log_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")


def process_item(ainative_path: Path, validator_id: str):
    """Process a single item for human validation."""
    with open(ainative_path) as f:
        ainative_data = json.load(f)

    eqjs_data = load_eqjs_source(ainative_data)
    display_item(ainative_data, eqjs_data)
    decision = prompt_decision()
    item_id = ainative_data.get("source_eqjs_id", ainative_path.stem)
    now = datetime.now(timezone.utc).isoformat()
    rlvr = generate_rlvr_triple(ainative_data, decision)

    if decision["human_choice"]:
        # APPROVE
        ainative_data["approval_status"] = "human_approved"
        ainative_data["candidates"]["selected_candidate"] = decision["human_choice"]
        ainative_data["human_validation"] = {
            **decision, "validator_id": validator_id, "validation_timestamp": now,
        }
        with open(ainative_path, "w") as f:
            json.dump(ainative_data, f, indent=2)

        paper_code = ainative_path.parent.name
        ready_dir = READY_DIR / paper_code
        ready_dir.mkdir(parents=True, exist_ok=True)
        approved_name = ainative_path.stem.replace("_ainative", "_approved") + ".json"
        ready_path = ready_dir / approved_name
        shutil.copy2(ainative_path, ready_path)
        print(f"\n  APPROVED: Candidate {decision['human_choice']}")
        print(f"  Copied to: {ready_path}")
    else:
        # REJECT
        ainative_data["approval_status"] = "rejected"
        ainative_data["human_validation"] = {
            **decision, "validator_id": validator_id, "validation_timestamp": now,
        }
        with open(ainative_path, "w") as f:
            json.dump(ainative_data, f, indent=2)
        print(f"\n  REJECTED: {decision['rejection_reason']} - {decision['rejection_explanation']}")

    write_approval_log({
        "timestamp": now, "item_id": item_id, "validator_id": validator_id,
        "decision": decision, "rlvr_generated": rlvr is not None,
        "output_file": str(ainative_path),
    })
    update_bo2_log(item_id, decision, validator_id, rlvr)


def main():
    print("=" * 70)
    print("PRISM V8 - Human Validation CLI")
    print("=" * 70)

    validator_id = input("\nEnter your Validator ID (format VAL-xxx): ").strip()
    if not validator_id:
        print("ERROR: Validator ID is mandatory.")
        sys.exit(1)

    pending = find_pending_items()
    if not pending:
        print("\nNo items awaiting human validation.")
        return

    print(f"\nFound {len(pending)} item(s) awaiting validation.")
    for i, path in enumerate(pending, 1):
        print(f"\n[{i}/{len(pending)}] {path.name}")
        process_item(path, validator_id)
        if i < len(pending):
            cont = input("\nContinue to next item? [y/n]: ").strip().lower()
            if cont != "y":
                print("Session ended.")
                break

    print(f"\nValidation session complete. Validator: {validator_id}")


if __name__ == "__main__":
    main()
