from azure.identity import (
    DefaultAzureCredential,
    ClientSecretCredential
)
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.resource import ResourceManagementClient
from typing import Optional, Tuple


def get_azure_credentials(
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None
):
    """
    Returns an Azure credential. Supports:
    - Client credentials (service principal)
    - Default Azure credential chain (CLI, managed identity, env vars)
    """
    if tenant_id and client_id and client_secret:
        return ClientSecretCredential(tenant_id, client_id, client_secret)
    return DefaultAzureCredential()


def get_subscription_id(credential=None) -> Tuple[Optional[str], Optional[str]]:
    try:
        if credential is None:
            credential = get_azure_credentials()

        sub_client = SubscriptionClient(credential)
        subs = list(sub_client.subscriptions.list())

        if not subs:
            return None, "No subscriptions found."

        return subs[0].subscription_id, None

    except Exception as e:
        return None, str(e)


def get_resource_client(subscription_id: str, credential=None) -> ResourceManagementClient:
    if credential is None:
        credential = get_azure_credentials()
    return ResourceManagementClient(credential, subscription_id)
