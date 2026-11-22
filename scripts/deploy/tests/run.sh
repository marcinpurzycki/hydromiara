#!/usr/bin/env bash
# Tests of the deployment script. No network, no Docker, no root: the commands
# docker, curl, ss and getent are replaced by the stand-ins in stubs/.
# Run: scripts/deploy/tests/run.sh
set -euo pipefail

TESTS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=$(cd "$TESTS_DIR/../../.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
FAILED=0
PASSED=0

ok() { PASSED=$((PASSED + 1)); }
fail() {
  FAILED=$((FAILED + 1))
  printf 'FAIL: %s\n' "$*" >&2
}
check() { # check DESCRIPTION COMMAND...
  local description=$1
  shift
  if "$@" >/dev/null 2>&1; then ok; else fail "$description"; fi
}
check_not() {
  local description=$1
  shift
  if "$@" >/dev/null 2>&1; then fail "$description"; else ok; fi
}
equal() { # equal DESCRIPTION EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then ok; else fail "$1: expected [$2], got [$3]"; fi
}

# --- pure functions -----------------------------------------------------------
ROOT_DIR="$WORK/unit"
ENV_FILE="$ROOT_DIR/.env"
mkdir -p "$ROOT_DIR"
# shellcheck source=scripts/deploy/lib.sh
source "$REPO_DIR/scripts/deploy/lib.sh"
# shellcheck source=scripts/deploy/envfile.sh
source "$REPO_DIR/scripts/deploy/envfile.sh"
# shellcheck source=scripts/deploy/parsers.sh
source "$REPO_DIR/scripts/deploy/parsers.sh"

check "plain domain" valid_domain hydromiara.example.org
check "domain with hyphen" valid_domain a-b.example.org
check_not "single label" valid_domain localhost
check_not "scheme" valid_domain https://example.org
check_not "path" valid_domain example.org/path
check_not "upper case" valid_domain Example.org
check_not "leading hyphen" valid_domain -a.example.org
check_not "double dot" valid_domain a..example.org
check_not "address" valid_domain 192.0.2.10
check_not "space" valid_domain "a b.example.org"
check "e-mail" valid_email ops@example.org
check_not "e-mail without domain" valid_email ops@
check "https base address" valid_base_url https://ai.example.org/v1
check "http on this machine" valid_base_url http://localhost:8080/v1
check_not "http elsewhere" valid_base_url http://ai.example.org/v1

printf '%s\n' '# comment' 'PLAIN=one' 'QUOTED="two words"' "SINGLE='three # not a comment'" \
  'COMMENTED=four # trailing' 'export EXPORTED=five' 'EMPTY=' 'TWICE=first' 'TWICE=second' \
  '  SPACED = six' >"$ENV_FILE"
equal "plain value" one "$(env_get PLAIN)"
equal "double quotes" "two words" "$(env_get QUOTED)"
equal "single quotes" "three # not a comment" "$(env_get SINGLE)"
equal "trailing comment" four "$(env_get COMMENTED)"
equal "export prefix" five "$(env_get EXPORTED)"
equal "empty value" "" "$(env_get EMPTY)"
equal "absent value" "" "$(env_get ABSENT)"
equal "last assignment wins" second "$(env_get TWICE)"
equal "spaces around the name" six "$(env_get SPACED)"
check_not "empty is not set" env_has EMPTY
check_not "a name that is a prefix of another" env_has PLAI

rm "$ENV_FILE"
printf 'DOMAIN=\nAI_API_KEY=\nKEEP=as-is\n' >"$ROOT_DIR/.env.example"
env_plan DOMAIN hydromiara.example.org
env_apply >/dev/null
equal "file created from the example" as-is "$(env_get KEEP)"
equal "value written" hydromiara.example.org "$(env_get DOMAIN)"
equal "mode of a new file" 600 "$(stat -c %a "$ENV_FILE")"
equal "no backup of a new file" 0 "$(find "$ROOT_DIR" -name '.env.backup-*' | wc -l)"
env_plan DOMAIN hydromiara.example.org
env_plan_default DOMAIN other.example.org
env_plan AI_API_KEY ""
equal "same values plan nothing" 0 "${#ENV_PENDING[@]}"
before=$(cat "$ENV_FILE")
chmod 644 "$ENV_FILE"
env_apply >/dev/null
equal "no change leaves the content" "$before" "$(cat "$ENV_FILE")"
equal "mode tightened" 600 "$(stat -c %a "$ENV_FILE")"
equal "no backup without a change" 0 "$(find "$ROOT_DIR" -name '.env.backup-*' | wc -l)"
env_plan AI_API_KEY 'p4$$ word#1'
env_plan NEW_NAME value
plan_text=$(env_describe_plan)
check_not "the plan does not show values" grep -q 'p4' <<<"$plan_text"
apply_text=$(env_apply)
check_not "the result does not show values" grep -q 'p4' <<<"$apply_text"
equal "special characters survive" 'p4$$ word#1' "$(env_get AI_API_KEY)"
equal "appended name" value "$(env_get NEW_NAME)"
equal "other values kept" as-is "$(env_get KEEP)"
backup=$(find "$ROOT_DIR" -name '.env.backup-*')
equal "one backup" 1 "$(wc -l <<<"$backup")"
equal "mode of the backup" 600 "$(stat -c %a "$backup")"
equal "the backup holds the old content" "$before" "$(cat "$backup")"
check_not "a quote in a value is refused" bash -c "source '$REPO_DIR/scripts/deploy/lib.sh'; source '$REPO_DIR/scripts/deploy/envfile.sh'; ENV_FILE=/nonexistent; env_plan X \"a'b\""

parsed=$(traefik_parse_args <"$TESTS_DIR/fixtures/traefik_args.txt")
equal "names from the Traefik arguments" $'entrypoint websecure\nresolver le' "$parsed"
check_not "the account address is not in the result" grep -q '@' <<<"$parsed"
equal "mixed case and protocol suffix" "entrypoint https" \
  "$(printf '%s\n' '--entryPoints.http.address=:80' '--entryPoints.https.address=0.0.0.0:443/tcp' | traefik_parse_args)"
equal "names from router labels" $'entrypoint websecure\nresolver le' \
  "$(traefik_parse_labels <"$TESTS_DIR/fixtures/labels.tsv")"
equal "no clash with unrelated containers" "" \
  "$(label_collisions hydromiara.example.org /srv/app <"$TESTS_DIR/fixtures/labels.tsv")"
check "clash of the domain" grep -q 'already serves the chosen domain' \
  <<<"$(label_collisions shop.example.org /srv/app <"$TESTS_DIR/fixtures/labels.tsv")"
# shellcheck disable=SC2016  # backticks are part of the Traefik rule
own=$(printf '%s\t%s\n' /hydromiara-api-1 com.docker.compose.project=hydromiara \
  /hydromiara-api-1 com.docker.compose.project.working_dir=/srv/app \
  /hydromiara-api-1 'traefik.http.routers.hydromiara-api.rule=Host(`hydromiara.example.org`)')
equal "own containers are not a clash" "" "$(label_collisions hydromiara.example.org /srv/app <<<"$own")"
check "same project from another directory" grep -q 'from another directory' \
  <<<"$(label_collisions hydromiara.example.org /srv/elsewhere <<<"$own")"
check "router name taken by another project" grep -q 'router or service name "hydromiara-api"' \
  <<<"$(printf '/x\ttraefik.http.routers.hydromiara-api.entrypoints=web\n' | label_collisions "" /srv/app)"

# --- whole script against the stand-ins ---------------------------------------
new_root() { # new_root NAME: a copy of the deployable files in a fresh directory
  local root="$WORK/$1"
  mkdir -p "$root" "$WORK/$1-state"
  cp -r "$REPO_DIR/scripts" "$REPO_DIR/deploy" "$REPO_DIR/docker-compose.yml" "$REPO_DIR/.env.example" "$root/"
  printf '%s' "$root"
}
deploy() { # deploy ROOT TRAEFIK(0|1) ARGS...
  local root=$1 traefik=$2
  shift 2
  printf 'ID=debian\nVERSION_CODENAME=trixie\nPRETTY_NAME="Debian GNU/Linux 13"\n' >"$root-state/os-release"
  env AI_API_KEY="${TEST_KEY:-}" STUB_LABELS="${TEST_LABELS:-}" PATH="$TESTS_DIR/stubs:$PATH" STUB_LOG="$root-state/calls" STUB_STATE="$root-state" \
    STUB_TRAEFIK="$traefik" DEPLOY_OS_RELEASE="$root-state/os-release" \
    DEPLOY_DAEMON_JSON="$root-state/daemon.json" bash "$root/scripts/deploy.sh" "$@" </dev/null 2>&1
}
snapshot() { (cd "$1" && find . -type f -exec sha256sum {} + | sort -k2); }
# shellcheck source=scripts/deploy/tests/cases.sh
source "$TESTS_DIR/cases.sh"

printf '%d passed, %d failed\n' "$PASSED" "$FAILED"
[[ $FAILED -eq 0 ]]
