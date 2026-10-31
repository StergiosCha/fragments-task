# Fragments 2027: repository audit (Phase 1)

*Audit of `main` at `c665107`, 31 October 2026. Read-only: no code, data or page was changed. All probes ran from a scratch directory outside the repository.*

The spec here is the task page (`index.html`, served at stergioscha.github.io/fragments-task; the live URL was not reachable from the audit sandbox, so the repository copy was read), together with `lab-materials/scoring_criteria.md` and `lab-materials/task_page.md` where they add detail.

---

## 0. Three things to act on before anything else

1. **The released practice gold contains a wrong label, caused by a Prover9 variable-naming bug.** In Prover9, a free name beginning with **u, v, w, x, y or z is a variable**. `prover._p9` passes proper-name constants through unchanged, and the nonce generator produces names starting with *v*, *w* and *z*. So `wutbu(wonbis)` ("Wonbis wutbus") reaches Prover9 as `wutbu(x)` ("everything wutbus"). The committed proof shows it (`2 wutbu(x). [assumption].`). Any premise set with such a constant can become inconsistent, and Prover9 then "proves" whatever it is asked first.
   - `practice_seed0/counter` item 47: *mislup not wutbu; wonbis wutbu ⊢ mislup wutbu*. Gold = **entailment**; the correct label is **contradiction** (premise 1 is the negation of the conclusion). A counter-model is easy to find.
   - `test_seed1`: nonce #86, scrambled #107 and #108 are labelled *contradiction*; scrambled #107's conclusion is literally its first premise.
   - In total, **4 of 112** committed entailment/contradiction labels are refuted by an explicit model. All four involve the u–z constant (`wonbis` in practice, `vossop` in seed 1). Neutral labels are unaffected, because they come from exact model checking.
   - The scorer uses the same translation, so it would *accept* these wrong certificates and re-prove them. Fix: rename every symbol on the way into LADR (for example prefix `c_`/`p_`), and add a test that every gold label survives an independent model check.
2. **A full-size "test" fragment with gold is public.** `fragments/test_seed1/` (110 items × 4 variants, gold, *withheld* models) is committed to the public repository and is in its history. The README says the real test fragment will be a fresh seed, so this may be harmless, but it breaks the rule "only the practice fragment is public before the test window". Seed 1 must never be used as the test, and the folder should probably be renamed (for example `dev_seed1`) or removed. Removing it does not unpublish it. **Decision for organisers.**
3. **The test seed can be recovered by brute force.** The generator is public and everything it outputs is a function of an integer `--seed`: lexicon, items, released models, *hidden models* and gold. The lexicon comes from `random.Random(seed)` alone. A participant who receives the test `lexicon.txt` can run `make_lexicon(random.Random(s))` for s = 0, 1, 2, … in seconds and regenerate the whole gold, including the withheld models. The page says "the generator and its seed are published after each cycle", but the generator is already public. Mitigation (to be agreed): a secret high-entropy seed (for example 128 random bits), kept out of the repository, **and/or** a secret salt mixed into every RNG. The test-year generator could also differ from the public one in parameters (lexicon size, model sizes).

---

## 1. What exists and what actually works

Environment: Python 3.13, Ubuntu 24.04. **Prover9/Mace4 could not be installed in the audit sandbox.** apt has no `prover9` package for 24.04, the UNM download returned 403, and building a third-party source clone was not permitted here. So every run below is the no-prover path. Prover9 runs are inferred from the committed data (which was clearly generated with Prover9: it contains proofs) and from the code.

| Component | Where | Status |
|---|---|---|
| Grammar, lexicon, semantics as data | `generator/fragment.py` | Works. One fixed CFG shape (S, NP×3, RC×2, VP×3) and 12 nonce words. Semantics is a hand-written evaluator, **not** an interpreter of `semantics.txt`: the text file is a fixed string printed next to it. |
| Parser | `fragment.parse` | Works. Exhaustive recursive descent, returns all derivations; no left recursion in either word order. No tests. |
| Semantic composition | `fragment.readings` | Works for one reading per tree. Scope ambiguity is hard-coded for one configuration only (§3.5). |
| Model checker | `fragment.holds` | Works (exact evaluation over finite models). It does a linear list scan per atom, which is slow but correct. |
| Prover9 wrapper | `generator/prover.py` | Present. TPTP→Prover9 by regex; 3 s timeout in the generator, 10 s in the scorer; timeouts and errors both look like "not proved". |
| Mace4 | — | **Not used.** `MACE4` is looked up but never called. Neutral certificates come from random sampling of models of size 1–3 (`label_terms`). |
| Four variants | `gen.build_variant` | All four are written, but **they do not share items** (§2, B1). |
| Gold | `gold/gold.jsonl`, `gold/models_hidden.json` | Written for every variant; parse and interpret gold reproduces byte-for-byte from the code (checked for practice_seed0). |
| Spec-as-system submission | `gold/gold_as_submission.jsonl` | Written. Scores 100% everywhere **except** `infer/certificate`, which needs Prover9 (33.3% without it, see below). |
| Scorer | `generator/score.py` | Runs; one variant at a time; per-level table on stdout. Several gaps against the page (§2, §3). |
| Baseline | `generator/baseline.py` | `--dry-run` works. It has never been run live (README "Open"). It does not meet the brief's requirements (§2). |
| Practice fragment | `fragments/practice_seed0/` | 52 items per variant (20 parse, 20 interpret, 12 infer, labels balanced 4/4/4), generated with Prover9. |
| Tests, Makefile, requirements, install doc | — | **None.** `README.md` points to `generator/README.md`, which does not exist. |

### Runs

- `python3 gen.py --seed 0` (no prover) runs in ~90 s per four variants and is **deterministic**: two runs, and a run with a different `PYTHONHASHSEED`, are byte-identical. Without Prover9 it writes **only neutral** infer items (10 instead of 30; the cap of n/3 per label is met for neutral only, and the loop gives up after 1800 tries).
- Regenerating seed 0 with `--n-parse 20 --n-interp 20 --n-infer 12` reproduces all spec files, hidden models and parse+interpret gold of the committed practice fragment exactly. The infer section differs, because it needs Prover9.
- `score.py` on `gold_as_submission.jsonl`, all four practice variants, without Prover9: 100% on parse, interpret and infer label, and **33.3% on infer certificate**. Entailment and contradiction certificates cannot be checked without Prover9. The no-prover fallback looks for a key `enumeration_bound` that the generator never writes, so the "100% by construction" ceiling holds only on a machine with Prover9.
- Deliberately wrong system 1 (*trusts appearances* on the counter variant: LFs computed with the unswapped nonce determiners): interpret drops to 45%, and 0 of the 11 items containing a swapped determiner are accepted. Good.
- Deliberately wrong system 2 (correct LFs, **every truth value set to false**): **100%** on all interpret metrics. The submitted `truth` field is never read (§3.1).
- Malformed JSON line in a submission: the scorer crashes with a raw traceback. Empty submission: 0% everywhere (correct).

---

## 2. Missing or broken, ordered by what blocks the January release

### Blocks the release (gold or scores would be wrong or not comparable)

- [ ] **B0. Prover9 reads constants starting with u–z as variables**, which gives wrong gold labels (§0.1), including one in the released practice data.
- [ ] **B0b. Most entailment items are trivial.** In **50 of the 56** committed entailment items (practice + seed 1, all variants), the conclusion string is identical to one of the premises. The `related()` edit can leave the sentence unchanged (for example, it can "change" the determiner to the same determiner), and nothing rejects that. Practice: 4/4 (nonce), 3/4 (english), 4/4 (scrambled), 3/4 (counter) entailments are copies; overall 51 of 168 infer items (30%). The entailment label is close to "is the conclusion a premise?". Fix: reject a conclusion equal to a premise (or equivalent to one, if that is wanted). Whether some such items are useful as controls is an **organisers' question**.
- [ ] **B1. Variants do not share abstract trees.** Each variant draws its items from its own RNG, `random.Random(f"{seed}-{variant}")`, so item 1 is `gesdam zispam gigup wonbis` in nonce but `every cat that Ren sees not walks` in english. The released and hidden models also differ per variant. The page says "Every item has twins with the same abstract tree", and the headline nonce→counter drop needs paired items. Fix: generate abstract trees and models once per seed and realise them per variant. *Open question:* should the models be shared too (yes for english/scrambled; for counter the same models are still fine, because only the determiner meanings change)?
- [ ] **B2. Gold readings are not derivable from the released semantics.** `semantics.txt` gives exactly one composition rule per configuration (`[VP TV NP] = \x. NP(\y. TV(x,y))`), which yields only the surface-scope reading. Yet the gold for "every N TV some N" contains the inverse-scope reading too, built by hidden code (`_interp_S`, lines 205–210). A system that follows the specification literally fails `reading-set` on every such item. The spec needs an explicit scope mechanism (quantifier raising, Cooper storage, or a stated rule "an object NP may take wide scope over the subject"). Its exact content alters what is measured: **organisers' decision**. The code must then implement *that* rule, completely (see B3).
- [ ] **B3. Scope readings are incomplete and contain duplicates** (§3.5). Only subject-vs-object scope at the top of S is generated. Objects under `not`, quantifiers inside relative clauses, and object NPs with relative clauses are not. Duplicates up to equivalence (for example *every…every*, *some…some*) count as two readings and push the item to level 3.
- [ ] **B4. Scrambled gold trees use canonical (SVO) child order**, not the order of the released scrambled grammar. Sentence `mippos gigup zukka tamwup that zispam tamwup` has gold tree `[S [NP [Det tamwup] [N zispam] [RC that [NP …] [TV gigup]]] [VP [IV mippos]]]`, whose leaves do not spell the sentence and whose shape matches no rule of `grammar.txt` (`S -> VP NP`, `RC -> TV NP that`, …). Likewise `semantics.txt` labels its rules in SVO order (`[RC that NP TV]`). A participant who parses with the released grammar gets "wrong" trees. *Question:* should the tree for scrambled be in surface order (what the grammar says) or canonical order? Either way the page must state it, and the scorer could compare up to the variant's permutation.
- [ ] **B5. Submission format is inconsistent across documents.** `lab-materials/task_page.md` shows `{"lf": "...", "truth": {"M1": true}}` (singular, a dict); `index.html`, the baseline and the scorer use `{"lfs": [...], "truth": [{...}, ...]}`. A submission following `task_page.md` scores 0 on interpret. The `infer.lfs` shape (`{"premises": [...], "conclusion": "..."}`) and the neutral-model format appear only in code. One normative format spec plus a validator is needed.
- [ ] **B6. Interpret truth values are not scored** (§3.1). The page asks for "its truth value in each given model" and scores "truth-value agreement on every model", but the scorer evaluates the submitted LF instead and ignores `truth`.
- [ ] **B7. Infer gold uses reading [0] only** (§3.5). Ambiguous premises or conclusions are labelled under the subject-wide-scope reading, silently.
- [ ] **B8. Certificates are not really checked** (§3.3). Entailment and contradiction: the submitted proof is ignored and Prover9 is re-run on the submitted LFs. Neutral: there is no domain or signature validation, the scorer crashes on a model that omits a predicate, and a submission with fewer premises passes the LF check (`zip` truncation).
- [ ] **B9. Determinism with Prover9 is not guaranteed** (§3.8). Proof text includes `% Proof 1 at 0.00 (+ 0.00) seconds.`, and a 3 s wall-clock timeout decides which items survive, which shifts the RNG for every later item.
- [ ] **B10. No pinned LADR version and no install recipe** that works on current Linux (no Ubuntu 24.04 package; the upstream URL returns 403 from here). Participants and the scorer both depend on it.
- [ ] **B11. Phenomenon level is computed by substring search** on the tree text: `"not" in tree_str(t)`. Any nonce word containing *not* puts a level-1 sentence at level 2 (frequency in §3.8). The level of ungrammatical parse items is taken from the tree they were perturbed from. *Also:* "monotonicity" (level 2) has no item type that targets it; level 2 is simply "contains *not*".
- [ ] **B12. Scorer reporting is far from the page's table.** It handles one variant per run: no per-variant table, no nonce→counter drop, no system-type or track field, no machine-readable output. `reading-recall` is all-or-nothing per item, not a recall.
- [ ] **B13. Submission validation.** Malformed lines crash; unknown or duplicate ids pass silently (last one wins); wrong field types fall through to "wrong" without a message.

### Needed for the January package (the release is incomplete without them)

- [ ] **N1. Baseline per the brief.** It should use one OpenAI-compatible endpoint (base URL + model; the current Anthropic-SDK branch and `openai` package dependency are extra), set temperature and seed, log every prompt and raw output, retry on API errors (currently one failure aborts the run and loses the file), and resume.
  - **The few-shot design leaks or misleads.** Examples come from `practice_seed0/nonce` gold. Run on the practice fragment itself, the prompt contains gold answers to the test items. Run on `practice_seed0/counter`, the examples use the same words with *every* and *no* unswapped, so they contradict the spec in context. The examples also use a lexicon that is not in the prompt's spec. *Question:* zero-shot, or few-shot from a fragment with a disjoint lexicon?
- [ ] **N2. Sanity tables**: the spec as a system (100%), random and majority baselines, a set of deliberately wrong systems (appearance-trusting, scope-blind, negation-dropping, argument-swapping), each per variant and level.
- [ ] **N3. Tests** (pytest) for parser, composition, model checker, TPTP reader, prover wrappers and scorer; a `Makefile` (`generate`, `gold`, `score`, `baseline`, `test`); a `requirements.txt` (stdlib + pytest; an HTTP client only for the baseline).
- [ ] **N4. Participant README**: submission format, tracks, system-type declaration, how to run the scorer locally, LADR install.
- [ ] **N5. Practice package regenerated** after B1–B11 (the current one will change), with a checksum manifest.

### In the scoring text but not needed for January (flag for the timeline)

- [ ] Control fragment with an inconsistent specification ("a high score on it is reported as spec-ignoring"), from `scoring_criteria.md`: not implemented.
- [ ] Proof checker for the no-tools track: not implemented (README "Open").
- [ ] Natural-language twins beyond English ("per language"): not implemented.
- [ ] Break round checker: not implemented (April).
- [ ] Human baseline: organisational, not code.

---

## 3. Correctness risks

### 3.1 Are logical forms compared by equivalence?

No string matching, but **not by logical equivalence either**. The scorer parses the submitted formula with its own small TPTP reader and computes its **truth vector over 5 models**: the 2 released (`M1`, `M2`) and the 3 withheld (`H1`–`H3`) of that variant, with domain sizes 2 or 3. Two formulas count as "equivalent" iff they agree on those 5 models. The page's "Prover9 as a bonus" equivalence check is not implemented.

- `interpret/truth-agreement` = every submitted LF's vector is one of the gold vectors. `interpret/reading-set` = the sets of vectors are equal. `reading-recall` = all gold vectors are covered (boolean).
- The submitted `truth` field is never read: the "all false" system above scores 100%. Whether truth predictions should be scored (released models only, since the participant cannot see hidden ones), separately from LF correctness, is a measurement decision. **Question for organisers.**
- The reader has **no operator precedence**: `p => q & r` is read as `(p => q) & r`. It accepts no multi-variable binders (`! [X,Y] :`), which TPTP allows. A free variable or unknown predicate silently becomes "wrong" with no message. The gold always fully brackets its formulas, so gold parses; participants' formulas might not.

### 3.2 Can two non-equivalent LFs agree on all released and withheld models?

Yes, often. Two probes (scratchpad `probe.py`):

- **One-edit wrong LFs on the committed gold.** For every interpret item, I generated each formula one edit away from the gold reading: swap a TV's arguments, add or drop a negation, ∀↔∃ (with →↔∧), →↔∧. I kept only the edits that are really *non-equivalent* (they differ on a battery of 1500 random models of size 1–5), then asked whether they agree with gold on the variant's 5 models (2 released + 3 withheld):

  | fragment / variant | non-equivalent edits | undetected by the 5 models | items with ≥ 1 undetected wrong LF |
  |---|---|---|---|
  | practice / nonce | 123 | 16 (13%) | 9 / 20 |
  | practice / english | 190 | 21 (11%) | 8 / 20 |
  | practice / scrambled | 189 | 12 (6%) | 5 / 20 |
  | practice / counter | 156 | 12 (8%) | 7 / 20 |
  | seed 1 / nonce | 336 | 47 (14%) | 19 / 40 |
  | seed 1 / english | 359 | 28 (8%) | 10 / 40 |
  | seed 1 / scrambled | 328 | 28 (9%) | 15 / 40 |
  | seed 1 / counter | 313 | 27 (9%) | 15 / 40 |

  Roughly **1 in 10 plausible mistakes is scored as correct**, and **about 40% of interpret items accept at least one wrong LF**. The appearance-trusting system happened to be caught on all its items (§1), because swapping *every*/*no* changes truth in most models; subtler errors are not caught.

- **Random pairs.** Across 30 seeds, I took 60 random sentences per seed, with 5 models drawn from the generator's own distribution (size 2–3). Of 52,768 non-equivalent pairs of LFs, **2,596 (4.9%) have identical truth vectors on all 5 models**. With 5 models there are at most 32 truth vectors, and they are far from uniform, since many sentences are true or false in most small models.

So a sizeable share of wrong LFs is scored as correct, and the same holds for infer, where the certificate check first requires the submitted LFs to "agree" with gold on the same 5 models. Options, not decided here: (a) many more withheld models, including larger domains and models built to separate common confusions (scope, negation placement, argument order); (b) exhaustive model checking over all models up to size *k* of the item's own signature (small: an item mentions 2–4 predicates); (c) a Prover9 equivalence proof in both directions, plus Mace4 for a counter-model, with a clear rule for timeouts. (b) followed by (c) gives a decision that never depends on a timeout in the "not equivalent" direction.

### 3.3 Neutral certificates

`score.check_cert` does check that **both** submitted models satisfy all (submitted) premises and that the conclusion is true in the first and false in the second. Gaps:

- It evaluates the *submitted* LFs, which only need to agree with gold on 5 models (§3.2). The gold LFs should be used, or the submitted ones should be proved equivalent first.
- Premises are paired with `zip`: a submission giving fewer premises than gold passes the LF check (confirmed on practice item with 2 premises).
- Models are not validated: no check that the domain is non-empty, that constants denote domain elements, that every predicate is present, or that extensions are subsets of D (or D×D). A model that omits a predicate makes `holds` raise `KeyError`, **which is not caught: the scorer crashes** (confirmed). An extension or constant mentioning an element outside D is not rejected: the result is whatever the evaluator happens to compute.
- Order matters (true model first). The page says "two models … in which the conclusion differs", so either order should probably be accepted.
- Entailment and contradiction: the `proof` string is never examined. Validity means "Prover9 re-proves the submitted label from the submitted LFs within 10 s". This is a re-derivation, not a certificate check. The page and scoring text promise a proof checker; for the tools track a minimal option is to accept Prover9 proof objects and check them with LADR's own tools (`prooftrans`/`ivy` output). The no-tools track needs its own calculus. **Organisers' decision.**
- Gold neutral certificates come from **random sampling**, not Mace4. They are genuine models (checked exactly by `holds`), so they are sound, but nothing is pinned to a tool version, contrary to the page ("Prover9 and Mace4").

### 3.4 Prover9/Mace4 timeouts

- In `prover._run`, a timeout returns `""`, and so do a crash and a syntax error. All of these look like "not proved".
- **Generator**: Prover9 is tried for entailment (3 s), then for contradiction (3 s), then sampling looks for one model where the conclusion is true and one where it is false. Because model checking is exact, **a timeout by itself cannot produce a wrong label** (wrong labels do occur, but they come from the u–z variable bug of §0.1, not from timeouts): a true entailment that times out has no false-conclusion model, so the item is dropped. What timeouts do cause is (i) *selection bias* (hard entailments and contradictions vanish), (ii) machine-dependent gold (§3.8) and, (iii) with no Prover9 at all, an item set with only neutral items, and the run does not stop. A broken `_p9` translation would also go unnoticed this way. **Two caveats**: if premises are jointly inconsistent, Prover9 proves *entailment* (ex falso). None of the committed items has genuinely inconsistent premises (checked by sampling 4000 models), but nothing prevents it, and the u–z bug makes *consistent* premises look inconsistent to Prover9, which is exactly how the wrong labels arise. And sampling covers domains up to 3 only, which is fine for soundness but means some genuine neutrals are dropped.
- **Scorer**: a timeout (10 s) on a *valid* submitted entailment marks the certificate invalid. On a slow machine the scorer can therefore score a correct submission as wrong, and the spec-as-system would score below 100%.

### 3.5 Scope ambiguity: is the gold set complete and duplicate-free?

Neither. `_interp_S` adds an inverse-scope reading only when the VP is directly `TV NP` with a quantified object. It dedupes by *alpha-equivalence* (`tptp(canon(f))`), not by logical equivalence.

Probe on 6000 generated sentences (40 seeds): 667 get 2 readings, none get more. **139 of the 667 (21%) are two logically equivalent "readings"** (equivalent on 1500 random models of size 1–5), for example *every dozon geskan every dozon*, or *every N that some N geskan wufi every N*. Hand-built cases:

  | configuration | readings generated |
  |---|---|
  | every N1 TV some N2 | 2 |
  | every N1 TV every N2 (equivalent) | 2 (should be 1) |
  | every N1 TV some N2 that IV | 2 |
  | every N1 not TV some N2 (object under negation) | 1 |
  | every N1 that TV some N2 IV (quantifier inside RC) | 1 |

- **Duplicates.** *every N1 TV every N2* gets 2 "readings" that are logically equivalent, and the item is tagged level 3 because `len(rs) > 1`. The scorer collapses duplicate truth vectors, so set equality is unaffected, but the level tags and the "ambiguous" count are wrong.
- **Missing readings.** These configurations get only one reading although they are standard scope ambiguities: object under negation (*every N1 not TV some N2*, and *not* vs subject), and a quantified NP inside a relative clause or inside the object. Whether they *should* be ambiguous depends on the scope rule the organisers adopt (B2). Today the code and the published semantics disagree, whatever the answer.
- **Infer** ignores ambiguity: `readings(t)[0]` is used for every premise and the conclusion.

Committed data: ambiguous sentences occur in 1/12, 1/12, 0/12, 2/12 practice infer items (nonce, english, scrambled, counter) and in 4–5 of 30 seed-1 items per variant. All of them are silently labelled under reading [0].

### 3.6 Counter-English

- The swap is made in the lexicon, before anything else: `make_lexicon(..., counter_english=(dets[0], dets[2]))`. Parse, interpret (readings and truth) and infer (labels via Prover9/sampling, certificates) are all computed from that lexicon, and `semantics.txt` prints the swapped definitions. So **the swapped semantics does flow into gold for all three item types.** Checked: every counter interpret gold reading set equals the readings recomputed with the swapped lexicon, and the appearance-trusting system fails every item with a swapped determiner.

(Practice counter: 20 of 20 interpret gold sets equal the readings recomputed with the swapped lexicon; `gesdam` = *no*, `tamwup` = *every* in that variant.)

- But (B1) the counter items are not the nonce items, so the drop cannot be computed per item.
- **Design mismatch.** The page says "a familiar-looking word is given a contradicting meaning", but the implementation keeps *nonce* words (the README and the variant card say "Nonce words, but the determiners meaning every and no have swapped meanings"). With nonce words nothing looks familiar. A system can only go wrong by carrying over the nonce variant's meaning of the same word, and only if both variants are seen together. *Question:* should counter use English words (`every` meaning *no*), the nonce words, or both?

### 3.7 Scrambled

- It is the same grammar with each rule's right-hand side permuted (`ORDERS["scrambled"]`: S, VP→TV NP, NP→Det N, NP→Det N RC, RC→that NP TV reversed; `not VP` and `that VP` unchanged). Semantics are keyed to canonical rules, so **the logical forms are the same as for the same tree in SVO**. Gold is identical up to the tree-order issue (B4), and up to B1, because the trees are not actually the same.
- The scrambled grammar can be checked for ambiguity:

  Parsing 300 generated sentences for each of 30 seeds in each word order gave **exactly one parse every time**, so neither grammar shows structural ambiguity in practice (a proof for the bounded grammar would be a good unit test). The parser is the same function with the permuted rules, so the scrambled parse is computed by the same code.

### 3.8 Determinism

- Without Prover9: byte-identical across runs and hash seeds (checked). The RNG is seeded from strings (stable in Python 3); every set that reaches output is sorted.
- With Prover9: **not guaranteed.** (i) The gold proof text includes a timing line (`% Proof 1 at 0.00 (+ 0.00) seconds.`). (ii) The 3 s wall-clock timeout decides whether an item is kept, which also changes how much of the RNG stream is used, so every later infer item can differ on a slower machine. (iii) Output may differ between LADR versions. The fix is to strip the timing lines, use a deterministic resource limit (`assign(max_given, …)` / `max_seconds` with `-x`) rather than wall clock, pin the version, and record the LADR version in the gold.
- Level-tag substring bug (B11):

  `level()` tests `"not" in tree_str(tree)`. **10 of 200 seeds** have a lexicon word containing *not* (for example `notkas`), and in those fragments every sentence using that word is tagged level 2 even without negation (`[S [NP [PN notkas]] [VP [IV walks]]]` → level 2).

---

## 4. Design questions for the organisers (flagged, not decided)

1. **Does the 2027 test fragment differ from the practice one in grammar structure, or only in lexicon?** Today `RULES` is fixed in code and only the words, models and items vary with the seed; the scrambled permutation is fixed too. If only the lexicon changes, a system can be engineered on the practice fragment (hand-written parser, hard-coded rules), which makes the model-with-tools track a code-reuse exercise. Varying structure (rule set, argument order of TV in the RC rule, which permutation, determiner inventory) tests reading the spec but needs the generator to read `grammar.txt`/`semantics.txt` rather than print them.
2. **Partial credit for ambiguous items.** Today: set equality, plus an all-or-nothing "recall". Alternatives: precision/recall/F1 over readings modulo equivalence, reported next to set equality. This depends on Q3 (what the reading set is).
3. **What is the scope rule?** (B2). It must be stated in `semantics.txt` and decides which items are ambiguous (§3.5). Related: should ambiguous premises in *infer* be allowed at all, and if so, what is the label (entailment under all readings? per-reading labels?).
4. **Model-with-tools ceiling.** A system that writes a parser and calls Prover9 should approach 100%. Options: report tools-track results separately and never pooled with model-alone; report "steps to 100%" or cost; make the structural variation of Q1 large enough that a parser must be built from the spec at test time; add item types that a generic pipeline does not cover (the break round). How should a near-100% tools result be presented: as the expected ceiling, or as a finding?
5. **Truth values in interpret** (§3.1): score the participant's predicted truth values on released models, LF correctness on all models, or both?
6. **Equivalence check**: how many withheld models, of what size; is an exhaustive check up to size *k* or a prover-based check acceptable, and what happens on a timeout (§3.2)?
7. **Proof certificates**: is "Prover9 re-proves it from your LFs" acceptable as validity for the tools track for 2027, and what does the no-tools track submit (§3.3)?
8. **Counter variant**: nonce words or English words (§3.6)? Should models and trees be shared across all four variants (B1)?
9. **Scrambled trees**: surface order or canonical order (B4)?
10. **Inconsistent premise sets** in infer: exclude them, or label them (entailment by ex falso)?
11. **Item counts.** The practice fragment has 52 items per variant; at the per-variant × per-level × per-type grain, some cells have 1–2 items (for example practice english infer level 1: 2 items). What size is the test fragment, and do we balance levels?
12. **`test_seed1` and the seed policy** (§0.2, §0.3).
14. **Trivial items** (B0b): drop infer items whose conclusion is a premise, or keep a few as controls?
13. **Control fragment** with an inconsistent spec (scoring text): in 2027 or not?

---

## 5. Proposed Phase 2 order (for approval)

Each item is one PR on its own branch off `main`, with tests:

1. **Seed hygiene**: decide on `test_seed1` (§0.2), document the secret-seed / salt policy (§0.3), add a `.gitignore` guard for non-practice fragments.
2. **LADR**: symbol renaming on the way into Prover9/Mace4 (B0) with a regression test on practice item 47; pinned version and install script/doc; deterministic wrappers (`max_given` / `-x` limits, timing lines stripped), timeouts reported explicitly (`proved` / `disproved` / `unknown`), Mace4 for neutral models with an exact re-check; pytest for both.
3. **Gold pipeline**: an independent model-check of every gold label; no conclusion equal to a premise (B0b, pending your answer); shared abstract trees and models across variants (B1); exact level tagging (B11); the scope rule once decided (B2/B3) with dedupe up to equivalence; infer ambiguity policy (B7); scrambled tree convention (B4). Tests for parser, composition and model checker, including fixed known-answer items. Determinism test (two runs, byte-identical).
4. **Scorer**: format spec + validator with clear messages (B5, B13); an equivalence check per the decision in §4.6; certificate validation (B8); truth-value scoring per §4.5; per-variant × per-level × per-type tables, nonce→counter drop, JSON output (B12).
5. **Sanity tables**: spec-as-system, random, majority, wrong systems.
6. **Baseline**: OpenAI-compatible, logged, fixed temperature/seed, few-shot policy per the answer to N1.
7. **Release package**: regenerated practice fragment, README for participants, Makefile.

Items 3 and 4 contain choices that change what is measured; those PRs will implement only the options you approve, and they will list each open choice in the PR description.
