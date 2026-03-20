"""
History view: searchable, filterable list of completed downloads.
Search by title, filter by format (All/Audio/Video), export to CSV.
"""
import csv
import os
import tkinter as tk
import customtkinter as ctk
from typing import Callable, Optional, List
from datetime import datetime

from gui.theme import COLORS, glass_frame, ghost_button, accent_button, label_style
from downloader.history import get_all as history_get_all, clear as history_clear


class HistoryView(ctk.CTkFrame):
    """
    on_play(file_path) — called when user clicks Play on an audio entry.
    writable_root — passed to history_get_all / history_clear.
    """

    def __init__(self, parent, writable_root: str, on_play: Callable = None, **kwargs):
        super().__init__(parent, fg_color=COLORS["surface"], **kwargs)
        self._root = writable_root
        self._on_play = on_play
        self._all_rows = []
        self._build()
        self.refresh()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Filter bar
        filter_bar = ctk.CTkFrame(self, fg_color="transparent")
        filter_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        filter_bar.grid_columnconfigure(0, weight=1)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filters())
        ctk.CTkEntry(filter_bar, textvariable=self._search_var,
                      placeholder_text="Search downloads…",
                      fg_color=COLORS["glass"], border_color=COLORS["glass-border"],
                      text_color=COLORS["text-primary"], corner_radius=8,
                      height=32).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._fmt_filter = ctk.CTkSegmentedButton(
            filter_bar, values=["All", "Audio", "Video"],
            command=lambda _: self._apply_filters(),
            fg_color=COLORS["glass"], selected_color=COLORS["accent"],
            text_color=COLORS["text-primary"],
        )
        self._fmt_filter.set("All")
        self._fmt_filter.grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(filter_bar, text="Export CSV", width=100,
                       command=self._export_csv, **ghost_button()).grid(row=0, column=2, padx=(0, 4))
        ctk.CTkButton(filter_bar, text="Clear All", width=90,
                       command=self._clear, **ghost_button()).grid(row=0, column=3)

        # Scrollable list
        self._list = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=COLORS["glass-border"],
        )
        self._list.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._list.grid_columnconfigure(0, weight=1)

    def refresh(self):
        try:
            self._all_rows = history_get_all(self._root) or []
        except Exception:
            self._all_rows = []
        self._apply_filters()

    def _apply_filters(self):
        query = self._search_var.get().lower()
        fmt = self._fmt_filter.get()

        filtered = []
        for row in self._all_rows:
            _id, title, url, fmt_type, fmt_detail, out_dir, created = row
            if query and query not in title.lower():
                continue
            if fmt == "Audio" and fmt_type.lower() != "audio":
                continue
            if fmt == "Video" and fmt_type.lower() != "video":
                continue
            filtered.append(row)

        for w in self._list.winfo_children():
            w.destroy()

        if not filtered:
            ctk.CTkLabel(self._list, text="No downloads match filters.",
                          **label_style(13, secondary=True)).pack(pady=30)
            return

        for row in reversed(filtered):  # newest first
            self._make_entry(row)

    def _make_entry(self, row):
        _id, title, url, fmt_type, fmt_detail, out_dir, created = row
        date_str = created[:10] if len(created) >= 10 else created

        card = ctk.CTkFrame(self._list, **glass_frame())
        card.pack(fill="x", pady=(0, 6), padx=4)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text=title, anchor="w",
                      **label_style(13)).grid(row=0, column=0, sticky="ew",
                                               padx=12, pady=(8, 0))
        meta = f"{date_str}  ·  {fmt_type} ({fmt_detail})"
        ctk.CTkLabel(card, text=meta, anchor="w",
                      **label_style(11, secondary=True)).grid(row=1, column=0, sticky="ew",
                                                               padx=12, pady=(0, 8))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=0, column=1, rowspan=2, padx=(0, 8))

        # Try to find the file
        if out_dir and os.path.isdir(out_dir):
            ctk.CTkButton(btn_row, text="Open Folder", width=100,
                           command=lambda d=out_dir: _open_folder(d),
                           **ghost_button()).pack(padx=4)

    def _export_csv(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"download_history_{datetime.now().strftime('%Y%m%d')}.csv",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Title", "URL", "Format", "Detail", "Output Dir"])
                for row in self._all_rows:
                    _id, title, url, fmt_type, fmt_detail, out_dir, created = row
                    writer.writerow([created[:10], title, url, fmt_type, fmt_detail, out_dir])
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Export failed", str(e))

    def _clear(self):
        from tkinter import messagebox
        if messagebox.askyesno("Clear history", "Delete all download history?"):
            try:
                history_clear(self._root)
                self.refresh()
            except Exception as e:
                messagebox.showerror("Error", str(e))


def _open_folder(path: str):
    import sys, subprocess
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])
