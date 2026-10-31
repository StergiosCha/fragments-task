# Submission format

A submission is a directory:

```
my_submission/
  submission.json     who you are, your track and your system type
  nonce.jsonl         answers for the nonce variant
  english.jsonl       answers for the english variant
  scrambled.jsonl     answers for the scrambled variant
  counter.jsonl       answers for the counter variant
```

You may leave out variants, but the nonce → counter drop can only be reported if both `nonce.jsonl` and `counter.jsonl` are present.

Check your files before submitting:

```
cd generator
python3 validate.py --variant ../fragments/practice_seed0/nonce --submission ../my_submission/nonce.jsonl
python3 score.py --fragment ../fragments/practice_seed0 --submission ../my_submission     # practice gold only
```

## submission.json

```json
{"team": "Athens", "system": "gpt-x zero-shot", "track": "model-alone", "system_type": "prompted-model"}
```

- `track`: `model-alone` (the model's outputs, from the specification in its context) or `model-with-tools` (the model with a prover, or with code it writes itself).
- `system_type`: `prompted-model`, `prover-loop`, `program-synthesis`, `neuro-symbolic` or `fine-tuned`.

## Answer files

One JSON object per line, one line per item, with the item's `id`. Items are numbered identically in all four variants: item 17 of `counter` is the twin of item 17 of `nonce`. An item you do not answer, or whose line has an error, is scored as wrong. The validator lists every such line with the reason.

### parse

```json
{"id": 17, "grammatical": true, "tree": "[S [NP [Det kro] [N blicket]] [VP [TV fepps] [NP [PN tam]]]]"}
{"id": 18, "grammatical": false}
```

`tree` is required when `grammatical` is true. Trees are compared up to whitespace.

The tree lists each node's children in the order of the grammar's *canonical* rules (`S -> NP VP`, `VP -> TV NP`, …), also in the scrambled variant. This is how the gold is written today. Whether scrambled trees should follow the scrambled rule order instead is an open question (AUDIT.md, B4).

### interpret

```json
{"id": 42, "lfs": ["! [X] : (blicket(X) => ? [Y] : (wug(Y) & fepps(X,Y)))"],
 "truth": [{"M1": true, "M2": false}]}
```

- `lfs`: the logical forms, one per reading (an ambiguous sentence has several).
- `truth`: one object per formula in `lfs`, giving its truth value in each released model.

Formulas use TPTP first-order syntax:

| | |
|---|---|
| quantifiers | `! [X] :` (for all), `? [X] :` (there is); several variables as `! [X,Y] :` |
| connectives | `~`, `&`, `\|`, `=>`, `<=>` |
| names | proper names and predicates exactly as in `semantics.txt` (lower case); variables in upper case |

The specification's own notation, `forall x (P(x) -> Q(x))` and `exists x (...)`, is also accepted. Binding, tightest first: `~` and quantifiers (a quantifier's scope is the next unit, so bracket longer bodies), then `&`, then `|`, then `=>` (right-associative) and `<=>`. When in doubt, add brackets.

Two formulas count as the same reading when they are equivalent. At present the scorer tests this by evaluating both on every released *and withheld* model.

### infer

```json
{"id": 88, "label": "entailment",
 "lfs": {"premises": ["! [X] : (blicket(X) => daxes(X))", "blicket(tam)"], "conclusion": "daxes(tam)"},
 "certificate": {"proof": "..."}}
{"id": 89, "label": "neutral",
 "lfs": {"premises": ["daxes(tam)"], "conclusion": "daxes(ren)"},
 "certificate": {"models": [{"D": ["a", "b"], "tam": "a", "ren": "a", "daxes": ["a"], "blicket": [], "fepps": []},
                            {"D": ["a", "b"], "tam": "a", "ren": "b", "daxes": ["a"], "blicket": [], "fepps": []}]}}
```

- `label`: `entailment`, `contradiction` or `neutral`.
- `lfs`: one formula per premise, in the item's order, and the conclusion.
- `certificate`:
  - for entailment and contradiction, `{"proof": "..."}`, a non-empty proof. At present the scorer re-derives the label from your formulas with Prover9; it does not read the proof text.
  - for neutral, `{"models": [m1, m2]}`: two models of the premises, the conclusion true in one and false in the other (either order).

  A model is written as in `models.json`: `D` lists the elements, each proper name maps to one element, each one-place predicate to a list of elements and each two-place predicate to a list of pairs `[x, y]`. Every name and predicate of the lexicon must be given, and nothing else.
- The label and the certificate are scored separately. Only a missing or unknown `label` makes an infer answer unscorable. Problems with `lfs` or `certificate` make the certificate invalid, and the validator says why, but the label is still scored.
