#!/usr/bin/env python3
"""Validate AI-native V8 JSON files against schema and invariants."""

import json
import sys
from pathlib import Path
from jsonschema import validate, ValidationError

SCHEMA_PATH = Path(__file__).parent.parent / "config" / "ainative-schema-v8.json"


def validate_ainative(filepath: str) -> dict:
    """Validate an AI-native file. Returns {valid, errors, warnings}."""
    errors = []
    warnings = []

    try:
        with open(filepath) as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return {"valid": False, "errors": [str(e)], "warnings": []}

    # Schema validation
    try:
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        validate(instance=data, schema=schema)
    except ValidationError as e:
        errors.append(f"Schema: {e.message}")

    # Q-matrix minimum
    q_matrix = data.get("stage1_output", {}).get("q_matrix", {})
    if len(q_matrix) < 2:
        errors.append("Q-matrix must have at least 2 misconception entries")

    # T2 rubric fluency check
    t2 = data.get("t2_rubric", {})
    if t2.get("fluency_excluded") is not True:
        errors.append("LOCKED: t2_rubric.fluency_excluded must be true")

    # Mastery gate threshold
    sc = data.get("scoring_config", {})
    if sc.get("mastery_gate_threshold") != 3:
        errors.append("LOCKED: mastery_gate_threshold must be 3")

    # Diagram-dependent Bo2 check
    diag = data.get("stage1_output", {}).get("diagram_dependent", False)
    candidates = data.get("candidates", {})
    gen_type = candidates.get("generation_type", "")
    if diag and gen_type != "Bo2":
        errors.append("diagram_dependent=true requires generation_type=Bo2")
    if diag and "pathway_B" not in candidates:
        errors.append("Bo2 items must have both pathway_A and pathway_B")

    # Transfer domains count
    td = data.get("stage1_output", {}).get("transfer_domains", [])
    if len(td) != 3:
        errors.append(f"transfer_domains must have exactly 3 entries, got {len(td)}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_ainative.py <filepath>")
        sys.exit(1)

    result = validate_ainative(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)
