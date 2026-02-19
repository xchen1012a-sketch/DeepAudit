#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5000}"
USERNAME="${USERNAME:-admin01}"
PASSWORD="${PASSWORD:-ChangeMe!2026}"
PASSWORD_ROTATE_TO="${PASSWORD_ROTATE_TO:-ChangeMe!2026A1}"
INVOICE_ID="${INVOICE_ID:-1}"
TARGET_RULE_KEY="${TARGET_RULE_KEY:-HOTEL_LIMIT_NORMAL}"
RULE_LIST_URL="${RULE_LIST_URL:-/api/governance/rules}"
RULE_SAVE_URL="${RULE_SAVE_URL:-/api/governance/rules}"
AUDIT_LOG_URL="${AUDIT_LOG_URL:-/api/admin/audit_logs?limit=1200}"
A1_THRESHOLD="${A1_THRESHOLD:-1}"

PASS_COUNT=0
FAIL_COUNT=0
COOKIE_JAR="$(mktemp)"
LOGIN_HTML="$(mktemp)"

CSRF_TOKEN=""
RULE_ID=""
ORIG_ENABLED=""
ORIG_THRESHOLD=""
ORIG_THRESHOLD_JSON=""
ORIG_SEVERITY=""
ORIG_VERSION=""
RULE_SEVERITY=""
RULE_VERSION=""

log() { printf '[INFO] %s\n' "$*"; }
pass() { PASS_COUNT=$((PASS_COUNT + 1)); printf '[PASS] %s\n' "$*"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); printf '[FAIL] %s\n' "$*"; }

cleanup() {
  if [[ -n "${RULE_ID}" && -n "${ORIG_THRESHOLD_JSON}" ]]; then
    log "Restoring original rule state for ${TARGET_RULE_KEY} (best effort)"
    restore_payload="$(python - <<'PY' "${ORIG_ENABLED}" "${ORIG_THRESHOLD}" "${ORIG_THRESHOLD_JSON}" "${ORIG_SEVERITY}"
import json
import sys
enabled = (sys.argv[1].strip().lower() == "true")
threshold = float(sys.argv[2])
threshold_json = json.loads(sys.argv[3])
severity = sys.argv[4].strip() or "MEDIUM"
print(json.dumps({
    "enabled": enabled,
    "threshold": threshold,
    "threshold_json": threshold_json,
    "severity": severity,
}, ensure_ascii=False))
PY
)"
    api_request "POST" "${RULE_SAVE_URL}/${RULE_ID}" "${restore_payload}" 1 || true
  fi
  rm -f "${COOKIE_JAR}" "${LOGIN_HTML}"
}
trap cleanup EXIT

RESP_CODE=""
RESP_BODY=""

api_request() {
  local method="$1"
  local path="$2"
  local payload="${3:-}"
  local is_write="${4:-0}"
  local body_file
  body_file="$(mktemp)"

  local curl_args=(
    -sS
    -b "${COOKIE_JAR}"
    -c "${COOKIE_JAR}"
    -X "${method}"
    "${BASE_URL}${path}"
    -H "Accept: application/json"
    -o "${body_file}"
    -w "%{http_code}"
  )

  if [[ "${is_write}" == "1" ]]; then
    curl_args+=(
      -H "Content-Type: application/json"
      -H "X-CSRF-Token: ${CSRF_TOKEN}"
      --data "${payload}"
    )
  fi

  RESP_CODE="$(curl "${curl_args[@]}")"
  RESP_BODY="$(cat "${body_file}")"
  rm -f "${body_file}"
}

extract_login_csrf() {
  python - <<'PY' "${LOGIN_HTML}"
import re
import sys
path = sys.argv[1]
text = open(path, "r", encoding="utf-8", errors="ignore").read()
m = re.search(r'name="csrf_token"\s+value="([^"]+)"', text)
if not m:
    raise SystemExit(2)
print(m.group(1))
PY
}

load_target_rule() {
  api_request "GET" "${RULE_LIST_URL}" "" 0
  if [[ "${RESP_CODE}" != "200" ]]; then
    log "Failed to load rules, http=${RESP_CODE}, body=${RESP_BODY}"
    return 1
  fi
  read -r RULE_ID RULE_ENABLED RULE_THRESHOLD RULE_THRESHOLD_JSON RULE_SEVERITY RULE_VERSION < <(
    python - <<'PY' "${RESP_BODY}" "${TARGET_RULE_KEY}"
import json
import sys
payload = json.loads(sys.argv[1])
target_key = sys.argv[2].strip().upper()
rules = payload.get("rules") or []
target = None
for item in rules:
    key = str(item.get("rule_key") or "").strip().upper()
    if key == target_key:
        target = item
        break
if not isinstance(target, dict):
    raise SystemExit(3)
enabled = bool(target.get("enabled"))
threshold = float(target.get("threshold") or 0.0)
threshold_json = target.get("threshold_json")
if isinstance(threshold_json, str):
    try:
        threshold_json = json.loads(threshold_json)
    except Exception:
        threshold_json = {}
if not isinstance(threshold_json, dict):
    threshold_json = {}
severity = str(target.get("severity") or "MEDIUM").strip().upper() or "MEDIUM"
version = int(target.get("version") or 0)
print(
    f"{int(target['id'])}\t{str(enabled).lower()}\t{threshold}\t"
    f"{json.dumps(threshold_json, ensure_ascii=False, separators=(',', ':'))}\t{severity}\t{version}"
)
PY
  )
  RULE_ID="${RULE_ID//$'\r'/}"
  RULE_ENABLED="${RULE_ENABLED//$'\r'/}"
  RULE_THRESHOLD="${RULE_THRESHOLD//$'\r'/}"
  RULE_THRESHOLD_JSON="${RULE_THRESHOLD_JSON//$'\r'/}"
  RULE_SEVERITY="${RULE_SEVERITY//$'\r'/}"
  RULE_VERSION="${RULE_VERSION//$'\r'/}"
}

assert_rule_hit_limit() {
  python - <<'PY' "${RESP_BODY}" "${TARGET_RULE_KEY}" "${1}"
import json
import re
import sys
payload = json.loads(sys.argv[1])
target_key = sys.argv[2]
expected = float(sys.argv[3])
data = payload.get("data") or {}
evidence = data.get("evidence") or []
for item in evidence:
    if not isinstance(item, dict):
        continue
    if str(item.get("type") or "").lower() != "rule_hit":
        continue
    if str(item.get("key") or "") != target_key:
        continue
    value = str(item.get("value") or "")
    m = re.search(r"limit=([0-9]+(?:\.[0-9]+)?)", value)
    if not m:
        continue
    if abs(float(m.group(1)) - expected) < 1e-9:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

assert_no_hotel_limit_hit() {
  python - <<'PY' "${RESP_BODY}"
import json
import sys
payload = json.loads(sys.argv[1])
data = payload.get("data") or {}
evidence = data.get("evidence") or []
for item in evidence:
    if not isinstance(item, dict):
        continue
    if str(item.get("type") or "").lower() != "rule_hit":
        continue
    key = str(item.get("key") or "")
    if "HOTEL_LIMIT" in key:
        raise SystemExit(1)
raise SystemExit(0)
PY
}

assert_rule_update_log() {
  python - <<'PY' "${RESP_BODY}" "${TARGET_RULE_KEY}" "${1}"
import json
import sys
payload = json.loads(sys.argv[1])
rule_key = sys.argv[2]
version = str(sys.argv[3])
logs = payload.get("logs") or []
for row in logs:
    if not isinstance(row, dict):
        continue
    if str(row.get("action_type") or "").upper() != "RULE_UPDATE":
        continue
    detail = str(row.get("detail") or "")
    if f"rule_key={rule_key}" in detail and f"new_version={version}" in detail:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

login() {
  curl -sS -c "${COOKIE_JAR}" "${BASE_URL}/login" -o "${LOGIN_HTML}" >/dev/null
  CSRF_TOKEN="$(extract_login_csrf)"
  local code
  code="$(
    curl -sS -b "${COOKIE_JAR}" -c "${COOKIE_JAR}" -X POST "${BASE_URL}/login" \
      --data-urlencode "username=${USERNAME}" \
      --data-urlencode "password=${PASSWORD}" \
      --data-urlencode "csrf_token=${CSRF_TOKEN}" \
      --data-urlencode "next=/dashboard" \
      -o /dev/null -w "%{http_code}"
  )"
  if [[ "${code}" != "302" && "${code}" != "200" ]]; then
    log "Login failed, http=${code}"
    exit 1
  fi
  api_request "GET" "/api/me" "" 0
  if [[ "${RESP_CODE}" != "200" ]]; then
    log "Login verify failed, http=${RESP_CODE}, body=${RESP_BODY}"
    exit 1
  fi
}

ensure_password_ready() {
  api_request "GET" "${RULE_LIST_URL}" "" 0
  if [[ "${RESP_CODE}" == "200" ]]; then
    return 0
  fi
  if [[ "${RESP_CODE}" != "403" ]]; then
    return 0
  fi
  if ! python - <<'PY' "${RESP_BODY}"
import json, sys
payload = json.loads(sys.argv[1] or "{}")
raise SystemExit(0 if str(payload.get("msg") or "") == "password_change_required" else 1)
PY
  then
    return 0
  fi
  log "Password change required, rotating with /api/auth/change_password"
  payload="$(python - <<'PY' "${PASSWORD}" "${PASSWORD_ROTATE_TO}"
import json, sys
print(json.dumps({"old_password": sys.argv[1], "new_password": sys.argv[2]}, ensure_ascii=False))
PY
)"
  api_request "POST" "/api/auth/change_password" "${payload}" 1
  if [[ "${RESP_CODE}" != "200" ]]; then
    log "Password change failed, http=${RESP_CODE}, body=${RESP_BODY}"
    exit 1
  fi
}

main() {
  log "Logging in to ${BASE_URL} as ${USERNAME}"
  login
  ensure_password_ready

  load_target_rule
  ORIG_ENABLED="${RULE_ENABLED}"
  ORIG_THRESHOLD="${RULE_THRESHOLD}"
  ORIG_THRESHOLD_JSON="${RULE_THRESHOLD_JSON}"
  ORIG_SEVERITY="${RULE_SEVERITY}"
  ORIG_VERSION="${RULE_VERSION}"

  # A1
  a1_payload="$(python - <<'PY' "${A1_THRESHOLD}"
import json, sys
limit = float(sys.argv[1])
print(json.dumps({"enabled": True, "threshold": limit, "threshold_json": {"limit": limit}}, ensure_ascii=False))
PY
)"
  api_request "POST" "${RULE_SAVE_URL}/${RULE_ID}" "${a1_payload}" 1
  if [[ "${RESP_CODE}" != "200" ]]; then
    fail "A1 save threshold failed (http=${RESP_CODE})"
  else
    api_request "POST" "/invoice/${INVOICE_ID}/ai" "{}" 1
    if [[ "${RESP_CODE}" == "200" ]] && assert_rule_hit_limit "${A1_THRESHOLD}"; then
      pass "A1 threshold update takes effect on /invoice/${INVOICE_ID}/ai evidence"
    else
      fail "A1 evidence does not reflect new threshold"
    fi
  fi

  # A2
  api_request "POST" "${RULE_SAVE_URL}/${RULE_ID}" '{"enabled":false}' 1
  if [[ "${RESP_CODE}" != "200" ]]; then
    fail "A2 disable rule failed (http=${RESP_CODE})"
  else
    api_request "POST" "/invoice/${INVOICE_ID}/ai" "{}" 1
    if [[ "${RESP_CODE}" == "200" ]] && assert_no_hotel_limit_hit; then
      pass "A2 disabled HOTEL_LIMIT rule no longer appears in evidence"
    else
      fail "A2 disabled rule still appears in evidence"
    fi
  fi

  # A3
  load_target_rule
  version_before="${RULE_VERSION}"
  a3_payload='{"enabled":true,"threshold":2,"threshold_json":{"limit":2}}'
  api_request "POST" "${RULE_SAVE_URL}/${RULE_ID}" "${a3_payload}" 1
  if [[ "${RESP_CODE}" != "200" ]]; then
    fail "A3 save rule failed (http=${RESP_CODE})"
  else
    version_after="$(python - <<'PY' "${RESP_BODY}"
import json, sys
payload = json.loads(sys.argv[1] or "{}")
rule = payload.get("rule") or {}
print(int(rule.get("version") or 0))
PY
)"
    version_after="${version_after//$'\r'/}"
    if [[ "${version_after}" -le "${version_before}" ]]; then
      fail "A3 version did not increase"
    else
      api_request "GET" "${AUDIT_LOG_URL}" "" 0
      if [[ "${RESP_CODE}" == "200" ]] && assert_rule_update_log "${version_after}"; then
        pass "A3 version increments and RULE_UPDATE audit contains rule_key + new_version"
      else
        fail "A3 RULE_UPDATE audit check failed"
      fi
    fi
  fi

  # A4
  api_request "POST" "${RULE_SAVE_URL}/${RULE_ID}" '{"threshold_json":null}' 1
  a4_ok_null="0"
  if [[ "${RESP_CODE}" == "200" ]]; then
    load_target_rule
    if python - <<'PY' "${RULE_THRESHOLD_JSON}"
import json, sys
payload = json.loads(sys.argv[1] or "{}")
raise SystemExit(0 if isinstance(payload, dict) and len(payload) > 0 else 1)
PY
    then
      a4_ok_null="1"
    fi
  fi
  api_request "POST" "${RULE_SAVE_URL}/${RULE_ID}" '{"threshold_json":""}' 1
  a4_ok_empty="0"
  if [[ "${RESP_CODE}" == "200" ]]; then
    load_target_rule
    if python - <<'PY' "${RULE_THRESHOLD_JSON}"
import json, sys
payload = json.loads(sys.argv[1] or "{}")
raise SystemExit(0 if isinstance(payload, dict) and len(payload) > 0 else 1)
PY
    then
      a4_ok_empty="1"
    fi
  fi
  if [[ "${a4_ok_null}" == "1" && "${a4_ok_empty}" == "1" ]]; then
    pass "A4 threshold_json null/empty string are backfilled to default dict"
  else
    fail "A4 threshold_json null/empty fallback failed"
  fi

  # A5
  load_target_rule
  version_before_bad="${RULE_VERSION}"
  threshold_json_before_bad="${RULE_THRESHOLD_JSON}"
  api_request "POST" "${RULE_SAVE_URL}/${RULE_ID}" '{"threshold_json":"{invalid_json"}' 1
  a5_http_ok="0"
  a5_payload_ok="0"
  if [[ "${RESP_CODE}" == "400" ]]; then
    a5_http_ok="1"
    if python - <<'PY' "${RESP_BODY}"
import json, sys
payload = json.loads(sys.argv[1] or "{}")
ok = payload.get("ok")
msg = str(payload.get("msg") or "")
raise SystemExit(0 if ok is False and msg == "invalid_threshold_json" else 1)
PY
    then
      a5_payload_ok="1"
    fi
  fi
  load_target_rule
  if [[ "${a5_http_ok}" == "1" && "${a5_payload_ok}" == "1" && "${RULE_VERSION}" == "${version_before_bad}" && "${RULE_THRESHOLD_JSON}" == "${threshold_json_before_bad}" ]]; then
    pass "A5 invalid threshold_json returns 400 and DB remains unchanged"
  else
    fail "A5 invalid threshold_json validation failed"
  fi

  log "Acceptance summary: PASS=${PASS_COUNT}, FAIL=${FAIL_COUNT}"
  if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
  fi
}

main "$@"
