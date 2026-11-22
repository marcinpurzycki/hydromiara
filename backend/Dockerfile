FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# libexpat is needed by the raster library wheels and is missing in the slim image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Unprivileged user; /data holds the report database and the drought files.
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /data/reports /data/edo \
    && chown -R app /data
USER app

EXPOSE 8000

# --proxy-headers: the service runs behind a TLS-terminating reverse proxy; the
#   forwarding headers are trusted only from the addresses in FORWARDED_ALLOW_IPS.
# --no-access-log: the access log would hold client addresses and whole report
#   addresses, and the address of a Report is the only key to it.
# --no-server-header: the answer does not name the server software.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--no-access-log", "--no-server-header"]
