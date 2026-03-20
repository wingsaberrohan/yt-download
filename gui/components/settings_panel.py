"""
Slide-in settings overlay panel.
Positioned with place() at right edge, animated via after() steps.
Contains: output folder, workers, filename template, scheduler default,
Telegram config, advanced options, yt-dlp update badge.
"""
import os
import tkinter as tk
import customtkinter as ctk
from typing import Callable, Dict, Any

from gui.theme import COLORS, glass_frame, accent_button, ghost_button, label_style


class SettingsPanel(ctk.CTkFrame):
    """
    Must be placed on the root/parent via place() after creation:
      panel = SettingsPanel(root, on_settings_change=..., ...)
      panel.place(relx=1.0, rely=0, anchor="ne", relheight=1.0, width=320)
    Call show() / hide() to animate.
    """

    PANEL_WIDTH = 320
    ANIM_STEPS = 18
    ANIM_INTERVAL_MS = 8

    def __init__(self, parent,
                 on_settings_change: Callable[[Dict[str, Any]], None],
                 writable_root: str,
                 initial: Dict[str, Any] = None,
                 **kwargs):
        super().__init__(parent, fg_color=COLORS["surface"],
                          border_width=1, border_color=COLORS["glass-border"],
                          corner_radius=0, **kwargs)
        self._on_change = on_settings_change
        self._root_dir = writable_root
        self._cfg = initial or {}
        self._visible = False
        self._anim_id = None
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="Settings", **label_style(16)).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="✕", width=28, height=28, command=self.hide,
                       **ghost_button()).grid(row=0, column=1)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                         scrollbar_button_color=COLORS["glass-border"])
        scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.grid_rowconfigure(1, weight=1)
        scroll.grid_columnconfigure(0, weight=1)

        def section(text):
            ctk.CTkLabel(scroll, text=text,
                          text_color=COLORS["text-secondary"],
                          font=("Segoe UI Variable", 11)).pack(anchor="w", padx=16, pady=(12, 2))

        def row_label(text):
            ctk.CTkLabel(scroll, text=text, **label_style(12)).pack(anchor="w", padx=16, pady=(6, 1))

        # ── Output folder ──
        section("DOWNLOADS")
        row_label("Output Folder")
        folder_row = ctk.CTkFrame(scroll, fg_color="transparent")
        folder_row.pack(fill="x", padx=16, pady=(0, 4))
        folder_row.grid_columnconfigure(0, weight=1)
        self._folder_var = tk.StringVar(
            value=self._cfg.get("output_dir",
                                 os.path.join(self._root_dir, "downloads")))
        ctk.CTkEntry(folder_row, textvariable=self._folder_var,
                      fg_color=COLORS["glass"], border_color=COLORS["glass-border"],
                      text_color=COLORS["text-primary"], corner_radius=8,
                      height=32).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(folder_row, text="…", width=36, height=32,
                       command=self._pick_folder, **ghost_button()).grid(row=0, column=1)

        # ── Workers ──
        section("PERFORMANCE")
        row_label("Parallel Downloads")
        self._workers_var = tk.IntVar(value=self._cfg.get("workers", 3))
        ctk.CTkSlider(scroll, from_=1, to=8, number_of_steps=7,
                       variable=self._workers_var,
                       progress_color=COLORS["accent"],
                       button_color=COLORS["accent"],
                       fg_color=COLORS["layer-3"]).pack(fill="x", padx=16, pady=(0, 2))
        self._workers_lbl = ctk.CTkLabel(scroll, text=f"{self._workers_var.get()} workers",
                                          **label_style(11, secondary=True))
        self._workers_lbl.pack(anchor="w", padx=16)
        self._workers_var.trace_add("write",
            lambda *_: self._workers_lbl.configure(text=f"{self._workers_var.get()} workers"))

        # ── Filename template ──
        section("FILENAMES")
        row_label("Template  (tokens: {title} {artist} {uploader} {date} {quality} {ext})")
        self._template_var = tk.StringVar(value=self._cfg.get("outtmpl", "{title}.{ext}"))
        ctk.CTkEntry(scroll, textvariable=self._template_var,
                      fg_color=COLORS["glass"], border_color=COLORS["glass-border"],
                      text_color=COLORS["text-primary"], corner_radius=8,
                      height=32).pack(fill="x", padx=16, pady=(0, 2))
        self._preview_lbl = ctk.CTkLabel(scroll, text="",
                                          **label_style(11, secondary=True))
        self._preview_lbl.pack(anchor="w", padx=16)
        self._template_var.trace_add("write", self._update_template_preview)
        self._update_template_preview()

        # ── Advanced ──
        section("ADVANCED")
        row_label("Cookies File (for age-restricted content)")
        cookie_row = ctk.CTkFrame(scroll, fg_color="transparent")
        cookie_row.pack(fill="x", padx=16, pady=(0, 4))
        cookie_row.grid_columnconfigure(0, weight=1)
        self._cookie_var = tk.StringVar(value=self._cfg.get("cookies_file", ""))
        ctk.CTkEntry(cookie_row, textvariable=self._cookie_var,
                      fg_color=COLORS["glass"], border_color=COLORS["glass-border"],
                      text_color=COLORS["text-primary"], corner_radius=8,
                      height=32).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(cookie_row, text="…", width=36, height=32,
                       command=self._pick_cookie, **ghost_button()).grid(row=0, column=1)

        # ── Telegram ──
        section("TELEGRAM (OPTIONAL)")
        for label, key in [("Bot Token", "telegram_token"), ("Channel ID", "telegram_channel")]:
            row_label(label)
            var = tk.StringVar(value=self._cfg.get(key, ""))
            setattr(self, f"_{key}_var", var)
            ctk.CTkEntry(scroll, textvariable=var,
                          fg_color=COLORS["glass"], border_color=COLORS["glass-border"],
                          text_color=COLORS["text-primary"], corner_radius=8,
                          height=32, show="*" if "token" in key else "").pack(
                fill="x", padx=16, pady=(0, 4))

        # Save button
        ctk.CTkButton(scroll, text="Apply Settings", height=36,
                       command=self._apply, **accent_button()).pack(
            fill="x", padx=16, pady=(16, 8))

    def _pick_folder(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(initialdir=self._folder_var.get())
        if path:
            self._folder_var.set(path)

    def _pick_cookie(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            self._cookie_var.set(path)

    def _update_template_preview(self, *_):
        tmpl = self._template_var.get()
        sample = (tmpl
                  .replace("{title}", "Song Title")
                  .replace("{artist}", "Artist")
                  .replace("{uploader}", "Uploader")
                  .replace("{date}", "20260320")
                  .replace("{quality}", "320kbps")
                  .replace("{ext}", "mp3")
                  .replace("{playlist_index}", "01"))
        self._preview_lbl.configure(text=f"Preview: {sample}")

    def _apply(self):
        self._cfg.update({
            "output_dir":        self._folder_var.get(),
            "workers":           self._workers_var.get(),
            "outtmpl":           self._template_var.get(),
            "cookies_file":      self._cookie_var.get(),
            "telegram_token":    self._telegram_token_var.get(),
            "telegram_channel":  self._telegram_channel_var.get(),
        })
        self._on_change(dict(self._cfg))
        self.hide()

    # ── Animation ────────────────────────────────────────────────────────

    def show(self):
        if self._visible:
            return
        self._visible = True
        self.lift()
        self._animate(target_relx=0.655)

    def hide(self):
        if not self._visible:
            return
        self._visible = False
        self._animate(target_relx=1.0, on_done=self.place_forget)

    def _animate(self, target_relx: float, on_done: Callable = None):
        if self._anim_id:
            try:
                self.after_cancel(self._anim_id)
            except Exception:
                pass
        try:
            info = self.place_info()
            current = float(info.get("relx", 1.0))
        except Exception:
            current = 1.0

        step = (target_relx - current) / self.ANIM_STEPS

        def _step(remaining, pos):
            if remaining <= 0:
                self.place_configure(relx=target_relx)
                if on_done:
                    on_done()
                return
            pos += step
            self.place_configure(relx=pos)
            self._anim_id = self.after(self.ANIM_INTERVAL_MS,
                                        lambda: _step(remaining - 1, pos))

        self.place_configure(relx=current, rely=0, anchor="ne",
                              relheight=1.0, width=self.PANEL_WIDTH)
        _step(self.ANIM_STEPS, current)
