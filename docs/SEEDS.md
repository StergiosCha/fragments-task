# Seeds and what may be public

Everything in a fragment is a function of its seed: the lexicon, the items, the released models, the
**withheld models** and the gold. The generator is public. So whoever knows a seed knows the gold.

## Rules

1. **Only practice fragments are committed.** `tests/test_release.py` fails if `fragments/` contains anything
   else, and `.gitignore` ignores every other folder there. Generate test fragments outside the repository.
2. **The test seed is a secret, high-entropy number.** A small seed can be found by trying seeds until the
   generated `lexicon.txt` matches the released one, which takes seconds. Draw it with
   ```
   python3 -c "import secrets; print(secrets.randbits(128))"
   ```
   and keep it outside the repository (for example in the organisers' password manager, held by two people).
   `gen.py --seed` accepts integers of any size.
3. **After the test window**, the seed and the generator version are published (task page), so that anyone can
   regenerate and check the gold.

## Open questions for the organisers

- `fragments/test_seed1/` is a full-size fragment with gold and withheld models. It has been public since the
  first commit. It must never be used as the test fragment. Should it be renamed (for example `dev_seed1`),
  kept as a public development set, or removed? Removing it does not unpublish it.
  `tests/test_release.py` allows it, by name, until this is decided.
- Is a secret salt in addition to the seed wanted (protection against a leaked seed), or is a secret 128-bit
  seed enough?
