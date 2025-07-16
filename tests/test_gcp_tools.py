import unittest

from clouds.gcp import tools


class TestGCPTools(unittest.TestCase):
    def setUp(self):
        self.project_id = "test-project-id"
        self.service_account_key_path = "/path/to/service-account.json"

    def test_analyze_gcp_storage_error_handling(self):
        result = tools.analyze_gcp_storage.invoke(
            {
                "project_id": "bad-project",
                "service_account_key_path": "/invalid/path.json",
            }
        )
        self.assertIn("error", result)
        self.assertIn("recommendations", result)

    def test_analyze_gcp_disks_error_handling(self):
        result = tools.analyze_gcp_disks.invoke(
            {
                "project_id": "bad-project",
                "service_account_key_path": "/invalid/path.json",
            }
        )
        self.assertIn("error", result)
        self.assertIn("recommendations", result)

    def test_analyze_gcp_bigquery_error_handling(self):
        result = tools.analyze_gcp_bigquery.invoke(
            {
                "project_id": "bad-project",
                "service_account_key_path": "/invalid/path.json",
            }
        )
        self.assertIn("error", result)
        self.assertIn("recommendations", result)


if __name__ == "__main__":
    unittest.main()
