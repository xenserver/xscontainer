import unittest
import signal
from mock import MagicMock, patch

from xscontainer.docker_monitor import *


class TestDockerMonitorRegistration(unittest.TestCase):
    """
    Test the DockerMonitor object and it's registration related functions.
    """

    @patch("xscontainer.docker_monitor.DockerMonitor.start_monitoring")
    def test_register_vm(self, mstart_monitoring):
        mock_vm = MagicMock()
        dm = DockerMonitor()

        dm.register(mock_vm)
        registered = dm.get_registered()
        mock_vm.set_other_config_key.assert_called_with(REGISTRATION_KEY, 'True')

        # Asserts
        mstart_monitoring.assert_called_with(mock_vm)
        self.assertEqual(len(registered), 1)
        self.assertEqual(registered.pop(), mock_vm)

    @patch("xscontainer.docker_monitor.DockerMonitor.start_monitoring")
    def test_unregister_vm(self, mstart_monitoring):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        dm.register(mock_vm)
        dm.deregister(mock_vm)
        registered = dm.get_registered()
        self.assertEqual(registered, [])
        mock_vm.remove_other_config_key.assert_called_with(REGISTRATION_KEY)

    @patch("xscontainer.docker_monitor.DockerMonitor.start_monitoring")
    def test_get_registered(self, mstart_monitoring):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        n = 5
        for i in range(n):
            dm.register(MagicMock())
        registered = dm.get_registered()
        self.assertEqual(len(registered), n)

    @patch("xscontainer.docker_monitor.DockerMonitor.start_monitoring")
    def test_is_registered(self, mstart_monitoring):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        self.assertEqual(dm.is_registered(mock_vm), False)
        dm.register(mock_vm)
        self.assertEqual(dm.is_registered(mock_vm), True)

    @patch("xscontainer.docker_monitor.DockerMonitor.start_monitoring")
    def test_registration_exception(self, mstart_monitoring):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        mock_vm.set_other_config.side_effect = Exception("Ah, can't change the key!")
        self.assertRaises(Exception, dm.register(mock_vm))

    @patch("xscontainer.docker_monitor.DockerMonitor.start_monitoring")
    def test_deregistration_exception(self, mstart_monitoring):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        dm.register(mock_vm)
        mock_vm.set_other_config.side_effect = Exception("Ah, can't change the key!")
        self.assertRaises(Exception, dm.deregister(mock_vm))

class TestDockerMonitorRefresh(unittest.TestCase):
    """
    Test the refresh mechanism for the DockerMonitor.
    """

    @patch("xscontainer.docker_monitor.DockerMonitor.process_vmrecord")
    def test_load_one_vm(self, mprocess_vmrecord):
        host = MagicMock()

        mvm_rec = MagicMock()

        host.client.get_all_vm_records.return_value = {'test_rec': mvm_rec}

        dm = DockerMonitor(host)
        dm.refresh()

        host.client.get_vms.assert_called_once()
        mprocess_vmrecord.assert_called_with(mvm_rec)


    @patch("xscontainer.docker_monitor.DockerMonitor.process_vmrecord")
    def test_load_all_vm(self, mprocess_vmrecord):
        host = MagicMock()

        # Mock out the vm_ref: vm_rec dictionary object
        mvm_recs = {}
        n = 10
        for i in range(n):
            mvm_recs["rec_%d" % i] = MagicMock()

        host.client.get_all_vm_records.return_value = mvm_recs

        dm = DockerMonitor(host)
        dm.refresh()

        host.client.get_vms.assert_called_once()

        # Assert we process every record.
        self.assertEqual(mprocess_vmrecord.call_count, n)


class TestDockerMonitorThreads(unittest.TestCase):
    """
    Test the DockerMonitor's ability to start and stop threads.
    """

    @patch("thread.start_new_thread")
    def test_start_monitoring(self, mstart_new_thread):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        dm.start_monitoring(mock_vm)
        mstart_new_thread.assert_called_with(monitor_vm, (mock_vm.get_session(), mock_vm.get_uuid()))

    @patch("os.kill")
    @patch("thread.start_new_thread")
    def test_stop_monitoring(self, mstart_new_thread, mos_kill):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        pid = 1200

        with patch.dict('xscontainer.docker_monitor.MONITORDICT', {mock_vm.get_id(): pid}):
            dm.stop_monitoring(mock_vm)
            mos_kill.assert_called_with(pid, signal.SIGTERM)
