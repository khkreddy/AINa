# CLAUDE.md — Instructions for Claude Code

## Project: prism-assessment-engine

You are building the execution infrastructure for the PRISM V8 AI-native
diagnostic assessment engine. This is a production system for converting
science exam questions into IRT-calibrated diagnostic assessments.

---

## Architecture Overview

```
raw/ → [daily cron] → eqjs/ → [daily cron] → ai-native/ → [human review] → ai-native-ready/
```

Each conversion step is governed by a skill document in `skills/`.
Diagram encoding is governed by protocols in `protocols/`.
All operations are logged to `metadata/`.

---

## Critical Rules

1. **Never modify files in `protocols/`.** These are frozen specifications.
   Read them. Follow them. Do not edit them.

2. **Never modify files in `raw/`.** These are source-of-truth human inputs.

3. **Every file write to `eqjs/`, `ai-native/`, or `ai-native-ready/`
   MUST pass schema validation first.** Use the validators in `scripts/`.

4. **Every operation MUST produce a log entry.** No silent operations.
   Logs go to `metadata/` in JSONL format (one JSON object per line).

5. **Diagram handling requires protocol loading.** Before encoding any
   diagram, load the relevant protocol from `protocols/` using the
   trigger matching in `skills/SKILL-protocol-selection.md`.

6. **Bo2 items require BOTH pathways.** Pathway A (Text-Abstraction)
   and Pathway B (Schema-Mutation) must be genuinely orthogonal.
   See `skills/SKILL-eqjs-to-ainative.md` §4.

7. **The T2 scoring rubric excludes fluency.** Score ONLY on scientific
   concept presence and correctness. See V8 §5.1.

8. **"I am not sure" is a routing signal, not an NRM category.**
   Tag it as `routing_LoK`. If selected, bypass T4 and classify as
   Lack of Knowledge.

---

## File Locations

| What | Where | Format |
|------|-------|--------|
| Raw questions | `raw/{paper_code}/` | .md, .json |
| EQJS output | `eqjs/{paper_code}/Q{n}.json` | EQJS-2.0 JSON |
| AI-native output | `ai-native/{paper_code}/Q{n}_ainative.json` | V8 AI-native JSON |
| Approved items | `ai-native-ready/{paper_code}/Q{n}_approved.json` | Same as ai-native |
| Protocols | `protocols/*.md` | Markdown (read-only) |
| Skills | `skills/*.md` | Markdown (read for guidance) |
| Working state | `config/working-state-capsule.md` | Markdown |
| JSON schemas | `config/*.json` | JSON Schema |
| Scripts | `scripts/*.py` | Python 3.10+ |
| Logs | `metadata/**/*.jsonl` | JSONL |

---

## Dependencies

```
pip install anthropic jsonschema
```

Environment variable required: `ANTHROPIC_API_KEY`

---

## Script Specifications

### scripts/validate_eqjs.py

```python
def validate_eqjs(filepath: str) -> dict:
    """
    Validate an EQJS-2.0 JSON file.
    
    Returns: {
        "valid": bool,
        "errors": list[str],
        "warnings": list[str]
    }
    
    Checks:
    - JSON Schema compliance against config/eqjs-schema-2.0.json
    - MCQ-INV-001: exactly 4 options with keys A, B, C, D
    - ANSWER-INV-001: correct_answer is one of A, B, C, D
    - If stimulus.diagrams exists: protocol field must be non-empty
      and reference a protocol in protocols/protocol-registry.json
    - common_errors must have entries for all incorrect options
    - percent_correct and option_distribution must sum correctly
    """
```

### scripts/validate_ainative.py

```python
def validate_ainative(filepath: str) -> dict:
    """
    Validate a V8 AI-native JSON file.
    
    Returns: {
        "valid": bool,
        "errors": list[str],
        "warnings": list[str]
    }
    
    Checks:
    - JSON Schema compliance against config/ainative-schema-v8.json
    - q_matrix has >= 2 misconception entries
    - All T3 options map to: q_matrix key, "Mastery", or "routing_LoK"
    - All T4 options map to: q_matrix key or "Mastery"
    - T4 does NOT have a routing_LoK option
    - If diagram_dependent: both pathway_A and pathway_B must exist
    - If not diagram_dependent: only pathway_A (or single candidate)
    - audit_result.status == "APPROVED" for auto_approved items
    - calibration_config.alpha == 1.0 (cold start default)
    - t2_rubric.fluency_excluded == true (locked decision)
    """
```

### scripts/run_raw_to_eqjs.py

```python
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
   c. Detect diagram → load protocol if needed
   d. Call Anthropic API with assembled prompt
   e. Parse and validate response
   f. Write to eqjs/ if valid
   g. Log to metadata/conversion-logs/raw-to-eqjs/

Rate limit: max 10 API calls per minute.
Retry: 3 attempts with exponential backoff on API errors.
"""
```

### scripts/run_eqjs_to_ainative.py

```python
"""
Daily cron script: convert new EQJS items to AI-native schema.

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

Stage prompts: Use V8 §1.1, §2A.1, §2B.1, §3.1 VERBATIM.
Do not modify prompt text. The prompts are frozen.
"""
```

### scripts/human_validate.py

```python
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
```

### scripts/convert_bo2_to_dpo.py

```python
"""
Convert Bo2 generation logs to DPO training triples.

Usage: python scripts/convert_bo2_to_dpo.py --output FILE

Filters:
- Only entries with human_choice not null
- Only entries with q_matrix_alignment_pass == true

Output: JSONL with {prompt, chosen, rejected, reason_category, reason_text}
"""
```

### scripts/automation_readiness.py

```python
"""
Check if automation criteria are met for V2 transition.

Usage: python scripts/automation_readiness.py

Criteria:
1. >= 1,000 validated Bo2 pairs
2. Reward model >= 85% agreement (if model exists)
3. Override rate < 5% in last 100 items

Output: Status report to stdout.
"""
```

---

## JSON Schema Specifications

### config/eqjs-schema-2.0.json

Must validate all EQJS fields including:
- metadata (id, source, protocol_conformance, validation_status)
- classification (subject, topic, difficulty, cognitive_level, etc.)
- content (question_text, question_format, options, stimulus)
- solution (correct_answer, marking_scheme, common_errors)
- semantic (concepts, prerequisites, reasoning_type)
- assessment_metadata (paper_code, skill_no, percent_correct, etc.)

### config/ainative-schema-v8.json

Must validate all AI-native fields including:
- ainative_version (must be "V8.0")
- source_eqjs_id, approval_status
- stage1_output (q_matrix, transfer_domains, diagram_dependent, etc.)
- t2_rubric (fluency_excluded must be true)
- scoring_config (joint_score_scale, mastery_gate_threshold, etc.)
- candidates (generation_type, pathways, CoT traces)
- audit_result (status, all 5/6 criteria, retries)
- calibration_config (phase, lltm_predicted_params)

---

## Testing

After building each script:
1. Run on 2-3 sample items from the existing EQJS examples
2. Verify output passes schema validation
3. Verify log entries are written correctly
4. Verify file locations match the directory structure

End-to-end test:
```bash
# 1. Place a raw question in raw/test_paper/
# 2. Run conversion
python scripts/run_raw_to_eqjs.py --paper test_paper
# 3. Verify EQJS output
python scripts/validate_eqjs.py eqjs/test_paper/Q1.json
# 4. Run AI-native conversion
python scripts/run_eqjs_to_ainative.py --item test_paper_Q1
# 5. Verify AI-native output
python scripts/validate_ainative.py ai-native/test_paper/Q1_ainative.json
# 6. Run human validation
python scripts/human_validate.py
# 7. Check logs
cat metadata/conversion-logs/raw-to-eqjs/*.jsonl | python -m json.tool
```

---

## What NOT To Do

- Do NOT add features not in this spec
- Do NOT modify protocol files
- Do NOT modify raw input files
- Do NOT skip validation before writing output files
- Do NOT make API calls without rate limiting
- Do NOT write files without logging the operation
- Do NOT hardcode API keys (use environment variables)
- Do NOT create a web UI (CLI only for now)
- Do NOT implement the scoring engine (§5-§7 of V8 manual) — that's Phase 2
- Do NOT implement calibration modules — that's Phase 2
