# Change-Type Taxonomy for FCA Policy Documents

A document is assigned **exactly one** label describing the *principal* effect it
has on firms' obligations. Choose the label that best matches the document's
headline action — when a document mixes effects (common in FCA outputs), label
by the **dominant** effect as stated in the abstract/feedback summary.

## Labels

| Label | Meaning | Typical documents |
|---|---|---|
| `new_rule` | Creates a new obligation, permission, regime or reporting requirement that did not exist before. | Policy Statements introducing a fresh regime; new Handbook module; new product/process rules. |
| `amendment` | Alters an existing rule, Handbook provision, form or process — tightening, loosening, or restructuring. | Policy Statements amending existing instruments; Handbook Notices; changes to reporting thresholds. |
| `consultation` | Seeks views on *proposed* changes; nothing is final or binding yet. | Consultation Papers; Discussion-style CPs; draft instruments published for comment. |
| `guidance` | Non-binding expectations, interpretation, good/bad practice, or clarification of how rules apply. | Finalised Guidance (FG); Q&A; Dear-CEO letters codified into guidance; technical notes. |
| `no_change` | Confirms that no rule change results — feedback statements, withdrawals, or outcome summaries with no regulatory impact. | Feedback Statements following a CP where the FCA decided not to proceed; withdrawal notices; general updates. |

## Decision rules

1. **A Consultation Paper is `consultation`** — even if it also describes
   proposed rules — because nothing is binding. (Unless it is a *feedback*
   statement: see rule 4.)
2. **A Policy Statement that changes rules is `amendment`** if it *modifies
   existing* obligations; **`new_rule`** if it establishes an obligation where
   none existed. Use the paper's own wording: "amends"/"changes"/"updates" →
   `amendment`; "introduces"/"creates"/"establishes" → `new_rule`.
3. **Finalised Guidance is `guidance`** unless the same document contains
   binding rule changes — then use `amendment` (rule changes dominate guidance).
4. **Feedback/response statements** that report consultation outcomes with
   **no resulting rule** → `no_change`. If a feedback statement *confirms* the
   rules will proceed unchanged, it is the PS's job, not this doc's → still
   `no_change`.
5. **Handbook Notices (HN)** almost always `amendment` (they enact changes to
   the Handbook); mark `new_rule` only when a genuinely new module/section is
   introduced.
6. **Draft Q&As and technical annexes** → `guidance` (interpretive material).

## Edge cases (decide once, record in Notes)

- *Superseded/withdrawn documents* → `no_change` (note "superseded by …").
- *Joint FCA/PRA or FCA/gov.uk documents*: label by the FCA's own section; if
  the FCA contribution is guidance-only, `guidance`.
- *CPs whose title contains "feedback"* → check the body: if it only reports
  feedback and proceeds no further, `no_change`; if it proposes *new* follow-up
  questions, `consultation`.
- *Documents that are mostly `guidance` but contain one mandatory deadline* →
  `guidance` (non-binding dominates unless the core of the document is binding).

## Filenames and storage

- Labeller works in `data/labelling/sample.csv` (fill `label` and optional
  `notes`).
- Source text for review: `data/text/<stem>.txt`.
- Completed labels should be committed back as `data/labelling/labels.csv`
  (same columns, `label` filled) — the canonical training file.
