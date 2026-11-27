locals {
  job_containers = {
    migrate = ["alembic", "upgrade", "head"]
    gc      = ["python", "-m", "app.jobs.gc"]
  }
}

resource "google_cloud_run_v2_job" "share_api" {
  for_each            = local.job_containers
  name                = "${var.name_prefix}-${each.key}"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1
    template {
      service_account = google_service_account.share_api.email
      max_retries     = 1
      timeout         = "600s"
      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.main.connection_name]
        }
      }
      containers {
        image   = var.placeholder_image
        command = each.value
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
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_secret_manager_secret_iam_member.share_api, google_secret_manager_secret_version.this]
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_gc" {
  name     = google_cloud_run_v2_job.share_api["gc"].name
  location = var.region
  role     = "roles/run.invoker"
  member   = google_service_account.scheduler.member
}

resource "google_cloud_scheduler_job" "gc" {
  name      = "${var.name_prefix}-retention-daily"
  region    = var.scheduler_region
  schedule  = "0 4 * * *"
  time_zone = var.business_timezone

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.share_api["gc"].name}:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [google_project_service.apis]
}
