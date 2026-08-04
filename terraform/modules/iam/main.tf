resource "aws_iam_policy" "developer_policy" {

  name        = "DeveloperS3Policy"
  description = "Developer can upload/download but cannot delete."

  policy = templatefile(
    "${path.root}/policies/identity/developer-policy.json",
    {
      bucket_arn = var.bucket_arn
    }
  )
}

resource "aws_iam_user_policy_attachment" "developer" {

  user       = aws_iam_user.developer.name
  policy_arn = aws_iam_policy.developer_policy.arn
}