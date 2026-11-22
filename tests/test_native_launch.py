import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1] / 'packaging/appimage'
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('native_launch', HERE / 'native.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeLaunchTests(unittest.TestCase):
    def test_guest_paths_map_to_relocated_data_without_changing_external_assets(self):
        state = Path('/home/player/My Games/recompdata')
        self.assertEqual(native.host_path('/work/cache/build/fracture', state), state / 'cache/build/fracture')
        self.assertEqual(native.host_path('/mnt/My Disc/game', state), Path('/mnt/My Disc/game'))
        self.assertEqual(native.host_path('/work-other/game', state), Path('/work-other/game'))

    def test_portable_environment_uses_host_paths_and_does_not_leak_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            env, libs = native.runtime_environment(Path('/app'), state, True,
                {'PYTHONHOME': '/bad', 'LD_PRELOAD': '/bad', 'DISPLAY': ':4'})
            self.assertNotIn('PYTHONHOME', env)
            self.assertNotIn('LD_PRELOAD', env)
            self.assertEqual(env['DISPLAY'], ':4')
            self.assertEqual(env['RECOMPLAUNCHER_DATA'], str(state))
            self.assertEqual(env['XDG_CACHE_HOME'], str(state / 'cache/xdg'))
            self.assertTrue(Path(env['TMPDIR']).is_dir())
            self.assertIn('/app/rootfs/opt/fracture-sdk/lib', libs)
            self.assertIn('/app/rootfs/usr/share/vulkan/icd.d/radeon_icd.json', env['VK_DRIVER_FILES'])

    def test_prepared_build_executes_native_binary_with_host_asset_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            (state / 'cache').mkdir()
            (state / 'cache/fracture').touch()
            (state / 'game').mkdir()
            (state / 'prepared.json').write_text('{}')
            metadata = json.dumps({'binary': '/work/cache/fracture', 'game': '/work/game'})
            (state / 'last-build.json').write_text(metadata)
            with patch.dict(os.environ, RECOMPLAUNCHER_DATA=str(state)), \
                 patch.object(native, 'relocate_binary') as relocate, \
                 patch.object(native.os, 'chdir'), patch.object(native, 'run_game') as execute:
                native.play(Path('/app'), state)
            relocate.assert_called_once()
            self.assertEqual(execute.call_args.args[0], state / 'cache/fracture')
            self.assertEqual(execute.call_args.args[1], state / 'game')
            self.assertEqual((state / 'last-build.json').read_text(), metadata)

    def test_portable_play_requires_successful_preparation(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch.dict(os.environ, RECOMPLAUNCHER_DATA=temporary):
            with self.assertRaises(native.SetupMissing):
                native.play(Path('/app'), Path(temporary))

    def test_supervisor_waits_for_restarted_game_and_reports_its_failure(self):
        for exit_code in (0, 7):
            with self.subTest(exit_code=exit_code), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                marker = root / 'restarted'
                script = root / 'fracture'
                script.write_text(f'#!{sys.executable}\n'
                                  'import os,time\n'
                                  'if os.fork(): os._exit(0)\n'
                                  'time.sleep(0.1)\n'
                                  f'open({str(marker)!r}, "w").write("done")\n'
                                  f'os._exit({exit_code})\n')
                script.chmod(0o755)
                self.assertEqual(native.run_game(script, root, dict(os.environ)), exit_code)
                self.assertEqual(marker.read_text(), 'done')
