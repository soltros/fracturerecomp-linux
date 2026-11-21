#!/bin/sh
# CI-only round trip: install a Games entry, then run its managed AppImage.
set -eu
entry=$1
image=$2
case "$FRACTURE_BUILDER_DATA" in /tmp/fracture-*) ;; *) exit 2 ;; esac
mkdir -p "$FRACTURE_BUILDER_DATA/menu-fixture/game"
cat > "$FRACTURE_BUILDER_DATA/menu-fixture/fracture" <<'GAME'
#!/bin/sh
printf 'game launched\n' > /work/menu-launch-ok
GAME
chmod +x "$FRACTURE_BUILDER_DATA/menu-fixture/fracture"
printf '{"binary":"/work/menu-fixture/fracture","game":"/work/menu-fixture/game"}\n' \
    > "$FRACTURE_BUILDER_DATA/last-build.json"
# Simulate normal AppImage invocation, exposing the actual image for the
# durable runtime copy even though CI initially extracted it without FUSE.
APPIMAGE="$image" "$entry" --install-shortcut
test -f "$XDG_DATA_HOME/applications/io.github.soltros.FractureRecomp.desktop"
test -s "$FRACTURE_BUILDER_DATA/runtime/FractureBuilder.AppImage"
# The desktop entry's shell wrapper must enter --play and run the game,
# without displaying the builder. Exercise the real image without FUSE.
APPIMAGE_EXTRACT_AND_RUN=1 /bin/sh "$FRACTURE_BUILDER_DATA/launch-fracture"
test "$(cat "$FRACTURE_BUILDER_DATA/menu-launch-ok")" = 'game launched'
echo 'Games menu shortcut launched the game successfully'
