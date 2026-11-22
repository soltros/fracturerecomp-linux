"""Opt-in, windowless preparation helpers for RecompLauncher."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import os
from pathlib import Path
import re
import shutil
import sys


def progress(value, message):
    print(f'progress {min(1, max(0, value)):.3f} {message}', flush=True)


def build_progress(command, line):
    match = re.match(r'\[(\d+)/(\d+)\]', line)
    if match:
        current, total = map(int, match.groups())
        codegen = 'fracture_codegen' in command
        base, span = (0.25, 0.2) if codegen else (0.5, 0.47)
        progress(base + span * current / max(1, total),
                 'Recompiling game code' if codegen else f'Compiling game: {current}/{total}')


class Tee:
    def __init__(self, stream, logfile):
        self.stream, self.logfile = stream, logfile

    def write(self, text):
        self.logfile.write(text)
        self.logfile.flush()
        return self.stream.write(text)

    def flush(self):
        self.stream.flush()
        self.logfile.flush()


@contextmanager
def preparation_log(state):
    logs = state / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    for number in (2, 1):
        source = logs / ('prepare.log' if number == 1 else f'prepare.log.{number - 1}')
        if source.exists():
            source.replace(logs / f'prepare.log.{number}')
    with (logs / 'prepare.log').open('w', encoding='utf-8') as log:
        with redirect_stdout(Tee(sys.stdout, log)), redirect_stderr(Tee(sys.stderr, log)):
            try:
                yield
            except Exception as error:
                log.write(f'Error: {error}\n')
                raise


def retain_folder(source, state):
    """Keep an independent copy, so Play and a later rebuild need no source."""
    target = state / 'game'
    if source.resolve() == target.resolve():
        return source
    partial = state / 'game.partial'
    if partial.exists():
        shutil.rmtree(partial)
    state_root = state.resolve()

    def ignore(folder, names):
        return [name for name in names
                if name.lower() == '$systemupdate'
                or (Path(folder) / name).resolve().is_relative_to(state_root)]

    count = 0

    def copy(src, dest):
        nonlocal count
        shutil.copy2(src, dest)
        count += 1
        if count == 1 or count % 100 == 0:
            progress(0.12, f'Keeping your game files: {count} files copied')

    try:
        shutil.copytree(source, partial, ignore=ignore, copy_function=copy)
        old = state / 'game.previous'
        if old.exists():
            shutil.rmtree(old)
        if target.exists():
            target.rename(old)
        partial.rename(target)
        if old.exists():
            shutil.rmtree(old)
    except Exception:
        if not target.exists() and (state / 'game.previous').exists():
            (state / 'game.previous').rename(target)
        raise
    return target


def publish_build(state, output, result):
    link = state / '.game-build.partial'
    link.unlink(missing_ok=True)
    link.symlink_to(os.path.relpath(output, state), target_is_directory=True)
    link.replace(state / 'game-build')
    # A completion marker is committed last, only after every required output.
    import json
    marker = state / 'prepared.json.partial'
    marker.write_text(json.dumps(result), encoding='utf-8')
    marker.replace(state / 'prepared.json')
    progress(1, 'Fracture is ready to play')
