"""
Main window shell — command-bar-first layout with glassmorphism theme.
Wires together all components; owns the download state machine.
"""
import os
import sys
import threading
import tkinter as tk
from queue import Empty
from typing import Optional, Dict, Any, List

import customtkinter as ctk

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES, DND_TEXT
    # Disabled: tkinterdnd2 0.4.3 is not compatible with Python 3.14 tkinter
    _DND_OK = False
except ImportError:
    _DND_OK = False

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
    get_video_preview, search_youtube, DownloadScheduler,
)
from downloader import history as history_module
from downloader.presets import load_presets

from gui import theme
from gui.theme import COLORS
from gui.components.command_bar import CommandBar
from gui.components.preset_pills import PresetPills
from gui.components.queue_view import QueueView, QueueItem
from gui.components.track_row import TrackRow
from gui.components.player import PlayerView
from gui.components.history_view import HistoryView
from gui.components.settings_panel import SettingsPanel

try:
    from upload_to_telegram import upload_folder_to_telegram
except ImportError:
    upload_folder_to_telegram = None


def _notify(title: str, message: str):
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=5)
    except Exception:
        pass


class MainWindow(ctk.CTkFrame):

    def __init__(self, parent, writable_root: str = None):
        super().__init__(parent, fg_color=COLORS["base"])
        self._root = writable_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._cfg: Dict[str, Any] = {
            "output_dir": os.path.join(self._root, "downloads"),
            "workers": 3,
            "outtmpl": "{title}.{ext}",
            "cookies_file": "",
            "telegram_token": "",
            "telegram_channel": "",
        }

        # Download state
        self._msg_queue = None
        self._poll_id = None
        self._cancel_event = None
        self._playlist_result: Optional[PlaylistResult] = None
        self._running = False
        self._track_rows: Dict[int, TrackRow] = {}
        self._active_preset: Optional[Dict] = None
        self._current_nav = "queue"  # queue | history | player
        self._update_badge_pending = False

        self._scheduler = DownloadScheduler()
        self._scheduler.start()

        self._build_ui()
        self.after(800, self._check_ytdlp_update)

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self):
        self.pack(fill="both", expand=True)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Title bar ──
        title_bar = ctk.CTkFrame(self, fg_color="transparent")
        title_bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        title_bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(title_bar, text="YT Downloader",
                      font=("Segoe UI Variable", 18, "bold"),
                      text_color=COLORS["text-primary"]).grid(row=0, column=0, sticky="w")

        self._settings_badge = ctk.CTkButton(
            title_bar, text="⚙", width=36, height=36,
            command=self._toggle_settings,
            **theme.ghost_button(),
        )
        self._settings_badge.grid(row=0, column=1)

        # ── Command bar + presets ──
        cmd_area = ctk.CTkFrame(self, fg_color="transparent")
        cmd_area.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        cmd_area.grid_columnconfigure(0, weight=1)

        self._cmd_bar = CommandBar(
            cmd_area,
            on_submit=self._on_url_submit,
            on_search=self._on_search,
            on_batch_urls=self._on_batch_urls,
        )
        self._cmd_bar.grid(row=0, column=0, sticky="ew")

        self._preset_pills = PresetPills(
            cmd_area,
            on_select=self._on_preset_selected,
            current_format_fn=self._get_current_format,
        )
        self._preset_pills.grid(row=1, column=0, sticky="w", pady=(6, 0))

        # Select first preset by default
        presets = load_presets()
        if presets:
            self._active_preset = presets[0]

        # ── Adaptive content area ──
        self._content = ctk.CTkFrame(self, fg_color=COLORS["surface"],
                                      border_width=1,
                                      border_color=COLORS["glass-border"],
                                      corner_radius=10)
        self._content.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 0))
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

        # Queue view (default)
        self._queue_view = QueueView(
            self._content,
            on_remove_item=lambda _: None,
            on_reorder=lambda a, b: None,
            on_schedule_item=self._on_schedule_item,
        )
        self._queue_view.grid(row=0, column=0, sticky="nsew")

        # History view (hidden initially)
        self._history_view = HistoryView(
            self._content, writable_root=self._root, on_play=self._play_file
        )

        # Player view (hidden initially)
        self._player_view = PlayerView(self._content)

        # Search results frame (hidden initially)
        self._search_frame = ctk.CTkScrollableFrame(
            self._content, fg_color="transparent",
            scrollbar_button_color=COLORS["glass-border"],
        )

        # ── Bottom nav ──
        nav = ctk.CTkFrame(self, fg_color=COLORS["layer-1"],
                            border_width=1, border_color=COLORS["glass-border"],
                            corner_radius=0)
        nav.grid(row=3, column=0, sticky="ew")
        nav.grid_columnconfigure(3, weight=1)

        self._nav_btns = {}
        for col, (key, icon) in enumerate([
            ("queue",   "≡  Queue"),
            ("history", "📁  History"),
            ("player",  "▶  Player"),
        ]):
            btn = ctk.CTkButton(
                nav, text=icon, height=38,
                command=lambda k=key: self._switch_nav(k),
                fg_color="transparent",
                hover_color=COLORS["accent-hover"],
                text_color=COLORS["text-secondary"],
                corner_radius=0,
            )
            btn.grid(row=0, column=col, sticky="ew", padx=1)
            nav.grid_columnconfigure(col, weight=1)
            self._nav_btns[key] = btn

        self._speed_lbl = ctk.CTkLabel(nav, text="",
                                        **theme.label_style(11, secondary=True))
        self._speed_lbl.grid(row=0, column=3, padx=12)

        # ── Cancel button (shown during downloads) ──
        self._cancel_btn = ctk.CTkButton(
            self, text="Cancel", height=32, width=100,
            command=self._cancel_download,
            fg_color=COLORS["error"], hover_color="#c0392b",
            text_color=COLORS["text-primary"], corner_radius=8,
        )
        # Not shown until download starts

        # ── Settings panel (place()-based overlay) ──
        self._settings_panel = SettingsPanel(
            self, on_settings_change=self._on_settings_change,
            writable_root=self._root, initial=dict(self._cfg),
        )
        # Not placed until first shown

        self._switch_nav("queue")

    # ── Navigation ────────────────────────────────────────────────────────

    def _switch_nav(self, key: str):
        self._current_nav = key

        # Update button styles
        for k, btn in self._nav_btns.items():
            btn.configure(
                text_color=COLORS["text-primary"] if k == key else COLORS["text-secondary"],
                fg_color=COLORS["accent-hover"] if k == key else "transparent",
            )

        # Hide all content widgets
        self._queue_view.grid_forget()
        self._history_view.grid_forget()
        self._player_view.grid_forget()
        self._search_frame.grid_forget()

        if key == "queue":
            self._queue_view.grid(row=0, column=0, sticky="nsew")
        elif key == "history":
            self._history_view.grid(row=0, column=0, sticky="nsew")
            self._history_view.refresh()
        elif key == "player":
            self._player_view.grid(row=0, column=0, sticky="nsew")

        # Update queue count label on nav button
        q_count = self._queue_view.count()
        self._nav_btns["queue"].configure(
            text=f"≡  Queue {q_count}" if q_count else "≡  Queue"
        )

    # ── Command bar callbacks ─────────────────────────────────────────────

    def _on_url_submit(self, url: str):
        preset = self._active_preset or load_presets()[0]
        item = QueueItem(url=url, title="Fetching…",
                         format_label=preset.get("name", ""))
        idx = self._queue_view.add_item(item)
        self._switch_nav("queue")
        # Fetch title in background
        threading.Thread(
            target=self._fetch_title_for_item,
            args=(idx, url), daemon=True
        ).start()
        # Start immediately if nothing running
        if not self._running:
            self._start_next_download()

    def _fetch_title_for_item(self, idx: int, url: str):
        try:
            preview = get_video_preview(url)
            if preview and preview.get("title"):
                self.after(0, lambda: self._queue_view.update_item_title(idx, preview["title"]))
        except Exception:
            pass

    def _on_search(self, query: str):
        self._cmd_bar.update_badge("🔍 Searching…")
        threading.Thread(
            target=self._do_search, args=(query,), daemon=True
        ).start()

    def _do_search(self, query: str):
        results = search_youtube(query)
        self.after(0, lambda: self._show_search_results(results, query))

    def _show_search_results(self, results: list, query: str):
        self._cmd_bar.update_badge("")
        for w in self._search_frame.winfo_children():
            w.destroy()

        if not results:
            ctk.CTkLabel(self._search_frame,
                          text=f'No results for "{query}"',
                          **theme.label_style(13, secondary=True)).pack(pady=20)
        else:
            ctk.CTkLabel(self._search_frame,
                          text=f'Results for "{query}"',
                          **theme.label_style(14)).pack(anchor="w", padx=12, pady=(8, 4))
            for r in results:
                self._make_search_result_card(r)

        # Show search frame in content area
        self._queue_view.grid_forget()
        self._history_view.grid_forget()
        self._player_view.grid_forget()
        self._search_frame.grid(row=0, column=0, sticky="nsew")

    def _make_search_result_card(self, result: dict):
        card = ctk.CTkFrame(self._search_frame, **theme.glass_frame())
        card.pack(fill="x", padx=8, pady=(0, 6))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text=result["title"][:60], anchor="w",
                      **theme.label_style(13)).grid(row=0, column=1, sticky="ew",
                                                     padx=10, pady=(6, 0))
        meta = f"{result['uploader']}  ·  {result['duration_str']}"
        ctk.CTkLabel(card, text=meta, anchor="w",
                      **theme.label_style(11, secondary=True)).grid(row=1, column=1, sticky="ew",
                                                                     padx=10, pady=(0, 6))
        ctk.CTkButton(card, text="Add", width=60, height=28,
                       command=lambda u=result["url"]: self._on_url_submit(u),
                       **theme.accent_button()).grid(row=0, column=2, rowspan=2, padx=(0, 8))

    def _on_batch_urls(self, urls: List[str]):
        from tkinter import messagebox
        if messagebox.askyesno("Batch Import",
                                f"Add {len(urls)} URLs to the queue?"):
            for url in urls:
                preset = self._active_preset or load_presets()[0]
                item = QueueItem(url=url, title=url[:60] + "…",
                                 format_label=preset.get("name", ""))
                self._queue_view.add_item(item)
            self._switch_nav("queue")
            if not self._running:
                self._start_next_download()

    # ── Preset callbacks ──────────────────────────────────────────────────

    def _on_preset_selected(self, preset: Dict):
        self._active_preset = preset

    def _get_current_format(self) -> Dict:
        """Return current format settings (used by + preset chip)."""
        if self._active_preset:
            return dict(self._active_preset)
        return {"format_type": "audio", "codec": "mp3", "quality": "320"}

    # ── Download orchestration ────────────────────────────────────────────

    def _start_next_download(self):
        if self._running:
            return
        items = self._queue_view.get_items()
        pending = [(i, item) for i, item in enumerate(items)
                   if item.state == "pending"]
        if not pending:
            return

        idx, item = pending[0]
        self._queue_view.update_item_state(idx, "downloading")
        self._running = True

        preset = self._active_preset or load_presets()[0]
        fmt_type = preset.get("format_type", "audio")
        codec    = preset.get("codec", "mp3")
        quality  = preset.get("quality", "320")

        # Map preset to engine params.
        # start_download uses: quality_name, audio_format_name, cookiefile, max_workers
        if fmt_type == "audio":
            format_type = FORMAT_AUDIO
            audio_format_name = (f"{codec.upper()} - {quality} kbps" if quality != "0"
                                  else f"{codec.upper()} (lossless)")
            quality_name = audio_format_name
        else:
            format_type = FORMAT_MP4
            audio_format_name = ""
            quality_name = quality

        os.makedirs(self._cfg["output_dir"], exist_ok=True)

        self._msg_queue, self._cancel_event = start_download(
            url=item.url,
            format_type=format_type,
            quality_name=quality_name,
            audio_format_name=audio_format_name,
            output_dir=self._cfg["output_dir"],
            max_workers=self._cfg.get("workers", DEFAULT_WORKERS),
            cookiefile=self._cfg.get("cookies_file") or None,
            outtmpl_template=self._cfg.get("outtmpl") or None,
        )

        # Show cancel button
        self._cancel_btn.grid(row=4, column=0, pady=(4, 8))

        self._track_rows = {}
        self._poll_queue()

    def _poll_queue(self):
        if self._msg_queue is None:
            return
        try:
            while True:
                msg_type, data = self._msg_queue.get_nowait()
                self._handle_msg(msg_type, data)
        except Empty:
            pass
        self._poll_id = self.after(150, self._poll_queue)

    def _handle_msg(self, msg_type: str, data):
        if msg_type == MSG_PLAYLIST_INFO:
            result: PlaylistResult = data
            self._playlist_result = result
            for i, track in enumerate(result.tracks):
                row = TrackRow(
                    self._queue_view,
                    track_index=i,
                    title=track.title or f"Track {i+1}",
                    url=track.url,
                    on_retry=lambda u: self._retry_track(u),
                    on_open_file=self._play_file,
                    on_send_telegram=self._send_to_telegram,
                )
                row.pack(fill="x", padx=8, pady=(0, 4))
                self._track_rows[i] = row

        elif msg_type == MSG_TRACK_START:
            track = data  # TrackInfo object; index is 1-based
            idx = track.index - 1
            if idx in self._track_rows:
                self._track_rows[idx].set_downloading()

        elif msg_type == MSG_TRACK_PERCENT:
            # data is (track.index [1-based], pct, speed_str, downloaded, total)
            raw_idx, pct, speed_str, downloaded, total = data
            idx = raw_idx - 1
            if idx in self._track_rows:
                self._track_rows[idx].update_progress(pct, speed_str, downloaded, total)
            if speed_str:
                self._speed_lbl.configure(text=f"⚡ {speed_str}")

        elif msg_type == MSG_TRACK_PROGRESS:
            # Supplementary progress message; MSG_TRACK_PERCENT is the primary progress signal
            pass

        elif msg_type == MSG_TRACK_PHASE:
            # data is (track.index [1-based], phase_str)
            raw_idx, phase = data
            idx = raw_idx - 1
            if idx in self._track_rows:
                self._track_rows[idx].set_phase(phase)

        elif msg_type == MSG_TRACK_DONE:
            track = data  # TrackInfo object; index is 1-based
            idx = track.index - 1
            file_path = getattr(track, 'output_path', None) or getattr(track, 'file_path', None)
            if idx in self._track_rows:
                self._track_rows[idx].set_done(file_path=file_path)
            # Only update QueueView state if no active TrackRows (avoids _render destroying them)
            if not self._track_rows:
                self._queue_view.update_item_state(idx, "done")

        elif msg_type == MSG_TRACK_FAILED:
            track = data  # TrackInfo object; index is 1-based
            idx = track.index - 1
            err = getattr(track, 'error', '') or ''
            if idx in self._track_rows:
                self._track_rows[idx].set_failed(err)
            # Only update QueueView state if no active TrackRows (avoids _render destroying them)
            if not self._track_rows:
                self._queue_view.update_item_state(idx, "failed", err)

        elif msg_type == MSG_FINISHED:
            self._on_download_finished(data)

    def _on_download_finished(self, result: PlaylistResult):
        self._running = False
        self._playlist_result = result
        self._cancel_btn.grid_forget()
        self._speed_lbl.configure(text="")

        # Add to history
        try:
            for t in result.tracks:
                if t.status == "done":
                    preset = self._active_preset or {}
                    history_module.add(
                        self._root, t.title, t.url,
                        preset.get("format_type", "audio"),
                        preset.get("name", ""),
                        self._cfg["output_dir"],
                    )
        except Exception:
            pass

        # Notify
        done = result.done_count
        failed = result.failed_count
        _notify("Download Complete",
                f"{done} done{f', {failed} failed' if failed else ''}")

        # Start next pending item if queue has more
        self.after(200, self._start_next_download)

    def _cancel_download(self):
        if self._cancel_event:
            self._cancel_event.set()
        self._running = False
        self._cancel_btn.grid_forget()

    def _retry_track(self, url: str):
        if self._playlist_result and not self._running:
            self._running = True
            preset = self._active_preset or {}
            fmt_type = preset.get("format_type", "audio")
            codec    = preset.get("codec", "mp3")
            quality  = preset.get("quality", "320")

            if fmt_type == "audio":
                format_type = FORMAT_AUDIO
                audio_format_name = (f"{codec.upper()} - {quality} kbps" if quality != "0"
                                      else f"{codec.upper()} (lossless)")
                quality_name = audio_format_name
            else:
                format_type = FORMAT_MP4
                audio_format_name = ""
                quality_name = quality

            self._msg_queue, self._cancel_event = retry_failed(
                self._playlist_result,
                format_type=format_type,
                quality_name=quality_name,
                audio_format_name=audio_format_name,
                output_dir=self._cfg["output_dir"],
                outtmpl_template=self._cfg.get("outtmpl") or None,
            )
            self._poll_queue()

    # ── Player ────────────────────────────────────────────────────────────

    def _play_file(self, path: str):
        self._player_view.load(path)
        self._switch_nav("player")

    # ── Telegram ──────────────────────────────────────────────────────────

    def _send_to_telegram(self, file_path: str):
        if not upload_folder_to_telegram:
            return
        token   = self._cfg.get("telegram_token", "")
        channel = self._cfg.get("telegram_channel", "")
        if not token or not channel:
            return
        threading.Thread(
            target=upload_folder_to_telegram,
            args=(os.path.dirname(file_path), token, channel),
            daemon=True,
        ).start()

    # ── Scheduler ────────────────────────────────────────────────────────

    def _on_schedule_item(self, idx: int, timestamp: float):
        items = self._queue_view.get_items()
        if 0 <= idx < len(items):
            self._scheduler.add(
                f"item-{idx}",
                timestamp,
                lambda: self.after(0, self._start_next_download),
            )

    # ── Settings ─────────────────────────────────────────────────────────

    def _toggle_settings(self):
        if self._settings_panel._visible:
            self._settings_panel.hide()
        else:
            self._settings_panel.show()

    def _on_settings_change(self, cfg: Dict[str, Any]):
        self._cfg.update(cfg)

    # ── yt-dlp update check ───────────────────────────────────────────────

    def _check_ytdlp_update(self):
        def check():
            try:
                latest = get_latest_version()
                current = get_current_version()
                if latest and current and latest != current:
                    self.after(0, lambda: self._settings_badge.configure(text="⚙●"))
            except Exception:
                pass
        threading.Thread(target=check, daemon=True).start()


def _patch_ctk_for_python314():
    """Fix CustomTkinter 5.2.2 incompatibilities with Python 3.14.

    Python 3.14 changed tkinter internals: nametowidget/_substitute fail when
    a CTkScrollbar's Canvas has a <Configure> event firing during widget init.
    We patch _nametowidget on Misc to gracefully handle the TypeError.
    """
    import sys
    if sys.version_info < (3, 14):
        return
    try:
        import tkinter as _tk
        _orig_ntw = _tk.Misc.nametowidget

        def _safe_nametowidget(self, name):
            try:
                return _orig_ntw(self, name)
            except TypeError:
                # _root() failed because self._root is not callable — walk master chain
                w = self
                try:
                    while getattr(w, 'master', None) is not None:
                        w = w.master
                except Exception:
                    pass
                name_parts = str(name).split('.')
                for n in name_parts:
                    if not n:
                        continue
                    try:
                        w = w.children[n]
                    except (AttributeError, KeyError):
                        break
                return w

        _tk.Misc.nametowidget = _safe_nametowidget
        _tk.Misc._nametowidget = _safe_nametowidget  # alias used by _substitute

        # Also remove the update_idletasks() call from CTkScrollbar._draw
        # which triggers events before widgets are fully set up
        from customtkinter.windows.widgets import ctk_scrollbar
        _orig_scrollbar_draw = ctk_scrollbar.CTkScrollbar._draw

        def _patched_scrollbar_draw(self, no_color_updates=False):
            _orig_scrollbar_draw(self, no_color_updates)
            # update_idletasks() was already called inside _orig_scrollbar_draw
            # but we prevent it from re-firing by cancelling any queued calls
            # (noop here — the fix is in _safe_nametowidget above)

        # No need to replace _draw now that _nametowidget handles the TypeError
    except Exception:
        pass  # Non-critical: if patch fails, app may still work


def run(writable_root: str = None):
    """Entry point — creates root window and starts the app."""
    _patch_ctk_for_python314()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    if _DND_OK:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    root.title("YT Downloader")
    root.geometry("920x660")
    root.minsize(800, 560)
    root.configure(bg=COLORS["base"])

    icon_path = _resolve_icon()
    if icon_path:
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass

    app = MainWindow(root, writable_root=writable_root)

    if _DND_OK:
        def _on_drop(event):
            data = event.data.strip()
            if data.endswith(".txt") and os.path.isfile(data):
                with open(data) as f:
                    lines = [l.strip() for l in f if l.strip().startswith("http")]
                if lines:
                    app._on_batch_urls(lines)
            elif data.startswith("http"):
                app._cmd_bar.set_url(data)
        root.drop_target_register(DND_TEXT, DND_FILES)
        root.dnd_bind("<<Drop>>", _on_drop)

    root.mainloop()


def _resolve_icon() -> Optional[str]:
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ico = os.path.join(base, "icon.ico")
    return ico if os.path.isfile(ico) else None
