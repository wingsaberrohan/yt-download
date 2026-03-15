"""
Modern CustomTkinter GUI: progress bars, cancel, paste, open folder,
audio format selection, dark/light toggle, and download speed display.
"""
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from queue import Empty

import customtkinter as ctk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from downloader import (
    start_download, retry_failed,
    FORMAT_AUDIO, FORMAT_MP4, MP4_QUALITIES, AUDIO_FORMATS,
    PlaylistResult, TrackInfo,
    MSG_PLAYLIST_INFO, MSG_TRACK_START, MSG_TRACK_PROGRESS,
    MSG_TRACK_PERCENT, MSG_TRACK_DONE, MSG_TRACK_FAILED,
    MSG_LOG, MSG_FINISHED,
    DEFAULT_WORKERS, MAX_WORKERS,
)


def is_youtube_url(text: str) -> bool:
    if not text or not text.strip():
        return False
    return bool(
        re.match(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/", text.strip(), re.I)
    )


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("YouTube Downloader")
        self.geometry("780x660")
        self.minsize(680, 580)

        icon_path = self._resolve_icon()
        if icon_path:
            self.iconbitmap(icon_path)

        self._msg_queue = None
        self._poll_id = None
        self._cancel_event = None
        self._playlist_result: PlaylistResult = None
        self._running = False

        self._build_ui()

    @staticmethod
    def _resolve_icon():
        if getattr(sys, "frozen", False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ico = os.path.join(base, "icon.ico")
        return ico if os.path.isfile(ico) else None

    def _build_ui(self):
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=15, pady=(10, 0))

        ctk.CTkLabel(
            top_bar, text="YouTube Downloader",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left")

        self.theme_switch = ctk.CTkSwitch(
            top_bar, text="Dark Mode", command=self._toggle_theme,
            font=ctk.CTkFont(size=12),
        )
        self.theme_switch.pack(side="right")
        self.theme_switch.select()

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=15, pady=10)

        # URL
        ctk.CTkLabel(main, text="YouTube URL (video or playlist):",
                     font=ctk.CTkFont(size=13)).pack(anchor="w")
        url_frame = ctk.CTkFrame(main, fg_color="transparent")
        url_frame.pack(fill="x", pady=(2, 8))
        self.url_var = tk.StringVar()
        self.url_entry = ctk.CTkEntry(
            url_frame, textvariable=self.url_var,
            placeholder_text="https://www.youtube.com/watch?v=...", height=36,
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(url_frame, text="Paste", width=70, height=36,
                       command=self._paste_url).pack(side="left")

        # Format
        fmt_frame = ctk.CTkFrame(main, fg_color="transparent")
        fmt_frame.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(fmt_frame, text="Format:",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 10))
        self.format_var = tk.StringVar(value=FORMAT_AUDIO)
        ctk.CTkRadioButton(
            fmt_frame, text="Audio", variable=self.format_var,
            value=FORMAT_AUDIO, command=self._on_format_change,
        ).pack(side="left", padx=(0, 12))
        ctk.CTkRadioButton(
            fmt_frame, text="Video (MP4)", variable=self.format_var,
            value=FORMAT_MP4, command=self._on_format_change,
        ).pack(side="left")

        # Audio format / Video quality (in separate sub-frames for clean toggle)
        self.options_container = ctk.CTkFrame(main, fg_color="transparent")
        self.options_container.pack(fill="x", pady=(0, 6))

        self.audio_options = ctk.CTkFrame(self.options_container, fg_color="transparent")
        ctk.CTkLabel(self.audio_options, text="Audio format:",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))
        self.audio_fmt_var = tk.StringVar(value=AUDIO_FORMATS[0][0])
        ctk.CTkComboBox(
            self.audio_options, variable=self.audio_fmt_var,
            values=[a[0] for a in AUDIO_FORMATS], state="readonly", width=200,
        ).pack(side="left")

        self.video_options = ctk.CTkFrame(self.options_container, fg_color="transparent")
        ctk.CTkLabel(self.video_options, text="Video quality:",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))
        self.quality_var = tk.StringVar(value=MP4_QUALITIES[0][0])
        ctk.CTkComboBox(
            self.video_options, variable=self.quality_var,
            values=[q[0] for q in MP4_QUALITIES], state="readonly", width=200,
        ).pack(side="left")

        self._on_format_change()

        # Output folder
        ctk.CTkLabel(main, text="Output folder:",
                     font=ctk.CTkFont(size=13)).pack(anchor="w")
        out_frame = ctk.CTkFrame(main, fg_color="transparent")
        out_frame.pack(fill="x", pady=(2, 6))
        self.out_var = tk.StringVar(value=os.path.abspath("downloads"))
        ctk.CTkEntry(out_frame, textvariable=self.out_var, height=36).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(out_frame, text="Browse", width=80, height=36,
                       command=self._browse_output).pack(side="left")

        # Parallel workers
        parallel_frame = ctk.CTkFrame(main, fg_color="transparent")
        parallel_frame.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(parallel_frame, text="Parallel downloads:",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))
        self.workers_var = tk.StringVar(value=str(DEFAULT_WORKERS))
        ctk.CTkOptionMenu(
            parallel_frame, variable=self.workers_var,
            values=[str(i) for i in range(1, MAX_WORKERS + 1)], width=60,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(parallel_frame, text=f"(1 = sequential, up to {MAX_WORKERS})",
                     text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left")

        # Buttons
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(4, 6))
        self.download_btn = ctk.CTkButton(
            btn_frame, text="Download", width=120, height=36,
            command=self._start_download,
            fg_color="#2563eb", hover_color="#1d4ed8",
        )
        self.download_btn.pack(side="left", padx=(0, 8))
        self.cancel_btn = ctk.CTkButton(
            btn_frame, text="Cancel", width=100, height=36,
            command=self._cancel_download, state="disabled",
            fg_color="#dc2626", hover_color="#b91c1c",
        )
        self.cancel_btn.pack(side="left", padx=(0, 8))
        self.retry_btn = ctk.CTkButton(
            btn_frame, text="Retry Failed", width=110, height=36,
            command=self._retry_failed, state="disabled",
            fg_color="#d97706", hover_color="#b45309",
        )
        self.retry_btn.pack(side="left", padx=(0, 8))
        self.open_folder_btn = ctk.CTkButton(
            btn_frame, text="Open Folder", width=110, height=36,
            command=self._open_folder, state="disabled",
            fg_color="#059669", hover_color="#047857",
        )
        self.open_folder_btn.pack(side="left")

        # Stats + speed
        stats_frame = ctk.CTkFrame(main, fg_color="transparent")
        stats_frame.pack(fill="x", pady=(2, 2))
        self.stats_var = tk.StringVar(value="")
        ctk.CTkLabel(stats_frame, textvariable=self.stats_var,
                     font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.speed_var = tk.StringVar(value="")
        ctk.CTkLabel(stats_frame, textvariable=self.speed_var,
                     font=ctk.CTkFont(size=12),
                     text_color="#60a5fa").pack(side="right")

        # Overall progress bar
        self.overall_progress = ctk.CTkProgressBar(main, height=8)
        self.overall_progress.pack(fill="x", pady=(2, 2))
        self.overall_progress.set(0)

        # Per-track progress bar
        self.track_progress = ctk.CTkProgressBar(main, height=6)
        self.track_progress.pack(fill="x", pady=(0, 4))
        self.track_progress.set(0)

        # Tabs: Progress + Summary
        self.tabview = ctk.CTkTabview(main)
        self.tabview.pack(fill="both", expand=True)
        self.tabview.add("Progress")
        self.tabview.add("Summary")

        self.log_text = ctk.CTkTextbox(
            self.tabview.tab("Progress"), state="disabled",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log_text.pack(fill="both", expand=True)

        self.summary_text = ctk.CTkTextbox(
            self.tabview.tab("Summary"), state="disabled",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.summary_text.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ helpers
    def _toggle_theme(self):
        ctk.set_appearance_mode("dark" if self.theme_switch.get() else "light")

    def _on_format_change(self):
        if self.format_var.get() == FORMAT_AUDIO:
            self.video_options.pack_forget()
            self.audio_options.pack(fill="x")
        else:
            self.audio_options.pack_forget()
            self.video_options.pack(fill="x")

    def _paste_url(self):
        try:
            text = self.clipboard_get()
            if text:
                self.url_var.set(text.strip())
        except Exception:
            pass

    def _browse_output(self):
        path = filedialog.askdirectory(
            title="Select output folder", initialdir=self.out_var.get())
        if path:
            self.out_var.set(path)

    def _open_folder(self):
        folder = self.out_var.get().strip()
        if folder and os.path.isdir(folder):
            os.startfile(folder)

    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _update_stats(self):
        r = self._playlist_result
        if not r:
            self.stats_var.set("")
            self.overall_progress.set(0)
            return
        self.stats_var.set(
            f"Total: {r.total}  |  Done: {r.done_count}  |  "
            f"Failed: {r.failed_count}  |  "
            f"Remaining: {r.total - r.done_count - r.failed_count}"
        )
        if r.total > 0:
            self.overall_progress.set(
                (r.done_count + r.failed_count) / r.total)

    # ------------------------------------------------------------------ download
    def _start_download(self):
        url = self.url_var.get().strip()
        if not is_youtube_url(url):
            messagebox.showerror(
                "Invalid URL",
                "Please enter a valid YouTube video or playlist URL.")
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
        self.speed_var.set("")
        self.overall_progress.set(0)
        self.track_progress.set(0)
        self._playlist_result = None
        self._set_running(True)
        self.tabview.set("Progress")

        self._cancel_event = threading.Event()

        self._msg_queue, self._cancel_event = start_download(
            url=url,
            output_dir=out_dir,
            format_type=self.format_var.get(),
            quality_name=self.quality_var.get(),
            max_workers=int(self.workers_var.get()),
            cancel_event=self._cancel_event,
            audio_format_name=self.audio_fmt_var.get(),
        )
        self._poll_queue()

    def _cancel_download(self):
        if self._cancel_event:
            self._cancel_event.set()
            self._log("Cancelling...")
            self.cancel_btn.configure(state="disabled")

    def _retry_failed(self):
        if not self._playlist_result or not self._playlist_result.failed_tracks:
            messagebox.showinfo(
                "Nothing to retry",
                "There are no failed tracks to retry.")
            return
        self._clear_log()
        self._set_running(True)
        self.tabview.set("Progress")
        self.speed_var.set("")
        self.track_progress.set(0)

        self._cancel_event = threading.Event()

        self._msg_queue, self._cancel_event = retry_failed(
            playlist_result=self._playlist_result,
            output_dir=self.out_var.get().strip(),
            format_type=self.format_var.get(),
            quality_name=self.quality_var.get(),
            max_workers=int(self.workers_var.get()),
            cancel_event=self._cancel_event,
            audio_format_name=self.audio_fmt_var.get(),
        )
        self._poll_queue()

    # ------------------------------------------------------------------ queue
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
        self._poll_id = self.after(150, self._poll_queue)

    def _handle_message(self, msg_type, payload):
        if msg_type == MSG_PLAYLIST_INFO:
            self._playlist_result = payload
            self._update_stats()

        elif msg_type == MSG_TRACK_START:
            track: TrackInfo = payload
            r = self._playlist_result
            total = r.total if r else "?"
            self._log(f"[{track.index}/{total}] Downloading: {track.title}")
            self.track_progress.set(0)
            self._update_stats()

        elif msg_type == MSG_TRACK_PROGRESS:
            self._log(payload)

        elif msg_type == MSG_TRACK_PERCENT:
            _idx, pct_float, speed_str = payload
            self.track_progress.set(pct_float)
            if speed_str:
                self.speed_var.set(f"Speed: {speed_str}")

        elif msg_type == MSG_TRACK_DONE:
            track: TrackInfo = payload
            self._log(f"[OK] {track.title}")
            self.track_progress.set(1.0)
            self._update_stats()

        elif msg_type == MSG_TRACK_FAILED:
            track: TrackInfo = payload
            self._log(f"[FAILED] {track.title} - {track.error}")
            self.track_progress.set(0)
            self._update_stats()

        elif msg_type == MSG_LOG:
            self._log(payload)

        elif msg_type == MSG_FINISHED:
            self._playlist_result = payload
            self._on_download_finished()

    def _on_download_finished(self):
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        self._msg_queue = None
        self._cancel_event = None
        self._set_running(False)
        self._update_stats()
        self._build_summary()
        self._log("\n--- All done ---")
        self.speed_var.set("")
        self.track_progress.set(0)
        self.tabview.set("Summary")
        self.open_folder_btn.configure(state="normal")

    def _set_running(self, running: bool):
        self._running = running
        self.download_btn.configure(state="disabled" if running else "normal")
        self.cancel_btn.configure(state="normal" if running else "disabled")
        has_failed = (
            self._playlist_result
            and self._playlist_result.failed_count > 0
        ) if not running else False
        self.retry_btn.configure(state="normal" if has_failed else "disabled")
        if running:
            self.open_folder_btn.configure(state="disabled")

    # ------------------------------------------------------------------ summary
    def _clear_summary(self):
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.configure(state="disabled")

    def _build_summary(self):
        r = self._playlist_result
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")

        if not r or not r.tracks:
            self.summary_text.insert("end", "No tracks were processed.\n")
            self.summary_text.configure(state="disabled")
            return

        self.summary_text.insert("end", f"Playlist: {r.playlist_title}\n\n")
        self.summary_text.insert(
            "end",
            f"Total: {r.total}   |   Downloaded: {r.done_count}"
            f"   |   Failed: {r.failed_count}\n\n")

        if r.done_count > 0:
            self.summary_text.insert("end", "--- Successfully downloaded ---\n")
            for t in r.tracks:
                if t.status == "done":
                    self.summary_text.insert("end", f"  {t.index}. {t.title}\n")
            self.summary_text.insert("end", "\n")

        if r.failed_count > 0:
            self.summary_text.insert("end", "--- Failed ---\n")
            for t in r.tracks:
                if t.status == "failed":
                    self.summary_text.insert("end", f"  {t.index}. {t.title}\n")
                    self.summary_text.insert("end", f"     Error: {t.error}\n")
            self.summary_text.insert("end", "\n")
            self.summary_text.insert(
                "end",
                "Click \"Retry Failed\" to re-attempt the failed tracks.\n")

        if r.failed_count == 0 and r.done_count == r.total:
            self.summary_text.insert(
                "end", "All tracks downloaded successfully!\n")

        self.summary_text.configure(state="disabled")


def run():
    app = MainWindow()
    app.mainloop()
