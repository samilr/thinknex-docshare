# Una cuenta de servicio por componente, con permisos mínimos y sin llaves JSON.

resource "google_service_account" "share_api" {
  account_id   = "${var.name_prefix}-share-api"
  display_name = "share-api (Cloud Run)"
}

resource "google_service_account" "document_api" {
  account_id   = "${var.name_prefix}-document-api"
  display_name = "document-api (Cloud Run)"
}

resource "google_service_account" "web" {
  account_id   = "${var.name_prefix}-web"
  display_name = "web (Cloud Run, sin permisos)"
}

resource "google_service_account" "scheduler" {
  account_id   = "${var.name_prefix}-scheduler"
  display_name = "Cloud Scheduler: dispara el job de retención"
}

# share-api: Cloud SQL, sus secretos y el bucket de snapshots
resource "google_project_iam_member" "share_api_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = google_service_account.share_api.member
}

resource "google_secret_manager_secret_iam_member" "share_api" {
  for_each  = local.share_api_secrets
  secret_id = google_secret_manager_secret.this[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.share_api.member
}

resource "google_storage_bucket_iam_member" "share_api_snapshots" {
  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.objectAdmin"
  member = google_service_account.share_api.member
}

# document-api: su bucket y su API key
resource "google_secret_manager_secret_iam_member" "dms" {
  for_each  = toset(local.dms_secrets)
  secret_id = google_secret_manager_secret.this[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.document_api.member
}

resource "google_project_iam_member" "dms_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = google_service_account.document_api.member
}

resource "google_storage_bucket_iam_member" "dms_bucket" {
  bucket = google_storage_bucket.dms.name
  role   = "roles/storage.objectAdmin"
  member = google_service_account.document_api.member
}
