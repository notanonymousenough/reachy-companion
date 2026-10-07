FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends sox libgomp1 libatomic1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements/worker.lock /app/requirements/worker.lock
RUN pip install --no-cache-dir -r /app/requirements/worker.lock
COPY pyproject.toml /app/
COPY src /app/src
RUN pip install --no-cache-dir --no-deps /app
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "reachy_companion"]
CMD ["--config", "/config/config.local.json", "worker", "serve"]
