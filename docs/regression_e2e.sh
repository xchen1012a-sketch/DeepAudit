#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5000}"
LOGIN_USERNAME="${LOGIN_USERNAME:-admin01}"
PASSWORD="${PASSWORD:-ChangeMe!2026}"
PASSWORD_ROTATE_TO="${PASSWORD_ROTATE_TO:-ChangeMe!2026A1}"
UPLOAD_FILE="${UPLOAD_FILE:-test_assets/test_invoice.png}"
UPLOAD_AMOUNT="${UPLOAD_AMOUNT:-860.00}"
RULE_KEY="${RULE_KEY:-HOTEL_LIMIT_NORMAL}"
RULE_FORCE_THRESHOLD="${RULE_FORCE_THRESHOLD:-1}"
RULE_LIST_URL="${RULE_LIST_URL:-/api/governance/rules}"
RULE_SAVE_URL="${RULE_SAVE_URL:-/api/governance/rules}"
AUDIT_LOG_URL="${AUDIT_LOG_URL:-/api/admin/audit_logs?limit=2000}"

PASS_COUNT=0
FAIL_COUNT=0
COOKIE_JAR="$(mktemp)"
LOGIN_HTML="$(mktemp)"
CSRF_TOKEN=""
RESP_CODE=""
RESP_BODY=""

RULE_ID=""
ORIG_ENABLED=""
ORIG_THRESHOLD=""
ORIG_THRESHOLD_JSON=""
ORIG_SEVERITY=""
ORIG_VERSION=""

INVOICE_ID=""
TRACE_ID=""
RISK_LEVEL=""
EVENT_ID=""
CASE_ID=""

log() { printf '[INFO] %s\n' "$*"; }
pass() { PASS_COUNT=$((PASS_COUNT + 1)); printf '[PASS] %s\n' "$*"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); printf '[FAIL] %s\n' "$*"; }

cleanup() {
  if [[ -n "${RULE_ID}" && -n "${ORIG_THRESHOLD_JSON}" ]]; then
    log "Restoring governance rule ${RULE_KEY} (best effort)"
    local restore_payload
    restore_payload="$(python - <<'PY' "${ORIG_ENABLED}" "${ORIG_THRESHOLD}" "${ORIG_THRESHOLD_JSON}" "${ORIG_SEVERITY}"
import json
import sys
enabled = str(sys.argv[1]).strip().lower() == "true"
threshold = float(sys.argv[2])
threshold_json = json.loads(sys.argv[3])
severity = str(sys.argv[4]).strip().upper() or "MEDIUM"
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

upload_invoice_manual() {
  local body_file
  body_file="$(mktemp)"
  RESP_CODE="$(
    curl -sS \
      -b "${COOKIE_JAR}" \
      -c "${COOKIE_JAR}" \
      -X POST "${BASE_URL}/upload" \
      -H "Accept: application/json" \
      -H "X-CSRF-Token: ${CSRF_TOKEN}" \
      -F "file=@${UPLOAD_FILE}" \
      -F "entry_mode=manual" \
      -F "amount=${UPLOAD_AMOUNT}" \
      -F "invoice_date=$(date +%F)" \
      -F "seller_name=Regression Hotel" \
      -F "expense_category=Travel" \
      -F "expense_description=E2E regression upload" \
      -o "${body_file}" \
      -w "%{http_code}"
  )"
  RESP_BODY="$(cat "${body_file}")"
  rm -f "${body_file}"
}

extract_login_csrf() {
  python - <<'PY' "${LOGIN_HTML}"
import re
import sys
text = open(sys.argv[1], "r", encoding="utf-8", errors="ignore").read()
m = re.search(r'name="csrf_token"\s+value="([^"]+)"', text)
if not m:
    raise SystemExit(2)
print(m.group(1))
PY
}

try_login_password() {
  local candidate="$1"
  local code
  code="$(
    curl -sS -b "${COOKIE_JAR}" -c "${COOKIE_JAR}" -X POST "${BASE_URL}/login" \
      --data-urlencode "username=${LOGIN_USERNAME}" \
      --data-urlencode "password=${candidate}" \
      --data-urlencode "csrf_token=${CSRF_TOKEN}" \
      --data-urlencode "next=/dashboard" \
      -o /dev/null -w "%{http_code}"
  )"
  if [[ "${code}" == "302" || "${code}" == "200" ]]; then
    PASSWORD="${candidate}"
    return 0
  fi
  return 1
}

login() {
  curl -sS -c "${COOKIE_JAR}" "${BASE_URL}/login" -o "${LOGIN_HTML}" >/dev/null
  CSRF_TOKEN="$(extract_login_csrf)"

  if try_login_password "${PASSWORD}"; then
    return 0
  fi
  if [[ -n "${PASSWORD_ROTATE_TO}" ]] && try_login_password "${PASSWORD_ROTATE_TO}"; then
    return 0
  fi
  log "Login failed with provided password candidates"
  exit 1
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
import json
import sys
payload = json.loads(sys.argv[1] or "{}")
raise SystemExit(0 if str(payload.get("msg") or "") == "password_change_required" else 1)
PY
  then
    return 0
  fi
  log "Password change required, rotating with /api/auth/change_password"
  local payload
  payload="$(python - <<'PY' "${PASSWORD}" "${PASSWORD_ROTATE_TO}"
import json
import sys
print(json.dumps({"old_password": sys.argv[1], "new_password": sys.argv[2]}, ensure_ascii=False))
PY
)"
  api_request "POST" "/api/auth/change_password" "${payload}" 1
  if [[ "${RESP_CODE}" != "200" ]]; then
    log "Password change failed, http=${RESP_CODE}, body=${RESP_BODY}"
    exit 1
  fi
}

load_target_rule() {
  api_request "GET" "${RULE_LIST_URL}" "" 0
  if [[ "${RESP_CODE}" != "200" ]]; then
    log "Failed to load rules, http=${RESP_CODE}, body=${RESP_BODY}"
    return 1
  fi

  read -r RULE_ID RULE_ENABLED RULE_THRESHOLD RULE_THRESHOLD_JSON RULE_SEVERITY RULE_VERSION < <(
    python - <<'PY' "${RESP_BODY}" "${RULE_KEY}"
import json
import sys
payload = json.loads(sys.argv[1])
target_key = sys.argv[2].strip().upper()
rules = payload.get("rules") or []
target = None
for row in rules:
    key = str(row.get("rule_key") or "").strip().upper()
    if key == target_key:
        target = row
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

main() {
  log "Running regression E2E against ${BASE_URL}"

  # E1 login
  login
  ensure_password_ready
  api_request "GET" "/api/me" "" 0
  if [[ "${RESP_CODE}" == "200" ]] && python - <<'PY' "${RESP_BODY}"
import json
import sys
payload = json.loads(sys.argv[1] or "{}")
raise SystemExit(0 if int(payload.get("id") or 0) > 0 else 1)
PY
  then
    pass "E1 login admin01 success"
  else
    fail "E1 login verify failed (http=${RESP_CODE})"
  fi

  # Setup: force HOTEL_LIMIT rule low for deterministic medium/high and RULE_UPDATE audit.
  load_target_rule
  ORIG_ENABLED="${RULE_ENABLED}"
  ORIG_THRESHOLD="${RULE_THRESHOLD}"
  ORIG_THRESHOLD_JSON="${RULE_THRESHOLD_JSON}"
  ORIG_SEVERITY="${RULE_SEVERITY}"
  ORIG_VERSION="${RULE_VERSION}"
  setup_payload="$(python - <<'PY' "${RULE_FORCE_THRESHOLD}"
import json
import sys
limit = float(sys.argv[1])
print(json.dumps({"enabled": True, "threshold": limit, "threshold_json": {"limit": limit}}, ensure_ascii=False))
PY
)"
  api_request "POST" "${RULE_SAVE_URL}/${RULE_ID}" "${setup_payload}" 1
  if [[ "${RESP_CODE}" != "200" ]]; then
    fail "Setup rule update failed (http=${RESP_CODE})"
  fi

  # E2 upload/import
  upload_invoice_manual
  if [[ "${RESP_CODE}" == "200" ]]; then
    INVOICE_ID="$(
      python - <<'PY' "${RESP_BODY}"
import json
import sys
payload = json.loads(sys.argv[1] or "{}")
if payload.get("ok") is True and int(payload.get("id") or 0) > 0:
    print(int(payload["id"]))
else:
    raise SystemExit(1)
PY
)"
    INVOICE_ID="${INVOICE_ID//$'\r'/}"
    pass "E2 upload/import created invoice_id=${INVOICE_ID}"
  else
    fail "E2 upload/import failed (http=${RESP_CODE}, body=${RESP_BODY})"
  fi

  # E3 AI explain
  api_request "POST" "/invoice/${INVOICE_ID}/ai" "{}" 1
  if [[ "${RESP_CODE}" == "200" ]]; then
    read -r TRACE_ID RISK_LEVEL < <(
      python - <<'PY' "${RESP_BODY}"
import json
import sys
payload = json.loads(sys.argv[1] or "{}")
if str(payload.get("status")) != "success":
    raise SystemExit(1)
data = payload.get("data") or {}
trace_id = str(data.get("trace_id") or "").strip()
risk_level = str(data.get("risk_level") or "").strip().upper()
if not trace_id:
    raise SystemExit(2)
print(f"{trace_id}\t{risk_level}")
PY
    )
    TRACE_ID="${TRACE_ID//$'\r'/}"
    RISK_LEVEL="${RISK_LEVEL//$'\r'/}"
    pass "E3 /invoice/${INVOICE_ID}/ai success with trace_id"
  else
    fail "E3 AI call failed (http=${RESP_CODE}, body=${RESP_BODY})"
  fi

  # E4 risk event creation verify via read-only API
  api_request "GET" "/api/risk/events?invoice_id=${INVOICE_ID}&limit=20" "" 0
  if [[ "${RESP_CODE}" == "200" ]]; then
    EVENT_ID="$(
      python - <<'PY' "${RESP_BODY}"
import json
import sys
payload = json.loads(sys.argv[1] or "{}")
events = payload.get("events") or []
for row in events:
    if not isinstance(row, dict):
        continue
    level = str(row.get("risk_level") or "").upper()
    if level in {"MEDIUM", "HIGH"} and int(row.get("id") or 0) > 0:
        print(int(row["id"]))
        raise SystemExit(0)
raise SystemExit(1)
PY
)"
    EVENT_ID="${EVENT_ID//$'\r'/}"
    pass "E4 risk_event created for invoice_id=${INVOICE_ID}"
  else
    fail "E4 risk_event query failed (http=${RESP_CODE}, body=${RESP_BODY})"
  fi

  # E5 create case
  api_request "POST" "/risk/events/${EVENT_ID}/create_case" '{"action_note":"regression_e2e_create_case"}' 1
  if [[ "${RESP_CODE}" == "200" ]]; then
    CASE_ID="$(
      python - <<'PY' "${RESP_BODY}"
import json
import sys
payload = json.loads(sys.argv[1] or "{}")
case = payload.get("case") or {}
cid = int(case.get("id") or 0)
if payload.get("ok") is True and cid > 0:
    print(cid)
    raise SystemExit(0)
raise SystemExit(1)
PY
)"
    CASE_ID="${CASE_ID//$'\r'/}"
    pass "E5 create_case success case_id=${CASE_ID}"
  else
    fail "E5 create_case failed (http=${RESP_CODE}, body=${RESP_BODY})"
  fi

  # E6 assign case
  api_request "POST" "/risk/cases/${CASE_ID}/assign" '{"assigned_to":"admin01","action_note":"regression_e2e_assign"}' 1
  if [[ "${RESP_CODE}" == "200" ]] && python - <<'PY' "${RESP_BODY}"
import json
import sys
payload = json.loads(sys.argv[1] or "{}")
case = payload.get("case") or {}
status = str(case.get("status") or "").upper()
raise SystemExit(0 if payload.get("ok") is True and status in {"ASSIGNED", "PROCESSING"} else 1)
PY
  then
    pass "E6 assign case success"
  else
    fail "E6 assign case failed (http=${RESP_CODE}, body=${RESP_BODY})"
  fi

  # E7 close case
  api_request "POST" "/risk/cases/${CASE_ID}/close" '{"resolution_note":"regression_e2e_close","action_note":"regression_e2e_close"}' 1
  if [[ "${RESP_CODE}" == "200" ]] && python - <<'PY' "${RESP_BODY}"
import json
import sys
payload = json.loads(sys.argv[1] or "{}")
case = payload.get("case") or {}
status = str(case.get("status") or "").upper()
raise SystemExit(0 if payload.get("ok") is True and status == "CLOSED" else 1)
PY
  then
    pass "E7 close case success"
  else
    fail "E7 close case failed (http=${RESP_CODE}, body=${RESP_BODY})"
  fi

  # E8 AI ledger trace chain
  api_request "GET" "/api/ai/ledger/${TRACE_ID}" "" 0
  if [[ "${RESP_CODE}" == "200" ]] && python - <<'PY' "${RESP_BODY}"
import json
import sys
payload = json.loads(sys.argv[1] or "{}")
ok = payload.get("ok") is True
hash_prev = str(payload.get("hash_prev") or "").strip()
hash_curr = str(payload.get("hash_curr") or "").strip()
raise SystemExit(0 if ok and hash_prev and hash_curr else 1)
PY
  then
    pass "E8 AI ledger hash chain exists"
  else
    fail "E8 AI ledger query failed (http=${RESP_CODE}, body=${RESP_BODY})"
  fi

  # E9 audit log action types
  api_request "GET" "${AUDIT_LOG_URL}" "" 0
  local audit_json_file
  audit_json_file="$(mktemp)"
  printf '%s' "${RESP_BODY}" > "${audit_json_file}"
  if [[ "${RESP_CODE}" == "200" ]] && python - <<'PY' "${audit_json_file}"
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8", errors="ignore") as fh:
    payload = json.loads(fh.read() or "{}")
logs = payload.get("logs") or []
required = {"RULE_UPDATE", "CASE_CREATED", "CASE_CLOSED", "LOGIN_SUCCESS"}
seen = set()
for row in logs:
    if isinstance(row, dict):
        seen.add(str(row.get("action_type") or "").upper())
missing = sorted(required - seen)
if missing:
    raise SystemExit(1)
PY
  then
    pass "E9 audit logs include RULE_UPDATE/CASE_CREATED/CASE_CLOSED/LOGIN_SUCCESS"
  else
    fail "E9 audit log verification failed (http=${RESP_CODE}, body=${RESP_BODY})"
  fi
  rm -f "${audit_json_file}"

  log "Regression summary: PASS=${PASS_COUNT}, FAIL=${FAIL_COUNT}"
  if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
  fi
}

main "$@"
