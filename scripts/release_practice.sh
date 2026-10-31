#!/usr/bin/env bash
# Regenerate the public practice fragment, check it, and write its checksums.
#
#   scripts/release_practice.sh [OUT]            (default OUT: fragments/practice_seed0)
#
# Needs the pinned LADR on PATH (make ladr). Stops at the first problem.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-fragments/practice_seed0}"
SEED=0                                  # the practice seed is public; test seeds never appear here (docs/SEEDS.md)
SIZES="--n-parse 20 --n-interp 20 --n-infer 12"

command -v prover9 >/dev/null && command -v mace4 >/dev/null || { echo "LADR not on PATH (make ladr)" >&2; exit 1; }

rm -rf "$OUT.new"
(cd generator && python3 gen.py --seed "$SEED" --out "../$OUT.new" $SIZES)
(cd generator && python3 check_gold.py "../$OUT.new"/{nonce,english,scrambled,counter})
(cd generator && python3 sanity.py --fragment "../$OUT.new" --out "../sanity" --markdown "../$OUT.new/SANITY.md" > /dev/null)
[ "$(grep -c '^| specification | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |$' "$OUT.new/SANITY.md")" = 4 ] \
  || { echo "the specification does not score 100% on every variant (see $OUT.new/SANITY.md)" >&2; exit 1; }
(cd "$OUT.new" && find . -type f ! -name MANIFEST.sha256 | LC_ALL=C sort | xargs sha256sum > MANIFEST.sha256)

rm -rf "$OUT"
mv "$OUT.new" "$OUT"
echo "practice fragment written to $OUT (checksums in $OUT/MANIFEST.sha256, sanity tables in $OUT/SANITY.md)"
