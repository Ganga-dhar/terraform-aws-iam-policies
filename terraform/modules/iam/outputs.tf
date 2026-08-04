output "user_name" {
  value = aws_iam_user.developer.name
}

output "access_key_id" {
  value = aws_iam_access_key.developer.id
}

output "policy_arn" {
  value = aws_iam_policy.developer_policy.arn
}

output "user_arn" {
  value = aws_iam_user.developer.arn
}