provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "Terraform-IAM-Lab"
      Environment = var.environment
      Owner       = "DevOps"
    }
  }
}