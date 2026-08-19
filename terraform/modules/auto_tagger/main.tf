# -----------------------------------------------------------------------------
# Auto-Tagger Module
# Deploys two Lambda functions and the EventBridge rules/pipes that invoke them:
#
#   1. event_tagger   – triggered on CloudTrail "Create*" API calls (real-time)
#   2. bulk_tagger    – triggered on a cron schedule (catch existing resources)
# -----------------------------------------------------------------------------

locals {
  name_prefix    = "auto-tagger-${var.environment}"
  mandatory_tags = jsonencode(var.mandatory_tags)
  dry_run_str    = var.dry_run ? "true" : "false"

  # Shared environment variables for both Lambdas
  lambda_env_vars = {
    MANDATORY_TAGS = local.mandatory_tags
    DRY_RUN        = local.dry_run_str
    TARGET_REGION  = var.aws_region
  }

  # Additional env for bulk tagger
  bulk_lambda_env_vars = merge(local.lambda_env_vars, {
    SERVICES = var.target_services
  })
}

# -----------------------------------------------------------------------------
# Archive the Python source into a zip for Lambda deployment
# -----------------------------------------------------------------------------

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = var.lambda_source_dir
  output_path = "${path.module}/lambda_package.zip"
}

# -----------------------------------------------------------------------------
# IAM Role for Lambda functions
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    sid     = "LambdaAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${local.name_prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Name = "${local.name_prefix}-lambda-role"
  }
}

resource "aws_iam_policy" "auto_tagger" {
  name        = "${local.name_prefix}-policy"
  description = "Permissions required by the auto-tagger Lambda functions."
  policy      = file("${path.root}/policies/identity/lambda-auto-tagger.json")

  tags = {
    Name = "${local.name_prefix}-policy"
  }
}

resource "aws_iam_role_policy_attachment" "auto_tagger" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.auto_tagger.arn
}

# -----------------------------------------------------------------------------
# CloudWatch Log Groups (explicit so retention is managed by Terraform)
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "event_tagger" {
  name              = "/aws/lambda/${local.name_prefix}-event-tagger"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.name_prefix}-event-tagger-logs"
  }
}

resource "aws_cloudwatch_log_group" "bulk_tagger" {
  name              = "/aws/lambda/${local.name_prefix}-bulk-tagger"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.name_prefix}-bulk-tagger-logs"
  }
}

# -----------------------------------------------------------------------------
# Lambda — Event Tagger (real-time, triggered by EventBridge / CloudTrail)
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "event_tagger" {
  function_name    = "${local.name_prefix}-event-tagger"
  description      = "Automatically tags newly created AWS resources via CloudTrail events."
  role             = aws_iam_role.lambda_exec.arn
  handler          = "event_tagger.lambda_handler"
  runtime          = var.lambda_runtime
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = local.lambda_env_vars
  }

  depends_on = [
    aws_cloudwatch_log_group.event_tagger,
    aws_iam_role_policy_attachment.auto_tagger,
  ]

  tags = {
    Name = "${local.name_prefix}-event-tagger"
  }
}

# -----------------------------------------------------------------------------
# Lambda — Bulk Tagger (scheduled, catches existing / missed resources)
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "bulk_tagger" {
  function_name    = "${local.name_prefix}-bulk-tagger"
  description      = "Scans existing AWS resources and applies missing mandatory tags."
  role             = aws_iam_role.lambda_exec.arn
  handler          = "bulk_tagger.lambda_handler"
  runtime          = var.lambda_runtime
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = local.bulk_lambda_env_vars
  }

  depends_on = [
    aws_cloudwatch_log_group.bulk_tagger,
    aws_iam_role_policy_attachment.auto_tagger,
  ]

  tags = {
    Name = "${local.name_prefix}-bulk-tagger"
  }
}

# -----------------------------------------------------------------------------
# EventBridge — CloudTrail rule for real-time tagging of NEW resources
# Listens for Create* / Run* / Allocate* / Copy* API calls across key services.
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "resource_created" {
  name        = "${local.name_prefix}-resource-created"
  description = "Fires on AWS resource creation events to trigger real-time auto-tagging."

  event_pattern = jsonencode({
    source      = ["aws.ec2", "aws.s3", "aws.rds", "aws.lambda",
                   "aws.dynamodb", "aws.ecs", "aws.eks",
                   "aws.sns", "aws.sqs", "aws.kms"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventName = [
        # EC2
        "RunInstances", "CreateVolume", "CreateSnapshot", "CopySnapshot",
        "CreateImage", "CopyImage", "CreateSecurityGroup", "CreateVpc",
        "CreateSubnet", "CreateRouteTable", "CreateInternetGateway",
        "CreateNatGateway", "CreateNetworkInterface", "CreateKeyPair",
        "AllocateAddress",
        # S3
        "CreateBucket",
        # RDS
        "CreateDBInstance", "RestoreDBInstanceFromDBSnapshot",
        "RestoreDBInstanceToPointInTime",
        "CreateDBCluster", "RestoreDBClusterFromSnapshot",
        # Lambda
        "CreateFunction20150331",
        # DynamoDB
        "CreateTable",
        # ECS
        "CreateCluster", "CreateService",
        # EKS
        "CreateCluster",
        # SNS
        "CreateTopic",
        # SQS
        "CreateQueue",
        # KMS
        "CreateKey"
      ]
      errorCode = [{ "exists" = false }]
    }
  })

  tags = {
    Name = "${local.name_prefix}-resource-created"
  }
}

resource "aws_cloudwatch_event_target" "event_tagger" {
  rule      = aws_cloudwatch_event_rule.resource_created.name
  target_id = "EventTaggerLambda"
  arn       = aws_lambda_function.event_tagger.arn
}

resource "aws_lambda_permission" "allow_eventbridge_event_tagger" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.event_tagger.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.resource_created.arn
}

# -----------------------------------------------------------------------------
# EventBridge — Scheduled rule for bulk tagger (cron)
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "bulk_tagger_schedule" {
  name                = "${local.name_prefix}-bulk-schedule"
  description         = "Scheduled trigger for the bulk auto-tagger Lambda."
  schedule_expression = var.bulk_tagger_schedule

  tags = {
    Name = "${local.name_prefix}-bulk-schedule"
  }
}

resource "aws_cloudwatch_event_target" "bulk_tagger" {
  rule      = aws_cloudwatch_event_rule.bulk_tagger_schedule.name
  target_id = "BulkTaggerLambda"
  arn       = aws_lambda_function.bulk_tagger.arn
}

resource "aws_lambda_permission" "allow_eventbridge_bulk_tagger" {
  statement_id  = "AllowScheduledInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.bulk_tagger.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.bulk_tagger_schedule.arn
}
