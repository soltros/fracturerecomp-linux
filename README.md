# Fracture Recomp for Linux

A native Linux port of [ASarafanov/fracturerecomp](https://github.com/ASarafanov/fracturerecomp), targeting Vulkan as the graphics backend.

This repository is an independent port. It does not include game data. Use files extracted from a legally owned copy of Fracture; no copyrighted game files should be committed or distributed here.

## Status

Porting work has not started. The upstream source and the extracted game files are needed to establish a working baseline and map the Windows-specific platform layers to Linux.

## Goals

- Build and run natively on Linux without Wine or Proton.
- Use Vulkan for rendering.
- Preserve the upstream game's behavior and supported configuration as closely as possible.
- Keep user-provided game data outside version control.

## Upstream

- Project: [ASarafanov/fracturerecomp](https://github.com/ASarafanov/fracturerecomp)
- Original project and contributor licenses remain applicable to any source incorporated into this port. See `LICENSE` and attribution notices once upstream source is brought in.
