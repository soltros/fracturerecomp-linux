#!/usr/bin/env python3
"""Small desktop wizard; all long-running work happens in a separate process."""
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

HERE = Path(__file__).resolve().parent


class Launcher:
    def __init__(self, root):
        self.root = root
        self.process = None
        self.events = queue.Queue()
        root.title('Fracture Recomp — Build & Play')
        root.geometry('820x580')
        root.minsize(640, 460)
        frame = ttk.Frame(root, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Fracture Recomp', font=('', 24, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Build once with your own game files, then play on Linux.',
                  wraplength=740).pack(anchor='w', pady=(4, 16))
        ttk.Label(frame, text='1. Choose your Xbox 360 ISO or extracted folder (default.xex + resources/).',
                  wraplength=740).pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=8)
        self.path = tk.StringVar()
        ttk.Entry(row, textvariable=self.path).pack(side='left', fill='x', expand=True)
        self.iso = ttk.Button(row, text='Choose ISO…', command=self.pick_iso)
        self.iso.pack(side='left', padx=5)
        self.folder = ttk.Button(row, text='Choose folder…', command=self.pick_folder)
        self.folder.pack(side='left')
        ttk.Label(frame, text='2. Build the game. The compiler and SDK are included; no downloads are needed.',
                  wraplength=740).pack(anchor='w', pady=(8, 4))
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=6)
        self.build = ttk.Button(buttons, text='Build game', command=self.start_build)
        self.build.pack(side='left')
        self.play = ttk.Button(buttons, text='Play', command=self.start_play)
        self.play.pack(side='left', padx=8)
        self.cancel = ttk.Button(buttons, text='Cancel', command=self.stop, state='disabled')
        self.cancel.pack(side='right')
        self.status = tk.StringVar(value='Ready. Your original game files will only be read.')
        ttk.Label(frame, textvariable=self.status, wraplength=740).pack(anchor='w', pady=6)
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.pack(fill='x', pady=(0, 8))
        self.log = scrolledtext.ScrolledText(frame, height=14, state='disabled', wrap='word')
        self.log.pack(fill='both', expand=True)
        ttk.Label(frame, text='Build logs and game settings are saved in your Fracture Builder data folder.',
                  wraplength=740).pack(anchor='w', pady=(10, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)
        self.refresh()

    def refresh(self):
        busy = self.process is not None
        for widget in (self.build, self.iso, self.folder):
            widget.configure(state='disabled' if busy else 'normal')
        self.play.configure(state='normal' if not busy and Path('/work/last-build.json').is_file() else 'disabled')
        self.cancel.configure(state='normal' if busy else 'disabled')

    def pick_iso(self):
        path = filedialog.askopenfilename(title='Choose your Fracture disc image',
                                          filetypes=[('Xbox 360 ISO', '*.iso'), ('All files', '*')])
        if path:
            self.path.set(path)

    def pick_folder(self):
        path = filedialog.askdirectory(title='Choose the folder with default.xex and resources/')
        if path:
            self.path.set(path)

    def start_build(self):
        if not self.path.get().strip():
            messagebox.showinfo('Choose your game files', 'Select an ISO or extracted game folder first.')
            return
        self.start(['--build', self.path.get()], 'Building your game… This can take several minutes.')

    def start_play(self):
        self.start(['--play'], 'Game running. Close the game to return here.')

    def start(self, args, status):
        try:
            self.process = subprocess.Popen([sys.executable, '-u', str(HERE / 'builder.py'), *args],
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, errors='replace', start_new_session=True)
        except OSError as error:
            messagebox.showerror('Could not start', str(error))
            return
        self.status.set(status)
        self.progress.start()
        self.refresh()
        threading.Thread(target=self.read_output, args=(self.process,), daemon=True).start()

    def read_output(self, process):
        with Path('/work/builder.log').open('a') as log:
            for line in process.stdout:
                log.write(line)
                log.flush()
                self.events.put(line)
        self.events.put(process.wait())

    def poll(self):
        # Bound work per tick so compiler output cannot starve the event loop.
        for _ in range(200):
            try:
                item = self.events.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, int):
                self.process = None
                self.progress.stop()
                self.status.set('Ready to play.' if item == 0 else 'Stopped. See the log below for details; you can try again.')
                self.refresh()
            else:
                self.log.configure(state='normal')
                self.log.insert('end', item)
                # Keep the GUI responsive even for a full compiler build.
                if int(self.log.index('end-1c').split('.')[0]) > 2500:
                    self.log.delete('1.0', '500.0')
                self.log.see('end')
                self.log.configure(state='disabled')
        self.root.after(100, self.poll)

    def stop(self):
        if self.process:
            pid = self.process.pid
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            self.root.after(3000, lambda: self.force_stop(pid))

    def force_stop(self, pid):
        if self.process and self.process.pid == pid and self.process.poll() is None:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def close(self):
        if self.process:
            if not messagebox.askyesno('Stop current task?', 'Stop the build or game and close Fracture Builder?'):
                return
            self.stop()
            self.root.after(3200, self.root.destroy)
        else:
            self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    Launcher(root)
    root.mainloop()
