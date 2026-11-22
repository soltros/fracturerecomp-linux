import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('game_desktop', ROOT / 'packaging/appimage/desktop.py')
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='fracture menu ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / 'Data = "100%" $HOME `echo unsafe` \\ café'
        self.state.mkdir()
        self.xdg = self.root / 'custom application data'
        self.xdg.mkdir()
        self.source = self.root / 'downloaded builder.AppImage'
        # An executable fixture exercises menu launch without game assets or FUSE.
        self.source.write_text('#!/bin/sh\nprintf "%s\\n%s\\n" "$1" "$FRACTURE_BUILDER_DATA" > "$FRACTURE_BUILDER_DATA/launched"\n')
        self.source.chmod(0o755)
        self.env = {
            'FRACTURE_HOST_DATA': str(self.state),
            'FRACTURE_HOST_DESKTOP_DATA': str(self.xdg),
            'FRACTURE_DESKTOP_DATA': str(self.xdg),
            'FRACTURE_SOURCE_IMAGE': str(self.source),
        }

    def test_installs_only_one_game_entry_and_survives_download_removal(self):
        path = Path(desktop.install_shortcut(self.state, 'revision-1', self.env))
        self.assertEqual(path.parent, self.xdg / 'applications')
        self.assertIn('Categories=Game;ActionGame;', path.read_text())
        self.assertIn('Name=Fracture\n', path.read_text())
        self.assertNotIn('/work/', path.read_text())
        self.source.unlink()
        subprocess.run(['/bin/sh', str(self.state / 'launch-fracture')], check=True)
        self.assertEqual((self.state / 'launched').read_text().splitlines(), ['--play', str(self.state)])

    def test_rebuild_reuses_or_atomically_updates_the_managed_runtime(self):
        desktop.install_shortcut(self.state, 'revision-1', self.env)
        image = self.state / 'runtime/FractureBuilder.AppImage'
        before = image.stat().st_ino
        desktop.install_shortcut(self.state, 'revision-1', self.env)
        self.assertEqual(image.stat().st_ino, before)
        self.source.write_text(self.source.read_text() + '# version 2\n')
        desktop.install_shortcut(self.state, 'revision-2', self.env)
        self.assertEqual(image.read_bytes(), self.source.read_bytes())
        self.assertEqual(len(list((self.xdg / 'applications').glob('*.desktop'))), 1)
        old = image.read_bytes()
        with patch.object(desktop.shutil, 'copyfile', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                desktop.install_shortcut(self.state, 'revision-3', self.env)
        self.assertEqual(image.read_bytes(), old)

    def test_extracted_appdir_uses_its_apprun(self):
        self.env.pop('FRACTURE_SOURCE_IMAGE')
        self.env['FRACTURE_HOST_LAUNCHER'] = str(self.source)
        desktop.install_shortcut(self.state, 'revision-1', self.env)
        subprocess.run(['/bin/sh', str(self.state / 'launch-fracture')], check=True)
        self.assertFalse((self.state / 'runtime').exists())
        self.assertEqual((self.state / 'launched').read_text().splitlines()[0], '--play')

    def test_does_not_write_menu_files_without_the_host_bridge(self):
        self.assertIsNone(desktop.install_shortcut(self.state, 'revision-1', {}))
        self.assertFalse((self.xdg / 'applications').exists())

    @unittest.skipUnless(shutil.which('desktop-file-validate') and shutil.which('gio'),
                         'desktop validation tools unavailable')
    def test_real_desktop_parser_launches_quoted_paths_without_shell_expansion(self):
        path = desktop.install_shortcut(self.state, 'revision-1', self.env)
        subprocess.run(['desktop-file-validate', path], check=True)
        subprocess.run(['gio', 'launch', path], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        marker = self.state / 'launched'
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(marker.read_text().splitlines(), ['--play', str(self.state)])


if __name__ == '__main__':
    unittest.main()
