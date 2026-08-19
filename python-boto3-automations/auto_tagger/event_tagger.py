"""
event_tagger.py
---------------
Lambda function triggered by EventBridge (CloudTrail CreateResource events).
Automatically applies mandatory tags to newly created AWS resources.

Supported resource types:
  - EC2: instances, volumes, snapshots, AMIs, security groups, VPCs,
         subnets, route tables, internet gateways, NAT gateways, ENIs,
         key pairs, EIPs
  - S3 buckets
  - RDS instances and clusters
  - Lambda functions
  - DynamoDB tables
  - ECS clusters and services
  - EKS clusters
  - SNS topics
  - SQS queues
  - KMS keys

Environment variables (set via Terraform):
  MANDATORY_TAGS  – JSON string of key/value pairs to enforce, e.g.
                    '{"Project":"MyApp","Environment":"dev","Owner":"DevOps"}'
  DRY_RUN         – set to "true" to log actions without applying tags
"""

import json
import logging
import os
import re

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_mandatory_tags() -> dict:
    raw = os.environ.get("MANDATORY_TAGS", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("MANDATORY_TAGS is not valid JSON: %s", raw)
        return {}


def _is_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "false").lower() == "true"


def _boto3_tags(tag_dict: dict) -> list:
    """Convert {k: v} → [{"Key": k, "Value": v}] format used by most AWS APIs."""
    return [{"Key": k, "Value": v} for k, v in tag_dict.items()]


def _boto3_tags_str(tag_dict: dict) -> list:
    """Convert {k: v} → [{"Key": k, "Value": v}] with string values."""
    return [{"Key": k, "Value": str(v)} for k, v in tag_dict.items()]


def _log_action(resource_type: str, resource_id: str, tags: dict):
    prefix = "[DRY-RUN] Would tag" if _is_dry_run() else "Tagging"
    logger.info("%s %s %s with %s", prefix, resource_type, resource_id, tags)


# ---------------------------------------------------------------------------
# Per-service tagging functions
# ---------------------------------------------------------------------------

def tag_ec2_resources(resource_ids: list, tags: dict, region: str):
    if not resource_ids:
        return
    ec2 = boto3.client("ec2", region_name=region)
    for rid in resource_ids:
        _log_action("EC2 resource", rid, tags)
    if not _is_dry_run():
        try:
            ec2.create_tags(Resources=resource_ids, Tags=_boto3_tags(tags))
            logger.info("Tagged EC2 resources: %s", resource_ids)
        except ClientError as exc:
            logger.error("Failed to tag EC2 resources %s: %s", resource_ids, exc)


def tag_s3_bucket(bucket_name: str, tags: dict, region: str):
    _log_action("S3 bucket", bucket_name, tags)
    if _is_dry_run():
        return
    s3 = boto3.client("s3", region_name=region)
    try:
        # Preserve existing tags and merge
        existing = {}
        try:
            resp = s3.get_bucket_tagging(Bucket=bucket_name)
            existing = {t["Key"]: t["Value"] for t in resp.get("TagSet", [])}
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchTagSet":
                raise
        merged = {**existing, **tags}
        s3.put_bucket_tagging(
            Bucket=bucket_name,
            Tagging={"TagSet": _boto3_tags(merged)},
        )
        logger.info("Tagged S3 bucket: %s", bucket_name)
    except ClientError as exc:
        logger.error("Failed to tag S3 bucket %s: %s", bucket_name, exc)


def tag_rds_resource(arn: str, tags: dict, region: str):
    _log_action("RDS resource", arn, tags)
    if _is_dry_run():
        return
    rds = boto3.client("rds", region_name=region)
    try:
        rds.add_tags_to_resource(ResourceName=arn, Tags=_boto3_tags(tags))
        logger.info("Tagged RDS resource: %s", arn)
    except ClientError as exc:
        logger.error("Failed to tag RDS resource %s: %s", arn, exc)


def tag_lambda_function(function_arn: str, tags: dict, region: str):
    _log_action("Lambda function", function_arn, tags)
    if _is_dry_run():
        return
    lmb = boto3.client("lambda", region_name=region)
    try:
        lmb.tag_resource(Resource=function_arn, Tags=tags)
        logger.info("Tagged Lambda function: %s", function_arn)
    except ClientError as exc:
        logger.error("Failed to tag Lambda function %s: %s", function_arn, exc)


def tag_dynamodb_table(table_arn: str, tags: dict, region: str):
    _log_action("DynamoDB table", table_arn, tags)
    if _is_dry_run():
        return
    ddb = boto3.client("dynamodb", region_name=region)
    try:
        ddb.tag_resource(ResourceArn=table_arn, Tags=_boto3_tags(tags))
        logger.info("Tagged DynamoDB table: %s", table_arn)
    except ClientError as exc:
        logger.error("Failed to tag DynamoDB table %s: %s", table_arn, exc)


def tag_ecs_resource(cluster_arn: str, tags: dict, region: str):
    _log_action("ECS resource", cluster_arn, tags)
    if _is_dry_run():
        return
    ecs = boto3.client("ecs", region_name=region)
    try:
        ecs.tag_resource(
            resourceArn=cluster_arn,
            tags=[{"key": k, "value": v} for k, v in tags.items()],
        )
        logger.info("Tagged ECS resource: %s", cluster_arn)
    except ClientError as exc:
        logger.error("Failed to tag ECS resource %s: %s", cluster_arn, exc)


def tag_eks_cluster(cluster_arn: str, tags: dict, region: str):
    _log_action("EKS cluster", cluster_arn, tags)
    if _is_dry_run():
        return
    eks = boto3.client("eks", region_name=region)
    try:
        eks.tag_resource(resourceArn=cluster_arn, tags=tags)
        logger.info("Tagged EKS cluster: %s", cluster_arn)
    except ClientError as exc:
        logger.error("Failed to tag EKS cluster %s: %s", cluster_arn, exc)


def tag_sns_topic(topic_arn: str, tags: dict, region: str):
    _log_action("SNS topic", topic_arn, tags)
    if _is_dry_run():
        return
    sns = boto3.client("sns", region_name=region)
    try:
        for k, v in tags.items():
            sns.tag_resource(ResourceArn=topic_arn, Tags=[{"Key": k, "Value": v}])
        logger.info("Tagged SNS topic: %s", topic_arn)
    except ClientError as exc:
        logger.error("Failed to tag SNS topic %s: %s", topic_arn, exc)


def tag_sqs_queue(queue_url: str, tags: dict, region: str):
    _log_action("SQS queue", queue_url, tags)
    if _is_dry_run():
        return
    sqs = boto3.client("sqs", region_name=region)
    try:
        sqs.tag_queue(QueueUrl=queue_url, Tags=tags)
        logger.info("Tagged SQS queue: %s", queue_url)
    except ClientError as exc:
        logger.error("Failed to tag SQS queue %s: %s", queue_url, exc)


def tag_kms_key(key_id: str, tags: dict, region: str):
    _log_action("KMS key", key_id, tags)
    if _is_dry_run():
        return
    kms = boto3.client("kms", region_name=region)
    try:
        kms.tag_resource(KeyId=key_id, Tags=_boto3_tags(tags))
        logger.info("Tagged KMS key: %s", key_id)
    except ClientError as exc:
        logger.error("Failed to tag KMS key %s: %s", key_id, exc)


# ---------------------------------------------------------------------------
# Event dispatcher — maps CloudTrail eventName → tagging action
# ---------------------------------------------------------------------------

# EC2 resource IDs are nested at different response key paths depending on
# the API call. Map eventName → (responseElements path, id key).
_EC2_EVENT_MAP = {
    # Instances
    "RunInstances": ("responseElements.instancesSet.items", "instanceId"),
    # Volumes
    "CreateVolume": ("responseElements", "volumeId"),
    # Snapshots
    "CreateSnapshot": ("responseElements", "snapshotId"),
    "CopySnapshot": ("responseElements", "snapshotId"),
    # Images (AMIs)
    "CreateImage": ("responseElements", "imageId"),
    "CopyImage": ("responseElements", "imageId"),
    # Security groups
    "CreateSecurityGroup": ("responseElements", "groupId"),
    # VPCs
    "CreateVpc": ("responseElements.vpc", "vpcId"),
    # Subnets
    "CreateSubnet": ("responseElements.subnet", "subnetId"),
    # Route tables
    "CreateRouteTable": ("responseElements.routeTable", "routeTableId"),
    # Internet gateways
    "CreateInternetGateway": ("responseElements.internetGateway", "internetGatewayId"),
    # NAT gateways
    "CreateNatGateway": ("responseElements.CreateNatGatewayResponse.natGateway", "natGatewayId"),
    # ENIs
    "CreateNetworkInterface": ("responseElements.networkInterface", "networkInterfaceId"),
    # Key pairs
    "CreateKeyPair": ("responseElements", "keyPairId"),
    # EIPs
    "AllocateAddress": ("responseElements", "allocationId"),
}


def _deep_get(data: dict, dotted_path: str):
    """Walk a dotted key path through nested dicts/lists."""
    parts = dotted_path.split(".")
    node = data
    for part in parts:
        if isinstance(node, list):
            # flatten lists by returning the first item (RunInstances returns a list)
            node = node[0] if node else {}
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _extract_ec2_ids(event_name: str, response_elements: dict) -> list:
    if event_name not in _EC2_EVENT_MAP:
        return []
    path, id_key = _EC2_EVENT_MAP[event_name]
    target = _deep_get(response_elements, path)
    if target is None:
        return []
    if isinstance(target, list):
        return [item[id_key] for item in target if id_key in item]
    if isinstance(target, dict) and id_key in target:
        return [target[id_key]]
    return []


def _handle_event(event_name: str, detail: dict, tags: dict, region: str):
    """Route a single CloudTrail event to the correct tagging function."""
    response = detail.get("responseElements") or {}
    request = detail.get("requestParameters") or {}

    # ---- EC2 ---------------------------------------------------------------
    if event_name in _EC2_EVENT_MAP:
        ids = _extract_ec2_ids(event_name, response)
        if ids:
            tag_ec2_resources(ids, tags, region)
        else:
            logger.warning("Could not extract EC2 IDs for event %s", event_name)
        return

    # ---- S3 ----------------------------------------------------------------
    if event_name == "CreateBucket":
        bucket = request.get("bucketName")
        if bucket:
            tag_s3_bucket(bucket, tags, region)
        return

    # ---- RDS ---------------------------------------------------------------
    if event_name in ("CreateDBInstance", "RestoreDBInstanceFromDBSnapshot",
                      "RestoreDBInstanceToPointInTime"):
        arn = response.get("dBInstanceArn") or response.get("dBInstance", {}).get("dBInstanceArn")
        if arn:
            tag_rds_resource(arn, tags, region)
        return

    if event_name in ("CreateDBCluster", "RestoreDBClusterFromSnapshot"):
        arn = response.get("dBClusterArn") or response.get("dBCluster", {}).get("dBClusterArn")
        if arn:
            tag_rds_resource(arn, tags, region)
        return

    # ---- Lambda ------------------------------------------------------------
    if event_name == "CreateFunction20150331":
        arn = response.get("functionArn") or response.get("functionConfiguration", {}).get("functionArn")
        if arn:
            tag_lambda_function(arn, tags, region)
        return

    # ---- DynamoDB ----------------------------------------------------------
    if event_name == "CreateTable":
        arn = response.get("tableDescription", {}).get("tableArn")
        if arn:
            tag_dynamodb_table(arn, tags, region)
        return

    # ---- ECS ---------------------------------------------------------------
    if event_name == "CreateCluster":
        arn = response.get("cluster", {}).get("clusterArn")
        if arn:
            tag_ecs_resource(arn, tags, region)
        return

    if event_name == "CreateService":
        arn = response.get("service", {}).get("serviceArn")
        if arn:
            tag_ecs_resource(arn, tags, region)
        return

    # ---- EKS ---------------------------------------------------------------
    if event_name == "CreateCluster" and detail.get("eventSource") == "eks.amazonaws.com":
        arn = response.get("cluster", {}).get("arn")
        if arn:
            tag_eks_cluster(arn, tags, region)
        return

    # ---- SNS ---------------------------------------------------------------
    if event_name == "CreateTopic":
        arn = response.get("topicArn")
        if arn:
            tag_sns_topic(arn, tags, region)
        return

    # ---- SQS ---------------------------------------------------------------
    if event_name == "CreateQueue":
        url = response.get("queueUrl")
        if url:
            tag_sqs_queue(url, tags, region)
        return

    # ---- KMS ---------------------------------------------------------------
    if event_name == "CreateKey":
        key_id = response.get("keyMetadata", {}).get("keyId")
        if key_id:
            tag_kms_key(key_id, tags, region)
        return

    logger.info("No tagging handler for event: %s", event_name)


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context):
    """
    Entry point invoked by EventBridge.
    Supports both single CloudTrail events and batched detail arrays.
    """
    mandatory_tags = _get_mandatory_tags()
    if not mandatory_tags:
        logger.warning("MANDATORY_TAGS is empty — nothing to enforce.")
        return {"status": "skipped", "reason": "no mandatory tags configured"}

    logger.info("Received event: %s", json.dumps(event))

    # EventBridge passes CloudTrail detail directly in event["detail"]
    detail = event.get("detail", {})
    event_name = detail.get("eventName", "")
    region = detail.get("awsRegion", os.environ.get("AWS_REGION", "ap-south-1"))

    # Enrich with caller identity as a tag if present
    user_identity = detail.get("userIdentity", {})
    caller = (
        user_identity.get("arn")
        or user_identity.get("userName")
        or user_identity.get("type", "unknown")
    )
    tags_to_apply = {**mandatory_tags, "CreatedBy": caller}

    if not event_name:
        logger.error("No eventName found in detail: %s", detail)
        return {"status": "error", "reason": "missing eventName"}

    _handle_event(event_name, detail, tags_to_apply, region)

    return {"status": "ok", "event": event_name}
