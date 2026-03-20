"""
Format preset pill chips.
Shows active preset highlighted in violet.
Right-click → Edit / Duplicate / Delete context menu.
'+' chip creates new preset from provided current_format_fn callback.
"""
import customtkinter as ctk
import tkinter as tk
from typing import List, Dict, Callable, Optional

from gui.theme import COLORS, ghost_button, accent_button
from downloader.presets import load_presets, save_presets


class PresetPills(ctk.CTkFrame):
    """
    Horizontal row of preset pills.
    on_select(preset_dict) called when user activates a preset.
    current_format_fn() should return the current format settings dict.
    """

    def __init__(self, parent, on_select: Callable, current_format_fn: Callable, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._on_select = on_select
        self._current_format_fn = current_format_fn
        self._active_index: Optional[int] = None
        self._presets: List[Dict] = []
        self._pill_buttons: List[ctk.CTkButton] = []
        self.refresh()

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._pill_buttons = []
        self._presets = load_presets()

        for i, preset in enumerate(self._presets):
            is_active = (i == self._active_index)
            btn = ctk.CTkButton(
                self,
                text=preset["name"],
                width=0,
                height=28,
                corner_radius=14,
                fg_color=COLORS["accent"] if is_active else COLORS["glass"],
                hover_color=COLORS["accent-hover"],
                text_color=COLORS["text-primary"],
                border_width=1,
                border_color=COLORS["glass-border"],
                command=lambda idx=i: self._select(idx),
            )
            btn.pack(side="left", padx=(0, 6))
            btn.bind("<Button-3>", lambda e, idx=i: self._context_menu(e, idx))
            self._pill_buttons.append(btn)

        # '+' chip
        add_btn = ctk.CTkButton(
            self, text="+", width=28, height=28, corner_radius=14,
            command=self._add_from_current,
            **ghost_button(),
        )
        add_btn.pack(side="left")

    def _select(self, index: int):
        self._active_index = index
        self.refresh()
        if self._on_select:
            self._on_select(self._presets[index])

    def _context_menu(self, event, index: int):
        menu = tk.Menu(self, tearoff=0, bg=COLORS["surface"],
                       fg=COLORS["text-primary"], activebackground=COLORS["accent-hover"])
        menu.add_command(label="Edit", command=lambda: self._edit(index))
        menu.add_command(label="Duplicate", command=lambda: self._duplicate(index))
        menu.add_separator()
        menu.add_command(label="Delete", command=lambda: self._delete(index))
        menu.tk_popup(event.x_root, event.y_root)

    def _edit(self, index: int):
        preset = self._presets[index]
        dialog = _PresetEditDialog(self, preset)
        self.wait_window(dialog)
        if dialog.result:
            self._presets[index] = dialog.result
            save_presets(self._presets)
            self.refresh()

    def _duplicate(self, index: int):
        copy = dict(self._presets[index])
        copy["name"] = copy["name"] + " Copy"
        self._presets.append(copy)
        save_presets(self._presets)
        self.refresh()

    def _delete(self, index: int):
        if len(self._presets) <= 1:
            return  # keep at least one preset
        self._presets.pop(index)
        if self._active_index and self._active_index >= len(self._presets):
            self._active_index = len(self._presets) - 1
        save_presets(self._presets)
        self.refresh()

    def _add_from_current(self):
        fmt = self._current_format_fn()
        new_preset = dict(name="New Preset", **fmt)
        dialog = _PresetEditDialog(self, new_preset)
        self.wait_window(dialog)
        if dialog.result:
            self._presets.append(dialog.result)
            save_presets(self._presets)
            self.refresh()


class _PresetEditDialog(ctk.CTkToplevel):
    def __init__(self, parent, preset: Dict):
        super().__init__(parent)
        self.title("Edit Preset")
        self.geometry("340x200")
        self.grab_set()
        self.configure(fg_color=COLORS["surface"])
        self.result = None

        ctk.CTkLabel(self, text="Preset name:", **_lbl()).pack(anchor="w", padx=20, pady=(16, 2))
        self._name_var = tk.StringVar(value=preset.get("name", ""))
        ctk.CTkEntry(self, textvariable=self._name_var, height=34).pack(fill="x", padx=20)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=16)
        ctk.CTkButton(btn_row, text="Save", width=100,
                      command=lambda: self._save(preset),
                      **accent_button()).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cancel", width=100,
                      command=self.destroy, **ghost_button()).pack(side="left")

    def _save(self, original: Dict):
        name = self._name_var.get().strip()
        if name:
            self.result = dict(original, name=name)
        self.destroy()


def _lbl():
    return dict(text_color=COLORS["text-primary"], font=("Segoe UI Variable", 12))
