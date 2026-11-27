#!/usr/bin/env bash
# Prepara un proyecto GCP para Terraform: APIs mínimas + bucket privado y versionado para el estado.
# Uso: infra/gcp/bootstrap.sh PROJECT_ID [REGION]
set -euo pipefail
cd "$(dirname "$0")/../.."

PROJECT_ID="${1:?uso: infra/gcp/bootstrap.sh PROJECT_ID [REGION]}"
REGION="${2:-southamerica-west1}"
BUCKET="${PROJECT_ID}-tfstate"

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com storage.googleapis.com

if ! gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" \
    --uniform-bucket-level-access --public-access-prevention
fi
gcloud storage buckets update "gs://$BUCKET" --versioning >/dev/null

terraform -chdir=infra/terraform init -reconfigure -input=false -backend-config="bucket=$BUCKET"
echo "Listo. Estado de Terraform en gs://$BUCKET"
