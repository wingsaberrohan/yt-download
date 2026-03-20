import time
from unittest.mock import MagicMock, patch

def test_schedule_fires_callback_at_time():
    from downloader.scheduler import DownloadScheduler
    fired = []
    sched = DownloadScheduler()
    sched.start()
    fire_at = time.time() + 1
    sched.add("item-1", fire_at, lambda: fired.append("item-1"))
    time.sleep(2.5)
    sched.stop()
    assert "item-1" in fired

def test_schedule_cancel_prevents_fire():
    from downloader.scheduler import DownloadScheduler
    fired = []
    sched = DownloadScheduler()
    sched.start()
    fire_at = time.time() + 2
    sched.add("item-2", fire_at, lambda: fired.append("item-2"))
    sched.cancel("item-2")
    time.sleep(3)
    sched.stop()
    assert "item-2" not in fired
