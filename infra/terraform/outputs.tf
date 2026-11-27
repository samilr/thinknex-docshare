output "web_url" {
  description = "URL pública del portal"
  value       = google_cloud_run_v2_service.web.uri
}

output "web_url_deterministic" {
  description = "URL determinística del portal (usada en los enlaces enviados)"
  value       = local.web_url
}

output "share_api_url" {
  value = google_cloud_run_v2_service.share_api.uri
}

output "document_api_url" {
  value = google_cloud_run_v2_service.document_api.uri
}

output "registry" {
  value = local.registry
}

output "region" {
  value = var.region
}

output "services" {
  value = {
    web          = google_cloud_run_v2_service.web.name
    share_api    = google_cloud_run_v2_service.share_api.name
    document_api = google_cloud_run_v2_service.document_api.name
    migrate_job  = google_cloud_run_v2_job.share_api["migrate"].name
    gc_job       = google_cloud_run_v2_job.share_api["gc"].name
  }
}

output "sql_connection_name" {
  value = google_sql_database_instance.main.connection_name
}

output "bootstrap_admin_email" {
  value = var.bootstrap_admin_email
}

output "admin_password" {
  value     = random_password.admin.result
  sensitive = true
}

output "demo_users_password" {
  value     = random_password.demo_users.result
  sensitive = true
}

output "github_wif_provider" {
  value = local.wif_enabled ? google_iam_workload_identity_pool_provider.github[0].name : null
}

output "github_deployer_service_account" {
  value = local.wif_enabled ? google_service_account.deployer[0].email : null
}

output "project_id" {
  value = var.project_id
}

output "snapshot_bucket" {
  value = google_storage_bucket.snapshots.name
}

output "dms_bucket" {
  value = google_storage_bucket.dms.name
}
