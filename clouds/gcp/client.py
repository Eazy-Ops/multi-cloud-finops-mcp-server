# clouds/gcp/client.py

from google.auth import default
from google.oauth2 import service_account
from google.cloud import billing_v1
from typing import Optional

def get_gcp_credentials(service_account_key_path: Optional[str] = None):
    """
    Return GCP credentials either from ADC or a given service account key.
    """
    if service_account_key_path:
        credentials = service_account.Credentials.from_service_account_file(
            service_account_key_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    else:
        credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return credentials

def get_billing_client(service_account_key_path: Optional[str] = None):
    """
    Returns a Cloud Billing client using appropriate credentials.
    """
    credentials = get_gcp_credentials(service_account_key_path)
    return billing_v1.CloudBillingClient(credentials=credentials)
