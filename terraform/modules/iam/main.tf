resource "aws_iam_user" "developer" {

  name = var.developer_user
}

resource "aws_iam_access_key" "developer" {

  user = aws_iam_user.developer.name
}