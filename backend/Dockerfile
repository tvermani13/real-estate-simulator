FROM python:3.11.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    NVIDIA_VISIBLE_DEVICES=void

WORKDIR /app

RUN groupadd --gid 10001 hearthline \
    && useradd --uid 10001 --gid hearthline --create-home --home-dir /home/hearthline hearthline \
    && mkdir -p /data \
    && chown hearthline:hearthline /data

COPY requirements.lock ./
RUN python -m pip install --requirement requirements.lock

COPY --chown=hearthline:hearthline app ./app

USER hearthline
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
