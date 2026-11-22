# shellcheck shell=bash
# Steps 3 and 4: the domain and the language-model interface.
# Values come from parameters, else from the existing .env, else from questions.
# Nothing here prints a value of .env; the key is read without echo.
# Uses helpers from lib.sh and envfile.sh.

DNS_STATE=""   # match | mismatch | unresolved | unchecked

domain_settings() {
  local domain=""
  if [[ -n "$OPT_DOMAIN" ]]; then
    domain=${OPT_DOMAIN,,}
    valid_domain "$domain" || die "--domain is not a valid host name (expected e.g. hydromiara.example.org)"
  elif env_has DOMAIN; then
    return 0
  elif interactive; then
    while true; do
      ask domain "Domain of the application (e.g. hydromiara.example.org)"
      domain=${domain,,}
      valid_domain "$domain" && break
      info "Not a valid host name: no scheme, no path, at least one dot."
    done
  elif [[ "$DRY_RUN" == 1 ]]; then
    info "  Note: the domain is not set; it will be asked for (or pass --domain)"
    return 0
  else
    die "the domain is not set: pass --domain or put DOMAIN into .env"
  fi
  env_plan DOMAIN "$domain"
}

# Addresses configured on this machine (global scope), one per line.
local_addresses() {
  if have ip; then
    ip -o addr show scope global 2>/dev/null | awk '{ sub(/\/.*/, "", $4); print $4 }'
  elif have hostname; then
    hostname -I 2>/dev/null | tr ' ' '\n'
  fi
}

# Compares what the domain resolves to with the addresses of this machine.
# Uses the system resolver only; no data is sent to any other service.
dns_detect() {
  local domain resolved address
  domain=$(env_value DOMAIN)
  DNS_STATE=unchecked
  [[ -n "$domain" && "$OPT_SKIP_DNS" != 1 ]] || return 0
  have getent || return 0
  resolved=$(getent ahosts "$domain" 2>/dev/null | awk '{ print $1 }' | sort -u || true)
  if [[ -z "$resolved" ]]; then
    DNS_STATE=unresolved
    return 0
  fi
  DNS_STATE=mismatch
  while IFS= read -r address; do
    if [[ -n "$address" ]] && grep -qxF "$address" <<<"$resolved"; then DNS_STATE=match; fi
  done < <(local_addresses)
  return 0
}

dns_describe() {
  case "$DNS_STATE" in
    match) info "  DNS: the domain resolves to an address of this server" ;;
    unresolved) info "  DNS: THE DOMAIN DOES NOT RESOLVE; without the record no certificate can be issued" ;;
    mismatch)
      info "  DNS: the domain resolves to an address that is not configured on this server."
      info "    That is normal behind NAT or a floating address; otherwise correct the DNS record first."
      ;;
    *) info "  DNS: not checked" ;;
  esac
}

# Stops or asks when DNS could not be confirmed (never in --dry-run).
dns_gate() {
  [[ "$DNS_STATE" == mismatch || "$DNS_STATE" == unresolved ]] || return 0
  if [[ "$ASSUME_YES" == 1 ]]; then
    die "DNS could not be confirmed for the domain; fix the record or pass --skip-dns-check"
  fi
  confirm "DNS could not be confirmed for the domain. Continue anyway?" || die "stopped by the operator"
}

# Reads the key from a file (first line) without printing it.
read_key_file() {
  local key=""
  [[ -r "$1" ]] || die "the key file cannot be read"
  IFS= read -r key <"$1" || true
  [[ -n "$key" ]] || die "the key file is empty"
  printf '%s' "$key"
}

ai_settings() {
  local base="" model="" key=""
  if [[ "$OPT_NO_AI" == 1 ]]; then
    env_plan AI_API_KEY ""
    env_plan OPENAI_MODEL ""
    return 0
  fi
  if [[ -n "$OPT_AI_KEY_FILE" ]]; then key=$(read_key_file "$OPT_AI_KEY_FILE"); fi
  [[ -n "$key" ]] || key=$OPT_AI_KEY
  if [[ -n "$OPT_AI_BASE_URL$OPT_AI_MODEL$key" ]]; then
    base=$OPT_AI_BASE_URL
    model=$OPT_AI_MODEL
  elif env_has AI_API_KEY && env_has OPENAI_MODEL; then
    return 0
  elif interactive; then
    info "The Report summary can be worded by a language model (an interface compatible with"
    info "OpenAI Chat Completions). Without it every Report uses the built-in template."
    confirm "Configure the language-model interface now?" || return 0
    ask base "Base address of the service (empty = default of the application)"
    ask model "Model name as the service knows it"
    ask_secret key "Key of the service (not shown)"
    [[ -n "$model" && -n "$key" ]] || die "both the model name and the key are required (or answer no)"
  else
    return 0
  fi
  if [[ -n "$base" ]]; then
    valid_base_url "$base" || die "the base address must start with https:// (http only for this machine)"
    env_plan AI_BASE_URL "$base"
  fi
  [[ -z "$model" ]] || env_plan OPENAI_MODEL "$model"
  [[ -z "$key" ]] || env_plan AI_API_KEY "$key"
}

ai_describe() {
  if [[ -n "$(env_value AI_API_KEY)" && -n "$(env_value OPENAI_MODEL)" ]]; then
    info "  Report summary: language model configured (values are not shown)"
  else
    info "  Report summary: built-in template (no language model configured)"
  fi
}

# FORWARDED_ALLOW_IPS: the addresses the application trusts for the client
# address header. Set to the subnet of the network "proxy" unless .env has it.
forwarded_settings() {
  local subnets
  env_has FORWARDED_ALLOW_IPS && return 0
  subnets=$(proxy_subnets)
  if [[ -n "$subnets" ]]; then
    env_plan_default FORWARDED_ALLOW_IPS "$subnets"
  elif [[ "$DRY_RUN" == 1 ]]; then
    info "  Note: FORWARDED_ALLOW_IPS will be set to the subnet of the network once it exists"
  fi
}
