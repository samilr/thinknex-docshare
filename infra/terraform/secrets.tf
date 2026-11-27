# Secretos generados por Terraform y guardados en Secret Manager. Los valores quedan también en el
# estado de Terraform: el bucket de estado es privado y versionado (ver docs/06-despliegue-gcp.md).

resource "random_password" "jwt" {
  length  = 64
  special = false
}

resource "random_password" "otp" {
  length  = 64
  special = false
}

resource "random_password" "dms_api_key" {
  length  = 48
  special = false
}

resource "random_password" "admin" {
  length      = 18
  min_upper   = 2
  min_lower   = 2
  min_numeric = 2
  special     = false
}

resource "random_password" "demo_users" {
  length      = 16
  min_upper   = 2
  min_lower   = 2
  min_numeric = 2
  special     = false
}

locals {
  # nombre lógico => valor. Los opcionales solo se crean si tienen valor.
  secret_values = merge(
    {
      "database-url"        = local.database_url
      "dms-database-url"    = local.dms_database_url
      "jwt-secret"          = random_password.jwt.result
      "otp-secret"          = random_password.otp.result
      "dms-api-key"         = random_password.dms_api_key.result
      "admin-password"      = random_password.admin.result
      "demo-users-password" = random_password.demo_users.result
    },
    var.resend_api_key != "" ? { "resend-api-key" = var.resend_api_key } : {},
    var.anthropic_api_key != "" ? { "anthropic-api-key" = var.anthropic_api_key } : {},
  )
  # Mínimo privilegio: cada servicio lee solo sus secretos.
  dms_secrets       = ["dms-api-key", "dms-database-url"]
  share_api_secrets = setsubtract(nonsensitive(toset(keys(local.secret_values))), ["dms-database-url"])
}

resource "google_secret_manager_secret" "this" {
  for_each  = nonsensitive(toset(keys(local.secret_values)))
  secret_id = "${var.name_prefix}-${each.key}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "this" {
  for_each    = nonsensitive(toset(keys(local.secret_values)))
  secret      = google_secret_manager_secret.this[each.key].id
  secret_data = local.secret_values[each.key]
}
