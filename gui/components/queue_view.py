"""
Queue manager: scrollable list of pending/active download items.
Each item is a glass card with status stripe, title, format badge,
up/down reorder buttons, remove button, right-click scheduler.
"""
import tkinter as tk
import customtkinter as ctk
from typing import List, Dict, Callable, Optional
from dataclasses import dataclass, field
import time

from gui.theme import COLORS, glass_frame, ghost_button, accent_button, label_style, status_stripe


@dataclass
class QueueItem:
    url: str
    title: str = "Loading…"
    format_label: str = "MP3 320"
    state: str = "pending"       # pending | downloading | converting | done | failed | scheduled
    scheduled_at: Optional[float] = None  # UNIX timestamp if scheduled
    error: str = ""


class QueueView(ctk.CTkScrollableFrame):
    """
    Callbacks:
      on_start_item(item: QueueItem)
      on_remove_item(index: int)
      on_reorder(from_idx: int, to_idx: int)
      on_schedule_item(index: int, timestamp: float)
    """

    def __init__(self, parent,
                 on_start_item: Callable = None,
                 on_remove_item: Callable = None,
                 on_reorder: Callable = None,
                 on_schedule_item: Callable = None,
                 **kwargs):
        super().__init__(parent, fg_color=COLORS["surface"],
                          scrollbar_button_color=COLORS["glass-border"],
                          **kwargs)
        self._items: List[QueueItem] = []
        self._on_start = on_start_item
        self._on_remove = on_remove_item
        self._on_reorder = on_reorder
        self._on_schedule = on_schedule_item
        self._item_frames: List[ctk.CTkFrame] = []
        self._countdown_id = None
        self._start_countdown_updates()

    # ── Public API ────────────────────────────────────────────────────────

    def add_item(self, item: QueueItem) -> int:
        self._items.append(item)
        self._render()
        return len(self._items) - 1

    def update_item_state(self, index: int, state: str, error: str = ""):
        if 0 <= index < len(self._items):
            self._items[index].state = state
            self._items[index].error = error
            self._render()

    def update_item_title(self, index: int, title: str):
        if 0 <= index < len(self._items):
            self._items[index].title = title
            self._render()

    def get_items(self) -> List[QueueItem]:
        return list(self._items)

    def clear_done(self):
        self._items = [i for i in self._items if i.state not in ("done", "failed")]
        self._render()

    def count(self) -> int:
        return len(self._items)

    def pending_count(self) -> int:
        return sum(1 for i in self._items if i.state == "pending")

    # ── Rendering ─────────────────────────────────────────────────────────

    def _render(self):
        for w in self.winfo_children():
            w.destroy()
        self._item_frames = []

        if not self._items:
            ctk.CTkLabel(self, text="Queue is empty — paste a URL above",
                          **label_style(13, secondary=True)).pack(pady=40)
            return

        for idx, item in enumerate(self._items):
            frame = self._make_item_frame(idx, item)
            frame.pack(fill="x", padx=8, pady=(0, 6))
            self._item_frames.append(frame)

    def _make_item_frame(self, idx: int, item: QueueItem) -> ctk.CTkFrame:
        outer = ctk.CTkFrame(self, **glass_frame())
        outer.grid_columnconfigure(2, weight=1)

        # Status stripe
        stripe_color = status_stripe(item.state)["fg_color"]
        ctk.CTkFrame(outer, width=4, corner_radius=2,
                      fg_color=stripe_color).grid(
            row=0, column=0, rowspan=2, sticky="ns", padx=(6, 8), pady=6)

        # Title
        ctk.CTkLabel(outer, text=item.title, anchor="w",
                      **label_style(13)).grid(row=0, column=2, sticky="ew", padx=(0, 8), pady=(6, 0))

        # Format badge + optional countdown
        badge_text = item.format_label
        if item.state == "scheduled" and item.scheduled_at:
            remaining = max(0, int(item.scheduled_at - time.time()))
            h, r = divmod(remaining, 3600)
            m, s = divmod(r, 60)
            badge_text += f"  ⏰ {h:02d}:{m:02d}:{s:02d}"

        ctk.CTkLabel(outer, text=badge_text, anchor="w",
                      **label_style(11, secondary=True)).grid(
            row=1, column=2, sticky="ew", padx=(0, 8), pady=(0, 6))

        # Up/Down/Remove buttons
        btn_col = ctk.CTkFrame(outer, fg_color="transparent")
        btn_col.grid(row=0, column=3, rowspan=2, padx=(0, 6), pady=4)

        if idx > 0:
            ctk.CTkButton(btn_col, text="▲", width=26, height=22,
                           command=lambda i=idx: self._move(i, -1),
                           **ghost_button()).pack(pady=(0, 2))
        if idx < len(self._items) - 1:
            ctk.CTkButton(btn_col, text="▼", width=26, height=22,
                           command=lambda i=idx: self._move(i, 1),
                           **ghost_button()).pack()

        ctk.CTkButton(outer, text="✕", width=26, height=26,
                       command=lambda i=idx: self._remove(i),
                       fg_color="transparent", hover_color=COLORS["error"],
                       text_color=COLORS["text-secondary"],
                       corner_radius=6).grid(row=0, column=4, padx=(0, 6), pady=6)

        # Right-click for schedule
        outer.bind("<Button-3>", lambda e, i=idx: self._ctx_menu(e, i))

        return outer

    def _move(self, idx: int, direction: int):
        new_idx = idx + direction
        if 0 <= new_idx < len(self._items):
            self._items[idx], self._items[new_idx] = self._items[new_idx], self._items[idx]
            if self._on_reorder:
                self._on_reorder(idx, new_idx)
            self._render()

    def _remove(self, idx: int):
        if 0 <= idx < len(self._items):
            self._items.pop(idx)
            if self._on_remove:
                self._on_remove(idx)
            self._render()

    def _ctx_menu(self, event, idx: int):
        menu = tk.Menu(self, tearoff=0, bg=COLORS["surface"],
                        fg=COLORS["text-primary"],
                        activebackground=COLORS["accent-hover"])
        menu.add_command(label="Schedule for…",
                          command=lambda: self._open_schedule_dialog(idx))
        menu.add_command(label="Remove", command=lambda: self._remove(idx))
        menu.tk_popup(event.x_root, event.y_root)

    def _open_schedule_dialog(self, idx: int):
        dialog = _ScheduleDialog(self)
        self.wait_window(dialog)
        if dialog.result_timestamp and self._on_schedule:
            self._on_schedule(idx, dialog.result_timestamp)
            self._items[idx].state = "scheduled"
            self._items[idx].scheduled_at = dialog.result_timestamp
            self._render()

    def _start_countdown_updates(self):
        has_scheduled = any(i.state == "scheduled" for i in self._items)
        if has_scheduled:
            self._render()
        self._countdown_id = self.after(1000, self._start_countdown_updates)


class _ScheduleDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Schedule Download")
        self.geometry("280x160")
        self.grab_set()
        self.configure(fg_color=COLORS["surface"])
        self.result_timestamp = None

        ctk.CTkLabel(self, text="Start download at:", **label_style(13)).pack(pady=(16, 8))

        time_row = ctk.CTkFrame(self, fg_color="transparent")
        time_row.pack()

        hours = [f"{h:02d}" for h in range(24)]
        mins  = [f"{m:02d}" for m in range(60)]

        self._hour_var = tk.StringVar(value="09")
        self._min_var  = tk.StringVar(value="00")

        ctk.CTkOptionMenu(time_row, values=hours, variable=self._hour_var,
                           width=70, fg_color=COLORS["glass"],
                           button_color=COLORS["accent"]).pack(side="left", padx=4)
        ctk.CTkLabel(time_row, text=":", **label_style(16)).pack(side="left")
        ctk.CTkOptionMenu(time_row, values=mins, variable=self._min_var,
                           width=70, fg_color=COLORS["glass"],
                           button_color=COLORS["accent"]).pack(side="left", padx=4)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=14)
        ctk.CTkButton(btn_row, text="Set", width=90, command=self._set,
                       **accent_button()).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="Cancel", width=90, command=self.destroy,
                       **ghost_button()).pack(side="left")

    def _set(self):
        import datetime
        now = datetime.datetime.now()
        h = int(self._hour_var.get())
        m = int(self._min_var.get())
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            target = target + datetime.timedelta(days=1)
        self.result_timestamp = target.timestamp()
        self.destroy()
