#!/usr/bin/env bash
# Deploys the application on a Linux server: Docker, Traefik, domain,
# language-model interface, start and check. Safe to run again; see --help.
# shellcheck source-path=SCRIPTDIR
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${DEPLOY_ENV_FILE:-$ROOT_DIR/.env}

usage() {
  cat <<'EOF'
Usage: scripts/deploy.sh [options]

Brings the application up under HTTPS on a Linux server, in five steps:
  1. Docker    installs Docker Engine and the Compose plugin when missing
               (Debian, Ubuntu); an existing installation is only checked.
  2. Traefik   a running Traefik and the network "proxy" are never changed:
               the names of the HTTPS entry point and the certificate resolver
               are read from it. Without Traefik the script creates the network
               and starts its own (ports 80/443, Let's Encrypt).
  3. Domain    asks for the domain, checks its DNS record, writes DOMAIN.
  4. AI        optional language-model interface for the Report summary.
  5. Start     docker compose up -d --build, waits for the api service and
               checks https://DOMAIN/api/health and the start page.

Settings live in .env (created from .env.example, mode 600). Existing values
are kept; a backup is written before every change; values are never printed.
Before anything is changed the script shows what it found and what it will do.

Options:
  --dry-run                    detect and print the plan; change nothing, ask nothing
  -y, --yes                    no questions: values come from the options or from
                               .env; a missing required value is an error
  --domain NAME                public host name, e.g. hydromiara.example.org
  --traefik-entrypoint NAME    HTTPS entry point of an existing Traefik
  --traefik-certresolver NAME  certificate resolver of an existing Traefik
  --acme-email ADDRESS         Let's Encrypt account address; needed only when the
                               script starts its own Traefik; stored only in .env
  --ai-base-url URL            base address of a service compatible with the
                               OpenAI Chat Completions interface (https)
  --ai-model NAME              model name as the service knows it
  --ai-key-file PATH           file whose first line is the service key; the key
                               can also be passed in the environment variable
                               AI_API_KEY (never as an option: options are visible
                               in the process list)
  --no-ai                      no language model: the Report summary comes from
                               the built-in template
  --skip-dns-check             do not compare the DNS record with this server
  --enable-log-rotation        write the daemon-wide log rotation and RESTART
                               Docker (interrupts every container on the server).
                               Never implied by --yes. On a Docker installed by
                               this run the rotation is configured automatically.
  -h, --help                   this text

Examples:
  scripts/deploy.sh --dry-run
  scripts/deploy.sh
  scripts/deploy.sh --yes --domain hydromiara.example.org --no-ai

The script never removes containers, images or volumes and never touches
containers of other projects. To stop the application: docker compose down
EOF
}

ASSUME_YES=0
DRY_RUN=0
ENABLE_LOG_ROTATION=0
OPT_DOMAIN=""
OPT_ENTRYPOINT=""
OPT_CERTRESOLVER=""
OPT_ACME_EMAIL=""
OPT_AI_BASE_URL=""
OPT_AI_MODEL=""
OPT_AI_KEY_FILE=""
OPT_NO_AI=0
OPT_SKIP_DNS=0
# The key may come through the environment; everything else Compose reads must
# come from .env only, so the same names are removed from the environment.
OPT_AI_KEY=${AI_API_KEY:-}
unset AI_API_KEY DOMAIN TRAEFIK_ENTRYPOINT TRAEFIK_CERTRESOLVER ACME_EMAIL OPENAI_MODEL \
  AI_BASE_URL AI_TIMEOUT_S AI_REASONING_EFFORT EDO_DATA_PATH FORWARDED_ALLOW_IPS

# Check with: shellcheck -x scripts/deploy.sh (follows the files below).
# shellcheck source=deploy/lib.sh
source "$SCRIPT_DIR/deploy/lib.sh"
# shellcheck source=deploy/envfile.sh
source "$SCRIPT_DIR/deploy/envfile.sh"
# shellcheck source=deploy/parsers.sh
source "$SCRIPT_DIR/deploy/parsers.sh"
# shellcheck source=deploy/docker.sh
source "$SCRIPT_DIR/deploy/docker.sh"
# shellcheck source=deploy/traefik.sh
source "$SCRIPT_DIR/deploy/traefik.sh"
# shellcheck source=deploy/settings.sh
source "$SCRIPT_DIR/deploy/settings.sh"
# shellcheck source=deploy/launch.sh
source "$SCRIPT_DIR/deploy/launch.sh"

need_value() { [[ $# -ge 2 && -n "$2" ]] || die "option $1 needs a value (see --help)"; }

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help) usage && exit 0 ;;
      -y | --yes) ASSUME_YES=1 ;;
      --dry-run) DRY_RUN=1 ;;
      --no-ai) OPT_NO_AI=1 ;;
      --skip-dns-check) OPT_SKIP_DNS=1 ;;
      --enable-log-rotation) ENABLE_LOG_ROTATION=1 ;;
      --domain) need_value "$@" && OPT_DOMAIN=$2 && shift ;;
      --traefik-entrypoint) need_value "$@" && OPT_ENTRYPOINT=$2 && shift ;;
      --traefik-certresolver) need_value "$@" && OPT_CERTRESOLVER=$2 && shift ;;
      --acme-email) need_value "$@" && OPT_ACME_EMAIL=$2 && shift ;;
      --ai-base-url) need_value "$@" && OPT_AI_BASE_URL=$2 && shift ;;
      --ai-model) need_value "$@" && OPT_AI_MODEL=$2 && shift ;;
      --ai-key-file) need_value "$@" && OPT_AI_KEY_FILE=$2 && shift ;;
      *) die "unknown option: $1 (see --help)" ;;
    esac
    shift
  done
  if [[ "$OPT_NO_AI" == 1 && -n "$OPT_AI_BASE_URL$OPT_AI_MODEL$OPT_AI_KEY_FILE" ]]; then
    die "--no-ai cannot be combined with the --ai-* options"
  fi
  if [[ "$ASSUME_YES" != 1 && "$DRY_RUN" != 1 && ! -t 0 ]]; then
    die "no terminal to ask questions on: use --yes with parameters, or --dry-run"
  fi
}

describe_plan() {
  step "Plan"
  env_describe_plan
  dns_describe
  ai_describe
  data_describe
  logrot_describe_plan
  traefik_describe_plan
  info "  Application: docker compose up -d --build (project \"$APP_PROJECT\", services api and web)"
  step "Not touched"
  info "  Containers, images, volumes and networks of other projects; nothing is removed."
  if [[ "$TRAEFIK_STATE" == existing ]]; then
    info "  The running Traefik, its configuration and certificates, ports 80/443, the network \"$PROXY_NETWORK\"."
  fi
  if [[ "$DOCKER_STATE" == present && "$DOCKER_FRESH" != 1 && "$ENABLE_LOG_ROTATION" != 1 ]]; then
    info "  The Docker installation and the daemon configuration (no restart of Docker)."
  fi
  info "  Values already present in .env, unless listed above under \"replace\"."
}

main() {
  parse_args "$@"
  have curl || die "curl is required"
  [[ -f "$ROOT_DIR/docker-compose.yml" ]] || die "docker-compose.yml not found in $ROOT_DIR"
  if [[ "$DRY_RUN" == 1 ]]; then info "DRY RUN: nothing will be changed."; fi

  step "Step 1/5: Docker"
  docker_detect
  docker_describe
  docker_ensure
  if [[ "$DOCKER_FRESH" == 1 ]]; then docker_describe; fi

  step "Step 2/5: Traefik"
  if [[ "$DOCKER_STATE" == present ]]; then traefik_detect; fi
  traefik_describe
  traefik_settings

  step "Step 3/5: Domain"
  domain_settings
  dns_detect
  if [[ "$DOCKER_STATE" == present ]]; then
    collisions_detect
    forwarded_settings
  fi

  step "Step 4/5: Language-model interface"
  ai_settings
  data_detect

  if [[ ${#PROBLEMS[@]} -gt 0 ]]; then
    step "Cannot continue"
    printf '  - %s\n' "${PROBLEMS[@]}" >&2
    die "resolve the points above and run the script again; nothing was changed"
  fi

  describe_plan
  if [[ "$DRY_RUN" == 1 ]]; then
    info ""
    info "Dry run finished: nothing was changed."
    exit 0
  fi
  dns_gate
  if interactive; then
    confirm "Apply this plan?" || die "stopped by the operator; nothing was changed"
  fi

  step "Step 5/5: Start"
  logrot_apply
  network_apply
  forwarded_settings
  env_apply
  traefik_apply
  data_apply
  app_launch
  wait_api_health
  public_check
  data_hint
  info ""
  info "Deployment finished: the application answers under https://<DOMAIN>/ (DOMAIN from .env)."
}

main "$@"
