"""
Per-track download row widget.
Shows: status stripe, thumbnail placeholder, title, channel, phase label,
progress bar, bytes/speed, expand toggle (retry / open / send to Telegram).
"""
import os
import sys
import threading
import tkinter as tk
import urllib.request
import tempfile

import customtkinter as ctk
from PIL import Image

from gui.theme import COLORS, glass_frame, accent_button, ghost_button, label_style, status_stripe


class TrackRow(ctk.CTkFrame):
    """
    One row in the downloads list.
    Callbacks:
      on_retry(track_url)
      on_open_file(file_path)
      on_send_telegram(file_path)
    """

    THUMB_SIZE = (48, 48)

    def __init__(self, parent, track_index: int, title: str, url: str,
                 on_retry=None, on_open_file=None, on_send_telegram=None, **kwargs):
        super().__init__(parent, **glass_frame(), **kwargs)
        self._index = track_index
        self._url = url
        self._file_path = None
        self._on_retry = on_retry
        self._on_open_file = on_open_file
        self._on_send_telegram = on_send_telegram
        self._expanded = False
        self._shimmer_on = False
        self._shimmer_id = None

        self._build(title)

    def _build(self, title: str):
        self.grid_columnconfigure(1, weight=1)

        # Left stripe (4px color indicator)
        self._stripe = ctk.CTkFrame(self, width=4, corner_radius=2,
                                     fg_color=COLORS["text-secondary"])
        self._stripe.grid(row=0, column=0, rowspan=3, sticky="ns", padx=(6, 8), pady=6)

        # Thumbnail placeholder
        self._thumb_lbl = ctk.CTkLabel(self, text="", width=48, height=48,
                                        fg_color=COLORS["layer-3"], corner_radius=6)
        self._thumb_lbl.grid(row=0, column=1, rowspan=2, padx=(0, 10), pady=8, sticky="w")

        # Title
        self._title_lbl = ctk.CTkLabel(
            self, text=title, anchor="w", wraplength=0,
            **label_style(13)
        )
        self._title_lbl.grid(row=0, column=2, sticky="ew", padx=(0, 10), pady=(8, 0))

        # Phase + speed on same row
        self._phase_lbl = ctk.CTkLabel(self, text="Queued", anchor="w",
                                        **label_style(11, secondary=True))
        self._phase_lbl.grid(row=1, column=2, sticky="ew", padx=(0, 10), pady=(0, 2))

        # Progress bar
        self._bar = ctk.CTkProgressBar(self, height=6, corner_radius=3,
                                        progress_color=COLORS["accent"],
                                        fg_color=COLORS["layer-3"])
        self._bar.set(0)
        self._bar.grid(row=2, column=1, columnspan=2, sticky="ew",
                        padx=(0, 10), pady=(0, 6))

        # Expand button
        self._expand_btn = ctk.CTkButton(self, text="›", width=28, height=28,
                                          command=self._toggle_expand,
                                          **ghost_button())
        self._expand_btn.grid(row=0, column=3, padx=(0, 6), pady=8)

        # Expanded detail frame (hidden initially)
        self._detail_frame = ctk.CTkFrame(self, fg_color=COLORS["layer-3"],
                                           corner_radius=6)
        # Not gridded until expanded

        # Bind click on row to expand
        self.bind("<Button-1>", lambda e: self._toggle_expand())

    def _toggle_expand(self):
        self._expanded = not self._expanded
        if self._expanded:
            self._expand_btn.configure(text="‹")
            self._build_detail()
            self._detail_frame.grid(row=3, column=0, columnspan=4,
                                     sticky="ew", padx=10, pady=(0, 8))
        else:
            self._expand_btn.configure(text="›")
            self._detail_frame.grid_forget()

    def _build_detail(self):
        for w in self._detail_frame.winfo_children():
            w.destroy()

        btn_frame = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=8, pady=6)

        if self._file_path and os.path.exists(self._file_path):
            ctk.CTkButton(btn_frame, text="Open File", width=100,
                          command=self._do_open_file, **ghost_button()).pack(side="left", padx=(0, 6))
            ctk.CTkButton(btn_frame, text="Send to Telegram", width=130,
                          command=self._do_send_telegram, **ghost_button()).pack(side="left")

        # Show retry if failed
        phase_text = self._phase_lbl.cget("text")
        if "Failed" in phase_text and self._on_retry:
            ctk.CTkButton(btn_frame, text="Retry", width=80,
                          command=lambda: self._on_retry(self._url),
                          **accent_button()).pack(side="right")

    def _do_open_file(self):
        if self._on_open_file and self._file_path:
            self._on_open_file(self._file_path)

    def _do_send_telegram(self):
        if self._on_send_telegram and self._file_path:
            self._on_send_telegram(self._file_path)

    # ── Public state setters ──────────────────────────────────────────────

    def set_stripe(self, state: str):
        cfg = status_stripe(state)
        self._stripe.configure(fg_color=cfg["fg_color"])

    def set_downloading(self, speed_str: str = ""):
        self.set_stripe("downloading")
        text = f"Downloading — {speed_str}" if speed_str else "Downloading…"
        self._phase_lbl.configure(text=text)
        self._start_shimmer()

    def update_progress(self, pct: float, speed_str: str,
                         downloaded=None, total=None):
        self._bar.set(pct)
        mb_text = ""
        if downloaded is not None:
            if total and total > 0:
                mb_text = f" · {downloaded/1_048_576:.1f}/{total/1_048_576:.1f} MB"
            elif downloaded > 0:
                mb_text = f" · {downloaded/1_048_576:.1f} MB"
        speed = f" — {speed_str}" if speed_str else ""
        pct_str = f"{pct*100:.0f}%"
        self._phase_lbl.configure(text=f"Downloading {pct_str}{speed}{mb_text}")

    def set_phase(self, phase: str):
        self._phase_lbl.configure(text=phase)

    def set_done(self, file_path: str = None):
        self._stop_shimmer()
        self._file_path = file_path
        self.set_stripe("done")
        self._bar.set(1.0)
        self._bar.configure(progress_color=COLORS["success"])
        self._phase_lbl.configure(text="✓ Done")

    def set_failed(self, err: str):
        self._stop_shimmer()
        self.set_stripe("failed")
        self._bar.set(0)
        short = err[:80] + "…" if len(err) > 80 else err
        self._phase_lbl.configure(text=f"Failed: {short}")

    def set_thumbnail(self, img: ctk.CTkImage):
        self._thumb_lbl.configure(image=img, text="")

    def load_thumbnail_async(self, url: str):
        threading.Thread(target=self._fetch_thumb, args=(url,), daemon=True).start()

    def _fetch_thumb(self, url: str):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
                urllib.request.urlretrieve(url, f.name)
                img = Image.open(f.name).resize(self.THUMB_SIZE)
                ctk_img = ctk.CTkImage(img, size=self.THUMB_SIZE)
                self.after(0, lambda: self.set_thumbnail(ctk_img))
        except Exception:
            pass

    def _start_shimmer(self):
        self._shimmer_on = True
        self._shimmer_tick()

    def _stop_shimmer(self):
        self._shimmer_on = False
        if self._shimmer_id:
            try:
                self.after_cancel(self._shimmer_id)
            except Exception:
                pass

    def _shimmer_tick(self):
        if not self._shimmer_on:
            return
        colors = [COLORS["accent"], "#a78bfa"]
        current = self._bar.cget("progress_color")
        next_color = colors[1] if current == colors[0] else colors[0]
        try:
            self._bar.configure(progress_color=next_color)
            self._shimmer_id = self.after(600, self._shimmer_tick)
        except Exception:
            pass
