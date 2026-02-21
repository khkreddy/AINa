# PRISM V8 — Repository Setup & Claude Code Implementation Guide

## Repository: `prism-assessment-engine`

---

## §1 Directory Structure

```
prism-assessment-engine/
│
├── README.md                          # This file
├── .github/
│   └── workflows/
│       ├── raw-to-eqjs.yml           # Daily cron: raw → EQJS conversion
│       └── eqjs-to-ainative.yml      # Daily cron: EQJS → AI-native schema
│
├── raw/                               # Human input questions (source of truth)
│   ├── Ei_ASSET_Sci_3A124/           # One folder per paper
│   │   ├── questions.md              # Raw question text + images
│   │   ├── statistics.json           # Per-question stats from exam board
│   │   └── examiner_comments.md      # Optional examiner remarks
│   ├── Ei_ASSET_Sci_38124/
│   └── ...
│
├── eqjs/                              # EQJS-2.0 JSON (machine-readable)
│   ├── Ei_ASSET_Sci_3A124/
│   │   ├── Q1.json                   # One JSON per question
│   │   ├── Q2.json
│   │   └── ...
│   ├── Ei_ASSET_Sci_38124/
│   └── ...
│
├── protocols/                         # Diagram encoding protocols (frozen)
│   ├── CESP-1.0.md                   # Chemical Experiment Setup Protocol
│   ├── PDDC-1.0.md                   # Phase Diagram Data Chart Protocol
│   ├── TS-PG-1.2.md                  # Time-Series Parametric Graph Protocol
│   ├── GRP-STACKED-1.0.md           # Stacked Bar Chart Protocol
│   ├── UCCP-1.1.md                   # Connectivity Diagram Protocol
│   └── protocol-registry.json        # Master list of all protocols + versions
│
├── ai-native/                         # AI-native assessment schema (generated)
│   ├── Ei_ASSET_Sci_3A124/
│   │   ├── Q1_ainative.json          # Full cascade: Q-matrix + T3 + T4
│   │   └── ...
│   └── ...
│
├── ai-native-ready/                   # Human-approved, deployable questions
│   ├── Ei_ASSET_Sci_3A124/
│   │   ├── Q1_approved.json
│   │   └── ...
│   └── ...
│
├── metadata/                          # All logs, profiles, performance data
│   ├── conversion-logs/
│   │   ├── raw-to-eqjs/
│   │   │   └── 2026-02-21_run.jsonl  # One log per daily run
│   │   └── eqjs-to-ainative/
│   │       └── 2026-02-21_run.jsonl
│   ├── human-approvals/
│   │   └── approvals.jsonl           # Append-only approval log
│   ├── bo2-generation-logs/
│   │   └── bo2_logs.jsonl            # RLVR/DPO-ready generation logs
│   ├── calibration/
│   │   ├── item-params/              # Per-item calibration records
│   │   ├── lltm-weights.json         # LLTM design matrix weights
│   │   └── mixture-class-params.json # Mixture IRT class parameters
│   ├── student-profiles/
│   │   └── profiles.jsonl            # Per-student θ history
│   └── performance-data/
│       └── sessions.jsonl            # Per-session response records
│
├── skills/                            # Skill documents for Claude/agents
│   ├── SKILL-raw-to-eqjs.md         # Raw → EQJS conversion skill
│   ├── SKILL-eqjs-to-ainative.md    # EQJS → AI-native skill
│   ├── SKILL-human-validation.md    # HITL validation skill
│   └── SKILL-protocol-selection.md  # Protocol selection decision tree
│
├── scripts/                           # Automation scripts
│   ├── run_raw_to_eqjs.py           # Daily cron script
│   ├── run_eqjs_to_ainative.py      # Daily cron script
│   ├── convert_bo2_to_dpo.py        # Log → DPO triple converter
│   ├── validate_eqjs.py             # EQJS schema validator
│   └── automation_readiness.py      # Check V2 automation criteria
│
└── config/
    ├── eqjs-schema-2.0.json         # JSON Schema for validation
    ├── ainative-schema-v8.json       # JSON Schema for AI-native output
    └── working-state-capsule.md      # Working state for raw→EQJS sessions
```

---

## §2 Daily Cron Jobs

### §2.1 Raw → EQJS (runs every 24 hours)

**Trigger:** New or modified files in `raw/` not yet present in `eqjs/`.

```yaml
# .github/workflows/raw-to-eqjs.yml
name: Raw to EQJS Conversion
on:
  schedule:
    - cron: '0 2 * * *'   # 2:00 AM UTC daily
  workflow_dispatch:        # Manual trigger

jobs:
  convert:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Detect new raw questions
        run: python scripts/run_raw_to_eqjs.py
      - name: Commit EQJS outputs
        run: |
          git add eqjs/ metadata/conversion-logs/
          git commit -m "auto: raw→eqjs $(date +%Y-%m-%d)" || true
          git push
```

**Script logic (`run_raw_to_eqjs.py`):**

```python
"""
Scans raw/ for papers not yet in eqjs/.
For each new paper:
  1. Load working-state-capsule.md as system context
  2. Load paper-specific statistics.json and examiner_comments.md
  3. Load relevant protocols from protocols/
  4. Call Claude API with working state + raw question
  5. Validate output against eqjs-schema-2.0.json
  6. Write to eqjs/{paper_code}/Q{n}.json
  7. Log to metadata/conversion-logs/raw-to-eqjs/{date}_run.jsonl
"""
```

### §2.2 EQJS → AI-Native (runs every 24 hours)

**Trigger:** New EQJS files not yet present in `ai-native/`.

```yaml
# .github/workflows/eqjs-to-ainative.yml
name: EQJS to AI-Native Conversion
on:
  schedule:
    - cron: '0 4 * * *'   # 4:00 AM UTC daily (after EQJS run)
  workflow_dispatch:

jobs:
  convert:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Generate AI-native schemas
        run: python scripts/run_eqjs_to_ainative.py
      - name: Commit outputs
        run: |
          git add ai-native/ metadata/conversion-logs/ metadata/bo2-generation-logs/
          git commit -m "auto: eqjs→ainative $(date +%Y-%m-%d)" || true
          git push
```

**Script logic (`run_eqjs_to_ainative.py`):**

```python
"""
Scans eqjs/ for items not yet in ai-native/.
For each new EQJS item:
  1. Run Stage 1 (Q-Matrix Extraction) — V8 §1
  2. Check diagram_dependent flag
  3. IF diagram_dependent:
       Run Stage 2-Bo2 (V8 §2A) → two candidates
       Run Stage 3 Audit (V8 §3) on both
       Write to ai-native/ with status: "awaiting_human_validation"
       Log full Bo2 record to metadata/bo2-generation-logs/
     ELSE:
       Run Stage 2-Single (V8 §2B) → one candidate
       Run Stage 3 Audit (V8 §3)
       IF APPROVED: write to ai-native/ with status: "auto_approved"
       IF FAILED: write with status: "failed_audit" + feedback
  4. Log to metadata/conversion-logs/eqjs-to-ainative/{date}_run.jsonl
"""
```

---

## §3 Conversion Log Schema

### §3.1 Raw → EQJS Log Entry

```json
{
  "timestamp": "2026-02-21T02:14:33Z",
  "run_id": "run-2026-02-21",
  "paper_code": "Ei_ASSET_Sci_38124",
  "question_id": "Ei_ASSET_Sci_38124_Q3",
  "status": "success | failed | skipped",
  "input_file": "raw/Ei_ASSET_Sci_38124/questions.md",
  "output_file": "eqjs/Ei_ASSET_Sci_38124/Q3.json",
  "protocols_used": ["CESP-1.0", "EQJS-2.0"],
  "validation_result": {
    "schema_valid": true,
    "invariants_checked": ["MCQ-INV-001", "ANSWER-INV-001"],
    "warnings": []
  },
  "model_used": "claude-sonnet-4-5",
  "duration_seconds": 12.4,
  "error": null
}
```

### §3.2 EQJS → AI-Native Log Entry

```json
{
  "timestamp": "2026-02-21T04:22:10Z",
  "run_id": "run-2026-02-21",
  "item_id": "Ei_ASSET_Sci_38124_Q3",
  "eqjs_source": "eqjs/Ei_ASSET_Sci_38124/Q3.json",
  "diagram_dependent": true,
  "generation_type": "Bo2 | Single",
  "stage1_status": "success",
  "stage2_status": "success",
  "stage3_status": "APPROVED | REJECTED",
  "stage3_retries": 1,
  "output_file": "ai-native/Ei_ASSET_Sci_38124/Q3_ainative.json",
  "approval_status": "awaiting_human_validation | auto_approved | failed_audit",
  "bo2_log_file": "metadata/bo2-generation-logs/bo2_logs.jsonl",
  "model_used": "claude-sonnet-4-5",
  "duration_seconds": 34.7,
  "error": null
}
```

### §3.3 Human Approval Log Entry

```json
{
  "timestamp": "2026-02-21T10:15:00+05:30",
  "item_id": "Ei_ASSET_Sci_38124_Q3",
  "source_file": "ai-native/Ei_ASSET_Sci_38124/Q3_ainative.json",
  "output_file": "ai-native-ready/Ei_ASSET_Sci_38124/Q3_approved.json",
  "validator_id": "VAL-017",
  "action": "approved | rejected | revision_requested",
  "human_choice": "A",
  "rejection_reason": null,
  "q_matrix_alignment_pass": true,
  "notes": "Free text",
  "bo2_rlvr_triple_generated": true
}
```

---

## §4 Protocol Registry

```json
{
  "protocol_registry_version": "1.0",
  "protocols": [
    {
      "id": "CESP-1.0",
      "name": "Chemical Experiment Setup Protocol",
      "status": "DRAFT",
      "file": "protocols/CESP-1.0.md",
      "scope": "Chemistry lab apparatus diagrams (2D front-view)",
      "triggers": ["apparatus", "experiment setup", "lab diagram", "distillation",
                    "titration", "electrolysis", "gas collection", "filtration"]
    },
    {
      "id": "PDDC-1.0",
      "name": "Phase Diagram Data Chart Protocol",
      "status": "FROZEN",
      "file": "protocols/PDDC-1.0.md",
      "scope": "Phase diagrams, ternary plots, region-partitioned scientific charts",
      "triggers": ["phase diagram", "triple point", "phase boundary",
                    "solid liquid gas", "soil texture triangle"]
    },
    {
      "id": "TS-PG-1.2",
      "name": "Time-Series Parametric Graph Protocol",
      "status": "FROZEN",
      "file": "protocols/TS-PG-1.2.md",
      "scope": "Periodic/seasonal time-series graphs with parametric equations",
      "triggers": ["seasonal graph", "temperature over months", "periodic curve",
                    "sinusoidal", "time series"]
    },
    {
      "id": "GRP-STACKED-1.0",
      "name": "Stacked Bar/Area Chart Protocol",
      "status": "FROZEN",
      "file": "protocols/GRP-STACKED-1.0.md",
      "scope": "Stacked bar charts, grouped bar charts, area charts",
      "triggers": ["stacked bar", "grouped chart", "bar graph with categories"]
    }
  ]
}
```

---

## §5 AI-Native Schema (per question)

This is the output format for files in `ai-native/` and `ai-native-ready/`.

```json
{
  "ainative_version": "V8.0",
  "source_eqjs_id": "Ei_ASSET_Sci_38124_Q3",
  "source_eqjs_file": "eqjs/Ei_ASSET_Sci_38124/Q3.json",
  "generated_at": "2026-02-21T04:22:10Z",
  "approval_status": "awaiting_human_validation | auto_approved | human_approved | failed_audit",

  "stage1_output": {
    "core_concept": "...",
    "mastery_logic": "...",
    "diagram_dependent": true,
    "diagram_mechanism": "...",
    "misconception_ordering": "unordered",
    "phase2_model": "NRM",
    "q_matrix": {
      "M1": {"option": "A", "description": "...", "attribute_profile": [1,0,0]},
      "M2": {"option": "B", "description": "...", "attribute_profile": [0,1,0]}
    },
    "transfer_domains": [
      {"domain": "...", "seed": "...", "preserves_mechanism": "..."}
    ]
  },

  "t2_rubric": {
    "scoring_model": "concept_presence_only",
    "correct_concepts": ["list of concepts that must be present"],
    "correct_mechanism": "the causal chain that earns score 3",
    "fluency_excluded": true
  },

  "scoring_config": {
    "joint_score_scale": [0, 1, 2, 3],
    "mastery_gate_threshold": 3,
    "phase2_model": "NRM",
    "routing_lok_enabled": true
  },

  "candidates": {
    "generation_type": "Bo2 | Single",
    "pathway_A": {
      "pathway_type": "Text-Abstraction",
      "T3_probe": { "...V8 §2A output format..." },
      "T4_transfer": { "...V8 §2A output format..." },
      "CoT_trace": "..."
    },
    "pathway_B": {
      "pathway_type": "Schema-Mutation",
      "T3_probe": { "...with structured_description..." },
      "T4_transfer": { "...with structured_description..." },
      "CoT_trace": "..."
    },
    "orthogonality_check": "...",
    "selected_candidate": null
  },

  "audit_result": {
    "status": "APPROVED | REJECTED",
    "evaluation": {
      "T3_purity_pass": true,
      "T3_discrimination_pass": true,
      "T4_transfer_distance_pass": true,
      "T4_purity_pass": true,
      "construct_purity_pass": true,
      "orthogonality_pass": true
    },
    "retries": 1,
    "critical_feedback": ""
  },

  "calibration_config": {
    "calibration_phase": "A_cold_start",
    "lltm_predicted_params": {
      "alpha": 1.0,
      "beta": -0.34,
      "d_steps": [-0.5, 0.0, 0.5]
    },
    "n_responses": 0
  }
}
```

---

## §6 Claude Code Implementation Instructions

### §6.1 Phase 1: Repository Scaffold (Day 1)

```
TASK: Initialize the prism-assessment-engine repository.

STEPS:
1. Create the full directory structure as specified in §1 above.
2. Create empty placeholder files:
   - config/eqjs-schema-2.0.json (JSON Schema for EQJS validation)
   - config/ainative-schema-v8.json (JSON Schema for AI-native output)
   - config/working-state-capsule.md (copy from uploaded working state capsule)
3. Copy all protocol files into protocols/:
   - CESP-1.0.md
   - PDDC-1.0.md
   - TS-PG-1.2.md
4. Create protocols/protocol-registry.json as specified in §4.
5. Create all four skill documents in skills/ (contents in §7 below).
6. Initialize git, create .gitignore:
   - Ignore: __pycache__, .env, *.pyc, node_modules/
   - Track: everything else including .jsonl log files
7. Create README.md with project overview and directory guide.

DO NOT create any Python scripts yet. Structure only.
```

### §6.2 Phase 2: Validation Scripts (Day 1-2)

```
TASK: Build the EQJS and AI-native schema validators.

FILE: scripts/validate_eqjs.py
FUNCTION: validate_eqjs(filepath) -> ValidationResult
- Load JSON from filepath
- Check against config/eqjs-schema-2.0.json
- Check invariants:
  - MCQ-INV-001: exactly 4 options (A, B, C, D)
  - ANSWER-INV-001: correct_answer is one of the option keys
  - If stimulus.diagrams exists: protocol field must reference a valid
    protocol from protocol-registry.json
- Return: {valid: bool, errors: [], warnings: []}

FILE: scripts/validate_ainative.py
FUNCTION: validate_ainative(filepath) -> ValidationResult
- Load JSON from filepath
- Check against config/ainative-schema-v8.json
- Check:
  - q_matrix has at least 2 misconceptions
  - All T3 options map to a q_matrix entry or "routing_LoK" or "Mastery"
  - All T4 options map to a q_matrix entry or "Mastery"
  - If diagram_dependent: candidates must have both pathway_A and pathway_B
  - If not diagram_dependent: candidates must have pathway_A only
  - audit_result.status must be "APPROVED"
- Return: {valid: bool, errors: [], warnings: []}
```

### §6.3 Phase 3: Raw → EQJS Pipeline Script (Day 2-3)

```
TASK: Build the daily raw → EQJS conversion script.

FILE: scripts/run_raw_to_eqjs.py

LOGIC:
1. Scan raw/ for all paper folders.
2. For each paper folder:
   a. List all question numbers expected (from statistics.json or 
      questions.md structure).
   b. Check eqjs/{paper_code}/ for existing Q{n}.json files.
   c. For each MISSING question:
      - Load working-state-capsule.md as system prompt context.
      - Load the specific question text from raw/{paper_code}/questions.md.
      - Load statistics.json for that question's stats.
      - Load examiner_comments.md if available.
      - Detect if question has a diagram. If so, load the relevant 
        protocol from protocols/ using protocol-registry.json trigger 
        matching.
      - Call Anthropic API (claude-sonnet-4-5) with:
        * System: working-state-capsule + protocol (if diagram)
        * Human: raw question text + stats + examiner comments
      - Parse JSON response.
      - Validate with validate_eqjs().
      - If valid: write to eqjs/{paper_code}/Q{n}.json
      - If invalid: log error, continue to next question.
      - Append log entry to metadata/conversion-logs/raw-to-eqjs/{date}_run.jsonl

DEPENDENCIES: anthropic (pip), jsonschema (pip)
ENV VARS: ANTHROPIC_API_KEY

IMPORTANT:
- Each question is an independent API call.
- Do NOT batch questions. The working state capsule expects one question 
  at a time.
- Rate limit: max 10 requests per minute.
- On API error: retry 3 times with exponential backoff, then log failure.
```

### §6.4 Phase 4: EQJS → AI-Native Pipeline Script (Day 3-4)

```
TASK: Build the daily EQJS → AI-native conversion script.

FILE: scripts/run_eqjs_to_ainative.py

LOGIC:
1. Scan eqjs/ for all item JSON files.
2. For each item not yet in ai-native/:
   a. Load the EQJS JSON.
   b. Run Stage 1 (Q-Matrix Extraction):
      - System prompt: V8 §1.1
      - Human: full EQJS JSON
      - Parse output: q_matrix, transfer_domains, diagram_dependent, 
        phase2_model
   c. Route based on diagram_dependent:

   IF diagram_dependent == true:
      - Run Stage 2-Bo2 (V8 §2A):
        * System prompt: V8 §2A.1
        * Human: question_text + diagrams + q_matrix + transfer_domains
        * Output: two candidates + CoT traces
      - Run Stage 3 Audit (V8 §3) on the Bo2 output:
        * Set IS_BO2 = true
        * If REJECTED: retry Stage 2 with feedback (max 3)
      - Write AI-native JSON with approval_status = "awaiting_human_validation"
      - Write full Bo2 log to metadata/bo2-generation-logs/bo2_logs.jsonl

   IF diagram_dependent == false:
      - Run Stage 2-Single (V8 §2B):
        * System prompt: V8 §2B.1
        * Human: question_text + q_matrix + transfer_domains
        * Output: single candidate
      - Run Stage 3 Audit (V8 §3):
        * Set IS_BO2 = false
        * If REJECTED: retry (max 3)
      - If APPROVED: write with approval_status = "auto_approved"
      - If FAILED after retries: write with approval_status = "failed_audit"

   d. Log to metadata/conversion-logs/eqjs-to-ainative/{date}_run.jsonl

STAGE 3 RETRY LOGIC:
  function run_with_retries(seed, q_matrix, is_bo2, max_retries=3):
      draft = run_stage2(seed, q_matrix)
      for i in range(max_retries):
          audit = run_stage3(seed, q_matrix, draft, is_bo2)
          if audit.status == "APPROVED":
              return (draft, audit)
          draft = run_stage2(seed, q_matrix, 
                             previous_draft=draft,
                             feedback=audit.critical_feedback)
      return (draft, audit)  # failed after max retries
```

### §6.5 Phase 5: Human Validation Interface (Day 4-5)

```
TASK: Build a minimal CLI validator tool for HITL review.

FILE: scripts/human_validate.py

USAGE: python scripts/human_validate.py

LOGIC:
1. Scan ai-native/ for items with approval_status == "awaiting_human_validation"
2. For each pending item, display:
   - Original EQJS question (formatted)
   - Q-Matrix
   - Candidate A (Text-Abstraction): T3 + T4
   - Candidate B (Schema-Mutation): T3 + T4
3. Prompt validator:
   - "Select candidate [A/B/Neither]: "
   - If A or B selected:
     - "Q-matrix alignment confirmed? [y/n]: "
     - If n: "Explain misalignment: "
   - If Neither:
     - "Rejection reason [Construct_Violation/Dependency_Failure/Scale_Misfit/Other]: "
     - "Explain: "
   - "Validator ID: "
4. Update the AI-native JSON:
   - Set selected_candidate to chosen pathway
   - Set approval_status to "human_approved" or "rejected"
5. If approved: copy to ai-native-ready/{paper}/{item}_approved.json
6. Append to metadata/human-approvals/approvals.jsonl
7. If Bo2: generate RLVR triple and append to metadata/bo2-generation-logs/

IMPORTANT: 
- This is a CLI tool, not a web UI. Keep it simple.
- Every interaction is logged. No silent operations.
- Validator ID is mandatory.
```

### §6.6 Phase 6: DPO/RLVR Conversion Script (Day 5)

```
TASK: Build the Bo2 log → DPO triple converter.

FILE: scripts/convert_bo2_to_dpo.py

USAGE: python scripts/convert_bo2_to_dpo.py --output dpo_triples.jsonl

LOGIC:
1. Load all entries from metadata/bo2-generation-logs/bo2_logs.jsonl
2. Filter: only entries where human_validation.human_choice is not null
   AND human_validation.q_matrix_alignment_pass == true
3. For each qualifying entry:
   - Reconstruct the Stage 2 prompt (system + human)
   - Set "chosen" = the human-selected candidate
   - Set "rejected" = the other candidate
   - Include reason_category and reason_text
4. Output to specified file in JSONL format.
5. Print summary: total entries, qualifying entries, conversion rate.
```

### §6.7 Phase 7: Automation Readiness Check (Day 5)

```
TASK: Build the weekly automation readiness checker.

FILE: scripts/automation_readiness.py

USAGE: python scripts/automation_readiness.py

LOGIC:
1. Count Bo2 logs with q_matrix_alignment_pass == true → n_pairs
2. Check: n_pairs >= 1000?
3. If reward model exists: evaluate on held-out 20% → agreement_rate
   Check: agreement_rate >= 0.85?
4. Count recent overrides (last 100 items) → override_rate
   Check: override_rate < 0.05?
5. Print status report:
   - Volume: {n_pairs}/1000 [{MET/NOT MET}]
   - Agreement: {agreement_rate}% [{MET/NOT MET/NO MODEL}]  
   - Override: {override_rate}% [{MET/NOT MET}]
   - OVERALL: [READY FOR V2 AUTOMATION / CONTINUE HITL]
```

---

## §7 Skill Documents

Four skill documents govern agent behavior. Each is placed in `skills/`.

See separate skill files:
- `SKILL-raw-to-eqjs.md` — §7.1
- `SKILL-eqjs-to-ainative.md` — §7.2
- `SKILL-human-validation.md` — §7.3
- `SKILL-protocol-selection.md` — §7.4

---

## §8 Implementation Order for Claude Code

```
Priority 1 (Day 1):
  □ Create full directory structure
  □ Copy protocols into protocols/
  □ Create protocol-registry.json
  □ Create config/working-state-capsule.md
  □ Create all 4 skill documents
  □ Create README.md
  □ Initialize git

Priority 2 (Day 2):
  □ Create config/eqjs-schema-2.0.json
  □ Create config/ainative-schema-v8.json
  □ Build scripts/validate_eqjs.py
  □ Build scripts/validate_ainative.py
  □ Test validators against sample EQJS files

Priority 3 (Day 3):
  □ Build scripts/run_raw_to_eqjs.py
  □ Test on 2-3 sample raw questions
  □ Verify log output format

Priority 4 (Day 4):
  □ Build scripts/run_eqjs_to_ainative.py
  □ Test full Stage 1 → 2 → 3 pipeline on sample items
  □ Verify Bo2 log format matches V8 §4.1

Priority 5 (Day 5):
  □ Build scripts/human_validate.py
  □ Build scripts/convert_bo2_to_dpo.py
  □ Build scripts/automation_readiness.py
  □ Test end-to-end: raw → eqjs → ainative → validation → approved

Priority 6 (Day 6-7):
  □ Create GitHub Actions workflows
  □ Test cron triggers
  □ Documentation review
  □ Tag v8.0.0
```
