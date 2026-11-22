"""Host-side UI and game entry point; PRoot is reserved for compilation."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

from desktop import atomic_write, install_shortcut


class SetupMissing(Exception):
    pass


def host_path(value, state):
    path = Path(value)
    if path.is_relative_to('/work'):
        return state / path.relative_to('/work')
    return path


def add_shortcut(appdir, state, result):
    if os.environ.get('RECOMPLAUNCHER_DATA'):
        return
    env = dict(os.environ)
    env['FRACTURE_DESKTOP_DATA'] = env['FRACTURE_HOST_DESKTOP_DATA']
    env['FRACTURE_SOURCE_IMAGE'] = env.get('APPIMAGE', '')
    revision = (appdir / 'rootfs/opt/fracture-source/BUILD-ID').read_text().strip()
    shortcut = install_shortcut(state, revision, env)
    if shortcut:
        result['shortcut'] = shortcut
        atomic_write(state / 'last-build.json', json.dumps(result))


def runtime_environment(appdir, state, portable, environ=None):
    env = dict(os.environ if environ is None else environ)
    root = appdir / 'rootfs'
    libraries = ':'.join(str(root / path) for path in (
        'opt/fracture-sdk/lib', 'opt/fracture-sdk/lib64',
        'usr/lib/x86_64-linux-gnu', 'usr/lib'))
    for key in ('PYTHONHOME', 'PYTHONPATH', 'TCL_LIBRARY', 'TK_LIBRARY', 'LD_PRELOAD'):
        env.pop(key, None)
    env['LD_LIBRARY_PATH'] = libraries
    # Match the bundled loader, libc and Mesa rather than mixing host drivers
    # with the image's userspace. No filesystem tracing is involved.
    drivers = ':'.join(str(root / 'usr/share/vulkan/icd.d' / name)
                       for name in ('radeon_icd.json', 'intel_icd.json',
                                    'intel_hasvk_icd.json', 'lvp_icd.json'))
    env.update(VK_DRIVER_FILES=drivers, VK_ICD_FILENAMES=drivers,
               VK_LAYER_PATH=str(root / 'usr/share/vulkan/explicit_layer.d'))
    if portable:
        env.update(RECOMPLAUNCHER_DATA=str(state), XDG_DATA_HOME=str(state / 'userdata'),
                   XDG_CONFIG_HOME=str(state / 'config'), XDG_CACHE_HOME=str(state / 'cache/xdg'))
        scratch = env.get('TMPDIR') or str(state / 'cache/tmp')
        Path(scratch).mkdir(parents=True, exist_ok=True)
        env.update(TMPDIR=scratch, TEMP=scratch, TMP=scratch)
    return env, libraries


def relocate_binary(appdir, binary, libraries):
    root = appdir / 'rootfs'
    loader = root / 'usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2'
    patcher = root / 'usr/bin/patchelf'
    command = [str(loader), '--library-path', libraries, str(patcher)]
    interpreter = subprocess.check_output([*command, '--print-interpreter', str(binary)], text=True).strip()
    rpath = subprocess.check_output([*command, '--print-rpath', str(binary)], text=True).strip()
    if interpreter != str(loader) or rpath != libraries:
        # Keep /proc/self/exe pointing to the actual game: its module lookup,
        # settings and restart code all use the executable's directory.
        subprocess.run([*command, '--set-interpreter', str(loader),
                        '--force-rpath', '--set-rpath', libraries, str(binary)], check=True)


def play(appdir, state):
    portable = bool(os.environ.get('RECOMPLAUNCHER_DATA'))
    if portable and not (state / 'prepared.json').is_file():
        raise SetupMissing('The game needs preparation. Run Set Up Again in RecompLauncher.')
    result = json.loads((state / 'last-build.json').read_text())
    binary, game = (host_path(result[key], state) for key in ('binary', 'game'))
    if not binary.is_file() or not game.is_dir():
        raise SetupMissing('The game build or assets are missing. Build the game again.')
    try:
        add_shortcut(appdir, state, result)
    except (OSError, ValueError) as error:
        print(f'Warning: could not update the Games menu shortcut: {error}', flush=True)
    env, libraries = runtime_environment(appdir, state, portable)
    relocate_binary(appdir, binary, libraries)
    os.chdir(binary.parent)
    os.execve(binary, [str(binary), '--game_data_root=' + str(game)], env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--play', action='store_true')
    parser.add_argument('--install-shortcut', action='store_true')
    parser.add_argument('--data')  # Already resolved by AppRun.
    args = parser.parse_args()
    appdir = Path(os.environ['APPDIR'])
    state = Path(os.environ['FRACTURE_NATIVE_DATA'])
    if not args.play and not args.install_shortcut:
        import tkinter as tk
        from launcher import Launcher
        root = tk.Tk()
        Launcher(root, state_dir=state)
        root.mainloop()
        return
    with (state / 'build.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another Fracture build or game is already running.')
        if args.play:
            os.set_inheritable(lock.fileno(), True)
            play(appdir, state)
        else:
            result = json.loads((state / 'last-build.json').read_text())
            add_shortcut(appdir, state, result)


if __name__ == '__main__':
    try:
        main()
    except SetupMissing as error:
        print(f'Error: {error}', file=sys.stderr, flush=True)
        sys.exit(3)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
