"""YouTube search via yt-dlp ytsearch pseudo-URL."""
from typing import List, Dict
import yt_dlp


def search_youtube(query: str, max_results: int = 5) -> List[Dict]:
    """
    Return up to max_results YouTube search results for query.
    Each result: {url, title, uploader, duration_str, thumbnail}
    Returns [] on any error.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
        entries = info.get("entries") or []
        results = []
        for e in entries[:max_results]:
            vid_id = e.get("id", "")
            duration = e.get("duration") or 0
            mins, secs = divmod(int(duration), 60)
            results.append({
                "url":          f"https://www.youtube.com/watch?v={vid_id}",
                "title":        e.get("title", "Unknown"),
                "uploader":     e.get("uploader") or e.get("channel", ""),
                "duration_str": f"{mins}:{secs:02d}",
                "thumbnail":    e.get("thumbnail", ""),
            })
        return results
    except Exception:
        return []
