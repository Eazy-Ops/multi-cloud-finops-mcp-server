from typing import Any, Dict, List, Optional, Tuple

import boto3


def get_stopped_ec2(
    session: boto3.Session, regions: List[str]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    results = []
    errors = []

    for region in regions:
        try:
            ec2 = session.client("ec2", region_name=region)
            response = ec2.describe_instances(
                Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
            )

            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    results.append(
                        {
                            "InstanceId": instance.get("InstanceId"),
                            "InstanceType": instance.get("InstanceType"),
                            "Region": region,
                            "LaunchTime": str(instance.get("LaunchTime")),
                            "Tags": instance.get("Tags", []),
                        }
                    )
        except Exception as e:
            errors.append(f"{region}: {str(e)}")

    return results, errors


def get_unattached_ebs_volumes(
    session: boto3.Session, regions: List[str]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    results = []
    errors = []

    for region in regions:
        try:
            ec2 = session.client("ec2", region_name=region)
            response = ec2.describe_volumes(
                Filters=[{"Name": "status", "Values": ["available"]}]
            )

            for volume in response.get("Volumes", []):
                results.append(
                    {
                        "VolumeId": volume.get("VolumeId"),
                        "Size": volume.get("Size"),
                        "Region": region,
                        "Tags": volume.get("Tags", []),
                    }
                )
        except Exception as e:
            errors.append(f"{region}: {str(e)}")

    return results, errors


def get_unassociated_eips(
    session: boto3.Session, regions: List[str]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    results = []
    errors = []

    for region in regions:
        try:
            ec2 = session.client("ec2", region_name=region)
            response = ec2.describe_addresses()

            for address in response.get("Addresses", []):
                if "InstanceId" not in address:
                    results.append(
                        {
                            "PublicIp": address.get("PublicIp"),
                            "AllocationId": address.get("AllocationId"),
                            "Region": region,
                        }
                    )
        except Exception as e:
            errors.append(f"{region}: {str(e)}")

    return results, errors


def get_budget_data(
    session: boto3.Session, account_id: str
) -> Tuple[Dict[str, Any], str]:
    try:
        client = session.client("budgets")
        response = client.describe_budgets(AccountId=account_id)

        budget_status = []
        for budget in response.get("Budgets", []):
            budget_status.append(
                {
                    "Name": budget["BudgetName"],
                    "Limit": budget.get("BudgetLimit", {}).get("Amount"),
                    "Unit": budget.get("BudgetLimit", {}).get("Unit"),
                    "TimeUnit": budget.get("TimeUnit"),
                }
            )

        return budget_status, ""
    except Exception as e:
        return [], str(e)


def cost_filters(
    tags: Optional[List[str]] = None,
    dimensions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Constructs filter parameters for AWS Cost Explorer API call based on provided tags and dimensions.
    """

    tag_filters_list: List[Dict[str, Any]] = []
    dimension_filters_list: List[Dict[str, Any]] = []
    filter_param: Optional[Dict[str, Any]] = None
    cost_explorer_kwargs: Dict[str, Any] = {}

    if tags:
        for t_str in tags:
            if "=" in t_str:
                key, value = t_str.split("=", 1)
                tag_filters_list.append({"Key": key, "Values": [value]})

    if dimensions:
        for d_str in dimensions:
            if "=" in d_str:
                key, value = d_str.split("=", 1)
                dimension_filters_list.append({"Key": key, "Values": [value]})

    filters = []
    if tag_filters_list:
        if len(tag_filters_list) == 1:
            filters.append({"Tags": tag_filters_list[0]})
        else:
            filters.append({"And": [{"Tags": f} for f in tag_filters_list]})

    if dimension_filters_list:
        if len(dimension_filters_list) == 1:
            filters.append({"Dimensions": dimension_filters_list[0]})
        else:
            filters.append({"And": [{"Dimensions": f} for f in dimension_filters_list]})

    if len(filters) == 1:
        filter_param = filters[0]
    elif len(filters) > 1:
        filter_param = {"And": filters}

    if filter_param:
        cost_explorer_kwargs["Filter"] = filter_param

    return cost_explorer_kwargs
