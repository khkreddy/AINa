# SKILL: Human Validation (HITL)

**Skill ID:** SKILL-human-validation  
**Version:** 1.0  
**Governs:** All human review and approval of AI-native assessment items  
**Reference:** V8 PRISM Construction Manual §4, §9

---

## 1. Trigger

This skill activates when:
- An item in `ai-native/` has `approval_status == "awaiting_human_validation"`
- A human runs `scripts/human_validate.py`
- A human manually reviews an item

## 2. Validator Requirements

- Validator MUST have a unique `validator_id` (format: VAL-xxx)
- Validator MUST be a subject-matter expert in the item's domain
- Validator MUST understand the Q-matrix concept and misconception mapping
- Validator ID is logged with EVERY decision for future HRM modeling

## 3. Review Checklist (Mandatory for Every Item)

### 3.1 For Bo2 Items (diagram_dependent == true)

The validator sees:
1. **Original EQJS question** — the seed item with full context
2. **Q-Matrix** — extracted misconceptions and core concept
3. **Candidate A** (Text-Abstraction) — T3 probe + T4 transfer, text only
4. **Candidate B** (Schema-Mutation) — T3 probe + T4 transfer, with new diagrams

The validator must assess:

| Check | Question | Action if Fails |
|-------|----------|-----------------|
| **Q-Matrix Alignment** | Does EACH distractor in the selected candidate map to EXACTLY ONE misconception in the Q-matrix? Could a student select a distractor for a reason NOT captured in the Q-matrix? | Set `q_matrix_alignment_pass = false`. Explain in notes. |
| **Diagnostic Purity** | Would selecting distractor X strictly require holding misconception X? Or could poor phrasing, reading difficulty, or an unlisted misconception cause the same selection? | Reject candidate. |
| **Transfer Distance** | Is T4 genuinely in a different domain? Not just a surface swap? | Reject candidate. |
| **Construct Purity** | Could a student fail due to vocabulary, reading level, or domain knowledge outside the curriculum? | Reject candidate. |
| **Scientific Accuracy** | Is the correct answer actually correct? Is the mechanism accurately described? | Reject candidate. Flag for urgent review. |

### 3.2 For Single-Generation Items (auto_approved)

These items were auto-approved by Stage 3. Human review is:
- **Not required** for routine items
- **Required** for items flagged with warnings during audit
- **Sampled** at 10% rate for ongoing quality monitoring

### 3.3 For Failed-Audit Items

Items with `approval_status == "failed_audit"`:
- Require human review to determine if the item is salvageable
- Validator may manually edit T3/T4 and approve
- Or validator may flag for complete regeneration

## 4. Decision Recording

### 4.1 Approval Decision
```json
{
  "human_choice": "A" | "B",
  "q_matrix_alignment_pass": true | false,
  "q_matrix_alignment_notes": "Any concerns about distractor mapping",
  "rejection_reason": null,
  "rejection_explanation": null
}
```

### 4.2 Rejection Decision
```json
{
  "human_choice": null,
  "q_matrix_alignment_pass": false,
  "rejection_reason": "Construct_Violation | Dependency_Failure | Scale_Misfit | Other",
  "rejection_explanation": "Specific explanation of what's wrong and why"
}
```

### 4.3 Rejection Reason Taxonomy

| Reason | Definition | Example |
|--------|------------|---------|
| **Construct_Violation** | A distractor does not map cleanly to its intended misconception. A student could select it for a different cognitive reason. | Distractor B mapped to "confuses mass with volume" but the phrasing also attracts students who confuse mass with weight. |
| **Dependency_Failure** | T3 or T4 has an unintended dependency on the seed item context, violating de-contextualization. | T3 uses the same chemical compound as T1, so a student who memorized the T1 answer could shortcut T3. |
| **Scale_Misfit** | T3 or T4 is dramatically easier or harder than intended, reducing diagnostic value. | T3 correct answer is obvious to anyone who read the question, regardless of conceptual understanding. |
| **Other** | Catch-all for issues not in the above categories. | Scientific inaccuracy, ambiguous phrasing, culturally inappropriate content. |

## 5. RLVR/DPO Signal Generation

Every human decision on a Bo2 item generates a training signal:

```json
{
  "prompt": "<reconstructed Stage 2 system+human prompt>",
  "winner": "<full output of selected candidate>",
  "loser": "<full output of rejected candidate>",
  "reason_category": "<rejection_reason for loser>",
  "reason_text": "<rejection_explanation for loser>",
  "validator_id": "<who made this decision>",
  "q_matrix_aligned": true | false
}
```

Rules:
- ONLY generate triple if `q_matrix_alignment_pass == true`
- If BOTH candidates are rejected, no triple is generated (log as "both_rejected")
- The `reason_category` explains WHY the loser lost, not just which was chosen

## 6. File Movement on Approval

```
On APPROVE:
  1. Update ai-native/{paper}/{item}_ainative.json:
     - Set approval_status = "human_approved"
     - Set candidates.selected_candidate = "A" or "B"
     - Add human_validation block
  2. Copy to ai-native-ready/{paper}/{item}_approved.json
  3. Append to metadata/human-approvals/approvals.jsonl
  4. Append RLVR triple to metadata/bo2-generation-logs/

On REJECT:
  1. Update ai-native/{paper}/{item}_ainative.json:
     - Set approval_status = "rejected"
     - Add human_validation block with rejection details
  2. DO NOT copy to ai-native-ready/
  3. Append to metadata/human-approvals/approvals.jsonl
  4. Item remains in ai-native/ for potential re-generation
```

## 7. Weekly Audit Protocol

Every week, a senior validator reviews:
- 10% of auto_approved items (random sample)
- All items where `q_matrix_alignment_pass == false` but item was still selected
- Override rate calculation: (overrides in audit) / (total audited)

If override rate > 5%: flag the generation pipeline for review.

## 8. Automation Transition

Current mode: **100% HITL** on all Bo2 items.

Transition to automated selection when ALL criteria met:
1. ≥1,000 validated Bo2 pairs with `q_matrix_alignment_pass == true`
2. Reward model achieves ≥85% agreement with human on held-out set
3. Human audit reduced to 10% with <5% override rate

After transition:
- Reward model selects candidate automatically
- 10% random sample still goes to human review
- If override rate exceeds 5% at any weekly audit, revert to 100% HITL
