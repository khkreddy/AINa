# SKILL: Raw → EQJS Conversion

**Skill ID:** SKILL-raw-to-eqjs  
**Version:** 1.0  
**Governs:** All conversions from raw question input to EQJS-2.0 JSON

---

## 1. Trigger

This skill activates when:
- A new file appears in `raw/{paper_code}/`
- The daily cron `run_raw_to_eqjs.py` executes
- A human manually requests conversion of a raw question

## 2. Required Context

Before converting ANY question, the agent MUST load:

1. **Working State Capsule** (`config/working-state-capsule.md`)
   - Contains schema rules, timing, diagram rules, pedagogical rules
   - This is the SYSTEM prompt for every conversion call

2. **Statistics** (from `raw/{paper_code}/statistics.json`)
   - Per-question: correct answer, skill number, percent correct, option distribution
   - These are injected verbatim into the JSON — no modification

3. **Examiner Comments** (from `raw/{paper_code}/examiner_comments.md`)
   - If available for the question, include in `expert_comment` field
   - If not available, omit `expert_comment` or use agent-generated comment

4. **Protocol** (from `protocols/`)
   - Only loaded if the question contains a diagram
   - Selected via protocol-registry.json trigger matching (see SKILL-protocol-selection)

## 3. Conversion Rules (Non-Negotiable)

### 3.1 Schema Compliance
- Output MUST conform to EQJS-2.0
- Every JSON MUST pass `validate_eqjs.py` before being written to `eqjs/`

### 3.2 Field Mapping

| Raw Input | EQJS Field | Rule |
|-----------|------------|------|
| Question number | `metadata.id` | Format: `{paper_code}_Q{n}` |
| Subject detection | `classification.subject` | Infer from content (biology/chemistry/physics) |
| Topic | `classification.topic` | Array of relevant topics |
| Difficulty | `classification.difficulty` | Infer from percent_correct: >70% easy, 40-70% medium, <40% hard |
| Cognitive level | `classification.cognitive_level` | Map from Bloom's: remember/understand/apply/analyze/evaluate/create |
| Time | `classification.estimated_time_seconds` | Use paper total / question count (e.g., 3600/45 ≈ 80s) |
| Percent correct | `classification.asset_percent_correct` | From statistics.json, verbatim |
| Question text | `content.question_text` | Exact text, no paraphrasing |
| Options A-D | `content.options` | Exact text, preserve ordering |
| Correct answer | `solution.correct_answer` | From statistics.json |
| Option distribution | `assessment_metadata.option_distribution_percent` | From statistics.json |
| Skill number | `semantic.asset_skill_no` | From statistics.json |

### 3.3 Diagram Handling

IF the question references a diagram, figure, or graph:

1. Identify diagram type using protocol-registry.json triggers
2. Load the matching protocol from `protocols/`
3. Follow the protocol's Stage 0 (Intent Canonicalization)
4. Encode the diagram in `content.stimulus.diagrams[]` using the protocol's JSON schema
5. Set `metadata.protocol_conformance` to include the protocol ID
6. Set `metadata.validation_status.checked_invariants` to include protocol-specific invariants

IF the diagram is ambiguous:
- Set `metadata.validation_status.requires_human_decision = true`
- Add a `validation_note` explaining the ambiguity
- DO NOT guess. Flag and continue.

### 3.4 Common Errors Field

For EACH incorrect option, generate:
```json
{
  "incorrect_answer": "A",
  "frequency_percent": 17,
  "misconception": "Clear, specific description of the misconception",
  "pedagogical_note": "Why a student might choose this; how to correct it"
}
```

Rules:
- `frequency_percent` comes from statistics.json option distribution
- `misconception` must be a specific cognitive error, not "student didn't know"
- `pedagogical_note` must be actionable for a teacher
- If option distribution data is unavailable, omit `frequency_percent` 
  but still provide misconception and pedagogical_note

### 3.5 Semantic Field

```json
{
  "concepts": ["list of scientific concepts tested"],
  "prerequisites": ["concepts student must already know"],
  "question_pattern": "descriptive pattern name",
  "reasoning_type": "conceptual | quantitative | procedural | analytical",
  "asset_skill_no": 3,
  "asset_skill_label": "From skill mapping table"
}
```

## 4. Quality Gates

Before writing to `eqjs/`:

1. **Schema validation**: passes `validate_eqjs.py`
2. **Answer check**: `solution.correct_answer` matches one of `content.options` keys
3. **Stats injection**: all numeric values from statistics.json are present and unmodified
4. **Diagram check**: if diagram present, protocol is declared and structured_data is non-empty
5. **Common errors**: at least one entry per incorrect option

## 5. Error Handling

- Schema validation failure → log error, DO NOT write file, continue to next question
- API error → retry 3 times, then log failure
- Ambiguous diagram → write file with `requires_human_decision: true`
- Missing statistics → write file with available data, log warning

## 6. Output Location

```
eqjs/{paper_code}/Q{n}.json
```

One file per question. UTF-8 encoding. Pretty-printed (2-space indent).
