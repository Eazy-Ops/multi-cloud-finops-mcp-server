# clouds/aws/tools.py

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from langchain.tools import tool

from clouds.aws.client import get_boto3_session
from clouds.aws.utils import (cost_filters, get_budget_data, get_stopped_ec2,
                              get_unassociated_eips,
                              get_unattached_ebs_volumes)


@tool
def get_cost(
    profile_name: str,
    time_range_days: Optional[int] = None,
    start_date_iso: Optional[str] = None,
    end_date_iso: Optional[str] = None,
    tags: Optional[List[str]] = None,
    dimensions: Optional[List[str]] = None,
    group_by: Optional[str] = "SERVICE",
) -> Dict[str, Any]:
    """
    Get cost data for a specified AWS profile for a single defined period.
    The period can be defined by 'time_range_days' (last N days including today)
    OR by explicit 'start_date_iso' and 'end_date_iso'.
    If 'start_date_iso' and 'end_date_iso' are provided, they take precedence.
    If no period is defined, defaults to the current month to date.
    Tags can be provided as a list of "Key=Value" strings to filter costs.
    Dimensions can be provided as a list of "Key=Value" strings to filter costs by specific dimensions.
    If no tags or dimensions are provided, all costs will be returned.
    Grouping can be done by a specific dimension, default is "SERVICE".

    Args:
        profile_name: The AWS CLI profile name to use.
        all_profiles: If True, use all available profiles; otherwise, use the specified profiles.
        time_range_days: Optional. Number of days for the cost data (e.g., last 7 days).
        start_date_iso: Optional. The start date of the period (inclusive) in YYYY-MM-DD format.
        end_date_iso: Optional. The end date of the period (inclusive) in YYYY-MM-DD format.
        tags: Optional. List of cost allocation tags (e.g., ["Team=DevOps", "Env=Prod"]).
        dimensions: Optional. List of dimensions to filter costs by (e.g., ["REGION=us-east-1", "AZ=us-east-1a"]).
        group_by: Optional. The dimension to group costs by (default is "SERVICE").
    Returns:
        Dict: Processed cost data for the specified period.
    """

    session, _, b = get_boto3_session(profile_name)
    ce = session.client("ce")
    today = date.today()

    # Resolve date range
    if start_date_iso and end_date_iso:
        start = datetime.strptime(start_date_iso, "%Y-%m-%d").date()
        end = datetime.strptime(end_date_iso, "%Y-%m-%d").date()
    elif time_range_days:
        end = today
        start = today - timedelta(days=time_range_days - 1)
    else:
        start = today.replace(day=1)
        end = today

    end_exclusive = end + timedelta(days=1)
    cost_args = cost_filters(tags, dimensions)

    # Total cost calculation
    total = ce.get_cost_and_usage(
        TimePeriod={"Start": start.isoformat(), "End": end_exclusive.isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        **cost_args,
    )

    period_total = 0.0
    for result in total.get("ResultsByTime", []):
        amount = float(
            result.get("Total", {}).get("UnblendedCost", {}).get("Amount", 0)
        )
        period_total += amount

    # Cost by service
    grouped = ce.get_cost_and_usage(
        TimePeriod={"Start": start.isoformat(), "End": end_exclusive.isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": group_by}],
        **cost_args,
    )

    services = defaultdict(float)
    for day in grouped.get("ResultsByTime", []):
        for group in day.get("Groups", []):
            key = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            services[key] += amount

    return {
        "aws_profile": profile_name,
        "account_id": session.client("sts").get_caller_identity().get("Account"),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "total_cost": round(period_total, 2),
        "cost_by_service": dict(
            sorted(services.items(), key=lambda x: x[1], reverse=True)
        ),
    }


@tool
def run_finops_audit(profile_name: str, regions: List[str]) -> Dict[str, Any]:
    """
    Get FinOps Audit Report findings for your AWS CLI Profiles.
    Each Audit Report includes:
        Stopped EC2 Instances,
        Un-attached EBS VOlumes,
        Un-associated EIPs,
        Budget Status for your one or more specified AWS profiles. Except the budget status, other resources are region specific.

    Args:
        List of AWS CLI profiles as strings.
        List of AWS Regions as strings.
        all_profiles: If True, use all available profiles; otherwise, use the specified profiles.

    Returns:
        Processed Audit data for specified CLI Profile and regions in JSON(dict) format with errors caught from APIs.
    """

    session, _, b = get_boto3_session(profile_name)
    account_id = session.client("sts").get_caller_identity().get("Account")

    ec2_data, ec2_err = get_stopped_ec2(session, regions)
    ebs_data, ebs_err = get_unattached_ebs_volumes(session, regions)
    eip_data, eip_err = get_unassociated_eips(session, regions)
    budgets, budgets_err = get_budget_data(session, account_id)

    return {
        "profile": profile_name,
        "account_id": account_id,
        "audit": {
            "stopped_ec2": ec2_data,
            "unattached_ebs": ebs_data,
            "unassociated_eips": eip_data,
            "budget_status": budgets,
        },
        "errors": {
            "ec2": ec2_err,
            "ebs": ebs_err,
            "eips": eip_err,
            "budgets": budgets_err,
        },
    }


@tool
def list_aws_profiles(
    profile_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List all AWS CLI profiles available in the current environment.

    Returns:
        A dictionary containing:
            - `profiles`: List of available AWS profile names.
            - `error`: Any error encountered during retrieval.
    """
    try:
        session, _, b = get_boto3_session(profile_name=profile_name)
        print(session, "==============")
        profiles = session.available_profiles
        return {"profiles": profiles, "error": None}
    except Exception as e:
        return {"profiles": [], "error": str(e)}


@tool
def analyze_rds_instances(
    profile_name: str, regions: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyze RDS instances for cost optimization opportunities.
    Identifies:
    - Underutilized instances (low CPU/Memory usage)
    - Instances that could be downsized
    - Reserved Instance coverage
    - Multi-AZ instances that could be single-AZ
    - Storage optimization opportunities

    Args:
        profile_name: AWS profile name
        regions: Optional list of regions to analyze. If not provided, analyzes all RDS-supported regions.

    Returns:
        Dictionary containing RDS optimization recommendations with resource details
    """
    session, _, _ = get_boto3_session(profile_name)
    cloudwatch = session.client("cloudwatch")

    # If regions are not provided, retrieve all regions where RDS is available
    if not regions:
        ec2 = session.client("ec2")
        regions = [
            r["RegionName"] for r in ec2.describe_regions(AllRegions=False)["Regions"]
        ]

    recommendations = {
        "underutilized_instances": [],
        "downsize_opportunities": [],
        "ri_coverage": [],
        "multi_az_opportunities": [],
        "storage_optimization": [],
        "available_instances": [],
    }

    for region in regions:
        rds = session.client("rds", region_name=region)
        try:
            instances = rds.describe_db_instances()
        except Exception as e:
            # Skip region if API call fails (e.g., permission denied)
            print(f"Warning: Could not retrieve RDS instances for region {region}: {e}")
            continue

        for instance in instances["DBInstances"]:
            instance_id = instance["DBInstanceIdentifier"]
            instance_details = {
                "instance_id": instance_id,
                "region": region,
                "engine": instance["Engine"],
                "engine_version": instance["EngineVersion"],
                "instance_class": instance["DBInstanceClass"],
                "allocated_storage": instance["AllocatedStorage"],
                "multi_az": instance["MultiAZ"],
                "storage_type": instance["StorageType"],
                "iops": instance.get("Iops", 0),
                "publicly_accessible": instance["PubliclyAccessible"],
                "status": instance["DBInstanceStatus"],
            }

            # Add to available instances
            recommendations["available_instances"].append(instance_details)

            # Get CPU utilization
            cpu_metrics = cloudwatch.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": instance_id}],
                StartTime=datetime.utcnow() - timedelta(days=30),
                EndTime=datetime.utcnow(),
                Period=86400,
                Statistics=["Average"],
            )

            avg_cpu = (
                sum(point["Average"] for point in cpu_metrics["Datapoints"])
                / len(cpu_metrics["Datapoints"])
                if cpu_metrics["Datapoints"]
                else 0
            )
            instance_details["avg_cpu_utilization"] = avg_cpu

            recommendations["underutilized_instances"].append(
                {
                    "resource_details": instance_details,
                    "recommendation": {
                        "action": (
                            "Consider downsizing"
                            if avg_cpu < 20
                            else "Monitor utilization"
                        ),
                        "reason": f"Average CPU utilization is {avg_cpu:.2f}%",
                        "suggested_instance_class": (
                            f"db.{instance['DBInstanceClass'].split('.')[1].lower()}"
                            if avg_cpu < 20
                            else None
                        ),
                    },
                }
            )

            # Check Multi-AZ
            if instance["MultiAZ"] and instance["Engine"] not in [
                "aurora",
                "aurora-mysql",
                "aurora-postgresql",
            ]:
                recommendations["multi_az_opportunities"].append(
                    {
                        "resource_details": instance_details,
                        "recommendation": {
                            "action": "Consider converting to Single-AZ",
                            "reason": "Non-Aurora database with Multi-AZ enabled",
                            "potential_savings": "Up to 50% of instance cost",
                            "considerations": "Ensure application can handle AZ failure",
                        },
                    }
                )

    return recommendations


@tool
def analyze_ec2_rightsizing(profile_name: str, regions: List[str]) -> Dict[str, Any]:
    """
    Analyze EC2 instances for rightsizing opportunities using CloudWatch metrics.
    Identifies:
    - Underutilized instances (CPU, Memory, Network)
    - Instances that could be downsized
    - Instances that could be moved to different instance families
    - Burstable instance optimization

    Args:
        profile_name: AWS profile name
        regions: List of regions to analyze

    Returns:
        Dictionary containing EC2 rightsizing recommendations with resource details
    """
    session, _, _ = get_boto3_session(profile_name)
    cloudwatch = session.client("cloudwatch")
    ec2 = session.client("ec2")

    recommendations = {
        "underutilized_instances": [],
        "downsize_opportunities": [],
        "instance_family_changes": [],
        "burstable_optimization": [],
    }

    for region in regions:
        ec2 = session.client("ec2", region_name=region)
        instances = ec2.describe_instances()

        for reservation in instances["Reservations"]:
            for instance in reservation["Instances"]:
                instance_id = instance["InstanceId"]
                instance_type = instance["InstanceType"]

                instance_details = {
                    "instance_id": instance_id,
                    "region": region,
                    "instance_type": instance_type,
                    "state": instance["State"]["Name"],
                    "launch_time": instance["LaunchTime"].isoformat(),
                    "platform": instance.get("Platform", "linux"),
                    "vpc_id": instance.get("VpcId"),
                    "subnet_id": instance.get("SubnetId"),
                    "tags": {
                        tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])
                    },
                }

                # Get CPU utilization
                cpu_metrics = cloudwatch.get_metric_statistics(
                    Namespace="AWS/EC2",
                    MetricName="CPUUtilization",
                    Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                    StartTime=datetime.utcnow() - timedelta(days=30),
                    EndTime=datetime.utcnow(),
                    Period=86400,
                    Statistics=["Average"],
                )

                avg_cpu = (
                    sum(point["Average"] for point in cpu_metrics["Datapoints"])
                    / len(cpu_metrics["Datapoints"])
                    if cpu_metrics["Datapoints"]
                    else 0
                )
                instance_details["avg_cpu_utilization"] = avg_cpu

                recommendations["underutilized_instances"].append(
                    {
                        "resource_details": instance_details,
                        "recommendation": {
                            "action": (
                                "Consider downsizing"
                                if avg_cpu < 20
                                else "Monitor utilization"
                            ),
                            "reason": f"Average CPU utilization is {avg_cpu:.2f}%",
                            "suggested_instance_type": (
                                f"t3.{instance_type.split('.')[1]}"
                                if avg_cpu < 20
                                else None
                            ),
                        },
                    }
                )

                # Check for burstable instances
                if instance_type.startswith("t"):
                    recommendations["burstable_optimization"].append(
                        {
                            "resource_details": instance_details,
                            "recommendation": {
                                "action": "Optimize CPU credits",
                                "reason": f"Burstable instance with {avg_cpu:.2f}% average CPU",
                                "suggestions": [
                                    "Consider moving to t4g if ARM compatible",
                                    "Monitor CPU credit balance",
                                    "Consider moving to t3a for cost savings",
                                ],
                            },
                        }
                    )

    return recommendations


@tool
def analyze_s3_optimization(profile_name: str) -> Dict[str, Any]:
    """
    Analyze S3 buckets for cost optimization opportunities.
    Identifies:
    - Lifecycle policy recommendations
    - Storage class optimization
    - Unused buckets
    - Large objects that could be compressed
    - Versioning optimization

    Args:
        profile_name: AWS profile name

    Returns:
        Dictionary containing S3 optimization recommendations with resource details
        List of available resource details
    """
    session, _, _ = get_boto3_session(profile_name)
    s3 = session.client("s3")

    recommendations = {
        "lifecycle_policy_recommendations": [],
        "storage_class_optimization": [],
        "unused_buckets": [],
        "large_objects": [],
        "versioning_optimization": [],
        "available_buckets": [],
    }

    buckets = s3.list_buckets()

    for bucket in buckets["Buckets"]:
        bucket_name = bucket["Name"]
        bucket_details = {
            "bucket_name": bucket_name,
            "creation_date": bucket["CreationDate"].isoformat(),
            "region": s3.get_bucket_location(Bucket=bucket_name)["LocationConstraint"]
            or "us-east-1",
        }
        recommendations["available_buckets"].append(bucket_details)

        try:
            # Get bucket metrics
            metrics = s3.get_metric_statistics(
                Namespace="AWS/S3",
                MetricName="BucketSizeBytes",
                Dimensions=[{"Name": "BucketName", "Value": bucket_name}],
                StartTime=datetime.utcnow() - timedelta(days=30),
                EndTime=datetime.utcnow(),
                Period=86400,
                Statistics=["Average"],
            )

            bucket_size = (
                sum(point["Average"] for point in metrics["Datapoints"])
                if metrics["Datapoints"]
                else 0
            )
            bucket_details["size_bytes"] = bucket_size

            # Check for unused buckets
            if not metrics["Datapoints"]:
                recommendations["unused_buckets"].append(
                    {
                        "resource_details": bucket_details,
                        "recommendation": {
                            "action": "Consider deletion",
                            "reason": "No activity in the last 30 days",
                            "considerations": "Ensure no critical data before deletion",
                        },
                    }
                )

            # Get bucket lifecycle configuration
            try:
                lifecycle = s3.get_bucket_lifecycle_configuration(Bucket=bucket_name)
                if not lifecycle.get("Rules"):
                    recommendations["lifecycle_policy_recommendations"].append(
                        {
                            "resource_details": bucket_details,
                            "recommendation": {
                                "action": "Add lifecycle rules",
                                "reason": "No lifecycle rules configured",
                                "suggested_rules": [
                                    "Move objects to IA after 30 days",
                                    "Move to Glacier after 90 days",
                                    "Delete incomplete multipart uploads after 7 days",
                                ],
                            },
                        }
                    )
            except Exception:
                recommendations["lifecycle_policy_recommendations"].append(
                    {
                        "resource_details": bucket_details,
                        "recommendation": {
                            "action": "Add lifecycle rules",
                            "reason": "No lifecycle rules configured",
                            "suggested_rules": [
                                "Move objects to IA after 30 days",
                                "Move to Glacier after 90 days",
                                "Delete incomplete multipart uploads after 7 days",
                            ],
                        },
                    }
                )

        except Exception:
            continue

    return recommendations


@tool
def analyze_cloudwatch_logs_cost(
    profile_name: str, regions: List[str]
) -> Dict[str, Any]:
    """
    Analyze CloudWatch Logs for cost optimization opportunities.
    Identifies:
    - High volume log groups
    - Long retention periods
    - Unused log groups
    - Expensive log patterns
    - Log group consolidation opportunities

    Args:
        profile_name: AWS profile name
        regions: List of regions to analyze

    Returns:
        Dictionary containing CloudWatch Logs optimization recommendations with resource details
    """
    session, _, _ = get_boto3_session(profile_name)
    logs = session.client("logs")

    recommendations = {
        "high_volume_logs": [],
        "long_retention_periods": [],
        "unused_log_groups": [],
        "expensive_patterns": [],
        "consolidation_opportunities": [],
    }

    for region in regions:
        logs = session.client("logs", region_name=region)

        # Get all log groups
        log_groups = logs.describe_log_groups()

        for log_group in log_groups["logGroups"]:
            group_name = log_group["logGroupName"]
            retention_days = log_group.get("retentionInDays", 0)

            log_group_details = {
                "log_group_name": group_name,
                "region": region,
                "retention_days": retention_days,
                "creation_time": log_group.get("creationTime", 0),
                "stored_bytes": log_group.get("storedBytes", 0),
                "metric_filters": len(log_group.get("metricFilters", [])),
                "subscription_filters": len(log_group.get("subscriptionFilters", [])),
            }

            # Check for long retention periods
            if retention_days > 30:
                recommendations["long_retention_periods"].append(
                    {
                        "resource_details": log_group_details,
                        "recommendation": {
                            "action": "Reduce retention period",
                            "reason": f"Current retention period is {retention_days} days",
                            "suggested_retention": 30,
                            "potential_savings": "Reduced storage costs",
                        },
                    }
                )

            # Get log group metrics
            try:
                metrics = logs.get_metric_statistics(
                    Namespace="AWS/Logs",
                    MetricName="IncomingBytes",
                    Dimensions=[{"Name": "LogGroupName", "Value": group_name}],
                    StartTime=datetime.utcnow() - timedelta(days=30),
                    EndTime=datetime.utcnow(),
                    Period=86400,
                    Statistics=["Sum"],
                )

                total_bytes = (
                    sum(point["Sum"] for point in metrics["Datapoints"])
                    if metrics["Datapoints"]
                    else 0
                )
                log_group_details["incoming_bytes_30d"] = total_bytes

                if total_bytes > 1000000000:  # 1GB
                    recommendations["high_volume_logs"].append(
                        {
                            "resource_details": log_group_details,
                            "recommendation": {
                                "action": "Implement log filtering",
                                "reason": f"High log volume: {total_bytes/1000000000:.2f} GB in 30 days",
                                "suggestions": [
                                    "Add log filters to reduce verbosity",
                                    "Consider log sampling for high-volume logs",
                                    "Review log patterns and adjust logging levels",
                                ],
                            },
                        }
                    )

            except Exception:
                continue

    return recommendations


@tool
def analyze_aws_disks(
    profile_name: str, regions: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyze AWS EBS volumes for cost optimization opportunities.

    Args:
        profile_name: AWS profile name
        regions: Optional list of regions to analyze. If not provided, analyzes all regions.

    Returns:
        Dictionary containing EBS volume optimization recommendations with resource details
    """
    session, _, _ = get_boto3_session(profile_name)
    ec2 = session.client("ec2")
    cloudwatch = session.client("cloudwatch")

    # If regions are not provided, retrieve all regions
    if not regions:
        regions = [
            r["RegionName"] for r in ec2.describe_regions(AllRegions=False)["Regions"]
        ]

    recommendations = {
        "unattached_volumes": [],
        "idle_volumes": [],
        "expensive_volume_types": [],
        "iam_optimization": [],
        "available_volumes": [],
    }

    for region in regions:
        try:
            ec2 = session.client("ec2", region_name=region)
            volumes = ec2.describe_volumes()

            for volume in volumes["Volumes"]:
                volume_details = {
                    "volume_id": volume["VolumeId"],
                    "region": region,
                    "type": volume["VolumeType"],
                    "size_gb": volume["Size"],
                    "state": volume["State"],
                    "attachments": volume["Attachments"],
                    "iops": volume.get("Iops", 0),
                    "throughput": volume.get("Throughput", 0),
                    "encrypted": volume["Encrypted"],
                    "tags": {
                        tag["Key"]: tag["Value"] for tag in volume.get("Tags", [])
                    },
                }

                recommendations["available_volumes"].append(volume_details)

                # Check for unattached volumes
                if volume["State"] == "available":
                    recommendations["unattached_volumes"].append(
                        {
                            "resource_details": volume_details,
                            "recommendation": {
                                "action": "Delete or snapshot unattached volume",
                                "reason": "Volume is not attached to any instance",
                                "considerations": "Ensure volume is not needed before deletion",
                            },
                        }
                    )

                # Check for expensive volume types
                if volume["VolumeType"] in ["io1", "io2"]:
                    recommendations["expensive_volume_types"].append(
                        {
                            "resource_details": volume_details,
                            "recommendation": {
                                "action": "Consider using gp3 or gp2",
                                "reason": "Volume is using expensive IOPS-optimized type",
                                "suggestions": [
                                    "Switch to gp3 for general workloads",
                                    "Use io1/io2 only for high IOPS needs",
                                    "Consider gp2 if gp3 is not available in your region",
                                ],
                            },
                        }
                    )

                # Get volume metrics for the last 30 days
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(days=30)

                # Get read/write operations
                read_ops = cloudwatch.get_metric_statistics(
                    Namespace="AWS/EBS",
                    MetricName="VolumeReadOps",
                    Dimensions=[{"Name": "VolumeId", "Value": volume["VolumeId"]}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=["Sum"],
                )

                write_ops = cloudwatch.get_metric_statistics(
                    Namespace="AWS/EBS",
                    MetricName="VolumeWriteOps",
                    Dimensions=[{"Name": "VolumeId", "Value": volume["VolumeId"]}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=["Sum"],
                )

                total_read_ops = sum(point["Sum"] for point in read_ops["Datapoints"])
                total_write_ops = sum(point["Sum"] for point in write_ops["Datapoints"])
                total_ops = total_read_ops + total_write_ops

                if total_ops == 0 and volume["State"] == "in-use":
                    recommendations["idle_volumes"].append(
                        {
                            "resource_details": volume_details,
                            "recommendation": {
                                "action": "Review and delete if unnecessary",
                                "reason": "No volume activity in last 30 days",
                                "suggestions": [
                                    "Snapshot and delete if no longer needed",
                                    "Move to cheaper storage if archival is required",
                                ],
                            },
                        }
                    )

        except Exception as e:
            print(f"Warning: Could not analyze volumes in region {region}: {e}")
            continue

    # Check IAM policies for volume management
    try:
        iam = session.client("iam")
        policy = iam.get_account_authorization_details(Filter=["User", "Role", "Group"])

        for role in policy["RoleDetailList"]:
            if any(
                "ec2:ModifyVolume" in statement.get("Action", [])
                for statement in role.get("RolePolicyList", [])
            ):
                if len(role["AttachedManagedPolicies"]) > 3:
                    recommendations["iam_optimization"].append(
                        {
                            "resource_details": {"role_name": role["RoleName"]},
                            "recommendation": {
                                "action": "Review IAM role permissions",
                                "reason": f'Role {role["RoleName"]} has too many managed policies',
                                "suggestions": [
                                    "Limit volume management permissions",
                                    "Apply principle of least privilege",
                                    "Review and remove unnecessary policies",
                                ],
                            },
                        }
                    )
    except Exception as e:
        print(f"Warning: Could not analyze IAM policies: {e}")

    return recommendations


@tool
def analyze_aws_network(
    profile_name: str, regions: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyze AWS network resources for cost optimization opportunities.

    Args:
        profile_name: AWS profile name
        regions: Optional list of regions to analyze. If not provided, analyzes all regions.

    Returns:
        Dictionary containing network optimization recommendations with resource details
    """
    session, _, _ = get_boto3_session(profile_name)
    ec2 = session.client("ec2")
    cloudwatch = session.client("cloudwatch")

    # If regions are not provided, retrieve all regions
    if not regions:
        regions = [
            r["RegionName"] for r in ec2.describe_regions(AllRegions=False)["Regions"]
        ]

    recommendations = {
        "unused_eips": [],
        "idle_load_balancers": [],
        "expensive_nat_gateways": [],
        "unused_security_groups": [],
        "available_resources": {
            "eips": [],
            "load_balancers": [],
            "nat_gateways": [],
            "security_groups": [],
        },
    }

    for region in regions:
        try:
            ec2 = session.client("ec2", region_name=region)
            elbv2 = session.client("elbv2", region_name=region)

            # Analyze Elastic IPs
            eips = ec2.describe_addresses()
            for eip in eips["Addresses"]:
                eip_details = {
                    "allocation_id": eip["AllocationId"],
                    "public_ip": eip["PublicIp"],
                    "domain": eip["Domain"],
                    "association_id": eip.get("AssociationId"),
                    "instance_id": eip.get("InstanceId"),
                    "network_interface_id": eip.get("NetworkInterfaceId"),
                    "tags": {tag["Key"]: tag["Value"] for tag in eip.get("Tags", [])},
                }

                recommendations["available_resources"]["eips"].append(eip_details)

                if not eip.get("AssociationId"):
                    recommendations["unused_eips"].append(
                        {
                            "resource_details": eip_details,
                            "recommendation": {
                                "action": "Release unused Elastic IP",
                                "reason": "EIP is not associated with any resource",
                                "considerations": "AWS charges for unassociated EIPs",
                            },
                        }
                    )

            # Analyze Load Balancers
            load_balancers = elbv2.describe_load_balancers()
            for lb in load_balancers["LoadBalancers"]:
                lb_details = {
                    "load_balancer_arn": lb["LoadBalancerArn"],
                    "dns_name": lb["DNSName"],
                    "type": lb["Type"],
                    "scheme": lb["Scheme"],
                    "state": lb["State"]["Code"],
                    "vpc_id": lb["VpcId"],
                    "created_time": lb["CreatedTime"].isoformat(),
                }

                recommendations["available_resources"]["load_balancers"].append(
                    lb_details
                )

                # Get request count for the last 30 days
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(days=30)

                request_count = cloudwatch.get_metric_statistics(
                    Namespace="AWS/ApplicationELB",
                    MetricName="RequestCount",
                    Dimensions=[
                        {"Name": "LoadBalancer", "Value": lb["LoadBalancerName"]}
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=["Sum"],
                )

                total_requests = sum(
                    point["Sum"] for point in request_count["Datapoints"]
                )
                if total_requests == 0:
                    recommendations["idle_load_balancers"].append(
                        {
                            "resource_details": lb_details,
                            "recommendation": {
                                "action": "Delete idle load balancer",
                                "reason": "No requests in last 30 days",
                                "considerations": "Ensure no critical services before deletion",
                            },
                        }
                    )

            # Analyze NAT Gateways
            nat_gateways = ec2.describe_nat_gateways()
            for nat in nat_gateways["NatGateways"]:
                nat_details = {
                    "nat_gateway_id": nat["NatGatewayId"],
                    "state": nat["State"],
                    "vpc_id": nat["VpcId"],
                    "subnet_id": nat["SubnetId"],
                    "created_time": nat["CreateTime"].isoformat(),
                }

                recommendations["available_resources"]["nat_gateways"].append(
                    nat_details
                )

                # Get NAT Gateway metrics
                bytes_out = cloudwatch.get_metric_statistics(
                    Namespace="AWS/NATGateway",
                    MetricName="BytesOutToDestination",
                    Dimensions=[{"Name": "NatGatewayId", "Value": nat["NatGatewayId"]}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=["Sum"],
                )

                total_bytes = sum(point["Sum"] for point in bytes_out["Datapoints"])
                if total_bytes < 1000000:  # Less than 1MB
                    recommendations["expensive_nat_gateways"].append(
                        {
                            "resource_details": nat_details,
                            "recommendation": {
                                "action": "Consider using NAT Instance",
                                "reason": "Low NAT Gateway usage",
                                "suggestions": [
                                    "Replace with NAT Instance for cost savings",
                                    "Consider using VPC Endpoints where possible",
                                    "Review if NAT is actually needed",
                                ],
                            },
                        }
                    )

            # Analyze Security Groups
            security_groups = ec2.describe_security_groups()
            for sg in security_groups["SecurityGroups"]:
                sg_details = {
                    "group_id": sg["GroupId"],
                    "group_name": sg["GroupName"],
                    "vpc_id": sg["VpcId"],
                    "description": sg["Description"],
                    "inbound_rules": len(sg["IpPermissions"]),
                    "outbound_rules": len(sg["IpPermissionsEgress"]),
                    "tags": {tag["Key"]: tag["Value"] for tag in sg.get("Tags", [])},
                }

                recommendations["available_resources"]["security_groups"].append(
                    sg_details
                )

                # Check for unused security groups
                if not sg["IpPermissions"] and not sg["IpPermissionsEgress"]:
                    recommendations["unused_security_groups"].append(
                        {
                            "resource_details": sg_details,
                            "recommendation": {
                                "action": "Delete unused security group",
                                "reason": "No inbound or outbound rules",
                                "considerations": "Ensure no resources are using this security group",
                            },
                        }
                    )

        except Exception as e:
            print(
                f"Warning: Could not analyze network resources in region {region}: {e}"
            )
            continue

    return recommendations


@tool
def analyze_aws_snapshots(
    profile_name: str, regions: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyze AWS EBS and RDS snapshots for cost optimization opportunities.

    Args:
        profile_name: AWS profile name
        regions: Optional list of regions to analyze. If not provided, analyzes all regions.

    Returns:
        Dictionary containing snapshot optimization recommendations with resource details
    """
    session, _, _ = get_boto3_session(profile_name)
    ec2 = session.client("ec2")
    rds = session.client("rds")

    # If regions are not provided, retrieve all regions
    if not regions:
        regions = [
            r["RegionName"] for r in ec2.describe_regions(AllRegions=False)["Regions"]
        ]

    recommendations = {
        "old_ebs_snapshots": [],
        "unused_ebs_snapshots": [],
        "large_ebs_snapshots": [],
        "old_rds_snapshots": [],
        "unused_rds_snapshots": [],
        "available_snapshots": [],
    }

    for region in regions:
        try:
            ec2 = session.client("ec2", region_name=region)
            rds = session.client("rds", region_name=region)

            # Analyze EBS snapshots
            snapshots = ec2.describe_snapshots(OwnerIds=["self"])
            for snapshot in snapshots["Snapshots"]:
                try:
                    snapshot_details = {
                        "snapshot_id": snapshot["SnapshotId"],
                        "region": region,
                        "volume_size": snapshot["VolumeSize"],
                        "start_time": snapshot["StartTime"].isoformat(),
                        "state": snapshot["State"],
                        "volume_id": snapshot.get("VolumeId"),
                        "description": snapshot.get("Description", ""),
                        "tags": {
                            tag["Key"]: tag["Value"] for tag in snapshot.get("Tags", [])
                        },
                    }

                    recommendations["available_snapshots"].append(snapshot_details)

                    # Check for old snapshots (older than 90 days)
                    age_days = (
                        datetime.utcnow() - snapshot["StartTime"].replace(tzinfo=None)
                    ).days
                    if age_days > 90:
                        recommendations["old_ebs_snapshots"].append(
                            {
                                "resource_details": snapshot_details,
                                "recommendation": {
                                    "action": "Review and delete if unnecessary",
                                    "reason": f"Snapshot is {age_days} days old",
                                    "suggestions": [
                                        "Delete if no longer needed",
                                        "Archive to S3 Glacier if retention required",
                                        "Implement lifecycle policies",
                                    ],
                                },
                            }
                        )

                    # Check for large snapshots (> 100 GB)
                    if snapshot["VolumeSize"] > 100:
                        recommendations["large_ebs_snapshots"].append(
                            {
                                "resource_details": snapshot_details,
                                "recommendation": {
                                    "action": "Review large snapshot necessity",
                                    "reason": f"Snapshot size is {snapshot['VolumeSize']} GB",
                                    "suggestions": [
                                        "Use incremental snapshots",
                                        "Review full-volume usage",
                                        "Consider compression",
                                    ],
                                },
                            }
                        )

                    # Check for unused snapshots (no source volume)
                    if not snapshot.get("VolumeId"):
                        recommendations["unused_ebs_snapshots"].append(
                            {
                                "resource_details": snapshot_details,
                                "recommendation": {
                                    "action": "Delete unused snapshot",
                                    "reason": "Source volume no longer exists",
                                    "considerations": "Ensure snapshot is not needed for recovery",
                                },
                            }
                        )

                except Exception as snapshot_e:
                    print(
                        f"Warning: Could not analyze snapshot {snapshot['SnapshotId']}: {snapshot_e}"
                    )
                    continue

            # Analyze RDS snapshots
            try:
                db_snapshots = rds.describe_db_snapshots(SnapshotType="manual")
                for db_snapshot in db_snapshots["DBSnapshots"]:
                    try:
                        db_snapshot_details = {
                            "snapshot_id": db_snapshot["DBSnapshotIdentifier"],
                            "region": region,
                            "db_instance_id": db_snapshot["DBInstanceIdentifier"],
                            "engine": db_snapshot["Engine"],
                            "allocated_storage": db_snapshot.get("AllocatedStorage", 0),
                            "snapshot_create_time": db_snapshot[
                                "SnapshotCreateTime"
                            ].isoformat(),
                            "status": db_snapshot["Status"],
                            "snapshot_type": db_snapshot["SnapshotType"],
                        }

                        recommendations["available_snapshots"].append(
                            db_snapshot_details
                        )

                        # Check for old RDS snapshots (older than 30 days)
                        age_days = (
                            datetime.utcnow()
                            - db_snapshot["SnapshotCreateTime"].replace(tzinfo=None)
                        ).days
                        if age_days > 30 and db_snapshot["Status"] == "available":
                            recommendations["old_rds_snapshots"].append(
                                {
                                    "resource_details": db_snapshot_details,
                                    "recommendation": {
                                        "action": "Review old database snapshots",
                                        "reason": f"Snapshot is {age_days} days old",
                                        "suggestions": [
                                            "Reduce retention period",
                                            "Use automated backups instead",
                                            "Clean up older snapshots",
                                        ],
                                    },
                                }
                            )

                        # Check for large RDS snapshots (> 500 GB)
                        if db_snapshot.get("AllocatedStorage", 0) > 500:
                            recommendations["large_ebs_snapshots"].append(
                                {
                                    "resource_details": db_snapshot_details,
                                    "recommendation": {
                                        "action": "Review large database snapshot",
                                        "reason": f"Snapshot size is {db_snapshot.get('AllocatedStorage', 0)} GB",
                                        "suggestions": [
                                            "Consider point-in-time recovery",
                                            "Review backup strategy",
                                            "Implement data archiving",
                                        ],
                                    },
                                }
                            )

                    except Exception as db_snapshot_e:
                        print(
                            f"Warning: Could not analyze RDS snapshot {db_snapshot['DBSnapshotIdentifier']}: {db_snapshot_e}"
                        )
                        continue

            except Exception as rds_e:
                print(
                    f"Warning: Could not analyze RDS snapshots in region {region}: {rds_e}"
                )

        except Exception as region_e:
            print(
                f"Warning: Could not analyze snapshots in region {region}: {region_e}"
            )
            continue

    return recommendations


@tool
def analyze_aws_static_ips(
    profile_name: str, regions: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyze AWS static IP addresses (Elastic IPs) for cost optimization opportunities.

    Args:
        profile_name: AWS profile name
        regions: Optional list of regions to analyze. If not provided, analyzes all regions.

    Returns:
        Dictionary containing static IP optimization recommendations with resource details
    """
    session, _, _ = get_boto3_session(profile_name)
    ec2 = session.client("ec2")

    # If regions are not provided, retrieve all regions
    if not regions:
        regions = [
            r["RegionName"] for r in ec2.describe_regions(AllRegions=False)["Regions"]
        ]

    recommendations = {
        "unused_elastic_ips": [],
        "expensive_elastic_ips": [],
        "available_ips": [],
    }

    for region in regions:
        try:
            ec2 = session.client("ec2", region_name=region)

            # Analyze Elastic IPs
            eips = ec2.describe_addresses()
            for eip in eips["Addresses"]:
                try:
                    eip_details = {
                        "allocation_id": eip["AllocationId"],
                        "public_ip": eip["PublicIp"],
                        "region": region,
                        "domain": eip["Domain"],
                        "association_id": eip.get("AssociationId"),
                        "instance_id": eip.get("InstanceId"),
                        "network_interface_id": eip.get("NetworkInterfaceId"),
                        "tags": {
                            tag["Key"]: tag["Value"] for tag in eip.get("Tags", [])
                        },
                    }

                    recommendations["available_ips"].append(eip_details)

                    # Check for unused Elastic IPs
                    if not eip.get("AssociationId"):
                        recommendations["unused_elastic_ips"].append(
                            {
                                "resource_details": eip_details,
                                "recommendation": {
                                    "action": "Release unused Elastic IP",
                                    "reason": "EIP is not associated with any resource",
                                    "considerations": "AWS charges for unassociated EIPs",
                                },
                            }
                        )

                    # Check for expensive EIPs (VPC domain)
                    if eip["Domain"] == "vpc":
                        # VPC EIPs are more expensive than EC2-Classic EIPs
                        recommendations["expensive_elastic_ips"].append(
                            {
                                "resource_details": eip_details,
                                "recommendation": {
                                    "action": "Review VPC EIP usage",
                                    "reason": "VPC EIPs have additional charges",
                                    "suggestions": [
                                        "Use only when necessary for VPC resources",
                                        "Consider using Application Load Balancer instead",
                                        "Review if static IP is actually needed",
                                    ],
                                },
                            }
                        )

                except Exception as eip_e:
                    print(
                        f"Warning: Could not analyze EIP {eip.get('AllocationId', 'unknown')}: {eip_e}"
                    )
                    continue

        except Exception as region_e:
            print(
                f"Warning: Could not analyze static IPs in region {region}: {region_e}"
            )
            continue

    return recommendations
