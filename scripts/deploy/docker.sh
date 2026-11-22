# shellcheck shell=bash
# Step 1: Docker Engine and the Compose plugin.
# An existing installation is only checked. A missing one is installed following
# the official instructions (Debian and Ubuntu: Docker's apt repository,
# https://docs.docker.com/engine/install/debian/ and .../ubuntu/).
# Uses helpers from lib.sh.

OS_RELEASE_FILE=${DEPLOY_OS_RELEASE:-/etc/os-release}
DAEMON_JSON=${DEPLOY_DAEMON_JSON:-/etc/docker/daemon.json}
DOCKER_DOCS=https://docs.docker.com/engine/install/
COMPOSE_DOCS=https://docs.docker.com/compose/install/linux/
MIN_COMPOSE_MAJOR=2

OS_ID=""
OS_NAME=""
DOCKER_STATE=""    # present | absent
DOCKER_FRESH=0     # 1 when installed during this run
ENGINE_VERSION=""
COMPOSE_VERSION=""
LOGROT_STATE=""    # configured | custom | driver | none | unknown

# os_field KEY: value of KEY from os-release, without executing the file.
os_field() {
  local line value=""
  [[ -r "$OS_RELEASE_FILE" ]] || return 0
  while IFS= read -r line; do
    if [[ "$line" == "$1="* ]]; then value=${line#*=}; fi
  done <"$OS_RELEASE_FILE"
  value=${value#[\"\']}
  printf '%s' "${value%[\"\']}"
}

# apt_suite: the suite of Docker's repository, as in the official instructions
# (Ubuntu: UBUNTU_CODENAME first; Debian: VERSION_CODENAME).
apt_suite() {
  local suite=""
  [[ "$OS_ID" == ubuntu ]] && suite=$(os_field UBUNTU_CODENAME)
  [[ -n "$suite" ]] || suite=$(os_field VERSION_CODENAME)
  printf '%s' "$suite"
}

docker_supported_os() { [[ "$OS_ID" == debian || "$OS_ID" == ubuntu ]]; }

logrot_detect() {
  local driver
  if [[ -f "$DAEMON_JSON" ]]; then
    if grep -q '"max-size"' "$DAEMON_JSON" 2>/dev/null; then
      LOGROT_STATE=configured
    else
      LOGROT_STATE=custom
    fi
    return 0
  fi
  driver=$(dk info --format '{{.LoggingDriver}}' 2>/dev/null || true)
  case "$driver" in
    json-file) LOGROT_STATE=none ;;
    "") LOGROT_STATE=unknown ;;
    *) LOGROT_STATE=driver ;;
  esac
}

docker_detect() {
  OS_ID=$(os_field ID)
  OS_NAME=$(os_field PRETTY_NAME)
  if ! have docker; then
    DOCKER_STATE=absent
    return 0
  fi
  DOCKER_STATE=present
  if ! dk info >/dev/null 2>&1; then
    if [[ $EUID -ne 0 ]] && have sudo && sudo -n docker info >/dev/null 2>&1; then
      DOCKER=(sudo docker)
      warn "this user may not use Docker directly; using sudo. To allow it:" \
        "sudo usermod -aG docker \"\$USER\" (membership equals root access), then log in again"
    elif [[ $EUID -ne 0 ]]; then
      die "Docker is installed but this user cannot reach the daemon; run the script as root or through sudo"
    else
      die "Docker is installed but the daemon does not answer; check: systemctl status docker"
    fi
  fi
  ENGINE_VERSION=$(dk version --format '{{.Server.Version}}' 2>/dev/null || true)
  COMPOSE_VERSION=$(dk compose version --short 2>/dev/null || true)
  COMPOSE_VERSION=${COMPOSE_VERSION#v}
  if [[ -z "$COMPOSE_VERSION" ]]; then
    die "the Docker Compose plugin (docker compose) is missing; install it: $COMPOSE_DOCS"
  fi
  if [[ ! "${COMPOSE_VERSION%%.*}" =~ ^[0-9]+$ || "${COMPOSE_VERSION%%.*}" -lt $MIN_COMPOSE_MAJOR ]]; then
    die "Docker Compose $COMPOSE_VERSION is too old; version $MIN_COMPOSE_MAJOR or newer is needed: $COMPOSE_DOCS"
  fi
  logrot_detect
}

docker_describe() {
  info "  System: ${OS_NAME:-unknown} (id: ${OS_ID:-unknown})"
  if [[ "$DOCKER_STATE" == absent ]]; then
    info "  Docker: not installed"
    return 0
  fi
  info "  Docker: Engine ${ENGINE_VERSION:-?}, Compose $COMPOSE_VERSION (present; only checked)"
  case "$LOGROT_STATE" in
    configured) info "  Log rotation of the daemon: configured" ;;
    custom) info "  Log rotation of the daemon: not set; the existing daemon configuration is never edited" ;;
    driver) info "  Log rotation of the daemon: left to the configured logging driver" ;;
    none) info "  Log rotation of the daemon: not configured (no daemon configuration file)" ;;
    *) info "  Log rotation of the daemon: could not be determined" ;;
  esac
}

# Installs Docker Engine and the Compose plugin from Docker's apt repository.
docker_install() {
  local suite arch base="https://download.docker.com/linux/$OS_ID"
  docker_supported_os || die "automatic installation covers Debian and Ubuntu only." \
    "Install Docker Engine and the Compose plugin for your distribution ($DOCKER_DOCS) and run this script again"
  have apt-get || die "apt-get not found; install Docker by hand: $DOCKER_DOCS"
  suite=$(apt_suite)
  [[ -n "$suite" ]] || die "the release code name is missing in $OS_RELEASE_FILE; install Docker by hand: $DOCKER_DOCS"
  info "installing Docker Engine from $base (suite $suite)"
  as_root env DEBIAN_FRONTEND=noninteractive apt-get update
  as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl
  as_root install -m 0755 -d /etc/apt/keyrings
  as_root curl -fsSL "$base/gpg" -o /etc/apt/keyrings/docker.asc
  as_root chmod a+r /etc/apt/keyrings/docker.asc
  arch=$(dpkg --print-architecture)
  printf 'Types: deb\nURIs: %s\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' \
    "$base" "$suite" "$arch" | as_root tee /etc/apt/sources.list.d/docker.sources >/dev/null
  as_root env DEBIAN_FRONTEND=noninteractive apt-get update
  as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  if have systemctl; then
    as_root systemctl enable --now docker.service containerd.service
  else
    warn "systemctl not found; make sure the Docker service starts at boot"
  fi
  DOCKER_FRESH=1
  docker_detect
  [[ "$DOCKER_STATE" == present ]] || die "Docker was installed but the docker command is still missing"
}

# Step 1 as a whole: install when missing (after consent), else nothing.
docker_ensure() {
  [[ "$DOCKER_STATE" == absent ]] || return 0
  if ! docker_supported_os; then
    die "Docker is not installed and automatic installation covers Debian and Ubuntu only." \
      "Install Docker Engine and the Compose plugin ($DOCKER_DOCS) and run this script again"
  fi
  if [[ "$DRY_RUN" == 1 ]]; then
    info "  Would install: Docker Engine and the Compose plugin from Docker's apt repository,"
    info "  enable the service at boot and configure log rotation (10 MB x 3 files per container)."
    return 0
  fi
  info "Docker is not installed. It will be installed from Docker's official apt repository"
  info "(packages docker-ce, docker-ce-cli, containerd.io, docker-buildx-plugin, docker-compose-plugin)."
  confirm "Install Docker now?" || die "stopped: Docker is required"
  docker_install
}

logrot_describe_plan() {
  [[ "$LOGROT_STATE" == none ]] || return 0
  if [[ "$DOCKER_FRESH" == 1 ]]; then
    info "  Log rotation: will be written to $DAEMON_JSON; Docker restarts (freshly installed, nothing runs yet)"
  elif [[ "$ENABLE_LOG_ROTATION" == 1 ]]; then
    info "  Log rotation: will be written to $DAEMON_JSON and DOCKER WILL BE RESTARTED:"
    info "    every container on this server is interrupted for a moment (--enable-log-rotation)"
  else
    info "  Log rotation of the daemon: SKIPPED. Enabling it restarts Docker and interrupts every"
    info "    container on this server; run again with --enable-log-rotation to do it on purpose."
    info "    The containers of this application limit their own logs in the compose files."
  fi
}

# Writes the daemon-wide log rotation. Only when there is no daemon
# configuration yet, and only on a fresh installation or on explicit request.
logrot_apply() {
  [[ "$LOGROT_STATE" == none ]] || return 0
  [[ "$DOCKER_FRESH" == 1 || "$ENABLE_LOG_ROTATION" == 1 ]] || return 0
  if [[ "$DOCKER_FRESH" != 1 && "$ASSUME_YES" != 1 ]]; then
    confirm "Restart Docker now? Every container on this server stops for a moment." || {
      info "log rotation skipped"
      return 0
    }
  fi
  have systemctl || {
    warn "systemctl not found; log rotation not configured"
    return 0
  }
  as_root install -m 0755 -d "$(dirname "$DAEMON_JSON")"
  printf '{\n  "log-driver": "json-file",\n  "log-opts": {\n    "max-size": "10m",\n    "max-file": "3"\n  }\n}\n' |
    as_root tee "$DAEMON_JSON" >/dev/null
  as_root systemctl restart docker
  LOGROT_STATE=configured
  info "log rotation configured (applies to containers created from now on)"
}
