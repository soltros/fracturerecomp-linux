#!/usr/bin/env bash
# Maintainer command. Builds the SDK once, then packages an offline builder.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for tool in docker python3 tar sha256sum curl; do
  command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done
docker info >/dev/null || { echo 'A working Docker daemon is required to package the AppImage.' >&2; exit 1; }
output="$ROOT/out/appimage"
mkdir -p "$output"
# Include local implementation changes in the build ID, not only git HEAD.
source_id="$(python3 packaging/appimage/source_id.py)"
image="fracture-builder:$source_id"
if [[ "${FRACTURE_USE_PREBUILT_IMAGE:-0}" == 1 ]]; then
  docker image inspect "$image" >/dev/null
else
  docker build --build-arg "BUILD_JOBS=${BUILD_JOBS:-2}" --build-arg "SOURCE_ID=$source_id" \
    -f packaging/appimage/Dockerfile -t "$image" .
fi
stage="$(mktemp -d "$output/stage.XXXXXXXX")"
container="$(docker create "$image")"
cleanup() { docker rm "$container" >/dev/null 2>&1 || true; rm -rf -- "$stage"; }
trap cleanup EXIT
appdir="$stage/FractureBuilder.AppDir"
mkdir -p "$appdir/rootfs" "$appdir/bootstrap/lib"
docker export "$container" | tar --extract --no-same-owner -C "$appdir/rootfs"
rm -f "$appdir/rootfs/.dockerenv"
cp packaging/appimage/AppRun packaging/appimage/fracture-builder.desktop \
  packaging/appimage/fracture-builder.png "$appdir/"
ln -s fracture-builder.png "$appdir/.DirIcon"
# Docker's system directories and SDK sources can retain root-only modes.
# The mounted AppImage must be readable by an ordinary desktop account.
chmod -R a+rX "$appdir/rootfs"
cp "$appdir/rootfs/usr/bin/busybox" "$appdir/bootstrap/busybox"
cp "$appdir/rootfs/usr/bin/proot" "$appdir/bootstrap/proot"
# Resolve the bootstrap dependencies inside the matching build container.
docker run --rm "$image" /bin/sh -c 'ldd /usr/bin/proot' > "$stage/ldd.txt"
python3 packaging/appimage/bootstrap_libs.py "$appdir" "$stage/ldd.txt"
chmod +x "$appdir/AppRun"
FRACTURE_BUILDER_DATA="$stage/smoke-state" "$appdir/AppRun" --self-test
# Pin the packaging tool by digest, even though its download tag is mutable.
tool="$output/appimagetool-x86_64.AppImage"
tool_sha=e8c1169c4af66c3184d7ee110713d4be04befe671fa358e2c1591ee840553b03
if [[ ! -f "$tool" ]] || ! echo "$tool_sha  $tool" | sha256sum --check --status; then
  curl -fL --retry 3 -o "$tool.partial" \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  echo "$tool_sha  $tool.partial" | sha256sum --check
  mv "$tool.partial" "$tool"
fi
chmod +x "$tool"
artifact="$output/FractureBuilder-$source_id-x86_64.AppImage"
# Extract the packaging tool so neither Docker nor the host needs FUSE.
(cd "$stage" && "$tool" --appimage-extract >/dev/null)
ARCH=x86_64 "$stage/squashfs-root/AppRun" --no-appstream "$appdir" "$artifact"
chmod +x "$artifact"
(cd "$output" && sha256sum "${artifact##*/}" > "${artifact##*/}.sha256")
echo "Created $artifact"
