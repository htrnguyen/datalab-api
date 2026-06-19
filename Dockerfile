FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends --no-upgrade \
    curl \
 && rm -rf /var/lib/apt/lists/* \
 && adduser --disabled-password --gecos "" --uid 1000 appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY --chown=appuser:appuser app/ ./app/

RUN mkdir -p /app/uploads && chown -R appuser:appuser /app/uploads

USER appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=0 \
    PORT=4242

EXPOSE 4242

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:4242/health || exit 1

STOPSIGNAL SIGTERM

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4242"]
