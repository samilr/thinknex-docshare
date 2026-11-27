# ADR-0006: GCP con Cloud Run, Cloud SQL y Terraform

**Estado:** aceptada

## Contexto
La demo debe quedar accesible para los evaluadores en una URL pública, con un costo bajo y una
infraestructura reproducible. Se evaluaron Azure (App Service) y GCP.

## Decisión
- **Cloud Run** para los tres contenedores, con mínimo 0 instancias. No hay servidores que
  administrar, el HTTPS viene incluido y el costo en reposo es nulo.
- **Cloud SQL Postgres 17 `db-f1-micro`** (edición Enterprise), en la región `southamerica-west1`
  (Santiago), cerca del negocio.
- **Cloud Storage** para los snapshots, con el adaptador `GcsBlobStorage` y credenciales del entorno
  (ADC). El código no cambió: es otro adaptador del mismo puerto `BlobStorage`.
- **Terraform** con estado en GCS. Las imágenes las despliega `deploy.sh`, y Terraform ignora el
  campo `image` para no pisar despliegues.

## Alternativas descartadas
- **GKE:** desproporcionado para tres servicios pequeños.
- **App Engine:** limita la contenerización y es menos portable.
- **Azure App Service:** viable, pero con un plan siempre encendido y mayor costo fijo.

## Consecuencias
- Hay arranques en frío de 1 a 3 s tras períodos sin uso (aceptable para una demo; se evita con `min_instance_count = 1`).
- Cloud SQL es el único costo fijo relevante (~US$10/mes). `make gcp-destroy` lo elimina.
