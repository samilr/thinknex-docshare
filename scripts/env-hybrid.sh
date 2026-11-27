#!/usr/bin/env bash
# Genera .env.hybrid para APP_ENV=hybrid: contenedores locales conectados a la infraestructura
# real de GCP. Lee nombres desde `terraform output` y secretos desde Secret Manager; el archivo
# resultante queda con permisos 600 y está en .gitignore (nunca se versiona).
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=".env.hybrid"
GCLOUD_DIR="${CLOUDSDK_CONFIG:-$HOME/.config/gcloud}"
ADC="$GCLOUD_DIR/application_default_credentials.json"

if [[ ! -f "$ADC" ]]; then
  cat >&2 <<'MSG'
Falta la credencial ADC de Google Cloud, que usan el proxy de Cloud SQL y las apps locales.
Ejecuta una vez:   gcloud auth application-default login
MSG
  exit 1
fi

# Terraform puede usar ADC; si no, toma un token temporal de la sesión de gcloud.
export GOOGLE_OAUTH_ACCESS_TOKEN="${GOOGLE_OAUTH_ACCESS_TOKEN:-$(gcloud auth print-access-token)}"
TF="terraform -chdir=infra/terraform"

PROJECT_ID=$($TF output -raw project_id)
PREFIX=$($TF output -json services | jq -r '.web | sub("-web$"; "")')
CONNECTION=$($TF output -raw sql_connection_name)
SNAPSHOT_BUCKET=$($TF output -raw snapshot_bucket)
DMS_BUCKET=$($TF output -raw dms_bucket)
ADMIN_EMAIL=$($TF output -raw bootstrap_admin_email)

secret() { gcloud secrets versions access latest --secret="${PREFIX}-$1" --project "$PROJECT_ID"; }

# La URL de la nube usa el socket /cloudsql; en hybrid se reemplaza por el proxy local.
CLOUD_DB_URL=$(secret database-url)
DB_CREDENTIALS=${CLOUD_DB_URL#*://}
DB_CREDENTIALS=${DB_CREDENTIALS%%@*}

umask 177
cat > "$OUT" <<EOF
# Generado por scripts/env-hybrid.sh — NO versionar. Contiene secretos del ambiente en la nube.
APP_ENV=hybrid
GOOGLE_CLOUD_PROJECT=$PROJECT_ID
GCLOUD_CONFIG_DIR=$GCLOUD_DIR
CLOUDSQL_CONNECTION_NAME=$CONNECTION
SHARE_DATABASE_URL=postgresql+psycopg://$DB_CREDENTIALS@cloud-sql-proxy:5432/share
DMS_DATABASE_URL=postgresql+psycopg://$DB_CREDENTIALS@cloud-sql-proxy:5432/dms
SNAPSHOT_BUCKET=$SNAPSHOT_BUCKET
DMS_BUCKET=$DMS_BUCKET
JWT_SECRET=$(secret jwt-secret)
OTP_SECRET=$(secret otp-secret)
DMS_API_KEY=$(secret dms-api-key)
BOOTSTRAP_ADMIN_EMAIL=$ADMIN_EMAIL
BOOTSTRAP_ADMIN_PASSWORD=$(secret admin-password)
DEMO_USERS_ENABLED=true
DEMO_USERS_PASSWORD=$(secret demo-users-password)
EOF
chmod 600 "$OUT"

cat <<MSG
$OUT generado para el proyecto $PROJECT_ID.
ATENCIÓN: en APP_ENV=hybrid el portal local (http://localhost:8080) trabaja sobre los DATOS REALES
de la nube (usuarios, documentos, envíos y auditoría). Los correos van a Mailpit local.
MSG
