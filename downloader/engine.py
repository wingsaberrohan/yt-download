"""
yt-dlp download engine: MP3 (320 kbps) or MP4 video at selected quality.
"""
import threading
from queue import Queue, Empty

import yt_dlp

# Quality options for MP4: (display name, yt-dlp format string)
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


def get_quality_format_string(quality_name: str) -> str:
    """Return yt-dlp format string for the given quality label."""
    for name, fmt in MP4_QUALITIES:
        if name == quality_name:
            return fmt
    return MP4_QUALITIES[0][1]  # default: best available


def download(
    url: str,
    output_dir: str,
    format_type: str,
    quality_name: str,
    progress_callback,
):
    """
    Download from URL to output_dir.
    format_type: 'mp3' or 'mp4'
    quality_name: used when format_type is 'mp4' (e.g. '1080p', 'Best available')
    progress_callback: callable(message: str) called from the main thread for log updates.
    """
    out_tmpl = str(output_dir).replace("\\", "/").rstrip("/") + "/%(title)s.%(ext)s"

    if format_type == FORMAT_MP3:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_tmpl,
            "extract_audio": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                }
            ],
            "merge_output_format": None,
        }
    else:
        fmt = get_quality_format_string(quality_name)
        ydl_opts = {
            "format": fmt,
            "outtmpl": out_tmpl,
            "merge_output_format": "mp4",
        }

    log_queue = Queue()

    class QueueLogger:
        def debug(self, msg):
            log_queue.put(("debug", msg))

        def info(self, msg):
            log_queue.put(("info", msg))

        def warning(self, msg):
            log_queue.put(("warning", msg))

        def error(self, msg):
            log_queue.put(("error", msg))

    def progress_hook(d):
        if d.get("status") == "downloading":
            msg = d.get("_default_template", "").format(**(d or {}))
            if msg:
                log_queue.put(("info", msg))
        elif d.get("status") == "finished":
            log_queue.put(("info", "Converting/merging..."))

    ydl_opts["logger"] = QueueLogger()
    ydl_opts["progress_hooks"] = [progress_hook]

    def run():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            log_queue.put(("info", "Download complete."))
        except Exception as e:
            log_queue.put(("error", str(e)))
        finally:
            log_queue.put((None, None))  # sentinel

    def drain_queue():
        try:
            while True:
                level, msg = log_queue.get_nowait()
                if level is None:
                    progress_callback(None)  # signal done
                    return
                if msg:
                    progress_callback(msg)
        except Empty:
            pass

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return drain_queue


def check_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    import shutil
    return shutil.which("ffmpeg") is not None


def setup_local_ffmpeg(project_root: str) -> bool:
    """
    If project_root/ffmpeg/bin/ffmpeg.exe exists, add it to PATH so yt-dlp can find it.
    Returns True if PATH was updated.
    """
    import os
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
    """
    Use FFmpeg from the imageio-ffmpeg package (downloads on first use).
    Adds its directory to PATH. Returns True if successful.
    """
    import os
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
