from typing import Optional, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def get_boto3_session(
    profile_name: Optional[str] = None,
) -> Tuple[Optional[boto3.Session], Optional[str], Optional[str]]:
    """
    Create a boto3 session using the specified profile or default credentials.
    Returns:
        session: A valid boto3.Session instance or None if failed.
        account_id: The AWS account ID associated with the session.
        error: An error message if the session creation failed.
    """
    try:
        if profile_name:
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()

        sts = session.client("sts")
        account_id = sts.get_caller_identity()["Account"]

        return session, account_id, None

    except (BotoCoreError, ClientError) as e:
        return None, None, str(e)
