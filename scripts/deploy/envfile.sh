# shellcheck shell=bash
# Reading and changing the .env file. Values are never printed: messages name
# the variables only. Every change is preceded by a backup with mode 600.
# Uses: ENV_FILE, ROOT_DIR, helpers from lib.sh.

# Changes collected during the run and written at once by env_apply.
declare -A ENV_PENDING=()
ENV_ORDER=()

# env_get KEY [FILE]: prints the value of KEY (empty when absent). The last
# assignment wins; surrounding quotes and an unquoted trailing comment are removed.
env_get() {
  local key=$1 file=${2:-$ENV_FILE} line value="" pattern
  [[ -f "$file" ]] || return 0
  pattern="^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=(.*)\$"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ $pattern ]]; then value=${BASH_REMATCH[2]}; fi
  done <"$file"
  value="${value#"${value%%[![:space:]]*}"}"
  if [[ "$value" =~ ^\'(.*)\'[[:space:]]*$ || "$value" =~ ^\"(.*)\"[[:space:]]*$ ]]; then
    value=${BASH_REMATCH[1]}
  else
    value="${value%%[[:space:]]#*}"
    value="${value%"${value##*[![:space:]]}"}"
  fi
  printf '%s' "$value"
}

# env_has KEY: true when KEY has a non-empty value in the file.
env_has() { [[ -n "$(env_get "$1")" ]]; }

# env_value KEY: the value the file will hold after env_apply.
env_value() {
  if [[ -v "ENV_PENDING[$1]" ]]; then
    printf '%s' "${ENV_PENDING[$1]}"
  else
    env_get "$1"
  fi
}

# env_plan KEY VALUE: registers a change; nothing when the file already holds VALUE.
env_plan() {
  local key=$1 value=$2
  [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || die "invalid variable name: $key"
  if [[ "$value" == *"'"* || "$value" == *$'\n'* ]]; then
    die "the value given for $key contains a quote or a line break; not supported"
  fi
  if [[ -f "$ENV_FILE" && "$(env_get "$key")" == "$value" ]]; then
    unset "ENV_PENDING[$key]"
    return 0
  fi
  # An absent variable and an empty one mean the same; do not add empty lines.
  if [[ -z "$value" && -z "$(env_get "$key")" ]]; then return 0; fi
  [[ -v "ENV_PENDING[$key]" ]] || ENV_ORDER+=("$key")
  ENV_PENDING[$key]=$value
}

# env_plan_default KEY VALUE: like env_plan, but an existing value is kept.
env_plan_default() {
  if ! env_has "$1" && [[ ! -v "ENV_PENDING[$1]" ]]; then env_plan "$1" "$2"; fi
}

# Prints the planned changes as variable names only.
env_describe_plan() {
  local key
  if [[ ! -f "$ENV_FILE" ]]; then
    info "  .env: will be created from .env.example with mode 600"
  elif [[ ${#ENV_PENDING[@]} -eq 0 ]]; then
    info "  .env: no changes (existing values are kept)"
  else
    info "  .env: backup first (mode 600), then the changes below; other values are kept"
  fi
  for key in "${ENV_ORDER[@]}"; do
    [[ -v "ENV_PENDING[$key]" ]] || continue
    if env_has "$key"; then
      info "    replace: $key"
    else
      info "    set:     $key"
    fi
  done
}

env_quote() {
  if [[ "$1" =~ ^[A-Za-z0-9_./:@,+=-]*$ ]]; then
    printf '%s' "$1"
  else
    printf "'%s'" "$1"
  fi
}

# Writes the collected changes. Without changes an existing file is left alone,
# except that its mode is tightened to 600.
env_apply() {
  local line key tmp backup pattern
  local -A written=()
  if [[ ! -f "$ENV_FILE" ]]; then
    [[ -f "$ROOT_DIR/.env.example" ]] || die ".env.example is missing in $ROOT_DIR"
    (umask 077 && cp "$ROOT_DIR/.env.example" "$ENV_FILE")
    chmod 600 "$ENV_FILE"
    info "created .env from .env.example (mode 600)"
  elif [[ ${#ENV_PENDING[@]} -gt 0 ]]; then
    backup="$ENV_FILE.backup-$(date +%Y%m%d-%H%M%S)"
    (umask 077 && cp "$ENV_FILE" "$backup")
    chmod 600 "$backup"
    info "backup of .env written: ${backup##*/} (mode 600)"
  fi
  if [[ ${#ENV_PENDING[@]} -gt 0 ]]; then
    tmp=$(umask 077 && mktemp "$ENV_FILE.tmp.XXXXXX")
    while IFS= read -r line || [[ -n "$line" ]]; do
      key=""
      pattern='^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*='
      if [[ "$line" =~ $pattern ]]; then key=${BASH_REMATCH[2]}; fi
      if [[ -n "$key" && -v "ENV_PENDING[$key]" ]]; then
        # The first assignment is replaced, repeated ones are dropped.
        if [[ ! -v "written[$key]" ]]; then
          printf '%s=%s\n' "$key" "$(env_quote "${ENV_PENDING[$key]}")"
          written[$key]=1
        fi
      else
        printf '%s\n' "$line"
      fi
    done <"$ENV_FILE" >"$tmp"
    for key in "${ENV_ORDER[@]}"; do
      [[ -v "ENV_PENDING[$key]" && ! -v "written[$key]" ]] || continue
      printf '%s=%s\n' "$key" "$(env_quote "${ENV_PENDING[$key]}")" >>"$tmp"
    done
    mv "$tmp" "$ENV_FILE"
    info "updated .env: ${ENV_ORDER[*]}"
    ENV_PENDING=()
    ENV_ORDER=()
  fi
  if [[ "$(stat -c %a "$ENV_FILE")" != 600 ]]; then
    chmod 600 "$ENV_FILE"
    info "mode of .env set to 600"
  fi
}
