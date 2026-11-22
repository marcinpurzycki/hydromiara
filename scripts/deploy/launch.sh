# shellcheck shell=bash
# Step 5: the drought indicator directory, starting the application and checking it.
# Uses helpers from lib.sh and envfile.sh.

APP_UID=10001   # the unprivileged user of the api image (backend/Dockerfile)
HEALTH_PROBE="import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
HEALTH_WAIT_S=${DEPLOY_HEALTH_WAIT_S:-180}
PUBLIC_TRIES=${DEPLOY_PUBLIC_TRIES:-12}

DATA_DIR=""
DATA_FILES=0

# The host directory mounted read-only as /data/edo (EDO_DATA_PATH, default ./data/edo).
data_detect() {
  local path
  path=$(env_value EDO_DATA_PATH)
  path=${path:-./data/edo}
  [[ "$path" == /* ]] || path="$ROOT_DIR/${path#./}"
  DATA_DIR=$path
  DATA_FILES=0
  if [[ -d "$DATA_DIR" ]]; then
    DATA_FILES=$(find "$DATA_DIR" -maxdepth 1 -type f -name 'cdinx_m_edo_*.tif' 2>/dev/null | wc -l)
  fi
}

data_describe() {
  if [[ ! -d "$DATA_DIR" ]]; then
    info "  Drought indicator files: the directory does not exist yet; it will be created empty"
  else
    info "  Drought indicator files: $DATA_FILES file(s) in the data directory"
  fi
}

data_hint() {
  [[ "$DATA_FILES" -eq 0 ]] || return 0
  info "NOTE: no drought indicator files found. The application works without them (the Report"
  info "  states the missing drought background). To add them: download the yearly archives of the"
  info "  Combined Drought Indicator from the source named in README (section on data sources) and run"
  info "    python3 scripts/unpack_drought_files.py ARCHIVE_DIR"
  info "  in the repository directory; no restart is needed."
}

# Creates the directory when missing and checks that the container user can read it.
data_apply() {
  local unreadable
  if [[ ! -d "$DATA_DIR" ]]; then
    mkdir -p "$DATA_DIR"
    chmod 755 "$DATA_DIR"
    info "created the data directory for the drought indicator files"
    return 0
  fi
  unreadable=$(find "$DATA_DIR" -maxdepth 1 \( -type d ! -perm -o=rx -o -type f ! -perm -o=r \) -print -quit 2>/dev/null)
  if [[ -n "$unreadable" ]]; then
    warn "the data directory or a file in it is not readable for other users; the container" \
      "user (uid $APP_UID) needs read access: chmod -R o+rX on the data directory"
  fi
}

app_launch() {
  info "building and starting the application (docker compose up -d --build)"
  app_compose up -d --build
}

# Waits until the api container answers its own health address.
wait_api_health() {
  local waited=0
  info "waiting for the api service (up to ${HEALTH_WAIT_S}s)"
  while [[ $waited -lt $HEALTH_WAIT_S ]]; do
    if app_compose exec -T api python -c "$HEALTH_PROBE" >/dev/null 2>&1; then
      info "the api service is healthy"
      return 0
    fi
    sleep 3
    waited=$((waited + 3))
  done
  warn "the api service did not become healthy in ${HEALTH_WAIT_S}s. State and last log lines:"
  app_compose ps || true
  app_compose logs --tail 30 api || true
  die "cause: the api container does not start or does not answer; see the log above"
}

# Names the most likely cause when the public address does not answer.
public_diagnose() {
  local domain=$1 url="https://$1/api/health" code
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 10 \
    --resolve "$domain:443:127.0.0.1" "$url" 2>/dev/null || true)
  case "$code" in
    200)
      if curl -fsS -o /dev/null --max-time 10 --resolve "$domain:443:127.0.0.1" "$url" 2>/dev/null; then
        warn "cause: DNS or firewall. The application answers on this server with a valid" \
          "certificate, but not through the public address: check the DNS record and that" \
          "port 443 is open from the Internet."
      else
        warn "cause: certificate. Routing works on this server but the certificate is not valid" \
          "(yet). Check that the DNS record points here, that port 80 is reachable from the" \
          "Internet, that TRAEFIK_CERTRESOLVER names an existing resolver, and the Traefik log."
      fi
      ;;
    404)
      warn "cause: labels. Traefik answers but has no router for the domain: check that" \
        "TRAEFIK_ENTRYPOINT names the HTTPS entry point, that DOMAIN is right and that the" \
        "containers are attached to the network \"proxy\"."
      ;;
    502 | 503 | 504)
      warn "cause: container. Traefik has the router but cannot reach the service" \
        "(status $code): check \"docker compose ps\" and the network \"proxy\"."
      ;;
    000 | "")
      warn "cause: nothing answers HTTPS on port 443 of this server: Traefik is not running" \
        "or its HTTPS entry point is not published."
      ;;
    *) warn "cause unclear: the health address answers with status $code on this server." ;;
  esac
}

# Checks https://DOMAIN/api/health and the start page from outside the containers.
public_check() {
  local domain try
  domain=$(env_get DOMAIN)
  info "checking https://<DOMAIN>/api/health (a new certificate can take a minute)"
  for ((try = 1; try <= PUBLIC_TRIES; try++)); do
    if curl -fsS -o /dev/null --max-time 10 "https://$domain/api/health" 2>/dev/null; then
      info "OK: https://<DOMAIN>/api/health answers 200"
      if curl -fsS -o /dev/null --max-time 10 "https://$domain/" 2>/dev/null; then
        info "OK: the start page https://<DOMAIN>/ answers"
      else
        warn "the health address works but the start page does not answer 200:" \
          "check the web service (docker compose ps, docker compose logs web)"
      fi
      return 0
    fi
    [[ $try -eq $PUBLIC_TRIES ]] || sleep 10
  done
  warn "https://<DOMAIN>/api/health did not answer 200"
  public_diagnose "$domain"
  die "the containers are running but the application is not reachable under the domain"
}
