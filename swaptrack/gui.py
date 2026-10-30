"""Tkinter GUI for SwapTrack."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__, core
from .core import Cancelled, LengthMode, SwapError

VIDEO_TYPES = [("Video files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.flv *.wmv *.mpg *.mpeg"), ("All files", "*.*")]
AUDIO_TYPES = [("Audio files", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma *.aiff"), ("All files", "*.*")]
SAVE_TYPES = [("MP4", "*.mp4"), ("MOV", "*.mov"), ("MKV", "*.mkv"), ("WebM", "*.webm"), ("AVI", "*.avi")]

MODE_LABELS = {
    LengthMode.MATCH_VIDEO: "Match video length (trim audio, or pad with silence)",
    LengthMode.LOOP_AUDIO: "Loop audio until the video ends",
    LengthMode.SHORTEST: "Stop at whichever is shorter",
}


class App(ttk.Frame):
    def __init__(self, root: tk.Tk):
        super().__init__(root, padding=16)
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self._output_auto = True

        self.video_var = tk.StringVar()
        self.audio_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=LengthMode.MATCH_VIDEO.value)
        self.volume_var = tk.DoubleVar(value=100.0)
        self.status_var = tk.StringVar(value="Pick a video and an audio file to get started.")

        self._build()
        self.pack(fill="both", expand=True)
        self.root.after(100, self._poll)

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self._file_row(0, "Video", self.video_var, self._pick_video)
        self._file_row(1, "New audio", self.audio_var, self._pick_audio)
        self._file_row(2, "Save as", self.output_var, self._pick_output, browse_text="Choose…")

        opts = ttk.LabelFrame(self, text="Options", padding=10)
        opts.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        opts.columnconfigure(1, weight=1)

        for i, mode in enumerate(LengthMode):
            ttk.Radiobutton(opts, text=MODE_LABELS[mode], value=mode.value, variable=self.mode_var).grid(
                row=i, column=0, columnspan=3, sticky="w", pady=1
            )

        ttk.Label(opts, text="Volume").grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Scale(opts, from_=0, to=200, variable=self.volume_var, command=self._on_volume).grid(
            row=3, column=1, sticky="ew", padx=10, pady=(10, 0)
        )
        self.volume_label = ttk.Label(opts, text="100%", width=6)
        self.volume_label.grid(row=3, column=2, pady=(10, 0))

        self.progress = ttk.Progressbar(self, maximum=100)
        self.progress.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(16, 4))
        ttk.Label(self, textvariable=self.status_var, wraplength=520).grid(row=5, column=0, columnspan=3, sticky="w")

        buttons = ttk.Frame(self)
        buttons.grid(row=6, column=0, columnspan=3, sticky="e", pady=(14, 0))
        self.cancel_btn = ttk.Button(buttons, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(0, 8))
        self.start_btn = ttk.Button(buttons, text="Replace audio", command=self._start)
        self.start_btn.pack(side="left")

    def _file_row(self, row, label, var, command, browse_text="Browse…") -> None:
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(self, textvariable=var, width=52).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(self, text=browse_text, command=command).grid(row=row, column=2, pady=4)

    def _pick_video(self) -> None:
        path = filedialog.askopenfilename(title="Select a video", filetypes=VIDEO_TYPES)
        if not path:
            return
        self.video_var.set(path)
        if self._output_auto or not self.output_var.get():
            p = Path(path)
            self.output_var.set(str(p.with_name(f"{p.stem}_swapped{p.suffix}")))
            self._output_auto = True

    def _pick_audio(self) -> None:
        path = filedialog.askopenfilename(title="Select the new audio", filetypes=AUDIO_TYPES)
        if path:
            self.audio_var.set(path)

    def _pick_output(self) -> None:
        initial = Path(self.output_var.get()) if self.output_var.get() else None
        path = filedialog.asksaveasfilename(
            title="Save the new video as",
            filetypes=SAVE_TYPES,
            defaultextension=initial.suffix if initial and initial.suffix else ".mp4",
            initialdir=str(initial.parent) if initial else None,
            initialfile=initial.name if initial else None,
        )
        if path:
            self.output_var.set(path)
            self._output_auto = False

    def _on_volume(self, _value=None) -> None:
        self.volume_label.config(text=f"{round(float(self.volume_var.get()))}%")

    def _start(self) -> None:
        video = self.video_var.get().strip()
        audio = self.audio_var.get().strip()
        output = self.output_var.get().strip()
        if not video or not audio:
            messagebox.showwarning("SwapTrack", "Please choose both a video and an audio file.")
            return
        if not output:
            messagebox.showwarning("SwapTrack", "Please choose where to save the result.")
            return
        if Path(output).exists() and not messagebox.askyesno(
            "SwapTrack", f"{Path(output).name} already exists. Overwrite it?"
        ):
            return

        self.cancel_event.clear()
        self.progress["value"] = 0
        self.status_var.set("Working…")
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")

        mode = LengthMode(self.mode_var.get())
        volume = float(self.volume_var.get()) / 100.0

        def work():
            try:
                result = core.swap_audio(
                    video, audio, output, mode, volume,
                    on_progress=lambda f: self.events.put(("progress", f)),
                    cancel_event=self.cancel_event,
                )
                self.events.put(("done", str(result)))
            except Cancelled:
                self.events.put(("cancelled", None))
            except SwapError as exc:
                self.events.put(("error", str(exc)))
            except Exception as exc:
                self.events.put(("error", f"Unexpected error: {exc}"))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _cancel(self) -> None:
        self.cancel_event.set()
        self.cancel_btn.config(state="disabled")
        self.status_var.set("Cancelling…")

    def _finish(self) -> None:
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.worker = None

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    self.progress["value"] = payload * 100
                    self.status_var.set(f"Working… {payload * 100:.0f}%")
                elif kind == "done":
                    self.progress["value"] = 100
                    self.status_var.set(f"Done! Saved to {payload}")
                    self._finish()
                    messagebox.showinfo("SwapTrack", f"Saved:\n{payload}")
                elif kind == "cancelled":
                    self.progress["value"] = 0
                    self.status_var.set("Cancelled.")
                    self._finish()
                elif kind == "error":
                    self.progress["value"] = 0
                    self.status_var.set("Something went wrong.")
                    self._finish()
                    messagebox.showerror("SwapTrack", payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)


def main() -> None:
    root = tk.Tk()
    root.title(f"SwapTrack {__version__}")
    root.minsize(640, 0)
    try:
        ttk.Style().theme_use("vista" if root.tk.call("tk", "windowingsystem") == "win32" else "clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
