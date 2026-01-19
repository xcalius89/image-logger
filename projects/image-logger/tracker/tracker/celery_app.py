from celery import Celery
import os

# URL de Redis/Celery broker (se lee de la .env o toma el valor por defecto)
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')

celery = Celery('tracker', broker=REDIS_URL, backend=REDIS_URL)

celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)