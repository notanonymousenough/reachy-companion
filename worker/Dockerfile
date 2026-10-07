FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends sox libgomp1 libatomic1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements/worker.lock /app/requirements/worker.lock
RUN --mount=type=cache,target=/root/.cache/pip \
    for attempt in 1 2 3; do \
      pip install --retries 5 --resume-retries 5 -r /app/requirements/worker.lock && exit 0; \
    done; exit 1
COPY pyproject.toml /app/
COPY src /app/src
RUN pip install --no-cache-dir --no-deps /app
ENV PYTHONUNBUFFERED=1
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.13/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.13/site-packages/nvidia/cudnn/lib:/usr/local/lib/python3.13/site-packages/nvidia/cuda_nvrtc/lib
ENV HF_HOME=/config/data/hf-cache
ENV HF_HUB_DISABLE_XET=1
ENTRYPOINT ["python", "-m", "reachy_companion"]
CMD ["--config", "/config/config.local.json", "worker", "serve"]
