import importlib.util
import os
from pathlib import Path
import unittest


@unittest.skipUnless(os.environ.get('DISPLAY') and os.environ.get('CI'), 'GUI smoke test runs under Xvfb in CI')
class LauncherTests(unittest.TestCase):
    def test_wizard_renders_and_reports_worker_failure(self):
        import tkinter as tk
        path = Path(__file__).resolve().parents[1] / 'packaging/appimage/launcher.py'
        spec = importlib.util.spec_from_file_location('launcher', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        root = tk.Tk()
        self.addCleanup(root.destroy)
        app = module.Launcher(root)
        root.update()
        self.assertEqual(str(app.build.cget('state')), 'normal')
        self.assertGreaterEqual(root.winfo_width(), 640)
        app.events.put('Error: Unsupported Fracture release.\n')
        app.events.put(1)
        app.poll()
        self.assertIn('Unsupported Fracture release', app.log.get('1.0', 'end'))
        self.assertIn('Stopped', app.status.get())
