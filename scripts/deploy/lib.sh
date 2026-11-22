# shellcheck shell=bash
# Shared helpers of the deployment script: messages, questions, privileges.
# Sourced by scripts/deploy.sh; not meant to be run on its own.

info() { printf '%s\n' "$*"; }
step() { printf '\n== %s ==\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

have() { command -v "$1" >/dev/null 2>&1; }

# True when questions may be asked: not --yes, not --dry-run, and a terminal.
interactive() { [[ "${ASSUME_YES:-0}" != 1 && "${DRY_RUN:-0}" != 1 && -t 0 ]]; }

# confirm QUESTION: yes/no question, default "no". In --yes mode the answer is
# yes; without a terminal (and without --yes) it is an error, never a guess.
confirm() {
  local answer
  if [[ "${ASSUME_YES:-0}" == 1 ]]; then return 0; fi
  [[ -t 0 ]] || die "cannot ask \"$1\" without a terminal; use --yes with parameters"
  read -r -p "$1 [y/N] " answer
  [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
}

# ask VARIABLE QUESTION [DEFAULT]: reads one line into VARIABLE.
ask() {
  local -n _target=$1
  local reply prompt="$2"
  [[ -n "${3:-}" ]] && prompt+=" [$3]"
  read -r -p "$prompt: " reply
  _target="${reply:-${3:-}}"
}

# ask_secret VARIABLE QUESTION: reads one line without echo.
ask_secret() {
  local -n _target=$1
  local reply
  read -r -s -p "$2: " reply
  printf '\n'
  _target="$reply"
}

# Runs a command as root: directly when root, through sudo otherwise.
as_root() {
  if [[ $EUID -eq 0 ]]; then
    "$@"
  elif have sudo; then
    sudo "$@"
  else
    die "root privileges are needed for: $* (run as root or install sudo)"
  fi
}

# The Docker client, through sudo when the user may not use the socket.
DOCKER=(docker)
dk() { "${DOCKER[@]}" "$@"; }

# Compose for the application project, always from the repository root.
app_compose() {
  dk compose --project-directory "$ROOT_DIR" -f "$ROOT_DIR/docker-compose.yml" \
    --env-file "$ENV_FILE" "$@"
}

# valid_domain NAME: a lower-case host name with at least two labels.
valid_domain() {
  local name=$1 label
  [[ ${#name} -le 253 && "$name" == *.* ]] || return 1
  [[ "$name" =~ ^[a-z0-9.-]+$ ]] || return 1
  local IFS=.
  for label in $name; do
    [[ -n "$label" && ${#label} -le 63 && "$label" != -* && "$label" != *- ]] || return 1
  done
  [[ "$name" != *. && "$name" != .* && "$name" != *..* ]] || return 1
  # The last label of a host name is not a number (that would be an address).
  [[ ! "${name##*.}" =~ ^[0-9]+$ ]]
}

# valid_email ADDRESS: loose shape check for the ACME account address.
valid_email() { [[ "$1" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:].]+$ ]]; }

# valid_base_url URL: https, or http for this machine only (as the service accepts).
valid_base_url() {
  [[ "$1" =~ ^https://[^/[:space:]]+(/[^[:space:]]*)?$ ]] && return 0
  [[ "$1" =~ ^http://(localhost|127\.0\.0\.1)(:[0-9]+)?(/[^[:space:]]*)?$ ]]
}
