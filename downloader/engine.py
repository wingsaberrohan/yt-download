"""
yt-dlp download engine: MP3 (320 kbps) or MP4 video at selected quality.
Supports per-track progress, success/failure tracking, and retry of failed items.
"""
import os
import threading
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import List, Optional, Callable

import yt_dlp

MP4_QUALITIES = [
    ("Best available", "bestvideo+bestaudio/best"),
    ("4K (2160p)", "bestvideo[height<=2160]+bestaudio/best[height<=2160]"),
    ("1080p", "bestvideo[height<=1080]+bestaudio/best[height<=1080]"),
    ("720p", "bestvideo[height<=720]+bestaudio/best[height<=720]"),
    ("480p", "bestvideo[height<=480]+bestaudio/best[height<=480]"),
    ("360p", "bestvideo[height<=360]+bestaudio/best[height<=360]"),
]

FORMAT_MP3 = "mp3"
FORMAT_MP4 = "mp4"


@dataclass
class TrackInfo:
    url: str
    title: str = ""
    index: int = 0
    status: str = "pending"  # pending | downloading | done | failed
    error: str = ""


@dataclass
class PlaylistResult:
    playlist_title: str = ""
    total: int = 0
    tracks: List[TrackInfo] = field(default_factory=list)

    @property
    def done_count(self):
        return sum(1 for t in self.tracks if t.status == "done")

    @property
    def failed_count(self):
        return sum(1 for t in self.tracks if t.status == "failed")

    @property
    def failed_tracks(self):
        return [t for t in self.tracks if t.status == "failed"]


# ---------- message types for the GUI queue ----------

MSG_PLAYLIST_INFO = "playlist_info"    # (MSG_PLAYLIST_INFO, PlaylistResult)
MSG_TRACK_START = "track_start"        # (MSG_TRACK_START, TrackInfo)
MSG_TRACK_PROGRESS = "track_progress"  # (MSG_TRACK_PROGRESS, str)
MSG_TRACK_DONE = "track_done"          # (MSG_TRACK_DONE, TrackInfo)
MSG_TRACK_FAILED = "track_failed"      # (MSG_TRACK_FAILED, TrackInfo)
MSG_LOG = "log"                        # (MSG_LOG, str)
MSG_FINISHED = "finished"              # (MSG_FINISHED, PlaylistResult)


def get_quality_format_string(quality_name: str) -> str:
    for name, fmt in MP4_QUALITIES:
        if name == quality_name:
            return fmt
    return MP4_QUALITIES[0][1]


def _build_ydl_opts(format_type: str, quality_name: str, output_dir: str,
                    logger=None, progress_hooks=None) -> dict:
    out_tmpl = output_dir.replace("\\", "/").rstrip("/") + "/%(title)s.%(ext)s"

    if format_type == FORMAT_MP3:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": out_tmpl,
            "extract_audio": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }],
            "merge_output_format": None,
        }
    else:
        fmt = get_quality_format_string(quality_name)
        opts = {
            "format": fmt,
            "outtmpl": out_tmpl,
            "merge_output_format": "mp4",
        }

    if logger:
        opts["logger"] = logger
    if progress_hooks:
        opts["progress_hooks"] = progress_hooks
    return opts


def extract_playlist_info(url: str) -> PlaylistResult:
    """Extract playlist metadata without downloading. Works for single videos too."""
    result = PlaylistResult()
    opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        return result

    entries = info.get("entries")
    if entries:
        result.playlist_title = info.get("title", "Playlist")
        tracks = list(entries)
        result.total = len(tracks)
        for i, entry in enumerate(tracks):
            if entry is None:
                continue
            track_url = entry.get("url") or entry.get("webpage_url") or ""
            if not track_url and entry.get("id"):
                track_url = f"https://www.youtube.com/watch?v={entry['id']}"
            result.tracks.append(TrackInfo(
                url=track_url,
                title=entry.get("title", f"Track {i+1}"),
                index=i + 1,
            ))
    else:
        result.playlist_title = info.get("title", "Single video")
        result.total = 1
        video_url = info.get("webpage_url") or info.get("original_url") or url
        result.tracks.append(TrackInfo(
            url=video_url,
            title=info.get("title", "Video"),
            index=1,
        ))

    return result


def download_tracks(
    tracks: List[TrackInfo],
    output_dir: str,
    format_type: str,
    quality_name: str,
    message_queue: Queue,
    playlist_result: PlaylistResult,
):
    """Download a list of tracks one by one, putting status messages on the queue."""

    class QuietLogger:
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass

    for track in tracks:
        track.status = "downloading"
        message_queue.put((MSG_TRACK_START, track))

        def progress_hook(d, _track=track):
            if d.get("status") == "downloading":
                pct = d.get("_percent_str", "").strip()
                speed = d.get("_speed_str", "").strip()
                eta = d.get("_eta_str", "").strip()
                if pct:
                    msg = f"  [{_track.index}/{playlist_result.total}] {pct}"
                    if speed:
                        msg += f" at {speed}"
                    if eta:
                        msg += f" ETA {eta}"
                    message_queue.put((MSG_TRACK_PROGRESS, msg))

        opts = _build_ydl_opts(
            format_type, quality_name, output_dir,
            logger=QuietLogger(),
            progress_hooks=[progress_hook],
        )
        opts["noplaylist"] = True

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([track.url])
            track.status = "done"
            message_queue.put((MSG_TRACK_DONE, track))
        except Exception as e:
            track.status = "failed"
            track.error = str(e)
            message_queue.put((MSG_TRACK_FAILED, track))


def start_download(
    url: str,
    output_dir: str,
    format_type: str,
    quality_name: str,
) -> tuple:
    """
    High-level download entry point. Returns (message_queue, playlist_result).
    Caller should poll message_queue for updates.
    """
    message_queue = Queue()

    def run():
        message_queue.put((MSG_LOG, "Fetching playlist/video info..."))
        try:
            result = extract_playlist_info(url)
        except Exception as e:
            result = PlaylistResult()
            result.playlist_title = "Error"
            message_queue.put((MSG_LOG, f"Failed to fetch info: {e}"))
            message_queue.put((MSG_FINISHED, result))
            return

        if not result.tracks:
            message_queue.put((MSG_LOG, "No tracks found."))
            message_queue.put((MSG_FINISHED, result))
            return

        message_queue.put((MSG_PLAYLIST_INFO, result))
        message_queue.put((MSG_LOG,
            f"Found {result.total} track(s) in \"{result.playlist_title}\""))

        os.makedirs(output_dir, exist_ok=True)
        download_tracks(result.tracks, output_dir, format_type, quality_name,
                        message_queue, result)
        message_queue.put((MSG_FINISHED, result))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return message_queue, None  # second value reserved


def retry_failed(
    playlist_result: PlaylistResult,
    output_dir: str,
    format_type: str,
    quality_name: str,
) -> Queue:
    """Retry only the failed tracks. Returns a message_queue to poll."""
    message_queue = Queue()
    failed = playlist_result.failed_tracks
    if not failed:
        message_queue.put((MSG_LOG, "No failed tracks to retry."))
        message_queue.put((MSG_FINISHED, playlist_result))
        return message_queue

    for t in failed:
        t.status = "pending"
        t.error = ""

    message_queue.put((MSG_LOG, f"Retrying {len(failed)} failed track(s)..."))

    def run():
        download_tracks(failed, output_dir, format_type, quality_name,
                        message_queue, playlist_result)
        message_queue.put((MSG_FINISHED, playlist_result))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return message_queue


def check_ffmpeg() -> bool:
    import shutil
    return shutil.which("ffmpeg") is not None


def setup_local_ffmpeg(project_root: str) -> bool:
    bin_dir = os.path.join(project_root, "ffmpeg", "bin")
    if not os.path.isdir(bin_dir):
        return False
    exe = os.path.join(bin_dir, "ffmpeg.exe")
    if not os.path.isfile(exe):
        return False
    path = os.environ.get("PATH", "")
    os.environ["PATH"] = bin_dir + os.pathsep + path
    return True


def setup_imageio_ffmpeg() -> bool:
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            bin_dir = os.path.dirname(exe)
            path = os.environ.get("PATH", "")
            os.environ["PATH"] = bin_dir + os.pathsep + path
            return True
    except Exception:
        pass
    return False
