from typing import Optional, Dict, Any, List
from langchain.tools import tool

from clouds.azure.client import get_azure_credentials
from clouds.azure.utils import (
    get_stopped_vms,
    get_unattached_disks,
    get_budget_data, get_cost_breakdown
)

@tool
def get_azure_cost(
    subscription_id: str,
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None
) -> Dict[str, Any]:

    """
    Get cost data for a specified Azure subscription for a single defined period.
    The period is defined either by 'time_range_days' (last N days including today),
    or by explicit 'start_date_iso' and 'end_date_iso' values.
    If both are provided, explicit dates take precedence.
    If no period is defined, defaults to the current month to date.

    Args:
        subscription_id: Azure Subscription ID.
        tenant_id: Optional. Azure Active Directory tenant ID.
        client_id: Optional. Azure client ID for service principal authentication.
        client_secret: Optional. Azure client secret for service principal authentication.

    Returns:
        Dict: Processed cost summary for the specified subscription and period.
              Includes error details if any occurred during data retrieval.
    """
    credentials = get_azure_credentials(tenant_id, client_id, client_secret)
    cost_data, error = get_cost_breakdown(credentials, subscription_id)
    if not cost_data:
        return {
            "subscription_id": subscription_id,
            "cost_summary": [],
            "error": "No Azure cost data found for the current month."
        }
    return {
        "subscription_id": subscription_id,
        "cost_summary": cost_data,
        "error": error
    }

@tool
def run_azure_finops_audit(
    subscription_id: str,
    regions: List[str],
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None
) -> Dict[str, Any]:

    """
    Run a FinOps audit for a specified Azure subscription across one or more regions.
    The audit includes:
        - Stopped Virtual Machines (VMs),
        - Unattached Managed Disks,
        - Current Budget Status.

    Args:
        subscription_id: Azure Subscription ID.
        regions: List of Azure region names to audit (e.g., ["eastus", "westus2"]).
        tenant_id: Optional. Azure Active Directory tenant ID.
        client_id: Optional. Azure client ID for service principal authentication.
        client_secret: Optional. Azure client secret for service principal authentication.

    Returns:
        Dict: Audit findings and any error messages encountered per component.
    """
    credentials = get_azure_credentials(tenant_id, client_id, client_secret)

    stopped_vms, vm_errors = get_stopped_vms(credentials, subscription_id)
    unattached_disks, disk_errors = get_unattached_disks(credentials, subscription_id)
    budget_data, budget_error = get_budget_data(credentials, subscription_id)

    return {
        "subscription_id": subscription_id,
        "audit": {
            "stopped_vms": stopped_vms,
            "unattached_disks": unattached_disks,
            "budget_status": budget_data,
        },
        "errors": {
            "vm_errors": vm_errors,
            "disk_errors": disk_errors,
            "budget_error": budget_error,
        }
    }
