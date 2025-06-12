# clouds/gcp/client.py

from google.auth import default
from google.oauth2 import service_account
from google.cloud import billing_v1
from google.auth.credentials import Credentials
from typing import Optional
import os


def get_gcp_credentials(service_account_key_path: Optional[str] = None) -> Credentials:
    """
    Return GCP credentials from:
    - A service account key file (if provided),
    - Or ADC (Application Default Credentials),
    - Or fallback to gcloud CLI user credentials if configured.
    """
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]

    if service_account_key_path:
        return service_account.Credentials.from_service_account_file(
            service_account_key_path, scopes=scopes
        )

    # Try ADC (may use gcloud CLI login if previously run `gcloud auth application-default login`)
    credentials, _ = default(scopes=scopes)
    return credentials


def get_billing_client(service_account_key_path: Optional[str] = None) -> billing_v1.CloudBillingClient:
    """
    Returns a GCP Cloud Billing client using resolved credentials.
    """
    credentials = get_gcp_credentials(service_account_key_path)
    return billing_v1.CloudBillingClient(credentials=credentials)