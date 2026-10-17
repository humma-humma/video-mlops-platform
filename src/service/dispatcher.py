"""Recover unpublished jobs and expired attempts independently of GPU capacity."""
import time

from .config import settings
from .lifecycle import dispatch_pending, reconcile_expired, retry_dependencies
from .telemetry import event

def tick():
    expired = reconcile_expired()
    retried = retry_dependencies()
    return {"dispatched": dispatch_pending(), "expired": expired, "retried": retried}

if __name__ == "__main__":
    while True:
        try:
            tick()
        except Exception:
            event("dispatcher_dependency_unavailable")
        time.sleep(settings.dispatch_interval_seconds)
