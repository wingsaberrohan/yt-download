# YouTube MP3 / MP4 Downloader

A simple desktop app to download YouTube videos or playlists as **MP3 (320 kbps)** or **MP4 video** (4K, 1080p, 720p, etc.) using [yt-dlp](https://github.com/yt-dlp/yt-dlp) and FFmpeg. Works on Windows, macOS, and Linux.

## Download (no install needed)

Pre-built binaries are available on the [Releases](https://github.com/wingsaberrohan/yt-download/releases) page:

| Platform | File | How to use |
|----------|------|------------|
| Windows  | `YT-Downloader.exe` | Just run it — no install needed |
| macOS    | `YT-Downloader.dmg` | Open the DMG, drag the app to Applications |

FFmpeg is bundled automatically. No Python or extra setup required.

---

## Run from source (developers)

### Requirements

- **Python 3.8+**
- Nothing else — FFmpeg is included via the `imageio-ffmpeg` package (downloaded automatically on first run).

### Setup and run

1. Open a terminal in the project folder.
2. Install dependencies (this installs yt-dlp and the FFmpeg bundle):
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   python main.py
   ```

The first time you run the app, FFmpeg may be downloaded automatically (via `imageio-ffmpeg`). No manual download or unzip needed.

### Optional: use your own FFmpeg

If you prefer a different FFmpeg build (e.g. full codecs), you can:

- **Option A** – Add FFmpeg’s `bin` folder to your system **PATH**, or  
- **Option B** – Place FFmpeg in the project so you have:  
  `Youtube download\ffmpeg\bin\ffmpeg.exe`

The app will use your FFmpeg if it finds it (local folder or PATH) before falling back to the bundled one.

## How to use

1. **Paste the URL**  
   In "YouTube URL", paste a single video link or a playlist link, e.g.  
   `https://www.youtube.com/watch?v=...` or `https://www.youtube.com/playlist?list=...`

2. **Choose format**  
   - **MP3 (320 kbps)** – audio only, 320 kbps MP3.  
   - **MP4 (video)** – full video + audio, merged into one MP4 file.

3. **Choose video quality** (only when MP4 is selected)  
   - **Best available** – highest resolution (e.g. 4K if the video has it).  
   - **4K (2160p)**, **1080p**, **720p**, **480p**, **360p** – cap at that resolution (or best below it if the video is lower).

4. **Set output folder**  
   Use the default `downloads` or click **Browse...** to pick another folder. Files will be saved there with the video title as the filename.

5. **Download**  
   Click **Download**. Progress appears in the log area. When it says "Download complete." / "Done.", the file(s) are in the output folder.

### Tips

- **Playlists**: Paste the playlist URL; all videos in the playlist will download with the same format and quality.
- **Single video**: Paste the normal watch URL; one file will be created.
- If a video doesn’t have the chosen resolution (e.g. no 4K), yt-dlp will pick the best available up to that cap.

## Features

| Feature             | Details                                       |
|---------------------|-----------------------------------------------|
| Output formats      | MP3 (320 kbps), MP4 (video)                   |
| Video quality       | Best, 4K, 1080p, 720p, 480p, 360p             |
| Single video        | Yes                                           |
| Playlists           | Yes, with per-track progress and summary       |
| Parallel downloads  | 1-8 concurrent tracks (default: 3)            |
| Retry failed        | One-click retry for only the failed tracks     |
| Summary report      | Shows succeeded/failed tracks with errors      |
| Platforms           | Windows (.exe), macOS (.dmg), or run from source |

All processing is done locally; no account or API key is required.
