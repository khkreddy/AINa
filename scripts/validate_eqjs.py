#!/usr/bin/env python3
"""Validate EQJS-2.0 JSON files against schema and invariants."""

import json
import sys
from pathlib import Path
from jsonschema import validate, ValidationError

SCHEMA_PATH = Path(__file__).parent.parent / "config" / "eqjs-schema-2.0.json"
REGISTRY_PATH = Path(__file__).parent.parent / "protocols" / "protocol-registry.json"


def load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def load_registry():
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def validate_eqjs(filepath: str) -> dict:
    """Validate an EQJS file. Returns {valid, errors, warnings}."""
    errors = []
    warnings = []

    try:
        with open(filepath) as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return {"valid": False, "errors": [str(e)], "warnings": []}

    # Schema validation
    try:
        schema = load_schema()
        validate(instance=data, schema=schema)
    except ValidationError as e:
        errors.append(f"Schema: {e.message}")

    # MCQ-INV-001: exactly 4 options
    options = data.get("content", {}).get("options", {})
    if set(options.keys()) != {"A", "B", "C", "D"}:
        errors.append("MCQ-INV-001: options must have exactly keys A, B, C, D")

    # ANSWER-INV-001: correct answer is valid
    correct = data.get("solution", {}).get("correct_answer", "")
    if correct not in {"A", "B", "C", "D"}:
        errors.append(f"ANSWER-INV-001: correct_answer '{correct}' not in A/B/C/D")

    # Protocol check for diagrams
    stimulus = data.get("content", {}).get("stimulus", {})
    diagrams = stimulus.get("diagrams", [])
    if diagrams:
        registry = load_registry()
        valid_protocols = {p["id"] for p in registry.get("protocols", [])}
        for diag in diagrams:
            proto = diag.get("protocol", "")
            if proto and proto not in valid_protocols:
                errors.append(f"Unknown protocol '{proto}' in diagram '{diag.get('diagram_id')}'")
            if not proto:
                warnings.append(f"Diagram '{diag.get('diagram_id')}' has no protocol declared")

    # Common errors check
    common_errors = data.get("solution", {}).get("common_errors", [])
    incorrect_options = {k for k in options if k != correct}
    covered = {ce.get("incorrect_answer") for ce in common_errors}
    missing = incorrect_options - covered
    if missing:
        warnings.append(f"Missing common_errors for options: {missing}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_eqjs.py <filepath>")
        sys.exit(1)

    result = validate_eqjs(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)
