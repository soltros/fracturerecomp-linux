#!/bin/sh
# Run against the extracted install, exactly as RecompLauncher does.
set -eu
install=$1
case "$install" in /tmp/*) ;; *) exit 2 ;; esac
unset APPIMAGE
export APPDIR="$install" ARGV0="$install/AppRun" RECOMPLAUNCHER=1
export RECOMPLAUNCHER_DATA="$install/recompdata"
mkdir -p "$RECOMPLAUNCHER_DATA" "$install/.recomplauncher-tmp" /tmp/invalid-fracture/resources
export TMPDIR="$install/.recomplauncher-tmp"
printf 'not a supported xex\n' > /tmp/invalid-fracture/default.xex
if "$install/AppRun" --prepare --game=/tmp/invalid-fracture --data "$RECOMPLAUNCHER_DATA" > /tmp/setup-output 2>&1; then
    echo 'Invalid game unexpectedly accepted' >&2
    exit 1
fi
grep -q '^progress 0.000 ' /tmp/setup-output
test -f "$RECOMPLAUNCHER_DATA/logs/prepare.log"
test ! -f "$RECOMPLAUNCHER_DATA/prepared.json"
# Synthetic completed build: no real game assets or skipped input validation.
mkdir -p "$RECOMPLAUNCHER_DATA/cache/fixture" "$RECOMPLAUNCHER_DATA/game"
cp "$FRACTURE_BUILDER_DATA/toolchain-smoke/native-game" "$RECOMPLAUNCHER_DATA/cache/fixture/fracture"
export FRACTURE_SMOKE_LOG="$RECOMPLAUNCHER_DATA/logs/portable-launch.log"
export FRACTURE_SMOKE_GAME="$RECOMPLAUNCHER_DATA/game"
chmod +x "$RECOMPLAUNCHER_DATA/cache/fixture/fracture"
printf '{"binary":"/work/cache/fixture/fracture","game":"/work/game"}\n' > "$RECOMPLAUNCHER_DATA/last-build.json"
printf '{}\n' > "$RECOMPLAUNCHER_DATA/prepared.json"
ln -s cache/fixture "$RECOMPLAUNCHER_DATA/game-build"
printf 'fullscreen = false\n# Preserved setting\n' > "$RECOMPLAUNCHER_DATA/settings.toml"
"$install/AppRun" --play --data "$RECOMPLAUNCHER_DATA"
grep -q 'native game launched' "$RECOMPLAUNCHER_DATA/logs/portable-launch.log"
test ! -d "$RECOMPLAUNCHER_DATA/runtime"
test ! -f "$RECOMPLAUNCHER_DATA/launch-fracture"
grep -q '# Preserved setting' "$RECOMPLAUNCHER_DATA/settings.toml"
# Moving the entire install must preserve the data and all stored game paths.
mv "$install" /tmp/fracture-recomplauncher-moved
install=/tmp/fracture-recomplauncher-moved
export APPDIR="$install" ARGV0="$install/AppRun" RECOMPLAUNCHER_DATA="$install/recompdata"
export TMPDIR="$install/.recomplauncher-tmp"
export FRACTURE_SMOKE_LOG="$RECOMPLAUNCHER_DATA/logs/portable-launch.log"
export FRACTURE_SMOKE_GAME="$RECOMPLAUNCHER_DATA/game"
"$install/AppRun" --play
grep -q 'native game launched' "$RECOMPLAUNCHER_DATA/logs/portable-launch.log"
echo 'RecompLauncher extracted-install setup, launch, and relocation checks passed'
