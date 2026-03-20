# YouTube Downloader Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the YouTube Downloader with glassmorphism-inspired UI, command-bar-first layout, and 7 new features (presets, queue manager, YouTube search, batch import, scheduler, audio player, smart filenames).

**Architecture:** Split monolithic `gui/app.py` (1328 lines) into focused components under `gui/components/`. New `downloader/` modules handle presets, search, and scheduling. Existing `engine.py`, `history.py`, `ytdlp_updater.py` are untouched.

**Tech Stack:** Python 3.8+, CustomTkinter 5.2+, tkinterdnd2, yt-dlp, pygame (new), plyer (new), requests

---

## File Map

**Create:**
- `gui/theme.py` — color tokens + CTk widget style factory functions
- `gui/components/__init__.py` — empty
- `gui/components/track_row.py` — per-track download row widget
- `gui/components/preset_pills.py` — format preset chips
- `gui/components/command_bar.py` — URL/search input bar
- `gui/components/queue_view.py` — queue list with up/down reorder
- `gui/components/player.py` — pygame.mixer audio player
- `gui/components/history_view.py` — searchable history with CSV export
- `gui/components/settings_panel.py` — slide-in settings overlay
- `downloader/presets.py` — load/save ~/.ytdl_presets.json
- `downloader/search.py` — yt-dlp YouTube search wrapper
- `downloader/scheduler.py` — scheduled download background thread
- `tests/test_presets.py` — unit tests for presets module
- `tests/test_search.py` — unit tests for search module
- `tests/test_scheduler.py` — unit tests for scheduler module

**Modify:**
- `requirements.txt` — add pygame, plyer
- `downloader/__init__.py` — export new modules
- `downloader/engine.py` — accept `outtmpl` parameter for filename templates
- `gui/app.py` — replace with new shell (~400 lines) using components

---

## Task 1: Dependencies + theme.py

**Files:**
- Modify: `requirements.txt`
- Create: `gui/theme.py`

- [ ] Add new deps to `requirements.txt`:
```
pygame>=2.5.0
plyer>=2.1.0
```

- [ ] Create `gui/theme.py`:
```python
"""Color tokens and CTk widget style factories for the glassmorphism theme."""

COLORS = {
    "base":           "#0e0f14",
    "surface":        "#13151c",
    "glass":          "#16171d",
    "glass-border":   "#252730",
    "accent":         "#7c6af7",
    "accent-hover":   "#2a2560",
    "accent-active":  "#6355d4",
    "success":        "#4ade80",
    "error":          "#f87171",
    "scheduled":      "#fbbf24",
    "text-primary":   "#f0f0f5",
    "text-secondary": "#8b8fa8",
    # elevation layers
    "layer-0": "#0e0f14",
    "layer-1": "#13151c",
    "layer-2": "#16171d",
    "layer-3": "#1c1e28",
}

_STRIPE_COLORS = {
    "pending":     "#8b8fa8",
    "downloading": "#7c6af7",
    "converting":  "#a78bfa",
    "done":        "#4ade80",
    "failed":      "#f87171",
    "scheduled":   "#fbbf24",
}


def glass_frame() -> dict:
    return dict(fg_color=COLORS["glass"], border_width=1,
                border_color=COLORS["glass-border"], corner_radius=10)


def surface_frame() -> dict:
    return dict(fg_color=COLORS["surface"], border_width=1,
                border_color=COLORS["glass-border"], corner_radius=10)


def accent_button() -> dict:
    return dict(fg_color=COLORS["accent"], hover_color=COLORS["accent-active"],
                text_color=COLORS["text-primary"], corner_radius=8)


def ghost_button() -> dict:
    return dict(fg_color="transparent", hover_color=COLORS["accent-hover"],
                text_color=COLORS["text-secondary"], border_width=1,
                border_color=COLORS["glass-border"], corner_radius=8)


def pill_entry() -> dict:
    return dict(fg_color=COLORS["glass"], border_color=COLORS["glass-border"],
                corner_radius=22, text_color=COLORS["text-primary"])


def status_stripe(state: str) -> dict:
    color = _STRIPE_COLORS.get(state, _STRIPE_COLORS["pending"])
    return dict(fg_color=color, width=4, corner_radius=2)


def label_style(size: int = 13, secondary: bool = False) -> dict:
    color = COLORS["text-secondary"] if secondary else COLORS["text-primary"]
    return dict(text_color=color, font=("Segoe UI Variable", size))
```

- [ ] Install deps: `pip install pygame>=2.5.0 plyer>=2.1.0`

- [ ] Commit:
```bash
git add requirements.txt gui/theme.py
git commit -m "feat: add theme.py color tokens and glass style factories"
```

---

## Task 2: downloader/presets.py

**Files:**
- Create: `downloader/presets.py`
- Create: `tests/test_presets.py`

- [ ] Write failing test `tests/test_presets.py`:
```python
import json, os, tempfile
import pytest

def test_defaults_returned_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path / p.lstrip("~/")))
    from downloader.presets import load_presets, DEFAULT_PRESETS
    presets = load_presets()
    assert len(presets) == 3
    assert presets[0]["name"] == "Music 320"

def test_save_and_reload(tmp_path, monkeypatch):
    preset_file = tmp_path / ".ytdl_presets.json"
    monkeypatch.setattr("downloader.presets.PRESETS_PATH", str(preset_file))
    from importlib import reload
    import downloader.presets as m
    reload(m)
    custom = [{"name": "Test", "format_type": "audio", "codec": "mp3", "quality": "128"}]
    m.save_presets(custom)
    assert preset_file.exists()
    loaded = m.load_presets()
    assert loaded[0]["name"] == "Test"
```

- [ ] Run test: `pytest tests/test_presets.py -v` → expect FAIL (module not found)

- [ ] Create `downloader/presets.py`:
```python
"""Format preset persistence — load/save ~/.ytdl_presets.json."""
import json
import os
from typing import List, Dict

PRESETS_PATH = os.path.expanduser("~/.ytdl_presets.json")

DEFAULT_PRESETS: List[Dict] = [
    {"name": "Music 320",    "format_type": "audio", "codec": "mp3",  "quality": "320"},
    {"name": "Archive 1080p","format_type": "video", "codec": "mp4",  "quality": "1080p"},
    {"name": "Quick MP3",    "format_type": "audio", "codec": "mp3",  "quality": "192"},
]


def load_presets() -> List[Dict]:
    """Return saved presets, or defaults if file doesn't exist."""
    try:
        with open(PRESETS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return [p.copy() for p in DEFAULT_PRESETS]


def save_presets(presets: List[Dict]) -> None:
    """Persist presets list to disk."""
    with open(PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(presets, f, indent=2)
```

- [ ] Run test: `pytest tests/test_presets.py -v` → expect PASS

- [ ] Update `downloader/__init__.py` — add to exports:
```python
from .presets import load_presets, save_presets, DEFAULT_PRESETS
```

- [ ] Commit:
```bash
git add downloader/presets.py downloader/__init__.py tests/test_presets.py
git commit -m "feat: add format presets persistence module"
```

---

## Task 3: downloader/search.py

**Files:**
- Create: `downloader/search.py`
- Create: `tests/test_search.py`

- [ ] Write failing test `tests/test_search.py`:
```python
from unittest.mock import patch, MagicMock

def test_search_returns_five_results():
    fake_info = {
        "entries": [
            {"id": f"vid{i}", "title": f"Title {i}", "uploader": "Chan",
             "duration": 180, "thumbnail": "http://example.com/thumb.jpg"}
            for i in range(5)
        ]
    }
    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = fake_info
        from downloader.search import search_youtube
        results = search_youtube("test query")
    assert len(results) == 5
    assert results[0]["title"] == "Title 0"
    assert "url" in results[0]

def test_search_returns_empty_on_error():
    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.side_effect = Exception("network error")
        from downloader.search import search_youtube
        results = search_youtube("test query")
    assert results == []
```

- [ ] Run: `pytest tests/test_search.py -v` → expect FAIL

- [ ] Create `downloader/search.py`:
```python
"""YouTube search via yt-dlp ytsearch pseudo-URL."""
from typing import List, Dict
import yt_dlp


def search_youtube(query: str, max_results: int = 5) -> List[Dict]:
    """
    Return up to max_results YouTube search results for query.
    Each result: {url, title, uploader, duration_str, thumbnail}
    Returns [] on any error.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
        entries = info.get("entries") or []
        results = []
        for e in entries[:max_results]:
            vid_id = e.get("id", "")
            duration = e.get("duration") or 0
            mins, secs = divmod(int(duration), 60)
            results.append({
                "url":          f"https://www.youtube.com/watch?v={vid_id}",
                "title":        e.get("title", "Unknown"),
                "uploader":     e.get("uploader") or e.get("channel", ""),
                "duration_str": f"{mins}:{secs:02d}",
                "thumbnail":    e.get("thumbnail", ""),
            })
        return results
    except Exception:
        return []
```

- [ ] Run: `pytest tests/test_search.py -v` → expect PASS

- [ ] Update `downloader/__init__.py` — add: `from .search import search_youtube`

- [ ] Commit:
```bash
git add downloader/search.py downloader/__init__.py tests/test_search.py
git commit -m "feat: add YouTube search module"
```

---

## Task 4: downloader/scheduler.py

**Files:**
- Create: `downloader/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] Write failing test `tests/test_scheduler.py`:
```python
import time
from unittest.mock import MagicMock, patch

def test_schedule_fires_callback_at_time():
    from downloader.scheduler import DownloadScheduler
    fired = []
    sched = DownloadScheduler()
    sched.start()
    # Schedule 1 second from now
    fire_at = time.time() + 1
    sched.add("item-1", fire_at, lambda: fired.append("item-1"))
    time.sleep(2.5)
    sched.stop()
    assert "item-1" in fired

def test_schedule_cancel_prevents_fire():
    from downloader.scheduler import DownloadScheduler
    fired = []
    sched = DownloadScheduler()
    sched.start()
    fire_at = time.time() + 2
    sched.add("item-2", fire_at, lambda: fired.append("item-2"))
    sched.cancel("item-2")
    time.sleep(3)
    sched.stop()
    assert "item-2" not in fired
```

- [ ] Run: `pytest tests/test_scheduler.py -v` → expect FAIL

- [ ] Create `downloader/scheduler.py`:
```python
"""Background scheduler: fires callbacks at scheduled wall-clock times."""
import threading
import time
from typing import Callable, Dict, Tuple


class DownloadScheduler:
    """
    Thread-safe scheduler. Each item has an id, a UNIX timestamp to fire at,
    and a zero-arg callback. Polls every 15 seconds.
    """

    def __init__(self):
        self._items: Dict[str, Tuple[float, Callable]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def add(self, item_id: str, fire_at: float, callback: Callable) -> None:
        with self._lock:
            self._items[item_id] = (fire_at, callback)

    def cancel(self, item_id: str) -> None:
        with self._lock:
            self._items.pop(item_id, None)

    def get_scheduled(self) -> Dict[str, float]:
        """Return {item_id: fire_at} for all pending items."""
        with self._lock:
            return {k: v[0] for k, v in self._items.items()}

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            to_fire = []
            with self._lock:
                for item_id, (fire_at, cb) in list(self._items.items()):
                    if now >= fire_at:
                        to_fire.append((item_id, cb))
                for item_id, _ in to_fire:
                    del self._items[item_id]
            for item_id, cb in to_fire:
                try:
                    cb()
                except Exception:
                    pass
            self._stop_event.wait(1)  # 1-second poll so tests run in reasonable time
```

- [ ] Run: `pytest tests/test_scheduler.py -v` → expect PASS

- [ ] Update `downloader/__init__.py` — add: `from .scheduler import DownloadScheduler`

- [ ] Commit:
```bash
git add downloader/scheduler.py downloader/__init__.py tests/test_scheduler.py
git commit -m "feat: add download scheduler module"
```

---

## Task 5: engine.py — outtmpl support

**Files:**
- Modify: `downloader/engine.py`

- [ ] Find the `start_download` function signature in `engine.py`. Add `outtmpl_template: str = None` parameter.

- [ ] Add a token translation helper near the top of `engine.py` (after imports):
```python
_OUTTMPL_TOKEN_MAP = {
    "{title}":          "%(title)s",
    "{artist}":         "%(artist)s",
    "{uploader}":       "%(uploader)s",
    "{date}":           "%(upload_date)s",
    "{playlist_index}": "%(playlist_index)s",
    # {quality} and {ext} are handled separately below
}

def _translate_outtmpl(template: str, quality_label: str) -> str:
    """Translate spec token syntax ({title}) to yt-dlp syntax (%(title)s)."""
    result = template
    for spec_token, ytdlp_token in _OUTTMPL_TOKEN_MAP.items():
        result = result.replace(spec_token, ytdlp_token)
    result = result.replace("{quality}", quality_label or "")
    result = result.replace("{ext}", "%(ext)s")
    return result
```

- [ ] Inside the function where `ydl_opts` dict is built, add:
```python
quality_label = audio_format_label or video_quality_label or ""
if outtmpl_template:
    translated = _translate_outtmpl(outtmpl_template, quality_label)
    ydl_opts["outtmpl"] = os.path.join(output_dir, translated)
else:
    ydl_opts["outtmpl"] = os.path.join(output_dir, "%(title)s.%(ext)s")
```

- [ ] Update `downloader/__init__.py` to re-export `start_download` (already exported — no change needed if it's a `from .engine import *` or explicit export).

- [ ] Run existing app briefly to confirm no crash: `python main.py` → app should open normally.

- [ ] Commit:
```bash
git add downloader/engine.py
git commit -m "feat: accept outtmpl_template in start_download for smart filenames"
```

---

## Task 6: gui/components/track_row.py

**Files:**
- Create: `gui/components/__init__.py`
- Create: `gui/components/track_row.py`

- [ ] Create `gui/components/__init__.py` (empty).

- [ ] Create `gui/components/track_row.py`:
```python
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
```

- [ ] Verify no syntax errors: `python -c "from gui.components.track_row import TrackRow; print('OK')"`

- [ ] Commit:
```bash
git add gui/components/__init__.py gui/components/track_row.py
git commit -m "feat: add TrackRow component with stripe, shimmer, expand"
```

---

## Task 7: gui/components/preset_pills.py

**Files:**
- Create: `gui/components/preset_pills.py`

- [ ] Create `gui/components/preset_pills.py`:
```python
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
```

- [ ] Verify: `python -c "from gui.components.preset_pills import PresetPills; print('OK')"`

- [ ] Commit:
```bash
git add gui/components/preset_pills.py
git commit -m "feat: add PresetPills component with right-click edit menu"
```

---

## Task 8: gui/components/command_bar.py

**Files:**
- Create: `gui/components/command_bar.py`

- [ ] Create `gui/components/command_bar.py`:
```python
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
```

- [ ] Verify: `python -c "from gui.components.command_bar import CommandBar; print('OK')"`

- [ ] Commit:
```bash
git add gui/components/command_bar.py
git commit -m "feat: add CommandBar component with URL detection and search debounce"
```

---

## Task 9: gui/components/queue_view.py

**Files:**
- Create: `gui/components/queue_view.py`

- [ ] Create `gui/components/queue_view.py`:
```python
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
```

- [ ] Verify: `python -c "from gui.components.queue_view import QueueView; print('OK')"`

- [ ] Commit:
```bash
git add gui/components/queue_view.py
git commit -m "feat: add QueueView component with reorder, schedule, context menu"
```

---

## Task 10: gui/components/player.py

**Files:**
- Create: `gui/components/player.py`

- [ ] Create `gui/components/player.py`:
```python
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
```

- [ ] Verify: `python -c "from gui.components.player import PlayerView; print('OK')"`

- [ ] Commit:
```bash
git add gui/components/player.py
git commit -m "feat: add PlayerView audio player with pygame.mixer"
```

---

## Task 11: gui/components/history_view.py

**Files:**
- Create: `gui/components/history_view.py`

- [ ] Create `gui/components/history_view.py`:
```python
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
```

- [ ] Verify: `python -c "from gui.components.history_view import HistoryView; print('OK')"`

- [ ] Commit:
```bash
git add gui/components/history_view.py
git commit -m "feat: add HistoryView with search, format filter, CSV export"
```

---

## Task 12: gui/components/settings_panel.py

**Files:**
- Create: `gui/components/settings_panel.py`

- [ ] Create `gui/components/settings_panel.py`:
```python
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
```

- [ ] Verify: `python -c "from gui.components.settings_panel import SettingsPanel; print('OK')"`

- [ ] Commit:
```bash
git add gui/components/settings_panel.py
git commit -m "feat: add SettingsPanel slide-in overlay with all settings fields"
```

---

## Task 13: Export new modules from downloader/__init__.py

**Must happen before Task 14** — `gui/app.py` imports these at the top level.

**Files:**
- Modify: `downloader/__init__.py`

- [ ] Read current `downloader/__init__.py` and add missing exports:
```python
from .search import search_youtube
from .presets import load_presets, save_presets, DEFAULT_PRESETS
from .scheduler import DownloadScheduler
```

- [ ] Verify: `python -c "from downloader import search_youtube, load_presets, DownloadScheduler; print('OK')"`

- [ ] Commit:
```bash
git add downloader/__init__.py
git commit -m "chore: export search, presets, scheduler from downloader package"
```

---

## Task 14: Rewrite gui/app.py

**Files:**
- Modify: `gui/app.py` (full rewrite — keep the old file as `gui/app_old.py` first)

- [ ] Back up: `cp gui/app.py gui/app_old.py`

- [ ] Rewrite `gui/app.py`:
```python
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
    _DND_OK = True
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
from downloader.history import add as history_add
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
        from downloader.search import search_youtube
        results = search_youtube(query)
        self.after(0, lambda: self._show_search_results(results, query))

    def _show_search_results(self, results: list, query: str):
        self._cmd_bar.update_badge(f"")
        for w in self._search_frame.winfo_children():
            w.destroy()

        if not results:
            ctk.CTkLabel(self._search_frame,
                          text=f"No results for "{query}"",
                          **theme.label_style(13, secondary=True)).pack(pady=20)
        else:
            ctk.CTkLabel(self._search_frame,
                          text=f"Results for "{query}"",
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

        # Map preset to engine params
        if fmt_type == "audio":
            format_type = FORMAT_AUDIO
            audio_fmt = (f"{codec.upper()} - {quality} kbps" if quality != "0"
                          else f"{codec.upper()} (lossless)")
            video_quality = None
        else:
            format_type = FORMAT_MP4
            audio_fmt = None
            video_quality = quality

        os.makedirs(self._cfg["output_dir"], exist_ok=True)

        self._msg_queue, self._cancel_event = start_download(
            url=item.url,
            format_type=format_type,
            audio_format_label=audio_fmt,
            video_quality_label=video_quality,
            output_dir=self._cfg["output_dir"],
            workers=self._cfg.get("workers", 3),
            cookies_file=self._cfg.get("cookies_file") or None,
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
            idx = data
            if idx in self._track_rows:
                self._track_rows[idx].set_downloading()

        elif msg_type == MSG_TRACK_PERCENT:
            idx, pct, speed_str, downloaded, total = data
            if idx in self._track_rows:
                self._track_rows[idx].update_progress(pct, speed_str, downloaded, total)
            if speed_str:
                self._speed_lbl.configure(text=f"⚡ {speed_str}")

        elif msg_type == MSG_TRACK_PHASE:
            idx, phase = data
            if idx in self._track_rows:
                self._track_rows[idx].set_phase(phase)

        elif msg_type == MSG_TRACK_DONE:
            # data is (idx, file_path) — engine.py must send file_path with MSG_TRACK_DONE
            # If engine only sends idx (current behavior), unpack safely:
            if isinstance(data, tuple):
                idx, file_path = data[0], data[1] if len(data) > 1 else None
            else:
                idx, file_path = data, None
            if idx in self._track_rows:
                self._track_rows[idx].set_done(file_path=file_path)
                self._queue_view.update_item_state(idx, "done")
            # Note: if engine.py currently only sends idx for MSG_TRACK_DONE,
            # update engine.py to send (idx, output_filepath) so Open File works.

        elif msg_type == MSG_TRACK_FAILED:
            idx, err = data
            if idx in self._track_rows:
                self._track_rows[idx].set_failed(err)
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
            from downloader.history import add as history_add
            for t in result.tracks:
                if t.status == "done":
                    preset = self._active_preset or {}
                    history_add(
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
            self._msg_queue, self._cancel_event = retry_failed(
                self._playlist_result,
                format_type=FORMAT_AUDIO,
                output_dir=self._cfg["output_dir"],
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
            item = items[idx]
            self._scheduler.add(
                f"item-{idx}",
                timestamp,
                lambda: self.after(0, self._start_next_download),
            )

    # ── Settings ─────────────────────────────────────────────────────────

    def _toggle_settings(self):
        info = self._settings_panel.place_info()
        if not info:
            # First show: place it
            self._settings_panel.place(relx=1.0, rely=0, anchor="ne",
                                        relheight=1.0,
                                        width=SettingsPanel.PANEL_WIDTH)
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


def run(writable_root: str = None):
    """Entry point — creates root window and starts the app."""
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
```

- [ ] Update `main.py` — ensure it calls `gui.app.run()`:
```python
# At the bottom of main.py, the existing call should be:
from gui.app import run
run(writable_root=writable_root)
```

- [ ] Test: `python main.py` — app should open with new UI. Verify:
  - Dark base background visible
  - Command bar renders as glass pill
  - Preset pills visible (Music 320, Archive 1080p, Quick MP3)
  - Bottom nav bar visible
  - ⚙ button opens settings overlay

- [ ] Commit:
```bash
git add gui/app.py gui/app_old.py main.py
git commit -m "feat: rewrite app.py with command-bar layout, all components wired"
```

---

## Task 14: Final integration test

- [ ] Run: `pip install -r requirements.txt` (installs pygame + plyer)

- [ ] Run: `python main.py` — smoke test all features:
  1. Paste a YouTube URL → badge shows "YouTube detected" → press Enter → item appears in queue → download starts → track row shows progress
  2. Type text in command bar → 500ms later search fires → results appear as cards → click Add → item queued
  3. Click preset pill → active pill turns violet
  4. Right-click a preset → Edit → rename → saved
  5. Click + pill → creates new preset from current settings
  6. Open settings (⚙) → panel slides in → change output folder → Apply → panel slides out
  7. Right-click queue item → Schedule for → set a time → countdown badge appears
  8. Click History tab → search bar filters entries
  9. Click Player tab → load an audio file → play/pause works

- [ ] Run unit tests: `pytest tests/ -v` → all pass

- [ ] If anything is broken, fix before proceeding.

- [ ] Delete backup: `rm gui/app_old.py`

- [ ] Final commit:
```bash
git add -A
git commit -m "feat: complete YouTube Downloader redesign v4.0

Glassmorphism UI, command-bar layout, format presets,
queue manager, YouTube search, batch import, download scheduler,
audio player (pygame), smart filenames, enhanced history.
"
```
