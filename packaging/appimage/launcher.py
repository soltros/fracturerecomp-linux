#!/usr/bin/env python3
"""Small desktop wizard; all long-running work happens in a separate process."""
import json
import os
import re
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = Path(__file__).resolve().parent


# Keep the visual system local so the same interface ships on every desktop.
COLORS = {
    'bg': '#10171e', 'card': '#19232d', 'border': '#2a3845',
    'field': '#111b24', 'text': '#edf2f5', 'muted': '#a1afbc',
    'accent': '#f2ad62', 'hover': '#ffc584', 'ink': '#17212b',
    'green': '#8bd5bd', 'error': '#f1a2a9',
}
FONT = 'DejaVu Sans'


class BuildProgress(tk.Canvas):
    """A thin progress track that stays legible at every Tk theme and DPI."""
    def __init__(self, parent):
        self.mode = 'determinate'
        self.maximum = 100
        self.value = 0
        self.pulse = 0
        self.timer = None
        super().__init__(parent, height=6, bg=COLORS['field'], highlightthickness=0, borderwidth=0)
        self.bind('<Configure>', lambda _: self.draw())

    def configure(self, cnf=None, **kwargs):
        for key in ('mode', 'maximum', 'value'):
            if key in kwargs:
                setattr(self, key, kwargs.pop(key))
        if cnf is not None or kwargs:
            super().configure(cnf, **kwargs)
        self.draw()

    def __getitem__(self, key):
        if key in ('mode', 'maximum', 'value'):
            return getattr(self, key)
        return super().__getitem__(key)

    def draw(self):
        self.delete('fill')
        width, height = self.winfo_width(), self.winfo_height()
        if self.mode == 'indeterminate':
            length = max(30, width // 5)
            left = self.pulse % (width + length) - length
            right = left + length
        else:
            left, right = 0, width * min(1, max(0, self.value / max(1, self.maximum)))
        self.create_rectangle(left, 0, right, height, fill=COLORS['accent'], outline='', tags='fill')

    def start(self):
        self.stop()
        self.animate()

    def animate(self):
        self.pulse += 8
        self.draw()
        self.timer = self.after(25, self.animate)

    def stop(self):
        if self.timer is not None:
            self.after_cancel(self.timer)
            self.timer = None

    def destroy(self):
        self.stop()
        super().destroy()


class Launcher:
    def __init__(self, root, state_dir=Path('/work')):
        self.root = root
        self.state_dir = Path(state_dir)
        self.process = None
        self.operation = None
        self.cancelled = False
        self.last_error = ''
        self.details_visible = False
        self.events = queue.Queue()
        self.wrap_labels = []
        root.title('Fracture Recomp — Build & Play')
        root.geometry('940x740')
        root.minsize(780, 710)
        root.configure(background=COLORS['bg'])
        try:
            self.icon = tk.PhotoImage(file=str(HERE / 'fracture-builder.png'))
            root.iconphoto(True, self.icon)
        except tk.TclError:
            pass
        self.configure_styles()
        shell = ttk.Frame(root, padding=(32, 20, 32, 16))
        shell.pack(fill='both', expand=True)

        header = ttk.Frame(shell)
        header.pack(fill='x')
        mark = tk.Canvas(header, width=38, height=38, bg=COLORS['bg'], highlightthickness=0)
        mark.pack(side='left', padx=(0, 12))
        mark.create_polygon(5, 3, 34, 3, 29, 12, 15, 12, 15, 19, 27, 19,
                            23, 27, 15, 27, 15, 36, 5, 36, fill=COLORS['accent'], outline='')
        ttk.Label(header, text='FRACTURE  /  RECOMP', style='Brand.TLabel').pack(side='left')
        tk.Label(header, text='  ●  OFFLINE BUILDER  ', font=(FONT, 9, 'bold'),
                 fg=COLORS['green'], bg='#1b302e', padx=10, pady=7).pack(side='right')
        ttk.Separator(shell).pack(fill='x', pady=(14, 16))
        ttk.Label(shell, text='Build once. Play anytime.', style='Hero.TLabel').pack(anchor='w')
        self.label(shell, 'Bring your copy of Fracture. The tools are already here.',
                   'Muted.TLabel').pack(anchor='w', pady=(6, 18))

        source = self.card(shell)
        self.label(source, '01  /  GAME FILES', 'Eyebrow.TLabel').pack(anchor='w')
        self.label(source, 'Start with your copy', 'CardTitle.TLabel').pack(anchor='w', pady=(7, 4))
        self.label(source, 'Choose an Xbox 360 ISO, or a folder containing default.xex and resources/.',
                   'CardMuted.TLabel', wrap=True).pack(anchor='w', pady=(0, 10))
        self.path = tk.StringVar()
        self.entry = ttk.Entry(source, textvariable=self.path, style='Path.TEntry', font=(FONT, 10))
        self.entry.pack(fill='x', ipady=1)
        choices = ttk.Frame(source, style='Card.TFrame')
        choices.pack(fill='x', pady=(10, 0))
        self.iso = ttk.Button(choices, text='Choose ISO…', command=self.pick_iso, style='Secondary.TButton')
        self.iso.pack(side='left')
        self.folder = ttk.Button(choices, text='Choose folder…', command=self.pick_folder, style='Secondary.TButton')
        self.folder.pack(side='left', padx=(9, 0))
        self.source_note = tk.StringVar(value='Your original files stay untouched.')
        ttk.Label(choices, textvariable=self.source_note, style='CardMuted.TLabel').pack(side='right')

        action = self.card(shell, pady=(14, 0))
        self.label(action, '02  /  BUILD & PLAY', 'Eyebrow.TLabel').pack(anchor='w')
        self.phase = tk.StringVar(value='Ready when you are')
        ttk.Label(action, textvariable=self.phase, style='CardTitle.TLabel').pack(anchor='w', pady=(7, 4))
        self.status = tk.StringVar(value='Select your game files to get started. No downloads or extra tools needed.')
        status_label = ttk.Label(action, textvariable=self.status, style='CardMuted.TLabel', wraplength=800)
        status_label.pack(anchor='w')
        self.wrap_labels.append(status_label)
        progress_track = tk.Frame(action, background=COLORS['field'], height=6)
        progress_track.pack(fill='x', pady=(14, 6))
        progress_track.pack_propagate(False)
        self.progress = BuildProgress(progress_track)
        self.progress.pack(fill='both', expand=True)
        self.progress_note = tk.StringVar(value='Everything is built locally on your computer.')
        ttk.Label(action, textvariable=self.progress_note, style='Small.TLabel').pack(anchor='w')
        buttons = ttk.Frame(action, style='Card.TFrame')
        buttons.pack(fill='x', pady=(12, 0))
        buttons.columnconfigure(3, weight=1)
        self.build = ttk.Button(buttons, text='Build game', command=self.start_build, style='Primary.TButton')
        self.build.grid(row=0, column=0, sticky='w')
        self.play = ttk.Button(buttons, text='▶  Play', command=self.start_play, style='Play.TButton')
        self.play.grid(row=0, column=1, padx=(10, 0))
        self.cancel = ttk.Button(buttons, text='Cancel', command=self.stop, style='Secondary.TButton')
        self.cancel.grid(row=0, column=2, padx=(10, 0))
        self.details_button = ttk.Button(buttons, text='Show build details', command=self.toggle_details, style='Quiet.TButton')
        self.details_button.grid(row=0, column=4, sticky='e')

        self.details = ttk.Frame(shell, style='Card.TFrame', padding=14)
        detail_header = ttk.Frame(self.details, style='Card.TFrame')
        detail_header.pack(fill='x', pady=(0, 9))
        ttk.Label(detail_header, text='BUILD DETAILS', style='Eyebrow.TLabel').pack(side='left')
        ttk.Button(detail_header, text='Copy log', command=self.copy_log, style='Quiet.TButton').pack(side='right')
        log_frame = ttk.Frame(self.details, style='Card.TFrame')
        log_frame.pack(fill='both', expand=True)
        self.log = tk.Text(log_frame, height=9, state='disabled', wrap='word',
                           bg=COLORS['field'], fg=COLORS['muted'], insertbackground=COLORS['text'],
                           selectbackground='#364958', relief='flat', borderwidth=0,
                           padx=12, pady=10, font=('DejaVu Sans Mono', 9), highlightthickness=0)
        self.log.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side='right', fill='y')
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.tag_configure('error', foreground=COLORS['error'])
        self.log.tag_configure('command', foreground=COLORS['green'])
        footer = ttk.Frame(shell)
        footer.pack(side='bottom', fill='x', pady=(14, 0), before=header)
        ttk.Label(footer, text='LINUX  /  VULKAN', style='Footer.TLabel').pack(side='left')
        ttk.Label(footer, text='Your assets. Your machine.', style='Footer.TLabel').pack(side='right')
        self.path.trace_add('write', lambda *_: self.refresh())
        try:
            previous = json.loads((self.state_dir / 'last-build.json').read_text())
            self.path.set(previous['game'])
        except (OSError, ValueError, KeyError):
            pass
        if self.has_build():
            self.phase.set('Your game is ready')
            self.status.set('Launch Fracture from Games, or press Play here.' if self.has_shortcut()
                            else 'Press Play to jump back in, or choose files to build again.')
            self.progress.configure(value=100)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Configure>', self.resize)
        root.after(100, self.poll)
        self.refresh()

    def configure_styles(self):
        c = COLORS
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', font=(FONT, 10), background=c['bg'], foreground=c['text'])
        style.configure('TFrame', background=c['bg'])
        style.configure('TLabel', background=c['bg'], foreground=c['text'])
        style.configure('TSeparator', background=c['border'])
        style.configure('Card.TFrame', background=c['card'])
        for name, size, color, background, weight in (
            ('Brand', 11, c['text'], c['bg'], 'bold'),
            ('Hero', 26, c['text'], c['bg'], 'bold'),
            ('Muted', 11, c['muted'], c['bg'], 'normal'),
            ('CardTitle', 16, c['text'], c['card'], 'bold'),
            ('CardMuted', 10, c['muted'], c['card'], 'normal'),
            ('Eyebrow', 9, c['accent'], c['card'], 'bold'),
            ('Small', 9, c['muted'], c['card'], 'normal'),
            ('Footer', 9, c['muted'], c['bg'], 'normal'),
        ):
            style.configure(name + '.TLabel', font=(FONT, size, weight), foreground=color, background=background)
        for name, background, foreground, hover in (
            ('Primary', c['accent'], c['ink'], c['hover']),
            ('Secondary', '#2a3946', c['text'], '#354958'),
            ('Play', '#285246', '#d0f3e5', '#356b59'),
            ('Quiet', c['card'], c['muted'], '#243440'),
        ):
            key = name + '.TButton'
            style.configure(key, background=background, foreground=foreground,
                            font=(FONT, 10, 'bold' if name in ('Primary', 'Play') else 'normal'),
                            padding=(16, 9) if name != 'Quiet' else (8, 8),
                            borderwidth=0, relief='flat', anchor='center',
                            focusthickness=2, focuscolor=c['accent'])
            style.map(key, background=[('disabled', '#24303b'), ('active', hover)],
                      foreground=[('disabled', '#6f818f')],
                      bordercolor=[('focus', c['accent']), ('!focus', background)],
                      lightcolor=[('!focus', background)], darkcolor=[('!focus', background)])
        style.configure('Path.TEntry', fieldbackground=c['field'], foreground=c['text'],
                        insertcolor=c['accent'], padding=8, bordercolor=c['border'],
                        lightcolor=c['border'], darkcolor=c['border'])
        style.map('Path.TEntry', bordercolor=[('focus', c['accent'])],
                  fieldbackground=[('disabled', c['card'])], foreground=[('disabled', c['muted'])])
        style.configure('Vertical.TScrollbar', troughcolor=c['field'], background=c['border'],
                        borderwidth=0, arrowcolor=c['muted'], bordercolor=c['field'],
                        lightcolor=c['border'], darkcolor=c['border'])

    def label(self, parent, text, style, wrap=False):
        label = ttk.Label(parent, text=text, style=style, wraplength=800 if wrap else 0)
        if wrap:
            self.wrap_labels.append(label)
        return label

    def card(self, parent, pady=0):
        border = tk.Frame(parent, background=COLORS['border'], padx=1, pady=1)
        border.pack(fill='x', pady=pady)
        frame = ttk.Frame(border, style='Card.TFrame', padding=(22, 16))
        frame.pack(fill='both', expand=True)
        return frame

    def resize(self, event):
        if event.widget is self.root:
            for label in self.wrap_labels:
                label.configure(wraplength=max(400, event.width - 112))

    def has_build(self):
        return (self.state_dir / 'last-build.json').is_file()

    def has_shortcut(self):
        try:
            return bool(json.loads((self.state_dir / 'last-build.json').read_text()).get('shortcut'))
        except (OSError, ValueError):
            return False

    def refresh(self):
        busy = self.process is not None
        self.build.configure(state='normal' if not busy and self.path.get().strip() else 'disabled',
                             text='Building…' if busy and self.operation == 'build' else 'Build game')
        for widget in (self.iso, self.folder, self.entry):
            widget.configure(state='disabled' if busy else 'normal')
        self.play.configure(state='normal' if not busy and self.has_build() else 'disabled',
                            text='Playing…' if busy and self.operation == 'play' else '▶  Play')
        if busy:
            self.cancel.grid()
        else:
            self.cancel.grid_remove()
        self.source_note.set('Files selected' if self.path.get().strip() else 'Your original files stay untouched.')

    def toggle_details(self):
        self.show_details(not self.details_visible)

    def show_details(self, visible):
        if visible == self.details_visible:
            return
        self.details_visible = visible
        self.details_button.configure(text='Hide build details' if visible else 'Show build details')
        if visible:
            self.details.pack(fill='both', expand=True, pady=(14, 0))
            self.previous_height = self.root.winfo_height()
            self.expanded_height = min(self.previous_height + 200, self.root.winfo_screenheight() - 65)
            self.root.geometry(f'{self.root.winfo_width()}x{max(self.previous_height, self.expanded_height)}')
        else:
            self.details.pack_forget()
            if self.root.winfo_height() == self.expanded_height:
                self.root.geometry(f'{self.root.winfo_width()}x{self.previous_height}')

    def copy_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log.get('1.0', 'end-1c'))

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
        self.start(['--build', self.path.get()], 'This can take several minutes. You can follow the build below.')

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
        self.operation = 'play' if args == ['--play'] else 'build'
        self.cancelled = False
        self.last_error = ''
        self.phase.set('Enjoy the game' if self.operation == 'play' else 'Checking your game files')
        self.status.set(status)
        self.progress.configure(mode='indeterminate', value=0)
        self.progress_note.set('Game running' if self.operation == 'play' else 'Preparing your local build…')
        self.progress.start()
        self.refresh()
        threading.Thread(target=self.read_output, args=(self.process,), daemon=True).start()

    def read_output(self, process):
        with (self.state_dir / 'builder.log').open('a') as log:
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
                if self.cancelled:
                    self.phase.set('Build cancelled' if self.operation == 'build' else 'Game stopped')
                    self.status.set('Your files are safe. Start again whenever you’re ready.')
                    self.progress_note.set('Stopped by you')
                elif item == 0:
                    self.phase.set('Your game is ready' if self.operation == 'build' else 'Welcome back')
                    if self.has_shortcut():
                        self.status.set('Launch Fracture from Games, or press Play here.')
                    else:
                        self.status.set('Press Play to start Fracture.' if self.operation == 'build' else 'Press Play whenever you want to jump back in.')
                    self.progress_note.set('Build complete' if self.operation == 'build' else 'Game closed')
                    self.progress.configure(mode='determinate', maximum=100, value=100)
                else:
                    self.phase.set('Build needs attention')
                    self.status.set(self.last_error or 'The task stopped. Check the details below, then try again.')
                    self.progress_note.set('Build stopped' if self.operation == 'build' else 'Game stopped')
                    self.show_details(True)
                self.refresh()
            else:
                self.log.configure(state='normal')
                self.update_phase(item)
                tag = 'error' if 'error' in item.lower() else 'command' if item.startswith('+ ') else ''
                self.log.insert('end', item, tag)
                # Keep the GUI responsive even for a full compiler build.
                if int(self.log.index('end-1c').split('.')[0]) > 2500:
                    self.log.delete('1.0', '500.0')
                self.log.see('end')
                self.log.configure(state='disabled')
        self.root.after(100, self.poll)

    def update_phase(self, line):
        if line.startswith('Error:'):
            self.last_error = line.removeprefix('Error:').strip()
        extraction = re.match(r'Extracting (\d+)/(\d+):', line)
        compilation = re.match(r'\[(\d+)/(\d+)\]', line)
        if extraction or compilation:
            current, total = map(int, (extraction or compilation).groups())
            self.progress.stop()
            self.progress.configure(mode='determinate', maximum=max(1, total), value=current)
            if extraction:
                self.phase.set('Extracting your game files')
                self.progress_note.set(f'{current:,} of {total:,} files')
            else:
                self.progress_note.set(f'{current:,} of {total:,} build tasks')
        if line.startswith('+ cmake'):
            self.progress.stop()
            self.progress.configure(mode='indeterminate', value=0)
            self.progress.start()
            if 'fracture_codegen' in line:
                self.phase.set('Recompiling the game code')
            elif '--build' in line:
                self.phase.set('Building your Linux game')
            else:
                self.phase.set('Preparing the build')
            self.progress_note.set('Working locally — no downloads needed')

    def stop(self):
        if self.process:
            self.cancelled = True
            self.status.set('Stopping safely…')
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
