#!/usr/bin/env python3
"""Offline build engine for the Fracture Builder AppImage (no GUI imports)."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import sys

SOURCE = Path('/opt/fracture-source')
SDK = Path('/opt/fracture-sdk')
STATE = Path('/work')
sys.path.insert(0, str(SOURCE / 'tools'))


class BuildError(Exception):
    pass


def validate_xex(data):
    import setup
    if len(data) < 24 or data[:4] != b'XEX2':
        raise BuildError('default.xex is not an Xbox 360 executable.')
    count = struct.unpack_from('>I', data, 20)[0]
    if count > (len(data) - 24) // 8:
        raise BuildError('default.xex has a truncated header.')
    title = None
    for i in range(count):
        key, offset = struct.unpack_from('>II', data, 24 + i * 8)
        if key == 0x40006:
            if offset > len(data) - 16:
                raise BuildError('default.xex has a truncated execution header.')
            title = struct.unpack_from('>I', data, offset + 12)[0]
            break
    if title != setup.TITLE_ID:
        raise BuildError('This executable is not Fracture (title ID 4C4107D4).')
    digest = hashlib.sha256(data).hexdigest()
    if digest not in setup.RELEASES:
        raise BuildError('Unsupported Fracture release. Use an unmodified v1 or v2 default.xex.')
    return setup.RELEASES[digest][0], digest


def safe_destination(root, name):
    # A disc image is untrusted input, including names within its file table.
    parts = PurePosixPath(name).parts
    if not parts or name.startswith('/') or '\\' in name or any(p in ('..', '.') for p in parts):
        raise BuildError(f'Unsafe path in disc image: {name!r}')
    dest = root.joinpath(*parts)
    if not dest.resolve().is_relative_to(root.resolve()):
        raise BuildError(f'Disc path leaves the extraction directory: {name!r}')
    return dest


def read_assets(source):
    import xdvdfs
    if source.is_dir():
        if not (source / 'resources').is_dir():
            raise BuildError('Choose the extracted folder containing default.xex and resources/.')
        xex = source / 'default.xex'
        if not xex.is_file() or xex.stat().st_size > 64 << 20:
            raise BuildError('Missing or oversized default.xex.')
        data = xex.read_bytes()
        release, digest = validate_xex(data)
        return release, digest, data, None
    if not source.is_file():
        raise BuildError(f'Input does not exist: {source}')
    with source.open('rb') as disc:
        entries = xdvdfs.list_entries(disc)
        xex = next((e for e in entries if e.path.lower() == 'default.xex' and not e.is_dir), None)
        if xex is None or xex.size > 64 << 20:
            raise BuildError('The disc does not contain a supported default.xex.')
        data = xdvdfs.read_file(disc, xex)
    release, digest = validate_xex(data)
    return release, digest, data, entries


def run(command, cwd):
    print('+ ' + ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=cwd, check=True)


def default_jobs():
    # Generated code consumes substantial RAM per compiler process.
    try:
        available = next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))
    except (OSError, StopIteration, ValueError):
        available = 4 << 30
    return max(1, min(8, os.cpu_count() or 2, available // (2 << 30)))


def build(source, jobs):
    import xdvdfs
    source = source.expanduser().resolve(strict=True)
    print('Checking your game files…', flush=True)
    release, digest, data, entries = read_assets(source)
    # Build workspaces are keyed by source revision, preventing stale copied source
    # after an AppImage update. The SDK is already installed in the image.
    revision = (SOURCE / 'BUILD-ID').read_text().strip()
    workspace = STATE / 'builds' / revision / release
    workspace.mkdir(parents=True, exist_ok=True)
    tree = workspace / 'source'
    if not tree.exists():
        temporary = workspace / 'source.partial'
        if temporary.exists():
            shutil.rmtree(temporary)
        shutil.copytree(SOURCE, temporary)
        temporary.rename(tree)
    if entries is not None:
        game = workspace / 'game'
        game.mkdir(exist_ok=True)
        files = [e for e in entries if not e.is_dir and not e.path.lower().startswith('$systemupdate/')]
        destinations = [safe_destination(game, e.path) for e in files]
        if len(set(destinations)) != len(destinations):
            raise BuildError('Disc image contains duplicate file names.')
        total = sum(e.size for e in files)
        if shutil.disk_usage(workspace).free < total + (2 << 30):
            raise BuildError('Not enough free space to extract this disc and build the game.')
        # Always overwrite partial files. A cancelled extraction must not appear complete.
        with source.open('rb') as disc:
            for index, (entry, dest) in enumerate(zip(files, destinations), 1):
                print(f'Extracting {index}/{len(files)}: {entry.path}', flush=True)
                xdvdfs.extract(disc, entry, str(dest))
        if not (game / 'resources').is_dir():
            raise BuildError('The extracted disc has no resources/ directory.')
        (game / 'default.xex').write_bytes(data)
    else:
        game = source
    xex_dir = tree / 'xex' / release
    xex_dir.mkdir(parents=True, exist_ok=True)
    (xex_dir / 'default.xex').write_bytes(data)
    output = workspace / 'output'
    configure = ['cmake', '-S', tree, '-B', output, '-G', 'Ninja',
                 '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_C_COMPILER=clang-20',
                 '-DCMAKE_CXX_COMPILER=clang++-20', f'-DCMAKE_PREFIX_PATH={SDK}',
                 f'-DFRACTURE_RELEASES={release}', '-DREXGLUE_RECOMP_DEBUG_INFO=none',
                 '-DREXGLUE_USE_D3D12=OFF', '-DREXGLUE_USE_VULKAN=ON']
    run(configure, tree)
    run(['cmake', '--build', output, '--target', 'fracture_codegen', '--parallel', jobs], tree)
    run(configure, tree)
    run(['cmake', '--build', output, '--parallel', jobs], tree)
    binary = output / 'fracture'
    if not binary.is_file() or not (output / f'fracture_{release}.so').is_file():
        raise BuildError('Build finished without the expected game executable and module.')
    # JSON strings are valid TOML basic strings for filesystem paths on Linux.
    (output / 'fracture.toml').write_text('game_data_root = ' + json.dumps(str(game), ensure_ascii=False) + '\n')
    result = {'binary': str(binary), 'game': str(game), 'release': release, 'sha256': digest}
    pending = STATE / 'last-build.json.partial'
    pending.write_text(json.dumps(result))
    pending.replace(STATE / 'last-build.json')
    print('Build complete. You can now press Play.', flush=True)


def play():
    result = json.loads((STATE / 'last-build.json').read_text())
    binary = Path(result['binary'])
    if not binary.is_file() or not Path(result['game']).is_dir():
        raise BuildError('Game files have moved. Select their new location and build again.')
    os.chdir(binary.parent)
    os.execv(str(binary), [str(binary)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, metavar='ISO_OR_FOLDER')
    parser.add_argument('--play', action='store_true')
    parser.add_argument('--jobs', type=int, default=default_jobs())
    args = parser.parse_args()
    if not 1 <= args.jobs <= 256:
        parser.error('--jobs must be between 1 and 256')
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'build.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BuildError('Another Fracture build or game is already running.')
        if args.play:
            # Keep the lock held across exec.
            os.set_inheritable(lock.fileno(), True)
            play()
        elif args.build:
            build(args.build, args.jobs)
        else:
            parser.error('choose --build or --play')


if __name__ == '__main__':
    try:
        main()
    except (BuildError, OSError, ValueError, struct.error, RecursionError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
