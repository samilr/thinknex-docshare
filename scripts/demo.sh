#!/usr/bin/env bash
# Demo de punta a punta contra el stack levantado con `make up`. Requiere curl y jq.
set -euo pipefail
cd "$(dirname "$0")/.."

BASE="${BASE_URL:-http://localhost:8000}"
set -a; . ./.env; set +a
mkdir -p out

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
step() { printf "\n\033[1;34m━━ %s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✔\033[0m %s\n" "$*"; }
info() { printf "  %s\n" "$*"; }

login() {
  curl -sf -X POST "$BASE/api/v1/auth/token" \
    --data-urlencode "username=$1" --data-urlencode "password=$DEMO_USERS_PASSWORD" | jq -r .access_token
}
api() { # api METHOD PATH TOKEN [JSON] -> imprime body; el HTTP status queda en out/.status
  local method=$1 path=$2 token=$3 body=${4:-}
  local args=(-s -o out/.body -w "%{http_code}" -X "$method" -H "Authorization: Bearer $token")
  [[ -n "$body" ]] && args+=(-H "Content-Type: application/json" -d "$body")
  curl "${args[@]}" "$BASE$path" > out/.status; cat out/.body
}
http_status() { cat out/.status; }
inbox()      { curl -sf "$BASE/api/v1/admin/inbox?limit=20" -H "Authorization: Bearer $ADMIN"; }
last_link()  { inbox | jq -r '[.items[] | select(.kind=="LINK")][0].body' | grep -oE 'https?://[^ ]+/s/[A-Za-z0-9_-]+'; }
last_otp()   { inbox | jq -r '[.items[] | select(.kind=="OTP")][0].body' | grep -oE '[0-9]{6}' | head -1; }

bold "Demo · Compartición segura de documentos"
ANA=$(login ana@thinknex.example); CARLA=$(login carla@thinknex.example)
ADMIN=$(curl -sf -X POST "$BASE/api/v1/auth/token" --data-urlencode "username=$BOOTSTRAP_ADMIN_EMAIL" \
  --data-urlencode "password=$BOOTSTRAP_ADMIN_PASSWORD" | jq -r .access_token)
ok "Login: ana (SHARER), carla (AUDITOR) y el ADMIN (lee la bandeja simulada)"

step "1. Catálogo del sistema documental (vía share-api)"
api GET /api/v1/documents "$ANA" | jq -r '.items[] | "  \(.id)  \(.classification|.[0:12])\t\(.title)"'

step "2. Ana comparte doc-003 (INTERNAL) con un auditor externo por EMAIL"
SHARE=$(api POST /api/v1/shares "$ANA" '{"document_id":"doc-003","recipient":{"name":"Pedro Auditor","email":"pedro@auditora.example"},"channel":"EMAIL","reason":"Solicitud de auditoría externa Q3","max_accesses":2}')
echo "$SHARE" | jq '{id, status, channel, expires_at, max_accesses, sensitivity_decision, notification_status}'
SHARE_ID=$(echo "$SHARE" | jq -r .id)
info "La respuesta NO incluye el enlace: solo lo recibe el destinatario → ver http://localhost:8025"

step "3. El destinatario abre el enlace, pide un OTP y descarga"
LINK=$(last_link)
info "Enlace recibido: ${LINK%/*}/<token>"
info "Página del destinatario: HTTP $(curl -s -o /dev/null -w '%{http_code}' "$LINK")"
curl -sf -X POST "$LINK/otp" | jq -c .
OTP=$(last_otp); info "OTP recibido por el canal: $OTP"
ACCESS=$(curl -sf -X POST "$LINK/verify" -H 'Content-Type: application/json' -d "{\"code\":\"$OTP\"}" | jq -r .access_token)
curl -sf "$LINK/download" -H "Authorization: Bearer $ACCESS" -o out/doc-003-compartido.pdf
ok "Descargado con marca de agua → out/doc-003-compartido.pdf ($(wc -c < out/doc-003-compartido.pdf | tr -d ' ') bytes)"

step "4. Documento con datos personales (doc-006) por WHATSAPP → requiere confirmación"
api POST /api/v1/shares "$ANA" '{"document_id":"doc-006","recipient":{"name":"María González","phone":"+56 9 8765 4321"},"channel":"WHATSAPP","reason":"Certificado solicitado por la clienta"}' \
  | jq -c '{status, title, reasons: .report.reasons, findings: [.report.findings[] | {type, count, samples}]}'
info "HTTP $(http_status) → se reenvía con acknowledge_sensitive=true"
api POST /api/v1/shares "$ANA" '{"document_id":"doc-006","recipient":{"name":"María González","phone":"+56 9 8765 4321"},"channel":"WHATSAPP","reason":"Certificado solicitado por la clienta","acknowledge_sensitive":true}' \
  | jq -c '{id, status, channel, sensitivity_decision}'
ok "HTTP $(http_status) · mensaje simulado de WhatsApp en la bandeja (/api/v1/admin/inbox)"

step "5. Documento RESTRICTED (doc-005) a un externo → bloqueado por política"
api POST /api/v1/shares "$ANA" '{"document_id":"doc-005","recipient":{"name":"Externo","email":"x@competidor.example"},"channel":"EMAIL","reason":"intento","acknowledge_sensitive":true}' | jq -c '{status, detail}'

step "6. Revocación: Ana revoca el share del paso 2 y el enlace deja de funcionar"
api POST "/api/v1/shares/$SHARE_ID/revoke" "$ANA" | jq -c '{id, status, revoked_at}'
info "Enlace tras revocar: HTTP $(curl -s -o /dev/null -w '%{http_code}' -X POST "$LINK/otp")"

step "7. Fuerza bruta de OTP: 5 intentos fallidos bloquean el enlace (doc-004 por SMS)"
api POST /api/v1/shares "$ANA" '{"document_id":"doc-004","recipient":{"name":"Cliente","phone":"+56 9 2222 3333"},"channel":"SMS","reason":"Catálogo comercial"}' >/dev/null
LINK2=$(last_link); curl -sf -X POST "$LINK2/otp" >/dev/null
for i in 1 2 3 4 5; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$LINK2/verify" -H 'Content-Type: application/json' -d '{"code":"000000"}')
  info "intento $i → HTTP $code"
done

step "8. Auditoría (Carla, AUDITOR): ¿quién compartió doc-003, cuándo y por qué medio?"
api GET "/api/v1/audit?document_id=doc-003" "$CARLA" \
  | jq -r '.items | reverse[] | "  \(.occurred_at[11:19])  \(.event_type|.[0:20])\t\(.channel // "-")\t\(.actor // .actor_type)\t\(.metadata.reason // .metadata.decision // "")"'

step "9. Integridad de la auditoría"
api GET /api/v1/audit/verify "$CARLA" | jq -c .
info "Intento de alterar un evento directamente en la BD:"
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-share}" \
  -c "UPDATE audit_events SET channel='SMS' WHERE id=(SELECT min(id) FROM audit_events)" 2>&1 | sed 's/^/  /' || true

printf "\n"; bold "Listo. Portal: http://localhost:8080 · Swagger: $BASE/docs · Mailpit: http://localhost:8025"
