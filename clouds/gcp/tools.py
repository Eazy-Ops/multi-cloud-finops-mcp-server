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
    Retrieve GCP cost breakdown for a specific project over a defined time period.

    The time period can be specified either by:
    - `time_range_days`: Number of days from today (e.g., last 7 days), or
    - `start_date_iso` and `end_date_iso`: Specific date range in YYYY-MM-DD format.

    If no time period is provided, the default is the current month-to-date.

    Args:
        project_id: GCP project ID to fetch cost data for.
        service_account_key_path: Optional. Path to the GCP service account JSON key file.
        time_range_days: Optional. Number of days for which to retrieve cost data.
        start_date_iso: Optional. Start date in YYYY-MM-DD format (overrides `time_range_days`).
        end_date_iso: Optional. End date in YYYY-MM-DD format (overrides `time_range_days`).

    Returns:
        A dictionary containing:
            - `project_id`: The input project ID.
            - `total_cost`: Total cost over the time period.
            - `cost_by_service`: Breakdown of cost by GCP services.
            - `error`: Any error encountered during cost retrieval.
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
    Run a GCP FinOps audit for a given project and billing account.

    The audit identifies common cost optimization opportunities, including:
    - Stopped Virtual Machine (VM) instances.
    - Unattached persistent disks.
    - Current budget usage and status for the billing account.

    Args:
        project_id: GCP project ID to audit.
        billing_account_id: Billing account ID associated with the GCP project.
        service_account_key_path: Optional. Path to the GCP service account JSON key file.

    Returns:
        A dictionary containing:
            - `project_id`: The audited project ID.
            - `audit`: Dictionary with findings for:
                - `stopped_vms`: List of stopped Compute Engine instances.
                - `unattached_disks`: List of unattached persistent disks.
                - `budget_status`: Current budget status from Cloud Billing.
            - `errors`: Any errors encountered while gathering audit data.
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
