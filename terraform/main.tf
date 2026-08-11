module "s3" {
  source = "./modules/s3"

  bucket_name_prefix = var.bucket_name_prefix

  developer_user_arn = module.iam.user_arn
}

module "iam" {
  source = "./modules/iam"

  developer_user = var.developer_user

  bucket_arn  = module.s3.bucket_arn
  bucket_name = module.s3.bucket_name
}