# Fracture Recomp for Linux

<a href="https://recomplauncher.com"><picture><source media="(prefers-color-scheme: dark)" srcset="https://recomplauncher.com/assets/press/launcher/badge-light.svg"><img alt="Get it on RecompLauncher" src="https://recomplauncher.com/assets/press/launcher/badge-dark.svg" height="48"></picture></a>

Bring your own Fracture Xbox 360 ISO or extracted `default.xex` + `resources/`
folder. Open the AppImage to build and play, or let RecompLauncher handle setup.
No game files are included.

A native Linux port of [ASarafanov/fracturerecomp](https://github.com/ASarafanov/fracturerecomp), targeting Vulkan as the graphics backend.

This repository is an independent Linux port of [ASarafanov/fracturerecomp](https://github.com/ASarafanov/fracturerecomp). Upstream has no declared license; see [UPSTREAM.md](UPSTREAM.md) for the imported revision and attribution. This repository does not include game data. Keep files extracted from a legally owned copy outside version control; no copyrighted game files should be committed or distributed here.

## Status

The upstream baseline and native Linux platform path are in place. The v2
release has generated and built on Linux x86_64, and its Vulkan game window is
running with user-provided game files. Broader behavior and fidelity checks are
still in progress.

## Goals

- Build and run natively on Linux without Wine or Proton.
- Use Vulkan for rendering.
- Preserve the upstream game's behavior and supported configuration as closely as possible.
- Keep user-provided game data outside version control.

## Porting notes

See [PORTING.md](PORTING.md) for the observed build structure, platform boundaries, and staged implementation plan.

## Build & Play AppImage

### RecompLauncher

The AppImage embeds `recomplauncher.json` at its root. RecompLauncher can pick
your ISO or extracted copy, run windowless preparation, expose the existing
game settings, and start Fracture directly. It extracts the AppImage and runs
`AppRun`; no FUSE mount, `$APPIMAGE`, separate runtime copy, or builder window
is needed in this mode.

Play runs the native game outside PRoot, using the bundled Linux libraries
and Mesa drivers. PRoot is used only by the build tools. Existing AppImage
builds can use this launch fix without recompiling: open the updated AppImage
and press Play once to refresh the Games-menu runtime.

Preparation retains the assets under `recompdata/game`, and generated build
files go under `recompdata/cache`. Later updates can rebuild from that retained
copy even after the original ISO/folder is removed. The packaged profile's
preparation version is the source build ID, so changed code is rebuilt when
needed. Only a successful build commits the completion marker.

`--data DIRECTORY` (or `RECOMPLAUNCHER_DATA`) selects one portable data folder:
`settings.toml`, `saves/`, `logs/`, `cache/`, and retained game files all stay
there. The normal standalone UI and data paths remain the default when the
new arguments/environment are absent.

```sh
./FractureBuilder-Linux-x86_64.AppImage --prepare --game="/path/to/Fracture.iso" --data "/path/to/recompdata"
./FractureBuilder-Linux-x86_64.AppImage --play --data "/path/to/recompdata"
```

The schema is vendored under `.github/recomplauncher` and checked in CI with
`python3 tools/validate_recomplauncher.py`. Known executable SHA-256 values
remain enforced by the existing installer; the profile makes no whole-disc
verified-dump claim because verified disc CRC32/size pairs are not available.

The offline builder AppImage packages Clang 20, CMake, Ninja, Python, and a
prebuilt Vulkan-only ReXGlue SDK. You supply the game files; the app validates
them and builds the matching native Linux game module. It does not download
game data or require development packages on your computer.

The packaging workflow has produced an AppImage and passed an offline
compiler/SDK smoke test. Actual gameplay with user-provided assets still
needs validation before calling this a tested game release.

1. Download `FractureBuilder-Linux-x86_64.AppImage` from the
   [latest release](https://github.com/soltros/fracturerecomp-linux/releases/latest).
   Mark the AppImage executable in your file manager
   (or run `chmod +x FractureBuilder-*.AppImage`).
2. Open it and choose your legally owned Fracture Xbox 360 ISO, or an extracted
   folder containing `default.xex` and `resources/`. Keep the files in your
   home directory or under `/media` or `/mnt`. Both supported v1 and v2
   executables are checked by title ID and SHA-256; modified files are rejected.
3. Press **Build game**, then **Play**. Later launches offer Play immediately.
   Leave the extracted folder where it is; the app reads it without copying
   the large assets. For an ISO, it extracts the assets into its data folder.

A successful build also adds **Fracture** to the **Games** section of your
Linux application menu. It launches the game directly. Rebuilding updates the
same entry. With an older existing build, press Play once in the updated
builder to add the shortcut without recompiling.

The menu entry is installed per user under `$XDG_DATA_HOME/applications`
(normally `~/.local/share/applications`). A managed copy of the AppImage is
kept in the builder's data folder so the shortcut survives moving or deleting
the original download; allow roughly another 465 MB for this runtime copy.
If you run an extracted AppDir instead, keep that extracted folder in place.

Building is offline, including the first build. The compiler uses a conservative
RAM-based parallelism limit; compilation can still take several minutes.
The AppImage is larger than a conventional game launcher because it includes
the compiler, Linux userspace, SDK, and SDK source/notices.

Initial target: Linux x86_64 (x86-64-v2 CPU) with an X11 or XWayland desktop, PRoot/ptrace
permitted, and Vulkan-capable Intel or AMD graphics supported by the bundled
Ubuntu 24.04 Mesa drivers. NVIDIA proprietary drivers are not integrated yet.
Wayland-only desktops without XWayland cannot display the Tk build wizard.
Docker and administrator access are only needed by the maintainer packaging
the app, not by players.

Builds, extracted ISO data, logs, and settings are stored under
`~/.local/share/fracture-builder` (or `$XDG_DATA_HOME/fracture-builder`). Saves
follow the game's existing user-directory behavior. The original ISO/folder
is never modified. Keep sufficient space for the toolchain image, build
output, and, for ISOs, a second copy of the game assets. Cancelling stops the
build; select the same input and build again to retry.

If your distribution cannot mount AppImages with FUSE:

```sh
./FractureBuilder-…-x86_64.AppImage --appimage-extract
./squashfs-root/AppRun
```

Command-line options are also available:

```sh
./FractureBuilder-…-x86_64.AppImage --build "/path/to/Fracture.iso" --jobs 2
./FractureBuilder-…-x86_64.AppImage --play
./FractureBuilder-…-x86_64.AppImage --self-test
./FractureBuilder-…-x86_64.AppImage --install-shortcut
```

For a different storage location, set `FRACTURE_BUILDER_DATA` to an absolute
directory. Reuse that location for subsequent launches. The game currently
runs inside the included PRoot userspace, which can add overhead; the game
code is compiled for Linux and does not use Wine or Proton. PRoot supplies
path translation, not a security boundary.

### Package the AppImage

On a Linux x86_64 machine with Docker, Python 3, curl, tar, and sha256sum:

```sh
BUILD_JOBS=2 bash scripts/build-appimage.sh
```

The first packaging build requires internet access and builds the pinned
ReXGlue SDK once. Docker caches that expensive step. The output AppImage and
SHA-256 file appear under `out/appimage/`. The GitHub Actions workflow runs
the same command, tests the asset validator with synthetic fixtures, and
smoke-tests the bundled tools without network access. It never receives any
game files. Inputs to the packaging container are explicitly allowlisted.
Ubuntu package copyright notices remain in `/usr/share/doc` inside the bundled
rootfs, and ReXGlue's source and third-party notices remain under
`/opt/rexglue-source`; the original upstream attribution is included too.

For a conventional developer build from an extracted game folder, install the
prerequisites listed in [PORTING.md](PORTING.md), then run:

```sh
python3 tools/setup_linux.py "/path/to/extracted/Fracture" --config release
```

## Upstream

- Project: [ASarafanov/fracturerecomp](https://github.com/ASarafanov/fracturerecomp)
- Source baseline: `5132ba71e417da55f8047d4bebae4c43aab5b223`.
