#!/usr/bin/env bash
# Build and install the pinned Prover9/Mace4 (LADR 2009-11A) used for all gold and scoring.
#
#   scripts/install_ladr.sh [DEST]        (default DEST: ./.ladr)
#
# Then put DEST/bin on your PATH, or set PROVER9=DEST/bin/prover9 and MACE4=DEST/bin/mace4.
# Needs: git, cmake, a C compiler. See docs/LADR.md.
set -euo pipefail

LADR_REPO="https://github.com/laitep/ladr.git"
LADR_COMMIT="8317cb2dea069cd57723f76bdee7d6bd818103a7"   # LADR 2009-11A + CMake build, 30 Nov 2023
LADR_VERSION="2009-11A"

DEST="$(mkdir -p "${1:-.ladr}" && cd "${1:-.ladr}" && pwd)"
SRC="$DEST/src"

if [ ! -d "$SRC/.git" ]; then
  git clone --quiet "$LADR_REPO" "$SRC"
fi
git -C "$SRC" fetch --quiet origin
git -C "$SRC" checkout --quiet "$LADR_COMMIT"

cmake -S "$SRC" -B "$SRC/build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$DEST" > "$DEST/build.log"
cmake --build "$SRC/build" --parallel >> "$DEST/build.log"
cmake --install "$SRC/build" >> "$DEST/build.log"

for prog in prover9 mace4; do
  out="$(printf 'formulas(assumptions).\nend_of_list.\n' | "$DEST/bin/$prog" 2>&1 || true)"
  if ! grep -q "version $LADR_VERSION," <<<"$out"; then
    echo "error: $DEST/bin/$prog does not report version $LADR_VERSION" >&2
    exit 1
  fi
done
echo "LADR $LADR_VERSION installed in $DEST/bin"
