"""
Command bar: large pill input for URL paste or YouTube search.
- Detects single URL → shows source badge
- Detects multiple URLs (newline-separated) → triggers on_batch_urls
- Detects non-URL text (500ms debounce) → triggers YouTube search
- Drag-drop handled by parent (fills entry via set_url)
"""
import re
import tkinter as tk
import customtkinter as ctk
from typing import Callable, List, Optional

from gui.theme import COLORS, label_style, accent_button


def _is_url(text: str) -> bool:
    text = text.strip()
    return text.startswith("http://") or text.startswith("https://")


def _detect_source(url: str) -> str:
    url = url.lower()
    if "youtube.com" in url or "youtu.be" in url:
        return "YouTube"
    if "soundcloud.com" in url:
        return "SoundCloud"
    if "spotify.com" in url:
        return "Spotify"
    if "instagram.com" in url:
        return "Instagram"
    if "tiktok.com" in url:
        return "TikTok"
    if "twitter.com" in url or "x.com" in url:
        return "Twitter/X"
    if "vimeo.com" in url:
        return "Vimeo"
    return "URL"


class CommandBar(ctk.CTkFrame):
    """
    Callbacks:
      on_submit(url: str)             — single URL confirmed (Enter or Download click)
      on_search(query: str)           — non-URL text after debounce
      on_batch_urls(urls: List[str])  — multiple URLs detected on paste
    """

    SEARCH_DEBOUNCE_MS = 500

    def __init__(self, parent,
                 on_submit: Callable,
                 on_search: Callable,
                 on_batch_urls: Callable,
                 **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._on_submit = on_submit
        self._on_search = on_search
        self._on_batch_urls = on_batch_urls
        self._debounce_id: Optional[str] = None

        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # Outer pill frame
        pill = ctk.CTkFrame(self, fg_color=COLORS["glass"],
                             border_width=1, border_color=COLORS["glass-border"],
                             corner_radius=22)
        pill.grid(row=0, column=0, sticky="ew")
        pill.grid_columnconfigure(1, weight=1)

        # Search icon label
        ctk.CTkLabel(pill, text="🔍", font=("Segoe UI Variable", 15),
                     text_color=COLORS["text-secondary"], width=36).grid(
            row=0, column=0, padx=(12, 0), pady=8)

        # Input
        self._var = tk.StringVar()
        self._entry = ctk.CTkEntry(
            pill, textvariable=self._var,
            placeholder_text="Paste URL or search YouTube…",
            fg_color="transparent", border_width=0,
            text_color=COLORS["text-primary"],
            placeholder_text_color=COLORS["text-secondary"],
            font=("Segoe UI Variable", 14),
            height=40,
        )
        self._entry.grid(row=0, column=1, sticky="ew", padx=8)
        self._entry.bind("<Return>", self._on_enter)
        self._entry.bind("<Control-v>", self._on_paste)
        self._var.trace_add("write", self._on_text_change)

        # Download button
        self._dl_btn = ctk.CTkButton(
            pill, text="Download", width=100, height=32,
            command=self._on_enter, **accent_button()
        )
        self._dl_btn.grid(row=0, column=2, padx=(0, 8), pady=4)

        # Paste shortcut button
        ctk.CTkButton(
            pill, text="Paste", width=60, height=32,
            command=self._paste_clipboard,
            fg_color="transparent", hover_color=COLORS["accent-hover"],
            text_color=COLORS["text-secondary"], border_width=0,
        ).grid(row=0, column=3, padx=(0, 4))

        # Badge row (shown below pill when URL detected)
        self._badge_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._badge_frame.grid(row=1, column=0, sticky="w", padx=12, pady=(2, 0))
        self._badge_lbl = ctk.CTkLabel(self._badge_frame, text="",
                                        **label_style(11, secondary=True))
        self._badge_lbl.pack(side="left")

    def _on_text_change(self, *_):
        text = self._var.get()
        if not text.strip():
            self._badge_lbl.configure(text="")
            return

        if _is_url(text.strip()):
            source = _detect_source(text.strip())
            self._badge_lbl.configure(text=f"🌐 {source} detected")
            self._cancel_debounce()
        else:
            self._badge_lbl.configure(text="")
            self._reset_debounce(text)

    def _reset_debounce(self, text: str):
        self._cancel_debounce()
        self._debounce_id = self.after(
            self.SEARCH_DEBOUNCE_MS,
            lambda: self._on_search(text) if text.strip() else None
        )

    def _cancel_debounce(self):
        if self._debounce_id:
            try:
                self.after_cancel(self._debounce_id)
            except Exception:
                pass
            self._debounce_id = None

    def _on_enter(self, *_):
        text = self._var.get().strip()
        if not text:
            return
        if _is_url(text):
            self._on_submit(text)
        else:
            self._on_search(text)

    def _on_paste(self, *_):
        try:
            clipboard = self._entry.clipboard_get()
            lines = [l.strip() for l in clipboard.splitlines() if l.strip()]
            urls = [l for l in lines if _is_url(l)]
            if len(urls) > 1:
                self._on_batch_urls(urls)
                return
        except Exception:
            pass

    def _paste_clipboard(self):
        try:
            text = self._entry.clipboard_get()
            self._var.set(text.strip())
        except Exception:
            pass

    def set_url(self, url: str):
        self._var.set(url)

    def clear(self):
        self._var.set("")
        self._badge_lbl.configure(text="")

    def get_text(self) -> str:
        return self._var.get().strip()

    def update_badge(self, text: str):
        self._badge_lbl.configure(text=text)

    def focus(self):
        self._entry.focus_set()
