from typing import Optional, Dict, Any, List
from langchain.tools import tool

from clouds.azure.client import get_azure_credentials
from clouds.azure.utils import (
    get_stopped_vms,
    get_unattached_disks,
    get_budget_data
)

@tool
def get_azure_cost(
    subscription_id: str,
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None
) -> Dict[str, Any]:

    """
    Get Azure cost breakdown for the current month for a given project.
    """
    credentials = get_azure_credentials(tenant_id, client_id, client_secret)
    cost_data, error = get_budget_data(credentials, subscription_id)
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
    Run Azure FinOps audit to find unused resources and report budget.
    Checks:
        - Terminated (idle) Compute Engine VMs
        - Unattached Persistent Disks
        - Budget usage
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
