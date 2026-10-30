# No Data Task — scoring criteria (draft for the shared document)

Two halves, two scoring regimes. The synthetic fragment is scored automatically; the field-grammar half is scored by a language expert. Both are stated separately below so that neither half's claims are read against the other.

## Part A. Synthetic fragment (automatic)

Gold is computed from the specification, never annotated. All checks are deterministic and the checker is published with the generator after each cycle.

| Item type | Checker | Metric |
|---|---|---|
| Parse | the organisers' parser for the released grammar | grammaticality accuracy; derivation exact match (tree equality) |
| Interpret | model checking on the released models and on models withheld from participants; a prover check of gold ↔ submitted as a bonus when it terminates | truth-value agreement on every model (released and withheld); for ambiguous items, set equality of readings modulo equivalence, plus reading recall |
| Infer | Prover9 / Mace4 on the submitted logical forms (tools track); proof checker for the fixed calculus (no-tools track) | label accuracy; certificate validity, reported separately. A neutral certificate is two models of the premises, one making the conclusion true and one false |
| Break (optional) | the same checkers on the submitted gold | admitted items; fooling rate on the other systems |

Reporting:
- Every score is reported per variant: nonce, natural-language twin (per language), scrambled order, counter-English. The counter-English drop relative to nonce is the headline per-system number.
- Every score is reported per phenomenon level (year one: 1 quantification, 2 negation and monotonicity, 3 relative clauses and scope ambiguity).
- Results are reported by declared system type (prompted model, prover loop, program synthesis, neuro-symbolic, fine-tuned) rather than on one leaderboard.
- The compiled specification (100% by construction) and a student human baseline appear in every table.
- A control fragment with an inconsistent specification is included; a high score on it is reported as spec-ignoring.

## Part B. Field-grammar language

Scored by a language expert on an acceptability scale. Criteria are defined by the organisers of that half (Maria, George); they go here when agreed.

## Shared

- Every submission declares its track (model alone / model with tools) and system type, and is accompanied by a short experiment report; the report is required for a result to appear in the overview.
- Multiple submissions per team are welcome; negative results are reported.
