from datetime import datetime
from typing import Optional, Dict, Any, List
from langchain.tools import tool
from google.cloud import resourcemanager_v3, container_v1

from clouds.gcp.client import get_gcp_credentials
from clouds.gcp.utils import (
    get_stopped_vms,
    get_unattached_disks,
    get_budget_data,
    get_gcp_cost_breakdown
)
from googleapiclient.discovery import build

@tool
def get_gcp_cost(
    project_id: str,
    service_account_key_path: Optional[str] = None,
    time_range_days: Optional[int] = None,
    start_date_iso: Optional[str] = None,
    end_date_iso: Optional[str] = None,
    region_wise: bool = False,

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
        region_wise: Optional. if true then we need to return region wise cost breakdown.

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
        end_date_iso,
        table_prefix="gcp_billing_export_",
        region_wise=region_wise,
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


@tool
def list_gcp_projects(service_account_key_path: Optional[str] = None) -> Dict[str, Any]:
    """
    List all GCP projects accessible with the provided service account or default ADC.

    Args:
        service_account_key_path: Optional path to service account JSON. If not given, uses local gcloud login.

    Returns:
        A dictionary with:
            - `projects`: List of dictionaries containing `project_id`, `name`, and `state`.
            - `error`: Any error encountered during retrieval.
    """
    try:
        credentials = get_gcp_credentials(service_account_key_path)
        client = resourcemanager_v3.ProjectsClient(credentials=credentials)

        # Use SearchProjectsRequest instead of ListProjectsRequest
        request = resourcemanager_v3.SearchProjectsRequest()
        projects = []

        for project in client.search_projects(request=request):
            projects.append({
                "project_id": project.project_id,
                "name": project.display_name,
                "state": resourcemanager_v3.Project.State(project.state).name,
            })

        return {"projects": projects, "error": None}

    except Exception as e:
        return {"projects": [], "error": str(e)}



@tool
def list_gke_clusters(project_id: str, location: str = "-", service_account_key_path: Optional[str] = None) -> Dict[str, Any]:
    """
    List all GKE clusters in the specified project and location.

    Args:
        project_id: GCP project ID.
        location: Region or zone ('-' for all).
        service_account_key_path: Optional path to the service account key file.

    Returns:
        A dictionary with:
            - `clusters`: List of cluster names and locations.
            - `error`: Any error encountered.
    """
    try:
        credentials = get_gcp_credentials(service_account_key_path)
        client = container_v1.ClusterManagerClient(credentials=credentials)
        parent = f"projects/{project_id}/locations/{location}"
        response = client.list_clusters(parent=parent)

        clusters = [
            {"name": cluster.name, "location": cluster.location}
            for cluster in response.clusters
        ]

        return {"clusters": clusters, "error": None}

    except Exception as e:
        return {"clusters": [], "error": str(e)}


@tool
def list_sql_instances(project_id: str, service_account_key_path: Optional[str] = None) -> Dict[str, Any]:
    """
    List all Cloud SQL instances for the given GCP project.

    Args:
        project_id: GCP project ID.
        service_account_key_path: Optional. Path to the service account JSON key file.

    Returns:
        A dictionary with:
            - `instances`: List of Cloud SQL instances with basic metadata.
            - `error`: Any error encountered.
    """
    try:
        credentials = get_gcp_credentials(service_account_key_path)

        service = build("sqladmin", "v1beta4", credentials=credentials)
        request = service.instances().list(project=project_id)
        response = request.execute()

        instances = []
        for instance in response.get("items", []):
            instances.append({
                "name": instance.get("name"),
                "region": instance.get("region"),
                "databaseVersion": instance.get("databaseVersion"),
                "state": instance.get("state"),
            })

        return {"instances": instances, "error": None}

    except Exception as e:
        return {"instances": [], "error": str(e)}


from google.cloud import logging_v2

@tool
def get_gcp_logs(
    project_id: str,
    filter_str: Optional[str] = None,
    page_size: int = 20,
    service_account_key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve recent log entries from Cloud Logging for the given project.

    Args:
        project_id: GCP project ID.
        filter_str: Optional filter string for log entries.
        page_size: Number of log entries to return.
        service_account_key_path: Optional path to the service account JSON key file.

    Returns:
        A dictionary with:
            - `entries`: List of recent log entries.
            - `error`: Any error encountered.
    """
    try:
        credentials = get_gcp_credentials(service_account_key_path)
        client = logging_v2.Client(project=project_id, credentials=credentials)
        entries = client.list_entries(filter_=filter_str, page_size=page_size)

        logs = []
        for entry in entries:
            logs.append({
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "logName": entry.log_name,
                "payload": entry.payload,
                "severity": entry.severity.name if entry.severity else None,
            })

        return {"entries": logs, "error": None}

    except Exception as e:
        return {"entries": [], "error": str(e)}
