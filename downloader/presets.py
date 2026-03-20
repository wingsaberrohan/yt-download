"""Format preset persistence — load/save ~/.ytdl_presets.json."""
import json
import os
from typing import List, Dict

PRESETS_PATH = os.path.expanduser("~/.ytdl_presets.json")

DEFAULT_PRESETS: List[Dict] = [
    {"name": "Music 320",    "format_type": "audio", "codec": "mp3",  "quality": "320"},
    {"name": "Archive 1080p","format_type": "video", "codec": "mp4",  "quality": "1080p"},
    {"name": "Quick MP3",    "format_type": "audio", "codec": "mp3",  "quality": "192"},
]


def load_presets() -> List[Dict]:
    """Return saved presets, or defaults if file doesn't exist."""
    try:
        with open(PRESETS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return [p.copy() for p in DEFAULT_PRESETS]


def save_presets(presets: List[Dict]) -> None:
    """Persist presets list to disk."""
    with open(PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(presets, f, indent=2)
