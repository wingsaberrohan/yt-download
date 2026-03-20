"""
yt-dlp download engine: audio (multiple formats) or MP4 video at selected quality.
Supports per-track progress, success/failure tracking, retry, parallel downloads,
and cancellation.
"""
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import List, Optional

import yt_dlp

_OUTTMPL_TOKEN_MAP = {
    "{title}":          "%(title)s",
    "{artist}":         "%(artist)s",
    "{uploader}":       "%(uploader)s",
    "{date}":           "%(upload_date)s",
    "{playlist_index}": "%(playlist_index)s",
}

def _translate_outtmpl(template: str, quality_label: str) -> str:
    """Translate spec token syntax ({title}) to yt-dlp syntax (%(title)s)."""
    result = template
    for spec_token, ytdlp_token in _OUTTMPL_TOKEN_MAP.items():
        result = result.replace(spec_token, ytdlp_token)
    result = result.replace("{quality}", quality_label or "")
    result = result.replace("{ext}", "%(ext)s")
    return result


MP4_QUALITIES = [
    ("Best available", "bestvideo+bestaudio/best"),
    ("4K (2160p)", "bestvideo[height<=2160]+bestaudio/best[height<=2160]"),
    ("1080p", "bestvideo[height<=1080]+bestaudio/best[height<=1080]"),
    ("720p", "bestvideo[height<=720]+bestaudio/best[height<=720]"),
    ("480p", "bestvideo[height<=480]+bestaudio/best[height<=480]"),
    ("360p", "bestvideo[height<=360]+bestaudio/best[height<=360]"),
]

AUDIO_FORMATS = [
    ("MP3 - 320 kbps", "mp3", "320"),
    ("MP3 - 192 kbps", "mp3", "192"),
    ("AAC - 256 kbps", "aac", "256"),
    ("FLAC (lossless)", "flac", "0"),
    ("WAV (lossless)", "wav", "0"),
    ("OGG - 256 kbps", "vorbis", "256"),
]

FORMAT_AUDIO = "audio"
FORMAT_MP3 = "mp3"
FORMAT_MP4 = "mp4"


@dataclass
class TrackInfo:
    url: str
    title: str = ""
    index: int = 0
    status: str = "pending"
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


MSG_PLAYLIST_INFO = "playlist_info"
MSG_TRACK_START = "track_start"
MSG_TRACK_PROGRESS = "track_progress"
MSG_TRACK_PERCENT = "track_percent"
MSG_TRACK_PHASE = "track_phase"
MSG_TRACK_DONE = "track_done"
MSG_TRACK_FAILED = "track_failed"
MSG_LOG = "log"
MSG_FINISHED = "finished"


class _DownloadCancelled(Exception):
    pass


# On 403, retry with different client/UA to work around YouTube blocking
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36"
)
FALLBACK_STRATEGIES = [
    {},
    {"extractor_args": {"youtube": {"player_client": ["web_embedded"]}}},
    {"extractor_args": {"youtube": {"player_client": ["ios"]}}},
    {"http_headers": {"User-Agent": MOBILE_UA}},
]


def _is_403_or_forbidden(exc: Exception) -> bool:
    s = str(exc).lower()
    if "403" in s or "forbidden" in s:
        return True
    if hasattr(exc, "code") and getattr(exc, "code") == 403:
        return True
    return False


def get_quality_format_string(quality_name: str) -> str:
    for name, fmt in MP4_QUALITIES:
        if name == quality_name:
            return fmt
    return MP4_QUALITIES[0][1]


def get_audio_format(audio_format_name: str) -> tuple:
    """Return (codec, quality) for the given audio format label."""
    for name, codec, quality in AUDIO_FORMATS:
        if name == audio_format_name:
            return codec, quality
    return AUDIO_FORMATS[0][1], AUDIO_FORMATS[0][2]


def _format_speed(speed_bytes: Optional[float]) -> str:
    if speed_bytes is None or speed_bytes <= 0:
        return ""
    if speed_bytes >= 1_048_576:
        return f"{speed_bytes / 1_048_576:.1f} MB/s"
    if speed_bytes >= 1024:
        return f"{speed_bytes / 1024:.0f} KB/s"
    return f"{speed_bytes:.0f} B/s"


def _build_ydl_opts(
    format_type: str,
    quality_name: str,
    output_dir: str,
    audio_format_name: str = "",
    logger=None,
    progress_hooks=None,
    write_subs: bool = False,
    sub_langs: Optional[List[str]] = None,
    remove_sponsors: bool = False,
    cookiefile: Optional[str] = None,
    outtmpl_template: str = None,
) -> dict:
    quality_label = audio_format_name or quality_name or ""
    if outtmpl_template:
        translated = _translate_outtmpl(outtmpl_template, quality_label)
        out_tmpl = os.path.join(output_dir, translated)
    else:
        out_tmpl = output_dir.replace("\\", "/").rstrip("/") + "/%(title)s.%(ext)s"

    if format_type == FORMAT_AUDIO:
        codec, quality = get_audio_format(audio_format_name)
        opts = {
            "format": "bestaudio/best",
            "outtmpl": out_tmpl,
            "extract_audio": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": quality,
            }],
            "merge_output_format": None,
        }
    elif format_type == FORMAT_MP3:
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
    if write_subs and sub_langs:
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = True
        opts["subtitleslangs"] = list(sub_langs)
        opts["subtitlesformat"] = "srt"
    if remove_sponsors:
        cats = ["sponsor", "selfpromo", "interaction"]
        existing_pp = opts.get("postprocessors") or []
        opts["postprocessors"] = existing_pp + [
            {"key": "SponsorBlock", "categories": cats, "when": "after_filter"},
            {"key": "ModifyChapters", "remove_sponsor_segments": cats},
        ]
    if cookiefile and os.path.isfile(cookiefile):
        opts["cookiefile"] = cookiefile

    # Faster DASH/HLS: parallel fragments + larger HTTP chunks (within yt-dlp)
    opts["concurrent_fragment_downloads"] = 6
    opts["http_chunk_size"] = 10 * 1024 * 1024  # 10 MiB

    return opts


def _merge_opts(base: dict, strategy: dict) -> dict:
    """Return a new dict: base updated with strategy (shallow merge for top-level keys)."""
    out = dict(base)
    for k, v in strategy.items():
        if k == "extractor_args" and k in out:
            out[k] = {**out[k], **v} if isinstance(out[k], dict) else dict(v)
        elif k == "http_headers" and k in out:
            out[k] = {**out[k], **v} if isinstance(out[k], dict) else dict(v)
        else:
            out[k] = v
    return out


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


def get_video_preview(url: str) -> Optional[dict]:
    """
    Extract title and thumbnail URL for the first/single video (no download).
    Returns {"title": str, "thumbnail": str} or None on error.
    """
    opts = {
        "extract_flat": False,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return None
        entries = info.get("entries")
        if entries:
            first = None
            for e in entries:
                if e is not None:
                    first = e
                    break
            if first is None:
                return None
            info = first
        title = info.get("title") or "Unknown"
        thumbnail = info.get("thumbnail") or ""
        return {"title": title, "thumbnail": thumbnail}
    except Exception:
        return None


DEFAULT_WORKERS = 3
MAX_WORKERS = 8


def _download_single_track(
    track: TrackInfo,
    output_dir: str,
    format_type: str,
    quality_name: str,
    message_queue: Queue,
    total: int,
    cancel_event: threading.Event = None,
    audio_format_name: str = "",
    write_subs: bool = False,
    sub_langs: Optional[List[str]] = None,
    remove_sponsors: bool = False,
    cookiefile: Optional[str] = None,
    outtmpl_template: str = None,
):
    """Download one track. Called from the thread pool."""
    if cancel_event and cancel_event.is_set():
        track.status = "failed"
        track.error = "Cancelled"
        message_queue.put((MSG_TRACK_FAILED, track))
        return

    class QuietLogger:
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass

    track.status = "downloading"
    message_queue.put((MSG_TRACK_START, track))

    def progress_hook(d):
        if cancel_event and cancel_event.is_set():
            raise _DownloadCancelled("Download cancelled by user")

        st = d.get("status")
        if st == "downloading":
            downloaded = d.get("downloaded_bytes", 0) or 0
            total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed")
            speed_str = _format_speed(speed)

            pct_float = 0.0
            if total_bytes > 0:
                pct_float = min(downloaded / total_bytes, 1.0)

            tb = int(total_bytes) if total_bytes else None
            message_queue.put((
                MSG_TRACK_PERCENT,
                (track.index, pct_float, speed_str, int(downloaded), tb),
            ))

            pct = d.get("_percent_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            if pct:
                msg = f"  [{track.index}/{total}] {pct}"
                if speed_str:
                    msg += f" at {speed_str}"
                if eta:
                    msg += f" ETA {eta}"
                message_queue.put((MSG_TRACK_PROGRESS, msg))
        elif st == "finished" and d.get("postprocessor") is None:
            # Download bytes complete; FFmpeg/postprocessors may still run
            message_queue.put((
                MSG_TRACK_PHASE,
                (track.index, "Processing…"),
            ))

    def postprocessor_hook(d):
        try:
            if d.get("status") == "started":
                pp = d.get("postprocessor") or "convert"
                message_queue.put((
                    MSG_TRACK_PHASE,
                    (track.index, f"Converting ({pp})…"),
                ))
        except Exception:
            pass

    base_opts = _build_ydl_opts(
        format_type, quality_name, output_dir,
        audio_format_name=audio_format_name,
        logger=QuietLogger(),
        progress_hooks=[progress_hook],
        write_subs=write_subs,
        sub_langs=sub_langs,
        remove_sponsors=remove_sponsors,
        cookiefile=cookiefile,
        outtmpl_template=outtmpl_template,
    )
    base_opts["noplaylist"] = True
    pph = list(base_opts.get("postprocessor_hooks") or [])
    pph.append(postprocessor_hook)
    base_opts["postprocessor_hooks"] = pph

    last_error = None
    for strategy in FALLBACK_STRATEGIES:
        if cancel_event and cancel_event.is_set():
            track.status = "failed"
            track.error = "Cancelled"
            message_queue.put((MSG_TRACK_FAILED, track))
            return
        opts = _merge_opts(base_opts, strategy)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([track.url])
            track.status = "done"
            message_queue.put((MSG_TRACK_DONE, track))
            return
        except _DownloadCancelled:
            track.status = "failed"
            track.error = "Cancelled"
            message_queue.put((MSG_TRACK_FAILED, track))
            return
        except Exception as e:
            last_error = e
            if _is_403_or_forbidden(e) and strategy != FALLBACK_STRATEGIES[-1]:
                continue
            break
    track.status = "failed"
    track.error = str(last_error) if last_error else "Unknown error"
    message_queue.put((MSG_TRACK_FAILED, track))


def download_tracks(
    tracks: List[TrackInfo],
    output_dir: str,
    format_type: str,
    quality_name: str,
    message_queue: Queue,
    playlist_result: PlaylistResult,
    max_workers: int = DEFAULT_WORKERS,
    cancel_event: threading.Event = None,
    audio_format_name: str = "",
    write_subs: bool = False,
    sub_langs: Optional[List[str]] = None,
    remove_sponsors: bool = False,
    cookiefile: Optional[str] = None,
    outtmpl_template: str = None,
):
    """Download tracks in parallel using a thread pool."""
    workers = max(1, min(max_workers, MAX_WORKERS))

    if workers == 1 or len(tracks) == 1:
        for track in tracks:
            if cancel_event and cancel_event.is_set():
                track.status = "failed"
                track.error = "Cancelled"
                message_queue.put((MSG_TRACK_FAILED, track))
                continue
            _download_single_track(
                track, output_dir, format_type, quality_name,
                message_queue, playlist_result.total,
                cancel_event=cancel_event,
                audio_format_name=audio_format_name,
                write_subs=write_subs,
                sub_langs=sub_langs,
                remove_sponsors=remove_sponsors,
                cookiefile=cookiefile,
                outtmpl_template=outtmpl_template,
            )
        return

    message_queue.put((MSG_LOG, f"Downloading with {workers} parallel workers..."))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _download_single_track,
                track, output_dir, format_type, quality_name,
                message_queue, playlist_result.total,
                cancel_event=cancel_event,
                audio_format_name=audio_format_name,
                write_subs=write_subs,
                sub_langs=sub_langs,
                remove_sponsors=remove_sponsors,
                cookiefile=cookiefile,
                outtmpl_template=outtmpl_template,
            ): track
            for track in tracks
        }
        for future in as_completed(futures):
            future.result()


def start_download(
    url: str,
    output_dir: str,
    format_type: str,
    quality_name: str,
    max_workers: int = DEFAULT_WORKERS,
    cancel_event: threading.Event = None,
    audio_format_name: str = "",
    write_subs: bool = False,
    sub_langs: Optional[List[str]] = None,
    remove_sponsors: bool = False,
    cookiefile: Optional[str] = None,
    outtmpl_template: str = None,
) -> tuple:
    """
    High-level download entry point. Returns (message_queue, cancel_event).
    Caller should poll message_queue for updates.
    """
    message_queue = Queue()
    if cancel_event is None:
        cancel_event = threading.Event()

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

        if cancel_event.is_set():
            message_queue.put((MSG_LOG, "Cancelled."))
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
        download_tracks(
            result.tracks, output_dir, format_type, quality_name,
            message_queue, result, max_workers=max_workers,
            cancel_event=cancel_event, audio_format_name=audio_format_name,
            write_subs=write_subs, sub_langs=sub_langs,
            remove_sponsors=remove_sponsors,
            cookiefile=cookiefile,
            outtmpl_template=outtmpl_template,
        )
        message_queue.put((MSG_FINISHED, result))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return message_queue, cancel_event


def retry_failed(
    playlist_result: PlaylistResult,
    output_dir: str,
    format_type: str,
    quality_name: str,
    max_workers: int = DEFAULT_WORKERS,
    cancel_event: threading.Event = None,
    audio_format_name: str = "",
    write_subs: bool = False,
    sub_langs: Optional[List[str]] = None,
    remove_sponsors: bool = False,
    cookiefile: Optional[str] = None,
) -> tuple:
    """Retry only the failed tracks. Returns (message_queue, cancel_event)."""
    message_queue = Queue()
    if cancel_event is None:
        cancel_event = threading.Event()

    failed = playlist_result.failed_tracks
    if not failed:
        message_queue.put((MSG_LOG, "No failed tracks to retry."))
        message_queue.put((MSG_FINISHED, playlist_result))
        return message_queue, cancel_event

    for t in failed:
        t.status = "pending"
        t.error = ""

    message_queue.put((MSG_LOG, f"Retrying {len(failed)} failed track(s)..."))

    def run():
        download_tracks(
            failed, output_dir, format_type, quality_name,
            message_queue, playlist_result, max_workers=max_workers,
            cancel_event=cancel_event, audio_format_name=audio_format_name,
            write_subs=write_subs, sub_langs=sub_langs,
            remove_sponsors=remove_sponsors,
            cookiefile=cookiefile,
        )
        message_queue.put((MSG_FINISHED, playlist_result))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return message_queue, cancel_event


def check_ffmpeg() -> bool:
    import shutil
    return shutil.which("ffmpeg") is not None


def setup_local_ffmpeg(project_root: str) -> bool:
    import sys
    import glob
    import shutil as _shutil

    ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"

    search_dirs = [
        os.path.join(project_root, "ffmpeg", "bin"),
        os.path.join(project_root, "ffmpeg"),
        os.path.join(project_root, "imageio_ffmpeg_bin"),
    ]

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        candidate = os.path.join(d, ffmpeg_name)
        if os.path.isfile(candidate):
            path = os.environ.get("PATH", "")
            os.environ["PATH"] = d + os.pathsep + path
            return True
        hits = glob.glob(os.path.join(d, "ffmpeg*"))
        for h in hits:
            if os.path.isfile(h) and os.access(h, os.X_OK):
                target = os.path.join(d, ffmpeg_name)
                if not os.path.isfile(target):
                    try:
                        _shutil.copy2(h, target)
                    except Exception:
                        pass
                path = os.environ.get("PATH", "")
                os.environ["PATH"] = d + os.pathsep + path
                return True

    return False


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
