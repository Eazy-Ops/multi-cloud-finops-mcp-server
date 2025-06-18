import unittest
from unittest.mock import MagicMock, patch

from clouds.aws import tools


class TestAWSTools(unittest.TestCase):
    def setUp(self):
        self.profile_name = "default"
        self.regions = ["us-east-1", "us-west-2"]

    @patch("clouds.aws.tools.get_boto3_session")
    def test_analyze_aws_disks_success(self, mock_get_session):
        mock_session = MagicMock()
        mock_ec2 = MagicMock()
        mock_cloudwatch = MagicMock()

        # Mock describe_volumes response
        mock_ec2.describe_volumes.return_value = {
            "Volumes": [
                {
                    "VolumeId": "vol-123",
                    "Size": 100,
                    "VolumeType": "gp2",
                    "State": "available",
                    "Attachments": [],
                    "Encrypted": True,
                    "Tags": [],
                }
            ]
        }

        # Mock get_metric_statistics response
        mock_cloudwatch.get_metric_statistics.return_value = {
            "Datapoints": [{"Sum": 0}]
        }

        mock_session.client.side_effect = lambda service, **kwargs: {
            "ec2": mock_ec2,
            "cloudwatch": mock_cloudwatch,
        }[service]

        mock_get_session.return_value = (mock_session, self.profile_name, self.regions)

        result = tools.analyze_aws_disks.invoke(
            {"profile_name": self.profile_name, "regions": self.regions}
        )

        self.assertIsInstance(result, dict)
        self.assertIn("unattached_volumes", result)
        self.assertIn("available_volumes", result)

    @patch("clouds.aws.tools.get_boto3_session")
    def test_analyze_aws_disks_error_handling(self, mock_get_session):
        mock_session = MagicMock()
        mock_ec2 = MagicMock()
        mock_cloudwatch = MagicMock()

        # Mock the describe_volumes method to raise an exception
        mock_ec2.describe_volumes.side_effect = Exception("Simulated EC2 failure")

        mock_session.client.side_effect = lambda service, **kwargs: {
            "ec2": mock_ec2,
            "cloudwatch": mock_cloudwatch,
        }[service]

        mock_get_session.return_value = (mock_session, self.profile_name, self.regions)

        result = tools.analyze_aws_disks.invoke(
            {"profile_name": self.profile_name, "regions": self.regions}
        )

        self.assertIsInstance(result, dict)
        self.assertIn("unattached_volumes", result)
        self.assertIn("available_volumes", result)
        # Should return empty lists when errors occur
        self.assertEqual(result["unattached_volumes"], [])
        self.assertEqual(result["available_volumes"], [])

    @patch("clouds.aws.tools.get_boto3_session")
    def test_analyze_aws_network_success(self, mock_get_session):
        mock_session = MagicMock()
        mock_ec2 = MagicMock()
        mock_elbv2 = MagicMock()
        mock_iam = MagicMock()
        mock_cloudwatch = MagicMock()

        # Mock describe_addresses (EIPs)
        mock_ec2.describe_addresses.return_value = {
            "Addresses": [
                {
                    "AllocationId": "eipalloc-123",
                    "PublicIp": "192.168.1.1",
                    "Domain": "vpc",
                    "AssociationId": None,  # Unused EIP
                    "Tags": [],
                }
            ]
        }

        mock_elbv2.describe_load_balancers.return_value = {
            "LoadBalancers": [
                {
                    "LoadBalancerArn": "arn:aws:elb:...",
                    "DNSName": "test.elb.amazonaws.com",
                    "Scheme": "internet-facing",
                    "VpcId": "vpc-123",
                    "Type": "application",
                }
            ]
        }

        mock_iam.get_account_authorization_details.return_value = {
            "UserDetailList": [],
            "GroupDetailList": [],
            "RoleDetailList": [],
        }

        mock_session.client.side_effect = lambda service, **kwargs: {
            "ec2": mock_ec2,
            "elbv2": mock_elbv2,
            "iam": mock_iam,
            "cloudwatch": mock_cloudwatch,
        }[service]

        mock_get_session.return_value = (mock_session, self.profile_name, self.regions)

        result = tools.analyze_aws_network.invoke(
            {"profile_name": self.profile_name, "regions": self.regions}
        )

        self.assertIsInstance(result, dict)
        self.assertIn("unused_eips", result)
        self.assertIn("available_resources", result)

    @patch("clouds.aws.tools.get_boto3_session")
    def test_analyze_aws_network_error_handling(self, mock_get_session):
        mock_session = MagicMock()
        mock_ec2 = MagicMock()
        mock_elbv2 = MagicMock()
        mock_cloudwatch = MagicMock()

        # Mock the describe_addresses method to raise an exception
        mock_ec2.describe_addresses.side_effect = Exception("Simulated failure")

        mock_session.client.side_effect = lambda service, **kwargs: {
            "ec2": mock_ec2,
            "elbv2": mock_elbv2,
            "cloudwatch": mock_cloudwatch,
        }[service]

        mock_get_session.return_value = (mock_session, self.profile_name, self.regions)

        result = tools.analyze_aws_network.invoke(
            {"profile_name": self.profile_name, "regions": self.regions}
        )

        self.assertIsInstance(result, dict)
        self.assertIn("unused_eips", result)
        self.assertIn("available_resources", result)
        # Should return empty lists when errors occur
        self.assertEqual(result["unused_eips"], [])
        self.assertEqual(result["available_resources"]["eips"], [])

    @patch("clouds.aws.tools.get_boto3_session")
    def test_analyze_rds_instances_success(self, mock_get_session):
        mock_session = MagicMock()
        mock_rds = MagicMock()
        mock_cloudwatch = MagicMock()

        mock_rds.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "rds-1",
                    "DBInstanceClass": "db.t3.medium",
                    "AllocatedStorage": 20,
                    "Engine": "postgres",
                    "EngineVersion": "13.0",
                    "MultiAZ": False,
                    "StorageType": "gp2",
                    "PubliclyAccessible": False,
                    "DBInstanceStatus": "available",
                }
            ]
        }

        mock_cloudwatch.get_metric_statistics.return_value = {
            "Datapoints": [{"Average": 30.0}]
        }

        mock_session.client.side_effect = lambda service, **kwargs: {
            "rds": mock_rds,
            "cloudwatch": mock_cloudwatch,
        }[service]

        mock_get_session.return_value = (mock_session, self.profile_name, self.regions)

        result = tools.analyze_rds_instances.invoke(
            {"profile_name": self.profile_name, "regions": self.regions}
        )

        self.assertIsInstance(result, dict)
        self.assertIn("available_instances", result)

    @patch("clouds.aws.tools.get_boto3_session")
    def test_analyze_rds_instances_error_handling(self, mock_get_session):
        mock_session = MagicMock()
        mock_rds = MagicMock()
        mock_cloudwatch = MagicMock()

        # Mock the describe_db_instances method to raise an exception
        mock_rds.describe_db_instances.side_effect = Exception("Simulated RDS failure")

        mock_session.client.side_effect = lambda service, **kwargs: {
            "rds": mock_rds,
            "cloudwatch": mock_cloudwatch,
        }[service]

        mock_get_session.return_value = (mock_session, self.profile_name, self.regions)

        result = tools.analyze_rds_instances.invoke(
            {"profile_name": self.profile_name, "regions": self.regions}
        )

        self.assertIsInstance(result, dict)
        self.assertIn("available_instances", result)
        # Should return empty lists when errors occur
        self.assertEqual(result["available_instances"], [])


if __name__ == "__main__":
    unittest.main()
