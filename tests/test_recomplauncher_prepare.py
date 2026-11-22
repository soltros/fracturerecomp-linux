import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_appimage_builder import builder, executable, setup


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='launcher paths ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / 'recomp data'
        self.state.mkdir()
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'BUILD-ID').write_text('revision-one')
        self.game = self.root / 'original copy'
        (self.game / 'resources').mkdir(parents=True)
        (self.game / 'resources/asset.dat').write_bytes(b'fixture')
        data = executable()
        (self.game / 'default.xex').write_bytes(data)
        self.digest = hashlib.sha256(data).hexdigest()
        patches = [patch.object(builder, 'SOURCE', self.source),
                   patch.object(builder, 'STATE', self.state),
                   patch.dict(setup.RELEASES, {self.digest: ('v2', 'test fixture')}),
                   patch.dict(os.environ, {'RECOMPLAUNCHER_DATA': str(self.state)}),
                   patch.object(builder, 'install_shortcut', side_effect=AssertionError('No external launcher copy in portable mode'))]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def fake_build(self, command, cwd):
        if command[:2] == ['cmake', '--build'] and '--target' not in command:
            output = Path(command[2])
            output.mkdir(exist_ok=True)
            (output / 'fracture').write_text('#!/bin/sh\nexit 0\n')
            (output / 'fracture_v2.so').write_bytes(b'fixture module')

    def prepare(self, source=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(builder, 'run', side_effect=self.fake_build):
            builder.build(source or self.game, 1, prepare=True)
        return output.getvalue()

    def test_prepare_keeps_copy_and_publishes_completion_last(self):
        output = self.prepare()
        self.assertIn('progress 1.000', output)
        result = json.loads((self.state / 'last-build.json').read_text())
        self.assertEqual(result['game'], str(self.state / 'game'))
        self.assertTrue((self.state / 'game-build/fracture').is_file())
        self.assertTrue((self.state / 'prepared.json').is_file())
        self.assertNotIn('shortcut', result)
        shutil.rmtree(self.game)
        self.assertEqual((self.state / 'game/resources/asset.dat').read_bytes(), b'fixture')
        self.assertEqual(builder.installed_game()['sha256'], self.digest)

    def test_update_rebuilds_from_kept_copy_and_preserves_settings(self):
        self.prepare()
        settings = self.state / 'settings.toml'
        settings.write_text('fullscreen = false\n# My preference\n')
        shutil.rmtree(self.game)
        (self.source / 'BUILD-ID').write_text('revision-two')
        self.prepare(self.state / 'game')
        self.assertIn('revision-two', str((self.state / 'game-build').resolve()))
        self.assertEqual(settings.read_text(), 'fullscreen = false\n# My preference\n')

    def test_failed_prepare_has_no_valid_done_marker(self):
        self.prepare()
        with patch.object(builder, 'run', side_effect=subprocess.CalledProcessError(1, 'cmake')):
            with self.assertRaises(subprocess.CalledProcessError):
                builder.build(self.state / 'game', 1, prepare=True)
        self.assertFalse((self.state / 'prepared.json').exists())
        with self.assertRaises(builder.SetupRequiredError):
            builder.installed_game()

    def test_play_starts_the_built_program_without_the_builder_ui(self):
        self.prepare()
        old_cwd = Path.cwd()
        self.addCleanup(os.chdir, old_cwd)
        with patch.object(builder.os, 'execv') as execute:
            builder.play()
        args = execute.call_args.args[1]
        self.assertEqual(args[1], '--game_data_root=' + str(self.state / 'game'))

    def test_prepare_logs_errors_and_rotates(self):
        with self.assertRaises(builder.BuildError):
            with builder.launcher_prepare.preparation_log(self.state):
                print('progress 0.100 Reading copy')
                raise builder.BuildError('invalid test copy')
        self.assertIn('invalid test copy', (self.state / 'logs/prepare.log').read_text())
        with builder.launcher_prepare.preparation_log(self.state):
            print('second setup')
        self.assertIn('invalid test copy', (self.state / 'logs/prepare.log.1').read_text())
