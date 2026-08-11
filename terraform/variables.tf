variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "bucket_name_prefix" {
  type    = string
  default = "terraform-iam-demo"
}

variable "developer_user" {
  type    = string
  default = "developer1"
}