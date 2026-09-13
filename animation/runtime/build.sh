#!/usr/bin/env bash
# build.sh - builds the DragonBones adapter/renderer for the real animation
# runtime layer, against the same unmodified DragonBones C++ core used by
# every POC (referenced by absolute path, nothing under DragonBonesCPP/ is
# written to). Reuses animation/dragonbones_poc4's already-generated
# character_ske.json/parts_manifest.json/parts/ at run time (see main.cpp),
# not at build time.
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

echo "Linking runtime_adapter.exe"
g++ "${OBJS[@]}" -o runtime_adapter.exe $LDFLAGS
echo "Build OK -> runtime_adapter.exe"
