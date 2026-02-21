# V8 PRISM Construction Manual

## AI-Native Diagnostic Assessment Engine — Execution Specification

**Version:** 8.0 — Production Build Spec  
**Status:** Construction Manual — No Theory, No History  
**Base:** V7/PRISM + Two-Tier IFA + Mixture IRT + D-Optimal KB  
**Date:** 21 February 2026

---

## §0 Locked Foundations

Copy these into every module header as code comments. They are non-negotiable.

```
// LOCKED: T2 rubric scores ONLY presence & correctness of scientific concepts.
//         Fluency, grammar, organization are explicitly excluded.
// LOCKED: Two-Tier IFA is default for all joint T1/T2 scoring.
//         Fit at calibration-time only. Primary θ used at runtime. ζ absorbed.
// LOCKED: Mixture IRT runs post-cascade.
//         P(guessing/slipping) as latent class. Down-weights θ if P(aberrant) high.
//         Within-cascade T3↔T4 logical check remains as heuristic prior.
// LOCKED: D-optimal + G-DINA runs offline batch.
//         N=200 first pass. N=500 validation pass.
// LOCKED: Diagram-heavy items use Bo2 generation + HITL selection.
//         Non-diagram items remain single-generation.
// LOCKED: Every human choice = machine-reusable training signal.
// LOCKED: Every component maps to G1–G5 or is deleted.
```

**Terminal Objectives (G1–G5):**

| ID | Objective | Success Criterion |
|----|-----------|-------------------|
| G1 | Classify every student-concept pair into diagnostic state | Posterior vector with entropy < 1.0 bit |
| G2 | Produce invariant measurements | Item params sample-independent; θ item-set-independent |
| G3 | AI-generated items at psychometric parity | a ≥ 1.0, RMSEA < 0.05 post-calibration |
| G4 | Scale to 1,500+ items without per-item expert panels | Cold-start via LLTM; warm at N ≥ 200 |
| G5 | Detect and quarantine aberrant responses | Person-fit detection power ≥ 0.80 |

---

## §1 Stage 1: Q-Matrix Extraction

**Trigger:** Once per EQJS seed item.  
**No changes from V7** except: output must include `diagram_dependent` flag and `transfer_domains`.

### §1.1 System Prompt

```
[SYSTEM]
You are an expert psychometrician and cognitive scientist. Your task is to 
extract the Cognitive Q-Matrix from a seed multiple-choice question.

You will be provided with a JSON representing a test item (EQJS schema).

INSTRUCTIONS:
1. Identify the Core Concept required to answer the question correctly.
2. Analyze the `common_errors` array. For each incorrect option, extract 
   the specific "Misconception Attribute" (M1, M2, etc.).
3. If `frequency_percent` is missing for any option, ignore the frequency 
   and rely entirely on the `misconception` and `pedagogical_note` text.
4. Determine if the misconception attributes have a natural ordinal ranking 
   (e.g., progressive levels of sophistication). Set misconception_ordering 
   accordingly.
5. If the seed item contains `stimulus.diagrams[]`, parse the 
   `structured_description` and `semantic_description` fields. The Core 
   Concept extraction MUST incorporate the visual/spatial mechanism.
6. Generate 3 transfer domain seeds — each must be a structurally different 
   domain where the identical underlying mechanism applies.

OUTPUT FORMAT (strict JSON):
{
  "core_concept": "String describing the fundamental scientific principle.",
  "mastery_logic": "String describing the correct reasoning chain.",
  "diagram_dependent": true | false,
  "diagram_mechanism": "String describing the spatial/visual mechanism 
                        (null if diagram_dependent is false)",
  "misconception_ordering": "ordered" | "unordered",
  "phase2_model": "GPCM" | "NRM",
  "q_matrix": {
    "M1": {
      "option": "A",
      "description": "Specific misconception description.",
      "attribute_profile": [1, 0, 0]
    },
    "M2": {
      "option": "B",
      "description": "...",
      "attribute_profile": [0, 1, 0]
    }
  },
  "transfer_domains": [
    {
      "domain": "cooking/baking",
      "seed": "Bread dough rising in a sealed container",
      "preserves_mechanism": "Conservation of mass when gas is produced"
    },
    {
      "domain": "industrial engineering",
      "seed": "Combustion in a sealed engine cylinder",
      "preserves_mechanism": "..."
    },
    {
      "domain": "environmental science",
      "seed": "Decomposition in a closed compost system",
      "preserves_mechanism": "..."
    }
  ]
}

[HUMAN]
SEED ITEM JSON:
{{seed_json}}
```

### §1.2 Decision Gate After Stage 1

```
IF diagram_dependent == true:
    Route to Stage 2-Bo2 (§2A)
ELSE:
    Route to Stage 2-Single (§2B)
```

---

## §2A Stage 2 — Bo2 Generator (Diagram-Heavy Items)

**Trigger:** `diagram_dependent == true` from Stage 1.  
**Output:** Two orthogonal candidates + CoT traces.  
**Maps to:** G3, G4

### §2A.1 System Prompt

```
[SYSTEM]
You are an expert assessment developer. You will generate TWO diagnostic 
item candidates for T3 (Concept Probe) and T4 (Far-Transfer Check), using 
TWO MANDATORY ORTHOGONAL PATHWAYS.

You are provided with:
- The seed EQJS item (including any diagram structured_description)
- The Q-Matrix with core concept and misconception attributes
- A list of pre-validated transfer domains

═══════════════════════════════════════════════════════════════════
PATHWAY A: TEXT-ABSTRACTION
═══════════════════════════════════════════════════════════════════
Strip ALL visual/spatial/diagrammatic elements from the concept.
Construct T3 and T4 as PURELY TEXTUAL items that test the same 
underlying mechanism through verbal/logical reasoning only.

Requirements:
- T3 must be a de-contextualized conceptual probe with ZERO reference 
  to any physical setup, apparatus, or diagram.
- T4 must use one of the provided transfer_domains.
- All distractors map to Q-matrix misconceptions.
- No spatial reasoning required to answer correctly.

═══════════════════════════════════════════════════════════════════
PATHWAY B: SCHEMA-MUTATION
═══════════════════════════════════════════════════════════════════
Generate a NEW diagram scenario that preserves the identical 
physical/biological mechanism but MUTATES the visual elements.

Requirements:
- T3: Output a new `structured_description` JSON block describing 
  a different apparatus/setup that tests the same concept.
- T4: Output a new `structured_description` JSON block in a 
  different transfer domain (from provided list).
- The structured_description must follow the EQJS diagram schema:
  {
    "diagram_id": "...",
    "diagram_type": "...",
    "components": [...],
    "relationships": [...],
    "semantic_description": "Plain English description of what 
                             the diagram shows"
  }
- Surface features (object names, colors, materials) must share 
  ZERO overlap with the seed item.
- The underlying mechanism must be IDENTICAL.

═══════════════════════════════════════════════════════════════════
RULES FOR BOTH PATHWAYS
═══════════════════════════════════════════════════════════════════
- T3 distractors MUST map to exactly the misconceptions in the 
  Q-matrix (M1, M2, etc.). No distractor may be attributable to 
  reading comprehension, poor phrasing, or a misconception NOT 
  in the Q-matrix.
- T3 MUST include a final option: "I am not sure / I do not know 
  this concept." Tagged as "routing_LoK" (NOT an NRM category).
- T4 distractors MUST predict what a student holding M1 or M2 
  would choose in the novel context.
- The correct answer must NOT be identifiable by elimination, 
  test-wiseness, or grammatical cues.
- T4 must NOT include an "I don't know" option.

═══════════════════════════════════════════════════════════════════
CHAIN-OF-THOUGHT REQUIREMENTS
═══════════════════════════════════════════════════════════════════
For EACH pathway, you must produce a CoT trace that:
1. States the core mechanism being tested.
2. Explains how the pathway preserves the mechanism.
3. Justifies the far-transfer distance for T4.
4. Explains why this pathway is ORTHOGONAL to the other 
   (if both pathways produce similar items, you have FAILED).

REJECT your own output if Pathway A and Pathway B differ only 
in wording, surface nouns, or minor structural variations. 
If this occurs, regenerate Pathway B with a fundamentally 
different approach.

OUTPUT FORMAT (strict JSON):
{
  "pathway_A_text_abstraction": {
    "CoT_trace": "...",
    "T3_probe": {
      "prompt": "...",
      "options": {
        "A": {"text": "...", "maps_to": "M1"},
        "B": {"text": "...", "maps_to": "Mastery"},
        "C": {"text": "...", "maps_to": "M2"},
        "D": {"text": "I am not sure.", "maps_to": "routing_LoK"}
      }
    },
    "T4_transfer": {
      "selected_domain": "...",
      "domain_shift_rationale": "...",
      "prompt": "...",
      "options": {
        "A": {"text": "...", "maps_to": "M2"},
        "B": {"text": "...", "maps_to": "Mastery"},
        "C": {"text": "...", "maps_to": "M1"}
      }
    }
  },
  "pathway_B_schema_mutation": {
    "CoT_trace": "...",
    "T3_probe": {
      "prompt": "...",
      "structured_description": { ... EQJS diagram schema ... },
      "options": {
        "A": {"text": "...", "maps_to": "M2"},
        "B": {"text": "...", "maps_to": "M1"},
        "C": {"text": "...", "maps_to": "Mastery"},
        "D": {"text": "I am not sure.", "maps_to": "routing_LoK"}
      }
    },
    "T4_transfer": {
      "selected_domain": "...",
      "domain_shift_rationale": "...",
      "prompt": "...",
      "structured_description": { ... EQJS diagram schema ... },
      "options": {
        "A": {"text": "...", "maps_to": "Mastery"},
        "B": {"text": "...", "maps_to": "M1"},
        "C": {"text": "...", "maps_to": "M2"}
      }
    }
  },
  "orthogonality_check": "Explain in 2 sentences why A and B 
                          are fundamentally different approaches."
}

[HUMAN]
SEED ITEM TEXT: {{question_text}}
SEED ITEM DIAGRAMS: {{stimulus_diagrams_json}}
Q-MATRIX JSON: {{q_matrix_json}}
TRANSFER DOMAINS: {{transfer_domains_json}}
```

---

## §2B Stage 2 — Single Generator (Non-Diagram Items)

**Trigger:** `diagram_dependent == false` from Stage 1.  
**Output:** Single T3/T4 candidate.  
**Identical to V7 Stage 2 prompt** with these updates:

1. Transfer domain constraint (must select from Stage 1 `transfer_domains`)
2. "I am not sure" tagged as `routing_LoK`
3. T2 scoring rubric reference (§5.1) included in context

### §2B.1 System Prompt

```
[SYSTEM]
You are an expert assessment developer. Using the provided Q-Matrix 
and Core Concept, generate T3 (Concept Probe) and T4 (Far-Transfer Check).

DOMAIN CONSTRAINT: For T4, you MUST use one of the provided 
transfer_domains. Do NOT invent your own domain shift.

T3 RULES:
- De-contextualize completely from the seed item.
- Ask directly about the fundamental principle.
- Each distractor maps to exactly one misconception in the Q-matrix.
- Include final option: "I am not sure / I do not know this concept."
  Tagged as "routing_LoK" — NOT an NRM category.
- Correct answer must NOT be identifiable by elimination, 
  test-wiseness, or grammatical cues.

T4 RULES:
- Use one of the provided transfer_domains.
- Surface features must share ZERO nouns or scenarios with T1 or T3.
- Underlying mechanism must be IDENTICAL to core concept.
- Each distractor predicts what a student holding M1 or M2 would 
  choose in this novel context.
- Structural transfer distance must be HIGH: swapping species within 
  the same kingdom, or colors/sizes within the same object class, 
  is INSUFFICIENT.
- Do NOT include an "I don't know" option in T4.

OUTPUT FORMAT (strict JSON):
{
  "T3_probe": {
    "prompt": "...",
    "options": {
      "A": {"text": "...", "maps_to": "M1"},
      "B": {"text": "...", "maps_to": "Mastery"},
      "C": {"text": "...", "maps_to": "M2"},
      "D": {"text": "I am not sure.", "maps_to": "routing_LoK"}
    }
  },
  "T4_transfer": {
    "selected_domain": "...",
    "domain_shift_rationale": "...",
    "prompt": "...",
    "options": {
      "A": {"text": "...", "maps_to": "M2"},
      "B": {"text": "...", "maps_to": "Mastery"},
      "C": {"text": "...", "maps_to": "M1"}
    }
  }
}

[HUMAN]
SEED ITEM TEXT: {{question_text}}
Q-MATRIX JSON: {{q_matrix_json}}
TRANSFER DOMAINS: {{transfer_domains_json}}
```

---

## §3 Stage 3: Psychometric Audit

**Trigger:** After every Stage 2 output (both Bo2 and Single).  
**Action:** APPROVED → forward to §4 (Calibration Queue) or §6 (HITL for Bo2).  
**Action:** REJECTED → feedback to Stage 2, max 3 retries.  
**Maps to:** G2, G3

### §3.1 System Prompt

```
[SYSTEM]
You are a Psychometric Auditor. Audit proposed T3 and T4 diagnostic 
items against IRT constraints. Apply ALL FIVE criteria below.

═══════════════════════════════════════════════════════════════════
CRITERION 1: DIAGNOSTIC PURITY (Q-Matrix Alignment)
═══════════════════════════════════════════════════════════════════
Does choosing Distractor X STRICTLY require the student to hold 
Misconception X?

FAIL conditions:
- A student could choose it due to poor phrasing or ambiguity.
- A student could choose it due to reading comprehension difficulty.
- A student could choose it due to a misconception NOT in the Q-matrix.
- Two distractors could attract the same misconception (conflation).

═══════════════════════════════════════════════════════════════════
CRITERION 2: IRT DISCRIMINATION (a-parameter)
═══════════════════════════════════════════════════════════════════
Is the correct answer too obvious? Does the item rely on:
- Rote memorization phrasing ("always", "never")
- Test-wiseness cues (longest option, grammatical mismatch)
- Elimination strategies (3 clearly wrong, 1 obviously right)

FAIL if a test-savvy student with NO conceptual understanding 
could select the correct answer.

═══════════════════════════════════════════════════════════════════
CRITERION 3: TRANSFER DISTANCE (T4 only)
═══════════════════════════════════════════════════════════════════
Is the T4 context genuinely novel?

FAIL conditions:
- Swaps within same category (dog→cat, red→blue, beaker→flask)
- Same domain with minor surface variation
- The transfer domain was NOT from the provided transfer_domains list

═══════════════════════════════════════════════════════════════════
CRITERION 4: CONSTRUCT PURITY
═══════════════════════════════════════════════════════════════════
Could a student fail due to construct-irrelevant factors?

FAIL conditions:
- Requires specialized vocabulary beyond the target grade level
- Requires knowledge of a domain not in the curriculum
- For Pathway B items: the structured_description introduces 
  spatial complexity beyond what the concept requires
- The "I am not sure" option is phrased in a way that stigmatizes 
  selection (e.g., "I give up" vs. neutral "I am not sure")

═══════════════════════════════════════════════════════════════════
CRITERION 5: PATHWAY ORTHOGONALITY (Bo2 items only)
═══════════════════════════════════════════════════════════════════
Do Pathway A and Pathway B represent fundamentally different 
assessment approaches?

FAIL conditions:
- Both pathways test the concept in the same modality (both text, 
  both diagram)
- Pathways differ only in wording or surface features
- Both pathways would be equally easy/hard for the same student 
  profile (no informative diversity)

YOUR OUTPUT MUST BE STRICT JSON:
{
  "evaluation": {
    "T3_purity_pass": boolean,
    "T3_discrimination_pass": boolean,
    "T4_transfer_distance_pass": boolean,
    "T4_purity_pass": boolean,
    "construct_purity_pass": boolean,
    "orthogonality_pass": boolean | null  // null for non-Bo2 items
  },
  "status": "APPROVED" | "REJECTED",
  "critical_feedback": "If REJECTED: state WHICH criterion failed, 
    WHICH specific distractor/element caused failure, and a 
    CONCRETE repair instruction. If APPROVED: empty string."
}

[HUMAN]
ORIGINAL SEED QUESTION: {{question_text}}
Q-MATRIX: {{q_matrix_json}}
PROPOSED T3 AND T4 ITEMS: {{t3_t4_draft_json}}
IS_BO2: {{true|false}}
```

### §3.2 Retry Logic

```pseudocode
function audit_and_refine(seed, q_matrix, draft, is_bo2):
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        result = run_stage3_audit(seed, q_matrix, draft, is_bo2)
        
        if result.status == "APPROVED":
            return {status: "APPROVED", draft: draft, retries: retry_count}
        
        retry_count += 1
        
        // Append feedback to Stage 2 context
        draft = run_stage2_regeneration(
            seed, q_matrix, 
            previous_draft=draft,
            feedback=result.critical_feedback,
            retry_number=retry_count
        )
    
    // Max retries exceeded
    return {
        status: "FAILED_AUDIT",
        draft: draft,
        retries: retry_count,
        last_feedback: result.critical_feedback
    }
    // FAILED_AUDIT items are logged and routed to human review queue
```

---

## §4 Logging Schema

**Mandatory from Day 1.** Every generation event produces a log record. No exceptions.

### §4.1 Bo2 Log Record (Diagram-Heavy Items)

```json
{
  "log_version": "V8.0",
  "log_type": "Bo2_generation",
  "item_id": "EQJS-39224-Q3",
  "seed_concept": "Conservation of mass in chemical reactions",
  "diagram_dependent": true,
  "diagram_type": "anamorphic_mirror",
  "diagram_mechanism": "Curved reflection and image distortion",
  
  "stage1_output": {
    "q_matrix": { "...full Q-matrix..." },
    "transfer_domains": [ "...3 domains..." ],
    "phase2_model": "NRM",
    "misconception_ordering": "unordered"
  },
  
  "generation": {
    "generation_pathway": ["Text-Abstraction", "Schema-Mutation"],
    "candidate_A": {
      "pathway": "Text-Abstraction",
      "T3_probe": { "...full output..." },
      "T4_transfer": { "...full output..." }
    },
    "candidate_B": {
      "pathway": "Schema-Mutation",
      "T3_probe": { "...full output..." },
      "T4_transfer": { "...full output..." }
    },
    "CoT_trace_A": "Full chain-of-thought for Pathway A",
    "CoT_trace_B": "Full chain-of-thought for Pathway B",
    "orthogonality_check": "2-sentence explanation"
  },
  
  "audit": {
    "stage3_result": "APPROVED",
    "retries": 1,
    "evaluation_details": { "...criterion results..." }
  },
  
  "human_validation": {
    "human_choice": "A",
    "rejection_reason": "Construct_Violation | Dependency_Failure | Scale_Misfit | Other | null",
    "rejection_explanation": "Free text (null if chosen candidate is accepted)",
    "q_matrix_alignment_pass": true,
    "q_matrix_alignment_notes": "Free text: any distractor mapping concerns",
    "validator_id": "VAL-017",
    "validation_timestamp": "2026-02-21T05:17:00Z"
  },
  
  "rlvr_triple": {
    "prompt": "...Stage 2 prompt with all context...",
    "winner": "A",
    "loser": "B",
    "reason_category": "Construct_Violation | Dependency_Failure | Scale_Misfit | Other",
    "reason_text": "...rejection_explanation..."
  },
  
  "generation_timestamp": "2026-02-21T05:12:00Z",
  "generator_model": "claude-sonnet-4-5-20250929",
  "audit_model": "claude-sonnet-4-5-20250929"
}
```

### §4.2 Single-Generation Log Record (Non-Diagram Items)

```json
{
  "log_version": "V8.0",
  "log_type": "single_generation",
  "item_id": "EQJS-39224-Q35",
  "seed_concept": "...",
  "diagram_dependent": false,
  
  "stage1_output": { "...same as §4.1..." },
  
  "generation": {
    "generation_pathway": ["Single"],
    "candidate": {
      "T3_probe": { "...full output..." },
      "T4_transfer": { "...full output..." }
    },
    "CoT_trace": "..."
  },
  
  "audit": {
    "stage3_result": "APPROVED",
    "retries": 0,
    "evaluation_details": { "..." }
  },
  
  "generation_timestamp": "...",
  "generator_model": "...",
  "audit_model": "..."
}
```

### §4.3 RLVR/DPO Triple Conversion Script (Pseudocode)

```pseudocode
function convert_logs_to_dpo_triples(log_directory):
    triples = []
    
    for log in load_logs(log_directory):
        if log.log_type != "Bo2_generation":
            continue
        if log.human_validation.human_choice is null:
            continue  // not yet validated
        
        winner_key = log.human_validation.human_choice  // "A" or "B"
        loser_key = "B" if winner_key == "A" else "A"
        
        triple = {
            "prompt": reconstruct_stage2_prompt(
                log.item_id,
                log.stage1_output.q_matrix,
                log.stage1_output.transfer_domains,
                log.diagram_mechanism
            ),
            "chosen": log.generation["candidate_" + winner_key],
            "rejected": log.generation["candidate_" + loser_key],
            "reason_category": log.human_validation.rejection_reason,
            "reason_text": log.human_validation.rejection_explanation,
            "validator_id": log.human_validation.validator_id,
            "q_matrix_aligned": log.human_validation.q_matrix_alignment_pass
        }
        
        // Only include if Q-matrix alignment confirmed
        if triple.q_matrix_aligned:
            triples.append(triple)
    
    return triples
```

---

## §5 Scoring Engine

### §5.1 T2 Scoring Rubric (LLM-as-Rater)

```
[SYSTEM]
You are a Science Reasoning Scorer. Score the student's reasoning 
response on a 0–3 scale based ONLY on scientific concept presence 
and correctness.

═══════════════════════════════════════════════════════════════════
SCORING CRITERIA — WHAT COUNTS
═══════════════════════════════════════════════════════════════════
- Presence of the correct scientific concept(s)
- Correct causal/mechanistic relationships between concepts
- Correct application of the concept to the specific question context

═══════════════════════════════════════════════════════════════════
SCORING CRITERIA — WHAT DOES NOT COUNT
═══════════════════════════════════════════════════════════════════
- Grammar, spelling, punctuation → IGNORE COMPLETELY
- Sentence structure or fluency → IGNORE COMPLETELY
- Organization or formatting → IGNORE COMPLETELY
- Vocabulary sophistication → IGNORE COMPLETELY
- Length of response → IGNORE COMPLETELY
- Use of technical terminology → IGNORE (accept vernacular 
  descriptions if scientifically accurate)

═══════════════════════════════════════════════════════════════════
RUBRIC
═══════════════════════════════════════════════════════════════════

Score 0: No relevant scientific concept present. Response is 
         blank, incoherent, or entirely off-topic.

Score 1: At least one relevant concept is present but applied 
         incorrectly OR the causal chain is incomplete/broken.
         Example: "It's because of energy" (names concept but 
         no mechanism).

Score 2: The correct concept is present AND partially applied, 
         but with at least one significant mechanistic error 
         or missing link in the causal chain.
         Example: "Exothermic means heat is released so temperature 
         goes up" (correct concept, correct direction, but missing 
         the mechanism of bond energy changes).

Score 3: The correct concept is present AND correctly applied 
         with a complete causal chain. No mechanistic errors.
         Example: "Bond breaking requires energy (endothermic) 
         and bond forming releases energy (exothermic). If energy 
         released > energy absorbed, the reaction is exothermic 
         overall." (complete mechanism, correct relationships).

OUTPUT FORMAT:
{
  "T2_score": 0 | 1 | 2 | 3,
  "concepts_identified": ["list of scientific concepts detected"],
  "mechanistic_chain": "brief description of the reasoning chain 
                        the student expressed",
  "scoring_rationale": "1–2 sentences explaining score assignment 
                        referencing ONLY concept presence/correctness"
}

[HUMAN]
QUESTION: {{question_text}}
CORRECT ANSWER: {{correct_answer_with_reasoning}}
STUDENT T1 RESPONSE: {{t1_selected_option}}
STUDENT T2 RESPONSE: {{t2_reasoning_text}}
```

### §5.2 Joint T1+T2 Score Mapping

```pseudocode
function compute_joint_score(t1_correct: bool, t2_score: int) -> int:
    // T2 score is 0–3 from §5.1
    // Joint score is 0–3 for GPCM
    
    if not t1_correct and t2_score <= 1:
        return 0  // No evidence of relevant knowledge
    
    if not t1_correct and t2_score >= 2:
        return 1  // Developing framework, application failure
    
    if t1_correct and t2_score <= 1:
        return 2  // Likely procedural recall or lucky guess
    
    if t1_correct and t2_score >= 2:
        return 3  // Strong evidence of mastery
```

### §5.3 Diagnostic Routing Decision Tree

```
                    joint_score = compute_joint_score(t1, t2)
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                score = 3      score = 2      score ∈ {0, 1}
                    │               │               │
                    ▼               ▼               ▼
            ┌────────────┐  ┌────────────┐  ┌────────────┐
            │  CLASSIFY   │  │  T3 PROBE  │  │  T3 PROBE  │
            │  Mastery    │  │  Focus:    │  │  Focus:    │
            │  (high conf)│  │  Does the  │  │  Conceptual│
            │  Skip T3/T4 │  │  student   │  │  boundaries│
            └────────────┘  │  actually   │  │  and       │
                            │  hold the   │  │  attribute │
                            │  concept?   │  │  mastery   │
                            └────────────┘  └────────────┘
                                    │               │
                                    └───────┬───────┘
                                            ▼
                                    T3 Response Observed
                                            │
                                ┌───────────┼───────────┐
                                │           │           │
                          routing_LoK   Misconception  Mastery
                          ("I'm not     (M1 or M2)    option
                           sure")            │         selected
                                │           │           │
                                ▼           ▼           ▼
                         ┌──────────┐ ┌──────────┐ ┌──────────┐
                         │ CLASSIFY │ │ PROCEED  │ │ PROCEED  │
                         │ Lack_of_ │ │ to T4    │ │ to T4    │
                         │Knowledge │ │ Transfer │ │ Transfer │
                         │ Skip T4  │ │ Confirm  │ │ Confirm  │
                         └──────────┘ └──────────┘ └──────────┘
                                            │           │
                                            └─────┬─────┘
                                                  ▼
                                          T4 Response Observed
                                                  │
                                                  ▼
                                    ┌─────────────────────────┐
                                    │  T3 ↔ T4 Consistency    │
                                    │  Check (Heuristic Prior) │
                                    └────────────┬────────────┘
                                                 ▼
                                    ┌─────────────────────────┐
                                    │  Post-Cascade Mixture    │
                                    │  IRT Scoring (§5.5)      │
                                    └────────────┬────────────┘
                                                 ▼
                                    ┌─────────────────────────┐
                                    │  Final Diagnostic Vector │
                                    │  (§5.6)                  │
                                    └─────────────────────────┘
```

### §5.4 Sequential EAP Update (Runtime)

```pseudocode
// ═══════════════════════════════════════════════════════════════
// PRIOR INITIALIZATION
// ═══════════════════════════════════════════════════════════════

function initialize_prior(student_id):
    history = load_student_history(student_id)
    
    if history is null:
        return GaussianPrior(mean=0.0, sd=1.0)
    else:
        // Use posterior from most recent cascade as prior
        return GaussianPrior(
            mean=history.last_theta_estimate,
            sd=history.last_theta_se
        )

// ═══════════════════════════════════════════════════════════════
// PHASE 1: MASTERY GATE (T1 + T2)
// Model: GPCM with primary θ only (ζ absorbed at calibration)
// ═══════════════════════════════════════════════════════════════

function eap_update_gpcm(prior, joint_score, item_params):
    // item_params: {alpha, beta, d_steps[]} from calibration
    // joint_score: 0–3 from §5.2
    
    // Quadrature grid: 40 points from -4 to +4
    grid = linspace(-4, 4, 40)
    
    for each theta in grid:
        // GPCM likelihood for observed score k
        likelihood[theta] = gpcm_probability(
            theta, joint_score, 
            item_params.alpha, 
            item_params.beta, 
            item_params.d_steps
        )
        // Posterior ∝ likelihood × prior
        posterior[theta] = likelihood[theta] * prior.density(theta)
    
    // Normalize
    posterior = posterior / sum(posterior * grid_spacing)
    
    // EAP = expected value of posterior
    theta_hat = sum(grid * posterior * grid_spacing)
    theta_se = sqrt(sum((grid - theta_hat)^2 * posterior * grid_spacing))
    
    return EAPResult(
        theta=theta_hat, 
        se=theta_se, 
        posterior=posterior
    )

// ═══════════════════════════════════════════════════════════════
// PHASE 2: DIAGNOSTIC PIVOT (T3)
// Model: NRM (or GPCM if misconception_ordering == "ordered")
// ═══════════════════════════════════════════════════════════════

function eap_update_nrm(prior_posterior, t3_response, item_params):
    // item_params: {a_k[], c_k[]} for each category k
    // t3_response: category index (M1, M2, Mastery, routing_LoK)
    
    if t3_response == "routing_LoK":
        // Do NOT update θ via NRM
        // Classify directly as Lack_of_Knowledge
        return LoKResult(
            theta=prior_posterior.theta,
            se=prior_posterior.se,
            classification="Lack_of_Knowledge",
            skip_T4=true
        )
    
    grid = linspace(-4, 4, 40)
    k = t3_response  // the selected category
    
    for each theta in grid:
        // NRM likelihood for selected category k
        numerator = exp(item_params.a[k] * theta + item_params.c[k])
        denominator = sum_over_h(
            exp(item_params.a[h] * theta + item_params.c[h])
        )
        likelihood[theta] = numerator / denominator
        
        // Prior is the posterior from Phase 1
        posterior[theta] = likelihood[theta] * prior_posterior.density(theta)
    
    posterior = normalize(posterior)
    theta_hat = eap_point_estimate(grid, posterior)
    theta_se = eap_standard_error(grid, posterior, theta_hat)
    
    return EAPResult(theta=theta_hat, se=theta_se, posterior=posterior)

// ═══════════════════════════════════════════════════════════════
// PHASE 3: TRANSFER VALIDATION (T4)
// Model: NRM (same as Phase 2)
// ═══════════════════════════════════════════════════════════════

function eap_update_t4(prior_posterior, t4_response, item_params):
    // Identical structure to Phase 2 NRM update
    // prior_posterior is the Phase 2 posterior
    return eap_update_nrm(prior_posterior, t4_response, item_params)
```

### §5.5 Post-Cascade Mixture IRT Adjustment

```pseudocode
// ═══════════════════════════════════════════════════════════════
// MIXTURE IRT: POST-CASCADE SCORING
// Runs AFTER all tiers complete. Uses pre-estimated class params.
// ═══════════════════════════════════════════════════════════════

// Class definitions (estimated during calibration):
// Class 1: "Engaged" — standard IRT parameters apply
// Class 2: "Aberrant" — elevated guessing, reduced discrimination

function mixture_irt_adjustment(response_vector, tier_posteriors, 
                                 class_params):
    // response_vector: [t1t2_joint_score, t3_category, t4_category]
    // tier_posteriors: [posterior_1, posterior_2, posterior_3]
    // class_params: {
    //   class_1: {pi: 0.85, item_params: {...}},  // engaged
    //   class_2: {pi: 0.15, item_params: {...}}   // aberrant
    // }
    
    // ─── Step 1: Compute class-conditional likelihoods ───
    
    L_engaged = compute_response_likelihood(
        response_vector, 
        class_params.class_1.item_params
    )
    
    L_aberrant = compute_response_likelihood(
        response_vector, 
        class_params.class_2.item_params
    )
    
    // ─── Step 2: Posterior class membership ───
    
    // Heuristic prior from T3↔T4 consistency check
    consistency = check_t3_t4_consistency(response_vector)
    
    if consistency == "inconsistent":
        // Shift prior toward aberrant class
        prior_aberrant = min(class_params.class_2.pi * 2.0, 0.50)
        prior_engaged = 1.0 - prior_aberrant
    else:
        prior_engaged = class_params.class_1.pi
        prior_aberrant = class_params.class_2.pi
    
    P_engaged = prior_engaged * L_engaged
    P_aberrant = prior_aberrant * L_aberrant
    
    // Normalize
    total = P_engaged + P_aberrant
    P_engaged = P_engaged / total
    P_aberrant = P_aberrant / total
    
    // ─── Step 3: Adjust θ estimate ───
    
    if P_aberrant > 0.50:
        // High probability of aberrance
        // Use engaged-class θ but inflate SE
        final_theta = tier_posteriors[-1].theta
        final_se = tier_posteriors[-1].se * 1.5  // inflated uncertainty
        aberrance_flag = true
    else:
        // Standard case
        final_theta = tier_posteriors[-1].theta
        final_se = tier_posteriors[-1].se
        aberrance_flag = false
    
    return MixtureResult(
        theta=final_theta,
        se=final_se,
        P_engaged=P_engaged,
        P_aberrant=P_aberrant,
        aberrance_flag=aberrance_flag
    )


function check_t3_t4_consistency(response_vector):
    t3_cat = response_vector.t3_category  // e.g., "M1"
    t4_cat = response_vector.t4_category  // e.g., "Mastery"
    
    if t3_cat == t4_cat:
        return "consistent"
    
    if (t3_cat in misconception_categories) and (t4_cat == "Mastery"):
        return "inconsistent"  // guessing on T3 or learning between tiers
    
    if (t3_cat == "Mastery") and (t4_cat in misconception_categories):
        return "inconsistent"  // slipping on T4 or shallow mastery
    
    if (t3_cat in misconception_categories) and 
       (t4_cat in misconception_categories) and (t3_cat != t4_cat):
        return "inconsistent"  // unstable misconception state
    
    return "consistent"
```

### §5.6 Final Diagnostic Vector Assembly

```pseudocode
function assemble_diagnostic_vector(t3_response, t4_response,
                                     mixture_result, q_matrix):
    
    // ─── Case 1: Mastery (scored 3 at T1+T2, skipped T3/T4) ───
    if cascade_terminated_at == "mastery_gate":
        return DiagnosticVector(
            P_mastery=0.95,
            P_misconceptions={m: 0.01 for m in q_matrix.misconceptions},
            P_lack_of_knowledge=0.02,
            P_aberrant=0.02,
            theta=tier_posteriors[0].theta,
            theta_se=tier_posteriors[0].se,
            entropy=compute_entropy([0.95, 0.01, 0.01, 0.02, 0.02]),
            hard_classification="Mastery" if entropy < 1.0 else "Inconclusive"
        )
    
    // ─── Case 2: Lack of Knowledge (routing_LoK at T3) ───
    if t3_response == "routing_LoK":
        return DiagnosticVector(
            P_mastery=0.03,
            P_misconceptions={m: 0.02 for m in q_matrix.misconceptions},
            P_lack_of_knowledge=0.90,
            P_aberrant=0.05,
            theta=tier_posteriors[0].theta,
            theta_se=tier_posteriors[0].se,
            entropy=compute_entropy([0.03, 0.02, 0.02, 0.90, 0.05]),
            hard_classification="Lack_of_Knowledge"
        )
    
    // ─── Case 3: Full cascade completed ───
    
    // Count diagnostic signals
    t3_signal = t3_response  // "M1", "M2", or "Mastery"
    t4_signal = t4_response  // "M1", "M2", or "Mastery"
    
    // Base probabilities from response pattern
    probs = initialize_uniform_probs(q_matrix)
    
    // Weight by T3 signal
    if t3_signal in misconception_categories:
        probs[t3_signal] += 0.35
    elif t3_signal == "Mastery":
        probs["Mastery"] += 0.35
    
    // Weight by T4 signal
    if t4_signal in misconception_categories:
        probs[t4_signal] += 0.35
    elif t4_signal == "Mastery":
        probs["Mastery"] += 0.35
    
    // Incorporate mixture IRT aberrance
    probs["Aberrant"] = mixture_result.P_aberrant
    
    // Normalize to sum to 1
    probs = normalize(probs)
    
    entropy = compute_entropy(probs.values())
    
    if entropy < 1.0:
        hard_class = argmax(probs)
    else:
        hard_class = "Inconclusive"
    
    return DiagnosticVector(
        P_mastery=probs["Mastery"],
        P_misconceptions={m: probs[m] for m in q_matrix.misconceptions},
        P_lack_of_knowledge=probs["Lack_of_Knowledge"],
        P_aberrant=probs["Aberrant"],
        theta=mixture_result.theta,
        theta_se=mixture_result.se,
        person_fit_lz_star=compute_lz_star(response_vector, 
                                            tier_posteriors),
        entropy=entropy,
        hard_classification=hard_class
    )


function compute_entropy(probability_vector):
    // Shannon entropy in bits
    H = 0
    for p in probability_vector:
        if p > 0:
            H -= p * log2(p)
    return H
```

---

## §6 Calibration Engine (Offline)

### §6.1 Three-Phase Calibration Pipeline

```pseudocode
// ═══════════════════════════════════════════════════════════════
// PHASE A: COLD START (LLTM Predicted Parameters)
// Trigger: Item enters pool with 0 response data
// ═══════════════════════════════════════════════════════════════

function lltm_predict_parameters(item_metadata):
    // Design matrix from EQJS fields
    features = [
        item_metadata.cognitive_level,           // 1–6 Bloom's
        item_metadata.percent_correct / 100,     // facility index
        len(item_metadata.prerequisites),        // DAG depth
        item_metadata.concept_complexity,         // from curriculum
        item_metadata.num_reasoning_steps,        // estimated
        encode_domain(item_metadata.domain)       // one-hot
    ]
    
    // LLTM weights (estimated from existing MCQ response data)
    beta_predicted = dot_product(lltm_weights, features)
    
    // Conservative discrimination default
    alpha_predicted = 1.0  // Rasch assumption
    
    // For GPCM step difficulties: equally spaced defaults
    d_steps = [-0.5, 0.0, 0.5]  // for 0–3 scale
    
    return ColdStartParams(
        alpha=alpha_predicted,
        beta=beta_predicted,
        d_steps=d_steps,
        calibration_phase="A_cold_start",
        n_responses=0
    )

// ═══════════════════════════════════════════════════════════════
// PHASE B: ONLINE CALIBRATION (N = 50–200)
// Trigger: Item accumulates response data
// Uses D-optimal examinee selection
// ═══════════════════════════════════════════════════════════════

function d_optimal_select_examinee(item_params, available_examinees, 
                                    cumulative_info_matrix):
    // For each available examinee, compute information gain
    best_theta = null
    best_det = -infinity
    
    for examinee in available_examinees:
        theta_est = examinee.current_theta_estimate
        
        // Fisher information for this item at this θ
        I_new = fisher_information(theta_est, item_params)
        
        // Updated cumulative information matrix
        M_new = cumulative_info_matrix + I_new
        
        // D-optimal criterion: maximize determinant
        det_new = determinant(M_new)
        
        if det_new > best_det:
            best_det = det_new
            best_theta = theta_est
            best_examinee = examinee
    
    return best_examinee


function online_calibration_batch(item_id, response_data):
    // Run at N = 50, 100, 150, 200
    n = len(response_data)
    
    if n < 50:
        return  // too early
    
    // MML-EM estimation
    params = em_estimation(
        responses=response_data,
        model="GPCM" if item.tier in ["T1T2"] else 
              item.phase2_model,  // "NRM" or "GPCM"
        max_iterations=100,
        convergence_criterion=0.001
    )
    
    // Compare with LLTM predictions
    lltm_deviation = abs(params.beta - item.cold_start_params.beta)
    if lltm_deviation > 1.5:
        log_warning(f"Item {item_id}: empirical β deviates {lltm_deviation} "
                    f"from LLTM prediction. Check item features.")
    
    return OnlineParams(
        alpha=params.alpha,
        beta=params.beta,
        d_steps=params.d_steps if applicable,
        a_categories=params.a_k if NRM,
        c_categories=params.c_k if NRM,
        standard_errors=params.se,
        calibration_phase="B_online",
        n_responses=n
    )

// ═══════════════════════════════════════════════════════════════
// PHASE C: OPERATIONAL CALIBRATION (N ≥ 200)
// Trigger: Sufficient data for stable estimates
// ═══════════════════════════════════════════════════════════════

function operational_calibration(item_id, response_data):
    // Full calibration with robust SE
    params = em_estimation(
        responses=response_data,
        model=item.phase2_model,
        max_iterations=500,
        convergence_criterion=0.0001,
        compute_robust_se=true
    )
    
    // Fit statistics
    fit = compute_fit_statistics(params, response_data)
    
    if fit.RMSEA > 0.05 or fit.infit_MNSQ > 1.3:
        flag_item_for_review(item_id, "Poor model-data fit", fit)
    
    return OperationalParams(
        ...params,
        fit_statistics=fit,
        calibration_phase="C_operational",
        n_responses=len(response_data)
    )
```

### §6.2 Two-Tier IFA Calibration (Batch, Offline)

```pseudocode
// ═══════════════════════════════════════════════════════════════
// TWO-TIER IFA: Fit at calibration. Separates primary θ from 
// specific ζ (T2 method variance). Primary θ → runtime EAP.
// 
// Reference: KB Extraction 1 equations
// ═══════════════════════════════════════════════════════════════

function fit_two_tier_ifa(response_matrix, item_tier_assignments):
    // response_matrix: N_students × N_items
    // item_tier_assignments: which items belong to which testlet
    
    // ─── Define model structure ───
    
    // Primary dimension: Scientific Concept Mastery (θ)
    // Loads on ALL items (T1 and T2)
    primary_dimensions = 1  // P = 1 for current implementation
    
    // Specific dimensions: one per T1+T2 testlet cluster
    // Absorbs residual dependence within each concept cascade
    testlet_clusters = group_items_by_concept(item_tier_assignments)
    specific_dimensions = len(testlet_clusters)  // S = num concepts
    
    // ─── Identification constraints (KB Table 1) ───
    constraints = {
        "mu_theta": 0.0,           // primary mean fixed
        "mu_zeta": [0.0] * S,      // all specific means fixed
        "var_theta": 1.0,           // primary variance fixed
        "var_zeta": [1.0] * S,      // all specific variances fixed
        "cov_zeta_zeta": 0.0,       // specific dims uncorrelated
        "cov_theta_zeta": 0.0       // primary-specific uncorrelated
    }
    
    // ─── Estimation ───
    // MML-EM with reduced dimensionality:
    // Integration over (P + 1) dimensions per testlet, not (P + S)
    // Because specific dims are orthogonal → factored likelihood
    
    model = TwoTierIFA(
        n_primary=primary_dimensions,
        n_specific=specific_dimensions,
        testlet_map=testlet_clusters,
        constraints=constraints,
        link="logit",  // for dichotomous
        response_model="GPCM"  // for polytomous T1+T2 joint scores
    )
    
    results = model.fit(
        data=response_matrix,
        method="MML-EM",
        quadrature_points=21,  // per dimension
        max_iterations=200,
        convergence=0.001
    )
    
    // ─── Extract primary θ estimates for runtime ───
    // These are the θ values used in the sequential EAP (§5.4)
    // The ζ (specific) factors are estimated but NOT propagated
    // to runtime — they are absorbed at calibration
    
    for each student:
        student.calibrated_theta = results.primary_theta[student]
        student.calibrated_theta_se = results.primary_theta_se[student]
    
    // ─── Extract item parameters for runtime ───
    for each item:
        item.runtime_params = {
            "alpha": results.primary_loadings[item],  // α_j on θ
            "beta": results.intercepts[item],          // d_j
            "d_steps": results.step_params[item],      // if GPCM
            "gamma": results.specific_loadings[item],  // γ_js (logged, 
                                                       //  not used runtime)
            "testlet_variance": results.specific_variance[item.testlet]
        }
    
    return TwoTierResults(
        model=model,
        student_thetas=results.primary_theta,
        item_params=item.runtime_params,
        fit=results.fit_statistics
    )
```

### §6.3 Mixture IRT Calibration (Batch, Offline)

```pseudocode
// ═══════════════════════════════════════════════════════════════
// MIXTURE IRT: Estimate class-specific item parameters
// Reference: KB Extraction 2 equations
// ═══════════════════════════════════════════════════════════════

function fit_mixture_irt(response_matrix, n_classes=2):
    // Class 1: "Engaged" — standard IRT
    // Class 2: "Aberrant" — elevated guessing, reduced discrimination
    
    model = MixtureIRT(
        n_classes=n_classes,
        base_model="2PL",  // within each class
        // Bayesian priors for guessing/slipping
        guessing_prior=BetaPrior(alpha=1, beta=9),   // E[g] ≈ 0.10
        slipping_prior=BetaPrior(alpha=1, beta=19)    // E[s] ≈ 0.05
    )
    
    results = model.fit(
        data=response_matrix,
        method="EM",
        max_iterations=300,
        convergence=0.0001
    )
    
    // ─── Store class-specific parameters for runtime ───
    class_params = {
        "class_1_engaged": {
            "pi": results.mixing_proportions[0],  // e.g., 0.85
            "item_params": results.class_params[0] // standard a, b
        },
        "class_2_aberrant": {
            "pi": results.mixing_proportions[1],  // e.g., 0.15
            "item_params": results.class_params[1] // reduced a, shifted b
        }
    }
    
    return MixtureResults(
        class_params=class_params,
        student_class_posteriors=results.posterior_memberships,
        fit=results.fit_statistics
    )
```

### §6.4 G-DINA Q-Matrix Flip-Detection (Batch, Offline)

```pseudocode
// ═══════════════════════════════════════════════════════════════
// G-DINA FLIP-DETECTION
// Reference: KB Extraction 3 — Wald test algorithm
// Trigger: N = 200 (early warning), N = 500 (full validation)
// ═══════════════════════════════════════════════════════════════

function gdina_flip_detection(response_matrix, q_matrix, n_responses):
    
    // ─── Early Warning (N = 200): Point-Biserial Heuristic ───
    if n_responses >= 200 and n_responses < 500:
        for each item j:
            for each distractor d in item j:
                // Compute point-biserial between selecting d 
                // and overall θ estimate
                rpb = point_biserial(
                    selected_d = (responses[:, j] == d),
                    theta = student_theta_estimates
                )
                
                expected_direction = get_expected_direction(
                    q_matrix[j][d]  // the misconception mapping
                )
                
                // INVERSION CHECK: high-θ students selecting 
                // "low knowledge" distractor
                if rpb > 0.15 and expected_direction == "negative":
                    flag_item(j, d, "Q-matrix inversion suspected",
                              rpb=rpb, n=n_responses)
                
            // CONFLATION CHECK: inter-distractor correlation
            for each pair (d1, d2) in item j distractors:
                if q_matrix maps d1→M1 and d2→M2:
                    // Check if same students select d1 on this item
                    // and d2 on other items testing same concept
                    r_cross = cross_item_distractor_correlation(
                        d1, d2, concept=item.concept_id
                    )
                    if r_cross > 0.40:
                        flag_item(j, "M1/M2 conflation suspected",
                                  r_cross=r_cross)
    
    // ─── Full Validation (N ≥ 500): Wald Test ───
    if n_responses >= 500:
        Q_current = copy(q_matrix)
        converged = false
        max_iterations = 10
        iteration = 0
        
        while not converged and iteration < max_iterations:
            iteration += 1
            
            // Step 1: Fit G-DINA under current Q
            model = GDINA(Q=Q_current)
            results = model.fit(response_matrix, method="MML-EM")
            delta_hat = results.delta_estimates
            delta_cov = results.delta_covariance
            
            any_flip = false
            
            // Step 2: For each item j, each attribute k
            for each item j:
                for each attribute k:
                    // Wald test: H0: q_jk should be current value
                    h = wald_contrast_vector(j, k, Q_current)
                    
                    W = h.T @ inv(delta_cov[j]) @ h
                    df = degrees_of_freedom(j, k)
                    p_value = 1 - chi2_cdf(W, df)
                    
                    if p_value < 0.05:
                        // Flip improves fit
                        Q_current[j][k] = 1 - Q_current[j][k]
                        any_flip = true
                        log_flip(j, k, W, p_value)
            
            // Step 3: Check convergence via BIC
            new_bic = compute_bic(results)
            if not any_flip or new_bic >= previous_bic:
                converged = true
            previous_bic = new_bic
        
        // Output: validated Q-matrix + flip log
        return QMatrixValidation(
            original_q=q_matrix,
            validated_q=Q_current,
            flips=flip_log,
            converged=converged,
            final_bic=new_bic
        )
```

### §6.5 DIF Monitoring (Post-Calibration)

```pseudocode
// ═══════════════════════════════════════════════════════════════
// DIF AUDIT: Runs after N ≥ 500 per item
// Grouping: gender, medium of instruction, board of origin
// ═══════════════════════════════════════════════════════════════

function dif_audit(item_id, response_data, grouping_vars):
    results = {}
    
    for group_var in grouping_vars:
        // Mantel-Haenszel for uniform DIF
        mh = mantel_haenszel_test(
            responses=response_data,
            grouping=group_var,
            matching=student_theta_estimates
        )
        
        // Logistic regression for nonuniform DIF
        lr = logistic_regression_dif(
            responses=response_data,
            grouping=group_var,
            matching=student_theta_estimates
        )
        
        delta_mh = abs(mh.log_odds_ratio * 2.35)  // ETS Δ scale
        
        if delta_mh < 1.0:
            action = "MONITOR"
        elif delta_mh < 1.5:
            action = "FLAG_FOR_REVIEW"
        else:
            action = "REMOVE_FROM_POOL"
        
        results[group_var] = {
            "delta_mh": delta_mh,
            "mh_p_value": mh.p_value,
            "lr_uniform_p": lr.uniform_p_value,
            "lr_nonuniform_p": lr.nonuniform_p_value,
            "action": action
        }
    
    return DIFResults(item_id=item_id, results=results)
```

---

## §7 Runtime Session Flow (Complete)

```pseudocode
// ═══════════════════════════════════════════════════════════════
// MAIN SESSION CONTROLLER
// ═══════════════════════════════════════════════════════════════

function run_diagnostic_session(student_id, concept_id):
    
    // ─── INITIALIZATION ───
    prior = initialize_prior(student_id)  // §5.4
    item_pool = load_calibrated_items(concept_id)
    q_matrix = load_q_matrix(concept_id)
    class_params = load_mixture_params()  // from §6.3
    
    // ─── SELECT T1 ITEM ───
    // Target P(correct) ≈ 0.70 at student's current θ
    t1_item = select_item_mfi(item_pool.t1_items, prior.theta)
    
    // ─── PRESENT T1 (MCQ) ───
    t1_response = present_and_collect(t1_item)
    t1_correct = (t1_response == t1_item.correct_answer)
    
    // ─── PRESENT T2 (Reasoning) ───
    t2_prompt = generate_t2_prompt(t1_item)
    t2_response_text = present_and_collect(t2_prompt)
    
    // ─── SCORE T2 (LLM Rater) ───
    t2_result = score_t2(t2_response_text, t1_item)  // §5.1
    t2_score = t2_result.T2_score
    
    // ─── COMPUTE JOINT SCORE ───
    joint_score = compute_joint_score(t1_correct, t2_score)  // §5.2
    
    // ─── EAP UPDATE: PHASE 1 ───
    posterior_1 = eap_update_gpcm(prior, joint_score, 
                                   t1_item.gpcm_params)  // §5.4
    
    // ─── MASTERY GATE ───
    if joint_score == 3:
        diagnostic = assemble_diagnostic_vector(
            cascade_terminated_at="mastery_gate",
            tier_posteriors=[posterior_1]
        )
        save_session(student_id, concept_id, diagnostic)
        return diagnostic
    
    // ─── SELECT AND PRESENT T3 ───
    t3_item = select_item_diagnostic(
        item_pool.t3_items, posterior_1.theta, q_matrix
    )
    t3_response = present_and_collect(t3_item)
    
    // ─── CHECK ROUTING ───
    if t3_response.maps_to == "routing_LoK":
        diagnostic = assemble_diagnostic_vector(
            t3_response="routing_LoK",
            cascade_terminated_at="T3_LoK",
            tier_posteriors=[posterior_1]
        )
        save_session(student_id, concept_id, diagnostic)
        return diagnostic
    
    // ─── EAP UPDATE: PHASE 2 ───
    posterior_2 = eap_update_nrm(
        posterior_1, t3_response.maps_to, 
        t3_item.nrm_params
    )
    
    // ─── SELECT AND PRESENT T4 ───
    t4_item = select_item_diagnostic(
        item_pool.t4_items, posterior_2.theta, q_matrix
    )
    t4_response = present_and_collect(t4_item)
    
    // ─── EAP UPDATE: PHASE 3 ───
    posterior_3 = eap_update_nrm(
        posterior_2, t4_response.maps_to, 
        t4_item.nrm_params
    )
    
    // ─── POST-CASCADE: MIXTURE IRT ADJUSTMENT ───
    response_vector = {
        t1t2_joint_score: joint_score,
        t3_category: t3_response.maps_to,
        t4_category: t4_response.maps_to
    }
    
    mixture_result = mixture_irt_adjustment(
        response_vector, 
        [posterior_1, posterior_2, posterior_3],
        class_params
    )
    
    // ─── ASSEMBLE FINAL DIAGNOSTIC ───
    diagnostic = assemble_diagnostic_vector(
        t3_response=t3_response.maps_to,
        t4_response=t4_response.maps_to,
        mixture_result=mixture_result,
        q_matrix=q_matrix,
        tier_posteriors=[posterior_1, posterior_2, posterior_3]
    )
    
    save_session(student_id, concept_id, diagnostic)
    return diagnostic
```

---

## §8 Output Schemas

### §8.1 Per-Session Output

```json
{
  "session_id": "SES-2026-02-21-0347",
  "student_id": "STU-2024-0347",
  "concept_id": "CHEM-AS-5.2.1",
  "timestamp": "2026-02-21T14:32:00Z",
  
  "cascade": {
    "T1_item_id": "T1-CHEM-5.2.1-012",
    "T1_response": "B",
    "T1_correct": true,
    "T2_response_text": "The activation energy is...",
    "T2_scorer_model": "claude-sonnet-4-5",
    "T2_score": 1,
    "T2_scoring_rationale": "Correct concept named but causal chain incomplete.",
    "T1T2_joint_score": 2,
    "T3_item_id": "T3-CHEM-5.2.1-004",
    "T3_response": "A",
    "T3_maps_to": "M1",
    "T4_item_id": "T4-CHEM-5.2.1-007",
    "T4_response": "C",
    "T4_maps_to": "M1"
  },
  
  "estimation": {
    "theta_prior": {"mean": 0.0, "sd": 1.0},
    "theta_post_T1T2": {"mean": 0.22, "sd": 0.71},
    "theta_post_T3": {"mean": -0.15, "sd": 0.52},
    "theta_post_T4": {"mean": -0.31, "sd": 0.41},
    "theta_final": {"mean": -0.31, "sd": 0.41},
    "mixture_P_engaged": 0.91,
    "mixture_P_aberrant": 0.09,
    "aberrance_flag": false,
    "t3_t4_consistency": "consistent",
    "person_fit_lz_star": -0.87
  },
  
  "diagnostic_output": {
    "P_mastery": 0.05,
    "P_M1_mass_not_gas": 0.72,
    "P_M2_reaction_loss": 0.08,
    "P_lack_of_knowledge": 0.12,
    "P_aberrant": 0.03,
    "entropy_bits": 0.91,
    "hard_classification": "M1",
    "confidence": "high"
  }
}
```

### §8.2 Per-Item Calibration Record

```json
{
  "item_id": "T3-CHEM-5.2.1-004",
  "tier": "T3",
  "concept_id": "CHEM-AS-5.2.1",
  "generation_source": "Bo2_pathway_A",
  "calibration_phase": "C_operational",
  "n_responses": 412,
  
  "parameters": {
    "model": "NRM",
    "category_slopes": {
      "M1": 1.42, "M2": 0.89, "Mastery": 1.67
    },
    "category_intercepts": {
      "M1": -0.23, "M2": -0.87, "Mastery": 0.91
    },
    "standard_errors": {
      "slopes": {"M1": 0.12, "M2": 0.15, "Mastery": 0.11},
      "intercepts": {"M1": 0.09, "M2": 0.11, "Mastery": 0.08}
    }
  },
  
  "fit_statistics": {
    "RMSEA": 0.032,
    "infit_MNSQ": 1.04,
    "outfit_MNSQ": 0.97
  },
  
  "q_matrix_validation": {
    "last_validated_at_n": 500,
    "flips_detected": 0,
    "validated": true
  },
  
  "dif_status": {
    "gender_delta_mh": 0.34,
    "medium_delta_mh": 0.78,
    "overall_action": "MONITOR"
  },
  
  "two_tier_params": {
    "primary_loading_alpha": 1.42,
    "specific_loading_gamma": 0.31,
    "testlet_cluster": "CHEM-AS-5.2.1"
  }
}
```

---

## §9 Automation Trigger (Version 2 Exit Criteria)

```pseudocode
// ═══════════════════════════════════════════════════════════════
// CHECK WEEKLY: Can we reduce HITL?
// ═══════════════════════════════════════════════════════════════

function check_automation_readiness():
    
    // Criterion 1: Volume
    n_validated_pairs = count_logs(
        log_type="Bo2_generation",
        human_validation.q_matrix_alignment_pass=true
    )
    volume_met = (n_validated_pairs >= 1000)
    
    // Criterion 2: Reward model agreement
    // Train reward model on existing logs
    // Test on held-out 20%
    reward_model = train_reward_model(
        triples=convert_logs_to_dpo_triples(log_directory)
    )
    holdout_agreement = evaluate_on_holdout(reward_model, holdout_set)
    agreement_met = (holdout_agreement >= 0.85)
    
    // Criterion 3: Override rate
    // In last 100 items with automated pre-selection:
    // How often does human override the model's choice?
    recent_overrides = count_overrides(last_n=100)
    override_rate = recent_overrides / 100
    override_met = (override_rate < 0.05)
    
    // ─── Decision ───
    if volume_met and agreement_met and override_met:
        return AutomationStatus(
            ready=true,
            mode="AUTOMATED_WITH_10_PERCENT_AUDIT",
            message="All three criteria met. Switch to automated "
                    "selection with 10% random human audit."
        )
    else:
        return AutomationStatus(
            ready=false,
            mode="100_PERCENT_HITL",
            blockers={
                "volume": n_validated_pairs if not volume_met else "OK",
                "agreement": holdout_agreement if not agreement_met else "OK",
                "override": override_rate if not override_met else "OK"
            }
        )
```

---

## §10 Invariant Compliance Matrix

Every section maps to G1–G5. Anything unmapped is deleted.

| Section | G1 Diagnostic | G2 Invariance | G3 Parity | G4 Scale | G5 Aberrance |
|---------|:---:|:---:|:---:|:---:|:---:|
| §1 Q-Matrix Extraction | ✓ | | ✓ | ✓ | |
| §2A Bo2 Generator | ✓ | | ✓ | ✓ | |
| §2B Single Generator | ✓ | | ✓ | ✓ | |
| §3 Psychometric Audit | | ✓ | ✓ | | |
| §4 Logging Schema | | | ✓ | ✓ | |
| §5.1 T2 Rubric | ✓ | ✓ | | | |
| §5.2 Joint Scoring | ✓ | | | | |
| §5.3 Routing | ✓ | | | | |
| §5.4 Sequential EAP | ✓ | ✓ | | | |
| §5.5 Mixture IRT | | | | | ✓ |
| §5.6 Diagnostic Vector | ✓ | | | | ✓ |
| §6.1 Calibration Pipeline | | ✓ | | ✓ | |
| §6.2 Two-Tier IFA | | ✓ | | | |
| §6.3 Mixture IRT Cal. | | | | | ✓ |
| §6.4 G-DINA Flip | ✓ | ✓ | | | |
| §6.5 DIF Monitoring | | ✓ | | | |
| §7 Runtime Flow | ✓ | ✓ | | | ✓ |
| §9 Automation Trigger | | | ✓ | ✓ | |

---

**END OF V8 CONSTRUCTION MANUAL**

No additions. No omissions. Execute.
