#!/usr/bin/env bash
# Construye las imágenes (linux/amd64), las publica en Artifact Registry y despliega en Cloud Run:
#   document-api → migraciones (job) → share-api → web
# Toma registro/región/nombres de `terraform output`, o de variables de entorno en CI:
#   REGISTRY, REGION, NAME_PREFIX
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -z "${REGISTRY:-}" ]]; then
  TF="terraform -chdir=infra/terraform"
  REGISTRY=$($TF output -raw registry)
  REGION=$($TF output -raw region)
  NAME_PREFIX=$($TF output -json services | jq -r '.web | sub("-web$"; "")')
fi
: "${REGION:?}" "${NAME_PREFIX:?}"
TAG="${TAG:-$(git rev-parse --short HEAD)}"
[[ -n "$(git status --porcelain)" && -z "${CI:-}" ]] && TAG="${TAG}-dirty"

step() { printf "\n\033[1;34m━━ %s\033[0m\n" "$*"; }
image() { echo "$REGISTRY/$1:$TAG"; }

step "Autenticando Docker con Artifact Registry"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

step "Construyendo y publicando imágenes ($TAG)"
docker buildx build --platform linux/amd64 --push -t "$(image document-api)" services/document-api
docker buildx build --platform linux/amd64 --push -t "$(image share-api)" services/share-api
docker buildx build --platform linux/amd64 --push -t "$(image web)" \
  --build-arg VITE_SHOW_DEMO_ACCOUNTS="${SHOW_DEMO_ACCOUNTS:-true}" web

step "Desplegando document-api"
gcloud run deploy "${NAME_PREFIX}-document-api" --image "$(image document-api)" --region "$REGION" --quiet

step "Migraciones de base de datos (Cloud Run Job)"
for job in migrate gc; do
  gcloud run jobs update "${NAME_PREFIX}-${job}" --image "$(image share-api)" --region "$REGION" --quiet
done
gcloud run jobs execute "${NAME_PREFIX}-migrate" --region "$REGION" --wait

step "Desplegando share-api y web"
gcloud run deploy "${NAME_PREFIX}-share-api" --image "$(image share-api)" --region "$REGION" --quiet
gcloud run deploy "${NAME_PREFIX}-web" --image "$(image web)" --region "$REGION" --quiet

URL=$(gcloud run services describe "${NAME_PREFIX}-web" --region "$REGION" --format='value(status.url)')
step "Listo: $URL"
