import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('DISPLAY') and os.environ.get('CI'), 'GUI tests run under Xvfb in CI')
class LauncherTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        path = Path(__file__).resolve().parents[1] / 'packaging/appimage/launcher.py'
        spec = importlib.util.spec_from_file_location('launcher', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.app = module.Launcher(self.root, state_dir=Path(self.temporary.name))
        self.root.update()

    def snapshot(self, name):
        from PIL import ImageGrab
        self.root.update()
        destination = Path('out/previews')
        destination.mkdir(parents=True, exist_ok=True)
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x + self.root.winfo_width(), y + self.root.winfo_height())).save(destination / name)

    def test_selection_and_failure_feedback(self):
        app = self.app
        self.snapshot('launcher-ready.png')
        self.assertEqual(str(app.build.cget('state')), 'disabled')
        self.assertFalse(app.details_visible)
        app.path.set('/home/player/Games/Fracture')
        self.assertEqual(str(app.build.cget('state')), 'normal')
        app.operation = 'build'
        app.events.put('Error: Unsupported Fracture release.\n')
        app.events.put(1)
        app.poll()
        self.snapshot('launcher-error.png')
        self.assertIn('Unsupported Fracture release', app.log.get('1.0', 'end'))
        self.assertIn('Unsupported Fracture release', app.status.get())
        self.assertTrue(app.details_visible)

    def test_progress_and_compact_layout(self):
        app = self.app
        app.path.set('/home/player/Games/Fracture.iso')
        app.operation = 'build'
        app.process = object()
        app.refresh()
        app.status.set('This can take several minutes. Everything is happening on your computer.')
        app.update_phase('+ cmake --build /work/output --parallel 4\n')
        app.update_phase('[42/180] Building CXX object fracture.cpp.o\n')
        self.snapshot('launcher-building.png')
        self.assertEqual(app.progress['value'], 42)
        self.assertIn('42', app.progress_note.get())
        self.assertEqual(str(app.entry.cget('state')), 'disabled')
        self.root.geometry('780x710')
        self.root.update()
        self.snapshot('launcher-compact.png')
        # Check ancestor bounds too: a button can be inside the window while
        # still being clipped by its card at the minimum window size.
        for widget in (app.build, app.play, app.cancel, app.details_button):
            bottom = widget.winfo_rooty() + widget.winfo_height()
            parent = widget.master
            while parent is not None:
                self.assertLessEqual(bottom, parent.winfo_rooty() + parent.winfo_height())
                parent = parent.master
        app.process = None
