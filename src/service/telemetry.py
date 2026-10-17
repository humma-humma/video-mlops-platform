"""Content-free structured events and bounded HTTP metric labels."""
from collections import Counter
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
from threading import Lock

trace_id = ContextVar("trace_id", default=None)
requests = Counter()
duration_sum = Counter()
lock = Lock()

class EventFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname, "event": record.getMessage(),
            **getattr(record, "context", {}),
        })

logger = logging.getLogger("video_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(EventFormatter())
    logger.addHandler(handler)
logger.propagate = False

def event(name, **context):
    logger.info(name, extra={"context": {k: v for k, v in context.items() if v is not None}})

def observe_request(method, route, status, seconds):
    with lock:
        requests[method, route, status] += 1
        duration_sum[method, route] += seconds

def http_metrics():
    with lock:
        counts, durations = dict(requests), dict(duration_sum)
    lines = ["# TYPE video_http_requests_total counter"]
    for (method, route, status), count in sorted(counts.items()):
        labels = f'method={json.dumps(method)},route={json.dumps(route)},status="{status}"'
        lines.append(f"video_http_requests_total{{{labels}}} {count}")
    lines.append("# TYPE video_http_request_duration_seconds summary")
    for (method, route), seconds in sorted(durations.items()):
        labels = f'method={json.dumps(method)},route={json.dumps(route)}'
        count = sum(n for (m, r, _), n in counts.items() if (m, r) == (method, route))
        lines.extend([f"video_http_request_duration_seconds_sum{{{labels}}} {seconds}",
                      f"video_http_request_duration_seconds_count{{{labels}}} {count}"])
    return lines
