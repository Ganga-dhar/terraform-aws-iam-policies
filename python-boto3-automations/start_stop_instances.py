import boto3

ec2 = boto3.client("ec2")

instance_id = "i-0123456789abcdef0"

#start
ec2.start_instances(InstanceIds=[instance_id])
# Stop
ec2.stop_instances(InstanceIds=[instance_id])

print(f"{instance_id} stopped")