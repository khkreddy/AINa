# SKILL: Protocol Selection for Diagram Encoding

**Skill ID:** SKILL-protocol-selection  
**Version:** 1.0  
**Governs:** Selecting the correct encoding protocol for diagrams in raw questions  
**Reference:** `protocols/protocol-registry.json`

---

## 1. Trigger

This skill activates when:
- A raw question contains a diagram, figure, graph, or visual element
- Stage 1 (Q-Matrix Extraction) detects `diagram_dependent == true`
- Stage 2-Bo2 Pathway B needs to generate a new `structured_description`

## 2. Decision Tree

```
Question contains a visual element?
    │
    NO → No protocol needed. diagram_dependent = false.
    │
    YES
    │
    What type of visual?
    │
    ├── Laboratory apparatus / experiment setup
    │   → CESP-1.0 (Chemical Experiment Setup Protocol)
    │
    ├── Phase diagram / ternary plot / region-partitioned chart
    │   → PDDC-1.0 (Phase Diagram Data Chart Protocol)
    │
    ├── Time-series / seasonal / periodic graph
    │   → TS-PG-1.2 (Time-Series Parametric Graph Protocol)
    │
    ├── Stacked bar chart / grouped bar chart / area chart
    │   → GRP-STACKED-1.0
    │
    ├── Circuit diagram / pipeline / connectivity diagram
    │   → UCCP-1.1 (if available)
    │
    ├── Simple labeled diagram (anatomy, cross-section, etc.)
    │   → Use semantic_description field directly
    │     No formal protocol required for simple labeled diagrams
    │     But structured_description MUST still be provided
    │
    └── Unknown / ambiguous
        → Flag: requires_human_decision = true
        → DO NOT guess protocol
        → Log: "Diagram type not matched to any protocol"
```

## 3. Protocol Trigger Keywords

Use these to match raw question content to protocols:

### CESP-1.0 Triggers
```
apparatus, experiment setup, lab diagram, distillation, titration,
electrolysis, gas collection, filtration, bunsen burner, condenser,
flask, beaker, test tube, burette, pipette, crucible, evaporating dish,
thermometer, retort stand, delivery tube, trough, gas syringe,
heating, reflux, chromatography, calorimetry, electrochemical cell
```

### PDDC-1.0 Triggers
```
phase diagram, triple point, critical point, phase boundary,
solid liquid gas, melting curve, boiling curve, sublimation curve,
soil texture triangle, ternary diagram, alloy phase, binary phase,
region-partitioned, state diagram
```

### TS-PG-1.2 Triggers
```
seasonal graph, temperature over months, rainfall over year,
periodic curve, sinusoidal, time series, monthly data,
cyclical pattern, annual variation, daylight hours
```

### GRP-STACKED-1.0 Triggers
```
stacked bar, grouped chart, bar graph with categories,
stacked area, comparative bar, resource extraction graph,
population pyramid, composition chart
```

## 4. Protocol Loading Rules

1. Load protocol file from `protocols/{protocol_id}.md`
2. Read the protocol's JSON schema section
3. When encoding a diagram in EQJS:
   - Set `content.stimulus.diagrams[].protocol` to the protocol ID
   - Follow the protocol's mandatory fields exactly
   - Include all invariants in `metadata.validation_status.checked_invariants`

## 5. Stage 2-Bo2 Pathway B: New Diagram Generation

When generating a NEW diagram for Pathway B (Schema-Mutation):

1. Identify the protocol used in the ORIGINAL EQJS diagram
2. The new diagram MUST use the SAME protocol
3. Follow the protocol's JSON schema for `structured_description`
4. Mutations allowed:
   - Different apparatus (CESP: different experiment with same mechanism)
   - Different data (PDDC: different substance's phase diagram)
   - Different time period (TS-PG: different location's seasonal data)
5. Mutations NOT allowed:
   - Switching protocol (e.g., replacing a CESP diagram with a PDDC diagram)
   - Omitting mandatory fields
   - Violating protocol invariants

## 6. Common Pitfalls

| Pitfall | Rule |
|---------|------|
| Simple image described only in question text | Still needs `diagram_dependent: true` if understanding the diagram is necessary to answer |
| Table of data (not a chart) | NOT a diagram. Do not assign protocol. Encode as structured data in question content. |
| Chemical equation or formula | NOT a diagram. Encode as text with appropriate formatting. |
| Molecular structure | Out of scope for all current protocols. Use semantic_description only. Flag if complex. |
| Multiple diagrams in one question | Each diagram gets its own entry in `stimulus.diagrams[]`, each with its own protocol |
| Diagram is decorative (not needed to answer) | Set `diagram_dependent: false`. Do not encode. Note in expert_comment. |

## 7. Protocol Registry Maintenance

The master list of protocols lives at `protocols/protocol-registry.json`.

When a new protocol is added:
1. Add the protocol .md file to `protocols/`
2. Add an entry to protocol-registry.json with: id, name, status, file, scope, triggers
3. Update this skill document's decision tree (§2) and trigger keywords (§3)
4. All future conversions will automatically detect the new protocol via trigger matching

Current registry:
```
CESP-1.0   — Chemical Experiment Setup (DRAFT)
PDDC-1.0   — Phase Diagram Data Chart (FROZEN)
TS-PG-1.2  — Time-Series Parametric Graph (FROZEN)
GRP-STACKED-1.0 — Stacked Bar Chart (FROZEN)
```
