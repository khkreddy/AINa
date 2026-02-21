#!/usr/bin/env python3
"""
Convert Bo2 generation logs to DPO training triples.

Usage: python scripts/convert_bo2_to_dpo.py --output FILE

Filters:
- Only entries with human_choice not null
- Only entries with q_matrix_alignment_pass == true

Output: JSONL with {prompt, chosen, rejected, reason_category, reason_text}
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
BO2_LOG_PATH = ROOT / "metadata" / "bo2-generation-logs" / "bo2_logs.jsonl"


def load_bo2_logs() -> list[dict]:
    """Load all Bo2 generation log entries."""
    if not BO2_LOG_PATH.exists():
        return []
    entries = []
    with open(BO2_LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def convert_to_dpo_triples(entries: list[dict]) -> list[dict]:
    """Filter and convert Bo2 log entries to DPO triples."""
    triples = []
    skipped_no_choice = 0
    skipped_no_alignment = 0

    for entry in entries:
        if entry.get("log_type") != "Bo2_generation":
            continue

        hv = entry.get("human_validation", {})
        human_choice = hv.get("human_choice")
        if human_choice is None:
            skipped_no_choice += 1
            continue

        if not hv.get("q_matrix_alignment_pass", False):
            skipped_no_alignment += 1
            continue

        winner_key = human_choice
        loser_key = "B" if winner_key == "A" else "A"

        generation = entry.get("generation", {})
        winner_data = generation.get(f"candidate_{winner_key}", {})
        loser_data = generation.get(f"candidate_{loser_key}", {})

        prompt_parts = [
            f"Item: {entry.get('item_id', 'unknown')}",
            f"Core concept: {entry.get('seed_concept', '')}",
            f"Diagram mechanism: {entry.get('diagram_mechanism', 'N/A')}",
            f"Q-Matrix: {json.dumps(entry.get('stage1_output', {}).get('q_matrix', {}))}",
            f"Transfer domains: {json.dumps(entry.get('stage1_output', {}).get('transfer_domains', []))}",
        ]

        triples.append({
            "prompt": "\n".join(prompt_parts),
            "chosen": json.dumps(winner_data),
            "rejected": json.dumps(loser_data),
            "reason_category": hv.get("rejection_reason"),
            "reason_text": hv.get("rejection_explanation"),
        })

    print(f"Processed {len(entries)} log entries:")
    print(f"  Valid triples: {len(triples)}")
    print(f"  Skipped (no human choice): {skipped_no_choice}")
    print(f"  Skipped (alignment fail): {skipped_no_alignment}")

    return triples


def main():
    parser = argparse.ArgumentParser(description="Convert Bo2 logs to DPO training triples")
    parser.add_argument("--output", type=str, required=True, help="Output JSONL file path")
    args = parser.parse_args()

    entries = load_bo2_logs()
    if not entries:
        print("No Bo2 log entries found.")
        sys.exit(0)

    triples = convert_to_dpo_triples(entries)
    if not triples:
        print("No valid DPO triples generated.")
        sys.exit(0)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for triple in triples:
            f.write(json.dumps(triple) + "\n")

    print(f"\nWritten {len(triples)} DPO triples to {output_path}")


if __name__ == "__main__":
    main()
