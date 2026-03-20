"""Background scheduler: fires callbacks at scheduled wall-clock times."""
import threading
import time
from typing import Callable, Dict, Tuple


class DownloadScheduler:
    """
    Thread-safe scheduler. Each item has an id, a UNIX timestamp to fire at,
    and a zero-arg callback. Polls every 1 second.
    """

    def __init__(self):
        self._items: Dict[str, Tuple[float, Callable]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def add(self, item_id: str, fire_at: float, callback: Callable) -> None:
        with self._lock:
            self._items[item_id] = (fire_at, callback)

    def cancel(self, item_id: str) -> None:
        with self._lock:
            self._items.pop(item_id, None)

    def get_scheduled(self) -> Dict[str, float]:
        """Return {item_id: fire_at} for all pending items."""
        with self._lock:
            return {k: v[0] for k, v in self._items.items()}

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            to_fire = []
            with self._lock:
                for item_id, (fire_at, cb) in list(self._items.items()):
                    if now >= fire_at:
                        to_fire.append((item_id, cb))
                for item_id, _ in to_fire:
                    del self._items[item_id]
            for item_id, cb in to_fire:
                try:
                    cb()
                except Exception:
                    pass
            self._stop_event.wait(1)  # 1-second poll
