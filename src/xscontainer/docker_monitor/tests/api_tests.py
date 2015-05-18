import unittest
from xscontainer import docker_monitor
from xscontainer.docker_monitor import api, REGISTRATION_KEY
from mock import patch, MagicMock


class TestAPIRegistration(unittest.TestCase):

    @patch('xscontainer.docker_monitor.api.VM')
    @patch('xscontainer.docker_monitor.api.XenAPIClient')
    def test_register_vm(self, mock_client, mock_vm):
        client_inst = mock_client.return_value = MagicMock()
        vm_inst = mock_vm.return_value = MagicMock()

        vm_uuid = MagicMock()
        api.register_vm(vm_uuid, None)

        mock_vm.assert_called_with(client_inst, uuid=vm_uuid)

        vm_inst.update_other_config.assert_called_once_with(
            REGISTRATION_KEY,
            docker_monitor.REGISTRATION_KEY_ON)

    @patch('xscontainer.docker_monitor.api.VM')
    @patch('xscontainer.docker_monitor.api.XenAPIClient')
    def test_deregister_vm(self, mock_client, mock_vm):
        client_inst = mock_client.return_value = MagicMock()
        vm_inst = mock_vm.return_value = MagicMock()

        vm_uuid = MagicMock()
        api.deregister_vm(vm_uuid, None)

        mock_vm.assert_called_with(client_inst, uuid=vm_uuid)

        vm_inst.update_other_config.assert_called_once_with(
            REGISTRATION_KEY,
            docker_monitor.REGISTRATION_KEY_OFF)
