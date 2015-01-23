import unittest
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
        mock_vm.set_other_config_key.assert_called_with(dm.REGISTRATION_KEY, 'True')

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
        mock_vm.remove_other_config_key.assert_called_with(dm.REGISTRATION_KEY)

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

class TestDockerMonitorLoad(unittest.TestCase):
    """
    Test the loading mechanism for the DockerMonitor.
    """

    @patch("xscontainer.docker_monitor.DockerMonitor.register")
    @patch("xscontainer.docker_monitor.DockerMonitor.should_monitor")
    def test_load_one_vm(self, mshould_monitor, mregister):
        host = MagicMock()

        vm1 = MagicMock()
        vm2 = MagicMock()
        host.get_vms.return_value = [vm1, vm2]

        # Only make one of them monitorable
        mshould_monitor = lambda x: x == vm1

        dm = DockerMonitor(host)
        dm.load_registered()
        host.get_vms.assert_called_once()
        mregister.assert_called_once()


    @patch("xscontainer.docker_monitor.DockerMonitor.register")
    @patch.object(DockerMonitor,"should_monitor")
    def test_load_multiple_vms(self, mshould_monitor, mregister):
        host = MagicMock()

        num_monitor = 5
        num_total = 20
        vms = []

        for i in range(num_monitor):
            mvm = MagicMock()
            mvm.should_monitor = True
            vms.append(mvm)

        for i in range(num_total - num_monitor):
            mvm = MagicMock()
            mvm.should_monitor = False
            vms.append(mvm)

        # Use the fake key to determine between
        mshould_monitor.side_effect = lambda x: x.should_monitor
        host.get_vms.return_value = vms

        dm = DockerMonitor(host)
        dm.load_registered()
        host.get_vms.assert_called_once()

        # Test we register all the monitorable vms
        self.assertEqual(mregister.call_count, num_monitor)

    def test_should_monitor(self):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        other_config = {dm.REGISTRATION_KEY: "True"}
        mock_vm.get_other_config.return_value = other_config
        self.assertTrue(dm.should_monitor(mock_vm))

class TestDockerMonitorThreads(unittest.TestCase):
    """
    Test the DockerMonitor's ability to start and stop threads.
    """

    @patch("thread.start_new_thread")
    def test_start_monitoring(self, mstart_new_thread):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        dm.register(mock_vm)
        mstart_new_thread.assert_called_with(monitor_vm, (mock_vm.get_session(), mock_vm.get_id()))

    @patch("os.close")
    @patch("thread.start_new_thread")
    def test_stop_monitoring(self, mstart_new_thread, mos_close):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        pid = 1200

        with patch.dict('xscontainer.docker_monitor.MONITORDICT', {mock_vm.get_id(): pid}):
            dm.stop_monitoring(mock_vm)
            mos_close.assert_called_with(pid)
