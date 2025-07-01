import os

from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GCP_BILLING_DATASET = os.getenv("GCP_BILLING_DATASET", "your-billing-dataset")
GCP_BILLING_TABLE_PREFIX = os.getenv("GCP_BILLING_TABLE_PREFIX", "gcp_billing_export_")
