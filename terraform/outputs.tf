output "bucket_name" {
  value = module.s3.bucket_name
}

output "bucket_arn" {
  value = module.s3.bucket_arn
}

output "developer_user" {
  value = module.iam.user_name
}

output "developer_user_arn" {
  value = module.iam.user_arn
}

output "developer_access_key" {
  value = module.iam.access_key_id
}

output "developer_secret_key" {
  value     = module.iam.secret_access_key
  sensitive = true
}

# -----------------------------------------------------------------------------
# Auto-Tagger outputs
# -----------------------------------------------------------------------------

output "event_tagger_function_name" {
  description = "Real-time event tagger Lambda name."
  value       = module.auto_tagger.event_tagger_function_name
}

output "bulk_tagger_function_name" {
  description = "Scheduled bulk tagger Lambda name."
  value       = module.auto_tagger.bulk_tagger_function_name
}

output "event_tagger_log_group" {
  description = "CloudWatch log group for the event tagger."
  value       = module.auto_tagger.event_tagger_log_group
}

output "bulk_tagger_log_group" {
  description = "CloudWatch log group for the bulk tagger."
  value       = module.auto_tagger.bulk_tagger_log_group
}

output "event_bridge_rule_arn" {
  description = "EventBridge rule ARN that fires on resource creation events."
  value       = module.auto_tagger.event_bridge_rule_arn
}