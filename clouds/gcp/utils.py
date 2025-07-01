from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from google.api_core.exceptions import NotFound
from google.cloud import bigquery
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from config import GCP_BILLING_DATASET, GCP_BILLING_TABLE_PREFIX


def get_stopped_vms(
    credentials, project_id: str
) -> Tuple[List[Dict[str, Any]], List[str]]:
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
                        results.append(
                            {
                                "id": instance.get("id"),
                                "name": instance.get("name"),
                                "zone": zone,
                                "machineType": instance.get("machineType", "").split(
                                    "/"
                                )[-1],
                                "creationTimestamp": instance.get("creationTimestamp"),
                                "tags": instance.get("tags", {}).get("items", []),
                            }
                        )
            request = compute.instances().aggregatedList_next(
                previous_request=request, previous_response=response
            )
    except HttpError as e:
        errors.append(str(e))
    return results, errors


def get_unattached_disks(
    credentials, project_id: str
) -> Tuple[List[Dict[str, Any]], List[str]]:
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
                        results.append(
                            {
                                "id": disk.get("id"),
                                "name": disk.get("name"),
                                "sizeGb": disk.get("sizeGb"),
                                "zone": zone,
                                "creationTimestamp": disk.get("creationTimestamp"),
                                "labels": disk.get("labels", {}),
                            }
                        )
            request = compute.disks().aggregatedList_next(
                previous_request=request, previous_response=response
            )
    except HttpError as e:
        errors.append(str(e))
    return results, errors


def get_budget_data(
    credentials, billing_account_id: str
) -> Tuple[List[Dict[str, Any]], str]:
    try:
        billing = build("billingbudgets", "v1", credentials=credentials)
        budgets = (
            billing.billingAccounts()
            .budgets()
            .list(parent=f"billingAccounts/{billing_account_id}")
            .execute()
        )
        result = []
        for budget in budgets.get("budgets", []):
            amount_obj = budget.get("amount", {}).get("specifiedAmount", {})
            result.append(
                {
                    "name": budget.get("displayName"),
                    "budget_filter": budget.get("budgetFilter", {}),
                    "amount": amount_obj.get("units", "0"),
                    "currency": amount_obj.get("currencyCode", "USD"),
                }
            )
        return result, ""
    except HttpError as e:
        return [], str(e)


def get_gcp_cost_breakdown(
    credentials,
    project_id: str,
    time_range_days: Optional[int] = None,
    start_date_iso: Optional[str] = None,
    end_date_iso: Optional[str] = None,
    region_wise: bool = False,
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
        table_name = f"`{GCP_BILLING_DATASET}.{GCP_BILLING_TABLE_PREFIX}*`"
        if region_wise:
            query = f"""
            SELECT
              service.description AS service,
              location.region AS region,
              SUM(cost) AS total_cost,
              currency
            FROM {table_name}
            WHERE usage_start_time BETWEEN '{start}' AND '{end}'
              AND project.id = '{project_id}'
            GROUP BY service, region, currency
            ORDER BY region, total_cost DESC
            """
        else:
            query = f"""
            SELECT
              service.description AS service,
              SUM(cost) AS total_cost,
              currency
            FROM {table_name}
            WHERE usage_start_time BETWEEN '{start}' AND '{end}'
              AND project.id = '{project_id}'
            GROUP BY service, currency
            ORDER BY total_cost DESC
            """

        query_job = bq_client.query(query)
        results = query_job.result()

        total_cost = 0.0
        currency = "USD"

        if region_wise:
            cost_by_region: Dict[str, Dict[str, float]] = {}

            for row in results:
                service = row.service
                region = row.region or "global"
                cost = float(row.total_cost)
                currency = row.currency

                if region not in cost_by_region:
                    cost_by_region[region] = {}
                cost_by_region[region][service] = (
                    cost_by_region[region].get(service, 0.0) + cost
                )
                total_cost += cost

            return {
                "project_id": project_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "total_cost": round(total_cost, 2),
                "currency": currency,
                "cost_by_region": {
                    region: {
                        service: round(cost, 2) for service, cost in services.items()
                    }
                    for region, services in cost_by_region.items()
                },
            }, ""

        else:
            cost_by_service: Dict[str, float] = {}

            for row in results:
                service = row.service
                cost = float(row.total_cost)
                currency = row.currency

                cost_by_service[service] = cost_by_service.get(service, 0.0) + cost
                total_cost += cost

            return {
                "project_id": project_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "total_cost": round(total_cost, 2),
                "currency": currency,
                "cost_by_service": {k: round(v, 2) for k, v in cost_by_service.items()},
            }, ""

    except NotFound:
        # Fallback mock for region_wise or service_wise
        mock_services = [
            {
                "service": "Compute Engine",
                "cost": 102.5,
                "currency": "USD",
                "region": "us-central1",
            },
            {
                "service": "Cloud Storage",
                "cost": 21.8,
                "currency": "USD",
                "region": "global",
            },
        ]
        total = sum(item["cost"] for item in mock_services)

        if region_wise:
            grouped_region = {}
            for item in mock_services:
                region = item["region"]
                service = item["service"]
                cost = item["cost"]

                if region not in grouped_region:
                    grouped_region[region] = {}
                grouped_region[region][service] = (
                    grouped_region[region].get(service, 0.0) + cost
                )

            return {
                "project_id": project_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "total_cost": round(total, 2),
                "currency": "USD",
                "cost_by_region": grouped_region,
                "note": "Returned mock region-wise data as no billing export was found.",
            }, ""

        else:
            grouped_service = {}
            for item in mock_services:
                service = item["service"]
                cost = item["cost"]
                grouped_service[service] = grouped_service.get(service, 0.0) + cost

            return {
                "project_id": project_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "total_cost": round(total, 2),
                "currency": "USD",
                "cost_by_service": grouped_service,
                "note": "Returned mock service-wise data as no billing export was found.",
            }, ""

    except Exception as e:
        return {}, str(e)


def get_metric_usage(monitoring_client, project_id, interval, metric_type, disk_id):
    filter_str = (
        f'metric.type = "{metric_type}" AND resource.labels.disk_id = "{disk_id}"'
    )
    from google.cloud import monitoring_v3

    try:

        series = monitoring_client.list_time_series(
            request={
                "name": f"projects/{project_id}",
                "filter": filter_str,
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )

        return sum(
            point.value.int64_value
            for time_series in series
            for point in time_series.points
        )
    except NotFound:
        # Metric not found (no data collected yet)
        return 0
