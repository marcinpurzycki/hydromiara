# shellcheck shell=bash
# Step 2: Traefik and the network "proxy".
# A running Traefik is never changed: the script reads the names of its HTTPS
# entry point and certificate resolver and proposes them. Only when no Traefik
# runs and ports 80/443 are free does it start its own from deploy/traefik/.
# Uses helpers from lib.sh, envfile.sh and parsers.sh.

PROXY_NETWORK=proxy
OWN_ENTRYPOINT=websecure   # names fixed in deploy/traefik/docker-compose.yml
OWN_RESOLVER=le

TRAEFIK_STATE=unknown      # existing | absent | unknown (Docker not installed yet)
TRAEFIK_NAME=""
TRAEFIK_IMAGE=""
PROXY_EXISTS=0
DETECTED_ENTRYPOINT=""
DETECTED_RESOLVERS=""
LABEL_DUMP=""
PROBLEMS=()

problem() { PROBLEMS+=("$*"); }

traefik_compose() {
  dk compose --project-directory "$ROOT_DIR/deploy/traefik" \
    -f "$ROOT_DIR/deploy/traefik/docker-compose.yml" --env-file "$ENV_FILE" "$@"
}

# Labels of all containers, reduced at once to the Traefik router/service names
# and the compose project labels: "CONTAINER<TAB>LABEL=VALUE".
label_dump() {
  local ids format
  mapfile -t ids < <(dk ps -aq)
  [[ ${#ids[@]} -gt 0 ]] || return 0
  # shellcheck disable=SC2016  # a Go template, not shell variables
  format='{{$n := .Name}}{{range $k, $v := .Config.Labels}}{{$n}}{{"\t"}}{{$k}}={{$v}}{{"\n"}}{{end}}'
  dk inspect --format "$format" "${ids[@]}" 2>/dev/null |
    grep -E $'\t(traefik\\.http\\.(routers|services)\\.|com\\.docker\\.compose\\.project)' || true
}

# port_busy PORT: true when something listens on the TCP port.
port_busy() {
  if have ss; then
    [[ -n "$(ss -Hltn "sport = :$1" 2>/dev/null)" ]]
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
  fi
}

# Subnets of the network "proxy", comma separated (empty when it does not exist).
proxy_subnets() {
  dk network inspect "$PROXY_NETWORK" \
    --format '{{range .IPAM.Config}}{{println .Subnet}}{{end}}' 2>/dev/null |
    grep -v '^$' | paste -sd, - || true
}

traefik_detect() {
  local id image name count=0 parsed networks port
  if dk network inspect "$PROXY_NETWORK" >/dev/null 2>&1; then PROXY_EXISTS=1; fi
  LABEL_DUMP=$(label_dump)
  while read -r id image name; do
    [[ "$image" =~ (^|/)traefik([:@]|$) ]] || continue
    count=$((count + 1))
    [[ $count -eq 1 ]] || continue
    TRAEFIK_NAME=$name
    TRAEFIK_IMAGE=$image
    parsed=$(dk inspect --format '{{range .Args}}{{println .}}{{end}}' "$id" | traefik_parse_args)
    # shellcheck disable=SC2016  # a Go template, not shell variables
    networks=$(dk inspect --format '{{range $k, $v := .NetworkSettings.Networks}}{{println $k}}{{end}}' "$id")
  done < <(dk ps --format '{{.ID}} {{.Image}} {{.Names}}')

  if [[ $count -eq 0 ]]; then
    TRAEFIK_STATE=absent
    for port in 80 443; do
      if port_busy "$port"; then
        problem "port $port is in use by something that is not a Traefik container." \
          "Free it or put Traefik in front of it yourself; this script will not touch it."
      fi
    done
    return 0
  fi
  TRAEFIK_STATE=existing
  [[ $count -eq 1 ]] || warn "$count Traefik containers are running; reading the first one ($TRAEFIK_NAME)"
  if [[ -z "$parsed" ]]; then parsed=$(traefik_parse_labels <<<"$LABEL_DUMP"); fi
  DETECTED_ENTRYPOINT=$(awk '$1 == "entrypoint" { print $2; exit }' <<<"$parsed")
  DETECTED_RESOLVERS=$(awk '$1 == "resolver" { print $2 }' <<<"$parsed" | paste -sd' ' -)
  if [[ $PROXY_EXISTS -eq 0 ]]; then
    problem "Traefik ($TRAEFIK_NAME) is running but the Docker network \"$PROXY_NETWORK\" does not exist." \
      "The application joins that network. Create it and connect Traefik yourself:" \
      "docker network create $PROXY_NETWORK && docker network connect $PROXY_NETWORK $TRAEFIK_NAME"
  elif ! grep -qx "$PROXY_NETWORK" <<<"$networks"; then
    problem "Traefik ($TRAEFIK_NAME) is not attached to the network \"$PROXY_NETWORK\"." \
      "Connect it yourself: docker network connect $PROXY_NETWORK $TRAEFIK_NAME"
  fi
}

# Clashes of names with containers that do not belong to this deployment.
collisions_detect() {
  local line
  while IFS= read -r line; do
    [[ -n "$line" ]] && problem "name clash: $line"
  done < <(label_collisions "$(env_value DOMAIN)" "$ROOT_DIR" <<<"$LABEL_DUMP")
  return 0
}

traefik_describe() {
  case "$TRAEFIK_STATE" in
    existing)
      info "  Traefik: running (container $TRAEFIK_NAME, image $TRAEFIK_IMAGE); it will not be changed"
      info "    HTTPS entry point: ${DETECTED_ENTRYPOINT:-not detected}"
      info "    certificate resolver(s): ${DETECTED_RESOLVERS:-not detected}"
      ;;
    absent) info "  Traefik: no running Traefik container found" ;;
    *) info "  Traefik: unknown until Docker is installed (a new server: this script starts its own)" ;;
  esac
  if [[ $PROXY_EXISTS -eq 1 ]]; then
    info "  Network \"$PROXY_NETWORK\": exists; it will not be changed"
  else
    info "  Network \"$PROXY_NETWORK\": does not exist"
  fi
}

# name_setting KEY PARAMETER DETECTED LABEL: decides one of the two Traefik
# names: parameter, else the value already in .env, else the detected name.
name_setting() {
  local key=$1 given=$2 detected=$3 label=$4 answer=""
  if [[ -n "$given" ]]; then
    env_plan "$key" "$given"
  elif env_has "$key"; then
    if [[ -n "$detected" && " $detected " != *" $(env_get "$key") "* ]]; then
      warn "$key in .env differs from the name read from Traefik ($detected); the .env value is kept"
    fi
  elif interactive; then
    ask answer "Name of the Traefik $label" "${detected%% *}"
    [[ -n "$answer" ]] || die "the name of the Traefik $label is required"
    env_plan "$key" "$answer"
  elif [[ -n "$detected" ]]; then
    env_plan "$key" "${detected%% *}"
  elif [[ "$DRY_RUN" == 1 ]]; then
    info "  Note: the Traefik $label could not be detected; it will be asked for (or pass a parameter)"
  else
    die "the Traefik $label could not be detected; pass it as a parameter (see --help)"
  fi
}

# Collects TRAEFIK_ENTRYPOINT, TRAEFIK_CERTRESOLVER and, for the own Traefik, ACME_EMAIL.
traefik_settings() {
  local email=""
  if [[ "$TRAEFIK_STATE" == existing ]]; then
    name_setting TRAEFIK_ENTRYPOINT "$OPT_ENTRYPOINT" "$DETECTED_ENTRYPOINT" "HTTPS entry point"
    name_setting TRAEFIK_CERTRESOLVER "$OPT_CERTRESOLVER" "$DETECTED_RESOLVERS" "certificate resolver"
    return 0
  fi
  env_plan TRAEFIK_ENTRYPOINT "$OWN_ENTRYPOINT"
  env_plan TRAEFIK_CERTRESOLVER "$OWN_RESOLVER"
  if [[ -n "$OPT_ACME_EMAIL" ]]; then
    email=$OPT_ACME_EMAIL
  elif env_has ACME_EMAIL; then
    return 0
  elif interactive; then
    ask email "E-mail address for the Let's Encrypt account (stored only in .env)"
  elif [[ "$DRY_RUN" == 1 ]]; then
    info "  Note: the e-mail address for Let's Encrypt will be asked for (or pass --acme-email)"
    return 0
  else
    die "the own Traefik needs an e-mail address for Let's Encrypt: pass --acme-email"
  fi
  valid_email "$email" || die "this does not look like an e-mail address"
  env_plan ACME_EMAIL "$email"
}

traefik_describe_plan() {
  if [[ "$TRAEFIK_STATE" == existing ]]; then return 0; fi
  [[ $PROXY_EXISTS -eq 1 ]] || info "  Network: will create the Docker network \"$PROXY_NETWORK\""
  info "  Traefik: will start its own (project hydromiara-traefik, image traefik:v3, ports 80 and 443,"
  info "    redirect to HTTPS, Let's Encrypt, Docker provider without default exposure, no dashboard)"
}

# Creates the network when missing; never touches an existing one.
network_apply() {
  [[ $PROXY_EXISTS -eq 1 ]] && return 0
  [[ "$TRAEFIK_STATE" == existing ]] && return 0
  dk network create "$PROXY_NETWORK" >/dev/null
  PROXY_EXISTS=1
  info "created the Docker network \"$PROXY_NETWORK\""
}

# Starts the own Traefik; does nothing when a Traefik was found running.
traefik_apply() {
  [[ "$TRAEFIK_STATE" == existing ]] && return 0
  info "starting Traefik from deploy/traefik/docker-compose.yml"
  traefik_compose up -d
}
