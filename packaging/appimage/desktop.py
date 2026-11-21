"""Install the built game's per-user Linux application-menu entry."""
import os
from pathlib import Path
import shlex
import shutil


DESKTOP_ID = 'io.github.soltros.FractureRecomp.desktop'


def desktop_value(value):
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


def exec_argument(value):
    # Desktop entries have two escaping layers: string values, then Exec
    # argument quoting. No shell command is evaluated by the desktop file.
    value = str(value).replace('%', '%%')
    for character in ('\\', '"', '`', '$'):
        value = value.replace(character, '\\' + character)
    return desktop_value('"' + value + '"')


def atomic_write(path, text, mode=0o644):
    temporary = path.with_name(path.name + '.partial')
    temporary.write_text(text, encoding='utf-8')
    temporary.chmod(mode)
    temporary.replace(path)


def install_shortcut(state, revision, env=None):
    """Return the host desktop-file path, or None outside the AppImage bridge.

    AppRun exposes writable host data through /work and /desktop-data. Only
    *host* paths go into the desktop entry and its wrapper; guest /work and
    temporary AppImage mount paths must never become menu commands.
    """
    env = os.environ if env is None else env
    host_data = env.get('FRACTURE_HOST_DATA')
    host_desktop = env.get('FRACTURE_HOST_DESKTOP_DATA')
    desktop_data = env.get('FRACTURE_DESKTOP_DATA')
    if not all((host_data, host_desktop, desktop_data)):
        return None
    if not all(Path(value).is_absolute() for value in (host_data, host_desktop, desktop_data)):
        raise ValueError('The application-menu data paths must be absolute.')
    state = Path(state)
    host_data = Path(host_data)
    source_image = Path(env['FRACTURE_SOURCE_IMAGE']) if env.get('FRACTURE_SOURCE_IMAGE') else None
    if source_image is not None:
        # Keep one managed copy so deleting/moving the downloaded builder
        # doesn't break the installed game. Replace it atomically on rebuild.
        runtime = state / 'runtime'
        runtime.mkdir(parents=True, exist_ok=True)
        image = runtime / 'FractureBuilder.AppImage'
        stamp = runtime / 'build-id'
        current = stamp.read_text().strip() if stamp.is_file() else None
        same_file = image.exists() and source_image.samefile(image)
        if not same_file and (current != revision or not image.is_file()
                              or image.stat().st_size != source_image.stat().st_size):
            partial = image.with_suffix('.AppImage.partial')
            try:
                shutil.copyfile(source_image, partial)
                partial.chmod(0o755)
                partial.replace(image)
            finally:
                partial.unlink(missing_ok=True)
        atomic_write(stamp, revision + '\n')
        command = host_data / 'runtime' / image.name
    else:
        # Explicit --appimage-extract users keep their extracted folder;
        # launch its AppRun directly, avoiding a dependency on FUSE.
        launcher = env.get('FRACTURE_HOST_LAUNCHER', '')
        if not launcher or not Path(launcher).is_absolute():
            raise ValueError('Could not find the extracted AppImage launcher.')
        command = Path(launcher)

    wrapper = state / 'launch-fracture'
    host_wrapper = host_data / wrapper.name
    atomic_write(wrapper, '#!/bin/sh\nset -eu\n'
                 + 'export FRACTURE_BUILDER_DATA=' + shlex.quote(str(host_data)) + '\n'
                 + 'exec ' + shlex.quote(str(command)) + ' --play\n', mode=0o755)
    icon = state / 'fracture.png'
    temporary_icon = icon.with_suffix('.png.partial')
    shutil.copyfile(Path(__file__).with_name('fracture-builder.png'), temporary_icon)
    temporary_icon.chmod(0o644)
    temporary_icon.replace(icon)

    applications = Path(desktop_data) / 'applications'
    applications.mkdir(parents=True, exist_ok=True)
    desktop = applications / DESKTOP_ID
    # /bin/sh is the executable and the wrapper is an argument, so even an
    # equals sign in the user's home/data directory remains a valid Exec key.
    content = ('[Desktop Entry]\nType=Application\nVersion=1.0\n'
               'Name=Fracture\nGenericName=Action game\n'
               'Comment=Play Fracture Recomp\n'
               'Exec=/bin/sh ' + exec_argument(host_wrapper) + '\n'
               'TryExec=/bin/sh\nIcon=' + desktop_value(host_data / icon.name) + '\n'
               'Terminal=false\nCategories=Game;ActionGame;\n'
               'Keywords=Fracture;Recomp;\nStartupNotify=false\n')
    # Publish the entry only once the runtime, wrapper and icon are ready.
    atomic_write(desktop, content)
    return str(Path(host_desktop) / 'applications' / DESKTOP_ID)
