# YouTube Downloader

A modern desktop app to download YouTube videos or playlists as audio (MP3, AAC, FLAC, WAV, OGG) or MP4 video (up to 4K) using [yt-dlp](https://github.com/yt-dlp/yt-dlp) and FFmpeg. Built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for a clean dark/light mode UI.

## Download (no install needed)

Pre-built binaries are available on the [Releases](https://github.com/wingsaberrohan/yt-download/releases) page:

| Platform | File | How to use |
|----------|------|------------|
| Windows  | `YT-Downloader-Windows.zip` | Extract and run `YT-Downloader.exe` |
| macOS    | `YT-Downloader.dmg` | Open the DMG, drag the app to Applications |

FFmpeg is bundled automatically. No Python or extra setup required.

---

## How to use

1. **Paste the URL** -- Click the **Paste** button or type a YouTube video / playlist URL.

2. **Choose format**
   - **Audio** -- Pick from MP3 (320/192 kbps), AAC, FLAC, WAV, or OGG.
   - **Video (MP4)** -- Pick quality: Best available, 4K, 1080p, 720p, 480p, or 360p.

3. **Set output folder** -- Use the default `downloads` folder or click **Browse** to pick another.

4. **Parallel downloads** -- Choose 1-8 concurrent workers (default: 3) for playlists.

5. **Download** -- Click **Download**. Visual progress bars show per-track and overall progress with live speed display.

6. **Cancel / Retry** -- Click **Cancel** to abort, or **Retry Failed** to re-attempt only the tracks that failed.

7. **Open Folder** -- After downloading, click **Open Folder** to jump straight to your files.

### Tips

- **Playlists**: Paste the playlist URL; all videos download with the same format and quality.
- **Single video**: Paste a normal watch URL; one file will be created.
- **Dark/Light mode**: Toggle the switch in the top-right corner.

---

## Features

| Feature             | Details                                                    |
|---------------------|------------------------------------------------------------|
| Audio formats       | MP3 (320/192 kbps), AAC (256 kbps), FLAC, WAV, OGG (256 kbps) |
| Video format        | MP4 -- Best, 4K, 1080p, 720p, 480p, 360p                  |
| Playlists           | Yes, with per-track progress and summary report            |
| Parallel downloads  | 1-8 concurrent tracks (default: 3)                        |
| Cancel downloads    | Stop all in-flight downloads instantly                     |
| Retry failed        | One-click retry for only the failed tracks                 |
| Paste from clipboard| Paste button next to the URL field                         |
| Open output folder  | Button to open the download folder in Explorer / Finder    |
| Progress bars       | Overall + per-track visual progress bars                   |
| Download speed      | Live speed display (KB/s, MB/s)                            |
| Dark / Light mode   | Toggle switch, defaults to dark                            |
| Modern UI           | CustomTkinter with rounded widgets and clean layout        |
| Platforms           | Windows (.exe), macOS (.dmg), or run from source           |

All processing is done locally; no account or API key is required.

---

## Run from source (developers)

### Requirements

- **Python 3.8+**
- Nothing else -- FFmpeg is included via the `imageio-ffmpeg` package (downloaded automatically on first run).

### Setup and run

1. Open a terminal in the project folder.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   python main.py
   ```

### Optional: use your own FFmpeg

If you prefer a different FFmpeg build (e.g. full codecs), you can:

- **Option A** -- Add FFmpeg's `bin` folder to your system **PATH**, or
- **Option B** -- Place FFmpeg in the project so you have:
  `ffmpeg/bin/ffmpeg.exe`

The app will use your FFmpeg if it finds it (local folder or PATH) before falling back to the bundled one.

---

## Build from source

To create a standalone .exe / .app yourself:

```bash
pip install pyinstaller
pyinstaller build.spec
```

The output will be in `dist/YT-Downloader/`. The `build.spec` file handles bundling CustomTkinter data files, the imageio-ffmpeg binary, and the app icon automatically.

### CI/CD

Push a tag like `v1.0.0` to trigger the GitHub Actions workflow that builds Windows and macOS binaries and creates a GitHub Release automatically.
