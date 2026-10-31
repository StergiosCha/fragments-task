# Prover9 and Mace4 (LADR)

All gold labels and certificate checks use **LADR 2009-11A**, the final release of Prover9 and Mace4 by William McCune. The code checks the version on every run and refuses any other version, unless you set `FRAGMENTS_ALLOW_ANY_LADR=1` for experiments. The point is that the same fragment gives the same gold on every machine.

## Install

```
scripts/install_ladr.sh            # builds into ./.ladr (needs git, cmake and a C compiler)
export PATH="$PWD/.ladr/bin:$PATH"
```

The script builds a fixed commit (`8317cb2`) of the maintained mirror at https://github.com/laitep/ladr. That commit is release 2009-11A with a CMake build added, which compiles with current compilers. The script ends by checking that both programs report version 2009-11A.

You can also point to binaries you built yourself with `PROVER9=/path/to/prover9` and `MACE4=/path/to/mace4`.

Package managers: Homebrew's `prover9` formula is also 2009-11A. Ubuntu 24.04 no longer ships a package, and the original download page at unm.edu is not always reachable.

## How the code uses LADR

`generator/prover.py` is the only module that calls the programs.

- **Renaming.** Before anything goes to LADR, constants are written `c_<name>`, predicates `p_<name>` and bound variables `x1, x2, …`. Prover9 treats any free name beginning with *u*–*z* as a variable. Without the renaming, the proper name `wonbis` in `wutbu(wonbis)` would be read as "everything" (this bug produced wrong gold in the first practice release).
- **Deterministic limits.**
  - Prover9 stops after `max_given = 2000` given clauses.
  - Mace4 searches domains of size 1 to 4.
  - There is no time limit in the search itself. A 120-second wall-clock limit exists only as a safety net, and hitting it is an error, not a result.
- **Explicit outcomes.**
  - `prove()` returns `proved`, `not_proved` (the search space is exhausted) or `unknown` (the limit was reached).
  - `find_model()` returns a model or nothing.
  - Errors from LADR raise an exception instead of being read as "no proof".
- **Cross-checks.**
  - Every Mace4 model is re-evaluated by our own model checker.
  - A proof of the conclusion together with a model of premises + ¬conclusion (or the reverse) raises an error.
  - Disagreements like these are how a translation bug would show up.
- **Labels** (`label_terms`):

  | label | condition |
  |---|---|
  | entailment | the conclusion is proved, *and* there is a model of premises + conclusion (so the premises are consistent) |
  | contradiction | ¬conclusion is proved, *and* there is a model of premises + ¬conclusion |
  | neutral | Mace4 finds a model of premises + conclusion and a model of premises + ¬conclusion |
  | inconsistent | both are proved; the generator skips such items, because the task does not define their label (organisers' question) |
  | undecided | anything else; the item is skipped |

- **Proof text** is stored without Prover9's comment lines, which contain timings, so gold files are byte-identical across runs.

## Running the tests

`pytest` runs everything. The tests that need the real programs are skipped when LADR is not installed, and they run in CI (`.github/workflows/tests.yml`), which builds LADR with the script above.
