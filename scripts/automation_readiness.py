#!/usr/bin/env python3
"""
Check if automation criteria are met for V2 transition.

Usage: python scripts/automation_readiness.py

Criteria:
1. >= 1,000 validated Bo2 pairs
2. Reward model >= 85% agreement (if model exists)
3. Override rate < 5% in last 100 items

Output: Status report to stdout.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
BO2_LOG_PATH = ROOT / "metadata" / "bo2-generation-logs" / "bo2_logs.jsonl"
APPROVAL_LOG_PATH = ROOT / "metadata" / "human-approvals" / "approvals.jsonl"
REWARD_MODEL_PATH = ROOT / "metadata" / "calibration" / "reward-model-metrics.json"


def load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file into a list of dicts."""
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def check_criterion_1() -> tuple[bool, int]:
    """Check: >= 1,000 validated Bo2 pairs with q_matrix_alignment_pass."""
    entries = load_jsonl(BO2_LOG_PATH)
    validated_count = 0
    for entry in entries:
        if entry.get("log_type") != "Bo2_generation":
            continue
        hv = entry.get("human_validation", {})
        if hv.get("human_choice") is not None and hv.get("q_matrix_alignment_pass", False):
            validated_count += 1
    return validated_count >= 1000, validated_count


def check_criterion_2() -> tuple[bool, float | None]:
    """Check: Reward model >= 85% agreement (if model exists)."""
    if not REWARD_MODEL_PATH.exists():
        return False, None
    with open(REWARD_MODEL_PATH) as f:
        metrics = json.load(f)
    agreement = metrics.get("agreement_rate", 0)
    return agreement >= 0.85, agreement


def check_criterion_3() -> tuple[bool, float]:
    """Check: Override rate < 5% in last 100 items."""
    entries = load_jsonl(APPROVAL_LOG_PATH)
    if not entries:
        return False, 0.0

    recent = entries[-100:]
    if len(recent) == 0:
        return False, 0.0

    overrides = 0
    for entry in recent:
        decision = entry.get("decision", {})
        if decision.get("rejection_reason") is not None:
            overrides += 1

    rate = overrides / len(recent)
    return rate < 0.05, rate


def main():
    print("=" * 60)
    print("PRISM V8 - Automation Readiness Report")
    print("=" * 60)

    c1_pass, c1_count = check_criterion_1()
    status1 = "PASS" if c1_pass else "FAIL"
    print(f"\n[{status1}] Criterion 1: Validated Bo2 pairs >= 1,000")
    print(f"       Current: {c1_count} / 1,000")

    c2_pass, c2_agreement = check_criterion_2()
    status2 = "PASS" if c2_pass else "FAIL"
    if c2_agreement is None:
        print(f"\n[{status2}] Criterion 2: Reward model agreement >= 85%")
        print(f"       Current: No reward model found")
    else:
        print(f"\n[{status2}] Criterion 2: Reward model agreement >= 85%")
        print(f"       Current: {c2_agreement * 100:.1f}%")

    c3_pass, c3_rate = check_criterion_3()
    status3 = "PASS" if c3_pass else "FAIL"
    print(f"\n[{status3}] Criterion 3: Override rate < 5% in last 100 items")
    print(f"       Current: {c3_rate * 100:.1f}%")

    all_pass = c1_pass and c2_pass and c3_pass
    print(f"\n{'=' * 60}")
    if all_pass:
        print("RESULT: ALL CRITERIA MET - Ready for automation transition")
    else:
        failed = []
        if not c1_pass:
            failed.append("Volume")
        if not c2_pass:
            failed.append("Reward Model")
        if not c3_pass:
            failed.append("Override Rate")
        print(f"RESULT: NOT READY - Failed: {', '.join(failed)}")
    print("=" * 60)

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
