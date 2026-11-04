# Fracture Recomp for Linux

A native Linux port of [ASarafanov/fracturerecomp](https://github.com/ASarafanov/fracturerecomp), targeting Vulkan as the graphics backend.

This repository is an independent Linux port of [ASarafanov/fracturerecomp](https://github.com/ASarafanov/fracturerecomp), imported with the permission confirmed by the port maintainer. Upstream has no declared license; see [UPSTREAM.md](UPSTREAM.md) for the imported revision and attribution. This repository does not include game data. Keep files extracted from a legally owned copy outside version control; no copyrighted game files should be committed or distributed here.

## Status

The upstream source baseline is present and Linux platform work is underway. The extracted game files are still needed to generate and build the game module and establish a runtime baseline.

## Goals

- Build and run natively on Linux without Wine or Proton.
- Use Vulkan for rendering.
- Preserve the upstream game's behavior and supported configuration as closely as possible.
- Keep user-provided game data outside version control.

## Porting notes

See [PORTING.md](PORTING.md) for the observed build structure, platform boundaries, and staged implementation plan.

## Upstream

- Project: [ASarafanov/fracturerecomp](https://github.com/ASarafanov/fracturerecomp)
- Source baseline: `5132ba71e417da55f8047d4bebae4c43aab5b223`.
