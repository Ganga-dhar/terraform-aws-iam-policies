output "user_name" {

  value = aws_iam_user.developer.name
}

output "access_key_id" {

  value = aws_iam_access_key.developer.id
}