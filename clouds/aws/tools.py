# clouds/aws/tools.py

from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from collections import defaultdict
from langchain.tools import tool

from clouds.aws.client import get_boto3_session
from clouds.aws.utils import (
    get_stopped_ec2,
    get_unattached_ebs_volumes,
    get_unassociated_eips,
    get_budget_data,
    cost_filters,
)

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
        amount = float(result.get("Total", {}).get("UnblendedCost", {}).get("Amount", 0))
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
        "cost_by_service": dict(sorted(services.items(), key=lambda x: x[1], reverse=True)),
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
def list_aws_profiles(profile_name: Optional[str] = None,) -> Dict[str, Any]:
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
def analyze_rds_instances(profile_name: str, regions: List[str]) -> Dict[str, Any]:
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
        regions: List of regions to analyze

    Returns:
        Dictionary containing RDS optimization recommendations
    """
    session, _, _ = get_boto3_session(profile_name)
    cloudwatch = session.client('cloudwatch')
    rds = session.client('rds')
    
    recommendations = {
        'underutilized_instances': [],
        'downsize_opportunities': [],
        'ri_coverage': [],
        'multi_az_opportunities': [],
        'storage_optimization': []
    }

    for region in regions:
        rds = session.client('rds', region_name=region)
        instances = rds.describe_db_instances()
        
        for instance in instances['DBInstances']:
            instance_id = instance['DBInstanceIdentifier']
            
            # Get CPU utilization
            cpu_metrics = cloudwatch.get_metric_statistics(
                Namespace='AWS/RDS',
                MetricName='CPUUtilization',
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': instance_id}],
                StartTime=datetime.utcnow() - timedelta(days=30),
                EndTime=datetime.utcnow(),
                Period=86400,
                Statistics=['Average']
            )
            
            avg_cpu = sum(point['Average'] for point in cpu_metrics['Datapoints']) / len(cpu_metrics['Datapoints']) if cpu_metrics['Datapoints'] else 0


            recommendations['underutilized_instances'].append({
                'instance_id': instance_id,
                'region': region,
                'avg_cpu': avg_cpu,
                'instance_class': instance['DBInstanceClass']
            })

            # Check Multi-AZ
            if instance['MultiAZ'] and instance['Engine'] not in ['aurora', 'aurora-mysql', 'aurora-postgresql']:
                recommendations['multi_az_opportunities'].append({
                    'instance_id': instance_id,
                    'region': region,
                    'current_class': instance['DBInstanceClass']
                })

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
        Dictionary containing EC2 rightsizing recommendations
    """
    session, _, _ = get_boto3_session(profile_name)
    cloudwatch = session.client('cloudwatch')
    ec2 = session.client('ec2')
    
    recommendations = {
        'underutilized_instances': [],
        'downsize_opportunities': [],
        'instance_family_changes': [],
        'burstable_optimization': []
    }

    for region in regions:
        ec2 = session.client('ec2', region_name=region)
        instances = ec2.describe_instances()
        
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                instance_type = instance['InstanceType']
                
                # Get CPU utilization
                cpu_metrics = cloudwatch.get_metric_statistics(
                    Namespace='AWS/EC2',
                    MetricName='CPUUtilization',
                    Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                    StartTime=datetime.utcnow() - timedelta(days=30),
                    EndTime=datetime.utcnow(),
                    Period=86400,
                    Statistics=['Average']
                )
                
                avg_cpu = sum(point['Average'] for point in cpu_metrics['Datapoints']) / len(cpu_metrics['Datapoints']) if cpu_metrics['Datapoints'] else 0
                
                if avg_cpu < 20:
                    recommendations['underutilized_instances'].append({
                        'instance_id': instance_id,
                        'region': region,
                        'avg_cpu': avg_cpu,
                        'instance_type': instance_type
                    })
                
                # Check for burstable instances
                if instance_type.startswith('t'):
                    recommendations['burstable_optimization'].append({
                        'instance_id': instance_id,
                        'region': region,
                        'instance_type': instance_type,
                        'avg_cpu': avg_cpu
                    })

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
        Dictionary containing S3 optimization recommendations
    """
    session, _, _ = get_boto3_session(profile_name)
    s3 = session.client('s3')
    
    recommendations = {
        'lifecycle_policy_recommendations': [],
        'storage_class_optimization': [],
        'unused_buckets': [],
        'large_objects': [],
        'versioning_optimization': []
    }

    buckets = s3.list_buckets()
    
    for bucket in buckets['Buckets']:
        bucket_name = bucket['Name']
        
        try:
            # Get bucket metrics
            metrics = s3.get_metric_statistics(
                Namespace='AWS/S3',
                MetricName='BucketSizeBytes',
                Dimensions=[{'Name': 'BucketName', 'Value': bucket_name}],
                StartTime=datetime.utcnow() - timedelta(days=30),
                EndTime=datetime.utcnow(),
                Period=86400,
                Statistics=['Average']
            )
            
            # Check for unused buckets
            if not metrics['Datapoints']:
                recommendations['unused_buckets'].append({
                    'bucket_name': bucket_name,
                    'creation_date': bucket['CreationDate'].isoformat()
                })
            
            # Get bucket lifecycle configuration
            try:
                lifecycle = s3.get_bucket_lifecycle_configuration(Bucket=bucket_name)
                if not lifecycle.get('Rules'):
                    recommendations['lifecycle_policy_recommendations'].append({
                        'bucket_name': bucket_name,
                        'recommendation': 'Add lifecycle rules for cost optimization'
                    })
            except:
                recommendations['lifecycle_policy_recommendations'].append({
                    'bucket_name': bucket_name,
                    'recommendation': 'Add lifecycle rules for cost optimization'
                })
            
        except Exception as e:
            continue

    return recommendations

@tool
def analyze_cloudwatch_logs_cost(profile_name: str, regions: List[str]) -> Dict[str, Any]:
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
        Dictionary containing CloudWatch Logs optimization recommendations
    """
    session, _, _ = get_boto3_session(profile_name)
    logs = session.client('logs')
    
    recommendations = {
        'high_volume_logs': [],
        'long_retention_periods': [],
        'unused_log_groups': [],
        'expensive_patterns': [],
        'consolidation_opportunities': []
    }

    for region in regions:
        logs = session.client('logs', region_name=region)
        
        # Get all log groups
        log_groups = logs.describe_log_groups()
        
        for log_group in log_groups['logGroups']:
            group_name = log_group['logGroupName']
            retention_days = log_group.get('retentionInDays', 0)
            
            # Check for long retention periods
            if retention_days > 30:
                recommendations['long_retention_periods'].append({
                    'log_group': group_name,
                    'retention_days': retention_days,
                    'recommendation': f'Consider reducing retention to 30 days'
                })
            
            # Get log group metrics
            try:
                metrics = logs.get_metric_statistics(
                    Namespace='AWS/Logs',
                    MetricName='IncomingBytes',
                    Dimensions=[{'Name': 'LogGroupName', 'Value': group_name}],
                    StartTime=datetime.utcnow() - timedelta(days=30),
                    EndTime=datetime.utcnow(),
                    Period=86400,
                    Statistics=['Sum']
                )
                
                total_bytes = sum(point['Sum'] for point in metrics['Datapoints']) if metrics['Datapoints'] else 0
                
                if total_bytes > 1000000000:  # 1GB
                    recommendations['high_volume_logs'].append({
                        'log_group': group_name,
                        'total_bytes': total_bytes,
                        'recommendation': 'Consider log filtering or sampling'
                    })
                    
            except Exception as e:
                continue

    return recommendations

