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
    service_account_key_path: Optional[str] = None,
    time_range_days: Optional[int] = None,
    start_date_iso: Optional[str] = None,
    end_date_iso: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get GCP cost breakdown for a given project. Supports flexible date range queries.
    """
    credentials = get_gcp_credentials(service_account_key_path)
    cost_summary, err = get_gcp_cost_breakdown(
        credentials,
        project_id,
        time_range_days,
        start_date_iso,
        end_date_iso
    )

    return {
        "project_id": project_id,
        **cost_summary,
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
