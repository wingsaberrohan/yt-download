"""
Main window: URL input, format (MP3/MP4), quality selector, output folder, progress log.
"""
import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Assume we're run from project root so parent is in path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from downloader import download, check_ffmpeg, FORMAT_MP3, FORMAT_MP4, MP4_QUALITIES


def is_youtube_url(text: str) -> bool:
    if not text or not text.strip():
        return False
    text = text.strip()
    return bool(
        re.match(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/", text, re.I)
    )


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("YouTube MP3 / MP4 Downloader")
        self.root.geometry("620x480")
        self.root.minsize(500, 400)

        self.download_done = False
        self.drain_queue = None
        self._poll_id = None

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # URL
        ttk.Label(main, text="YouTube URL (video or playlist):").pack(anchor=tk.W)
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(main, textvariable=self.url_var, width=70)
        url_entry.pack(fill=tk.X, pady=(0, 8))

        # Format
        fmt_frame = ttk.Frame(main)
        fmt_frame.pack(anchor=tk.W, pady=(0, 4))
        ttk.Label(fmt_frame, text="Format:").pack(side=tk.LEFT, padx=(0, 8))
        self.format_var = tk.StringVar(value=FORMAT_MP3)
        ttk.Radiobutton(
            fmt_frame, text="MP3 (320 kbps)", variable=self.format_var,
            value=FORMAT_MP3, command=self._on_format_change
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(
            fmt_frame, text="MP4 (video)", variable=self.format_var,
            value=FORMAT_MP4, command=self._on_format_change
        ).pack(side=tk.LEFT)

        # Quality (for MP4)
        qual_frame = ttk.Frame(main)
        qual_frame.pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(qual_frame, text="Video quality:").pack(side=tk.LEFT, padx=(0, 8))
        self.quality_var = tk.StringVar(value=MP4_QUALITIES[0][0])
        self.quality_combo = ttk.Combobox(
            qual_frame, textvariable=self.quality_var,
            values=[q[0] for q in MP4_QUALITIES],
            state="readonly", width=18
        )
        self.quality_combo.pack(side=tk.LEFT)
        self._on_format_change()

        # Output folder
        out_frame = ttk.Frame(main)
        out_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(out_frame, text="Output folder:").pack(anchor=tk.W)
        self.out_var = tk.StringVar(value=os.path.abspath("downloads"))
        out_entry = ttk.Entry(out_frame, textvariable=self.out_var, width=60)
        out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(out_frame, text="Browse...", command=self._browse_output).pack(side=tk.LEFT)

        # Download button
        self.download_btn = ttk.Button(main, text="Download", command=self._start_download)
        self.download_btn.pack(anchor=tk.W, pady=(8, 8))

        # Progress log
        ttk.Label(main, text="Progress:").pack(anchor=tk.W)
        log_frame = ttk.Frame(main)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD, state=tk.DISABLED)
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_format_change(self):
        is_mp4 = self.format_var.get() == FORMAT_MP4
        self.quality_combo.state(["!disabled" if is_mp4 else "disabled"])

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select output folder", initialdir=self.out_var.get())
        if path:
            self.out_var.set(path)

    def _log(self, msg: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _start_download(self):
        url = self.url_var.get().strip()
        if not is_youtube_url(url):
            messagebox.showerror("Invalid URL", "Please enter a valid YouTube video or playlist URL.")
            return

        out_dir = self.out_var.get().strip()
        if not out_dir:
            messagebox.showerror("Error", "Please choose an output folder.")
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot create output folder: {e}")
            return

        self.download_done = False
        self.download_btn.configure(state=tk.DISABLED)
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state=tk.DISABLED)

        def on_progress(msg):
            if msg is None:
                self.download_done = True
                self._on_download_finished()
                return
            self._log(msg)

        self.drain_queue = download(
            url=url,
            output_dir=out_dir,
            format_type=self.format_var.get(),
            quality_name=self.quality_var.get(),
            progress_callback=on_progress,
        )
        self._poll_drain()

    def _poll_drain(self):
        if self.download_done or self.drain_queue is None:
            return
        self.drain_queue()
        if not self.download_done:
            self._poll_id = self.root.after(200, self._poll_drain)

    def _on_download_finished(self):
        if self._poll_id:
            self.root.after_cancel(self._poll_id)
            self._poll_id = None
        self.drain_queue = None
        self.download_btn.configure(state=tk.NORMAL)
        self._log("Done.")


def run():
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
