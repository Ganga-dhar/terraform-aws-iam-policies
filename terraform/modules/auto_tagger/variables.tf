variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
}

variable "aws_region" {
  description = "AWS region where resources will be deployed."
  type        = string
  default     = "ap-south-1"
}

variable "mandatory_tags" {
  description = "Map of tag key/value pairs that must exist on every resource."
  type        = map(string)
  default = {
    Project     = "Terraform-IAM-Lab"
    Environment = "dev"
    Owner       = "DevOps"
  }
}

variable "dry_run" {
  description = "When true, Lambda logs what it would tag but makes no changes."
  type        = bool
  default     = false
}

variable "lambda_source_dir" {
  description = "Path (relative to the Terraform root) to the Python source directory."
  type        = string
  default     = "../python-boto3-automations/auto_tagger"
}

variable "lambda_runtime" {
  description = "Python runtime for both Lambda functions."
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout" {
  description = "Lambda execution timeout in seconds."
  type        = number
  default     = 300
}

variable "lambda_memory" {
  description = "Lambda memory allocation in MB."
  type        = number
  default     = 256
}

variable "bulk_tagger_schedule" {
  description = "EventBridge Scheduler cron expression for the bulk tagger (UTC)."
  type        = string
  # Default: every day at 01:00 UTC
  default = "cron(0 1 * * ? *)"
}

variable "target_services" {
  description = "Comma-separated list of AWS services the bulk tagger will scan. Leave empty for all."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 14
}
