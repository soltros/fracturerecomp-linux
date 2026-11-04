# Fracture Recomp for Linux

A native Linux port of [ASarafanov/fracturerecomp](https://github.com/ASarafanov/fracturerecomp), targeting Vulkan as the graphics backend.

This repository is an independent port. It does not include game data. Use files extracted from a legally owned copy of Fracture; no copyrighted game files should be committed or distributed here. Upstream currently has no declared license, so its source must not be copied here unless the author grants permission or adds a license that permits the port.

## Status

The upstream source has been inspected for architecture and porting requirements. Implementation is waiting on permission to reuse upstream code and the extracted game files needed for a real build and runtime baseline.

## Goals

- Build and run natively on Linux without Wine or Proton.
- Use Vulkan for rendering.
- Preserve the upstream game's behavior and supported configuration as closely as possible.
- Keep user-provided game data outside version control.

## Porting notes

See [PORTING.md](PORTING.md) for the observed build structure, platform boundaries, and staged implementation plan.

## Upstream

- Project: [ASarafanov/fracturerecomp](https://github.com/ASarafanov/fracturerecomp)
- Original project and contributor licenses remain applicable to any source incorporated into this port. See `LICENSE` and attribution notices once upstream source is brought in.
