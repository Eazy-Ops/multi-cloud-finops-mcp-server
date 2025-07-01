import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from google.cloud import container_v1, logging_v2, resourcemanager_v3
from googleapiclient.discovery import build
from langchain.tools import tool

from clouds.gcp.client import get_gcp_credentials
from clouds.gcp.utils import (get_budget_data, get_gcp_cost_breakdown,
                              get_metric_usage, get_stopped_vms,
                              get_unattached_disks)

logger = logging.getLogger(__name__)


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
        region_wise=region_wise,
    )

    return {"project_id": project_id, **cost_summary, "error": err}


@tool
def run_gcp_finops_audit(
    project_id: str,
    billing_account_id: str,
    service_account_key_path: Optional[str] = None,
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
        },
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
            projects.append(
                {
                    "project_id": project.project_id,
                    "name": project.display_name,
                    "state": resourcemanager_v3.Project.State(project.state).name,
                }
            )

        return {"projects": projects, "error": None}

    except Exception as e:
        return {"projects": [], "error": str(e)}


@tool
def list_gke_clusters(
    project_id: str, location: str = "-", service_account_key_path: Optional[str] = None
) -> Dict[str, Any]:
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
def list_sql_instances(
    project_id: str, service_account_key_path: Optional[str] = None
) -> Dict[str, Any]:
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
            instances.append(
                {
                    "name": instance.get("name"),
                    "region": instance.get("region"),
                    "databaseVersion": instance.get("databaseVersion"),
                    "state": instance.get("state"),
                }
            )

        return {"instances": instances, "error": None}

    except Exception as e:
        return {"instances": [], "error": str(e)}


@tool
def get_gcp_logs(
    project_id: str,
    filter_str: Optional[str] = None,
    page_size: int = 20,
    service_account_key_path: Optional[str] = None,
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
            logs.append(
                {
                    "timestamp": (
                        entry.timestamp.isoformat() if entry.timestamp else None
                    ),
                    "logName": entry.log_name,
                    "payload": entry.payload,
                    "severity": entry.severity.name if entry.severity else None,
                }
            )

        return {"entries": logs, "error": None}

    except Exception as e:
        return {"entries": [], "error": str(e)}


@tool
def analyze_gcp_storage(
    project_id: str, service_account_key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze GCP Cloud Storage buckets for cost optimization opportunities.

    Args:
        project_id: GCP project ID to analyze
        service_account_key_path: Optional. Path to the service account JSON key file.

    Returns:
        Dictionary containing Cloud Storage optimization recommendations with resource details
    """
    from google.cloud import monitoring_v3, storage

    try:
        credentials = get_gcp_credentials(service_account_key_path)

        storage_client = storage.Client(project=project_id, credentials=credentials)
        monitoring_client = monitoring_v3.MetricServiceClient(credentials=credentials)

        recommendations = {
            "lifecycle_policy_recommendations": [],
            "storage_class_optimization": [],
            "unused_buckets": [],
            "large_objects": [],
            "versioning_optimization": [],
            "iam_optimization": [],
            "available_buckets": [],
        }

        buckets = storage_client.list_buckets()

        for bucket in buckets:
            try:
                iam_policy = bucket.get_iam_policy()
                iam_bindings = iam_policy.bindings if iam_policy else []
                lifecycle_rules = (
                    list(bucket.lifecycle_rules) if bucket.lifecycle_rules else []
                )
                bucket_details = {
                    "bucket_name": bucket.name,
                    "project_id": project_id,
                    "location": bucket.location,
                    "storage_class": bucket.storage_class,
                    "created": bucket.time_created.isoformat(),
                    "versioning_enabled": bucket.versioning_enabled,
                    "labels": bucket.labels,
                    "lifecycle_rules": len(lifecycle_rules),
                    "iam_members": len(iam_bindings),
                }

                # Add to available buckets
                recommendations["available_buckets"].append(bucket_details)

                # Get bucket metrics for the last 30 days
                interval = monitoring_v3.TimeInterval(
                    {
                        "end_time": {"seconds": int(datetime.now().timestamp())},
                        "start_time": {
                            "seconds": int(
                                (datetime.now() - timedelta(days=30)).timestamp()
                            )
                        },
                    }
                )

                storage_metric = monitoring_client.list_time_series(
                    request={
                        "name": f"projects/{project_id}",
                        "filter": f'metric.type = "storage.googleapis.com/storage/total_bytes" AND resource.labels.bucket_name = "{bucket.name}"',
                        "interval": interval,
                        "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                    }
                )

                total_bytes = sum(
                    point.value.double_value
                    for series in storage_metric
                    for point in series.points
                )

                bucket_details["total_bytes"] = total_bytes

                if total_bytes == 0:
                    recommendations["unused_buckets"].append(
                        {
                            "resource_details": bucket_details,
                            "recommendation": {
                                "action": "Consider deletion",
                                "reason": "No data stored in the last 30 days",
                                "considerations": "Ensure no critical data before deletion",
                            },
                        }
                    )

                if not bucket.lifecycle_rules:
                    recommendations["lifecycle_policy_recommendations"].append(
                        {
                            "resource_details": bucket_details,
                            "recommendation": {
                                "action": "Add lifecycle rules",
                                "reason": "No lifecycle rules configured",
                                "suggested_rules": [
                                    "Move objects to Nearline after 30 days",
                                    "Move to Coldline after 90 days",
                                    "Delete incomplete multipart uploads after 7 days",
                                ],
                            },
                        }
                    )

                if bucket.storage_class == "STANDARD" and total_bytes > 1_000_000_000:
                    recommendations["storage_class_optimization"].append(
                        {
                            "resource_details": bucket_details,
                            "recommendation": {
                                "action": "Consider storage class change",
                                "reason": f"Large bucket ({total_bytes / 1_000_000_000:.2f} GB) using Standard storage",
                                "suggestions": [
                                    "Consider Nearline for infrequently accessed data",
                                    "Consider Coldline for archival data",
                                    "Consider Archive for long-term archival data",
                                ],
                            },
                        }
                    )

                if bucket.versioning_enabled:
                    versioned_objects = list(bucket.list_blobs(versions=True))
                    if len(versioned_objects) > 1000:
                        recommendations["versioning_optimization"].append(
                            {
                                "resource_details": bucket_details,
                                "recommendation": {
                                    "action": "Optimize versioning",
                                    "reason": f"Large number of versioned objects ({len(versioned_objects)})",
                                    "suggestions": [
                                        "Implement lifecycle rules for versioned objects",
                                        "Review versioning necessity for all objects",
                                        "Use versioning only for critical data",
                                    ],
                                },
                            }
                        )

                for binding in iam_policy.bindings:
                    if (
                        binding["role"] == "roles/storage.admin"
                        and len(binding["members"]) > 3
                    ):
                        recommendations["iam_optimization"].append(
                            {
                                "resource_details": bucket_details,
                                "recommendation": {
                                    "action": "Review IAM permissions",
                                    "reason": f'Too many storage admins ({len(binding["members"])})',
                                    "suggestions": [
                                        "Review admin access necessity",
                                        "Consider using more specific roles",
                                        "Implement least privilege principle",
                                    ],
                                },
                            }
                        )

            except Exception as inner_e:
                logger.warning(
                    f"Warning: Could not analyze bucket {bucket.name}: {inner_e}"
                )
                continue

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}


@tool
def analyze_gcp_disks(
    project_id: str, service_account_key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze GCP Compute Engine disks for cost optimization opportunities.

    Args:
        project_id: GCP project ID to analyze
        service_account_key_path: Optional. Path to the service account JSON key file.

    Returns:
        Dictionary containing Compute Engine disk optimization recommendations with resource details.
    """
    from google.cloud import compute_v1, monitoring_v3

    try:
        credentials = get_gcp_credentials(service_account_key_path)

        disk_client = compute_v1.DisksClient(credentials=credentials)
        zone_client = compute_v1.ZonesClient(credentials=credentials)
        monitoring_client = monitoring_v3.MetricServiceClient(credentials=credentials)

        recommendations = {
            "unattached_disks": [],
            "idle_disks": [],
            "expensive_disk_types": [],
            "iam_optimization": [],
            "available_disks": [],
        }
        zones = [zone.name for zone in zone_client.list(project=project_id)]

        for zone in zones:
            for disk in disk_client.list(project=project_id, zone=zone):
                try:
                    disk_details = {
                        "disk_name": disk.name,
                        "zone": zone,
                        "type": disk.type.split("/")[-1],
                        "size_gb": disk.size_gb,
                        "users": disk.users,
                        "labels": disk.labels,
                        "creation_timestamp": disk.creation_timestamp,
                    }

                    recommendations["available_disks"].append(disk_details)

                    # Unattached disk
                    if not disk.users:
                        recommendations["unattached_disks"].append(
                            {
                                "resource_details": disk_details,
                                "recommendation": {
                                    "action": "Delete or snapshot unattached disk",
                                    "reason": "Disk is not attached to any instance",
                                    "considerations": "Ensure disk is not needed before deletion",
                                },
                            }
                        )

                    # Expensive disk type
                    if "pd-ssd" in disk.type:
                        recommendations["expensive_disk_types"].append(
                            {
                                "resource_details": disk_details,
                                "recommendation": {
                                    "action": "Consider using pd-standard",
                                    "reason": "Disk is using expensive SSD type",
                                    "suggestions": [
                                        "Switch to pd-balanced or pd-standard for general workloads",
                                        "Use SSD only for high IOPS needs",
                                    ],
                                },
                            }
                        )

                    # Disk usage metrics (read/write ops)
                    interval = monitoring_v3.TimeInterval(
                        {
                            "end_time": {"seconds": int(datetime.now().timestamp())},
                            "start_time": {
                                "seconds": int(
                                    (datetime.now() - timedelta(days=30)).timestamp()
                                )
                            },
                        }
                    )
                    read_bytes = get_metric_usage(
                        monitoring_client,
                        project_id,
                        interval,
                        "compute.googleapis.com/disk/read_bytes_count",
                        disk.id,
                    )

                    write_bytes = get_metric_usage(
                        monitoring_client,
                        project_id,
                        interval,
                        "compute.googleapis.com/disk/write_bytes_count",
                        disk.id,
                    )

                    total_activity = read_bytes + write_bytes

                    if total_activity == 0:
                        recommendations["idle_disks"].append(
                            {
                                "resource_details": disk_details,
                                "recommendation": {
                                    "action": "Review and delete if unnecessary",
                                    "reason": "No disk activity in last 30 days",
                                    "suggestions": [
                                        "Snapshot and delete if no longer needed",
                                        "Move to cheaper storage if archival is required",
                                    ],
                                },
                            }
                        )

                except Exception as disk_e:
                    logger.warning(
                        f"Warning: Could not analyze disk {disk.name}: {disk_e}"
                    )
                    continue

        from google.cloud import resourcemanager_v3

        iam_client = resourcemanager_v3.ProjectsClient(credentials=credentials)
        resource_name = f"projects/{project_id}"
        iam_policy = iam_client.get_iam_policy(request={"resource": resource_name})

        for binding in iam_policy.bindings:
            if binding.role == "roles/compute.admin" and len(binding.members) > 5:
                recommendations["iam_optimization"].append(
                    {
                        "resource_details": {"project_id": project_id},
                        "recommendation": {
                            "action": "Review compute.admin IAM role",
                            "reason": f"Too many members with compute.admin ({len(binding.members)})",
                            "suggestions": [
                                "Limit admin roles to only required users",
                                "Apply principle of least privilege",
                            ],
                        },
                    }
                )

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}


@tool
def analyze_gcp_snapshots(
    project_id: str, service_account_key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze GCP disk and database snapshots for cost optimization opportunities.

    Args:
        project_id: GCP project ID to analyze.
        service_account_key_path: Optional. Path to the service account JSON key file.

    Returns:
        Dictionary containing snapshot optimization recommendations with resource details.
    """
    from google.cloud import compute_v1
    from googleapiclient.discovery import build

    try:
        credentials = get_gcp_credentials(service_account_key_path)
        snapshot_client = compute_v1.SnapshotsClient(credentials=credentials)
        recommendations = {
            "old_disk_snapshots": [],
            "unused_disk_snapshots": [],
            "large_snapshots": [],
            "database_snapshots": [],
            "available_snapshots": [],
        }

        for snapshot in snapshot_client.list(project=project_id):
            try:
                snapshot_details = {
                    "snapshot_name": snapshot.name,
                    "disk_size_gb": snapshot.disk_size_gb,
                    "creation_timestamp": snapshot.creation_timestamp,
                    "status": snapshot.status,
                    "source_disk": (
                        snapshot.source_disk.split("/")[-1]
                        if snapshot.source_disk
                        else None
                    ),
                    "labels": dict(snapshot.labels),
                }

                recommendations["available_snapshots"].append(snapshot_details)

                # Old snapshot > 90 days
                creation_time = datetime.fromisoformat(
                    snapshot.creation_timestamp.replace("Z", "+00:00")
                )
                age_days = (datetime.now(creation_time.tzinfo) - creation_time).days
                if age_days > 90:
                    recommendations["old_disk_snapshots"].append(
                        {
                            "resource_details": snapshot_details,
                            "recommendation": {
                                "action": "Review and delete if unnecessary",
                                "reason": f"Snapshot is {age_days} days old",
                                "suggestions": [
                                    "Delete if no longer needed",
                                    "Archive to cold storage",
                                    "Implement lifecycle rules",
                                ],
                            },
                        }
                    )

                # Large snapshot > 100 GB
                if snapshot.disk_size_gb > 100:
                    recommendations["large_snapshots"].append(
                        {
                            "resource_details": snapshot_details,
                            "recommendation": {
                                "action": "Review large snapshot necessity",
                                "reason": f"Snapshot size is {snapshot.disk_size_gb} GB",
                                "suggestions": [
                                    "Use incremental snapshots",
                                    "Review full-disk usage",
                                ],
                            },
                        }
                    )

                # Unused snapshots (no source disk)
                if not snapshot.source_disk:
                    recommendations["unused_disk_snapshots"].append(
                        {
                            "resource_details": snapshot_details,
                            "recommendation": {
                                "action": "Delete unused snapshot",
                                "reason": "Source disk no longer exists",
                                "considerations": "Ensure snapshot is not needed for recovery",
                            },
                        }
                    )

            except Exception as snapshot_e:
                logger.warning(
                    f"Warning: Could not analyze snapshot {snapshot.name}: {snapshot_e}"
                )
                continue

        # Cloud SQL snapshot analysis
        try:
            sqladmin = build("sqladmin", "v1", credentials=credentials)
            instances = sqladmin.instances().list(project=project_id).execute()

            for instance in instances.get("items", []):
                try:
                    backups = (
                        sqladmin.backupRuns()
                        .list(project=project_id, instance=instance["name"])
                        .execute()
                    )

                    for backup in backups.get("items", []):
                        backup_details = {
                            "backup_id": backup.get("id"),
                            "instance_name": instance["name"],
                            "database_version": instance.get("databaseVersion"),
                            "start_time": backup.get("startTime"),
                            "end_time": backup.get("endTime"),
                            "status": backup.get("status"),
                            "type": backup.get("backupKind"),
                        }

                        recommendations["database_snapshots"].append(backup_details)

                        # Old backup check (> 30 days)
                        if (
                            backup.get("startTime")
                            and backup.get("status") == "SUCCESSFUL"
                        ):
                            start_time = datetime.fromisoformat(
                                backup["startTime"].replace("Z", "+00:00")
                            )
                            age = (datetime.now(start_time.tzinfo) - start_time).days
                            if age > 30:
                                recommendations["old_disk_snapshots"].append(
                                    {
                                        "resource_details": backup_details,
                                        "recommendation": {
                                            "action": "Review old database backups",
                                            "reason": f"Backup is {age} days old",
                                            "suggestions": [
                                                "Reduce retention",
                                                "Use PITR if available",
                                                "Clean up older backups",
                                            ],
                                        },
                                    }
                                )

                except Exception as e:
                    logger.warning(
                        f"Warning: Could not process backups for instance {instance['name']}: {e}"
                    )
                    continue

        except Exception as sql_e:
            logger.warning(f"Warning: Could not analyze Cloud SQL: {sql_e}")

        return recommendations

    except Exception as e:
        return {
            "error": str(e),
            "recommendations": [
                "Ensure valid service account credentials and required APIs are enabled."
            ],
        }


@tool
def analyze_gcp_static_ips(
    project_id: str, service_account_key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze GCP static IP addresses for cost optimization opportunities.

    Args:
        project_id: GCP project ID to analyze
        service_account_key_path: Optional. Path to the service account JSON key file.

    Returns:
        Dictionary containing static IP optimization recommendations with resource details.
    """
    from google.cloud import compute_v1

    try:
        credentials = get_gcp_credentials(service_account_key_path)

        address_client = compute_v1.AddressesClient(credentials=credentials)
        region_client = compute_v1.RegionsClient(credentials=credentials)

        recommendations = {
            "unused_static_ips": [],
            "expensive_regional_ips": [],
            "unattached_global_ips": [],
            "available_ips": [],
        }

        # Get all regions
        regions = [region.name for region in region_client.list(project=project_id)]

        for region in regions:
            try:
                # Analyze regional static IPs
                for address in address_client.list(project=project_id, region=region):
                    try:
                        address_details = {
                            "address_name": address.name,
                            "region": region,
                            "address": address.address,
                            "address_type": address.address_type,
                            "network_tier": address.network_tier,
                            "users": address.users,
                            "labels": address.labels,
                        }

                        recommendations["available_ips"].append(address_details)

                        # Check for unused static IPs
                        if not address.users:
                            recommendations["unused_static_ips"].append(
                                {
                                    "resource_details": address_details,
                                    "recommendation": {
                                        "action": "Release unused static IP",
                                        "reason": "Static IP is not attached to any resource",
                                        "considerations": "GCP charges for unassigned static IPs",
                                    },
                                }
                            )

                        # Check for expensive regional IPs (Premium tier)
                        if address.network_tier == "PREMIUM":
                            recommendations["expensive_regional_ips"].append(
                                {
                                    "resource_details": address_details,
                                    "recommendation": {
                                        "action": "Consider using Standard tier",
                                        "reason": "Static IP is using Premium network tier",
                                        "suggestions": [
                                            "Switch to Standard tier for cost savings",
                                            "Use Premium tier only for global load balancing",
                                            "Review if Premium features are actually needed",
                                        ],
                                    },
                                }
                            )

                    except Exception as address_e:
                        logger.warning(
                            f"Warning: Could not analyze address {address.name}: {address_e}"
                        )
                        continue

            except Exception as region_e:
                logger.warning(
                    f"Warning: Could not analyze region {region}: {region_e}"
                )
                continue

        # Analyze global static IPs
        try:
            global_address_client = compute_v1.GlobalAddressesClient(
                credentials=credentials
            )

            for address in global_address_client.list(project=project_id):
                try:
                    address_details = {
                        "address_name": address.name,
                        "address": address.address,
                        "address_type": address.address_type,
                        "network_tier": address.network_tier,
                        "users": address.users,
                        "labels": address.labels,
                    }

                    recommendations["available_ips"].append(address_details)

                    # Check for unattached global IPs
                    if not address.users:
                        recommendations["unattached_global_ips"].append(
                            {
                                "resource_details": address_details,
                                "recommendation": {
                                    "action": "Release unused global static IP",
                                    "reason": "Global static IP is not attached to any resource",
                                    "considerations": "Global IPs are more expensive than regional IPs",
                                },
                            }
                        )

                except Exception as global_address_e:
                    logger.warning(
                        f"Warning: Could not analyze global address {address.name}: {global_address_e}"
                    )
                    continue

        except Exception as global_e:
            logger.warning(f"Warning: Could not analyze global addresses: {global_e}")

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}


@tool
def analyze_gcp_gke_clusters(
    project_id: str, service_account_key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze GCP GKE (Google Kubernetes Engine) clusters for cost optimization opportunities.

    Args:
        project_id: GCP project ID to analyze
        service_account_key_path: Optional. Path to the service account JSON key file.

    Returns:
        Dictionary containing GKE cluster optimization recommendations with resource details
    """
    from google.cloud import compute_v1, container_v1, monitoring_v3

    try:
        credentials = get_gcp_credentials(service_account_key_path)

        gke_client = container_v1.ClusterManagerClient(credentials=credentials)
        monitoring_client = monitoring_v3.MetricServiceClient(credentials=credentials)
        compute_client = compute_v1.InstancesClient(credentials=credentials)

        recommendations = {
            "underutilized_clusters": [],
            "expensive_node_pools": [],
            "unused_clusters": [],
            "iam_optimization": [],
            "available_clusters": [],
        }

        # Get all locations (regions and zones)
        locations = ["-"]  # Global
        try:
            compute_client = compute_v1.RegionsClient(credentials=credentials)
            for region in compute_client.list(project=project_id):
                locations.append(region.name)
        except Exception as e:
            logger.warning("Could not list regions: %s", e)

        for location in locations:
            try:
                # List GKE clusters in the location
                parent = f"projects/{project_id}/locations/{location}"
                clusters = gke_client.list_clusters(parent=parent)

                for cluster in clusters.clusters:
                    try:
                        cluster_info = {
                            "cluster_name": cluster.name,
                            "location": location,
                            "version": cluster.current_master_version,
                            "status": cluster.status.name,
                            "endpoint": cluster.endpoint,
                            "create_time": cluster.create_time,
                            "network": cluster.network,
                            "subnetwork": cluster.subnetwork,
                            "node_pools_count": len(cluster.node_pools),
                            "initial_node_count": cluster.initial_node_count,
                            "tags": (
                                dict(cluster.resource_labels)
                                if cluster.resource_labels
                                else {}
                            ),
                        }

                        recommendations["available_clusters"].append(cluster_info)

                        # Check for unused clusters (no node pools or empty node pools)
                        if not cluster.node_pools:
                            recommendations["unused_clusters"].append(
                                {
                                    "resource_details": cluster_info,
                                    "recommendation": {
                                        "action": "Delete unused GKE cluster",
                                        "reason": "Cluster has no node pools",
                                        "considerations": "Ensure no workloads depend on this cluster",
                                    },
                                }
                            )
                        else:
                            # Analyze node pools
                            for node_pool in cluster.node_pools:
                                try:
                                    node_pool_info = {
                                        "node_pool_name": node_pool.name,
                                        "cluster_name": cluster.name,
                                        "location": location,
                                        "machine_type": (
                                            node_pool.config.machine_type
                                            if node_pool.config
                                            else None
                                        ),
                                        "initial_node_count": node_pool.initial_node_count,
                                        "autoscaling_enabled": (
                                            node_pool.autoscaling.enabled
                                            if node_pool.autoscaling
                                            else False
                                        ),
                                        "min_node_count": (
                                            node_pool.autoscaling.min_node_count
                                            if node_pool.autoscaling
                                            else None
                                        ),
                                        "max_node_count": (
                                            node_pool.autoscaling.max_node_count
                                            if node_pool.autoscaling
                                            else None
                                        ),
                                        "status": node_pool.status.name,
                                        "version": node_pool.version,
                                        "spot_instances": (
                                            node_pool.config.spot
                                            if node_pool.config
                                            else False
                                        ),
                                    }

                                    # Check for expensive machine types
                                    expensive_types = [
                                        "n1-standard-2",
                                        "n1-standard-4",
                                        "n2-standard-2",
                                        "n2-standard-4",
                                        "e2-standard-2",
                                        "e2-standard-4",
                                    ]
                                    if (
                                        node_pool.config
                                        and node_pool.config.machine_type
                                        in expensive_types
                                    ):
                                        recommendations["expensive_node_pools"].append(
                                            {
                                                "resource_details": node_pool_info,
                                                "recommendation": {
                                                    "action": "Consider using Spot instances or smaller machine types",
                                                    "reason": f"Node pool uses expensive machine type: {node_pool.config.machine_type}",
                                                    "suggestions": [
                                                        "Enable Spot instances for cost savings",
                                                        "Use smaller machine types if workload allows",
                                                        "Consider committed use discounts",
                                                        "Implement cluster autoscaler for dynamic scaling",
                                                    ],
                                                },
                                            }
                                        )

                                    # Check for underutilized node pools
                                    if node_pool.initial_node_count > 2 or (
                                        node_pool.autoscaling
                                        and node_pool.autoscaling.min_node_count > 2
                                    ):
                                        # Get CPU utilization metrics for the node pool
                                        end_time = datetime.utcnow()
                                        start_time = end_time - timedelta(days=7)

                                        try:
                                            interval = monitoring_v3.TimeInterval(
                                                {
                                                    "end_time": {
                                                        "seconds": int(
                                                            end_time.timestamp()
                                                        )
                                                    },
                                                    "start_time": {
                                                        "seconds": int(
                                                            start_time.timestamp()
                                                        )
                                                    },
                                                }
                                            )

                                            # Get CPU utilization for the node pool
                                            cpu_usage = get_metric_usage(
                                                monitoring_client,
                                                project_id,
                                                interval,
                                                "kubernetes.io/node/cpu/core_usage_time",
                                                cluster.name,
                                            )

                                            if (
                                                cpu_usage < 20
                                            ):  # Less than 20% CPU utilization
                                                recommendations[
                                                    "underutilized_clusters"
                                                ].append(
                                                    {
                                                        "resource_details": node_pool_info,
                                                        "recommendation": {
                                                            "action": "Reduce node pool size or enable Spot instances",
                                                            "reason": f"Low CPU utilization ({cpu_usage:.2f}%) with {node_pool.initial_node_count} nodes",
                                                            "suggestions": [
                                                                "Reduce initial node count to minimum required",
                                                                "Enable Spot instances for cost savings",
                                                                "Implement cluster autoscaler",
                                                                "Consider using GKE Autopilot for serverless workloads",
                                                            ],
                                                        },
                                                    }
                                                )
                                        except Exception as metric_e:
                                            logger.warning(
                                                "Could not get metrics for node pool %s: %s",
                                                node_pool.name,
                                                metric_e,
                                            )

                                    # Check if Spot instances are not enabled
                                    if node_pool.config and not node_pool.config.spot:
                                        recommendations["expensive_node_pools"].append(
                                            {
                                                "resource_details": node_pool_info,
                                                "recommendation": {
                                                    "action": "Enable Spot instances for cost savings",
                                                    "reason": "Node pool is using on-demand instances",
                                                    "suggestions": [
                                                        "Enable Spot instances for non-critical workloads",
                                                        "Use Spot instances for development/test environments",
                                                        "Consider mixed Spot and on-demand for production",
                                                    ],
                                                },
                                            }
                                        )

                                except Exception as node_pool_e:
                                    logger.warning(
                                        "Could not analyze node pool %s: %s",
                                        node_pool.name,
                                        node_pool_e,
                                    )
                                    continue

                        # Check IAM roles for excessive permissions
                        try:
                            from google.cloud import resourcemanager_v3

                            iam_client = resourcemanager_v3.ProjectsClient(
                                credentials=credentials
                            )
                            resource_name = f"projects/{project_id}"
                            iam_policy = iam_client.get_iam_policy(
                                request={"resource": resource_name}
                            )

                            for binding in iam_policy.bindings:
                                if (
                                    binding.role == "roles/container.admin"
                                    and len(binding.members) > 3
                                ):
                                    recommendations["iam_optimization"].append(
                                        {
                                            "resource_details": {
                                                "cluster_name": cluster.name,
                                                "project_id": project_id,
                                            },
                                            "recommendation": {
                                                "action": "Review GKE cluster IAM permissions",
                                                "reason": f"Project has {len(binding.members)} container admins",
                                                "suggestions": [
                                                    "Apply principle of least privilege",
                                                    "Review and remove unnecessary permissions",
                                                    "Use custom roles instead of predefined roles",
                                                    "Regularly audit IAM permissions",
                                                ],
                                            },
                                        }
                                    )
                        except Exception as iam_e:
                            logger.warning(
                                "Could not analyze IAM for cluster %s: %s",
                                cluster.name,
                                iam_e,
                            )

                    except Exception as cluster_e:
                        logger.warning(
                            "Could not analyze cluster %s: %s", cluster.name, cluster_e
                        )
                        continue

            except Exception as location_e:
                logger.warning(
                    "Could not analyze GKE clusters in location %s: %s",
                    location,
                    location_e,
                )
                continue

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}


@tool
def analyze_gcp_bigquery(
    project_id: str, service_account_key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze GCP BigQuery datasets and tables for cost optimization opportunities.

    Args:
        project_id: GCP project ID to analyze
        service_account_key_path: Optional. Path to the service account JSON key file.

    Returns:
        Dictionary containing BigQuery optimization recommendations with resource details.
    """
    from datetime import datetime, timedelta

    from google.cloud import bigquery

    try:
        credentials = get_gcp_credentials(service_account_key_path)
        bq_client = bigquery.Client(project=project_id, credentials=credentials)

        recommendations = {
            "large_tables": [],
            "unused_tables": [],
            "long_retention_tables": [],
            "available_tables": [],
        }

        # Analyze all datasets and tables
        for dataset in bq_client.list_datasets():
            dataset_ref = dataset.reference
            for table in bq_client.list_tables(dataset_ref):
                try:
                    table_ref = table.reference
                    table_obj = bq_client.get_table(table_ref)
                    table_details = {
                        "dataset_id": dataset_ref.dataset_id,
                        "table_id": table_ref.table_id,
                        "project_id": project_id,
                        "location": table_obj.location,
                        "num_rows": table_obj.num_rows,
                        "size_bytes": table_obj.num_bytes,
                        "created": (
                            table_obj.created.isoformat() if table_obj.created else None
                        ),
                        "expires": (
                            table_obj.expires.isoformat() if table_obj.expires else None
                        ),
                        "labels": table_obj.labels,
                    }
                    recommendations["available_tables"].append(table_details)

                    # Large table check (> 1 TB)
                    if table_obj.num_bytes and table_obj.num_bytes > 1_000_000_000_000:
                        recommendations["large_tables"].append(
                            {
                                "resource_details": table_details,
                                "recommendation": {
                                    "action": "Partition or delete large table",
                                    "reason": f"Table size is {table_obj.num_bytes / 1_000_000_000_000:.2f} TB",
                                    "suggestions": [
                                        "Partition tables by date or other fields",
                                        "Delete old or unused data",
                                        "Export and archive infrequently accessed data",
                                    ],
                                },
                            }
                        )

                    # Unused table check (no queries in last 90 days)
                    last_90_days = datetime.utcnow() - timedelta(days=90)
                    # Table.last_modified is updated on schema/data change, not query, so we use metadata
                    if table_obj.num_rows == 0 or (
                        table_obj.modified and table_obj.modified < last_90_days
                    ):
                        recommendations["unused_tables"].append(
                            {
                                "resource_details": table_details,
                                "recommendation": {
                                    "action": "Delete or archive unused table",
                                    "reason": "Table has not been modified or queried in the last 90 days",
                                    "suggestions": [
                                        "Delete if no longer needed",
                                        "Export to Cloud Storage for archival",
                                    ],
                                },
                            }
                        )

                    # Long retention check (no expiration set)
                    if not table_obj.expires:
                        recommendations["long_retention_tables"].append(
                            {
                                "resource_details": table_details,
                                "recommendation": {
                                    "action": "Set table expiration",
                                    "reason": "Table has no expiration and may accumulate costs over time",
                                    "suggestions": [
                                        "Set expiration for temporary or staging tables",
                                        "Regularly review tables without expiration",
                                    ],
                                },
                            }
                        )

                except Exception as table_e:
                    logger.warning(
                        f"Warning: Could not analyze table {table_ref}: {table_e}"
                    )
                    continue

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}
