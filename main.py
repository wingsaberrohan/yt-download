"""
YouTube MP3 / MP4 Downloader - entry point.
"""
import sys
import os

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from downloader import check_ffmpeg, setup_local_ffmpeg, setup_imageio_ffmpeg
from gui.app import run


def main():
    # 1) Use local ffmpeg folder if present (e.g. project/ffmpeg/bin/ffmpeg.exe)
    setup_local_ffmpeg(PROJECT_ROOT)
    # 2) If still missing, use FFmpeg from imageio-ffmpeg (installed with pip; may download on first run)
    if not check_ffmpeg():
        setup_imageio_ffmpeg()

    if not check_ffmpeg():
        print(
            "FFmpeg was not found. Make sure you ran: pip install -r requirements.txt\n"
            "If the problem persists, install FFmpeg manually: "
            "https://www.gyan.dev/ffmpeg/builds/\n"
        )
        sys.exit(1)
    run()


if __name__ == "__main__":
    main()
