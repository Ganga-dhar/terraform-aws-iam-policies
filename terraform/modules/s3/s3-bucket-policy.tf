resource "aws_s3_bucket_policy" "this" {

  bucket = aws_s3_bucket.this.id

  policy = templatefile(

    "${path.root}/policies/resourse-based/s3-bucket-policy.json",

    {

      bucket_arn        = aws_s3_bucket.this.arn

      developer_user_arn = var.developer_user_arn

    }

  )

}