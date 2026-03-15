"""
GUI: URL input, format/quality, download with per-track progress,
retry failed, and summary report tab.
"""
import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from queue import Empty

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from downloader import (
    start_download, retry_failed,
    FORMAT_MP3, FORMAT_MP4, MP4_QUALITIES,
    PlaylistResult, TrackInfo,
    MSG_PLAYLIST_INFO, MSG_TRACK_START, MSG_TRACK_PROGRESS,
    MSG_TRACK_DONE, MSG_TRACK_FAILED, MSG_LOG, MSG_FINISHED,
    DEFAULT_WORKERS, MAX_WORKERS,
)


def is_youtube_url(text: str) -> bool:
    if not text or not text.strip():
        return False
    return bool(
        re.match(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/", text.strip(), re.I)
    )


STATUS_ICONS = {
    "pending":     "[ ]",
    "downloading": "[~]",
    "done":        "[OK]",
    "failed":      "[X]",
}


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("YouTube MP3 / MP4 Downloader")
        self.root.geometry("720x600")
        self.root.minsize(620, 520)

        self._msg_queue = None
        self._poll_id = None
        self._playlist_result: PlaylistResult = None
        self._running = False

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # URL
        ttk.Label(main, text="YouTube URL (video or playlist):").pack(anchor=tk.W)
        self.url_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.url_var, width=80).pack(fill=tk.X, pady=(0, 8))

        # Format
        fmt_frame = ttk.Frame(main)
        fmt_frame.pack(anchor=tk.W, pady=(0, 4))
        ttk.Label(fmt_frame, text="Format:").pack(side=tk.LEFT, padx=(0, 8))
        self.format_var = tk.StringVar(value=FORMAT_MP3)
        ttk.Radiobutton(fmt_frame, text="MP3 (320 kbps)", variable=self.format_var,
                        value=FORMAT_MP3, command=self._on_format_change).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(fmt_frame, text="MP4 (video)", variable=self.format_var,
                        value=FORMAT_MP4, command=self._on_format_change).pack(side=tk.LEFT)

        # Quality
        qual_frame = ttk.Frame(main)
        qual_frame.pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(qual_frame, text="Video quality:").pack(side=tk.LEFT, padx=(0, 8))
        self.quality_var = tk.StringVar(value=MP4_QUALITIES[0][0])
        self.quality_combo = ttk.Combobox(
            qual_frame, textvariable=self.quality_var,
            values=[q[0] for q in MP4_QUALITIES], state="readonly", width=18)
        self.quality_combo.pack(side=tk.LEFT)
        self._on_format_change()

        # Output folder
        out_frame = ttk.Frame(main)
        out_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(out_frame, text="Output folder:").pack(anchor=tk.W)
        self.out_var = tk.StringVar(value=os.path.abspath("downloads"))
        ttk.Entry(out_frame, textvariable=self.out_var, width=60).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(out_frame, text="Browse...", command=self._browse_output).pack(side=tk.LEFT)

        # Parallel downloads
        parallel_frame = ttk.Frame(main)
        parallel_frame.pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(parallel_frame, text="Parallel downloads:").pack(side=tk.LEFT, padx=(0, 8))
        self.workers_var = tk.IntVar(value=DEFAULT_WORKERS)
        self.workers_spin = ttk.Spinbox(
            parallel_frame, from_=1, to=MAX_WORKERS,
            textvariable=self.workers_var, width=4, state="readonly")
        self.workers_spin.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(parallel_frame, text=f"(1 = sequential, up to {MAX_WORKERS})",
                  foreground="gray").pack(side=tk.LEFT)

        # Buttons row
        btn_frame = ttk.Frame(main)
        btn_frame.pack(anchor=tk.W, pady=(4, 4))
        self.download_btn = ttk.Button(btn_frame, text="Download", command=self._start_download)
        self.download_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.retry_btn = ttk.Button(btn_frame, text="Retry Failed", command=self._retry_failed, state=tk.DISABLED)
        self.retry_btn.pack(side=tk.LEFT)

        # Stats bar
        self.stats_var = tk.StringVar(value="")
        ttk.Label(main, textvariable=self.stats_var, font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(2, 4))

        # Notebook with Progress + Summary tabs
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Progress tab
        progress_frame = ttk.Frame(self.notebook)
        self.notebook.add(progress_frame, text="Progress")
        self.log_text = tk.Text(progress_frame, height=14, wrap=tk.WORD, state=tk.DISABLED)
        log_scroll = ttk.Scrollbar(progress_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.tag_configure("ok", foreground="green")
        self.log_text.tag_configure("fail", foreground="red")
        self.log_text.tag_configure("info", foreground="gray")

        # Summary tab
        summary_frame = ttk.Frame(self.notebook)
        self.notebook.add(summary_frame, text="Summary")
        self.summary_text = tk.Text(summary_frame, height=14, wrap=tk.WORD, state=tk.DISABLED)
        summary_scroll = ttk.Scrollbar(summary_frame, command=self.summary_text.yview)
        self.summary_text.configure(yscrollcommand=summary_scroll.set)
        self.summary_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        summary_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.summary_text.tag_configure("header", font=("Segoe UI", 11, "bold"))
        self.summary_text.tag_configure("ok", foreground="green")
        self.summary_text.tag_configure("fail", foreground="red")
        self.summary_text.tag_configure("stat", font=("Segoe UI", 10, "bold"))

    # ------------------------------------------------------------------ helpers
    def _on_format_change(self):
        self.quality_combo.state(["!disabled" if self.format_var.get() == FORMAT_MP4 else "disabled"])

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select output folder", initialdir=self.out_var.get())
        if path:
            self.out_var.set(path)

    def _log(self, msg: str, tag: str = ""):
        self.log_text.configure(state=tk.NORMAL)
        if tag:
            self.log_text.insert(tk.END, msg + "\n", tag)
        else:
            self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _update_stats(self):
        r = self._playlist_result
        if not r:
            self.stats_var.set("")
            return
        self.stats_var.set(
            f"Total: {r.total}  |  Done: {r.done_count}  |  "
            f"Failed: {r.failed_count}  |  "
            f"Remaining: {r.total - r.done_count - r.failed_count}"
        )

    # ------------------------------------------------------------------ download
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

        self._clear_log()
        self._clear_summary()
        self.stats_var.set("")
        self._playlist_result = None
        self._set_running(True)
        self.notebook.select(0)

        self._msg_queue, _ = start_download(
            url=url,
            output_dir=out_dir,
            format_type=self.format_var.get(),
            quality_name=self.quality_var.get(),
            max_workers=self.workers_var.get(),
        )
        self._poll_queue()

    def _retry_failed(self):
        if not self._playlist_result or not self._playlist_result.failed_tracks:
            messagebox.showinfo("Nothing to retry", "There are no failed tracks to retry.")
            return
        self._clear_log()
        self._set_running(True)
        self.notebook.select(0)

        self._msg_queue = retry_failed(
            playlist_result=self._playlist_result,
            output_dir=self.out_var.get().strip(),
            format_type=self.format_var.get(),
            quality_name=self.quality_var.get(),
            max_workers=self.workers_var.get(),
        )
        self._poll_queue()

    # ------------------------------------------------------------------ queue polling
    def _poll_queue(self):
        if self._msg_queue is None:
            return
        try:
            while True:
                msg_type, payload = self._msg_queue.get_nowait()
                self._handle_message(msg_type, payload)
                if msg_type == MSG_FINISHED:
                    return
        except Empty:
            pass
        self._poll_id = self.root.after(150, self._poll_queue)

    def _handle_message(self, msg_type, payload):
        if msg_type == MSG_PLAYLIST_INFO:
            self._playlist_result = payload
            self._update_stats()

        elif msg_type == MSG_TRACK_START:
            track: TrackInfo = payload
            r = self._playlist_result
            total = r.total if r else "?"
            self._log(f"[{track.index}/{total}] Downloading: {track.title}")
            self._update_stats()

        elif msg_type == MSG_TRACK_PROGRESS:
            self._log(payload, "info")

        elif msg_type == MSG_TRACK_DONE:
            track: TrackInfo = payload
            self._log(f"[OK] {track.title}", "ok")
            self._update_stats()

        elif msg_type == MSG_TRACK_FAILED:
            track: TrackInfo = payload
            self._log(f"[FAILED] {track.title} — {track.error}", "fail")
            self._update_stats()

        elif msg_type == MSG_LOG:
            self._log(payload)

        elif msg_type == MSG_FINISHED:
            self._playlist_result = payload
            self._on_download_finished()

    def _on_download_finished(self):
        if self._poll_id:
            self.root.after_cancel(self._poll_id)
            self._poll_id = None
        self._msg_queue = None
        self._set_running(False)
        self._update_stats()
        self._build_summary()
        self._log("\n--- All done ---")
        self.notebook.select(1)

    def _set_running(self, running: bool):
        self._running = running
        self.download_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        has_failed = (self._playlist_result and self._playlist_result.failed_count > 0) if not running else False
        self.retry_btn.configure(state=tk.NORMAL if has_failed else tk.DISABLED)

    # ------------------------------------------------------------------ summary
    def _clear_summary(self):
        self.summary_text.configure(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.configure(state=tk.DISABLED)

    def _build_summary(self):
        r = self._playlist_result
        self.summary_text.configure(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)

        if not r or not r.tracks:
            self.summary_text.insert(tk.END, "No tracks were processed.\n")
            self.summary_text.configure(state=tk.DISABLED)
            return

        self.summary_text.insert(tk.END, f"Playlist: {r.playlist_title}\n", "header")
        self.summary_text.insert(tk.END, "\n")

        self.summary_text.insert(tk.END,
            f"Total: {r.total}   |   Downloaded: {r.done_count}   |   Failed: {r.failed_count}\n", "stat")
        self.summary_text.insert(tk.END, "\n")

        if r.done_count > 0:
            self.summary_text.insert(tk.END, "--- Successfully downloaded ---\n", "header")
            for t in r.tracks:
                if t.status == "done":
                    self.summary_text.insert(tk.END, f"  {t.index}. {t.title}\n", "ok")
            self.summary_text.insert(tk.END, "\n")

        if r.failed_count > 0:
            self.summary_text.insert(tk.END, "--- Failed ---\n", "header")
            for t in r.tracks:
                if t.status == "failed":
                    self.summary_text.insert(tk.END, f"  {t.index}. {t.title}\n", "fail")
                    self.summary_text.insert(tk.END, f"     Error: {t.error}\n", "fail")
            self.summary_text.insert(tk.END, "\n")
            self.summary_text.insert(
                tk.END,
                "Click \"Retry Failed\" to re-attempt only the failed tracks.\n",
            )

        if r.failed_count == 0 and r.done_count == r.total:
            self.summary_text.insert(tk.END, "All tracks downloaded successfully!\n", "ok")

        self.summary_text.configure(state=tk.DISABLED)


def run():
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
