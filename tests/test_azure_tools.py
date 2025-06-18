import unittest
from unittest.mock import patch, MagicMock
from clouds.azure import tools


class TestAzureTools(unittest.TestCase):
    """Test cases for Azure tools functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.subscription_id = "test-subscription-id"
        self.service_principal_credentials = {
            'client_id': 'test-client-id',
            'client_secret': 'test-client-secret',
            'tenant_id': 'test-tenant-id'
        }

    @patch('clouds.azure.tools.get_azure_credentials')
    @patch('clouds.azure.tools.ComputeManagementClient')
    @patch('clouds.azure.tools.MonitorManagementClient')
    def test_analyze_azure_disks_success(self, mock_monitor_client, mock_compute_client, mock_get_credentials):
        """Test successful analysis of Azure disks."""
        mock_get_credentials.return_value = MagicMock()

        mock_disk = MagicMock()
        mock_disk.id = "test-disk-id"
        mock_disk.name = "test-disk"
        mock_disk.location = "eastus"
        mock_disk.sku.name = "Premium_LRS"
        mock_disk.disk_size_gb = 100
        mock_disk.os_type = "Linux"
        mock_disk.managed_by = None
        mock_disk.tags = {"environment": "test"}

        mock_compute_instance = MagicMock()
        mock_compute_instance.disks.list.return_value = [mock_disk]
        mock_compute_client.return_value = mock_compute_instance

        mock_monitor_instance = MagicMock()
        mock_monitor_client.return_value = mock_monitor_instance

        result = tools.analyze_azure_disks.invoke({
            'subscription_id': self.subscription_id,
            'service_principal_credentials': self.service_principal_credentials
        })

        self.assertIn('unattached_disks', result)
        self.assertIn('available_disks', result)
        self.assertEqual(len(result['unattached_disks']), 1)
        self.assertEqual(len(result['available_disks']), 1)

        disk_details = result['available_disks'][0]
        self.assertEqual(disk_details['name'], 'test-disk')
        self.assertEqual(disk_details['location'], 'eastus')
        self.assertEqual(disk_details['sku'], 'Premium_LRS')

    @patch('clouds.azure.tools.get_azure_credentials')
    @patch('clouds.azure.tools.NetworkManagementClient')
    @patch('clouds.azure.tools.MonitorManagementClient')
    def test_analyze_azure_network_success(self, mock_monitor_client, mock_network_client, mock_get_credentials):
        """Test successful analysis of Azure network resources."""
        mock_get_credentials.return_value = MagicMock()

        mock_public_ip = MagicMock()
        mock_public_ip.id = "test-ip-id"
        mock_public_ip.name = "test-public-ip"
        mock_public_ip.location = "eastus"
        mock_public_ip.ip_address = "192.168.1.1"
        mock_public_ip.public_ip_allocation_method = "Static"
        mock_public_ip.ip_configuration = None
        mock_public_ip.tags = {"environment": "test"}

        mock_network_instance = MagicMock()
        mock_network_instance.public_ip_addresses.list_all.return_value = [mock_public_ip]
        mock_network_instance.load_balancers.list_all.return_value = []
        mock_network_instance.nat_gateways.list_all.return_value = []
        mock_network_instance.network_security_groups.list_all.return_value = []
        mock_network_client.return_value = mock_network_instance

        mock_monitor_instance = MagicMock()
        mock_monitor_client.return_value = mock_monitor_instance

        result = tools.analyze_azure_network.invoke({
            'subscription_id': self.subscription_id,
            'service_principal_credentials': self.service_principal_credentials
        })

        self.assertIn('unused_public_ips', result)
        self.assertIn('available_resources', result)
        self.assertEqual(len(result['unused_public_ips']), 1)
        self.assertEqual(len(result['available_resources']['public_ips']), 1)

        ip_details = result['available_resources']['public_ips'][0]
        self.assertEqual(ip_details['name'], 'test-public-ip')
        self.assertEqual(ip_details['location'], 'eastus')
        self.assertEqual(ip_details['ip_address'], '192.168.1.1')

    @patch('clouds.azure.tools.get_azure_credentials')
    @patch('clouds.azure.tools.StorageManagementClient')
    @patch('clouds.azure.tools.MonitorManagementClient')
    def test_analyze_azure_storage_success(self, mock_monitor_client, mock_storage_client, mock_get_credentials):
        """Test successful analysis of Azure storage accounts."""
        mock_get_credentials.return_value = MagicMock()

        mock_storage_account = MagicMock()
        mock_storage_account.id = "test-storage-id"
        mock_storage_account.name = "teststorageaccount"
        mock_storage_account.location = "eastus"
        mock_storage_account.sku.name = "Standard_LRS"
        mock_storage_account.kind = "StorageV2"
        mock_storage_account.tags = {"environment": "test"}

        mock_storage_instance = MagicMock()
        mock_storage_instance.storage_accounts.list.return_value = [mock_storage_account]
        mock_storage_client.return_value = mock_storage_instance

        mock_metric_data = MagicMock()
        mock_metric_data.value = [MagicMock()]
        mock_metric_data.value[0].timeseries = [MagicMock()]
        mock_metric_data.value[0].timeseries[0].data = [MagicMock()]
        mock_metric_data.value[0].timeseries[0].data[0].total = 0

        mock_monitor_instance = MagicMock()
        mock_monitor_instance.metrics.list.return_value = mock_metric_data
        mock_monitor_client.return_value = mock_monitor_instance

        result = tools.analyze_azure_storage.invoke({
            'subscription_id': self.subscription_id,
            'service_principal_credentials': self.service_principal_credentials
        })

        self.assertIn('unused_storage_accounts', result)
        self.assertIn('available_storage_accounts', result)
        self.assertEqual(len(result['available_storage_accounts']), 1)

        storage_details = result['available_storage_accounts'][0]
        self.assertEqual(storage_details['name'], 'teststorageaccount')
        self.assertEqual(storage_details['location'], 'eastus')
        self.assertEqual(storage_details['sku'], 'Standard_LRS')

    def test_analyze_azure_disks_error_handling(self):
        """Test error handling in analyze_azure_disks."""
        result = tools.analyze_azure_disks.invoke({
            'subscription_id': "invalid-subscription",
            'service_principal_credentials': {"invalid": "credentials"}
        })
        self.assertIn('error', result)
        self.assertIn('recommendations', result)

    def test_analyze_azure_network_error_handling(self):
        """Test error handling in analyze_azure_network."""
        result = tools.analyze_azure_network.invoke({
            'subscription_id': "invalid-subscription",
            'service_principal_credentials': {"invalid": "credentials"}
        })
        self.assertIn('error', result)
        self.assertIn('recommendations', result)

    def test_analyze_azure_storage_error_handling(self):
        """Test error handling in analyze_azure_storage."""
        result = tools.analyze_azure_storage.invoke({
            'subscription_id': "invalid-subscription",
            'service_principal_credentials': {"invalid": "credentials"}
        })
        self.assertIn('error', result)
        self.assertIn('recommendations', result)


if __name__ == '__main__':
    unittest.main()
