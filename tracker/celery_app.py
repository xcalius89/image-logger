from celery import Celery

def make_celery(app):
    celery = Celery(app.import_name, broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)
    return celery


celery = make_celery(app)

# Example task
@celery.task
def add(x, y):
    return x + y

