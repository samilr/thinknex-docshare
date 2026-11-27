locals {
  project_number = data.google_project.this.number
  # URL determinística de Cloud Run: evita la dependencia circular web <-> share-api.
  web_url = "https://${var.name_prefix}-web-${local.project_number}.${var.region}.run.app"

  share_api_env = {
    ENV                     = "prod"
    LOG_LEVEL               = "INFO"
    RUN_MIGRATIONS          = "false"
    PUBLIC_BASE_URL         = local.web_url
    BUSINESS_TIMEZONE       = var.business_timezone
    FORWARDED_ALLOW_IPS     = "*"
    STORAGE_BACKEND         = "gcs"
    SNAPSHOT_BUCKET         = google_storage_bucket.snapshots.name
    DMS_BASE_URL            = google_cloud_run_v2_service.document_api.uri
    DMS_AUDIENCE            = google_cloud_run_v2_service.document_api.uri
    EMAIL_PROVIDER          = var.resend_api_key != "" ? "resend" : "none"
    EMAIL_FROM              = var.email_from
    SIMULATED_INBOX_ENABLED = tostring(var.simulated_inbox_enabled)
    BOOTSTRAP_ADMIN_EMAIL   = var.bootstrap_admin_email
    DEMO_USERS_ENABLED      = tostring(var.demo_users_enabled)
    SENSITIVITY_LLM_ENABLED = tostring(var.anthropic_api_key != "")
  }
  share_api_secret_env = merge(
    {
      DATABASE_URL             = "database-url"
      JWT_SECRET               = "jwt-secret"
      OTP_SECRET               = "otp-secret"
      DMS_API_KEY              = "dms-api-key"
      BOOTSTRAP_ADMIN_PASSWORD = "admin-password"
      DEMO_USERS_PASSWORD      = "demo-users-password"
    },
    var.resend_api_key != "" ? { RESEND_API_KEY = "resend-api-key" } : {},
    var.anthropic_api_key != "" ? { ANTHROPIC_API_KEY = "anthropic-api-key" } : {},
  )
}

# --------------------------------------------------------------------------- document-api
resource "google_cloud_run_v2_service" "document_api" {
  name                = "${var.name_prefix}-document-api"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL" # protegido por IAM: solo share-api puede invocarlo

  template {
    service_account = google_service_account.document_api.email
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }
    containers {
      image = var.placeholder_image
      ports {
        container_port = 8001
      }
      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true
        startup_cpu_boost = true # arranques en frío más rápidos, sin costo en reposo
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.this["dms-database-url"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "STORAGE_BACKEND"
        value = "gcs"
      }
      env {
        name  = "DMS_BUCKET"
        value = google_storage_bucket.dms.name
      }
      env {
        name  = "DMS_AUTO_SEED"
        value = "true"
      }
      env {
        name = "DMS_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.this["dms-api-key"].secret_id
            version = "latest"
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
  depends_on = [
    google_secret_manager_secret_iam_member.dms,
    google_secret_manager_secret_version.this,
    google_project_iam_member.dms_sql,
    google_sql_database.dms,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "dms_invoker" {
  name     = google_cloud_run_v2_service.document_api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = google_service_account.share_api.member
}

# --------------------------------------------------------------------------- share-api
resource "google_cloud_run_v2_service" "share_api" {
  name                = "${var.name_prefix}-share-api"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.share_api.email
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }
    containers {
      image = var.placeholder_image
      ports {
        container_port = 8000
      }
      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true
        startup_cpu_boost = true # arranques en frío más rápidos, sin costo en reposo
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      dynamic "env" {
        for_each = local.share_api_env
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = local.share_api_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this[env.value].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
  depends_on = [
    google_secret_manager_secret_iam_member.share_api,
    google_secret_manager_secret_version.this,
    google_project_iam_member.share_api_sql,
  ]
}

# --------------------------------------------------------------------------- web (portal)
resource "google_cloud_run_v2_service" "web" {
  name                = "${var.name_prefix}-web"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.web.email
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image = var.placeholder_image
      ports {
        container_port = 8080
      }
      resources {
        limits            = { cpu = "1", memory = "256Mi" }
        cpu_idle          = true
        startup_cpu_boost = true # arranques en frío más rápidos, sin costo en reposo
      }
      env {
        name  = "SHARE_API_URL"
        value = google_cloud_run_v2_service.share_api.uri
      }
      env {
        name  = "DNS_RESOLVER"
        value = "169.254.169.254" # resolver del metadata server en Cloud Run
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
}

# Acceso público: el portal y la API (que tiene su propia autenticación).
resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = {
    web       = google_cloud_run_v2_service.web.name
    share_api = google_cloud_run_v2_service.share_api.name
  }
  name     = each.value
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
