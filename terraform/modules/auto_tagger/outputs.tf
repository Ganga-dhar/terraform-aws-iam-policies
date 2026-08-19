output "event_tagger_function_name" {
  description = "Name of the real-time event tagger Lambda function."
  value       = aws_lambda_function.event_tagger.function_name
}

output "event_tagger_function_arn" {
  description = "ARN of the real-time event tagger Lambda function."
  value       = aws_lambda_function.event_tagger.arn
}

output "bulk_tagger_function_name" {
  description = "Name of the scheduled bulk tagger Lambda function."
  value       = aws_lambda_function.bulk_tagger.function_name
}

output "bulk_tagger_function_arn" {
  description = "ARN of the scheduled bulk tagger Lambda function."
  value       = aws_lambda_function.bulk_tagger.arn
}

output "lambda_exec_role_arn" {
  description = "ARN of the shared IAM execution role used by both Lambda functions."
  value       = aws_iam_role.lambda_exec.arn
}

output "event_tagger_log_group" {
  description = "CloudWatch log group for the event tagger."
  value       = aws_cloudwatch_log_group.event_tagger.name
}

output "bulk_tagger_log_group" {
  description = "CloudWatch log group for the bulk tagger."
  value       = aws_cloudwatch_log_group.bulk_tagger.name
}

output "event_bridge_rule_arn" {
  description = "ARN of the EventBridge rule that triggers the event tagger."
  value       = aws_cloudwatch_event_rule.resource_created.arn
}

output "bulk_tagger_schedule_rule_arn" {
  description = "ARN of the EventBridge scheduled rule for the bulk tagger."
  value       = aws_cloudwatch_event_rule.bulk_tagger_schedule.arn
}
