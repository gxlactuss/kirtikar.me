# The Kirtikar demo API, as it runs on a Hugging Face Space.
#
# Three things about this image are Spaces-specific and not incidental:
# it listens on 7860 (the port a Docker Space routes to), it runs as uid 1000
# (the uid a Space starts the container with, so anything written at runtime
# has to be owned by it), and the IS-Net model is baked in at build time
# rather than fetched on first use — a 176MB download on the first visitor's
# run is exactly the kind of cold start this deployment exists to avoid.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# libgomp1 is onnxruntime's OpenMP runtime and libglib2.0-0 is what
# opencv-python-headless still links against; neither comes with the slim base
# and both fail only at import time, which is a confusing way to find out.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app
WORKDIR /app

# constraints.txt pins every transitive package too, so a rebuild months from
# now installs the same bytes the tests ran against.
COPY --chown=app:app requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

USER app

# Download the cutout model into the image. U2NET_HOME has to be set for both
# this build step and the running container, or the warm-up at startup looks
# in a different directory and downloads it all over again.
ENV U2NET_HOME=/home/app/.u2net
RUN python -c "import rembg; rembg.new_session('isnet-general-use')"

COPY --chown=app:app . /app

# Writable state lives under the home directory because that is what uid 1000
# owns. It is ephemeral: a Space restart takes the database and the uploaded
# media with it, which the site already handles — a 404 on a listing it was
# polling is read as "the Space restarted" and falls back to a recorded run.
RUN mkdir -p /home/app/data/media

ENV DEMO_MODE=true \
    ENVIRONMENT=demo \
    DATABASE_URL=sqlite:////home/app/data/kirtikar.db \
    MEDIA_STORAGE_DIR=/home/app/data/media \
    DEMO_LIMIT_STATE_PATH=/home/app/data/demo-limit.json \
    PIPELINE_MAX_STAGE_ATTEMPTS=2

EXPOSE 7860

HEALTHCHECK --interval=60s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:7860/health || exit 1

# One worker, deliberately. The pipeline is dispatched through FastAPI's
# BackgroundTasks, the demo's daily cap counts in process memory, and the
# database is a single SQLite file — all three assume one process, and a
# second worker would quietly break all three at once.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
