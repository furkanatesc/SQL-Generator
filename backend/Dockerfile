FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY evals /app/evals

# Sprint 32.0 — persistent state dirs. Named volumes inherit this ownership on first
# mount, so the non-root user can write the SQLite/trace DBs, uploads and the
# embedded Qdrant store.
RUN mkdir -p /app/uploads /app/data /app/qdrant_data \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Liveness probe; python:3.11-slim ships no curl, so use the stdlib.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
