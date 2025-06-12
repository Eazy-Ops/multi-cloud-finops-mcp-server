# clouds/azure/client.py

from azure.identity import DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.resource import ResourceManagementClient
from typing import Optional, Tuple


def get_azure_credentials():
    """
    Returns a DefaultAzureCredential instance for authenticating with Azure SDKs.
    This works with environment variables, managed identities, or Azure CLI.
    """
    return DefaultAzureCredential()


def get_subscription_id(credential=None) -> Tuple[Optional[str], Optional[str]]:
    """
    Get the default subscription ID using the provided credential.
    """
    try:
        if credential is None:
            credential = get_azure_credentials()

        sub_client = SubscriptionClient(credential)
        subs = list(sub_client.subscriptions.list())

        if not subs:
            return None, "No subscriptions found."

        default_sub = subs[0]
        return default_sub.subscription_id, None

    except Exception as e:
        return None, str(e)


def get_resource_client(subscription_id: str, credential=None) -> ResourceManagementClient:
    """
    Returns a ResourceManagementClient for managing Azure resources.
    """
    if credential is None:
        credential = get_azure_credentials()

    return ResourceManagementClient(credential, subscription_id)
