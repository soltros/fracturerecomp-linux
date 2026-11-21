"""Copy the dynamic loader and PRoot's dependency closure from its rootfs."""
from pathlib import Path
import re
import shutil
import sys

appdir = Path(sys.argv[1])
dependencies = re.findall(r'(/[^\s()]+)', Path(sys.argv[2]).read_text())
if not dependencies or 'not found' in Path(sys.argv[2]).read_text():
    raise SystemExit('Could not resolve the PRoot bootstrap libraries')
for dependency in dependencies:
    # Follow absolute symlinks *within* the exported rootfs, never on the host.
    source = appdir / 'rootfs' / dependency.lstrip('/')
    for _ in range(40):
        if not source.is_symlink():
            break
        target = source.readlink()
        source = (appdir / 'rootfs' / str(target).lstrip('/')) if target.is_absolute() else source.parent / target
    else:
        raise SystemExit(f'Symlink loop: {dependency}')
    destination = appdir / 'bootstrap'
    if Path(dependency).name != 'ld-linux-x86-64.so.2':
        destination /= 'lib'
    shutil.copy2(source, destination / Path(dependency).name)
