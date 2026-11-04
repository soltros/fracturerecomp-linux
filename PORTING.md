# Linux porting notes

These notes come from inspecting the public upstream repository at
`ASarafanov/fracturerecomp` (default branch `master`, HEAD
`5132ba71e417da55f8047d4bebae4c43aab5b223`). No upstream source is copied in
this repository. GitHub reports no declared license for upstream, so source
reuse requires permission from its author or an upstream license that allows
this derivative work.

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

## Build host snapshot

At the time these notes were updated, this workspace did not have `clang++`,
`cmake`, `ninja`, `pkg-config`, or `vulkaninfo` on `PATH`; Python 3.12.15 was
available. This environment therefore cannot currently build the SDK or
validate Vulkan device enumeration. A Linux build host needs the SDK's stated
toolchain plus SDL3 and Vulkan development/runtime components, and a Vulkan
capable GPU/driver for runtime verification.

## Port sequence

1. Obtain upstream source reuse permission (or wait for a suitable upstream
   license) and import the baseline with attribution and license notices.
2. Add a Linux build/setup path that builds the pinned ReXGlue SDK with Vulkan
   and produces host plus generated game module(s) on Linux.
3. Port filesystem locations, executable restart, file selection, GPU listing,
   input, and any remaining Win32 calls to native Linux/SDL equivalents.
4. Make Vulkan mandatory on Linux, including GPU selection and actionable
   startup diagnostics; preserve the Windows backend behavior in any shared
   source port.
5. Build against the user-provided extracted game files, then verify install,
   launch, settings, input, audio, saves, and gameplay against the upstream
   behavior on a Linux Vulkan system.

The complete goal remains a 1:1 native Linux run. The extracted game files
are user-provided inputs and must remain untracked and undistributed.
