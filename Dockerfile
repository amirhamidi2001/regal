FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --uid 1000 --create-home app

WORKDIR /app

COPY requirements.txt /app/requirements.txt
ARG PIP_INDEX_URL
RUN if [ -n "${PIP_INDEX_URL:-}" ]; then \
        pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r /app/requirements.txt; \
    else \
        pip install --no-cache-dir -r /app/requirements.txt; \
    fi

COPY . /app
RUN mkdir -p /app/staticfiles && chown app:app /app/staticfiles

USER app

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
