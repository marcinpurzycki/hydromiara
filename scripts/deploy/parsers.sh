# shellcheck shell=bash
# Pure text functions over the output of "docker inspect": no Docker calls, no
# output besides the result. Only names are extracted; values such as account
# addresses or credentials that may stand in the same output are never printed.

# The application's own names; a clash with them on the server stops the run.
APP_PROJECT=hydromiara
APP_ROUTERS='hydromiara-api|hydromiara-web'

# traefik_parse_args: reads the arguments of a Traefik container, one per line.
# Prints "entrypoint NAME" for the entry point listening on port 443 and
# "resolver NAME" for every ACME certificate resolver.
traefik_parse_args() {
  local arg name address seen=" "
  shopt -s nocasematch
  while IFS= read -r arg || [[ -n "$arg" ]]; do
    if [[ "$arg" =~ ^--entrypoints\.([^.=]+)\.address=(.*)$ ]]; then
      name=${BASH_REMATCH[1]}
      address=${BASH_REMATCH[2]%/tcp}
      if [[ "$address" == *:443 && "$seen" != *" e:$name "* ]]; then
        printf 'entrypoint %s\n' "$name"
        seen+="e:$name "
      fi
    elif [[ "$arg" =~ ^--certificatesresolvers\.([^.=]+)\.acme\. ]]; then
      name=${BASH_REMATCH[1]}
      if [[ "$seen" != *" r:$name "* ]]; then
        printf 'resolver %s\n' "$name"
        seen+="r:$name "
      fi
    fi
  done
  shopt -u nocasematch
}

# traefik_parse_labels: reads "CONTAINER<TAB>LABEL=VALUE" lines and prints the
# entry point and the resolver of the first router that names both. Used when
# the Traefik arguments do not tell (configuration kept in a file).
traefik_parse_labels() {
  local container label key value router
  local -A entry=() resolver=()
  local order=()
  while IFS=$'\t' read -r container label || [[ -n "$container" ]]; do
    key=${label%%=*}
    value=${label#*=}
    if [[ "$key" =~ ^traefik\.http\.routers\.([^.]+)\.entrypoints$ ]]; then
      router="$container/${BASH_REMATCH[1]}"
      entry[$router]=${value%%,*}
      order+=("$router")
    elif [[ "$key" =~ ^traefik\.http\.routers\.([^.]+)\.tls\.certresolver$ ]]; then
      router="$container/${BASH_REMATCH[1]}"
      resolver[$router]=$value
      order+=("$router")
    fi
  done
  for router in "${order[@]}"; do
    if [[ -n "${entry[$router]:-}" && -n "${resolver[$router]:-}" ]]; then
      printf 'entrypoint %s\nresolver %s\n' "${entry[$router]}" "${resolver[$router]}"
      return 0
    fi
  done
}

# label_collisions DOMAIN WORKDIR: reads "CONTAINER<TAB>LABEL=VALUE" lines of all
# containers and prints one line per clash with this deployment. A container
# belongs to this deployment when its compose project is the application's and
# its working directory is WORKDIR.
label_collisions() {
  local domain=$1 workdir=$2 container label key value
  local -A project=() directory=() reported=()
  local lines=()
  while IFS=$'\t' read -r container label || [[ -n "$container" ]]; do
    [[ -n "$container" ]] || continue
    key=${label%%=*}
    value=${label#*=}
    case "$key" in
      com.docker.compose.project) project[$container]=$value ;;
      com.docker.compose.project.working_dir) directory[$container]=$value ;;
    esac
    lines+=("$container"$'\t'"$label")
  done
  for label in "${lines[@]}"; do
    container=${label%%$'\t'*}
    label=${label#*$'\t'}
    key=${label%%=*}
    value=${label#*=}
    if [[ "${project[$container]:-}" == "$APP_PROJECT" && "${directory[$container]:-}" == "$workdir" ]]; then
      continue
    fi
    if [[ "${project[$container]:-}" == "$APP_PROJECT" && ! -v "reported[p:$container]" ]]; then
      reported[p:$container]=1
      printf 'container %s uses the compose project name "%s" from another directory\n' \
        "${container#/}" "$APP_PROJECT"
    fi
    if [[ "$key" =~ ^traefik\.http\.(routers|services)\.($APP_ROUTERS)\. ]]; then
      if [[ ! -v "reported[n:$container:${BASH_REMATCH[2]}]" ]]; then
        reported[n:$container:${BASH_REMATCH[2]}]=1
        printf 'container %s already uses the Traefik router or service name "%s"\n' \
          "${container#/}" "${BASH_REMATCH[2]}"
      fi
    fi
    if [[ -n "$domain" && "$key" =~ ^traefik\.http\.routers\.[^.]+\.rule$ && "$value" == *"\`$domain\`"* ]]; then
      if [[ ! -v "reported[d:$container]" ]]; then
        reported[d:$container]=1
        printf 'container %s already serves the chosen domain\n' "${container#/}"
      fi
    fi
  done
}
