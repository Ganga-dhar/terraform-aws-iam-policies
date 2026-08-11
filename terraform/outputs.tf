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