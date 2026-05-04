variable "deployment_name" {
  type = string
}

variable "environment" {
  type        = string
  description = "dev | staging | prod — controls log retention"
}

variable "region" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "app_security_group_id" {
  type = string
}

variable "cluster_name_suffix" {
  type = string
}

variable "service_name" {
  type = string
}

variable "container_image" {
  type = string
}

variable "cpu" {
  type = number
}

variable "memory" {
  type = number
}

variable "desired_count" {
  type = number
}

variable "secrets_arns" {
  type        = list(string)
  description = "Secrets Manager ARNs readable by the task role"
}

variable "s3_bucket_arn" {
  type = string
}
