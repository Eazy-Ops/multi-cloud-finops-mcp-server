from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime
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


def get_gcp_cost_breakdown(credentials, project_id: str) -> Tuple[List[Dict[str, Any]], str]:
    try:
        now = datetime.utcnow()
        start_date = (now.replace(day=1)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')

        # Placeholder – real cost breakdowns need BigQuery export
        return [{
            "service": "Compute Engine",
            "cost": 100.50,
            "currency": "USD"
        }, {
            "service": "Cloud Storage",
            "cost": 20.00,
            "currency": "USD"
        }], ""
    except Exception as e:
        return [], str(e)
