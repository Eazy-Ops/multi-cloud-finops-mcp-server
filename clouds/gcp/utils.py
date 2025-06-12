from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from clouds.gcp.client import get_gcp_credentials


def get_stopped_vms(credentials, project_id: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    results = []
    errors = []
    try:
        compute = build("compute", "v1", credentials=credentials)
        request = compute.instances().aggregatedList(project=project_id)
        while request is not None:
            response = request.execute()
            for zone, instances_scoped_list in response.get("items", {}).items():
                for instance in instances_scoped_list.get("instances", []):
                    if instance.get("status") == "TERMINATED":
                        results.append({
                            "id": instance.get("id"),
                            "name": instance.get("name"),
                            "zone": zone,
                            "machineType": instance.get("machineType", "").split("/")[-1],
                            "creationTimestamp": instance.get("creationTimestamp"),
                            "tags": instance.get("tags", {}).get("items", [])
                        })
            request = compute.instances().aggregatedList_next(previous_request=request, previous_response=response)
    except HttpError as e:
        errors.append(str(e))
    return results, errors


def get_unattached_disks(credentials, project_id: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    results = []
    errors = []
    try:
        compute = build("compute", "v1", credentials=credentials)
        request = compute.disks().aggregatedList(project=project_id)
        while request is not None:
            response = request.execute()
            for zone, disks_scoped_list in response.get("items", {}).items():
                for disk in disks_scoped_list.get("disks", []):
                    if not disk.get("users"):
                        results.append({
                            "id": disk.get("id"),
                            "name": disk.get("name"),
                            "sizeGb": disk.get("sizeGb"),
                            "zone": zone,
                            "creationTimestamp": disk.get("creationTimestamp"),
                            "labels": disk.get("labels", {})
                        })
            request = compute.disks().aggregatedList_next(previous_request=request, previous_response=response)
    except HttpError as e:
        errors.append(str(e))
    return results, errors


def get_budget_data(credentials, billing_account_id: str) -> Tuple[List[Dict[str, Any]], str]:
    try:
        billing = build("billingbudgets", "v1", credentials=credentials)
        budgets = billing.billingAccounts().budgets().list(parent=f"billingAccounts/{billing_account_id}").execute()
        result = []
        for budget in budgets.get("budgets", []):
            amount_obj = budget.get("amount", {}).get("specifiedAmount", {})
            result.append({
                "name": budget.get("displayName"),
                "budget_filter": budget.get("budgetFilter", {}),
                "amount": amount_obj.get("units", "0"),
                "currency": amount_obj.get("currencyCode", "USD"),
            })
        return result, ""
    except HttpError as e:
        return [], str(e)



from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from google.cloud import bigquery
from google.api_core.exceptions import NotFound

def get_gcp_cost_breakdown(
    credentials,
    project_id: str,
    time_range_days: Optional[int] = None,
    start_date_iso: Optional[str] = None,
    end_date_iso: Optional[str] = None,
    dataset: str = "dev-ezo.dev_dataset",
    table_prefix: str = "gcp_billing_export_"  # default table prefix
) -> Tuple[Dict[str, Any], str]:
    try:
        now = datetime.utcnow().date()

        if start_date_iso and end_date_iso:
            start = datetime.strptime(start_date_iso, "%Y-%m-%d").date()
            end = datetime.strptime(end_date_iso, "%Y-%m-%d").date()
        elif time_range_days:
            end = now
            start = now - timedelta(days=time_range_days - 1)
        else:
            start = now.replace(day=1)
            end = now

        bq_client = bigquery.Client(credentials=credentials, project=project_id)
        table_name = f"`{dataset}.gcp_billing_export_*`"
        print(table_name, "===============" , project_id)
        query = f"""
        SELECT
          service.description AS service,
          SUM(cost) AS total_cost,
          currency
        FROM {table_name}
        WHERE usage_start_time BETWEEN '{start}' AND '{end}'
        AND project.id IN ('{project_id}')
        GROUP BY service, currency
        ORDER BY total_cost DESC
        """

        query_job = bq_client.query(query)
        results = query_job.result()

        cost_by_service = {}
        total_cost = 0
        currency = "USD"

        for row in results:
            cost_by_service[row.service] = float(row.total_cost)
            total_cost += float(row.total_cost)
            currency = row.currency

        return {
            "project_id": project_id,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "total_cost": round(total_cost, 2),
            "currency": currency,
            "cost_by_service": cost_by_service,
        }, ""

    except NotFound:
        # Fallback to mock
        mock_services = [
            {"service": "Compute Engine", "cost": 102.5, "currency": "USD"},
            {"service": "Cloud Storage", "cost": 21.8, "currency": "USD"},
        ]
        total = sum(item["cost"] for item in mock_services)
        grouped = {s["service"]: s["cost"] for s in mock_services}

        return {
            "project_id": project_id,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "total_cost": round(total, 2),
            "currency": "USD",
            "cost_by_service": grouped,
            "note": "Returned mock data as no billing export was found."
        }, ""

    except Exception as e:
        return {}, str(e)


