locals {
  sid = replace("trimcp-${var.deployment_name}", "_", "-")
}

resource "google_secret_manager_secret" "mongo_uri" {
  secret_id = "${local.sid}-mongo-uri"

  replication {
    auto {}
  }
}

# No secret version here — operators add MongoDB Atlas (or other) URI after deploy (Appendix I.7).
# Example: gcloud secrets versions add trimcp-acme-dev-mongo-uri --data-file=- <<< 'mongodb+srv://...'

output "connection_secret_id" {
  description = "Secret Manager id; populate with MongoDB-compatible connection string post-deploy"
  value       = google_secret_manager_secret.mongo_uri.secret_id
}

output "connection_secret_resource" {
  value = google_secret_manager_secret.mongo_uri.id
}
