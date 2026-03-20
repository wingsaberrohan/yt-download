# YouTube Downloader — Full Redesign Spec
**Date:** 2026-03-20
**Status:** Approved
**Scope:** UI overhaul (glassmorphism), UX restructure (command-bar first), 7 new features

---

## 1. Overview

Complete redesign of the YouTube Downloader desktop app (CustomTkinter, Windows/macOS). The redesign addresses four areas simultaneously: visual polish, workflow clarity, download experience, and new functionality.

**Design direction:** Glassmorphism / Windows 11 Fluent — frosted glass panels, depth layers, soft violet accent, dark-only theme.
**Layout pattern:** Command-bar first — a prominent URL/search input at the top, adaptive content area below, bottom navigation bar.
**Primary file:** `gui/app.py` (currently 1328 lines — will be split into components)

---

## 2. Visual Design System

### Color Palette

| Token | Value | Usage |
|-------|-------|-------|
| `color-base` | `#0e0f14` | Window background |
| `color-surface` | `#13151c` | Panel backgrounds |
| `color-glass` | `rgba(255,255,255,0.06)` | All cards/panels |
| `color-glass-border` | `rgba(255,255,255,0.10)` | Card edges |
| `color-accent` | `#7c6af7` | Buttons, progress, active states |
| `color-accent-glow` | `rgba(124,106,247,0.25)` | Hover/active glow |
| `color-success` | `#4ade80` | Done status |
| `color-error` | `#f87171` | Failed status |
| `color-text-primary` | `#f0f0f5` | Headings, labels |
| `color-text-secondary` | `#8b8fa8` | Subtitles, metadata |

### Typography
- Font: `Segoe UI Variable` (Windows 11), fallback `Segoe UI`
- Sizes: 11px metadata · 13px body · 15px labels · 20px section titles
- Weights: 400 regular · 500 medium · 600 semibold

### Glass Treatment
- Background: `rgba(255,255,255,0.06)` + `backdrop-filter: blur(24px)`
- Border: `1px solid rgba(255,255,255,0.10)`
- Elevation levels: base → glass panel → elevated card (3 layers of depth)

### Theme
Dark-only. No light/dark toggle (glassmorphism requires dark base).

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

### Settings
Slide-in overlay panel from the right (like Windows 11 Quick Settings). Triggered by ⚙ icon in title bar. Contains: output folder, worker count, filename template, scheduler defaults, Telegram config, advanced options.

---

## 4. Command Bar

- **URL input:** Paste or type a URL → auto-detects source (YouTube video/playlist/channel, SoundCloud, etc.) → shows a badge: `"YouTube Playlist · 47 tracks"`
- **Search mode:** Typing non-URL text → switches to YouTube search → shows 5 result cards inline (thumbnail, title, channel, duration) → click to queue
- **Drag & drop:** Drop URL onto window → auto-fills command bar
- **On Enter / Download click:** Detected URL added to queue with active preset applied

---

## 5. Format Presets

- **3 defaults:** `Music 320` (MP3 320kbps), `Archive 1080p` (MP4 1080p), `Quick MP3` (MP3 192kbps)
- **Long-press** preset pill → edit name + format settings → save
- **`+` chip** at end of row → creates preset from current format settings
- **Active preset** highlighted in violet
- Stored in user config (JSON), not hardcoded

---

## 6. Queue Manager

- Each queued item: glass card with thumbnail, title, format badge, status stripe (left edge)
- **Drag to reorder** queue items
- **Click × to remove** individual items
- **Batch controls:** Select All · Remove Selected · Change Format for Selected
- **Batch URL import:** Paste newline-separated URLs into command bar, or drag a `.txt` file onto the window → bulk-adds all URLs to queue
- **Scheduler badge:** Shows countdown on items scheduled for a future time

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
- Progress bar: rounded pill, violet fill with shimmer animation, % + speed + ETA
- Phase label cycling: `Fetching…` → `Downloading…` → `Converting…` → `✓ Done`
- **Expandable:** Click row → expands to show full title, format detail, file size, open-file button, "Send to Telegram" action
- **Retry button** shown on failed rows

---

## 8. New Features

### 8.1 Built-in Media Player
- **Audio:** Waveform visualizer + seek bar + playback controls (play/pause/skip)
- **Video:** Inline player (system VLC/mpv if available, fallback to "Open in system player" button)
- Auto-loads last completed download
- Lives in bottom 40% of content area when Player tab is active

### 8.2 YouTube Search
- Typing non-URL in command bar triggers search via yt-dlp's search capability (`ytsearch5:query`)
- 5 results shown as cards: thumbnail, title, channel, duration
- Click result → added to queue with active preset

### 8.3 Batch URL Import
- Paste multiple newline-separated URLs into command bar → detected → "Add 12 URLs to queue?" confirmation
- Drag `.txt` file onto window → same flow

### 8.4 Download Scheduler
- Per-item: right-click queue item → "Schedule for…" → time picker
- Global: Settings panel → "Default schedule" toggle
- Scheduled items show countdown badge
- System notification when scheduled download starts/completes

### 8.5 Smart Filename Templates
- Settings panel → Filename Template field
- Available tokens: `{title}` `{artist}` `{uploader}` `{date}` `{quality}` `{ext}` `{playlist_index}`
- Live preview below field: `{artist} - {title} [{quality}].{ext}` → `Adele - Hello [320kbps].mp3`
- Default: `{title}.{ext}` (preserves current behavior)

### 8.6 History Tab Improvements
- Searchable by title, date range, format type
- Each entry: thumbnail + title + format + date + file size
- Click → play in built-in player OR open in Explorer
- Export history as CSV button

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
├── app.py              # Main window shell + state machine (~400 lines, down from 1328)
├── components/
│   ├── command_bar.py  # Command bar + search results
│   ├── preset_pills.py # Preset chips + editor
│   ├── queue_view.py   # Queue list + drag-reorder
│   ├── track_row.py    # Per-track progress row (currently _TrackRowUI)
│   ├── player.py       # Built-in media player
│   ├── history_view.py # History tab with search
│   └── settings_panel.py # Slide-in settings overlay
└── theme.py            # Color tokens, glass style helpers
```

### New Modules
```
downloader/
├── scheduler.py        # Download scheduler logic
├── search.py           # yt-dlp YouTube search wrapper
└── presets.py          # Format preset load/save (JSON)
```

### Preserved Unchanged
- `downloader/engine.py` — download logic, message queue, fallback strategies
- `downloader/history.py` — SQLite history tracker
- `downloader/ytdlp_updater.py` — auto-update mechanism
- `upload_to_telegram.py` — Telegram integration
- `main.py` — entry point, FFmpeg setup

---

## 11. Out of Scope
- Light mode (dark-only for glassmorphism)
- Cloud sync / remote access
- Browser extension integration
- Mobile companion app

---

## 12. Success Criteria
- App feels visually premium on Windows 11 (glassmorphism renders correctly)
- Single URL download: paste → enter → downloading in under 2 clicks
- Batch import: drop a 20-URL .txt → all queued → downloads start
- Format presets: switching between presets takes 1 click
- All existing functionality preserved (no regressions)
- Window resizes gracefully between 800px and 1400px wide
