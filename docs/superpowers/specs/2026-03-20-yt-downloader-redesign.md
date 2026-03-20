# YouTube Downloader — Full Redesign Spec
**Date:** 2026-03-20
**Status:** Approved
**Scope:** UI overhaul (simulated glassmorphism), UX restructure (command-bar first), 7 new features

---

## 1. Overview

Complete redesign of the YouTube Downloader desktop app (CustomTkinter, Windows/macOS). The redesign addresses four areas simultaneously: visual polish, workflow clarity, download experience, and new functionality.

**Design direction:** Glassmorphism-inspired / Windows 11 Fluent — simulated frosted panels using layered opaque colors, depth via border contrast, soft violet accent, dark-only theme. True CSS backdrop-filter blur is not available in Tkinter; the glass effect is approximated with carefully chosen hex colors at each depth layer.
**Layout pattern:** Command-bar first — a prominent URL/search input at the top, adaptive content area below, bottom navigation bar.
**Primary file:** `gui/app.py` (currently 1328 lines — will be split into components)

---

## 2. Visual Design System

### Color Palette

All colors are opaque hex values pre-blended against the dark base. No CSS `rgba()` or `backdrop-filter` — Tkinter requires hex strings only.

| Token | Value | Usage |
|-------|-------|-------|
| `color-base` | `#0e0f14` | Window background |
| `color-surface` | `#13151c` | Panel backgrounds |
| `color-glass` | `#16171d` | Simulated glass cards/panels (≈ white 6% over base) |
| `color-glass-border` | `#252730` | Card edge color (≈ white 10% over base) |
| `color-accent` | `#7c6af7` | Buttons, progress bars, active states |
| `color-accent-hover` | `#2a2560` | Hover state background tint (replaces glow) |
| `color-accent-active` | `#6355d4` | Pressed/active button state |
| `color-success` | `#4ade80` | Done status |
| `color-error` | `#f87171` | Failed status |
| `color-scheduled` | `#fbbf24` | Scheduler badge |
| `color-text-primary` | `#f0f0f5` | Headings, labels |
| `color-text-secondary` | `#8b8fa8` | Subtitles, metadata |

### Typography
- Font: `Segoe UI Variable` (Windows 11), fallback `Segoe UI`
- Sizes: 11px metadata · 13px body · 15px labels · 20px section titles
- Weights: 400 regular · 500 medium · 600 semibold

### Simulated Glass Treatment (Tkinter implementation)
True `backdrop-filter: blur` is not available in Tkinter. Glass effect is simulated via:
- `fg_color = color-glass` (`#16171d`) — slightly lighter than base
- `border_width = 1`, `border_color = color-glass-border` (`#252730`)
- `corner_radius = 10` for cards, `corner_radius = 22` for pill inputs
- Elevation layers achieved by using progressively lighter `fg_color` values:
  - Layer 0 (base): `#0e0f14`
  - Layer 1 (panels): `#13151c`
  - Layer 2 (cards): `#16171d`
  - Layer 3 (elevated/active): `#1c1e28`

### Theme
Dark-only. No light/dark toggle (simulated glassmorphism requires dark base for effect to read correctly).

---

## 3. Layout Structure

### Window
- Default: 920×660px · Minimum: 800×560px · Resizable

### Structure (top → bottom)

```
┌──────────────────────────────────────────────────────────┐
│  [App icon]                                    [⚙ badge] │  Title bar
├──────────────────────────────────────────────────────────┤
│       ╔══════════════════════════════════════╗           │
│       ║  🔍  Paste URL or search YouTube…   ║           │  Command bar (glass pill)
│       ╚══════════════════════════════════════╝           │
│  [▶ Music 320]  [📼 Archive 1080p]  [🎵 Quick MP3]  [+] │  Preset pills
├──────────────────────────────────────────────────────────┤
│                                                          │
│                  ADAPTIVE CONTENT AREA                   │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  [≡ Queue 3]    [📁 History]    [▶ Player]   ⚡ 2.4 MB/s │  Bottom nav + speed
└──────────────────────────────────────────────────────────┘
```

### Adaptive Content Area States

| State | Content |
|-------|---------|
| **Idle** | Hero "drop a URL" card + 3 recent downloads + storage stat |
| **Downloading** | Queue list with glass progress rows + cancel/pause controls |
| **Player open** | Player card (top 40%) + queue/history (bottom 60%) |

### Settings Overlay Panel (Tkinter implementation)
Slide-in overlay from the right, triggered by ⚙ icon. Implemented as a `CTkFrame` using `place()` geometry manager:
- Frame positioned at `relx=1.0, rely=0, anchor="ne"`, width=320px, full height
- Shown by animating `relx` from `1.0` → `0.655` via repeated `after(8ms)` steps (smooth slide)
- Hidden by reversing animation back to `relx=1.0`, then `place_forget()`
- Frame sits above main content (higher `place()` z-order)
- Contains: output folder, worker count, filename template, scheduler defaults, Telegram config, advanced options

---

## 4. Command Bar

- **URL input:** Paste or type a URL → auto-detects source (YouTube video/playlist/channel, SoundCloud, etc.) → shows a badge label: `"YouTube Playlist · 47 tracks"`
- **Search mode:** Typing non-URL text → switches to YouTube search → shows 5 result cards inline (thumbnail, title, channel, duration) → click to queue
- **Drag & drop:** Drop URL onto window → auto-fills command bar (existing `tkinterdnd2` integration)
- **On Enter / Download click:** Detected URL added to queue with active preset applied

---

## 5. Format Presets

- **3 defaults:** `Music 320` (MP3 320kbps), `Archive 1080p` (MP4 1080p), `Quick MP3` (MP3 192kbps)
- **Right-click** preset pill → context menu with "Edit", "Delete", "Duplicate" options (replaces long-press — Tkinter has no native long-press; `<Button-3>` is the standard secondary-action idiom)
- **`+` chip** at end of row → creates preset from current format settings
- **Active preset** highlighted in violet (`fg_color = color-accent`)
- Stored in `~/.ytdl_presets.json` (user home dir), not hardcoded

---

## 6. Queue Manager

- Each queued item: glass card (`CTkFrame`, Layer 2) with thumbnail, title, format badge, status stripe (left-edge colored `CTkFrame`, width=4px)
- **Reorder:** Up/Down arrow buttons per row (MVP). Drag-to-reorder is a stretch goal — requires manual `<B1-Motion>` tracking and widget re-packing; not in initial implementation
- **Click × to remove** individual items
- **Batch controls:** Select All · Remove Selected · Change Format for Selected
- **Batch URL import:** Paste newline-separated URLs into command bar → detected as multiple URLs → "Add N URLs to queue?" confirmation dialog. Drag `.txt` file onto window → same flow
- **Scheduler badge:** Shows countdown label on items scheduled for a future time

### Queue Item States (left-edge stripe color)
| State | Color |
|-------|-------|
| Pending | `#8b8fa8` (grey) |
| Downloading | `#7c6af7` (violet) |
| Converting | `#a78bfa` (lighter violet) |
| Done | `#4ade80` (green) |
| Failed | `#f87171` (red) |
| Scheduled | `#fbbf24` (amber) |

---

## 7. Per-Track Download Rows

- Thumbnail (48×48) + title (truncated to 1 line) + channel name
- Progress bar: `CTkProgressBar` with `corner_radius=6`, violet `progress_color`, % + speed + ETA labels
- Shimmer effect: cycling `progress_color` between `#7c6af7` and `#a78bfa` via `after()` while downloading
- Phase label cycling: `Fetching…` → `Downloading…` → `Converting…` → `✓ Done`
- **Expandable:** Click row → toggles expanded frame showing full title, format detail, file size, open-file button, "Send to Telegram" action button
- **Retry button** shown on failed rows

---

## 8. New Features

### 8.1 Built-in Media Player
- **Audio playback library:** `pygame.mixer` (add `pygame` to `requirements.txt`)
  - Play/pause/stop controls
  - Seek bar: `CTkSlider` updated every 500ms via `after()` polling `pygame.mixer.music.get_pos()`
  - No waveform visualizer in initial implementation (too complex for solo dev; add in future iteration)
- **Video:** No inline video player in initial implementation. "Open in system player" button uses `os.startfile()` (Windows) / `subprocess.run(["open", path])` (macOS)
- Auto-loads last completed download when Player tab is activated
- Lives in top 40% of content area when Player tab is active

### 8.2 YouTube Search
- Typing non-URL text in command bar (after 500ms debounce) triggers search via yt-dlp's built-in pseudo-URL: `ytsearch5:<query>` passed to `yt_dlp.YoutubeDL.extract_info()` in a background thread
- 5 results shown as `CTkFrame` cards: thumbnail (fetched async), title, channel, duration
- Click result → added to queue with active preset

### 8.3 Batch URL Import
- Command bar detects paste containing `\n` → splits on newlines → filters valid URLs → shows `CTkInputDialog`-style confirmation: "Add 12 URLs to queue?"
- Drag `.txt` file onto window (via `tkinterdnd2`) → reads file, same validation + confirmation flow

### 8.4 Download Scheduler
- **Per-item:** Right-click queue item → context menu → "Schedule for…" → opens a `CTkToplevel` dialog with hour/minute `CTkOptionMenu` spinners (HH and MM dropdowns, 00-23 and 00-59)
- **Global default:** Settings panel → "Schedule all downloads for" toggle + time picker
- Scheduler logic in `downloader/scheduler.py`: background thread polls `time.time()` every 30s, fires `start_download()` from the existing `downloader` public API when scheduled time is reached. No changes to `engine.py` internals required.
- **Notifications:** Use `plyer.notification` (add `plyer` to `requirements.txt`) for cross-platform system tray notifications. Fallback to `CTkToplevel` toast if `plyer` raises `NotImplementedError`
- Scheduled items show countdown label badge (`HH:MM`) in amber

### 8.5 Smart Filename Templates
- Settings panel → Filename Template `CTkEntry` field
- Available tokens: `{title}` `{artist}` `{uploader}` `{date}` `{quality}` `{ext}` `{playlist_index}`
- Live preview `CTkLabel` below field updates on every keystroke
- Example: `{artist} - {title} [{quality}].{ext}` → `Adele - Hello [320kbps].mp3`
- Default: `{title}.{ext}` (preserves current behavior)
- Template applied in `downloader/engine.py` `outtmpl` parameter

### 8.6 History Tab Improvements
- Search bar (`CTkEntry`) filters displayed entries by title substring
- Date range filter: two `CTkOptionMenu` dropdowns (From / To month-year)
- Format filter: `CTkSegmentedButton` (All / Audio / Video)
- Each entry: thumbnail + title + format + date + file size in a `CTkFrame` card
- Click row → play in built-in player (audio) or open in Explorer (video/audio)
- "Export CSV" button → writes `download_history/export_{date}.csv` via `csv` stdlib

### 8.7 Format Presets (see Section 5)

---

## 9. Decluttering / UX Simplification

| Element | Current Location | New Location |
|---------|-----------------|--------------|
| SponsorBlock | Visible checkbox in Settings | Collapsed inside "Advanced ▾" per queue item |
| Subtitles | Visible checkbox in Settings | Collapsed inside "Advanced ▾" per queue item |
| Cookies | Visible checkbox in Settings | Settings overlay panel |
| Telegram upload | Settings tab | Post-download action on completed row ("Send to Telegram") |
| yt-dlp update | Status bar message | Silent dot badge on ⚙ settings icon |
| Worker count | Visible slider in Settings | Settings overlay panel |

---

## 10. Architecture Changes

### File Structure (proposed)
```
gui/
├── app.py                  # Main window shell + state machine (~400 lines, down from 1328)
├── theme.py                # Color tokens + CTk widget style helpers (see API below)
└── components/
    ├── command_bar.py      # Command bar + URL detection + search results
    ├── preset_pills.py     # Preset chips + right-click editor
    ├── queue_view.py       # Queue list + up/down reorder
    ├── track_row.py        # Per-track progress row (extracted from _TrackRowUI)
    ├── player.py           # Audio player (pygame.mixer)
    ├── history_view.py     # History tab with search + filter + CSV export
    └── settings_panel.py   # Slide-in settings overlay (place()-based)
```

### `theme.py` Public API
```python
# Color constants (all opaque hex)
COLORS: dict[str, str]  # all tokens from Section 2 color table

# CTk widget style factory functions — return kwargs dicts for unpacking
def glass_frame() -> dict:
    # returns: fg_color, border_width, border_color, corner_radius
def accent_button() -> dict:
    # returns: fg_color, hover_color, text_color, border_width, corner_radius
def ghost_button() -> dict:
    # returns: fg_color="transparent", hover_color, text_color, border_width, corner_radius
def pill_entry() -> dict:
    # returns: fg_color, border_color, corner_radius=22, text_color
def status_stripe(state: str) -> dict:
    # state: "pending"|"downloading"|"converting"|"done"|"failed"|"scheduled"
    # returns: fg_color (the stripe color for that state)
```

Usage: `CTkFrame(parent, **theme.glass_frame())`

### New Modules
```
downloader/
├── scheduler.py    # Background thread polling scheduled items; calls downloader public API
├── search.py       # yt-dlp ytsearch5 wrapper; returns list of result dicts
└── presets.py      # Load/save ~/.ytdl_presets.json; returns list of preset dicts
```

### Scheduler Integration with engine.py
`scheduler.py` calls `start_download()` from `downloader/__init__.py` (the existing public API) at the scheduled time. No modifications to `engine.py` internals are required — the existing threading and queue architecture handles all download execution.

### Preserved Unchanged
- `downloader/engine.py` — download logic, message queue, fallback strategies
- `downloader/history.py` — SQLite history tracker
- `downloader/ytdlp_updater.py` — auto-update mechanism
- `upload_to_telegram.py` — Telegram integration
- `main.py` — entry point, FFmpeg setup

### New Dependencies (add to `requirements.txt`)
```
pygame>=2.5.0       # Audio playback in built-in player
plyer>=2.1.0        # Cross-platform system notifications
```

---

## 11. Out of Scope
- Light mode (dark-only for glassmorphism effect)
- True CSS backdrop-filter blur (not achievable in Tkinter)
- Drag-to-reorder queue items (deferred; use Up/Down buttons for MVP)
- Audio waveform visualizer (deferred; too complex for initial implementation)
- Inline video player (deferred; use "Open in system player" for MVP)
- Cloud sync / remote access
- Browser extension integration
- Mobile companion app

---

## 12. Success Criteria
- All panels render with correct hex colors from `theme.py`. No widget shows the default grey CustomTkinter background. Passes visual QA on Windows 11 at 100% and 150% display scaling
- Single URL download: paste into command bar → press Enter → track row appears and download starts (2 interactions max)
- Batch import: drag a 20-URL `.txt` file onto window → confirmation dialog → all 20 queued → downloads start
- Format presets: clicking a preset pill applies its format settings in 1 click
- Scheduler: right-click a queued item → set a time → item shows countdown badge; download fires at the scheduled time
- All existing functionality preserved: audio formats, video quality, playlists, subtitles, SponsorBlock, cookies, Telegram, history, drag-drop URL (no regressions)
- Window resizes gracefully between 800px and 1400px wide with no clipped or overflowing widgets
