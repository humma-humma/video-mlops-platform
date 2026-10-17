from celery import Celery

from .config import settings

celery_app = Celery("video_service", broker=settings.broker_url, backend=settings.broker_url)
celery_app.conf.task_track_started = True
celery_app.conf.update(
    task_default_queue=settings.task_queue,
    task_publish_retry=False,
    broker_connection_timeout=3,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.task_soft_time_limit,
    task_time_limit=settings.task_time_limit,
    task_acks_late=True,
    task_reject_on_worker_lost=False,
    broker_transport_options={"visibility_timeout": settings.task_time_limit + 120,
                              "socket_connect_timeout": 3, "socket_timeout": 3},
)
