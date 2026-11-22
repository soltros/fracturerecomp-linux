"""Start the actual extracted AppRun without arguments under Xvfb."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

entry = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='fracture-legacy-') as folder:
    env = dict(os.environ)
    for key in ('APPIMAGE', 'RECOMPLAUNCHER', 'RECOMPLAUNCHER_DATA', 'FRACTURE_DATA_MAPPED'):
        env.pop(key, None)
    env.update(APPDIR=str(entry.parent), FRACTURE_BUILDER_DATA=folder + '/data',
               XDG_DATA_HOME=folder + '/xdg')
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen([str(entry)], env=env, stdout=log, stderr=log, start_new_session=True)
        try:
            time.sleep(3)
            if process.poll() is not None:
                log.seek(0)
                raise RuntimeError('Default GUI startup exited: ' + log.read().decode(errors='replace'))
            print('Default AppRun startup without new arguments passed')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
