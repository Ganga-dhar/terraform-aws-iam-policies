variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "bucket_name_prefix" {
  type    = string
  default = "terraform-iam-demo"
}

variable "developer_user" {
  type    = string
  default = "developer1"
}

# -----------------------------------------------------------------------------
# Auto-Tagger
# -----------------------------------------------------------------------------

variable "auto_tagger_dry_run" {
  description = "When true, the auto-tagger Lambdas will log actions but not apply any tags."
  type        = bool
  default     = false
}

variable "auto_tagger_schedule" {
  description = "EventBridge cron expression for the bulk tagger (UTC). Default: daily at 01:00."
  type        = string
  default     = "cron(0 1 * * ? *)"
}

variable "auto_tagger_services" {
  description = "Comma-separated AWS services for the bulk tagger to scan. Empty = all services."
  type        = string
  default     = ""
}

variable "auto_tagger_log_retention_days" {
  description = "CloudWatch log retention in days for auto-tagger log groups."
  type        = number
  default     = 14
}