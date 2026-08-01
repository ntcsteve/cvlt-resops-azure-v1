#!/usr/bin/env bash
# Prove the observability stack WORKS, without spending a cent on Azure.
#
# Nothing in the stack is Azure-specific — it is three containers and four config
# files. Azure only supplies a VM to run Docker on. So the part that can actually
# break is testable on a laptop, in about a minute, repeatably and free.
#
# It runs THE REAL FILES from ./stack/ — the same ones cloud-init embeds. A test
# against a copy would prove nothing about what deploys.
#
#   ./test-stack.sh          run it
#   KEEP=1 ./test-stack.sh   leave it up afterwards to poke at
#
# Six checks, in the order things break:
#   1  containers reach healthy
#   2  pushgateway accepts a real `resops metrics` payload
#   3  prometheus has the series
#   4  grafana's datasource is healthy
#   5  grafana LOADED the dashboard (provisioning errors are silent otherwise)
#   6  EVERY panel query returns data  ◀ the one that catches an empty panel
#      before a room sees one
set -uo pipefail
cd "$(dirname "$0")"

REPO=$(cd ../.. && pwd)
GRAFANA=http://localhost:3000
PROM=http://localhost:9090
PUSH=http://localhost:9091
export GRAFANA_PASSWORD=test-only-not-a-secret
PASS=0 FAIL=0

ok()   { printf '  \033[32mPASS\033[0m  %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; FAIL=$((FAIL+1)); }
step() { printf '\n\033[1m%s\033[0m\n' "$*"; }

cleanup() {
  if [ "${KEEP:-0}" = "1" ]; then
    printf '\nKEEP=1 — stack left up. grafana %s (admin / %s)\n' "$GRAFANA" "$GRAFANA_PASSWORD"
    printf 'tear down with: docker compose -f %s/docker-compose.yml down\n' "$PWD/stack"
  else
    docker compose -f stack/docker-compose.yml down -v >/dev/null 2>&1
  fi
}
trap cleanup EXIT

command -v docker >/dev/null || { echo "docker not found — this test needs it"; exit 1; }

step "Starting the real stack (infra/observability/stack/)"
docker compose -f stack/docker-compose.yml up -d >/dev/null 2>&1 || {
  echo "compose up failed"; docker compose -f stack/docker-compose.yml logs --tail 30; exit 1; }

# --- 1. containers healthy -------------------------------------------------- #
step "1. containers"
for svc in pushgateway prometheus grafana; do
  for _ in $(seq 1 60); do
    docker compose -f stack/docker-compose.yml ps "$svc" 2>/dev/null | grep -q "Up" && break
    sleep 1
  done
  if docker compose -f stack/docker-compose.yml ps "$svc" 2>/dev/null | grep -q "Up"; then
    ok "$svc is up"
  else
    bad "$svc never came up"
  fi
done

# Grafana needs a moment past "Up" before its API answers.
for _ in $(seq 1 60); do
  curl -sf "$GRAFANA/api/health" >/dev/null 2>&1 && break
  sleep 1
done

# --- 2. publish real metrics ------------------------------------------------ #
step "2. publish a real run"
( cd "$REPO" && python3 -m resops gate config/estate.yaml >/dev/null 2>&1 )

# Pipe STRAIGHT through, exactly as `terraform output publish_command` prints it.
# Do NOT capture into a variable first: command substitution strips trailing
# newlines, the exposition format requires one, and pushgateway answers 400. That
# bug was in this script until the test caught it — a test that reshapes the
# payload is testing itself, not the thing it claims to.
code=$( cd "$REPO" && python3 -m resops metrics config/estate.yaml 2>/dev/null \
        | curl -s -o /dev/null -w '%{http_code}' --data-binary @- "$PUSH/metrics/job/resops" )
[ "$code" = "200" ] && ok "pushgateway accepted the payload (HTTP $code)" \
                    || bad "pushgateway rejected the payload (HTTP $code)"

# --- 3. prometheus has it --------------------------------------------------- #
step "3. prometheus"
for _ in $(seq 1 40); do
  n=$(curl -sf "$PROM/api/v1/query?query=resops_workloads_total" \
      | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["data"]["result"]))' 2>/dev/null)
  [ "${n:-0}" -gt 0 ] && break
  sleep 1
done
[ "${n:-0}" -gt 0 ] && ok "scraped the pushed series" \
                    || bad "prometheus never saw resops_workloads_total"

# --- 4. datasource healthy -------------------------------------------------- #
step "4. grafana datasource"
health=$(curl -sf -u "admin:$GRAFANA_PASSWORD" \
         "$GRAFANA/api/datasources/uid/resops-prom/health" \
         | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status","?"))' 2>/dev/null)
[ "$health" = "OK" ] && ok "datasource resops-prom is healthy" \
                     || bad "datasource unhealthy or missing (status=${health:-none})"

# --- 5. dashboard actually loaded ------------------------------------------- #
step "5. dashboard provisioning"
panels=$(curl -sf -u "admin:$GRAFANA_PASSWORD" \
         "$GRAFANA/api/dashboards/uid/resops-recoverability" \
         | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["dashboard"]["panels"]))' 2>/dev/null)
[ "${panels:-0}" -gt 0 ] && ok "grafana loaded the dashboard ($panels panels)" \
                         || bad "grafana did NOT load the dashboard — provisioning errors are silent"

# --- 6. every panel query returns data -------------------------------------- #
# The check that matters. Static validation cannot catch a query that parses but
# matches nothing; this does, before a room sees an empty panel.
step "6. panel queries"
python3 - "$PROM" > /tmp/panelcheck.txt <<'PY'
import json, sys, urllib.parse, urllib.request
prom = sys.argv[1]
dash = json.load(open("stack/dashboards/resops.json"))
green = red = 0
for panel in dash["panels"]:
    for target in panel.get("targets", []):
        expr = target["expr"].replace("$framework", "dora")   # the template var
        url = f"{prom}/api/v1/query?query={urllib.parse.quote(expr)}"
        try:
            n = len(json.load(urllib.request.urlopen(url, timeout=10))["data"]["result"])
        except Exception as err:                    # noqa: BLE001 — report, never raise
            print(f"  \033[31mFAIL\033[0m  {panel['title'][:44]:44} query errored: {err}")
            red += 1
            continue
        if n:
            print(f"  \033[32mPASS\033[0m  {panel['title'][:44]:44} {n} series")
            green += 1
        else:
            print(f"  \033[31mFAIL\033[0m  {panel['title'][:44]:44} returned NOTHING")
            red += 1
print(f"COUNTS {green} {red}")
PY
grep -v '^COUNTS ' /tmp/panelcheck.txt
counts=$(grep '^COUNTS ' /tmp/panelcheck.txt)
PASS=$((PASS + $(echo "$counts" | cut -d' ' -f2)))
FAIL=$((FAIL + $(echo "$counts" | cut -d' ' -f3)))
rm -f /tmp/panelcheck.txt

step "RESULT"
printf '  %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
printf '\n  The stack works. Azure only adds a VM to run it on.\n'
