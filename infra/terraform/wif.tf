# Despliegue desde GitHub Actions sin llaves JSON (Workload Identity Federation).
# Solo se crea si var.github_repository tiene valor ("owner/repo").

locals {
  wif_enabled = var.github_repository != ""
}

resource "google_iam_workload_identity_pool" "github" {
  count                     = local.wif_enabled ? 1 : 0
  workload_identity_pool_id = "${var.name_prefix}-github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = local.wif_enabled ? 1 : 0
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == \"${var.github_repository}\""
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  count        = local.wif_enabled ? 1 : 0
  account_id   = "${var.name_prefix}-deployer"
  display_name = "Despliegue desde GitHub Actions"
}

resource "google_service_account_iam_member" "deployer_wif" {
  count              = local.wif_enabled ? 1 : 0
  service_account_id = google_service_account.deployer[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repository}"
}

resource "google_project_iam_member" "deployer" {
  for_each = local.wif_enabled ? toset(["roles/run.developer", "roles/artifactregistry.writer"]) : toset([])
  project  = var.project_id
  role     = each.value
  member   = google_service_account.deployer[0].member
}

# Para desplegar revisiones que corren con las cuentas de servicio de runtime.
resource "google_service_account_iam_member" "deployer_act_as" {
  for_each = local.wif_enabled ? {
    share_api    = google_service_account.share_api.name
    document_api = google_service_account.document_api.name
    web          = google_service_account.web.name
  } : {}
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer[0].member
}
