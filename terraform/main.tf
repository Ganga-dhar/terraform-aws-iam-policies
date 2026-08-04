module "s3" {

  source = "./modules/s3"

  bucket_name_prefix = var.bucket_name_prefix
}

module "iam" {

  source = "./modules/iam"

  developer_user = var.developer_user
}