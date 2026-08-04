output "user_name" {
  value = aws_iam_user.developer.name
}

output "user_arn" {
  value = aws_iam_user.developer.arn
}

output "access_key_id" {
  value = aws_iam_access_key.developer.id
}

output "secret_access_key" {
  value     = aws_iam_access_key.developer.secret
  sensitive = true
}