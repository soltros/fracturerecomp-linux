# Linux porting notes

These notes track the source imported from `ASarafanov/fracturerecomp`, default
branch `master`, commit `5132ba71e417da55f8047d4bebae4c43aab5b223`. The port
maintainer confirmed permission to port the source. The upstream repository
has no declared license; see [UPSTREAM.md](UPSTREAM.md) for attribution.

## Architecture observed upstream

- CMake 3.25+, C++23, and ReXGlue SDK 0.10.0 drive the host and generated game
  code. `cmake/fracture_recomp.cmake` generates separate game modules for v1
  and v2 from each user's `default.xex`.
- The setup script is Windows-only (`setup.bat`) and currently builds the SDK
  with both D3D12 and Vulkan plugins. The pinned ReXGlue v0.10.0 SDK itself
  already supports Linux, ships Linux AMD64 and ARM64 CMake presets, and
  enables Vulkan by default on Linux (D3D12 is Windows-only). The port needs a
  Linux setup/install path for that existing SDK support, not a new SDK
  backend.
- The game renderer already has a Vulkan selection path, but the current app
  can fall back to D3D12. Linux must select Vulkan as its required backend and
  report a clear error if Vulkan or a compatible device is unavailable.
- Host functionality is spread across `src/` rather than being isolated in a
  platform layer. Win32-dependent behavior includes OS/user paths and restart
  in settings, GPU enumeration (DXGI), installer file picking (COM), direct
  XInput polling, executable/module path lookup, and UTF-16 path handling.
- Controller handling already offers SDL in the settings UI; the Linux port
  should use SDL consistently instead of direct XInput paths.
- The non-Windows branches are mostly explicit stubs today: game module loading
  reports Windows-only, restart is unimplemented, Vulkan GPU enumeration
  returns no devices, installer browse reports only drag-and-drop, installer
  pad navigation returns no input, and menu-hook discovery returns null.
  Merely compiling the existing non-Windows target would not provide a usable
  Linux game.

The inspected SDK revision is `f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`
(tag `v0.10.0`). Its license is BSD-style with Xenia-derived notices; retain
the SDK's `LICENSE` and third-party notices if its source is built or bundled.

## Linux runtime checkpoint

On 2026-11-05, the v2 `default.xex` generated and compiled successfully with
the pinned ReXGlue 0.10.0 SDK on Linux x86_64. The host selected SDL's Wayland
video driver, loaded `fracture_v2.so`, and opened the game with Vulkan on the
maintainer's NixOS desktop. The maintainer confirmed gameplay in the window.
This establishes a first native runtime checkpoint; it does not yet establish
full feature or visual parity.

The checked build used Clang 20, CMake 4.4, Ninja, Vulkan, SDL3, X11, and
Wayland development dependencies. The SDK's SDL build must include the system's
Wayland or X11 video driver. On NixOS, run the app in an environment that makes
the dynamic SDL backend libraries and Vulkan loader available at runtime.

## SDK bootstrap

On Linux x86_64 with Git, Clang 20+, CMake 3.25+, Ninja, the ReXGlue Linux
development dependencies, and Vulkan headers/tools installed, run:

```sh
./scripts/bootstrap-sdk-linux.sh
```

The script pins ReXGlue v0.10.0 by commit, checks out its recursive submodules,
explicitly disables D3D12 and enables Vulkan, and installs both Release and
RelWithDebInfo SDK configurations under the ignored `third_party/` directory.
It does not need or read Fracture game files.

## Port sequence

1. Exercise the setup path from a clean Linux checkout and document any
   distribution-specific SDK dependencies.
2. Port filesystem locations, executable restart, file selection, GPU listing,
   input, and any remaining Win32 calls to native Linux/SDL equivalents.
3. Make Vulkan mandatory on Linux, including GPU selection and actionable
   startup diagnostics; preserve the Windows backend behavior in any shared
   source port.
4. Compare install, settings, input, audio, saves, and gameplay against the
   upstream behavior on a Linux Vulkan system, and address any differences.

The complete goal remains a 1:1 native Linux run. The extracted game files
are user-provided inputs and must remain untracked and undistributed.
