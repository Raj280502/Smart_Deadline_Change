import os
import threading
from datetime import datetime

from integrations.placement_scraper import sync_placement_drives
from storage.auth_repository import get_user_credentials


_scheduler_thread = None
_stop_event = threading.Event()
_status = {
    "running": False,
    "interval_minutes": None,
    "send_notifications": True,
    "user_id": None,
    "last_run_at": None,
    "last_result": None,
    "last_error": None,
}


def start_scheduler(
    interval_minutes: int = None,
    send_notifications: bool = True,
    user_id: int = 1,
) -> dict:
    """Start a lightweight in-process placement watcher loop."""
    global _scheduler_thread

    if _scheduler_thread and _scheduler_thread.is_alive():
        return get_scheduler_status()

    interval_minutes = interval_minutes or int(
        os.getenv("PLACEMENT_WATCH_INTERVAL_MINUTES", "30")
    )
    _stop_event.clear()
    _status.update({
        "running": True,
        "interval_minutes": interval_minutes,
        "send_notifications": send_notifications,
        "user_id": user_id,
        "last_error": None,
    })

    _scheduler_thread = threading.Thread(
        target=_run_loop,
        args=(interval_minutes, send_notifications, user_id),
        daemon=True,
    )
    _scheduler_thread.start()
    return get_scheduler_status()


def stop_scheduler() -> dict:
    _stop_event.set()
    _status["running"] = False
    return get_scheduler_status()


def get_scheduler_status() -> dict:
    return dict(_status)


def _run_loop(interval_minutes: int, send_notifications: bool, user_id: int):
    while not _stop_event.is_set():
        try:
            _status["last_run_at"] = datetime.now().isoformat()
            credentials = get_user_credentials(user_id)
            _status["last_result"] = sync_placement_drives(
                send_notifications=send_notifications,
                credentials=credentials,
                user_id=user_id,
            )
            _status["last_error"] = None
        except Exception as exc:
            _status["last_error"] = str(exc)

        _stop_event.wait(max(interval_minutes, 1) * 60)

    _status["running"] = False
