variable "project_id" {
  type = string
}

variable "deployment_name" {
  type = string
}

variable "region" {
  type = string
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "worker_service_account_email" {
  type        = string
  description = "Grant objectAdmin on this bucket only"
}
