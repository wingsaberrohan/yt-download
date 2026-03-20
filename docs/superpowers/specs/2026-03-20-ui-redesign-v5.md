# YT Downloader — UI Redesign v5.0 Spec
**Date:** 2026-03-20
**Status:** Approved
**Scope:** Replace hidden-settings UI with inline options row + collapsible Advanced panel; remove preset pills; improve nav bar feedback

---

## 1. Problem Statement

The current v4.0 UI hides all major download options (format, quality, SponsorBlock, subtitles, output folder, workers) inside a slide-in settings panel behind the ⚙ gear icon. Users must open settings to change even the most basic option like format or quality. Preset pills are the only shortcut but they're non-obvious. The result: a UI that looks clean but feels broken to new users.

---

## 2. Design Goals

1. **Major options visible on screen** — format, quality, SponsorBlock, subtitles always shown, no settings panel needed for common use
2. **Advanced options collapsible inline** — output folder, workers, filename template, cookies in an expandable section below the options row
3. **Remove preset pills** — replaced by a lightweight "☆ Save as Preset" button
4. **Responsive** — minimum supported resolution: 1280×820, options row wraps gracefully
5. **Keyboard accessible** — proper tab order across all controls

---

## 3. Layout Structure

```
┌─────────────────────────────────────────────────┐
│  ▶ YT Downloader                           [⚙]  │  Title bar
├─────────────────────────────────────────────────┤
│  🔍  Paste URL or search…     [Paste] [Download] │  Command bar (unchanged)
│  (badge: "🌐 YouTube detected")                  │
├─────────────────────────────────────────────────┤
│ [🎵Audio|📼Video] [320kbps▾] [●SponsorBlock]    │  Options row
│ [○Subtitles] [☆ Save as Preset]  [⚙ Advanced▾] │
│ ▾ Advanced panel (inline expand):               │
│   Output Folder [path][…]  Workers [──●──] 3    │
│   Filename [{title}.{ext}] Cookies [(none)][…]  │
├─────────────────────────────────────────────────┤
│                                                 │
│           CONTENT AREA (queue/history/player)   │
│                                                 │
├─────────────────────────────────────────────────┤
│  [≡ Queue ●2]   [📁 History]   [▶ Player]  ⚡   │  Bottom nav
└─────────────────────────────────────────────────┘
```

---

## 4. Options Row

### Format Toggle
- `CTkSegmentedButton` with values `["🎵 Audio", "📼 Video"]`
- Default: Audio
- On change: updates Quality dropdown options
  - Audio: `["128 kbps", "192 kbps", "320 kbps", "FLAC"]`, default `320 kbps`
  - Video: `["720p", "1080p", "4K"]`, default `1080p`

### Quality Dropdown
- `CTkOptionMenu`, values depend on active format
- Saves selection per format independently (switching format restores last-used quality for that format)

### SponsorBlock Toggle
- `CTkButton` styled as a pill: green dot indicator when on, grey when off
- Default: on
- Maps to `remove_sponsors=True/False` in `start_download()`

### Subtitles Toggle
- Same pill style as SponsorBlock
- Default: off
- Maps to `write_subs=True/False` and `sub_langs=["en"]` (when on) in `start_download()`
- When off: `write_subs=False`, `sub_langs=[]`

### ☆ Save as Preset Button
- Ghost-style `CTkButton`
- On click: opens `_PresetNameDialog` (CTkToplevel, small, name entry + Save/Cancel)
- Captures current format + quality → saves to `~/.ytdl_presets.json` via `downloader/presets.py`
- Replaces the removed `PresetPills` component entirely

### ⚙ Advanced ▾ Button
- Ghost-style `CTkButton`, pushed to right via `pack(side="right")`
- Arrow rotates 180° when open (via `configure(text=...)`)
- Toggles the Advanced panel

---

## 5. Advanced Panel (Inline Collapsible)

### Behaviour
- Sits directly below the options row, above the content area
- Expand/collapse via `CTkFrame` with `grid_remove()` / `grid()` (no animation needed — instant show/hide is fine; avoids CTk animation bugs)
- State persists for the session (collapses on app restart)

### Fields (2-column grid layout)

| Field | Widget | Default |
|-------|--------|---------|
| Output Folder | `CTkEntry` + `…` browse button | `downloads/` relative to app root |
| Parallel Downloads | `CTkSlider` (1–8) + live label | 3 |
| Filename Template | `CTkEntry` + live preview label | `{title}.{ext}` |
| Cookies File | `CTkEntry` + `…` browse button | (empty) |

### Responsiveness
- At window width < 860px: grid switches to single-column (4 rows)
- Panel is inside the main scrollable area so it never clips on 1280×820

### Saving
- All changes apply immediately on widget interaction (no Apply button)
- Calls `self._on_settings_change(cfg)` just like the existing settings panel does

---

## 6. Removed: Preset Pills Row

`gui/components/preset_pills.py` and `PresetPills` widget are **removed from the layout**.

The `PresetPills` class and file are kept on disk (not deleted) in case they are useful later, but they are no longer imported or instantiated in `app.py`.

`downloader/presets.py` is kept — still used by the Save as Preset dialog.

---

## 7. ⚙ Settings Panel (Slide-in, Top-right Gear)

Scope reduced to:
- Telegram Bot Token (CTkEntry, masked)
- Telegram Channel ID (CTkEntry)
- yt-dlp update status (label + Update button)

Output folder, workers, filename template, cookies are **removed** from the settings panel — they now live in the Advanced inline panel.

Gear icon shows a violet dot badge when a yt-dlp update is available (unchanged from v4).

---

## 8. Bottom Navigation Bar

### Active Tab Indicator
- Active tab: `border_width_top=3` via a thin `CTkFrame` accent line above the button (since CTkButton doesn't support per-edge border width), OR use `fg_color=COLORS["accent-hover"]` + `text_color=COLORS["accent"]` for the active state — whichever renders more cleanly
- Inactive tabs: `fg_color="transparent"`, `text_color=COLORS["text-secondary"]`

### Queue Badge
- When 1+ items are pending or downloading: button text = `f"≡  Queue {N}"` (double-space, matching existing code style in `_switch_nav`)
- When queue is empty or all done: text = `"≡  Queue"`
- Updated on every `_switch_nav()` call and after each MSG_TRACK_DONE / MSG_TRACK_FAILED message

---

## 9. Responsive Behaviour (min 1280×820)

### Options row wrapping
- At narrow widths the row wraps naturally (`pack` with `wrap` or `grid` with column weights)
- Row 1 at narrow: Format + Quality + Advanced button
- Row 2 at narrow: SponsorBlock + Subtitles + Save as Preset

### Tab Order (keyboard navigation)
```
1. URL input
2. Format toggle (Audio)
3. Format toggle (Video)
4. Quality dropdown
5. SponsorBlock toggle
6. Subtitles toggle
7. Save as Preset button
8. Advanced ▾ button
9–12. Advanced panel fields (Output, Workers, Template, Cookies) — only when panel open
20+. Content area track rows
30. Queue nav tab
31. History nav tab
32. Player nav tab
```

Tab order set via `CTkFrame.tk_focusNext()` ordering (widget creation order) — no manual `tabindex` needed in Tkinter; order follows widget instantiation sequence.

---

## 10. Files Changed

### Modified
| File | Change |
|------|--------|
| `gui/app.py` | Remove PresetPills import + usage; add OptionsRow frame with format/quality/toggles/save/advanced; wire Advanced panel; update `_build_ui`, `_on_url_submit`, `_start_next_download`, and `_retry_track` to call `self._options_row.get_format_settings()` instead of reading `self._active_preset`; update queue badge logic |
| `gui/components/settings_panel.py` | Remove output folder, workers, filename template, cookies fields; keep Telegram fields; **add** yt-dlp update status label + Update button (this is a new addition to the panel, not an existing element) |

### New
| File | Purpose |
|------|---------|
| `gui/components/options_row.py` | `OptionsRow(CTkFrame)` — contains format toggle, quality dropdown, toggles, save button, advanced toggle + inline advanced panel |

### Kept unchanged
| File | Reason |
|------|--------|
| `gui/components/preset_pills.py` | Kept on disk, no longer used in app.py |
| `gui/components/command_bar.py` | No changes |
| `gui/components/queue_view.py` | No changes |
| `gui/components/track_row.py` | No changes |
| `gui/components/player.py` | No changes |
| `gui/components/history_view.py` | No changes |
| `downloader/presets.py` | Still used by Save as Preset dialog |
| All downloader modules | No changes |

---

## 11. `OptionsRow` Public API

```python
class OptionsRow(CTkFrame):
    def __init__(self, parent, on_change: Callable[[dict], None], initial: dict, **kwargs)

    def get_format_settings(self) -> dict:
        """
        Returns a dict ready for start_download() call sites:
        {
            "format_type": "audio" | "video",        # matches preset schema key
            "audio_format_name": str,                 # e.g. "MP3 - 320 kbps" — matches AUDIO_FORMATS tuples
            "quality_name": str,                      # e.g. "1080p" for video, same as audio_format_name for audio
            "codec": str,                             # e.g. "mp3", "flac", "mp4"
            "quality": str,                           # e.g. "320", "0" (FLAC), "1080"
            "remove_sponsors": bool,
            "write_subs": bool,
            "sub_langs": list[str],                   # ["en"] when write_subs True, else []
        }
        """

    def set_format_settings(self, settings: dict) -> None:
        # Accepts a preset dict (same schema as DEFAULT_PRESETS in presets.py)
        # and updates all widgets accordingly
```

### Quality label → engine parameter mapping

| Display label | `audio_format_name` | `codec` | `quality` |
|--------------|-------------------|---------|-----------|
| 128 kbps | `"MP3 - 128 kbps"` | `"mp3"` | `"128"` |
| 192 kbps | `"MP3 - 192 kbps"` | `"mp3"` | `"192"` |
| 320 kbps | `"MP3 - 320 kbps"` | `"mp3"` | `"320"` |
| FLAC | `"FLAC (lossless)"` | `"flac"` | `"0"` |
| 720p | *(video — no audio_format_name)* | `"mp4"` | `"720"` |
| 1080p | *(video — no audio_format_name)* | `"mp4"` | `"1080"` |
| 4K | *(video — no audio_format_name)* | `"mp4"` | `"2160"` |

For video, `quality_name` is passed directly (e.g. `"1080p"`). `audio_format_name` is only used when `format_type == "audio"`.

### Save as Preset — schema written to `~/.ytdl_presets.json`

The `_PresetNameDialog` must translate `get_format_settings()` output into the preset schema used by `downloader/presets.py`:

```python
preset = {
    "name": user_entered_name,
    "format_type": settings["format_type"],   # "audio" | "video"
    "codec": settings["codec"],
    "quality": settings["quality"],
}
```

`on_change(settings_dict)` called on any widget change — `app.py` merges the returned dict into `self._cfg` using `self._cfg.update(settings_dict)`. The Advanced panel sends the full cfg dict on each change (output_dir, workers, outtmpl, cookies_file keys).

---

## 12. Success Criteria

- Opening the app shows format, quality, SponsorBlock and subtitles controls immediately — zero clicks required
- Clicking ⚙ Advanced reveals output folder, workers, template, cookies inline — no overlay panel
- ⚙ Settings gear opens slide-in with only Telegram fields
- Preset pills row is gone — top of app has only: title bar → command bar → options row → content
- Queue badge shows correct active download count
- Active nav tab has visible violet indicator
- App works at 1280×820 with no clipped or overflowing widgets
- Tab order follows logical sequence through all controls

---

## 13. Out of Scope

- Drag-to-reorder queue (deferred from v4)
- Light mode
- Inline video player
- Any changes to downloader engine, history, or Telegram upload logic
