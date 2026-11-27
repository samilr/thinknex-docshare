variable "project_id" {
  description = "ID del proyecto GCP"
  type        = string
}

variable "region" {
  description = "Región principal (Santiago por defecto)"
  type        = string
  default     = "southamerica-west1"
}

variable "scheduler_region" {
  description = "Región de Cloud Scheduler (solo dispara el job de retención)"
  type        = string
  default     = "us-central1"
}

variable "name_prefix" {
  description = "Prefijo de los recursos"
  type        = string
  default     = "docshare"
}

variable "sql_tier" {
  description = "Tamaño de Cloud SQL (db-f1-micro alcanza para la demo)"
  type        = string
  default     = "db-f1-micro"
}

variable "deletion_protection" {
  description = "Protege Cloud SQL contra borrado (false en la demo para poder destruirla)"
  type        = bool
  default     = false
}

variable "business_timezone" {
  type    = string
  default = "America/Santiago"
}

# --- Usuarios iniciales -----------------------------------------------------------------
variable "bootstrap_admin_email" {
  type    = string
  default = "admin@thinknex.example"
}

variable "demo_users_enabled" {
  description = "Crea ana/bruno (SHARER) y carla (AUDITOR) con datos ficticios"
  type        = bool
  default     = true
}

variable "simulated_inbox_enabled" {
  description = "Bandeja simulada visible para ADMIN (SOLO DEMO: guarda enlaces y OTP en claro)"
  type        = bool
  default     = true
}

# --- Integraciones opcionales -------------------------------------------------------------
variable "resend_api_key" {
  description = "Si se define, el canal email envía correos reales vía Resend"
  type        = string
  default     = ""
  sensitive   = true
}

variable "email_from" {
  type    = string
  default = "ThinkNex Docs (demo) <onboarding@resend.dev>"
}

variable "anthropic_api_key" {
  description = "Si se define, activa el chequeo de sensibilidad asistido por LLM"
  type        = string
  default     = ""
  sensitive   = true
}

variable "github_repository" {
  description = "owner/repo para desplegar desde GitHub Actions con WIF (vacío = no se crea)"
  type        = string
  default     = ""
}

variable "placeholder_image" {
  description = "Imagen inicial de Cloud Run; scripts/deploy.sh la reemplaza por las reales"
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
