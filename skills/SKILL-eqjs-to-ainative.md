# SKILL: EQJS → AI-Native Assessment Schema

**Skill ID:** SKILL-eqjs-to-ainative  
**Version:** 1.0  
**Governs:** All conversions from EQJS-2.0 to AI-native diagnostic assessment schema  
**Reference:** V8 PRISM Construction Manual §1–§4

---

## 1. Trigger

This skill activates when:
- A new EQJS file appears in `eqjs/` not yet present in `ai-native/`
- The daily cron `run_eqjs_to_ainative.py` executes
- A human manually requests AI-native conversion of an EQJS item

## 2. Pipeline Overview

```
EQJS JSON
    │
    ▼
Stage 1: Q-Matrix Extraction (one call per item)
    │
    ├── diagram_dependent == true ──→ Stage 2-Bo2 (two candidates)
    │                                      │
    │                                      ▼
    │                                Stage 3 Audit (with orthogonality check)
    │                                      │
    │                                      ▼
    │                              Status: awaiting_human_validation
    │
    └── diagram_dependent == false ─→ Stage 2-Single (one candidate)
                                           │
                                           ▼
                                     Stage 3 Audit
                                           │
                                           ▼
                                   Status: auto_approved / failed_audit
```

## 3. Stage 1: Q-Matrix Extraction

### 3.1 Input
- Full EQJS JSON for the question

### 3.2 System Prompt
- Use V8 §1.1 system prompt verbatim
- No modifications

### 3.3 Critical Extraction Rules

**Q-Matrix entries:**
- One entry per incorrect option (M1, M2, etc.)
- Each entry must have: option letter, description, attribute_profile
- `description` must be a SPECIFIC misconception, not generic "wrong answer"
- `attribute_profile` must be a binary vector

**Model selection:**
- If misconceptions have ordinal ranking → `phase2_model: "GPCM"`
- If misconceptions are categorically distinct → `phase2_model: "NRM"`
- When in doubt, default to NRM (safer assumption)

**Diagram detection:**
- IF `content.stimulus.diagrams[]` exists AND is non-empty → `diagram_dependent: true`
- Parse `structured_description` and `semantic_description` from the diagram
- Extract `diagram_mechanism`: the spatial/physical principle encoded in the diagram
- IF no diagrams → `diagram_dependent: false`, `diagram_mechanism: null`

**Transfer domains:**
- Generate exactly 3
- Each must be a structurally different domain
- Each must preserve the identical underlying mechanism
- Include `preserves_mechanism` explanation

### 3.4 Validation
- Q-matrix must have at least 2 misconception entries
- Transfer domains must have exactly 3 entries
- `phase2_model` must be "NRM" or "GPCM"
- `diagram_dependent` must be boolean

## 4. Stage 2-Bo2: Diagram-Heavy Items

### 4.1 Trigger
- `diagram_dependent == true` from Stage 1

### 4.2 System Prompt
- Use V8 §2A.1 system prompt verbatim

### 4.3 Input Assembly
```
SEED ITEM TEXT: content.question_text from EQJS
SEED ITEM DIAGRAMS: content.stimulus.diagrams[] from EQJS
Q-MATRIX JSON: Stage 1 output
TRANSFER DOMAINS: Stage 1 transfer_domains
```

### 4.4 Output Requirements
- TWO complete candidates (Pathway A and Pathway B)
- Pathway A: Text-Abstraction (NO diagrams, pure text)
- Pathway B: Schema-Mutation (NEW structured_description JSON)
- Each candidate has: T3_probe + T4_transfer + CoT_trace
- orthogonality_check: 2-sentence explanation of how A ≠ B

### 4.5 Pathway B Diagram Rules
When generating structured_description for Pathway B:
1. Identify the protocol used in the original EQJS diagram
2. The NEW structured_description MUST follow the SAME protocol
3. Load the protocol from `protocols/` and follow its JSON schema
4. Surface features (object names, materials, colors) must be DIFFERENT
5. Underlying mechanism must be IDENTICAL
6. If the protocol requires specific invariants, they must be satisfied

### 4.6 Failure Modes
- If both pathways produce similar items → Stage 3 will REJECT (orthogonality fail)
- If Pathway B produces invalid structured_description → Stage 3 will REJECT (construct purity fail)
- If retry limit (3) reached → write with `approval_status: "failed_audit"`

## 5. Stage 2-Single: Non-Diagram Items

### 5.1 Trigger
- `diagram_dependent == false` from Stage 1

### 5.2 System Prompt
- Use V8 §2B.1 system prompt verbatim

### 5.3 Output Requirements
- ONE candidate only
- T3_probe + T4_transfer
- Transfer domain MUST be from Stage 1 transfer_domains list

## 6. Stage 3: Psychometric Audit

### 6.1 System Prompt
- Use V8 §3.1 system prompt verbatim

### 6.2 Five Audit Criteria

| # | Criterion | Applies To | Critical Check |
|---|-----------|------------|----------------|
| 1 | Diagnostic Purity | T3 + T4 | Each distractor maps to exactly one misconception |
| 2 | IRT Discrimination | T3 + T4 | Correct answer not identifiable by elimination |
| 3 | Transfer Distance | T4 only | Genuinely novel domain, not surface swap |
| 4 | Construct Purity | T3 + T4 | No construct-irrelevant variance |
| 5 | Orthogonality | Bo2 only | Pathways A and B are fundamentally different |

### 6.3 Retry Logic
```
max_retries = 3
on REJECTION:
    append critical_feedback to Stage 2 context
    regenerate
    re-audit
after max_retries:
    write with approval_status = "failed_audit"
    log all feedback for human review
```

## 7. Logging

### 7.1 Bo2 Items
Every Bo2 generation produces a FULL log record matching V8 §4.1 schema:
- item_id, diagram_type, diagram_mechanism
- Both candidates with full output
- Both CoT traces
- Audit result
- Placeholder for human_validation (filled later by HITL)
- Placeholder for rlvr_triple (filled after human choice)

Written to: `metadata/bo2-generation-logs/bo2_logs.jsonl`

### 7.2 All Items
Every conversion (Bo2 and Single) produces a conversion log entry:
Written to: `metadata/conversion-logs/eqjs-to-ainative/{date}_run.jsonl`

## 8. T2 Rubric Generation

For EVERY item (Bo2 and Single), generate a T2 rubric:
```json
{
  "scoring_model": "concept_presence_only",
  "correct_concepts": ["extracted from mastery_logic"],
  "correct_mechanism": "the causal chain from mastery_logic",
  "fluency_excluded": true
}
```

Rules:
- `correct_concepts` must be specific scientific concepts, not vague
- `correct_mechanism` must describe the full causal chain
- `fluency_excluded` is ALWAYS true (locked decision)

## 9. LLTM Cold-Start Parameters

For EVERY item, compute cold-start calibration parameters:

```json
{
  "calibration_phase": "A_cold_start",
  "lltm_predicted_params": {
    "alpha": 1.0,
    "beta": <computed from EQJS metadata>,
    "d_steps": [-0.5, 0.0, 0.5]
  }
}
```

Beta prediction uses EQJS fields:
- `classification.cognitive_level` → Bloom's index (1-6)
- `classification.asset_percent_correct` → facility (0-1)
- `semantic.prerequisites` → count
- `classification.difficulty` → ordinal (easy=1, medium=2, hard=3)

Formula: `beta = -1 * qnorm(percent_correct/100)` as initial approximation
(Will be replaced by LLTM weights once `metadata/calibration/lltm-weights.json` exists)

## 10. Output Location

```
ai-native/{paper_code}/Q{n}_ainative.json
```

One file per question. UTF-8 encoding. Pretty-printed (2-space indent).
