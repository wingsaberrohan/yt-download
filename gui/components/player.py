"""
Audio player using pygame.mixer.
Shows: file name, seek bar, play/pause/stop buttons.
Video files: 'Open in system player' button only.
"""
import os
import sys
import subprocess
import threading
import customtkinter as ctk
import tkinter as tk
from typing import Optional

from gui.theme import COLORS, glass_frame, accent_button, ghost_button, label_style

try:
    import pygame
    pygame.mixer.init()
    _PYGAME_OK = True
except Exception:
    _PYGAME_OK = False

_AUDIO_EXTS = {".mp3", ".flac", ".wav", ".ogg", ".aac", ".m4a"}
_VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov"}


def _open_system_player(path: str):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])


class PlayerView(ctk.CTkFrame):
    """Embedded audio player (top 40% of content area when active)."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **glass_frame(), **kwargs)
        self._file_path: Optional[str] = None
        self._playing = False
        self._duration_ms = 0
        self._poll_id = None
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # File name label
        self._name_lbl = ctk.CTkLabel(
            self, text="No file loaded",
            **label_style(13), anchor="center"
        )
        self._name_lbl.grid(row=0, column=0, pady=(14, 6), padx=16, sticky="ew")

        # Seek bar
        self._seek_var = tk.DoubleVar(value=0)
        self._seek = ctk.CTkSlider(
            self, from_=0, to=100, variable=self._seek_var,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            fg_color=COLORS["layer-3"],
            command=self._on_seek,
        )
        self._seek.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 4))

        # Time labels
        time_row = ctk.CTkFrame(self, fg_color="transparent")
        time_row.grid(row=2, column=0, sticky="ew", padx=20)
        self._pos_lbl = ctk.CTkLabel(time_row, text="0:00", **label_style(11, secondary=True))
        self._pos_lbl.pack(side="left")
        self._dur_lbl = ctk.CTkLabel(time_row, text="0:00", **label_style(11, secondary=True))
        self._dur_lbl.pack(side="right")

        # Controls
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.grid(row=3, column=0, pady=(6, 14))

        self._play_btn = ctk.CTkButton(ctrl, text="▶ Play", width=90,
                                        command=self._toggle_play, **accent_button())
        self._play_btn.pack(side="left", padx=6)

        ctk.CTkButton(ctrl, text="⏹ Stop", width=80,
                       command=self._stop, **ghost_button()).pack(side="left", padx=6)

        ctk.CTkButton(ctrl, text="Open in Player", width=120,
                       command=self._open_system, **ghost_button()).pack(side="left", padx=6)

    # ── Public ───────────────────────────────────────────────────────────

    def load(self, path: str):
        self._stop()
        self._file_path = path
        self._name_lbl.configure(text=os.path.basename(path))
        ext = os.path.splitext(path)[1].lower()
        is_audio = ext in _AUDIO_EXTS

        if is_audio and _PYGAME_OK:
            try:
                pygame.mixer.music.load(path)
                sound = pygame.mixer.Sound(path)
                self._duration_ms = int(sound.get_length() * 1000)
                del sound
                self._seek.configure(to=max(1, self._duration_ms))
                self._seek_var.set(0)
                self._update_dur_label(self._duration_ms)
                self._play_btn.configure(state="normal")
            except Exception as e:
                self._name_lbl.configure(text=f"Cannot load: {os.path.basename(path)}")
        else:
            self._play_btn.configure(state="disabled")

    # ── Controls ─────────────────────────────────────────────────────────

    def _toggle_play(self):
        if not _PYGAME_OK or not self._file_path:
            return
        if self._playing:
            pygame.mixer.music.pause()
            self._playing = False
            self._play_btn.configure(text="▶ Play")
            if self._poll_id:
                self.after_cancel(self._poll_id)
        else:
            if pygame.mixer.music.get_pos() == -1:
                pygame.mixer.music.play()
            else:
                pygame.mixer.music.unpause()
            self._playing = True
            self._play_btn.configure(text="⏸ Pause")
            self._poll_position()

    def _stop(self):
        if _PYGAME_OK:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self._playing = False
        self._play_btn.configure(text="▶ Play")
        self._seek_var.set(0)
        self._pos_lbl.configure(text="0:00")
        if self._poll_id:
            try:
                self.after_cancel(self._poll_id)
            except Exception:
                pass

    def _on_seek(self, value):
        if _PYGAME_OK and self._file_path:
            try:
                pygame.mixer.music.set_pos(float(value) / 1000)
            except Exception:
                pass

    def _open_system(self):
        if self._file_path:
            _open_system_player(self._file_path)

    def _poll_position(self):
        if not self._playing or not _PYGAME_OK:
            return
        pos = pygame.mixer.music.get_pos()
        if pos >= 0:
            self._seek_var.set(pos)
            self._update_pos_label(pos)
        self._poll_id = self.after(500, self._poll_position)

    def _update_pos_label(self, ms: int):
        self._pos_lbl.configure(text=_fmt_time(ms))

    def _update_dur_label(self, ms: int):
        self._dur_lbl.configure(text=_fmt_time(ms))


def _fmt_time(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"
