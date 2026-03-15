"""
yt-dlp auto-updater: prepend writable updates/ to path and allow installing latest from PyPI.
"""
import os
import sys
import json
import zipfile
import urllib.request
import threading
from typing import Optional, Tuple, Callable

# Writable directory for updated yt-dlp (takes precedence over bundled)
UPDATES_DIR_NAME = "ytdlp_updates"


def get_updates_dir(app_root: str) -> str:
    """Return the writable directory for yt-dlp updates."""
    if getattr(sys, "frozen", False):
        # Next to the executable (e.g. dist/YT-Downloader/)
        base = os.path.dirname(sys.executable)
    else:
        base = app_root
    return os.path.join(base, UPDATES_DIR_NAME)


def add_updates_to_path(app_root: str) -> bool:
    """
    Prepend updates directory to sys.path so a user-installed yt-dlp takes precedence.
    Call this before importing yt_dlp. Returns True if updates dir was added.
    """
    updates_dir = get_updates_dir(app_root)
    if not os.path.isdir(updates_dir):
        return False
    if os.path.isdir(os.path.join(updates_dir, "yt_dlp")):
        sys.path.insert(0, updates_dir)
        return True
    return False


def get_current_version() -> str:
    """Return the current yt-dlp version string."""
    try:
        import yt_dlp
        return getattr(yt_dlp, "__version__", "unknown")
    except Exception:
        return "unknown"


def get_latest_version() -> Optional[str]:
    """Fetch latest yt-dlp version from PyPI. Returns None on error."""
    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/yt-dlp/json",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return data.get("info", {}).get("version")
    except Exception:
        return None


def _download_file(url: str, dest_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "YT-Downloader/2.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            chunk_size = 65536
            downloaded = 0
            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total:
                        progress_callback(downloaded, total)
        return True
    except Exception:
        return False


def update_ytdlp(app_root: str, progress_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
    """
    Download latest yt-dlp wheel from PyPI and extract to updates dir.
    progress_callback(message: str) is called with status strings.
    Returns (success, message).
    """
    def log(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    updates_dir = get_updates_dir(app_root)
    try:
        os.makedirs(updates_dir, exist_ok=True)
    except Exception as e:
        return False, f"Cannot create folder: {e}"

    log("Fetching PyPI metadata...")
    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/yt-dlp/json",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return False, f"Failed to fetch version info: {e}"

    version = data.get("info", {}).get("version")
    if not version:
        return False, "Could not determine latest version"

    # Find wheel URL (prefer manylinux/win pure Python wheel)
    urls = data.get("urls", [])
    wheel_url = None
    for u in urls:
        if u.get("packagetype") == "bdist_wheel" and u.get("filename", "").endswith(".whl"):
            # Prefer no binary (py3-none-any) for portability
            fn = u["filename"]
            if "py3-none-any" in fn or "any.whl" in fn:
                wheel_url = u.get("url")
                break
    if not wheel_url and urls:
        for u in urls:
            if u.get("packagetype") == "bdist_wheel":
                wheel_url = u.get("url")
                break
    if not wheel_url:
        return False, "No wheel found for this platform"

    log(f"Downloading yt-dlp {version}...")
    wheel_path = os.path.join(updates_dir, f"yt-dlp-{version}-py3-none-any.whl")
    if not _download_file(wheel_url, wheel_path, None):
        return False, "Download failed"

    log("Extracting...")
    try:
        with zipfile.ZipFile(wheel_path, "r") as z:
            for name in z.namelist():
                if name.startswith("yt_dlp/"):
                    z.extract(name, updates_dir)
                elif name.startswith("yt_dlp-") and "dist-info" in name:
                    z.extract(name, updates_dir)
        try:
            os.remove(wheel_path)
        except Exception:
            pass
    except Exception as e:
        return False, f"Extract failed: {e}"

    log("Done. Restart the app to use the new version.")
    return True, f"Updated to yt-dlp {version}. Restart the app to use it."
