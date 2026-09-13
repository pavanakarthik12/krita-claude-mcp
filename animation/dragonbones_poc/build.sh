#!/usr/bin/env bash
# build.sh - builds POC #2's renderer.
#
# Compiles the SAME unmodified DragonBones C++ core used by the proven
# DragonBonesCPP/poc (referenced by absolute path, not copied - nothing
# under DragonBonesCPP/ is written to), plus this directory's own
# src/main.cpp and src/PocRuntime.h (a verbatim copy of the already-proven
# glue code from that POC - our own file, not DragonBones source).
set -eo pipefail

cd "$(dirname "$0")"

DBCPP="/c/Users/pavan/OneDrive/Desktop/DragonBonesCPP"

export TMPDIR="${TMPDIR:-${TEMP:-${TMP:-/tmp}}}"
export TMP="${TMP:-${TMPDIR}}"
export TEMP="${TEMP:-${TMPDIR}}"

CXXFLAGS="-std=c++17 -O2 -Wall -fpermissive -I $DBCPP/DragonBones/src -I $DBCPP/3rdParty -I src $(pkg-config --cflags sfml-graphics sfml-window sfml-system)"
LDFLAGS="$(pkg-config --libs sfml-graphics sfml-window sfml-system)"

mkdir -p build/obj

OBJS=()
for f in $(find "$DBCPP/DragonBones/src" -name '*.cpp') src/main.cpp; do
  base=$(echo "$f" | sed 's#[./:]#_#g')
  obj="build/obj/${base}.o"
  OBJS+=("$obj")
  if [ ! -f "$obj" ] || [ "$f" -nt "$obj" ]; then
    echo "Compiling $f"
    g++ -c "$f" -o "$obj" $CXXFLAGS
  fi
done

echo "Linking dragonbones_poc2.exe"
g++ "${OBJS[@]}" -o dragonbones_poc2.exe $LDFLAGS
echo "Build OK -> dragonbones_poc2.exe"
