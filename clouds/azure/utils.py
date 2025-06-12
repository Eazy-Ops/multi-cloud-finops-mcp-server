# clouds/azure/utils.py

from typing import List, Tuple, Dict, Any, Optional
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.consumption import ConsumptionManagementClient
from azure.mgmt.resource import SubscriptionClient
from azure.mgmt.resource.subscriptions.models import Subscription
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import HttpResponseError
from datetime import datetime, timedelta


def get_stopped_vms(credential: DefaultAzureCredential, subscription_id: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    results = []
    errors = []

    try:
        compute_client = ComputeManagementClient(credential, subscription_id)
        vms = compute_client.virtual_machines.list_all()

        for vm in vms:
            instance_view = compute_client.virtual_machines.instance_view(vm.resource_group_name, vm.name)
            statuses = [s.code for s in instance_view.statuses]
            if any("stopped" in s.lower() or "deallocated" in s.lower() for s in statuses):
                results.append({
                    "name": vm.name,
                    "resource_group": vm.resource_group_name,
                    "location": vm.location,
                    "statuses": statuses,
                })

    except HttpResponseError as e:
        errors.append(str(e))

    return results, errors


def get_unattached_disks(credential: DefaultAzureCredential, subscription_id: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    results = []
    errors = []

    try:
        compute_client = ComputeManagementClient(credential, subscription_id)
        disks = compute_client.disks.list()

        for disk in disks:
            if not disk.managed_by:
                results.append({
                    "name": disk.name,
                    "location": disk.location,
                    "disk_size_gb": disk.disk_size_gb,
                    "resource_group": disk.id.split("/")[4],
                    "os_type": str(disk.os_type),
                    "tags": disk.tags or {},
                })

    except HttpResponseError as e:
        errors.append(str(e))

    return results, errors


def get_subscription_display_name(credential: DefaultAzureCredential, subscription_id: str) -> str:
    try:
        subscription_client = SubscriptionClient(credential)
        sub: Subscription = subscription_client.subscriptions.get(subscription_id)
        return sub.display_name
    except Exception:
        return subscription_id


def get_budget_data(credential: DefaultAzureCredential, subscription_id: str) -> Tuple[List[Dict[str, Any]], str]:
    # Azure Budgets are handled in the Cost Management API (preview or through Portal setup)
    # This is a placeholder
    return [{
        "name": "Monthly Budget",
        "amount": "500",
        "currency": "USD",
        "time_grain": "Monthly"
    }], ""


def get_cost_breakdown(credential: DefaultAzureCredential, subscription_id: str) -> Tuple[List[Dict[str, Any]], str]:
    try:
        consumption_client = ConsumptionManagementClient(credential, subscription_id)
        end_date = datetime.utcnow().date()
        start_date = end_date.replace(day=1)

        usage = consumption_client.usage_details.list(
            scope=f"/subscriptions/{subscription_id}",
            expand="properties/meterDetails",
            filter=f"properties/usageEnd ge '{start_date}' AND properties/usageEnd le '{end_date}'"
        )

        cost_by_service = {}
        for item in usage:
            service = item.properties.meter_details.meter_name
            cost = float(item.properties.pretax_cost)
            cost_by_service[service] = cost_by_service.get(service, 0.0) + cost

        breakdown = [{"service": k, "cost": round(v, 2), "currency": "USD"} for k, v in cost_by_service.items()]
        return breakdown, ""

    except Exception as e:
        return [], str(e)
