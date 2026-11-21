FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Unprivileged user; /data holds the report database and the drought files.
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /data/reports /data/edo \
    && chown -R app /data
USER app

EXPOSE 8000

# --proxy-headers: the service runs behind a TLS-terminating reverse proxy.
CMD ["fastapi", "run", "app/main.py", "--proxy-headers", "--port", "8000"]
