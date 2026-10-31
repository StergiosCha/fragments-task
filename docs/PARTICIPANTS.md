# Fragments 2027: guide for participants

*Draft for the January 2027 practice release. Points still to be settled by the organisers are marked **(open)**.*

Fragments asks whether a system can learn a language from its specification alone. Each year we publish a new
**fragment**: a small grammar, a lexicon of invented words, rules that map sentences to first-order logic, and a
few small models. Your system parses sentences of the fragment, gives their logical forms, and decides
entailments. Every answer is checked automatically by a parser, a model checker or a theorem prover. No answer is
annotated by hand. The task page is https://stergioscha.github.io/fragments-task/.

## What you get

For each of the four **variants** of a fragment, a folder with:

| file | contents |
|---|---|
| `lexicon.txt` | the words, by category (PN proper name, N noun, IV intransitive verb, TV transitive verb, Det determiner) |
| `grammar.txt` | the context-free grammar |
| `semantics.txt` | the meaning of every rule and every word, in lambda notation |
| `models.json` | small finite models (`M1`, `M2`, …): a domain `D` and the extension of every word |
| `items.jsonl` | the test items, one JSON object per line |

The practice fragment (`fragments/practice_seed0/`) also includes `gold/`: the gold answers, the models we
withhold, and `gold_as_submission.jsonl`, which is the specification itself written as a submission. The test
fragment, released in April 2027, comes without `gold/`.

### The four variants

All four contain **the same items, with the same ids**: item 17 is one abstract sentence, realised four ways.

| variant | what changes |
|---|---|
| `nonce` | invented words; the default |
| `english` | the same sentences with English words |
| `scrambled` | the same rules with their parts in a different order, so the word order is unnatural |
| `counter` | the nonce words, but the determiners that mean *every* and *no* in `nonce` swap meanings |

All four use the same models. The difference between your `nonce` and `counter` scores is the headline
number: a system that follows the specification loses nothing, while one that relies on what the words
seem to mean does. **(open: the counter variant may use English words instead.)**

### The three item types

```json
{"id": 1, "type": "parse", "sentence": "gesdam zispam gigup wonbis"}
{"id": 21, "type": "interpret", "sentence": "zusdit petfat not mippos"}
{"id": 41, "type": "infer", "premises": ["wonbis wutbu"], "conclusion": "zusdit zukka gigup wonbis"}
```

- **parse**: is the string a sentence of the fragment, and what is its derivation tree?
- **interpret**: the logical form of every reading of the sentence, and its truth value in each released model.
- **infer**: do the premises entail the conclusion, contradict it, or neither? Give the logical forms and a
  certificate: a proof, or, for *neutral*, two models of the premises that disagree on the conclusion.

Each item has a phenomenon level, and scores are reported per level:
1. quantification (*every*, *some*, *no*);
2. negation;
3. relative clauses and scope ambiguity.

## What you send

A directory with one JSON-lines file per variant and a `submission.json`. The full format, with examples, is in
[SUBMISSION.md](SUBMISSION.md). Check every file before you send it:

```
cd generator
python3 validate.py --variant ../fragments/practice_seed0/nonce --submission ../my_submission/nonce.jsonl
```

The validator lists every problem with its line number. It needs only Python 3.10 or later.

## Tracks and system types

Declare one **track** in `submission.json`:

| track | meaning |
|---|---|
| `model-alone` | the model's own outputs, from the specification in its context |
| `model-with-tools` | the model with a prover, or with code it writes itself |

and one **system type**: `prompted-model`, `prover-loop`, `program-synthesis`, `neuro-symbolic` or `fine-tuned`.
Results are reported per track and system type, not on one leaderboard. Several submissions per team are
welcome, and so are negative results. Each submission comes with a short experiment report.

**(open: how results of the model-with-tools track are presented, given that a parser plus a prover can in principle reach 100%.)**

## How you are scored

| item | checked by | metrics |
|---|---|---|
| parse | the organisers' parser | grammaticality accuracy; derivation match |
| interpret | the model checker, on the released models and on models we withhold | every formula agrees with a gold reading on every model; the set of readings equals the gold set |
| infer | Prover9 and Mace4 on your formulas | label accuracy; certificate validity (reported separately) |

Two formulas count as the same reading if they are equivalent; you do not need to match the gold's wording.
At present equivalence is tested on the released and withheld models **(open: a stronger check)**.

Score the practice fragment yourself:

```
make ladr                 # once: builds Prover9/Mace4 2009-11A (docs/LADR.md); needed for proof certificates
export PATH="$PWD/.ladr/bin:$PATH"
make score FRAGMENT=fragments/practice_seed0 SUBMISSION=my_submission
```

## A baseline to start from

`generator/baseline.py` gives a model the specification and asks for one item per request. It works with any
OpenAI-compatible endpoint, hosted or local:

```
export FRAGMENTS_BASE_URL=http://localhost:8000/v1 FRAGMENTS_MODEL=my-model
make baseline FRAGMENT=fragments/practice_seed0 RUN=runs/my-model
```

## Rules

- Do not use the practice gold or the withheld practice models to tune on the test fragment's items. They are
  given so that you can test your pipeline.
- Do not try to recover the test fragment's seed or gold; the generator is public so that everyone can check
  our gold after the test window.

## Timeline

| | |
|---|---|
| January 2027 | practice fragment, scoring scripts and baseline released |
| April 2027 | test fragment released; two-week submission window; break submissions |
| May 2027 | scores returned; experiment reports due |
| 14–17 September 2027 | CLEF 2027, Bucharest |

Contact: eloquent-clef2027-organizers@googlegroups.com
