from celery import Celery

from .config import settings

celery_app = Celery("video_service", broker=settings.broker_url, backend=settings.broker_url)
celery_app.conf.task_track_started = True
