resource "random_password" "db" {
  length  = 32
  special = false # va dentro de DATABASE_URL: sin caracteres que requieran escape
}

resource "google_sql_database_instance" "main" {
  name                = "${var.name_prefix}-pg"
  database_version    = "POSTGRES_17"
  region              = var.region
  deletion_protection = var.deletion_protection

  settings {
    tier              = var.sql_tier
    edition           = "ENTERPRISE" # requerido para tiers shared-core
    availability_type = "ZONAL"
    disk_size         = 10
    disk_autoresize   = true

    backup_configuration {
      enabled    = true
      start_time = "05:00"
    }

    # IP pública SIN redes autorizadas: solo se accede con el conector de Cloud SQL (IAM + TLS).
    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "share" {
  name     = "share"
  instance = google_sql_database_instance.main.name
}

# Base del sistema documental simulado (document-api), en la misma instancia.
resource "google_sql_database" "dms" {
  name     = "dms"
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "share" {
  name     = "share"
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}

locals {
  dms_database_url = "postgresql+psycopg://${google_sql_user.share.name}:${random_password.db.result}@/${google_sql_database.dms.name}?host=/cloudsql/${google_sql_database_instance.main.connection_name}"
  database_url     = "postgresql+psycopg://${google_sql_user.share.name}:${random_password.db.result}@/${google_sql_database.share.name}?host=/cloudsql/${google_sql_database_instance.main.connection_name}"
}
