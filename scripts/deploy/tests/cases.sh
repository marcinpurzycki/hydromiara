# shellcheck shell=bash
# Whole-script cases, sourced by run.sh (uses its helpers and stand-ins).

MUTATING='(^| )(up|down|create|rm|rmi|restart|run|exec|build|stop|start|pull|prune|kill|connect)( |$)'
SECRETS='secret-host|topsecretkey123|secret-model|ai\.example\.org'

check "--help" grep -q -- '--dry-run' <<<"$(bash "$REPO_DIR/scripts/deploy.sh" --help)"

# A server that already runs Traefik and already has a filled-in .env.
root=$(new_root existing)
touch "$root-state/proxy"
printf '%s\n' 'DOMAIN=secret-host.example.org' 'TRAEFIK_ENTRYPOINT=websecure' 'TRAEFIK_CERTRESOLVER=le' \
  'AI_API_KEY=topsecretkey123' 'OPENAI_MODEL=secret-model' 'AI_BASE_URL=https://ai.example.org/v1' >"$root/.env"
chmod 600 "$root/.env"
before=$(snapshot "$root")
first=$(deploy "$root" 1 --dry-run) || fail "dry run on an existing server exits with an error"
second=$(deploy "$root" 1 --dry-run) || true
equal "two dry runs print the same" "$first" "$second"
equal "a dry run changes no file" "$before" "$(snapshot "$root")"
check_not "a dry run makes no changing Docker call" grep -Eq "$MUTATING" "$root-state/calls"
check "the entry point is detected" grep -q 'HTTPS entry point: websecure' <<<"$first"
check "the resolver is detected" grep -q 'certificate resolver(s): le' <<<"$first"
check "Traefik is reported as untouched" grep -q 'it will not be changed' <<<"$first"
check "log rotation is reported as skipped" grep -q 'SKIPPED' <<<"$first"
check_not "a dry run prints no value of .env" grep -Eq "$SECRETS" <<<"$first"
check "the subnet setting is planned" grep -q 'set:     FORWARDED_ALLOW_IPS' <<<"$first"

out=$(deploy "$root" 1 --yes --skip-dns-check) || fail "run on an existing server exits with an error: $out"
check_not "the run prints no value of .env" grep -Eq "$SECRETS" <<<"$out"
equal "the subnet of the network is written" 172.30.0.0/16 "$(env_get FORWARDED_ALLOW_IPS "$root/.env")"
equal "the domain is kept" secret-host.example.org "$(env_get DOMAIN "$root/.env")"
equal "the key is kept" topsecretkey123 "$(env_get AI_API_KEY "$root/.env")"
equal "one backup after the first run" 1 "$(find "$root" -name '.env.backup-*' | wc -l)"
check "the application is started" grep -q 'docker-compose.yml --env-file .* up -d --build' "$root-state/calls"
check_not "no network is created" grep -q 'network create' "$root-state/calls"
check_not "no second Traefik is started" grep -q 'deploy/traefik' "$root-state/calls"
check_not "the daemon configuration is not written" test -e "$root-state/daemon.json"
check_not "nothing is removed" grep -Eq '(^| )(down|rm|rmi|prune|kill|stop)( |$)' "$root-state/calls"
before=$(snapshot "$root")
out=$(deploy "$root" 1 --yes --skip-dns-check) || fail "second run exits with an error: $out"
equal "a second run changes no file" "$before" "$(snapshot "$root")"
check "a second run reports no changes" grep -q '.env: no changes' <<<"$out"

before=$(snapshot "$root")
out=$(deploy "$root" 1 --yes) && fail "unconfirmed DNS must stop a run without questions"
check "the DNS stop names the option" grep -q -- '--skip-dns-check' <<<"$out"
equal "the DNS stop changes no file" "$before" "$(snapshot "$root")"

# Another project on the server already uses one of the application's router names.
printf '/blog-1\ttraefik.http.routers.hydromiara-web.entrypoints=websecure\n' >"$WORK/clash.tsv"
out=$(TEST_LABELS="$WORK/clash.tsv" deploy "$root" 1 --yes --skip-dns-check) && fail "a name clash must stop the run"
check "the clash is named" grep -q 'name clash: container blog-1' <<<"$out"
equal "the clash changes no file" "$before" "$(snapshot "$root")"

# A new server: Docker present, no Traefik, no network, no .env.
root=$(new_root fresh)
out=$(deploy "$root" 0 --yes --skip-dns-check --acme-email ops@example.org) && fail "a missing domain must stop a run without questions"
check "the missing domain is named" grep -q -- '--domain' <<<"$out"
out=$(deploy "$root" 0 --yes --skip-dns-check --domain hydromiara.example.org --no-ai) &&
  fail "a missing account address must stop a run without questions"
check "the missing account address is named" grep -q -- '--acme-email' <<<"$out"
check_not "a stopped run leaves no .env" test -e "$root/.env"
out=$(deploy "$root" 0 --dry-run --domain hydromiara.example.org --acme-email ops@example.org) ||
  fail "dry run on a new server exits with an error"
check "the own Traefik is planned" grep -q 'will start its own' <<<"$out"
check_not "a dry run on a new server leaves no .env" test -e "$root/.env"
check_not "a dry run on a new server creates nothing" grep -Eq "$MUTATING" "$root-state/calls"
out=$(TEST_KEY=k3y-from-env deploy "$root" 0 --yes --skip-dns-check --domain hydromiara.example.org \
  --acme-email ops@example.org --ai-model some-model) || fail "run on a new server exits with an error: $out"
check_not "the account address and the key are not printed" grep -Eq 'ops@example|k3y-from-env' <<<"$out"
check "the network is created" grep -qx 'network create proxy' "$root-state/calls"
check "the own Traefik is started" grep -q 'deploy/traefik/docker-compose.yml --env-file .* up -d' "$root-state/calls"
equal "mode of the new .env" 600 "$(stat -c %a "$root/.env")"
equal "entry point of the own Traefik" websecure "$(env_get TRAEFIK_ENTRYPOINT "$root/.env")"
equal "resolver of the own Traefik" le "$(env_get TRAEFIK_CERTRESOLVER "$root/.env")"
equal "account address stored" ops@example.org "$(env_get ACME_EMAIL "$root/.env")"
equal "key from the environment stored" k3y-from-env "$(env_get AI_API_KEY "$root/.env")"
equal "subnet stored after the network exists" 172.30.0.0/16 "$(env_get FORWARDED_ALLOW_IPS "$root/.env")"
check "the data directory is created" test -d "$root/data/edo"
check_not "no daemon configuration without a fresh Docker" test -e "$root-state/daemon.json"
out=$(deploy "$root" 0 --yes --skip-dns-check --no-ai) || fail "switching the model off exits with an error: $out"
equal "the key is cleared by --no-ai" "" "$(env_get AI_API_KEY "$root/.env")"
equal "the domain survives --no-ai" hydromiara.example.org "$(env_get DOMAIN "$root/.env")"
