import boto3

ec2 = boto3.client("ec2", region_name="ap-south-1")
response = ec2.describe_instance()

for reservation in response["Reservations"]:
    for instance in reservation["Instances"]:
        print(
            f"Instance ID: {instance['InstanceId']}, "
            f"State: {instance['State']['Name']}, "
            f"Type: {instance['InstanceType']}"
        )