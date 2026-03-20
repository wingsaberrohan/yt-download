"""
Modern CustomTkinter GUI: progress bars, cancel, paste, open folder,
audio format selection, dark/light toggle, and download speed display.
"""
from dataclasses import dataclass

import os
import re
import sys
import tempfile
import threading
import tkinter as tk
import urllib.request
from tkinter import filedialog, messagebox
from queue import Empty

import customtkinter as ctk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from downloader import (
    start_download, retry_failed,
    FORMAT_AUDIO, FORMAT_MP4, MP4_QUALITIES, AUDIO_FORMATS,
    PlaylistResult, TrackInfo,
    MSG_PLAYLIST_INFO, MSG_TRACK_START, MSG_TRACK_PROGRESS,
    MSG_TRACK_PERCENT, MSG_TRACK_PHASE, MSG_TRACK_DONE, MSG_TRACK_FAILED,
    MSG_LOG, MSG_FINISHED,
    DEFAULT_WORKERS, MAX_WORKERS,
    get_current_version, get_latest_version, update_ytdlp,
    get_video_preview,
)
from downloader.history import add as history_add, get_all as history_get_all, clear as history_clear

try:
    from upload_to_telegram import upload_folder_to_telegram
except ImportError:
    upload_folder_to_telegram = None


def is_supported_url(text: str) -> bool:
    """Accept any http/https URL (yt-dlp supports 1800+ sites)."""
    if not text or not text.strip():
        return False
    s = text.strip()
    return s.startswith("http://") or s.startswith("https://")


def _fmt_mb_pair(downloaded: int | None, total: int | None) -> str:
    if downloaded is None:
        return ""
    if total and total > 0:
        return f"{downloaded / 1_048_576:.1f} / {total / 1_048_576:.1f} MB"
    if downloaded > 0:
        return f"{downloaded / 1_048_576:.1f} MB"
    return ""


@dataclass
class _TrackRowUI:
    """One row in the per-track downloads list."""
    frame: ctk.CTkFrame
    title_lbl: ctk.CTkLabel
    meta_lbl: ctk.CTkLabel
    status_lbl: ctk.CTkLabel
    bytes_lbl: ctk.CTkLabel
    bar: ctk.CTkProgressBar

    def set_queued(self) -> None:
        self.status_lbl.configure(text="Queued")
        self.bar.set(0)
        self.bytes_lbl.configure(text="")

    def set_downloading(self, speed_str: str = "") -> None:
        t = "Downloading"
        if speed_str:
            t = f"Downloading — {speed_str}"
        self.status_lbl.configure(text=t)

    def update_progress(
        self,
        pct: float,
        speed_str: str,
        downloaded: int | None,
        total: int | None,
    ) -> None:
        self.bar.set(pct)
        if speed_str:
            self.status_lbl.configure(text=f"Downloading — {speed_str}")
        else:
            self.status_lbl.configure(text="Downloading")
        self.bytes_lbl.configure(text=_fmt_mb_pair(downloaded, total))

    def set_phase(self, phase: str) -> None:
        self.status_lbl.configure(text=phase)

    def set_done(self) -> None:
        self.status_lbl.configure(text="Done")
        self.bar.set(1.0)

    def set_failed(self, err: str) -> None:
        short = err if len(err) <= 100 else err[:97] + "…"
        self.status_lbl.configure(text=f"Failed: {short}")
        self.bar.set(0)


class MainWindow(ctk.CTkFrame):
    def __init__(self, parent, writable_root: str = None):
        super().__init__(parent, fg_color="transparent")
        self._writable_root = writable_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self._msg_queue = None
        self._poll_id = None
        self._cancel_event = None
        self._playlist_result: PlaylistResult = None
        self._running = False
        self._download_queue = []
        self._queue_running = False
        self._telegram_uploading = False
        self._scroll_resize_job = None
        self._track_rows: dict[int, _TrackRowUI] = {}

        self._build_ui()
        self.after(800, self._check_ytdlp_update_available)
        self._refresh_history()
        self.after(150, lambda: self.url_entry.focus_set())

    def _refresh_history(self):
        try:
            rows = history_get_all(self._writable_root)
            self.history_text.configure(state="normal")
            self.history_text.delete("1.0", "end")
            if not rows:
                self.history_text.insert("end", "No download history yet.\n")
            else:
                for r in rows:
                    _id, title, url, fmt_type, fmt_detail, out_dir, created = r
                    date_str = created[:10] if len(created) >= 10 else created
                    self.history_text.insert("end", f"{date_str}  |  {fmt_type} ({fmt_detail})\n  {title}\n  {url}\n\n")
            self.history_text.configure(state="disabled")
        except Exception:
            pass

    def _clear_history(self):
        if messagebox.askyesno("Clear history", "Delete all download history?"):
            try:
                history_clear(self._writable_root)
                self._refresh_history()
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def _check_ytdlp_update_available(self):
        def _version_tuple(v: str):
            try:
                return tuple(int(x) for x in v.strip().split(".")[:4])
            except Exception:
                return (0,)

        def check():
            latest = get_latest_version()
            if latest is None:
                return
            current = get_current_version()
            if not latest or not current or latest == current:
                return
            if _version_tuple(latest) > _version_tuple(current):
                self.after(0, lambda: self.version_var.set(
                    f"yt-dlp: {current}  (update {latest} available)"
                ))
        threading.Thread(target=check, daemon=True).start()

    @staticmethod
    def _resolve_icon():
        if getattr(sys, "frozen", False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ico = os.path.join(base, "icon.ico")
        return ico if os.path.isfile(ico) else None

    def _schedule_settings_scroll_height(self, _event=None):
        """Resize settings panel height so tabview keeps most vertical space (small screens)."""
        if self._scroll_resize_job:
            try:
                self.after_cancel(self._scroll_resize_job)
            except Exception:
                pass
        self._scroll_resize_job = self.after(100, self._resize_settings_scroll)

    def _resize_settings_scroll(self):
        self._scroll_resize_job = None
        try:
            h = self.winfo_height()
            if h < 200:
                return
            # ~30% of window, clamped — leaves ~40%+ for tabs + chrome on ~820px height
            sh = max(160, min(380, int(h * 0.30)))
            self.settings_scroll.configure(height=sh)
        except Exception:
            pass

    def _on_self_configure(self, event):
        if event.widget is not self:
            return
        self._schedule_settings_scroll_height()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=1)
        self.grid_rowconfigure(4, weight=0)
        self.bind("<Configure>", self._on_self_configure)

        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 4))

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

        # Scrollable settings (URL → workers); height adjusted on resize
        self.settings_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0, height=280,
        )
        self.settings_scroll.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 6))
        sc = self.settings_scroll

        ctk.CTkLabel(
            sc,
            text="Video URL (YouTube, Instagram, TikTok, and 1800+ sites):",
            font=ctk.CTkFont(size=13),
        ).pack(anchor="w")
        url_frame = ctk.CTkFrame(sc, fg_color="transparent")
        url_frame.pack(fill="x", pady=(2, 8))
        self.url_var = tk.StringVar()
        self.url_entry = ctk.CTkEntry(
            url_frame, textvariable=self.url_var,
            placeholder_text="https://www.youtube.com/watch?v=... or any supported URL",
            height=36,
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            url_frame, text="Paste", width=70, height=36,
            command=self._paste_url,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            url_frame, text="Fetch preview", width=100, height=36,
            command=self._fetch_preview,
        ).pack(side="left")

        self.preview_frame = ctk.CTkFrame(sc, fg_color=("gray90", "gray17"), corner_radius=6)
        self.preview_frame.pack(fill="x", pady=(0, 8))
        self.preview_inner = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        self.preview_inner.pack(fill="x", padx=8, pady=8)
        self.preview_thumb_label = ctk.CTkLabel(
            self.preview_inner, text="", width=140, height=79,
        )
        self.preview_thumb_label.pack(side="left", padx=(0, 10))
        self.preview_title_var = tk.StringVar(value="")
        self.preview_title_label = ctk.CTkLabel(
            self.preview_inner, textvariable=self.preview_title_var,
            font=ctk.CTkFont(size=12), wraplength=360, anchor="w", justify="left",
        )
        self.preview_title_label.pack(side="left", fill="x", expand=True)
        self._preview_image = None
        self._preview_temp_file = None

        fmt_frame = ctk.CTkFrame(sc, fg_color="transparent")
        fmt_frame.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            fmt_frame, text="Format:", font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 10))
        self.format_var = tk.StringVar(value=FORMAT_AUDIO)
        ctk.CTkRadioButton(
            fmt_frame, text="Audio", variable=self.format_var,
            value=FORMAT_AUDIO, command=self._on_format_change,
        ).pack(side="left", padx=(0, 12))
        ctk.CTkRadioButton(
            fmt_frame, text="Video (MP4)", variable=self.format_var,
            value=FORMAT_MP4, command=self._on_format_change,
        ).pack(side="left")

        self.options_container = ctk.CTkFrame(sc, fg_color="transparent")
        self.options_container.pack(fill="x", pady=(0, 6))

        self.audio_options = ctk.CTkFrame(self.options_container, fg_color="transparent")
        ctk.CTkLabel(
            self.audio_options, text="Audio format:", font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 8))
        self.audio_fmt_var = tk.StringVar(value=AUDIO_FORMATS[0][0])
        ctk.CTkComboBox(
            self.audio_options, variable=self.audio_fmt_var,
            values=[a[0] for a in AUDIO_FORMATS], state="readonly", width=200,
        ).pack(side="left")

        self.video_options = ctk.CTkFrame(self.options_container, fg_color="transparent")
        ctk.CTkLabel(
            self.video_options, text="Video quality:", font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 8))
        self.quality_var = tk.StringVar(value=MP4_QUALITIES[0][0])
        ctk.CTkComboBox(
            self.video_options, variable=self.quality_var,
            values=[q[0] for q in MP4_QUALITIES], state="readonly", width=200,
        ).pack(side="left")

        self._on_format_change()

        ctk.CTkLabel(
            sc, text="Output folder:", font=ctk.CTkFont(size=13),
        ).pack(anchor="w")
        out_frame = ctk.CTkFrame(sc, fg_color="transparent")
        out_frame.pack(fill="x", pady=(2, 6))
        self.out_var = tk.StringVar(value=os.path.abspath("downloads"))
        ctk.CTkEntry(
            out_frame, textvariable=self.out_var, height=36,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            out_frame, text="Browse", width=80, height=36,
            command=self._browse_output,
        ).pack(side="left")

        cookie_frame = ctk.CTkFrame(sc, fg_color="transparent")
        cookie_frame.pack(fill="x", pady=(0, 6))
        self.cookie_var = tk.StringVar(value="")
        ctk.CTkLabel(
            cookie_frame, text="Cookies:", font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkEntry(
            cookie_frame, textvariable=self.cookie_var, height=32,
            placeholder_text="No cookie file",
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            cookie_frame, text="Load cookies…", width=100, height=32,
            command=self._browse_cookies,
        ).pack(side="left")

        sub_frame = ctk.CTkFrame(sc, fg_color="transparent")
        sub_frame.pack(fill="x", pady=(0, 6))
        self.subs_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            sub_frame, text="Download subtitles (SRT)", variable=self.subs_var,
            font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(
            sub_frame, text="Language:", font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 6))
        self.sub_lang_var = tk.StringVar(value="en")
        sub_lang_options = [
            "en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh", "ru", "ar", "hi",
        ]
        ctk.CTkComboBox(
            sub_frame, variable=self.sub_lang_var,
            values=sub_lang_options, state="readonly", width=80,
        ).pack(side="left", padx=(0, 16))
        self.sponsorblock_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            sub_frame, text="Remove sponsors (SponsorBlock)", variable=self.sponsorblock_var,
            font=ctk.CTkFont(size=13),
        ).pack(side="left")

        parallel_frame = ctk.CTkFrame(sc, fg_color="transparent")
        parallel_frame.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            parallel_frame, text="Parallel downloads:", font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 8))
        self.workers_var = tk.StringVar(value=str(DEFAULT_WORKERS))
        ctk.CTkOptionMenu(
            parallel_frame, variable=self.workers_var,
            values=[str(i) for i in range(1, MAX_WORKERS + 1)], width=60,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            parallel_frame, text=f"(1 = sequential, up to {MAX_WORKERS})",
            text_color=("gray50", "#AAB0B8"), font=ctk.CTkFont(size=11),
        ).pack(side="left")

        # Telegram (same vars; UI lives in tab — built after tabview exists)
        self.telegram_var = tk.BooleanVar(value=False)
        self.telegram_token_var = tk.StringVar(
            value=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        )
        self.telegram_channel_var = tk.StringVar(value="@wing_karaoke")
        self.telegram_topic_var = tk.StringVar(value="")
        self.telegram_album_var = tk.StringVar(value="No")
        self.telegram_workers_var = tk.StringVar(value="5")

        # Runtime strip: always visible (not inside scroll)
        runtime = ctk.CTkFrame(self, fg_color="transparent")
        runtime.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 4))

        btn_frame = ctk.CTkFrame(runtime, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(2, 4))
        self.download_btn = ctk.CTkButton(
            btn_frame, text="Download", width=120, height=36,
            command=self._start_download,
            fg_color="#2563eb", hover_color="#1d4ed8",
        )
        self.download_btn.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_frame, text="Add to Queue", width=100, height=36,
            command=self._add_to_queue,
            fg_color="#64748b", hover_color="#475569",
        ).pack(side="left", padx=(0, 8))
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

        stats_frame = ctk.CTkFrame(runtime, fg_color="transparent")
        stats_frame.pack(fill="x", pady=(0, 2))
        self.stats_var = tk.StringVar(value="")
        ctk.CTkLabel(
            stats_frame, textvariable=self.stats_var,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        self.speed_var = tk.StringVar(value="")
        ctk.CTkLabel(
            stats_frame, textvariable=self.speed_var,
            font=ctk.CTkFont(size=12),
            text_color=("#1d4ed8", "#60a5fa"),
        ).pack(side="right")

        self.overall_progress = ctk.CTkProgressBar(runtime, height=8)
        self.overall_progress.pack(fill="x", pady=(2, 2))
        self.overall_progress.set(0)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=3, column=0, sticky="nsew", padx=15, pady=(0, 4))
        self.tabview.add("Progress")
        self.tabview.add("Log")
        self.tabview.add("Summary")
        self.tabview.add("Queue")
        self.tabview.add("History")

        tab_prog = self.tabview.tab("Progress")
        tab_prog.grid_columnconfigure(0, weight=1)
        tab_prog.grid_rowconfigure(0, weight=1)
        self.downloads_scroll = ctk.CTkScrollableFrame(
            tab_prog, fg_color="transparent", corner_radius=0,
        )
        self.downloads_scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._rows_container = ctk.CTkFrame(
            self.downloads_scroll, fg_color="transparent",
        )
        self._rows_container.pack(fill="x", expand=True)
        ctk.CTkLabel(
            tab_prog,
            text="Per-item progress above — technical output on the Log tab.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#8899A8"),
        ).grid(row=1, column=0, sticky="w", padx=6, pady=(0, 4))

        self.log_text = ctk.CTkTextbox(
            self.tabview.tab("Log"), state="disabled",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        tab_sum = self.tabview.tab("Summary")
        tab_sum.grid_columnconfigure(0, weight=1)
        tab_sum.grid_rowconfigure(0, weight=1)
        tab_sum.grid_rowconfigure(1, weight=2)
        self.summary_rows_scroll = ctk.CTkScrollableFrame(
            tab_sum, fg_color="transparent", corner_radius=0,
        )
        self.summary_rows_scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 2))
        self._summary_rows_inner = ctk.CTkFrame(
            self.summary_rows_scroll, fg_color="transparent",
        )
        self._summary_rows_inner.pack(fill="x", expand=True)
        self.summary_text = ctk.CTkTextbox(
            tab_sum, state="disabled",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.summary_text.grid(row=1, column=0, sticky="nsew", padx=4, pady=(2, 4))

        tab_queue = self.tabview.tab("Queue")
        queue_frame = ctk.CTkFrame(tab_queue, fg_color="transparent")
        queue_frame.pack(fill="both", expand=True)
        queue_frame.grid_columnconfigure(0, weight=1)
        queue_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            queue_frame, text="Queued URLs (downloaded one after another):",
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=0, sticky="w")
        self.queue_text = ctk.CTkTextbox(
            queue_frame, state="disabled",
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self.queue_text.grid(row=1, column=0, sticky="nsew", pady=(4, 8))
        qbtn_frame = ctk.CTkFrame(queue_frame, fg_color="transparent")
        qbtn_frame.grid(row=2, column=0, sticky="ew")
        ctk.CTkButton(
            qbtn_frame, text="Start Queue", width=100,
            command=self._start_queue,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            qbtn_frame, text="Clear Queue", width=100,
            fg_color="#b91c1c", hover_color="#991b1b", command=self._clear_queue,
        ).pack(side="left")

        tab_hist = self.tabview.tab("History")
        hist_frame = ctk.CTkFrame(tab_hist, fg_color="transparent")
        hist_frame.pack(fill="both", expand=True)
        hist_frame.grid_columnconfigure(0, weight=1)
        hist_frame.grid_rowconfigure(0, weight=1)
        self.history_text = ctk.CTkTextbox(
            hist_frame, state="disabled",
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self.history_text.grid(row=0, column=0, sticky="nsew")
        hist_btn_frame = ctk.CTkFrame(hist_frame, fg_color="transparent")
        hist_btn_frame.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ctk.CTkButton(
            hist_btn_frame, text="Refresh", width=80,
            command=self._refresh_history,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            hist_btn_frame, text="Clear history", width=100,
            fg_color="#b91c1c", hover_color="#991b1b", command=self._clear_history,
        ).pack(side="left")

        if upload_folder_to_telegram:
            self.tabview.add("Upload to Telegram")
            tg_tab = self.tabview.tab("Upload to Telegram")
            tg_wrap = ctk.CTkScrollableFrame(tg_tab, fg_color="transparent", corner_radius=0)
            tg_wrap.pack(fill="both", expand=True)
            self.telegram_frame = ctk.CTkFrame(
                tg_wrap, fg_color=("gray90", "gray20"), corner_radius=6,
            )
            self.telegram_frame.pack(fill="x", pady=(0, 8))
            tg_inner = ctk.CTkFrame(self.telegram_frame, fg_color="transparent")
            tg_inner.pack(fill="x", padx=10, pady=8)
            ctk.CTkCheckBox(
                tg_inner, text="Upload to Telegram after download",
                variable=self.telegram_var, font=ctk.CTkFont(size=13),
                command=self._on_telegram_toggle,
            ).pack(anchor="w")
            self.telegram_opts = ctk.CTkFrame(tg_inner, fg_color="transparent")
            self.telegram_opts.pack(fill="x", pady=(6, 0))
            ctk.CTkLabel(
                self.telegram_opts, text="Bot token:", font=ctk.CTkFont(size=12),
            ).grid(row=0, column=0, sticky="w", padx=(0, 6), pady=2)
            ctk.CTkEntry(
                self.telegram_opts, textvariable=self.telegram_token_var,
                width=280, height=28, placeholder_text="Or set TELEGRAM_BOT_TOKEN",
            ).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=2)
            ctk.CTkLabel(
                self.telegram_opts, text="Channel:", font=ctk.CTkFont(size=12),
            ).grid(row=1, column=0, sticky="w", padx=(0, 6), pady=2)
            ctk.CTkEntry(
                self.telegram_opts, textvariable=self.telegram_channel_var,
                width=180, height=28, placeholder_text="@channel",
            ).grid(row=1, column=1, sticky="w", padx=(0, 8), pady=2)
            ctk.CTkLabel(
                self.telegram_opts, text="Topic ID (folder):",
                font=ctk.CTkFont(size=12),
            ).grid(row=2, column=0, sticky="w", padx=(0, 6), pady=2)
            ctk.CTkEntry(
                self.telegram_opts, textvariable=self.telegram_topic_var,
                width=100, height=28, placeholder_text="Optional",
            ).grid(row=2, column=1, sticky="w", padx=(0, 8), pady=2)
            ctk.CTkLabel(
                self.telegram_opts, text="Group as albums:",
                font=ctk.CTkFont(size=12),
            ).grid(row=3, column=0, sticky="w", padx=(0, 6), pady=2)
            ctk.CTkOptionMenu(
                self.telegram_opts, variable=self.telegram_album_var,
                values=["No", "5 per message", "10 per message"], width=140,
            ).grid(row=3, column=1, sticky="w", padx=(0, 8), pady=2)
            ctk.CTkLabel(
                self.telegram_opts, text="Upload workers:",
                font=ctk.CTkFont(size=12),
            ).grid(row=4, column=0, sticky="w", padx=(0, 6), pady=2)
            ctk.CTkOptionMenu(
                self.telegram_opts, variable=self.telegram_workers_var,
                values=[str(i) for i in range(1, 17)], width=60,
            ).grid(row=4, column=1, sticky="w", padx=(0, 8), pady=2)
            self.telegram_opts.grid_columnconfigure(1, weight=1)
            self._on_telegram_toggle()

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=15, pady=(2, 8))
        self.version_var = tk.StringVar(value=f"yt-dlp: {get_current_version()}")
        ctk.CTkLabel(
            footer, textvariable=self.version_var,
            font=ctk.CTkFont(size=11), text_color=("gray50", "#AAB0B8"),
        ).pack(side="left")
        ctk.CTkButton(
            footer, text="Update yt-dlp", width=100, height=28,
            command=self._update_ytdlp_clicked,
            fg_color="#475569", hover_color="#334155",
        ).pack(side="right")

        self.after_idle(self._resize_settings_scroll)

    # ------------------------------------------------------------------ helpers
    def _update_ytdlp_clicked(self):
        def do_update():
            def progress(msg: str):
                self.after(0, lambda: self._log(f"[yt-dlp update] {msg}"))
            ok, message = update_ytdlp(self._writable_root, progress_callback=progress)
            self.after(0, lambda: _done(ok, message))
        def _done(ok: bool, message: str):
            if ok:
                messagebox.showinfo("yt-dlp updated", message)
                self.version_var.set("yt-dlp: updated — restart app to use new version")
            else:
                messagebox.showerror("Update failed", message)
        self._log("[yt-dlp update] Checking for update...")
        threading.Thread(target=do_update, daemon=True).start()

    # ------------------------------------------------------------------ helpers (continued)
    def _toggle_theme(self):
        ctk.set_appearance_mode("dark" if self.theme_switch.get() else "light")

    def _on_telegram_toggle(self):
        if not getattr(self, "telegram_opts", None):
            return
        enabled = self.telegram_var.get()
        for child in self.telegram_opts.winfo_children():
            if isinstance(child, ctk.CTkLabel):
                continue
            try:
                child.configure(state="normal" if enabled else "disabled")
            except (tk.TclError, TypeError, ValueError):
                pass

    def _telegram_upload_done(self, ok: int, fail: int, error: str | None = None) -> None:
        self._telegram_uploading = False
        if error:
            self._log(f"[Telegram] Upload failed: {error}")
        else:
            self._log(f"[Telegram] Upload done. Uploaded: {ok}, Failed: {fail}")
        self._set_running(self._running)

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

    def _fetch_preview(self):
        url = self.url_var.get().strip()
        if not is_supported_url(url):
            messagebox.showwarning("Invalid URL", "Enter a valid http(s) URL first.")
            return
        self.preview_title_var.set("Fetching...")
        if self._preview_image:
            self.preview_thumb_label.configure(image=None, text="")
            self._preview_image = None
        if self._preview_temp_file and os.path.isfile(self._preview_temp_file):
            try:
                os.unlink(self._preview_temp_file)
            except Exception:
                pass
            self._preview_temp_file = None

        def do_fetch():
            preview = get_video_preview(url)
            self.after(0, lambda: self._show_preview(preview))

        threading.Thread(target=do_fetch, daemon=True).start()

    def _show_preview(self, preview):
        if preview is None:
            self.preview_title_var.set("Could not load preview.")
            return
        self.preview_title_var.set(preview.get("title") or "Unknown")
        thumb_url = preview.get("thumbnail") or ""
        if not thumb_url:
            self.preview_thumb_label.configure(image=None, text="No image")
            return
        try:
            path = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
            self._preview_temp_file = path
            urllib.request.urlretrieve(thumb_url, path)
            img = ctk.CTkImage(light_image=path, dark_image=path, size=(140, 79))
            self._preview_image = img
            self.preview_thumb_label.configure(image=img, text="")
        except Exception:
            self.preview_thumb_label.configure(image=None, text="Image load failed")

    def _on_drop(self, event):
        """Handle URL (or file path) dropped onto the window."""
        data = (event.data or "").strip()
        if not data:
            return
        # Browser often gives one URL per line or in braces
        for part in data.replace("{", " ").replace("}", " ").split():
            part = part.strip()
            if part.startswith("http://") or part.startswith("https://"):
                self.url_var.set(part)
                return
        if data.startswith("http://") or data.startswith("https://"):
            self.url_var.set(data)
            return
        # Single file path (e.g. from Explorer)
        if "\n" in data:
            data = data.split("\n")[0].strip()
        if data and (data.startswith("http://") or data.startswith("https://")):
            self.url_var.set(data)

    def _browse_output(self):
        path = filedialog.askdirectory(
            title="Select output folder", initialdir=self.out_var.get())
        if path:
            self.out_var.set(path)

    def _browse_cookies(self):
        path = filedialog.askopenfilename(
            title="Select cookies.txt (Netscape format)",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.cookie_var.set(path)

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

    @staticmethod
    def _parse_track_percent_payload(payload):
        if len(payload) >= 5:
            return payload[0], payload[1], payload[2], payload[3], payload[4]
        idx, pct, speed = payload[0], payload[1], payload[2]
        return idx, pct, speed, None, None

    def _truncate_title(self, title: str, max_len: int = 64) -> str:
        t = (title or "").strip() or "Untitled"
        if len(t) <= max_len:
            return t
        return t[: max_len - 1] + "…"

    def _meta_detail_str(self) -> str:
        if self.format_var.get() == FORMAT_MP4:
            return f"Video · {self.quality_var.get()}"
        return f"Audio · {self.audio_fmt_var.get()}"

    def _clear_download_rows(self) -> None:
        self._track_rows.clear()
        for w in self._rows_container.winfo_children():
            w.destroy()

    def _create_track_row(self, track: TrackInfo) -> _TrackRowUI:
        card = ctk.CTkFrame(
            self._rows_container,
            fg_color=("gray92", "gray18"),
            corner_radius=8,
        )
        card.pack(fill="x", pady=(0, 8))
        title = self._truncate_title(track.title)
        tl = ctk.CTkLabel(
            card,
            text=f"{track.index}. {title}",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        tl.pack(fill="x", padx=10, pady=(8, 2))
        out_base = os.path.basename(self.out_var.get().strip() or "downloads")
        ml = ctk.CTkLabel(
            card,
            text=f"{self._meta_detail_str()}  ·  folder: {out_base}",
            font=ctk.CTkFont(size=11),
            text_color=("gray35", "#AAB0B8"),
            anchor="w",
        )
        ml.pack(fill="x", padx=10, pady=(0, 2))
        sl = ctk.CTkLabel(
            card, text="Queued", font=ctk.CTkFont(size=12), anchor="w",
        )
        sl.pack(fill="x", padx=10, pady=(2, 2))
        bl = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(size=11),
            text_color=("gray40", "#8B98A8"),
            anchor="w",
        )
        bl.pack(fill="x", padx=10, pady=(0, 4))
        bar = ctk.CTkProgressBar(card, height=8)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        bar.set(0)
        return _TrackRowUI(card, tl, ml, sl, bl, bar)

    def _rebuild_track_rows_from_playlist(self) -> None:
        r = self._playlist_result
        if not r or not r.tracks:
            return
        self._clear_download_rows()
        for t in r.tracks:
            self._track_rows[t.index] = self._create_track_row(t)
            row = self._track_rows[t.index]
            if t.status == "done":
                row.set_done()
            elif t.status == "failed":
                row.set_failed(t.error or "")
            elif t.status == "downloading":
                row.set_downloading()
            else:
                row.set_queued()

    def _populate_summary_visual(self) -> None:
        for w in self._summary_rows_inner.winfo_children():
            w.destroy()
        r = self._playlist_result
        if not r or not r.tracks:
            return
        for t in r.tracks:
            fr = ctk.CTkFrame(
                self._summary_rows_inner,
                fg_color=("gray92", "gray18"),
                corner_radius=6,
            )
            fr.pack(fill="x", pady=(0, 6))
            if t.status == "done":
                st = "Done"
            elif t.status == "failed":
                st = "Failed"
            else:
                st = t.status or "—"
            ctk.CTkLabel(
                fr,
                text=f"{t.index}. {self._truncate_title(t.title, 56)} — {st}",
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).pack(fill="x", padx=8, pady=6)
            if t.status == "failed" and t.error:
                ctk.CTkLabel(
                    fr,
                    text=(t.error[:120] + "…") if len(t.error) > 120 else t.error,
                    font=ctk.CTkFont(size=11),
                    text_color="#ef4444",
                    anchor="w",
                ).pack(fill="x", padx=8, pady=(0, 6))

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
    def _add_to_queue(self):
        url = self.url_var.get().strip()
        if not is_supported_url(url):
            messagebox.showwarning("Invalid URL", "Enter a valid http(s) URL first.")
            return
        self._download_queue.append(url)
        self._refresh_queue_display()

    def _refresh_queue_display(self):
        self.queue_text.configure(state="normal")
        self.queue_text.delete("1.0", "end")
        for i, u in enumerate(self._download_queue, 1):
            self.queue_text.insert("end", f"{i}. {u}\n")
        self.queue_text.configure(state="disabled")

    def _clear_queue(self):
        self._download_queue.clear()
        self._refresh_queue_display()

    def _start_queue(self):
        if not self._download_queue:
            messagebox.showinfo("Queue empty", "Add URLs to the queue first.")
            return
        if self._running:
            messagebox.showinfo("Busy", "A download is already running.")
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
        self._queue_running = True
        self._start_next_queued_download()

    def _start_next_queued_download(self):
        if not self._download_queue:
            self._queue_running = False
            self._log("\n--- Queue finished ---")
            self._set_running(False)
            return
        url = self._download_queue.pop(0)
        self._refresh_queue_display()
        self.url_var.set(url)
        self._log(f"\n--- Queue: downloading ({len(self._download_queue)} left) ---")
        self._clear_log()
        self._clear_summary()
        self.stats_var.set("")
        self.speed_var.set("")
        self.overall_progress.set(0)
        self._playlist_result = None
        self._set_running(True)
        self.tabview.set("Progress")
        self._cancel_event = threading.Event()
        sub_langs = [self.sub_lang_var.get().strip()] if self.subs_var.get() else None
        self._msg_queue, self._cancel_event = start_download(
            url=url,
            output_dir=self.out_var.get().strip(),
            format_type=self.format_var.get(),
            quality_name=self.quality_var.get(),
            max_workers=int(self.workers_var.get()),
            cancel_event=self._cancel_event,
            audio_format_name=self.audio_fmt_var.get(),
            write_subs=bool(sub_langs),
            sub_langs=sub_langs,
            remove_sponsors=self.sponsorblock_var.get(),
            cookiefile=self.cookie_var.get().strip() or None,
        )
        self._poll_queue()

    def _start_download(self):
        url = self.url_var.get().strip()
        if not is_supported_url(url):
            messagebox.showerror(
                "Invalid URL",
                "Please enter a valid http:// or https:// URL (e.g. YouTube, Instagram, TikTok).")
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
        self._playlist_result = None
        self._set_running(True)
        self.tabview.set("Progress")

        self._cancel_event = threading.Event()

        sub_langs = [self.sub_lang_var.get().strip()] if self.subs_var.get() else None
        self._msg_queue, self._cancel_event = start_download(
            url=url,
            output_dir=out_dir,
            format_type=self.format_var.get(),
            quality_name=self.quality_var.get(),
            max_workers=int(self.workers_var.get()),
            cancel_event=self._cancel_event,
            audio_format_name=self.audio_fmt_var.get(),
            write_subs=bool(sub_langs),
            sub_langs=sub_langs,
            remove_sponsors=self.sponsorblock_var.get(),
            cookiefile=self.cookie_var.get().strip() or None,
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
        self._rebuild_track_rows_from_playlist()
        self._set_running(True)
        self.tabview.set("Progress")
        self.speed_var.set("")

        self._cancel_event = threading.Event()

        sub_langs = [self.sub_lang_var.get().strip()] if self.subs_var.get() else None
        self._msg_queue, self._cancel_event = retry_failed(
            playlist_result=self._playlist_result,
            output_dir=self.out_var.get().strip(),
            format_type=self.format_var.get(),
            quality_name=self.quality_var.get(),
            max_workers=int(self.workers_var.get()),
            cancel_event=self._cancel_event,
            audio_format_name=self.audio_fmt_var.get(),
            write_subs=bool(sub_langs),
            sub_langs=sub_langs,
            remove_sponsors=self.sponsorblock_var.get(),
            cookiefile=self.cookie_var.get().strip() or None,
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
            self._clear_download_rows()
            for t in payload.tracks:
                self._track_rows[t.index] = self._create_track_row(t)
            self._update_stats()

        elif msg_type == MSG_TRACK_START:
            track: TrackInfo = payload
            r = self._playlist_result
            total = r.total if r else "?"
            self._log(f"[{track.index}/{total}] Downloading: {track.title}")
            row = self._track_rows.get(track.index)
            if row:
                row.set_downloading()
            self._update_stats()

        elif msg_type == MSG_TRACK_PROGRESS:
            self._log(payload)

        elif msg_type == MSG_TRACK_PERCENT:
            idx, pct_float, speed_str, down_b, total_b = self._parse_track_percent_payload(
                payload)
            row = self._track_rows.get(idx)
            if row:
                row.update_progress(
                    pct_float, speed_str or "", down_b, total_b,
                )
            if speed_str:
                self.speed_var.set(f"Speed: {speed_str}")

        elif msg_type == MSG_TRACK_PHASE:
            idx, phase = payload
            row = self._track_rows.get(idx)
            if row:
                row.set_phase(phase)

        elif msg_type == MSG_TRACK_DONE:
            track: TrackInfo = payload
            self._log(f"[OK] {track.title}")
            row = self._track_rows.get(track.index)
            if row:
                row.set_done()
            self._update_stats()
            try:
                fmt_detail = self.quality_var.get() if self.format_var.get() == FORMAT_MP4 else self.audio_fmt_var.get()
                history_add(
                    self._writable_root,
                    title=track.title,
                    url=track.url,
                    format_type=self.format_var.get(),
                    format_detail=fmt_detail,
                    output_dir=self.out_var.get().strip(),
                )
            except Exception:
                pass

        elif msg_type == MSG_TRACK_FAILED:
            track: TrackInfo = payload
            self._log(f"[FAILED] {track.title} - {track.error}")
            row = self._track_rows.get(track.index)
            if row:
                row.set_failed(track.error or "")
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
        self.tabview.set("Summary")
        self.open_folder_btn.configure(state="normal")

        # Only upload to Telegram if user explicitly enabled the option (never by default).
        if self.telegram_var.get() and upload_folder_to_telegram:
            token = (self.telegram_token_var.get() or "").strip() or os.environ.get("TELEGRAM_BOT_TOKEN", "")
            channel = (self.telegram_channel_var.get() or "").strip()
            if token and channel:
                out_dir = self.out_var.get().strip()
                if out_dir and os.path.isdir(out_dir):
                    topic_s = (self.telegram_topic_var.get() or "").strip()
                    topic_id = int(topic_s) if topic_s.isdigit() else None
                    album_map = {"No": 0, "5 per message": 5, "10 per message": 10}
                    album_size = album_map.get(self.telegram_album_var.get(), 0)
                    workers = int(self.telegram_workers_var.get() or 5)
                    self._telegram_uploading = True

                    def progress_cb(current: int, total: int, message: str) -> None:
                        self.after(0, lambda: self._log(f"[Telegram] {message}"))

                    def do_upload() -> None:
                        try:
                            ok, fail = upload_folder_to_telegram(
                                token=token,
                                channel=channel,
                                folder_path=out_dir,
                                topic_id=topic_id,
                                album_size=album_size,
                                workers=workers,
                                progress_callback=progress_cb,
                            )
                            self.after(0, lambda: self._telegram_upload_done(ok, fail))
                        except Exception as e:
                            self.after(0, lambda: self._telegram_upload_done(0, 0, str(e)))

                    threading.Thread(target=do_upload, daemon=True).start()
                else:
                    self._log("[Telegram] Output folder not found; upload skipped.")
            else:
                self._log("[Telegram] Set bot token and channel to upload after download.")

        if self._queue_running and self._download_queue:
            self.after(500, self._start_next_queued_download)
        elif self._queue_running:
            self._queue_running = False
            self._log("\n--- Queue finished ---")

    def _set_running(self, running: bool):
        self._running = running
        busy = running or self._telegram_uploading
        self.download_btn.configure(state="disabled" if busy else "normal")
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
        for w in self._summary_rows_inner.winfo_children():
            w.destroy()
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
            self._populate_summary_visual()
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
        self._populate_summary_visual()


def _patch_ctk_root_drag_drop(root: ctk.CTk) -> bool:
    """
    Bind tkinterdnd2 methods onto CTk. Python 3.12+ Tk may use __getattr__
    delegating to self.tk, which hides BaseWidget.drop_target_register / dnd_bind.
    """
    import types

    import tkinter as tk
    from tkinterdnd2 import TkinterDnD, DND_TEXT

    try:
        TkinterDnD._require(root)
    except Exception:
        return False

    for _name in (
        "_substitute_dnd",
        "_dnd_bind",
        "dnd_bind",
        "drop_target_register",
        "drop_target_unregister",
    ):
        _fn = tk.BaseWidget.__dict__.get(_name)
        if callable(_fn):
            setattr(root, _name, types.MethodType(_fn, root))

    try:
        root.drop_target_register(DND_TEXT)
    except Exception:
        return False
    return True


def run(writable_root: str = None):
    root = ctk.CTk()
    use_dnd = False
    try:
        use_dnd = _patch_ctk_root_drag_drop(root)
    except Exception:
        use_dnd = False

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    _text = ["gray10", "#DCE4EE"]
    for widget_type in (
        "CTkLabel", "CTkCheckBox", "CTkRadioButton", "CTkSwitch",
    ):
        if widget_type in ctk.ThemeManager.theme:
            ctk.ThemeManager.theme[widget_type]["text_color"] = _text
    root.title("YouTube Downloader")
    root.geometry("780x660")
    root.minsize(920, 600)
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ico = os.path.join(base, "icon.ico")
    if os.path.isfile(ico):
        try:
            root.iconbitmap(ico)
        except Exception:
            pass

    app = MainWindow(root, writable_root)
    app.pack(fill="both", expand=True, padx=0, pady=0)
    if use_dnd:
        try:
            root.dnd_bind("<<Drop>>", lambda e: app._on_drop(e))
        except Exception:
            pass
    root.mainloop()
