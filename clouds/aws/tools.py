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