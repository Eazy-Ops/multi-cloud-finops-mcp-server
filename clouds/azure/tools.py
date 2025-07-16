import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.containerservice import ContainerServiceClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.storage import StorageManagementClient
from langchain.tools import tool

from clouds.azure.client import get_azure_credentials
from clouds.azure.utils import (get_budget_data, get_cost_breakdown,
                                get_stopped_vms, get_total_bytes,
                                get_unattached_disks)

logger = logging.getLogger(__name__)


@tool
def get_azure_cost(
    subscription_id: str,
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
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
            "error": "No Azure cost data found for the current month.",
        }
    return {
        "subscription_id": subscription_id,
        "cost_summary": cost_data,
        "error": error,
    }


@tool
def run_azure_finops_audit(
    subscription_id: str,
    regions: List[str],
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
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
        },
    }


@tool
def analyze_azure_disks(
    subscription_id: str, service_principal_credentials: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Analyze Azure managed disks for cost optimization opportunities.

    Args:
        subscription_id: Azure subscription ID
        service_principal_credentials: Optional. Dictionary containing service principal credentials:
            {
                'client_id': 'your_client_id',
                'client_secret': 'your_client_secret',
                'tenant_id': 'your_tenant_id'
            }

    Returns:
        Dictionary containing disk optimization recommendations with resource details
    """
    try:
        credentials = get_azure_credentials(service_principal_credentials)
        compute_client = ComputeManagementClient(credentials, subscription_id)
        monitor_client = MonitorManagementClient(credentials, subscription_id)

        recommendations = {
            "unattached_disks": [],
            "idle_disks": [],
            "expensive_disk_types": [],
            "iam_optimization": [],
            "available_disks": [],
        }
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=30)
        disks = compute_client.disks.list()
        for disk in disks:
            disk_details = {
                "disk_id": disk.id,
                "name": disk.name,
                "location": disk.location,
                "sku": disk.sku.name if disk.sku else None,
                "size_gb": disk.disk_size_gb,
                "os_type": str(disk.os_type),
                "creation_time": (
                    disk.time_created.isoformat() if disk.time_created else None
                ),
                "tags": disk.tags,
            }

            recommendations["available_disks"].append(disk_details)
            if not disk.managed_by:
                recommendations["unattached_disks"].append(
                    {
                        "resource_details": disk_details,
                        "recommendation": {
                            "action": "Delete or snapshot unattached disk",
                            "reason": "Disk is not attached to any VM",
                            "considerations": "Ensure disk is not needed before deletion",
                        },
                    }
                )

            if disk.sku and disk.sku.name in ["Premium_LRS", "Premium_ZRS"]:
                recommendations["expensive_disk_types"].append(
                    {
                        "resource_details": disk_details,
                        "recommendation": {
                            "action": "Consider using Standard SSD",
                            "reason": "Disk is using Premium storage",
                            "suggestions": [
                                "Switch to StandardSSD_LRS for general workloads",
                                "Use Premium storage only for high IOPS needs",
                                "Consider Standard_LRS for development/test workloads",
                            ],
                        },
                    }
                )

            if disk.managed_by:
                try:
                    metrics_data = monitor_client.metrics.list(
                        resource_uri=disk.id,
                        timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                        interval="P1D",
                        metricnames="UsedSize",
                        aggregation="Average",
                    )

                    total_used = sum(
                        dp.average
                        for dp in metrics_data.value[0].timeseries[0].data
                        if dp.average is not None
                    )

                    if total_used == 0:
                        recommendations["idle_disks"].append(
                            {
                                "resource_details": disk_details,
                                "recommendation": {
                                    "action": "Review and delete if unnecessary",
                                    "reason": "No disk usage detected in last 30 days",
                                    "suggestions": [
                                        "Snapshot and delete if no longer needed",
                                        "Move to cheaper storage if archival is required",
                                    ],
                                },
                            }
                        )
                except Exception:
                    continue
        try:
            auth_client = AuthorizationManagementClient(credentials, subscription_id)
            role_assignments = auth_client.role_assignments.list()
            for assignment in role_assignments:
                if (
                    "Microsoft.Compute/disks/write"
                    in assignment.role_definition_id.lower()
                ):
                    recommendations["iam_optimization"].append(
                        {
                            "resource_details": {"role_assignment_id": assignment.id},
                            "recommendation": {
                                "action": "Review disk management permissions",
                                "reason": f"Broad disk permissions granted to principal {assignment.principal_id}",
                                "suggestions": [
                                    "Enforce least privilege principle",
                                    "Restrict disk write access to necessary roles",
                                    "Audit role definitions for over-privilege",
                                ],
                            },
                        }
                    )
        except Exception:
            pass

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}


@tool
def analyze_azure_network(
    subscription_id: str, service_principal_credentials: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Analyze Azure network resources for cost optimization opportunities.

    Args:
        subscription_id: Azure subscription ID
        service_principal_credentials: Optional. Dictionary containing service principal credentials:
            {
                'client_id': 'your_client_id',
                'client_secret': 'your_client_secret',
                'tenant_id': 'your_tenant_id'
            }

    Returns:
        Dictionary containing network optimization recommendations with resource details
    """
    try:
        credentials = get_azure_credentials(service_principal_credentials)
        network_client = NetworkManagementClient(credentials, subscription_id)
        monitor_client = MonitorManagementClient(credentials, subscription_id)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=30)

        recommendations = {
            "unused_public_ips": [],
            "idle_load_balancers": [],
            "expensive_nat_gateways": [],
            "unused_nsgs": [],
            "available_resources": {
                "public_ips": [],
                "load_balancers": [],
                "nat_gateways": [],
                "nsgs": [],
            },
        }

        # Analyze Public IPs
        public_ips = network_client.public_ip_addresses.list_all()
        for ip in public_ips:
            ip_details = {
                "ip_id": ip.id,
                "name": ip.name,
                "location": ip.location,
                "ip_address": ip.ip_address,
                "allocation_method": ip.public_ip_allocation_method,
                "sku": ip.sku.name if ip.sku else None,
                "tags": ip.tags,
            }

            recommendations["available_resources"]["public_ips"].append(ip_details)

            if not ip.ip_configuration:
                recommendations["unused_public_ips"].append(
                    {
                        "resource_details": ip_details,
                        "recommendation": {
                            "action": "Delete unused public IP",
                            "reason": "Public IP is not associated with any resource",
                            "considerations": "Azure charges for unassociated public IPs",
                        },
                    }
                )

        # Analyze Load Balancers
        load_balancers = network_client.load_balancers.list_all()
        for lb in load_balancers:
            lb_details = {
                "lb_id": lb.id,
                "name": lb.name,
                "location": lb.location,
                "sku": lb.sku.name if lb.sku else None,
                "frontend_ip_configurations": len(lb.frontend_ip_configurations),
                "backend_address_pools": len(lb.backend_address_pools),
                "tags": lb.tags,
            }

            recommendations["available_resources"]["load_balancers"].append(lb_details)

            byte_count = monitor_client.metrics.list(
                resource_uri=lb.id,
                timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                interval="P1D",
                metricnames="ByteCount",
                aggregation="Total",
            )

            total_bytes = get_total_bytes(byte_count)
            if total_bytes == 0:
                recommendations["idle_load_balancers"].append(
                    {
                        "resource_details": lb_details,
                        "recommendation": {
                            "action": "Delete idle load balancer",
                            "reason": "No traffic in last 30 days",
                            "considerations": "Ensure no critical services before deletion",
                        },
                    }
                )

        # Analyze NAT Gateways
        nat_gateways = network_client.nat_gateways.list_all()
        for nat in nat_gateways:
            nat_details = {
                "nat_id": nat.id,
                "name": nat.name,
                "location": nat.location,
                "sku": nat.sku.name if nat.sku else None,
                "idle_timeout": nat.idle_timeout_in_minutes,
                "tags": nat.tags,
            }

            recommendations["available_resources"]["nat_gateways"].append(nat_details)
            byte_count = monitor_client.metrics.list(
                resource_uri=nat.id,
                timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                interval="P1D",
                metricnames="ByteCount",
                aggregation="Total",
            )

            total_bytes = get_total_bytes(byte_count)
            if total_bytes < 1000000:  # Less than 1MB
                recommendations["expensive_nat_gateways"].append(
                    {
                        "resource_details": nat_details,
                        "recommendation": {
                            "action": "Consider using NAT VM",
                            "reason": "Low NAT Gateway usage",
                            "suggestions": [
                                "Replace with NAT VM for cost savings",
                                "Consider using Service Endpoints where possible",
                                "Review if NAT is actually needed",
                            ],
                        },
                    }
                )

        # Analyze Network Security Groups
        nsgs = network_client.network_security_groups.list_all()
        for nsg in nsgs:
            nsg_details = {
                "nsg_id": nsg.id,
                "name": nsg.name,
                "location": nsg.location,
                "security_rules": len(nsg.security_rules),
                "default_security_rules": len(nsg.default_security_rules),
                "tags": nsg.tags,
            }

            recommendations["available_resources"]["nsgs"].append(nsg_details)

            # Check for unused NSGs
            if not nsg.security_rules and not nsg.default_security_rules:
                recommendations["unused_nsgs"].append(
                    {
                        "resource_details": nsg_details,
                        "recommendation": {
                            "action": "Delete unused NSG",
                            "reason": "No security rules defined",
                            "considerations": "Ensure no resources are using this NSG",
                        },
                    }
                )

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}


@tool
def analyze_azure_storage(
    subscription_id: str, service_principal_credentials: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Analyze Azure Storage accounts for cost optimization opportunities.

    Args:
        subscription_id: Azure subscription ID
        service_principal_credentials: Optional. Dictionary containing service principal credentials:
            {
                'client_id': 'your_client_id',
                'client_secret': 'your_client_secret',
                'tenant_id': 'your_tenant_id'
            }

    Returns:
        Dictionary containing storage optimization recommendations with resource details
    """

    try:
        credentials = get_azure_credentials(service_principal_credentials)
        storage_client = StorageManagementClient(credentials, subscription_id)
        monitor_client = MonitorManagementClient(credentials, subscription_id)

        recommendations = {
            "lifecycle_policy_recommendations": [],
            "storage_tier_optimization": [],
            "unused_storage_accounts": [],
            "large_containers": [],
            "versioning_optimization": [],
            "available_storage_accounts": [],
        }

        # Get all storage accounts
        storage_accounts = storage_client.storage_accounts.list()
        for account in storage_accounts:
            account_details = {
                "account_id": account.id,
                "name": account.name,
                "location": account.location,
                "sku": account.sku.name,
                "kind": account.kind,
                "access_tier": (
                    account.access_tier if hasattr(account, "access_tier") else None
                ),
                "creation_time": (
                    account.creation_time.isoformat() if account.creation_time else None
                ),
                "tags": account.tags,
            }

            recommendations["available_storage_accounts"].append(account_details)

            # Get storage metrics
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=30)

            capacity = monitor_client.metrics.list(
                resource_uri=account.id,
                timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                interval="PT1H",
                metricnames="UsedCapacity",
                aggregation="Total",
            )

            total_capacity = sum(
                point.total
                for point in capacity.value[0].timeseries[0].data
                if point.total is not None
            )

            # Check for unused storage accounts
            if total_capacity == 0:
                recommendations["unused_storage_accounts"].append(
                    {
                        "resource_details": account_details,
                        "recommendation": {
                            "action": "Delete unused storage account",
                            "reason": "No data stored in last 30 days",
                            "considerations": "Ensure no critical data before deletion",
                        },
                    }
                )

            # Check storage tier optimization
            if (
                account.sku.name == "Standard_LRS" and total_capacity > 1000000000
            ):  # 1GB
                recommendations["storage_tier_optimization"].append(
                    {
                        "resource_details": account_details,
                        "recommendation": {
                            "action": "Consider storage tier change",
                            "reason": f"Large storage account ({total_capacity/1000000000:.2f} GB) using Standard storage",
                            "suggestions": [
                                "Consider Cool tier for infrequently accessed data",
                                "Use Archive tier for long-term storage",
                                "Enable lifecycle management for automatic tiering",
                            ],
                        },
                    }
                )

            # Check for lifecycle management
            try:
                lifecycle = storage_client.management_policies.get(
                    account.name, "default"
                )
                if not lifecycle.policy.rules:
                    recommendations["lifecycle_policy_recommendations"].append(
                        {
                            "resource_details": account_details,
                            "recommendation": {
                                "action": "Add lifecycle management rules",
                                "reason": "No lifecycle rules configured",
                                "suggested_rules": [
                                    "Move to Cool tier after 30 days",
                                    "Move to Archive tier after 90 days",
                                    "Delete old versions after 365 days",
                                ],
                            },
                        }
                    )
            except Exception:
                recommendations["lifecycle_policy_recommendations"].append(
                    {
                        "resource_details": account_details,
                        "recommendation": {
                            "action": "Add lifecycle management rules",
                            "reason": "No lifecycle rules configured",
                            "suggested_rules": [
                                "Move to Cool tier after 30 days",
                                "Move to Archive tier after 90 days",
                                "Delete old versions after 365 days",
                            ],
                        },
                    }
                )

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}


@tool
def analyze_azure_instances(
    subscription_id: str, service_principal_credentials: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Analyze Azure Virtual Machines (instances) for cost optimization opportunities.

    Args:
        subscription_id: Azure subscription ID.
        service_principal_credentials: Optional dictionary containing service principal credentials:
            {
                'client_id': 'your_client_id',
                'client_secret': 'your_client_secret',
                'tenant_id': 'your_tenant_id'
            }

    Returns:
        Dictionary containing VM optimization recommendations with resource details.
    """
    try:
        credentials = get_azure_credentials(service_principal_credentials)
        compute_client = ComputeManagementClient(credentials, subscription_id)
        monitor_client = MonitorManagementClient(credentials, subscription_id)
        auth_client = AuthorizationManagementClient(credentials, subscription_id)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=30)

        recommendations = {
            "stopped_instances": [],
            "underutilized_instances": [],
            "expensive_skus": [],
            "iam_optimization": [],
            "available_instances": [],
        }

        vms = compute_client.virtual_machines.list_all()

        for vm in vms:
            instance_details = {
                "vm_id": vm.id,
                "name": vm.name,
                "location": vm.location,
                "size": vm.hardware_profile.vm_size if vm.hardware_profile else None,
                "os_type": (
                    vm.storage_profile.os_disk.os_type.value
                    if vm.storage_profile and vm.storage_profile.os_disk
                    else None
                ),
                "tags": vm.tags,
            }

            recommendations["available_instances"].append(instance_details)

            # Check if VM is deallocated (stopped)
            instance_view = compute_client.virtual_machines.instance_view(
                resource_group_name=vm.id.split("/")[4], vm_name=vm.name
            )
            statuses = instance_view.statuses
            power_state = next(
                (s.display_status for s in statuses if s.code.startswith("PowerState")),
                None,
            )

            if power_state == "VM deallocated":
                recommendations["stopped_instances"].append(
                    {
                        "resource_details": instance_details,
                        "recommendation": {
                            "action": "Deallocate or delete stopped VM",
                            "reason": "VM is stopped but still incurs cost for attached disks",
                            "suggestions": [
                                "Delete if no longer needed",
                                "Start only when required",
                            ],
                        },
                    }
                )

            # Check for expensive VM sizes
            if vm.hardware_profile and vm.hardware_profile.vm_size.startswith(
                "Standard_D"
            ):
                recommendations["expensive_skus"].append(
                    {
                        "resource_details": instance_details,
                        "recommendation": {
                            "action": "Consider resizing to cheaper instance type",
                            "reason": "D-series VMs are generally more expensive",
                            "suggestions": [
                                "Switch to B-series or A-series for dev/test workloads",
                                "Evaluate usage pattern and IOPS before resizing",
                            ],
                        },
                    }
                )

            # Check CPU usage over last 30 days
            try:
                metrics = monitor_client.metrics.list(
                    resource_uri=vm.id,
                    timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                    interval="P1D",
                    metricnames="Percentage CPU",
                    aggregation="Average",
                )

                if (
                    metrics.value
                    and metrics.value[0].timeseries
                    and metrics.value[0].timeseries[0].data
                ):
                    total_cpu = sum(
                        dp.average
                        for dp in metrics.value[0].timeseries[0].data
                        if dp.average is not None
                    )
                    if total_cpu == 0:
                        recommendations["underutilized_instances"].append(
                            {
                                "resource_details": instance_details,
                                "recommendation": {
                                    "action": "Review underutilized instance",
                                    "reason": "No CPU activity detected in last 30 days",
                                    "suggestions": [
                                        "Shutdown or resize instance",
                                        "Move to reserved instance or spot pricing",
                                    ],
                                },
                            }
                        )
            except Exception as metric_err:
                logger.warning("Metric error for VM %s: %s", vm.name, metric_err)
                continue

        # IAM review
        try:
            role_assignments = auth_client.role_assignments.list()
            for assignment in role_assignments:
                if (
                    "Microsoft.Compute/virtualMachines/write"
                    in assignment.role_definition_id.lower()
                ):
                    recommendations["iam_optimization"].append(
                        {
                            "resource_details": {"role_assignment_id": assignment.id},
                            "recommendation": {
                                "action": "Review VM management permissions",
                                "reason": f"Broad VM permissions granted to principal {assignment.principal_id}",
                                "suggestions": [
                                    "Enforce least privilege principle",
                                    "Restrict VM write access to essential users",
                                    "Audit custom roles and remove excess rights",
                                ],
                            },
                        }
                    )
        except Exception as iam_err:
            logger.warning("IAM error: %s", iam_err)

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}


@tool
def analyze_azure_snapshots(
    subscription_id: str, service_principal_credentials: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Analyze Azure managed disk snapshots and database backups for cost optimization opportunities.

    Args:
        subscription_id: Azure subscription ID
        service_principal_credentials: Optional. Dictionary containing service principal credentials:
            {
                'client_id': 'your_client_id',
                'client_secret': 'your_client_secret',
                'tenant_id': 'your_tenant_id'
            }

    Returns:
        Dictionary containing snapshot optimization recommendations with resource details
    """
    try:
        credentials = get_azure_credentials(service_principal_credentials)
        compute_client = ComputeManagementClient(credentials, subscription_id)

        recommendations = {
            "old_disk_snapshots": [],
            "unused_disk_snapshots": [],
            "large_disk_snapshots": [],
            "available_snapshots": [],
        }

        # Analyze managed disk snapshots
        snapshots = compute_client.snapshots.list()
        for snapshot in snapshots:
            try:
                snapshot_details = {
                    "snapshot_id": snapshot.id,
                    "name": snapshot.name,
                    "location": snapshot.location,
                    "disk_size_gb": snapshot.disk_size_gb,
                    "sku": snapshot.sku.name if snapshot.sku else None,
                    "creation_time": (
                        snapshot.time_created.isoformat()
                        if snapshot.time_created
                        else None
                    ),
                    "os_type": str(snapshot.os_type) if snapshot.os_type else None,
                    "source_disk_id": (
                        snapshot.creation_data.source_resource_id
                        if snapshot.creation_data
                        else None
                    ),
                    "tags": snapshot.tags,
                }

                recommendations["available_snapshots"].append(snapshot_details)

                # Check for old snapshots (older than 90 days)
                if snapshot.time_created:
                    age_days = (
                        datetime.utcnow() - snapshot.time_created.replace(tzinfo=None)
                    ).days
                    if age_days > 90:
                        recommendations["old_disk_snapshots"].append(
                            {
                                "resource_details": snapshot_details,
                                "recommendation": {
                                    "action": "Review and delete if unnecessary",
                                    "reason": f"Snapshot is {age_days} days old",
                                    "suggestions": [
                                        "Delete if no longer needed",
                                        "Archive to cheaper storage",
                                        "Implement lifecycle policies",
                                    ],
                                },
                            }
                        )

                # Check for large snapshots (> 100 GB)
                if snapshot.disk_size_gb and snapshot.disk_size_gb > 100:
                    recommendations["large_disk_snapshots"].append(
                        {
                            "resource_details": snapshot_details,
                            "recommendation": {
                                "action": "Review large snapshot necessity",
                                "reason": f"Snapshot size is {snapshot.disk_size_gb} GB",
                                "suggestions": [
                                    "Use incremental snapshots",
                                    "Review full-disk usage",
                                    "Consider compression",
                                ],
                            },
                        }
                    )

                # Check for unused snapshots (no source disk)
                if (
                    not snapshot.creation_data
                    or not snapshot.creation_data.source_resource_id
                ):
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
                    "Could not analyze snapshot %s: %s", snapshot.name, snapshot_e
                )
                continue

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}


@tool
def analyze_azure_static_ips(
    subscription_id: str, service_principal_credentials: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Analyze Azure static IP addresses for cost optimization opportunities.

    Args:
        subscription_id: Azure subscription ID
        service_principal_credentials: Optional. Dictionary containing service principal credentials:
            {
                'client_id': 'your_client_id',
                'client_secret': 'your_client_secret',
                'tenant_id': 'your_tenant_id'
            }

    Returns:
        Dictionary containing static IP optimization recommendations with resource details
    """
    try:
        credentials = get_azure_credentials(service_principal_credentials)
        network_client = NetworkManagementClient(credentials, subscription_id)

        recommendations = {
            "unused_public_ips": [],
            "expensive_public_ips": [],
            "available_ips": [],
        }

        # Get all resource groups
        resource_groups = []
        try:
            from azure.mgmt.resource import ResourceManagementClient

            resource_client = ResourceManagementClient(credentials, subscription_id)
            resource_groups = [rg.name for rg in resource_client.resource_groups.list()]
        except Exception as rg_e:
            logger.warning("Could not list resource groups: %s", rg_e)

        for resource_group in resource_groups:
            try:
                # Analyze Public IP addresses
                public_ips = network_client.public_ip_addresses.list(resource_group)
                for public_ip in public_ips:
                    try:
                        ip_details = {
                            "ip_id": public_ip.id,
                            "name": public_ip.name,
                            "resource_group": resource_group,
                            "location": public_ip.location,
                            "ip_address": public_ip.ip_address,
                            "allocation_method": public_ip.public_ip_allocation_method,
                            "sku": public_ip.sku.name if public_ip.sku else None,
                            "tags": public_ip.tags,
                        }

                        recommendations["available_ips"].append(ip_details)

                        # Check for unused public IPs
                        if not public_ip.ip_configuration:
                            recommendations["unused_public_ips"].append(
                                {
                                    "resource_details": ip_details,
                                    "recommendation": {
                                        "action": "Delete unused public IP",
                                        "reason": "Public IP is not associated with any resource",
                                        "considerations": "Azure charges for unassigned public IPs",
                                    },
                                }
                            )

                        # Check for expensive public IPs (Standard SKU)
                        if public_ip.sku and public_ip.sku.name == "Standard":
                            recommendations["expensive_public_ips"].append(
                                {
                                    "resource_details": ip_details,
                                    "recommendation": {
                                        "action": "Consider using Basic SKU",
                                        "reason": "Public IP is using Standard SKU",
                                        "suggestions": [
                                            "Switch to Basic SKU for cost savings",
                                            "Use Standard SKU only for specific features",
                                            "Review if Standard features are needed",
                                        ],
                                    },
                                }
                            )

                    except Exception as ip_e:
                        logger.warning(
                            "Could not analyze public IP %s: %s", public_ip.name, ip_e
                        )
                        continue

            except Exception as rg_network_e:
                logger.warning(
                    "Could not analyze network resources in resource group %s: %s",
                    resource_group,
                    rg_network_e,
                )
                continue

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}


@tool
def analyze_azure_aks_clusters(
    subscription_id: str, service_principal_credentials: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Analyze Azure AKS (Azure Kubernetes Service) clusters for cost optimization opportunities.

    Args:
        subscription_id: Azure subscription ID
        service_principal_credentials: Optional. Dictionary containing service principal credentials:
            {
                'client_id': 'your_client_id',
                'client_secret': 'your_client_secret',
                'tenant_id': 'your_tenant_id'
            }

    Returns:
        Dictionary containing AKS cluster optimization recommendations with resource details
    """

    try:
        credentials = get_azure_credentials(service_principal_credentials)

        aks_client = ContainerServiceClient(credentials, subscription_id)
        monitor_client = MonitorManagementClient(credentials, subscription_id)

        recommendations = {
            "underutilized_clusters": [],
            "expensive_node_pools": [],
            "unused_clusters": [],
            "iam_optimization": [],
            "available_clusters": [],
        }

        # List all AKS clusters
        clusters = aks_client.managed_clusters.list()

        for cluster in clusters:
            try:
                cluster_info = {
                    "cluster_name": cluster.name,
                    "location": cluster.location,
                    "version": cluster.kubernetes_version,
                    "status": cluster.provisioning_state,
                    "fqdn": cluster.fqdn,
                    "created_at": (
                        cluster.creation_time.isoformat()
                        if cluster.creation_time
                        else None
                    ),
                    "resource_group": cluster.id.split("/")[4],
                    "node_count": (
                        cluster.agent_pool_profiles[0].count
                        if cluster.agent_pool_profiles
                        else 0
                    ),
                    "vm_size": (
                        cluster.agent_pool_profiles[0].vm_size
                        if cluster.agent_pool_profiles
                        else None
                    ),
                    "tags": cluster.tags,
                }

                recommendations["available_clusters"].append(cluster_info)

                # Check for unused clusters (no agent pools or empty agent pools)
                if not cluster.agent_pool_profiles:
                    recommendations["unused_clusters"].append(
                        {
                            "resource_details": cluster_info,
                            "recommendation": {
                                "action": "Delete unused AKS cluster",
                                "reason": "Cluster has no agent pools",
                                "considerations": "Ensure no workloads depend on this cluster",
                            },
                        }
                    )
                else:
                    # Analyze agent pools
                    for agent_pool in cluster.agent_pool_profiles:
                        try:
                            agent_pool_info = {
                                "pool_name": agent_pool.name,
                                "cluster_name": cluster.name,
                                "location": cluster.location,
                                "vm_size": agent_pool.vm_size,
                                "count": agent_pool.count,
                                "min_count": (
                                    agent_pool.min_count
                                    if hasattr(agent_pool, "min_count")
                                    else None
                                ),
                                "max_count": (
                                    agent_pool.max_count
                                    if hasattr(agent_pool, "max_count")
                                    else None
                                ),
                                "enable_auto_scaling": (
                                    agent_pool.enable_auto_scaling
                                    if hasattr(agent_pool, "enable_auto_scaling")
                                    else False
                                ),
                                "mode": agent_pool.mode,
                                "os_type": agent_pool.os_type,
                                "spot_max_price": (
                                    agent_pool.spot_max_price
                                    if hasattr(agent_pool, "spot_max_price")
                                    else None
                                ),
                            }

                            # Check for expensive VM sizes
                            expensive_sizes = [
                                "Standard_D2s_v3",
                                "Standard_D4s_v3",
                                "Standard_E2s_v3",
                                "Standard_E4s_v3",
                                "Standard_F4s_v2",
                                "Standard_F8s_v2",
                            ]
                            if agent_pool.vm_size in expensive_sizes:
                                recommendations["expensive_node_pools"].append(
                                    {
                                        "resource_details": agent_pool_info,
                                        "recommendation": {
                                            "action": "Consider using Spot instances or smaller VM sizes",
                                            "reason": f"Agent pool uses expensive VM size: {agent_pool.vm_size}",
                                            "suggestions": [
                                                "Enable Spot instances for cost savings",
                                                "Use smaller VM sizes if workload allows",
                                                "Consider reserved instances for predictable workloads",
                                                "Implement cluster autoscaler for dynamic scaling",
                                            ],
                                        },
                                    }
                                )

                            # Check for underutilized agent pools
                            if agent_pool.count > 2:
                                # Get CPU utilization metrics for the agent pool
                                end_time = datetime.utcnow()
                                start_time = end_time - timedelta(days=7)

                                try:
                                    # Get metrics for the agent pool
                                    metrics = monitor_client.metrics.list(
                                        resource_uri=cluster.id,
                                        timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                                        interval="P1D",
                                        metricnames="cpuUsageNanoCores",
                                        aggregation="Average",
                                    )

                                    if (
                                        metrics.value
                                        and metrics.value[0].timeseries
                                        and metrics.value[0].timeseries[0].data
                                    ):
                                        total_cpu = sum(
                                            dp.average
                                            for dp in metrics.value[0]
                                            .timeseries[0]
                                            .data
                                            if dp.average is not None
                                        )
                                        avg_cpu = (
                                            total_cpu
                                            / len(metrics.value[0].timeseries[0].data)
                                            if metrics.value[0].timeseries[0].data
                                            else 0
                                        )

                                        if (
                                            avg_cpu < 20
                                        ):  # Less than 20% CPU utilization
                                            recommendations[
                                                "underutilized_clusters"
                                            ].append(
                                                {
                                                    "resource_details": agent_pool_info,
                                                    "recommendation": {
                                                        "action": "Reduce agent pool size or enable Spot instances",
                                                        "reason": f"Low CPU utilization ({avg_cpu:.2f}%) with {agent_pool.count} nodes",
                                                        "suggestions": [
                                                            "Reduce node count to minimum required",
                                                            "Enable Spot instances for cost savings",
                                                            "Implement cluster autoscaler",
                                                            "Consider using AKS with virtual nodes for serverless workloads",
                                                        ],
                                                    },
                                                }
                                            )
                                except Exception as metric_e:
                                    logger.warning(
                                        "Could not get metrics for agent pool %s: %s",
                                        agent_pool.name,
                                        metric_e,
                                    )

                            # Check if Spot instances are not enabled
                            if not agent_pool.spot_max_price:
                                recommendations["expensive_node_pools"].append(
                                    {
                                        "resource_details": agent_pool_info,
                                        "recommendation": {
                                            "action": "Enable Spot instances for cost savings",
                                            "reason": "Agent pool is using on-demand instances",
                                            "suggestions": [
                                                "Enable Spot instances for non-critical workloads",
                                                "Use Spot instances for development/test environments",
                                                "Consider mixed Spot and on-demand for production",
                                                "Set appropriate spot max price",
                                            ],
                                        },
                                    }
                                )

                        except Exception as agent_pool_e:
                            logger.warning(
                                "Could not analyze agent pool %s: %s",
                                agent_pool.name,
                                agent_pool_e,
                            )
                            continue

                # Check IAM roles for excessive permissions
                try:
                    from azure.mgmt.authorization import \
                        AuthorizationManagementClient

                    auth_client = AuthorizationManagementClient(
                        credentials, subscription_id
                    )

                    role_assignments = auth_client.role_assignments.list()
                    for assignment in role_assignments:
                        if (
                            "Microsoft.ContainerService/managedClusters/write"
                            in assignment.role_definition_id.lower()
                        ):
                            recommendations["iam_optimization"].append(
                                {
                                    "resource_details": {
                                        "cluster_name": cluster.name,
                                        "role_assignment_id": assignment.id,
                                    },
                                    "recommendation": {
                                        "action": "Review AKS cluster IAM permissions",
                                        "reason": f"Broad AKS permissions granted to principal {assignment.principal_id}",
                                        "suggestions": [
                                            "Apply principle of least privilege",
                                            "Review and remove unnecessary permissions",
                                            "Use custom roles instead of built-in roles",
                                            "Regularly audit IAM permissions",
                                        ],
                                    },
                                }
                            )
                except Exception as iam_e:
                    logger.warning(
                        "Could not analyze IAM for cluster %s: %s", cluster.name, iam_e
                    )

            except Exception as cluster_e:
                logger.warning(
                    "Could not analyze cluster %s: %s", cluster.name, cluster_e
                )
                continue

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}


@tool
def analyze_azure_sql_databases(
    subscription_id: str, service_principal_credentials: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Analyze Azure SQL Databases for cost optimization opportunities.
    Identifies:
    - Idle databases (no connections or low DTU usage)
    - Oversized databases (high max size, low usage)
    - Long backup retention

    Args:
        subscription_id: Azure subscription ID
        service_principal_credentials: Optional. Dictionary containing service principal credentials.

    Returns:
        Dictionary containing SQL database optimization recommendations with resource details
    """
    from datetime import datetime, timedelta

    from azure.mgmt.monitor import MonitorManagementClient
    from azure.mgmt.sql import SqlManagementClient

    def extract_resource_group_from_id(resource_id: str) -> str:
        parts = resource_id.split("/")
        try:
            rg_index = parts.index("resourceGroups")
            return parts[rg_index + 1]
        except (ValueError, IndexError):
            return None

    try:
        credentials = get_azure_credentials(service_principal_credentials)
        sql_client = SqlManagementClient(credentials, subscription_id)
        monitor_client = MonitorManagementClient(credentials, subscription_id)

        recommendations = {
            "idle_databases": [],
            "oversized_databases": [],
            "long_backup_retention": [],
            "available_databases": [],
        }

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=30)

        for server in sql_client.servers.list():
            resource_group = extract_resource_group_from_id(server.id)
            for db in sql_client.databases.list_by_server(resource_group, server.name):
                if db.name.lower() == "master":
                    continue
                db_details = {
                    "server_name": server.name,
                    "database_name": db.name,
                    "location": db.location,
                    "edition": getattr(db, "edition", "Unknown"),
                    "max_size_bytes": db.max_size_bytes,
                    "status": db.status,
                    "creation_date": (
                        db.creation_date.isoformat() if db.creation_date else None
                    ),
                    "current_service_objective": getattr(
                        db, "current_service_objective_name", None
                    ),
                    "requested_service_objective": getattr(
                        db, "requested_service_objective_name", None
                    ),
                    "tags": db.tags,
                }
                recommendations["available_databases"].append(db_details)

                # Check for idle databases (low DTU usage)
                try:
                    metrics = monitor_client.metrics.list(
                        resource_uri=db.id,
                        timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                        interval="P1D",
                        metricnames="cpu_percent",
                        aggregation="Average",
                    )
                    if (
                        metrics.value
                        and metrics.value[0].timeseries
                        and metrics.value[0].timeseries[0].data
                    ):
                        avg_cpu = sum(
                            dp.average
                            for dp in metrics.value[0].timeseries[0].data
                            if dp.average is not None
                        ) / len(metrics.value[0].timeseries[0].data)
                        if avg_cpu < 5:
                            recommendations["idle_databases"].append(
                                {
                                    "resource_details": db_details,
                                    "recommendation": {
                                        "action": "Review or delete idle database",
                                        "reason": f"Average CPU usage is {avg_cpu:.2f}% in last 30 days",
                                        "suggestions": [
                                            "Delete if no longer needed",
                                            "Scale down to lower tier",
                                            "Pause if using serverless tier",
                                        ],
                                    },
                                }
                            )
                except Exception as metric_e:
                    logger.warning(
                        f"Could not get DTU metrics for database {db.name}: {metric_e}"
                    )

                # Check for oversized databases (large max size, low usage)
                if (
                    db.max_size_bytes and db.max_size_bytes > 100 * 1024 * 1024 * 1024
                ):  # >100GB
                    recommendations["oversized_databases"].append(
                        {
                            "resource_details": db_details,
                            "recommendation": {
                                "action": "Reduce max size or archive data",
                                "reason": f"Database max size is {db.max_size_bytes / (1024**3):.2f} GB",
                                "suggestions": [
                                    "Reduce max size if possible",
                                    "Archive old data to cheaper storage",
                                    "Review data retention policies",
                                ],
                            },
                        }
                    )

                # Check for long backup retention
                if (
                    hasattr(db, "backup_retention_days")
                    and db.backup_retention_days
                    and db.backup_retention_days > 14
                ):
                    recommendations["long_backup_retention"].append(
                        {
                            "resource_details": db_details,
                            "recommendation": {
                                "action": "Reduce backup retention period",
                                "reason": f"Backup retention is {db.backup_retention_days} days",
                                "suggestions": [
                                    "Reduce retention to 7-14 days if possible",
                                    "Export backups to cheaper storage",
                                ],
                            },
                        }
                    )

        return recommendations

    except Exception as e:
        return {"error": str(e), "recommendations": {}}
