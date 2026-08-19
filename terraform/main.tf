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

module "auto_tagger" {
  source = "./modules/auto_tagger"

  environment = var.environment
  aws_region  = var.aws_region

  mandatory_tags = {
    Project     = "Terraform-IAM-Lab"
    Environment = var.environment
    Owner       = "DevOps"
  }

  dry_run              = var.auto_tagger_dry_run
  bulk_tagger_schedule = var.auto_tagger_schedule
  target_services      = var.auto_tagger_services
  log_retention_days   = var.auto_tagger_log_retention_days
  lambda_source_dir    = "../python-boto3-automations/auto_tagger"
}