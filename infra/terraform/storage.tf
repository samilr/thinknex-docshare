resource "google_storage_bucket" "snapshots" {
  name                        = "${var.project_id}-${var.name_prefix}-snapshots"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  # Respaldo de la retención de la app: ningún snapshot vive más de 30 días.
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket" "dms" {
  name                        = "${var.project_id}-${var.name_prefix}-dms"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  depends_on = [google_project_service.apis]
}
