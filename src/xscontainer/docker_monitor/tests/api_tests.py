import unittest
from xscontainer.docker_monitor import DockerMonitor, api, REGISTRATION_KEY
from xscontainer.docker_monitor.api import *
from mock import patch, MagicMock


class TestAPIRegistration(unittest.TestCase):

    @patch('xscontainer.docker_monitor.api.VM')
    @patch('xscontainer.docker_monitor.api.LocalXenAPIClient')
    def test_register_vm(self, mock_client, mock_vm):
        client_inst = mock_client.return_value = MagicMock()
        vm_inst = mock_vm.return_value = MagicMock()

        vm_uuid = MagicMock()
        api.register_vm(vm_uuid)

        mock_vm.assert_called_with(client_inst, uuid=vm_uuid)

        vm_inst.add_to_other_config.assert_called_once_with(
            REGISTRATION_KEY, "True")

    @patch('xscontainer.docker_monitor.api.VM')
    @patch('xscontainer.docker_monitor.api.LocalXenAPIClient')
    def test_deregister_vm(self, mock_client, mock_vm):
        client_inst = mock_client.return_value = MagicMock()
        vm_inst = mock_vm.return_value = MagicMock()

        vm_uuid = MagicMock()
        api.deregister_vm(vm_uuid)

        mock_vm.assert_called_with(client_inst, uuid=vm_uuid)

        vm_inst.remove_from_other_config.assert_called_once_with(
            REGISTRATION_KEY)
