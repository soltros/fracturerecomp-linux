#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SDK_VERSION="0.10.0"
SDK_COMMIT="f5337cdc947ff6d4c4196737e2c807a48f2a1fc2"
SDK_REPO="https://github.com/rexglue/rexglue-sdk.git"
SDK_ROOT="$ROOT/third_party/rexglue-sdk"
SDK_SOURCE="$SDK_ROOT/src"
SDK_PREFIX="$SDK_ROOT/$SDK_VERSION/linux-amd64"
SDK_BUILD="$SDK_SOURCE/out/build/linux-amd64"

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

for tool in git cmake clang clang++; do
  command -v "$tool" >/dev/null 2>&1 || fail "$tool is required; install the Linux ReXGlue build prerequisites first"
done
command -v ninja >/dev/null 2>&1 || fail "ninja is required by the ReXGlue linux-amd64 preset"

if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  fail "this bootstrap currently targets Linux x86_64"
fi

if [[ -d "$SDK_SOURCE/.git" ]]; then
  actual_commit="$(git -C "$SDK_SOURCE" rev-parse HEAD)"
  [[ "$actual_commit" == "$SDK_COMMIT" ]] || fail "found SDK source at $actual_commit; expected $SDK_COMMIT. Remove $SDK_SOURCE to fetch the pinned release."
else
  mkdir -p "$SDK_ROOT"
  git clone --quiet --branch "v$SDK_VERSION" --depth 1 --recurse-submodules --shallow-submodules --jobs 8 "$SDK_REPO" "$SDK_SOURCE"
  actual_commit="$(git -C "$SDK_SOURCE" rev-parse HEAD)"
  [[ "$actual_commit" == "$SDK_COMMIT" ]] || fail "SDK tag resolved to $actual_commit; expected $SDK_COMMIT"
fi

# A prior interrupted clone may have missing submodules.
git -C "$SDK_SOURCE" submodule update --init --recursive --depth 1 --jobs 8

cmake --preset linux-amd64 \
  -DREXGLUE_USE_D3D12=OFF \
  -DREXGLUE_USE_VULKAN=ON \
  "-DCMAKE_INSTALL_PREFIX=$SDK_PREFIX"

jobs="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '4')"
cmake --build "$SDK_BUILD" --config Release --target install --parallel "$jobs"
cmake --build "$SDK_BUILD" --config RelWithDebInfo --target install --parallel "$jobs"

printf '\nReXGlue %s (Vulkan, Linux x86_64) installed at:\n%s\n' "$SDK_VERSION" "$SDK_PREFIX"
printf 'Configure the app with: cmake -S . -B out/build/linux-amd64 -DCMAKE_PREFIX_PATH="%s"\n' "$SDK_PREFIX"
