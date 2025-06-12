from datetime import datetime
from typing import Optional, Dict, Any, List
from langchain.tools import tool

from clouds.gcp.client import get_gcp_credentials
from clouds.gcp.utils import (
    get_stopped_vms,
    get_unattached_disks,
    get_budget_data,
    get_gcp_cost_breakdown
)

@tool
def get_gcp_cost(
    project_id: str,
    service_account_key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get GCP cost breakdown for the current month for a given project.
    """
    credentials = get_gcp_credentials(service_account_key_path)
    cost_data, err = get_gcp_cost_breakdown(credentials, project_id)

    return {
        "project_id": project_id,
        "start_date": datetime.utcnow().replace(day=1).strftime('%Y-%m-%d'),
        "end_date": datetime.utcnow().strftime('%Y-%m-%d'),
        "cost_summary": cost_data,
        "error": err
    }


@tool
def run_gcp_finops_audit(
    project_id: str,
    billing_account_id: str,
    service_account_key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run a GCP FinOps audit to find unused resources and report budget.
    Checks:
        - Terminated (idle) Compute Engine VMs
        - Unattached Persistent Disks
        - Budget usage
    """
    credentials = get_gcp_credentials(service_account_key_path)

    vms, vms_err = get_stopped_vms(credentials, project_id)
    disks, disk_err = get_unattached_disks(credentials, project_id)
    budgets, budgets_err = get_budget_data(credentials, billing_account_id)

    return {
        "project_id": project_id,
        "audit": {
            "stopped_vms": vms,
            "unattached_disks": disks,
            "budget_status": budgets,
        },
        "errors": {
            "vms": vms_err,
            "disks": disk_err,
            "budgets": budgets_err,
        }
    }
