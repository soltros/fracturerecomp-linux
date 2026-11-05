#!/usr/bin/env python3
"""Build the native Linux port from an existing extracted game directory."""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import setup as upstream_setup  # noqa: E402


def run(command):
    print("+", " ".join(str(part) for part in command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def stage_extracted_files(source):
    source = source.expanduser().resolve(strict=True)
    xex = source / "default.xex"
    if not xex.is_file() or not (source / "resources").is_dir():
        raise SystemExit(f"{source} must contain default.xex and resources/")

    digest = hashlib.sha256(xex.read_bytes()).hexdigest()
    release = upstream_setup.RELEASES.get(digest)
    title_id = upstream_setup.xex_title_id(xex.read_bytes())
    if title_id != upstream_setup.TITLE_ID:
        raise SystemExit(f"{xex} has title ID {title_id or 0:08X}; expected Fracture {upstream_setup.TITLE_ID:08X}")
    if not release:
        raise SystemExit(f"{xex} does not match either supported Fracture release (SHA-256 {digest})")
    variant, description = release

    game_path = ROOT / "game"
    if game_path.is_symlink():
        if game_path.resolve() != source:
            game_path.unlink()
            game_path.symlink_to(source, target_is_directory=True)
    elif game_path.exists():
        raise SystemExit(f"{game_path} exists and is not the extracted game directory link")
    else:
        game_path.symlink_to(source, target_is_directory=True)

    release_dir = ROOT / "xex" / variant
    release_dir.mkdir(parents=True, exist_ok=True)
    xex_link = release_dir / "default.xex"
    if xex_link.is_symlink():
        if xex_link.resolve() != xex:
            xex_link.unlink()
        else:
            xex_link.unlink()
            shutil.copy2(xex, xex_link)
    elif xex_link.exists():
        if hashlib.sha256(xex_link.read_bytes()).hexdigest() != digest:
            raise SystemExit(f"Refusing to replace a different local file at {xex_link}")
    else:
        # ReXGlue codegen requires the XEX to resolve inside game_root, so the
        # small entrypoint is copied; the rest of the extracted files stay put.
        shutil.copy2(xex, xex_link)

    print(f"Using {description}; game files remain at {source}")
    return variant


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_directory", type=Path, help="folder containing default.xex and resources/")
    parser.add_argument("--config", choices=("debug", "release", "relwithdebinfo"), default="relwithdebinfo")
    args = parser.parse_args()

    if not sys.platform.startswith("linux") or os.uname().machine not in ("x86_64", "amd64"):
        raise SystemExit("This setup command currently targets Linux x86_64")

    variant = stage_extracted_files(args.game_directory)
    run([str(ROOT / "scripts" / "bootstrap-sdk-linux.sh")])

    preset = f"linux-amd64-{args.config}"
    configure = [
        "cmake", "--preset", preset,
        f"-DFRACTURE_RELEASES={variant}",
        "-DREXGLUE_USE_D3D12=OFF",
        "-DREXGLUE_USE_VULKAN=ON",
    ]
    run(configure)
    jobs = str(os.cpu_count() or 4)
    run(["cmake", "--build", "--preset", preset, "--target", "fracture_codegen", "--parallel", jobs])
    run(configure)
    run(["cmake", "--build", "--preset", preset, "--parallel", jobs])
    print(f"Built Linux Vulkan app at out/build/{preset}/fracture")


if __name__ == "__main__":
    main()
