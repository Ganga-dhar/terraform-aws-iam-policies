output "bucket_name" {

  value = module.s3.bucket_name
}

output "developer_username" {

  value = module.iam.user_name
}

output "developer_access_key_id" {

  value = module.iam.access_key_id
}