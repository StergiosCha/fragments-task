---
layout: default
title: No Data Task — Fragments
---

# No Data Task: can a language model learn a language from its specification alone?

*Part of the [ELOQUENT lab](https://eloquent-lab.github.io/) at CLEF 2027. This page describes the synthetic-fragment part of the task; the field-grammar part is described [here](#field-grammar-part).*

A model in practical use is often handed rules it has never seen: a style guide, a domain ontology, an in-house format. We want to know whether it can follow such a specification instead of falling back on what it knows from training. To test this we release a new **fragment** of a language each year, in the sense of Montague: a small grammar, a lexicon of invented words, compositional rules mapping sentences to first-order logic, and a few small models. Because the fragment is new, it cannot be in any training set; because every gold answer is computed from the specification, every submission is checked by a parser, a model checker or a prover. No annotation, no string matching.

Everyone is welcome: a submission can be as small as running one prompted model over the items, and we ship a baseline that does exactly that.

## What you get

Four plain-text files. A linguist reads them in ten minutes.

```
lexicon.txt    PN: Tam, Ren   N: blicket, wug   IV: daxes   TV: fepps   Det: kro, sib, nul
grammar.txt    S -> NP VP     NP -> Det N | PN     VP -> IV | TV NP
semantics.txt  [S NP VP] = NP(VP)   [NP Det N] = Det(N)   [VP TV NP] = \x. NP(\y. TV(x,y))
               kro = \P.\Q. forall x (P(x) -> Q(x))   sib = \P.\Q. exists x (P(x) & Q(x))   ...
models.json    M1: D={a,b,c} blicket={a,b} wug={c} daxes={a} fepps={(a,c),(b,c)} tam=a ren=c
```

plus a file of test items, one JSON object per line. A **practice fragment** with full gold answers, the scoring scripts and the baseline are released first so you can test your pipeline end to end.

## What you return

One JSON line per item.

- **parse** — is the string in the fragment, and what is its derivation?
  `{"id": 17, "grammatical": true, "tree": "[S [NP [Det kro] [N blicket]] [VP [TV fepps] [NP [Det sib] [N wug]]]]"}`
- **interpret** — the logical form in TPTP first-order syntax, and its truth value in each given model. Any formula equivalent to the gold counts.
  `{"id": 42, "lf": "! [X] : (blicket(X) => ? [Y] : (wug(Y) & fepps(X,Y)))", "truth": {"M1": true, "M2": false}}`
- **infer** — entailment, contradiction or neutral, with a certificate: the logical forms of all sentences plus a proof, or for neutral items two models of the premises in which the conclusion differs.
  `{"id": 88, "label": "entailment", "lfs": {...}, "certificate": {...}}`

Every item also appears as a natural-language twin in several languages, with scrambled word order, and as a **counter-English** twin in which a familiar-looking word is given a contradicting meaning. Consistency across these is what we measure.

## Tracks and system types

Declare one track, **model alone** or **model with tools** (a prover, or code the model writes), and a system type: prompted model, prover loop, program synthesis, neuro-symbolic, fine-tuned. Results are reported per type, not on one leaderboard. This is not a competition: several submissions per team and negative results are welcome, and the short experiment report that accompanies each submission is where the interesting findings go.

## Evaluation

Automatic throughout: parse against the organisers' parser; interpret by truth on the released models and on models we withhold; infer by provers and a proof checker, with label accuracy and certificate validity reported separately. Scores are broken down by variant, by phenomenon level (this year: quantification; negation and monotonicity; relative clauses and scope ambiguity) and by system type. Details: [scoring criteria](scoring).

## Break round (optional)

Submit new items with gold answers. Items that pass our checker are run against all other systems, builder/breaker style as in Voight-Kampff.

## Timeline

| | |
|---|---|
| January 2027 | practice fragment, scoring scripts, baseline |
| April 2027 | test fragment released; two-week submission window; break submissions |
| May 2027 | scores returned; experiment reports due |
| 14–17 September 2027 | CLEF 2027, Bucharest: results |

## Field-grammar part

The second part of the No Data Task asks the same question of a real language with no digital resources: given only a grammar and a lexicon prepared by field linguists, generate a set of specified utterances. These are scored by a language expert on an acceptability scale. That half has its own organisers; details will be added by them.

## Organisers and contact

Stergios Chatzikyriakidis (University of Crete) · Aarne Talman (University of Helsinki) · [further organisers] · contact: eloquent-clef2027-organizers AT googlegroups.com
