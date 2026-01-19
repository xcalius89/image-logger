# tracker/Dockerfile
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REPO_ROOT=/app

WORKDIR /app

# system deps needed for some python packages and for cloning Sherlock if requested
RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential curl \
  && rm -rf /var/lib/apt/lists/*

# copy and install python deps
COPY tracker/requirements.txt /app/tracker/requirements.txt
RUN pip install --upgrade pip \
  && pip install --no-cache-dir -r /app/tracker/requirements.txt

# copy project
COPY . /app

# create runtime dirs
RUN mkdir -p /app/tracker_data /app/.pages/sherlock /app/.tools

EXPOSE 5000

# default command: run Gunicorn serving the Flask app
# In production you may want to use a process manager or different cmd for workers
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "tracker.app:app", "--workers", "3", "--threads", "2"]