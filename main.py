"""
YouTube Downloader - entry point.
"""
import sys
import os

if getattr(sys, "frozen", False):
    APP_ROOT = sys._MEIPASS
    WRITABLE_ROOT = os.path.dirname(sys.executable)
else:
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))
    WRITABLE_ROOT = APP_ROOT

sys.path.insert(0, APP_ROOT)

# Prepend writable yt-dlp updates folder so user-installed updates take precedence
from downloader.ytdlp_updater import add_updates_to_path
add_updates_to_path(WRITABLE_ROOT)

from downloader import check_ffmpeg, setup_local_ffmpeg, setup_imageio_ffmpeg
from gui.app import run


def main():
    setup_local_ffmpeg(APP_ROOT)

    if not check_ffmpeg():
        setup_imageio_ffmpeg()

    if not check_ffmpeg():
        if not getattr(sys, "frozen", False):
            print(
                "FFmpeg was not found. Make sure you ran: pip install -r requirements.txt\n"
                "If the problem persists, install FFmpeg manually: "
                "https://www.gyan.dev/ffmpeg/builds/\n"
            )
        sys.exit(1)

    run(WRITABLE_ROOT)


if __name__ == "__main__":
    main()
