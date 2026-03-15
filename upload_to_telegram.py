"""
Upload a folder of audio/files to a Telegram channel.
Uses Telegram Bot API: create a bot with @BotFather, add it as admin to your channel,
then run this script with the bot token and folder path.

Can be used as a module: upload_folder_to_telegram(token, channel, folder_path, ...)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

# Default channel (your karaoke channel)
DEFAULT_CHANNEL = "@wing_karaoke"

# Audio extensions -> send as audio (playable in Telegram). Others -> send as document.
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".m4b", ".ogg", ".oga", ".opus", ".flac", ".wav", ".aac"}


def safe_display_name(name: str) -> str:
    """Make filename safe for console output (Windows cp1252)."""
    return name.encode("ascii", errors="replace").decode("ascii")

# Delay between uploads to avoid rate limits (seconds)
UPLOAD_DELAY = 0.5

# Telegram Bot API base URL
API_BASE = "https://api.telegram.org/bot"


def get_token(env_key: str = "TELEGRAM_BOT_TOKEN") -> str | None:
    return os.environ.get(env_key)


def collect_files(folder: str) -> list[tuple[str, str]]:
    """Return list of (full_path, filename) for supported audio/document files."""
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in AUDIO_EXTENSIONS or ext in {".zip", ".pdf", ".txt", ".jpg", ".jpeg", ".png"}:
            out.append((path, name))
        # Also allow any other extension as document (e.g. .webm, .mkv)
        elif ext:
            out.append((path, name))
    return out


def is_audio(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in AUDIO_EXTENSIONS


def upload_file(
    token: str,
    channel: str,
    file_path: str,
    filename: str,
    use_audio: bool,
    topic_id: int | None = None,
) -> tuple[bool, str | None]:
    """Upload one file via sendAudio or sendDocument. Returns (success, error_msg)."""
    method = "sendAudio" if use_audio else "sendDocument"
    param_name = "audio" if use_audio else "document"
    url = f"{API_BASE}{token}/{method}"

    payload = {"chat_id": channel}
    if topic_id is not None:
        payload["message_thread_id"] = topic_id

    try:
        with open(file_path, "rb") as f:
            files = {param_name: (filename, f)}
            r = requests.post(url, data=payload, files=files, timeout=120)
    except OSError as e:
        return False, str(e)
    except requests.RequestException as e:
        return False, str(e)

    try:
        data = r.json()
    except Exception:
        data = {}
    if not data.get("ok"):
        msg = data.get("description", r.text or "No response body")
        params = data.get("parameters", {})
        retry_after = params.get("retry_after")
        return False, msg if not retry_after else f"{msg} (retry_after={retry_after}s)"
    return True, None


def send_media_group(
    token: str,
    channel: str,
    file_paths: list[tuple[str, str]],
    topic_id: int | None = None,
) -> tuple[bool, str | None]:
    """Send 2-10 audio files as one album. file_paths = [(path, filename), ...]. Returns (success, error_msg)."""
    if not (2 <= len(file_paths) <= 10):
        return False, "sendMediaGroup requires 2-10 items"
    url = f"{API_BASE}{token}/sendMediaGroup"
    media = []
    files_list = []
    for i, (path, name) in enumerate(file_paths):
        media.append({"type": "audio", "media": f"attach://file{i}", "title": name[:64]})
    payload = {"chat_id": channel, "media": json.dumps(media)}
    if topic_id is not None:
        payload["message_thread_id"] = topic_id
    try:
        with requests.Session() as session:
            file_objs = []
            try:
                for i, (path, name) in enumerate(file_paths):
                    f = open(path, "rb")
                    file_objs.append(f)
                    files_list.append((f"file{i}", (name, f)))
                r = session.post(url, data=payload, files=files_list, timeout=180)
            finally:
                for f in file_objs:
                    f.close()
    except OSError as e:
        return False, str(e)
    except requests.RequestException as e:
        return False, str(e)
    try:
        data = r.json()
    except Exception:
        data = {}
    if not data.get("ok"):
        msg = data.get("description", r.text or "No response body")
        return False, msg
    return True, None


def _upload_one(
    item: tuple[int, str, str, bool],
    token: str,
    channel: str,
    topic_id: int | None = None,
) -> tuple[int, str, bool, str | None]:
    """Worker: (index, path, name, use_audio) -> (index, name, success, error)."""
    i, path, name, use_audio = item
    ok, err = upload_file(token, channel, path, name, use_audio, topic_id=topic_id)
    return (i, name, ok, err)


def upload_folder_to_telegram(
    token: str,
    channel: str,
    folder_path: str,
    topic_id: int | None = None,
    album_size: int = 0,
    workers: int = 5,
    progress_callback: Callable[[int, int, str], None] | None = None,
    file_list: list[tuple[str, str]] | None = None,
) -> tuple[int, int]:
    """
    Upload all supported files from folder_path to the Telegram channel.
    Returns (uploaded_count, failed_count).
    - topic_id: optional message_thread_id (channel topic = folder).
    - album_size: 0 = one message per file; 2-10 = group that many audio files per album (sendMediaGroup).
    - workers: parallel uploads when album_size=0.
    - progress_callback(current, total, message) called from any thread.
    - file_list: if provided, use this list of (path, filename) instead of scanning folder_path.
    """
    folder = os.path.abspath(folder_path)
    files = file_list if file_list is not None else collect_files(folder)
    if not files:
        return 0, 0
    total = len(files)
    ok = 0
    fail = 0
    lock = threading.Lock()

    def report(current: int, msg: str) -> None:
        if progress_callback:
            progress_callback(current, total, msg)

    if album_size >= 2:
        album_size = min(10, max(2, album_size))
        audio_batch = []
        non_audio = []
        for path, name in files:
            if is_audio(name):
                audio_batch.append((path, name))
            else:
                non_audio.append((path, name))
        i = 0
        for start in range(0, len(audio_batch), album_size):
            batch = audio_batch[start : start + album_size]
            if len(batch) < 2:
                for path, name in batch:
                    success, err = upload_file(token, channel, path, name, True, topic_id=topic_id)
                    with lock:
                        if success:
                            ok += 1
                        else:
                            fail += 1
                    i += 1
                    report(ok + fail, f"Uploaded {ok + fail}/{total}")
            else:
                success, err = send_media_group(token, channel, batch, topic_id=topic_id)
                with lock:
                    if success:
                        ok += len(batch)
                    else:
                        fail += len(batch)
                        if progress_callback:
                            progress_callback(ok + fail, total, f"Album failed: {err or 'unknown'}")
                i += len(batch)
                report(ok + fail, f"Uploaded {ok + fail}/{total}")
        for path, name in non_audio:
            success, err = upload_file(token, channel, path, name, False, topic_id=topic_id)
            with lock:
                if success:
                    ok += 1
                else:
                    fail += 1
            report(ok + fail, f"Uploaded {ok + fail}/{total}")
        return ok, fail

    tasks = [
        (i, path, name, is_audio(name))
        for i, (path, name) in enumerate(files, 1)
    ]
    workers = max(1, workers)

    if workers <= 1:
        for i, (path, name) in enumerate(files, 1):
            use_audio = is_audio(name)
            success, err = upload_file(token, channel, path, name, use_audio, topic_id=topic_id)
            if success:
                ok += 1
            else:
                fail += 1
            report(ok + fail, f"Uploaded {ok + fail}/{total}")
            if i < len(files) and UPLOAD_DELAY > 0:
                time.sleep(UPLOAD_DELAY)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_upload_one, t, token, channel, topic_id): t[0]
                for t in tasks
            }
            for future in as_completed(futures):
                i, name, success, err = future.result()
                with lock:
                    if success:
                        ok += 1
                    else:
                        fail += 1
                report(ok + fail, f"Uploaded {ok + fail}/{total}")
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload files from a folder to a Telegram channel (Bot API)."
    )
    parser.add_argument(
        "folder",
        help="Path to folder containing audio/files to upload",
    )
    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help=f"Channel username (default: {DEFAULT_CHANNEL})",
    )
    parser.add_argument(
        "--token",
        default=get_token(),
        help="Bot token (or set TELEGRAM_BOT_TOKEN)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=UPLOAD_DELAY,
        help=f"Seconds between uploads (default: {UPLOAD_DELAY})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list files that would be uploaded",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Upload only first N files (0 = all). Use 1 to test.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Parallel upload workers (default: 1). Use 8–16 for faster uploads.",
    )
    parser.add_argument(
        "--topic-id",
        type=int,
        default=None,
        metavar="ID",
        help="Channel topic ID (folder). Optional.",
    )
    parser.add_argument(
        "--album-size",
        type=int,
        default=0,
        metavar="N",
        help="Group audio into albums of N files (2-10). 0 = one message per file.",
    )
    args = parser.parse_args()

    folder = os.path.abspath(args.folder)
    files = collect_files(folder)
    if not files:
        print(f"No supported files found in: {folder}", file=sys.stderr)
        return 1

    if args.limit and args.limit > 0:
        files = files[: args.limit]

    print(f"Channel: {args.channel}", flush=True)
    print(f"Folder:  {folder}", flush=True)
    print(f"Files:   {len(files)}", flush=True)
    if args.topic_id is not None:
        print(f"Topic ID: {args.topic_id}", flush=True)
    if args.album_size:
        print(f"Album size: {args.album_size}", flush=True)
    if args.dry_run:
        for _path, name in files[:20]:
            print(f"  {safe_display_name(name)}")
        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more")
        return 0

    if not args.token:
        print(
            "Bot token required. Create a bot with @BotFather, add it as admin to your channel,\n"
            "then set TELEGRAM_BOT_TOKEN or pass --token.",
            file=sys.stderr,
        )
        return 1

    if args.limit and args.limit > 0:
        print(f"(Upload limited to first {len(files)} file(s))\n", flush=True)

    workers = max(1, args.workers)
    if workers > 1 and args.album_size == 0:
        print(f"Parallel workers: {workers}\n", flush=True)

    print_lock = threading.Lock()

    def progress_cb(current: int, total: int, message: str) -> None:
        with print_lock:
            print(f"[{current}/{total}] {message}", flush=True)

    ok, fail = upload_folder_to_telegram(
        token=args.token,
        channel=args.channel,
        folder_path=folder,
        topic_id=args.topic_id,
        album_size=args.album_size,
        workers=workers,
        progress_callback=progress_cb,
        file_list=files,
    )

    print(f"\nDone. Uploaded: {ok}, Failed: {fail}", flush=True)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
