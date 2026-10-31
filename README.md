# Fragments: learning a language from its specification

A shared task of the ELOQUENT lab, CLEF 2027. Task page: https://stergioscha.github.io/fragments-task/

Working repository for the task (the synthetic-fragment half of the lab's No Data Task), CLEF 2027, Bucharest, 14–17 September 2027.

The idea in one paragraph: each year we release a new *fragment* of a language in Montague's
sense — a small grammar, a lexicon of invented words, compositional rules mapping sentences to
first-order logic, and a few small models. Systems must parse sentences of the fragment, give their
logical forms, and decide entailments. Because the fragment is new, it cannot be in any training
data; because every gold answer is computed from the specification, every submission is checked by
a parser, a model checker or a theorem prover. The question the task answers is whether a model
follows a specification it has been given or falls back on what it already knows.

## What is here

| Folder | Contents |
|---|---|
| `proposal/` | The task proposal in the CLEF lab-proposal format (`fragments_eloquent.pdf`, LaTeX source and bibliography) |
| `lab-materials/` | `task_page.md`, the draft task page for the ELOQUENT site; `scoring_criteria.md`, the scoring text for the lab's shared document |
| `generator/` | The code: fragment generator, scorer and prompting baseline (Python 3, Prover9/Mace4) |
| `fragments/practice_seed0/` | A small practice fragment with full gold answers, in all four variants |
| `fragments/test_seed1/` | A full-size fragment, also with gold, to exercise the pipeline. The real test fragment will be a fresh seed released only in the test window |

Participants: start with [docs/PARTICIPANTS.md](docs/PARTICIPANTS.md) (what you get, what you send, how it is scored).
Organisers: [docs/SEEDS.md](docs/SEEDS.md) says what may be public; `make release-practice` rebuilds the practice package.

## The fragment package

Participants receive four plain-text files. This is the whole specification; a linguist reads it in ten minutes.

```
lexicon.txt    PN: fukas, vossop   N: dozon, raske, ziba   IV: zopmap, vospem   TV: geskan, wufi   Det: tinpet, kuswun, rasgon
grammar.txt    S -> NP VP     NP -> Det N | PN | Det N RC     RC -> that VP | that NP TV     VP -> IV | TV NP | not VP
semantics.txt  [S NP VP] = NP(VP)     [VP TV NP] = \x. NP(\y. TV(x,y))     tinpet = \P.\Q. forall x (P(x) -> Q(x))   ...
models.json    M1: D = {a,b,c}, dozon = {a,b}, geskan = {(a,c),(b,c)}, fukas = a, ...
```

Three kinds of test item, one JSON object per line, one JSON answer per line:

- **parse** — is the string in the fragment, and what is its derivation tree?
- **interpret** — the logical form in TPTP first-order syntax, and its truth value in each model. Any formula equivalent to the gold counts.
- **infer** — entailment, contradiction or neutral, with a certificate: the logical forms plus a proof, or for neutral items two models of the premises in which the conclusion differs.

Every fragment comes in four variants with the same abstract sentences: **nonce** (invented words),
**english** (the same trees with English words), **scrambled** (the same rules, inverted word order), and
**counter** (nonce words, but the determiners meaning *every* and *no* have swapped meanings, so a
system that trusts how the words look will visibly go wrong). Consistency across variants is what we measure.

## Running the code

Requirements: Python 3.10+ and Prover9/Mace4, version LADR 2009-11A: `make ladr` builds it into `./.ladr`
(see [docs/LADR.md](docs/LADR.md)). The generator refuses to compute gold without it; `--without-ladr` is for
development only (it produces neutral inference items only). `make test` runs the tests.

Generate a fragment:

```
make generate SEED=7 OUT=out/seed7       # or: cd generator && python3 gen.py --seed 7 --out ../out/seed7
make check-gold OUT=out/seed7            # independent re-check of every gold answer
```

Each item is built once as an abstract tree and written out in all four variants with the same id, so item *n*
of `nonce`, `english`, `scrambled` and `counter` are twins; the variants also share the released and withheld models.

Score a submission. A submission is a directory with one JSON-lines file per variant and a `submission.json`
declaring track and system type; the format, with examples, is in [docs/SUBMISSION.md](docs/SUBMISSION.md).
`validate.py` checks a file first and explains every problem by line number:

```
make score FRAGMENT=fragments/practice_seed0 SUBMISSION=my_submission JSON=results.json
cd generator && python3 validate.py --variant ../fragments/practice_seed0/nonce --submission ../my_submission/nonce.jsonl
```

The scorer prints, for every variant, each metric of the scoring table per phenomenon level, and the nonce → counter
drop. `gold/gold_as_submission.jsonl` in each variant is the specification itself scored as a system; it must give 100%.

Run the prompting baseline: the four specification files in the context, one request per item, zero-shot, at
temperature 0 and seed 0. It works with any OpenAI-compatible endpoint, hosted or local (vLLM, llama.cpp, Ollama, …),
needs nothing beyond the Python standard library, logs every prompt and raw reply, and resumes if interrupted.
`--dry-run` prints the prompt without calling anything:

```
export FRAGMENTS_BASE_URL=http://localhost:8000/v1 FRAGMENTS_MODEL=my-model   # FRAGMENTS_API_KEY if needed
make baseline FRAGMENT=fragments/practice_seed0 RUN=runs/my-model
make score FRAGMENT=fragments/practice_seed0 SUBMISSION=runs/my-model
```

## Scoring in brief

| Item | Checked by | Metric |
|---|---|---|
| parse | the organisers' parser | grammaticality accuracy; derivation match |
| interpret | model checker on the released models and on models we withhold; Prover9 as a bonus | truth-value agreement on every model; set equality of readings for ambiguous sentences |
| infer | Prover9 and Mace4 on the submitted formulas | label accuracy and certificate validity, reported separately |

Everything is reported per variant and per phenomenon level (this year: quantification; negation and
monotonicity; relative clauses and scope ambiguity). Results are reported by declared system type,
not on one leaderboard.

## Status and timeline

Done: proposal, task page draft, scoring text, generator, scorer, baseline, practice and test fragments.
Open: publishing the task page on the lab site; a live run of the baseline; natural-language twins beyond
English (Grammatical Framework would give these cheaply); a proof checker for the no-tools track if that
track runs in year one.

| | |
|---|---|
| January 2027 | practice fragment, scoring scripts and baseline released |
| April 2027 | test fragment released, two-week submission window |
| May 2027 | scores returned, experiment reports due |
| September 2027 | CLEF 2027, Bucharest |

## People

No Data Task team: Maria Barrett, Stergios Chatzikyriakidis, Jussi Karlgren, Bruno Nadalic Sotic, Aarne Talman.

ELOQUENT 2027 lab organisers: Maria Barrett, Sarah Bouaraba, Stergios Chatzikyriakidis, Diandra Fabre, Federica Gamba, Lorraine Goeuriot, Rohit Raj Gunti, Jindřich Helcl, Jussi Karlgren, Jindřich Libovický, Josiane Mothe, Philippe Mulhem, Bruno Nadalic Sotic, Lucie Poláková, Yves Scherrer, Didier Schwab, Pavel Šindelář, Aarne Talman, Markarit Vartampetian, Erik Velldal, Eline Visser, Lilja Øvrelid.
The inference pipeline grew out of NESTOR, a project of the computational-semantics seminar in Athens.

MIT licence.
