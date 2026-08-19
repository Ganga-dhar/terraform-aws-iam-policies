"""
bulk_tagger.py
--------------
Lambda function (or standalone script) that scans EXISTING AWS resources
and applies any missing mandatory tags.

Can be invoked:
  1. Directly as a Lambda (scheduled via EventBridge Scheduler / cron rule)
  2. Locally: python bulk_tagger.py

Environment variables:
  MANDATORY_TAGS  – JSON string, e.g. '{"Project":"MyApp","Environment":"dev","Owner":"DevOps"}'
  TARGET_REGION   – AWS region to scan (defaults to AWS_REGION / ap-south-1)
  DRY_RUN         – "true" to log without applying changes
  SERVICES        – comma-separated list of services to scan; omit to scan all.
                    Valid values: ec2,s3,rds,lambda,dynamodb,ecs,eks,sns,sqs,kms

Returns a summary dict with counts: scanned, already_tagged, updated, failed.
"""

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _get_mandatory_tags() -> dict:
    raw = os.environ.get("MANDATORY_TAGS", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("MANDATORY_TAGS is not valid JSON: %s", raw)
        return {}


def _get_region() -> str:
    return os.environ.get("TARGET_REGION", os.environ.get("AWS_REGION", "ap-south-1"))


def _is_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "false").lower() == "true"


def _target_services() -> set:
    raw = os.environ.get("SERVICES", "")
    if not raw:
        return {"ec2", "s3", "rds", "lambda", "dynamodb", "ecs", "eks", "sns", "sqs", "kms"}
    return {s.strip().lower() for s in raw.split(",")}


def _missing_tags(existing: dict, required: dict) -> dict:
    """Return only the tags from `required` that are absent in `existing`."""
    return {k: v for k, v in required.items() if k not in existing}


def _to_kv(tag_list: list) -> dict:
    """Convert [{"Key":k,"Value":v}] → {k: v}."""
    return {t["Key"]: t["Value"] for t in tag_list if "Key" in t}


def _boto3_tags(tag_dict: dict) -> list:
    return [{"Key": k, "Value": v} for k, v in tag_dict.items()]


# ---------------------------------------------------------------------------
# Result accumulator
# ---------------------------------------------------------------------------

class Stats:
    def __init__(self):
        self.scanned = 0
        self.already_tagged = 0
        self.updated = 0
        self.failed = 0

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "already_tagged": self.already_tagged,
            "updated": self.updated,
            "failed": self.failed,
        }


# ---------------------------------------------------------------------------
# Per-service scanners
# ---------------------------------------------------------------------------

def scan_ec2(mandatory: dict, region: str, stats: Stats):
    ec2 = boto3.client("ec2", region_name=region)
    resource_types = [
        ("describe_instances",       _iter_ec2_instances),
        ("describe_volumes",         _iter_ec2_volumes),
        ("describe_snapshots",       _iter_ec2_snapshots),
        ("describe_security_groups", _iter_ec2_generic("SecurityGroups", "GroupId")),
        ("describe_vpcs",            _iter_ec2_generic("Vpcs", "VpcId")),
        ("describe_subnets",         _iter_ec2_generic("Subnets", "SubnetId")),
    ]
    for method_name, iterator in resource_types:
        try:
            paginator_name = method_name  # same name for paginators
            paginator = ec2.get_paginator(paginator_name)
            for page in paginator.paginate():
                for rid, existing_tags in iterator(page):
                    _process_resource(
                        apply_fn=lambda missing, rid=rid: ec2.create_tags(
                            Resources=[rid], Tags=_boto3_tags(missing)
                        ),
                        resource_id=rid,
                        resource_type="EC2",
                        existing_tags=existing_tags,
                        mandatory=mandatory,
                        stats=stats,
                    )
        except ClientError as exc:
            logger.error("EC2 scan error (%s): %s", method_name, exc)
            stats.failed += 1


def _iter_ec2_instances(page: dict):
    for reservation in page.get("Reservations", []):
        for inst in reservation.get("Instances", []):
            yield inst["InstanceId"], _to_kv(inst.get("Tags") or [])


def _iter_ec2_volumes(page: dict):
    for vol in page.get("Volumes", []):
        yield vol["VolumeId"], _to_kv(vol.get("Tags") or [])


def _iter_ec2_snapshots(page: dict):
    for snap in page.get("Snapshots", []):
        yield snap["SnapshotId"], _to_kv(snap.get("Tags") or [])


def _iter_ec2_generic(collection_key: str, id_key: str):
    def _iter(page: dict):
        for item in page.get(collection_key, []):
            yield item[id_key], _to_kv(item.get("Tags") or [])
    return _iter


# -- S3 -----------------------------------------------------------------------

def scan_s3(mandatory: dict, region: str, stats: Stats):
    s3 = boto3.client("s3", region_name=region)
    try:
        buckets = s3.list_buckets().get("Buckets", [])
    except ClientError as exc:
        logger.error("S3 list_buckets error: %s", exc)
        stats.failed += 1
        return

    for bucket in buckets:
        name = bucket["Name"]
        stats.scanned += 1
        existing = {}
        try:
            resp = s3.get_bucket_tagging(Bucket=name)
            existing = _to_kv(resp.get("TagSet", []))
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchTagSet":
                logger.error("S3 get_bucket_tagging error for %s: %s", name, exc)
                stats.failed += 1
                continue

        missing = _missing_tags(existing, mandatory)
        if not missing:
            stats.already_tagged += 1
            continue

        logger.info("%s S3 bucket %s — adding tags: %s",
                    "[DRY-RUN]" if _is_dry_run() else "Updating", name, missing)
        if _is_dry_run():
            stats.updated += 1
            continue
        try:
            merged = {**existing, **missing}
            s3.put_bucket_tagging(Bucket=name, Tagging={"TagSet": _boto3_tags(merged)})
            stats.updated += 1
        except ClientError as exc:
            logger.error("S3 tag error for %s: %s", name, exc)
            stats.failed += 1


# -- RDS ----------------------------------------------------------------------

def scan_rds(mandatory: dict, region: str, stats: Stats):
    rds = boto3.client("rds", region_name=region)
    for describe_fn, arn_key, collection in [
        (rds.describe_db_instances, "DBInstanceArn", "DBInstances"),
        (rds.describe_db_clusters,  "DBClusterArn",  "DBClusters"),
    ]:
        try:
            paginator = rds.get_paginator(describe_fn.__name__)
            for page in paginator.paginate():
                for resource in page.get(collection, []):
                    arn = resource[arn_key]
                    existing = _to_kv(resource.get("TagList") or [])
                    _process_resource(
                        apply_fn=lambda missing, arn=arn: rds.add_tags_to_resource(
                            ResourceName=arn, Tags=_boto3_tags(missing)
                        ),
                        resource_id=arn,
                        resource_type="RDS",
                        existing_tags=existing,
                        mandatory=mandatory,
                        stats=stats,
                    )
        except ClientError as exc:
            logger.error("RDS scan error: %s", exc)
            stats.failed += 1


# -- Lambda -------------------------------------------------------------------

def scan_lambda(mandatory: dict, region: str, stats: Stats):
    lmb = boto3.client("lambda", region_name=region)
    try:
        paginator = lmb.get_paginator("list_functions")
        for page in paginator.paginate():
            for fn in page.get("Functions", []):
                arn = fn["FunctionArn"]
                try:
                    tag_resp = lmb.list_tags(Resource=arn)
                    existing = tag_resp.get("Tags", {})
                except ClientError as exc:
                    logger.error("Lambda list_tags error for %s: %s", arn, exc)
                    stats.failed += 1
                    continue
                _process_resource(
                    apply_fn=lambda missing, arn=arn: lmb.tag_resource(
                        Resource=arn, Tags=missing
                    ),
                    resource_id=arn,
                    resource_type="Lambda",
                    existing_tags=existing,
                    mandatory=mandatory,
                    stats=stats,
                )
    except ClientError as exc:
        logger.error("Lambda scan error: %s", exc)
        stats.failed += 1


# -- DynamoDB -----------------------------------------------------------------

def scan_dynamodb(mandatory: dict, region: str, stats: Stats):
    ddb = boto3.client("dynamodb", region_name=region)
    try:
        paginator = ddb.get_paginator("list_tables")
        for page in paginator.paginate():
            for table_name in page.get("TableNames", []):
                try:
                    desc = ddb.describe_table(TableName=table_name)
                    arn = desc["Table"]["TableArn"]
                    tag_resp = ddb.list_tags_of_resource(ResourceArn=arn)
                    existing = _to_kv(tag_resp.get("Tags", []))
                except ClientError as exc:
                    logger.error("DynamoDB describe/tag error for %s: %s", table_name, exc)
                    stats.failed += 1
                    continue
                _process_resource(
                    apply_fn=lambda missing, arn=arn: ddb.tag_resource(
                        ResourceArn=arn, Tags=_boto3_tags(missing)
                    ),
                    resource_id=arn,
                    resource_type="DynamoDB",
                    existing_tags=existing,
                    mandatory=mandatory,
                    stats=stats,
                )
    except ClientError as exc:
        logger.error("DynamoDB scan error: %s", exc)
        stats.failed += 1


# -- ECS ----------------------------------------------------------------------

def scan_ecs(mandatory: dict, region: str, stats: Stats):
    ecs = boto3.client("ecs", region_name=region)
    try:
        paginator = ecs.get_paginator("list_clusters")
        for page in paginator.paginate():
            for cluster_arn in page.get("clusterArns", []):
                try:
                    tag_resp = ecs.list_tags_for_resource(resourceArn=cluster_arn)
                    existing = {t["key"]: t["value"] for t in tag_resp.get("tags", [])}
                except ClientError as exc:
                    logger.error("ECS tag error for %s: %s", cluster_arn, exc)
                    stats.failed += 1
                    continue
                _process_resource(
                    apply_fn=lambda missing, arn=cluster_arn: ecs.tag_resource(
                        resourceArn=arn,
                        tags=[{"key": k, "value": v} for k, v in missing.items()],
                    ),
                    resource_id=cluster_arn,
                    resource_type="ECS",
                    existing_tags=existing,
                    mandatory=mandatory,
                    stats=stats,
                )
    except ClientError as exc:
        logger.error("ECS scan error: %s", exc)
        stats.failed += 1


# -- EKS ----------------------------------------------------------------------

def scan_eks(mandatory: dict, region: str, stats: Stats):
    eks = boto3.client("eks", region_name=region)
    try:
        paginator = eks.get_paginator("list_clusters")
        for page in paginator.paginate():
            for cluster_name in page.get("clusters", []):
                try:
                    desc = eks.describe_cluster(name=cluster_name)
                    cluster = desc["cluster"]
                    arn = cluster["arn"]
                    existing = cluster.get("tags", {})
                except ClientError as exc:
                    logger.error("EKS describe error for %s: %s", cluster_name, exc)
                    stats.failed += 1
                    continue
                _process_resource(
                    apply_fn=lambda missing, arn=arn: eks.tag_resource(
                        resourceArn=arn, tags=missing
                    ),
                    resource_id=arn,
                    resource_type="EKS",
                    existing_tags=existing,
                    mandatory=mandatory,
                    stats=stats,
                )
    except ClientError as exc:
        logger.error("EKS scan error: %s", exc)
        stats.failed += 1


# -- SNS ----------------------------------------------------------------------

def scan_sns(mandatory: dict, region: str, stats: Stats):
    sns = boto3.client("sns", region_name=region)
    try:
        paginator = sns.get_paginator("list_topics")
        for page in paginator.paginate():
            for topic in page.get("Topics", []):
                arn = topic["TopicArn"]
                try:
                    tag_resp = sns.list_tags_for_resource(ResourceArn=arn)
                    existing = _to_kv(tag_resp.get("Tags", []))
                except ClientError as exc:
                    logger.error("SNS tag error for %s: %s", arn, exc)
                    stats.failed += 1
                    continue
                _process_resource(
                    apply_fn=lambda missing, arn=arn: sns.tag_resource(
                        ResourceArn=arn, Tags=_boto3_tags(missing)
                    ),
                    resource_id=arn,
                    resource_type="SNS",
                    existing_tags=existing,
                    mandatory=mandatory,
                    stats=stats,
                )
    except ClientError as exc:
        logger.error("SNS scan error: %s", exc)
        stats.failed += 1


# -- SQS ----------------------------------------------------------------------

def scan_sqs(mandatory: dict, region: str, stats: Stats):
    sqs = boto3.client("sqs", region_name=region)
    try:
        paginator = sqs.get_paginator("list_queues")
        for page in paginator.paginate():
            for url in page.get("QueueUrls", []):
                try:
                    tag_resp = sqs.list_queue_tags(QueueUrl=url)
                    existing = tag_resp.get("Tags", {})
                except ClientError as exc:
                    logger.error("SQS tag error for %s: %s", url, exc)
                    stats.failed += 1
                    continue
                _process_resource(
                    apply_fn=lambda missing, url=url: sqs.tag_queue(
                        QueueUrl=url, Tags=missing
                    ),
                    resource_id=url,
                    resource_type="SQS",
                    existing_tags=existing,
                    mandatory=mandatory,
                    stats=stats,
                )
    except ClientError as exc:
        logger.error("SQS scan error: %s", exc)
        stats.failed += 1


# -- KMS ----------------------------------------------------------------------

def scan_kms(mandatory: dict, region: str, stats: Stats):
    kms = boto3.client("kms", region_name=region)
    try:
        paginator = kms.get_paginator("list_keys")
        for page in paginator.paginate():
            for key in page.get("Keys", []):
                key_id = key["KeyId"]
                try:
                    meta = kms.describe_key(KeyId=key_id)["KeyMetadata"]
                    # Skip AWS-managed keys — they cannot be tagged by customers
                    if meta.get("KeyManager") == "AWS":
                        continue
                    if meta.get("KeyState") in ("PendingDeletion", "Disabled"):
                        continue
                    tag_resp = kms.list_resource_tags(KeyId=key_id)
                    existing = _to_kv(tag_resp.get("Tags", []))
                except ClientError as exc:
                    logger.error("KMS tag error for %s: %s", key_id, exc)
                    stats.failed += 1
                    continue
                _process_resource(
                    apply_fn=lambda missing, kid=key_id: kms.tag_resource(
                        KeyId=kid, Tags=_boto3_tags(missing)
                    ),
                    resource_id=key_id,
                    resource_type="KMS",
                    existing_tags=existing,
                    mandatory=mandatory,
                    stats=stats,
                )
    except ClientError as exc:
        logger.error("KMS scan error: %s", exc)
        stats.failed += 1


# ---------------------------------------------------------------------------
# Generic resource processor
# ---------------------------------------------------------------------------

def _process_resource(
    apply_fn,
    resource_id: str,
    resource_type: str,
    existing_tags: dict,
    mandatory: dict,
    stats: Stats,
):
    stats.scanned += 1
    missing = _missing_tags(existing_tags, mandatory)
    if not missing:
        stats.already_tagged += 1
        return

    logger.info(
        "%s %s %s — adding tags: %s",
        "[DRY-RUN]" if _is_dry_run() else "Updating",
        resource_type,
        resource_id,
        missing,
    )

    if _is_dry_run():
        stats.updated += 1
        return

    try:
        apply_fn(missing)
        stats.updated += 1
    except ClientError as exc:
        logger.error("Failed to tag %s %s: %s", resource_type, resource_id, exc)
        stats.failed += 1


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

_SERVICE_SCANNERS = {
    "ec2":      scan_ec2,
    "s3":       scan_s3,
    "rds":      scan_rds,
    "lambda":   scan_lambda,
    "dynamodb": scan_dynamodb,
    "ecs":      scan_ecs,
    "eks":      scan_eks,
    "sns":      scan_sns,
    "sqs":      scan_sqs,
    "kms":      scan_kms,
}


def lambda_handler(event: dict, context):
    """
    Entry point for scheduled bulk-tagging runs.
    `event` is ignored — configuration comes from environment variables.
    """
    mandatory = _get_mandatory_tags()
    if not mandatory:
        logger.warning("MANDATORY_TAGS is empty — nothing to enforce.")
        return {"status": "skipped", "reason": "no mandatory tags configured"}

    region = _get_region()
    services = _target_services()
    stats = Stats()

    logger.info(
        "Starting bulk tag scan | region=%s | services=%s | dry_run=%s | tags=%s",
        region, sorted(services), _is_dry_run(), mandatory,
    )

    for svc in sorted(services):
        scanner = _SERVICE_SCANNERS.get(svc)
        if not scanner:
            logger.warning("Unknown service '%s' — skipping.", svc)
            continue
        logger.info("Scanning service: %s", svc)
        scanner(mandatory, region, stats)

    summary = stats.as_dict()
    logger.info("Bulk tagging complete: %s", summary)
    return {"status": "ok", "summary": summary}


# ---------------------------------------------------------------------------
# Local execution entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        stream=sys.stdout,
    )
    result = lambda_handler({}, None)
    print("\n=== Result ===")
    print(json.dumps(result, indent=2))
