# UI Redesign v5.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hidden settings panel with an always-visible inline options row (format, quality, toggles) and a collapsible Advanced panel, remove preset pills, and improve the nav bar active state + queue badge.

**Architecture:** New `OptionsRow` component owns all format/quality/toggle state and exposes `get_format_settings()`. `app.py` replaces `_active_preset` reads with `self._options_row.get_format_settings()` at every download call site. Settings panel is slimmed to Telegram + yt-dlp update only.

**Tech Stack:** Python 3.14, CustomTkinter 5.2.2, tkinter, `downloader/presets.py`, `downloader/ytdlp_updater.py`

**Spec:** `docs/superpowers/specs/2026-03-20-ui-redesign-v5.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `gui/components/options_row.py` | OptionsRow widget: format toggle, quality dropdown, SponsorBlock/Subtitles toggles, Save as Preset, Advanced inline panel |
| **Modify** | `gui/app.py` | Remove PresetPills; add OptionsRow; update `_start_next_download` + `_retry_track` + `_get_current_format`; remove `_on_preset_selected` |
| **Modify** | `gui/components/settings_panel.py` | Remove output folder / workers / template / cookies; add yt-dlp update section |
| **Modify** | `gui/app.py` (nav bar) | Queue badge count; active tab accent style |
| **Kept unchanged** | `gui/components/preset_pills.py` | File kept on disk; no longer imported |
| **Test** | `tests/test_options_row.py` | Unit tests for `get_format_settings()` and `set_format_settings()` |

---

## Quality Label → Engine Parameter Map

Used by `OptionsRow.get_format_settings()` and `_PresetNameDialog`:

```python
_AUDIO_MAP = {
    "128 kbps": {"audio_format_name": "MP3 - 128 kbps", "codec": "mp3", "quality": "128"},
    "192 kbps": {"audio_format_name": "MP3 - 192 kbps", "codec": "mp3", "quality": "192"},
    "320 kbps": {"audio_format_name": "MP3 - 320 kbps", "codec": "mp3", "quality": "320"},
    "FLAC":     {"audio_format_name": "FLAC (lossless)", "codec": "flac", "quality": "0"},
}
_VIDEO_MAP = {
    "720p":  {"codec": "mp4", "quality": "720"},
    "1080p": {"codec": "mp4", "quality": "1080"},
    "4K":    {"codec": "mp4", "quality": "2160"},
}
```

---

## Task 1: Create `gui/components/options_row.py`

**Files:**
- Create: `gui/components/options_row.py`
- Create: `tests/test_options_row.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_options_row.py
import pytest
import tkinter as tk
import customtkinter as ctk

@pytest.fixture(scope="module")
def root():
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()

def test_default_audio_format(root):
    from gui.components.options_row import OptionsRow
    row = OptionsRow(root, on_change=lambda d: None, initial={})
    s = row.get_format_settings()
    assert s["format_type"] == "audio"
    assert s["audio_format_name"] == "MP3 - 320 kbps"
    assert s["codec"] == "mp3"
    assert s["quality"] == "320"
    assert s["remove_sponsors"] is True
    assert s["write_subs"] is False
    assert s["sub_langs"] == []
    row.destroy()

def test_switch_to_video(root):
    from gui.components.options_row import OptionsRow
    row = OptionsRow(root, on_change=lambda d: None, initial={})
    row.set_format_settings({"format_type": "video", "codec": "mp4", "quality": "1080"})
    s = row.get_format_settings()
    assert s["format_type"] == "video"
    assert s["quality"] == "1080"
    assert s["codec"] == "mp4"
    assert s["audio_format_name"] == ""
    row.destroy()

def test_flac_quality(root):
    from gui.components.options_row import OptionsRow
    row = OptionsRow(root, on_change=lambda d: None, initial={})
    row.set_format_settings({"format_type": "audio", "codec": "flac", "quality": "0"})
    s = row.get_format_settings()
    assert s["audio_format_name"] == "FLAC (lossless)"
    assert s["quality"] == "0"
    row.destroy()

def test_on_change_callback(root):
    calls = []
    from gui.components.options_row import OptionsRow
    row = OptionsRow(root, on_change=lambda d: calls.append(d), initial={})
    row.set_format_settings({"format_type": "video", "codec": "mp4", "quality": "720"})
    # on_change fires on set_format_settings
    assert len(calls) >= 1
    assert calls[-1]["format_type"] == "video"
    row.destroy()
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd "C:/Users/Rohan/Documents/Youtube download"
python -m pytest tests/test_options_row.py -v 2>&1 | head -30
```

Expected: `ImportError` — `options_row` does not exist yet.

- [ ] **Step 3: Create `gui/components/options_row.py`**

```python
"""
Inline options row: format toggle, quality dropdown, SponsorBlock/Subtitles
toggles, Save as Preset button, and collapsible Advanced panel.

Public API:
    get_format_settings() -> dict   # ready for start_download() call sites
    set_format_settings(dict)       # apply preset to widgets
"""
import os
import tkinter as tk
import customtkinter as ctk
from typing import Callable, Dict, Any

from gui.theme import COLORS, ghost_button, accent_button, label_style
from downloader.presets import load_presets, save_presets

# ── Quality maps ────────────────────────────────────────────────────────────

_AUDIO_LABELS  = ["128 kbps", "192 kbps", "320 kbps", "FLAC"]
_VIDEO_LABELS  = ["720p", "1080p", "4K"]
_AUDIO_DEFAULT = "320 kbps"
_VIDEO_DEFAULT = "1080p"

_AUDIO_MAP = {
    "128 kbps": {"audio_format_name": "MP3 - 128 kbps", "codec": "mp3", "quality": "128"},
    "192 kbps": {"audio_format_name": "MP3 - 192 kbps", "codec": "mp3", "quality": "192"},
    "320 kbps": {"audio_format_name": "MP3 - 320 kbps", "codec": "mp3", "quality": "320"},
    "FLAC":     {"audio_format_name": "FLAC (lossless)", "codec": "flac", "quality": "0"},
}
_VIDEO_MAP = {
    "720p":  {"codec": "mp4", "quality": "720"},
    "1080p": {"codec": "mp4", "quality": "1080"},
    "4K":    {"codec": "mp4", "quality": "2160"},
}

# Map (format_type, codec, quality) → display label for set_format_settings
_REVERSE_AUDIO = {(v["codec"], v["quality"]): k for k, v in _AUDIO_MAP.items()}
_REVERSE_VIDEO = {v["quality"]: k for k, v in _VIDEO_MAP.items()}


class OptionsRow(ctk.CTkFrame):
    """
    Horizontal options row + inline collapsible Advanced panel.
    on_change(dict) fired on every widget change.
    """

    def __init__(self, parent, on_change: Callable[[Dict[str, Any]], None],
                 initial: Dict[str, Any], **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._on_change = on_change
        self._adv_visible = False

        # Per-format last-used quality memory
        self._audio_quality = _AUDIO_DEFAULT
        self._video_quality = _VIDEO_DEFAULT

        # Advanced cfg (mirrors app._cfg keys)
        self._adv_cfg: Dict[str, Any] = {
            "output_dir":   initial.get("output_dir", ""),
            "workers":      initial.get("workers", 3),
            "outtmpl":      initial.get("outtmpl", "{title}.{ext}"),
            "cookies_file": initial.get("cookies_file", ""),
        }

        self._build()

        # Apply initial format if provided
        if initial.get("format_type"):
            self.set_format_settings(initial)

    # ── Build ────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # Row 0: controls
        row_frame = ctk.CTkFrame(self, fg_color="transparent")
        row_frame.grid(row=0, column=0, sticky="ew")
        row_frame.grid_columnconfigure(99, weight=1)  # spacer col before Advanced

        col = 0

        # Format segmented button
        self._fmt_var = tk.StringVar(value="🎵 Audio")
        self._fmt_seg = ctk.CTkSegmentedButton(
            row_frame,
            values=["🎵 Audio", "📼 Video"],
            variable=self._fmt_var,
            command=self._on_format_change,
            fg_color=COLORS["glass"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent-active"],
            unselected_color=COLORS["glass"],
            unselected_hover_color=COLORS["layer-3"],
            text_color=COLORS["text-primary"],
            font=("Segoe UI Variable", 12),
            height=30,
        )
        self._fmt_seg.grid(row=0, column=col, padx=(0, 6))
        col += 1

        # Quality dropdown
        self._quality_var = tk.StringVar(value=_AUDIO_DEFAULT)
        self._quality_menu = ctk.CTkOptionMenu(
            row_frame,
            variable=self._quality_var,
            values=_AUDIO_LABELS,
            command=lambda _: self._fire_change(),
            fg_color=COLORS["glass"],
            button_color=COLORS["glass-border"],
            button_hover_color=COLORS["layer-3"],
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["layer-3"],
            text_color=COLORS["text-primary"],
            font=("Segoe UI Variable", 12),
            height=30,
            width=110,
        )
        self._quality_menu.grid(row=0, column=col, padx=(0, 6))
        col += 1

        # SponsorBlock toggle
        self._sponsor_on = True
        self._sponsor_btn = ctk.CTkButton(
            row_frame, text="● SponsorBlock", height=30, width=0,
            command=self._toggle_sponsor,
            fg_color=COLORS["glass"],
            hover_color=COLORS["layer-3"],
            text_color=COLORS["success"],
            border_width=1, border_color="#4ade8044",
            corner_radius=8,
            font=("Segoe UI Variable", 12),
        )
        self._sponsor_btn.grid(row=0, column=col, padx=(0, 6))
        col += 1

        # Subtitles toggle
        self._subs_on = False
        self._subs_btn = ctk.CTkButton(
            row_frame, text="○ Subtitles", height=30, width=0,
            command=self._toggle_subs,
            fg_color=COLORS["glass"],
            hover_color=COLORS["layer-3"],
            text_color=COLORS["text-secondary"],
            border_width=1, border_color=COLORS["glass-border"],
            corner_radius=8,
            font=("Segoe UI Variable", 12),
        )
        self._subs_btn.grid(row=0, column=col, padx=(0, 6))
        col += 1

        # Save as Preset
        ctk.CTkButton(
            row_frame, text="☆ Save as Preset", height=30, width=0,
            command=self._save_preset,
            **ghost_button(),
            font=("Segoe UI Variable", 12),
        ).grid(row=0, column=col, padx=(0, 6))
        col += 1

        # Spacer (pushes Advanced to right)
        row_frame.grid_columnconfigure(col, weight=1)
        col += 1

        # Advanced toggle (right-aligned)
        self._adv_btn = ctk.CTkButton(
            row_frame, text="⚙ Advanced ▾", height=30, width=0,
            command=self._toggle_adv,
            **ghost_button(),
            font=("Segoe UI Variable", 12),
        )
        self._adv_btn.grid(row=0, column=col)

        # Row 1: Advanced panel (hidden initially)
        self._adv_frame = ctk.CTkFrame(
            self, fg_color=COLORS["surface"],
            border_width=1, border_color=COLORS["glass-border"],
            corner_radius=8,
        )
        self._build_adv()
        # Not shown until toggled

    def _build_adv(self):
        f = self._adv_frame
        f.grid_columnconfigure(0, weight=1)
        f.grid_columnconfigure(1, weight=1)

        def _lbl(text, r, c):
            ctk.CTkLabel(f, text=text, **label_style(11, secondary=True)).grid(
                row=r, column=c, sticky="w", padx=(14, 4), pady=(10, 0))

        def _entry(row, col, var, placeholder=""):
            return ctk.CTkEntry(
                f, textvariable=var, placeholder_text=placeholder,
                fg_color=COLORS["glass"], border_color=COLORS["glass-border"],
                text_color=COLORS["text-primary"], corner_radius=7, height=30,
                font=("Segoe UI Variable", 12),
            )

        # Output folder
        _lbl("Output Folder", 0, 0)
        self._folder_var = tk.StringVar(value=self._adv_cfg["output_dir"])
        folder_row = ctk.CTkFrame(f, fg_color="transparent")
        folder_row.grid(row=1, column=0, sticky="ew", padx=(14, 6), pady=(2, 8))
        folder_row.grid_columnconfigure(0, weight=1)
        _entry(1, 0, self._folder_var).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(folder_row, text="…", width=30, height=30,
                      command=self._pick_folder, **ghost_button()).grid(row=0, column=1)
        self._folder_var.trace_add("write", lambda *_: self._adv_change())

        # Workers
        _lbl("Parallel Downloads", 0, 1)
        self._workers_var = tk.IntVar(value=self._adv_cfg["workers"])
        worker_row = ctk.CTkFrame(f, fg_color="transparent")
        worker_row.grid(row=1, column=1, sticky="ew", padx=(4, 14), pady=(2, 8))
        worker_row.grid_columnconfigure(0, weight=1)
        ctk.CTkSlider(
            worker_row, from_=1, to=8, number_of_steps=7,
            variable=self._workers_var,
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            fg_color=COLORS["layer-3"],
            command=lambda _: self._adv_change(),
        ).grid(row=0, column=0, sticky="ew")
        self._workers_lbl = ctk.CTkLabel(
            worker_row, text=f"{self._workers_var.get()} workers",
            **label_style(11, secondary=True))
        self._workers_lbl.grid(row=0, column=1, padx=(6, 0))
        self._workers_var.trace_add(
            "write",
            lambda *_: self._workers_lbl.configure(
                text=f"{self._workers_var.get()} workers"))

        # Filename template
        _lbl("Filename Template", 2, 0)
        self._template_var = tk.StringVar(value=self._adv_cfg["outtmpl"])
        tmpl_row = ctk.CTkFrame(f, fg_color="transparent")
        tmpl_row.grid(row=3, column=0, sticky="ew", padx=(14, 6), pady=(2, 0))
        tmpl_row.grid_columnconfigure(0, weight=1)
        _entry(3, 0, self._template_var).grid(row=0, column=0, sticky="ew")
        self._preview_lbl = ctk.CTkLabel(
            f, text="", **label_style(10, secondary=True))
        self._preview_lbl.grid(row=4, column=0, sticky="w", padx=14, pady=(0, 8))
        self._template_var.trace_add("write", self._update_tmpl_preview)
        self._update_tmpl_preview()
        self._template_var.trace_add("write", lambda *_: self._adv_change())

        # Cookies
        _lbl("Cookies File", 2, 1)
        self._cookie_var = tk.StringVar(value=self._adv_cfg["cookies_file"])
        cookie_row = ctk.CTkFrame(f, fg_color="transparent")
        cookie_row.grid(row=3, column=1, sticky="ew", padx=(4, 14), pady=(2, 8))
        cookie_row.grid_columnconfigure(0, weight=1)
        _entry(3, 1, self._cookie_var,
               placeholder="(none — for age-restricted)").grid(
            row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(cookie_row, text="…", width=30, height=30,
                      command=self._pick_cookie, **ghost_button()).grid(row=0, column=1)
        self._cookie_var.trace_add("write", lambda *_: self._adv_change())

    # ── Event handlers ───────────────────────────────────────────────────

    def _on_format_change(self, value: str):
        is_audio = "Audio" in value
        labels = _AUDIO_LABELS if is_audio else _VIDEO_LABELS
        default = self._audio_quality if is_audio else self._video_quality
        self._quality_menu.configure(values=labels)
        self._quality_var.set(default)
        self._fire_change()

    def _toggle_sponsor(self):
        self._sponsor_on = not self._sponsor_on
        if self._sponsor_on:
            self._sponsor_btn.configure(
                text="● SponsorBlock",
                text_color=COLORS["success"],
                border_color="#4ade8044")
        else:
            self._sponsor_btn.configure(
                text="○ SponsorBlock",
                text_color=COLORS["text-secondary"],
                border_color=COLORS["glass-border"])
        self._fire_change()

    def _toggle_subs(self):
        self._subs_on = not self._subs_on
        if self._subs_on:
            self._subs_btn.configure(
                text="● Subtitles",
                text_color=COLORS["success"],
                border_color="#4ade8044")
        else:
            self._subs_btn.configure(
                text="○ Subtitles",
                text_color=COLORS["text-secondary"],
                border_color=COLORS["glass-border"])
        self._fire_change()

    def _toggle_adv(self):
        self._adv_visible = not self._adv_visible
        if self._adv_visible:
            self._adv_frame.grid(row=1, column=0, sticky="ew", pady=(6, 0))
            self._adv_btn.configure(text="⚙ Advanced ▴")
        else:
            self._adv_frame.grid_remove()
            self._adv_btn.configure(text="⚙ Advanced ▾")

    def _adv_change(self):
        self._adv_cfg.update({
            "output_dir":   self._folder_var.get(),
            "workers":      self._workers_var.get(),
            "outtmpl":      self._template_var.get(),
            "cookies_file": self._cookie_var.get(),
        })
        self._fire_change()

    def _fire_change(self):
        self._on_change(self.get_format_settings())

    def _update_tmpl_preview(self, *_):
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

    def _pick_folder(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(initialdir=self._folder_var.get() or ".")
        if path:
            self._folder_var.set(path)

    def _pick_cookie(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            self._cookie_var.set(path)

    def _save_preset(self):
        dialog = _PresetNameDialog(self, self.get_format_settings())
        self.wait_window(dialog)

    # ── Public API ───────────────────────────────────────────────────────

    def get_format_settings(self) -> Dict[str, Any]:
        """Return dict ready for start_download() call sites."""
        quality_label = self._quality_var.get()
        is_audio = "Audio" in self._fmt_var.get()

        if is_audio:
            m = _AUDIO_MAP.get(quality_label, _AUDIO_MAP[_AUDIO_DEFAULT])
            result = {
                "format_type":        "audio",
                "audio_format_name":  m["audio_format_name"],
                "quality_name":       m["audio_format_name"],
                "codec":              m["codec"],
                "quality":            m["quality"],
            }
        else:
            m = _VIDEO_MAP.get(quality_label, _VIDEO_MAP[_VIDEO_DEFAULT])
            result = {
                "format_type":        "video",
                "audio_format_name":  "",
                "quality_name":       quality_label,  # e.g. "1080p"
                "codec":              m["codec"],
                "quality":            m["quality"],
            }

        result.update({
            "remove_sponsors": self._sponsor_on,
            "write_subs":      self._subs_on,
            "sub_langs":       ["en"] if self._subs_on else [],
        })
        result.update(self._adv_cfg)
        return result

    def set_format_settings(self, settings: Dict[str, Any]) -> None:
        """Apply a preset dict (format_type, codec, quality keys) to widgets."""
        fmt = settings.get("format_type", "audio")
        codec = settings.get("codec", "mp3")
        quality = settings.get("quality", "320")

        if fmt == "audio":
            self._fmt_var.set("🎵 Audio")
            self._quality_menu.configure(values=_AUDIO_LABELS)
            label = _REVERSE_AUDIO.get((codec, quality), _AUDIO_DEFAULT)
            self._quality_var.set(label)
            self._audio_quality = label
        else:
            self._fmt_var.set("📼 Video")
            self._quality_menu.configure(values=_VIDEO_LABELS)
            label = _REVERSE_VIDEO.get(quality, _VIDEO_DEFAULT)
            self._quality_var.set(label)
            self._video_quality = label

        self._fire_change()


class _PresetNameDialog(ctk.CTkToplevel):
    def __init__(self, parent, settings: Dict[str, Any]):
        super().__init__(parent)
        self.title("Save Preset")
        self.geometry("300x150")
        self.grab_set()
        self.configure(fg_color=COLORS["surface"])
        self._settings = settings

        ctk.CTkLabel(self, text="Preset name:", **label_style(12)).pack(
            anchor="w", padx=20, pady=(16, 2))
        self._name_var = tk.StringVar()
        ctk.CTkEntry(self, textvariable=self._name_var, height=34).pack(
            fill="x", padx=20)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=12)
        ctk.CTkButton(btn_row, text="Save", width=90, command=self._save,
                      **accent_button()).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cancel", width=90, command=self.destroy,
                      **ghost_button()).pack(side="left")

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            return
        from downloader.presets import load_presets, save_presets
        presets = load_presets()
        preset = {
            "name":        name,
            "format_type": self._settings.get("format_type", "audio"),
            "codec":       self._settings.get("codec", "mp3"),
            "quality":     self._settings.get("quality", "320"),
        }
        presets.append(preset)
        save_presets(presets)
        self.destroy()
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd "C:/Users/Rohan/Documents/Youtube download"
python -m pytest tests/test_options_row.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add gui/components/options_row.py tests/test_options_row.py
git commit -m "feat: add OptionsRow component with inline Advanced panel"
```

---

## Task 2: Wire OptionsRow into `gui/app.py`

**Files:**
- Modify: `gui/app.py`

Remove PresetPills; add OptionsRow; update `_build_ui`, `_start_next_download`, `_retry_track`, `_get_current_format`; remove `_on_preset_selected`.

- [ ] **Step 1: Update imports in `gui/app.py`**

Remove these lines (around line 35–36 and line 41):
```python
from gui.components.preset_pills import PresetPills     # REMOVE
```
```python
from downloader.presets import load_presets             # REMOVE (no longer needed directly)
```

Add after the existing component imports:
```python
from gui.components.options_row import OptionsRow
```

- [ ] **Step 2: Replace PresetPills block in `_build_ui`**

Find this block (around lines 128–138):
```python
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
```

Replace with:
```python
        self._options_row = OptionsRow(
            cmd_area,
            on_change=self._on_options_change,
            initial=dict(self._cfg),
        )
        self._options_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
```

- [ ] **Step 3: Add `_on_options_change` handler and remove stale methods**

Add new method after `_build_ui`:
```python
    def _on_options_change(self, settings: dict):
        """Called whenever OptionsRow changes — merge into cfg."""
        self._cfg.update({
            k: v for k, v in settings.items()
            if k in ("output_dir", "workers", "outtmpl", "cookies_file")
        })
```

Remove (or leave as dead code with a comment) these two methods:
```python
    def _on_preset_selected(self, preset: dict):   # REMOVE
    def _get_current_format(self) -> Dict:          # REMOVE
```

Also remove `self._active_preset` usage in `__init__` (line ~83):
```python
        self._active_preset: Optional[Dict] = None  # REMOVE this line
```

- [ ] **Step 4: Update `_start_next_download` to read from OptionsRow**

Replace the preset-reading block (lines ~363–378):
```python
        preset = self._active_preset or load_presets()[0]
        fmt_type = preset.get("format_type", "audio")
        codec    = preset.get("codec", "mp3")
        quality  = preset.get("quality", "320")

        # Map preset to engine params.
        if fmt_type == "audio":
            format_type = FORMAT_AUDIO
            audio_format_name = (f"{codec.upper()} - {quality} kbps" if quality != "0"
                                  else f"{codec.upper()} (lossless)")
            quality_name = audio_format_name
        else:
            format_type = FORMAT_MP4
            audio_format_name = ""
            quality_name = quality
```

Replace with:
```python
        fmt = self._options_row.get_format_settings()
        if fmt["format_type"] == "audio":
            format_type = FORMAT_AUDIO
            audio_format_name = fmt["audio_format_name"]
            quality_name      = fmt["quality_name"]
        else:
            format_type       = FORMAT_MP4
            audio_format_name = ""
            quality_name      = fmt["quality_name"]
```

Also update the `start_download` call to pass the new toggle params (after `cookiefile=`):
```python
        self._msg_queue, self._cancel_event = start_download(
            url=item.url,
            format_type=format_type,
            quality_name=quality_name,
            audio_format_name=audio_format_name,
            output_dir=self._cfg["output_dir"],
            max_workers=self._cfg.get("workers", DEFAULT_WORKERS),
            cookiefile=self._cfg.get("cookies_file") or None,
            outtmpl_template=self._cfg.get("outtmpl") or None,
            remove_sponsors=fmt.get("remove_sponsors", True),
            write_subs=fmt.get("write_subs", False),
            sub_langs=fmt.get("sub_langs", []),
        )
```

> **Note:** Check `engine.py`'s `start_download` signature supports `remove_sponsors`, `write_subs`, `sub_langs`. If those params don't exist yet, pass them as `**{}` (no-op) and note it for the engine team. Do not modify engine.py internals.

- [ ] **Step 5: Update `_retry_track` similarly**

Replace the preset block in `_retry_track` (lines ~514–527) with the same pattern:
```python
        fmt = self._options_row.get_format_settings()
        if fmt["format_type"] == "audio":
            format_type       = FORMAT_AUDIO
            audio_format_name = fmt["audio_format_name"]
            quality_name      = fmt["quality_name"]
        else:
            format_type       = FORMAT_MP4
            audio_format_name = ""
            quality_name      = fmt["quality_name"]
```

- [ ] **Step 6: Smoke test — app launches without error**

```bash
cd "C:/Users/Rohan/Documents/Youtube download"
python -c "
import subprocess, sys, time
proc = subprocess.Popen([sys.executable, 'main.py'], stderr=subprocess.PIPE, text=True)
time.sleep(3)
ret = proc.poll()
if ret is not None:
    print('CRASH:', proc.stderr.read(500))
else:
    print('OK — app running')
    proc.terminate()
"
```

Expected: `OK — app running`

- [ ] **Step 7: Commit**

```bash
git add gui/app.py
git commit -m "feat: wire OptionsRow into app, remove preset pills"
```

---

## Task 3: Slim down `gui/components/settings_panel.py`

**Files:**
- Modify: `gui/components/settings_panel.py`

Remove: Output Folder, Parallel Downloads, Filename Template, Cookies File sections.
Add: yt-dlp update status + Update button.
Keep: Telegram Bot Token, Telegram Channel ID, Apply button.

- [ ] **Step 1: Remove the 3 sections from `_build()`**

In `settings_panel.py`, delete these sections entirely from `_build()`:
- `# ── Output folder ──` block (the `section("DOWNLOADS")` block)
- `# ── Workers ──` block (the `section("PERFORMANCE")` block)
- `# ── Filename template ──` block (the `section("FILENAMES")` block)
- The cookies row inside `# ── Advanced ──` section (keep the section header for Telegram)
- Delete `_pick_folder`, `_pick_cookie`, `_update_template_preview` methods

Also remove from `_apply()`:
```python
            "output_dir":        self._folder_var.get(),    # REMOVE
            "workers":           self._workers_var.get(),   # REMOVE
            "outtmpl":           self._template_var.get(),  # REMOVE
            "cookies_file":      self._cookie_var.get(),    # REMOVE
```

- [ ] **Step 2: Add yt-dlp update section to `_build()`**

Add before the Telegram section:
```python
        # ── yt-dlp update ──
        section("YT-DLP")
        update_row = ctk.CTkFrame(scroll, fg_color="transparent")
        update_row.pack(fill="x", padx=16, pady=(4, 8))
        update_row.grid_columnconfigure(0, weight=1)
        self._update_lbl = ctk.CTkLabel(
            update_row, text="Checking…", **label_style(12, secondary=True))
        self._update_lbl.grid(row=0, column=0, sticky="w")
        self._update_btn = ctk.CTkButton(
            update_row, text="Update", width=80, height=30,
            command=self._do_update, **accent_button())
        self._update_btn.grid(row=0, column=1)
        self._update_btn.grid_remove()  # hidden until update available
        self.after(500, self._check_update)
```

Add these methods to `SettingsPanel`:
```python
    def _check_update(self):
        import threading
        threading.Thread(target=self._fetch_update_status, daemon=True).start()

    def _fetch_update_status(self):
        try:
            from downloader.ytdlp_updater import get_current_version, get_latest_version
            current = get_current_version()
            latest  = get_latest_version()
            if latest and latest != current:
                self.after(0, lambda: (
                    self._update_lbl.configure(
                        text=f"Update available: {latest}",
                        text_color=COLORS["accent"]),
                    self._update_btn.grid()))
            else:
                self.after(0, lambda: self._update_lbl.configure(
                    text=f"yt-dlp {current} (up to date)",
                    text_color=COLORS["text-secondary"]))
        except Exception:
            self.after(0, lambda: self._update_lbl.configure(text="Version check failed"))

    def _do_update(self):
        self._update_btn.configure(state="disabled", text="Updating…")
        import threading
        def _run():
            try:
                from downloader.ytdlp_updater import update_ytdlp
                update_ytdlp()
                self.after(0, lambda: self._update_lbl.configure(
                    text="Updated! Restart to apply.", text_color=COLORS["success"]))
            except Exception as e:
                self.after(0, lambda: self._update_lbl.configure(
                    text=f"Update failed: {e}", text_color=COLORS["error"]))
            finally:
                self.after(0, lambda: self._update_btn.configure(
                    state="normal", text="Update"))
        threading.Thread(target=_run, daemon=True).start()
```

- [ ] **Step 3: Update `_apply()` — keep only Telegram keys**

```python
    def _apply(self):
        self._cfg.update({
            "telegram_token":   self._telegram_token_var.get(),
            "telegram_channel": self._telegram_channel_var.get(),
        })
        self._on_change(dict(self._cfg))
        self.hide()
```

- [ ] **Step 4: Smoke test — settings panel opens without error**

```bash
cd "C:/Users/Rohan/Documents/Youtube download"
python -c "
import subprocess, sys, time
proc = subprocess.Popen([sys.executable, 'main.py'], stderr=subprocess.PIPE, text=True)
time.sleep(3)
ret = proc.poll()
if ret is not None:
    print('CRASH:', proc.stderr.read(500))
else:
    print('OK')
    proc.terminate()
"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add gui/components/settings_panel.py
git commit -m "feat: slim settings panel to Telegram only, add yt-dlp update UI"
```

---

## Task 4: Nav bar — queue badge + active tab indicator

**Files:**
- Modify: `gui/app.py` (`_build_ui` nav section + `_switch_nav` method)

- [ ] **Step 1: Update nav button active style in `_switch_nav`**

Find the existing style update loop in `_switch_nav` (around line 225):
```python
        for k, btn in self._nav_btns.items():
            btn.configure(
                text_color=COLORS["text-primary"] if k == key else COLORS["text-secondary"],
                fg_color=COLORS["accent-hover"] if k == key else "transparent",
            )
```

Replace with:
```python
        for k, btn in self._nav_btns.items():
            active = (k == key)
            btn.configure(
                text_color=COLORS["accent"] if active else COLORS["text-secondary"],
                fg_color=COLORS["accent-hover"] if active else "transparent",
                border_width=0,
            )
```

- [ ] **Step 2: Update queue badge text in `_switch_nav`**

Find the badge update at the bottom of `_switch_nav` (around line 247):
```python
        q_count = self._queue_view.count()
        self._nav_btns["queue"].configure(
            text=f"≡  Queue {q_count}" if q_count else "≡  Queue"
        )
```

Replace with (only count pending + downloading, not done):
```python
        items = self._queue_view.get_items()
        active_count = sum(1 for it in items if it.state in ("pending", "downloading"))
        self._nav_btns["queue"].configure(
            text=f"≡  Queue  {active_count}" if active_count else "≡  Queue"
        )
```

- [ ] **Step 3: Also call badge update on MSG_TRACK_DONE and MSG_TRACK_FAILED**

In `_handle_msg`, after the existing `elif msg_type == MSG_TRACK_DONE:` block, add:
```python
            self._update_queue_badge()
```

And after `elif msg_type == MSG_TRACK_FAILED:` block add the same.

Add helper method:
```python
    def _update_queue_badge(self):
        items = self._queue_view.get_items()
        active_count = sum(1 for it in items if it.state in ("pending", "downloading"))
        self._nav_btns["queue"].configure(
            text=f"≡  Queue  {active_count}" if active_count else "≡  Queue"
        )
```

- [ ] **Step 4: Smoke test — launch app, verify nav looks right**

```bash
cd "C:/Users/Rohan/Documents/Youtube download"
python -c "
import subprocess, sys, time
proc = subprocess.Popen([sys.executable, 'main.py'], stderr=subprocess.PIPE, text=True)
time.sleep(3)
ret = proc.poll()
if ret is not None:
    print('CRASH:', proc.stderr.read(500))
else:
    print('OK')
    proc.terminate()
"
```

Expected: `OK`

- [ ] **Step 5: Run full test suite**

```bash
cd "C:/Users/Rohan/Documents/Youtube download"
python -m pytest tests/ -v
```

Expected: all tests PASS (at minimum the 4 new options_row tests + existing 6 tests).

- [ ] **Step 6: Commit**

```bash
git add gui/app.py
git commit -m "feat: nav badge shows active downloads, active tab accent style"
```

---

## Final Check

- [ ] App launches at 1280×820 — options row visible, Advanced hidden by default
- [ ] Click ⚙ Advanced ▾ — panel expands inline, pushes queue down
- [ ] Format toggle Audio→Video — quality dropdown switches to 720p/1080p/4K
- [ ] ⚙ gear opens slim settings panel (Telegram + yt-dlp only)
- [ ] Preset pills row is gone from the UI
- [ ] Queue nav badge shows `≡  Queue  2` when 2 items active
- [ ] Push to remote

```bash
git push origin feature/redesign-v4
```
