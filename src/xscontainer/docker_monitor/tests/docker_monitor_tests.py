import unittest
import signal
from mock import MagicMock, patch

from xscontainer.docker_monitor import *


class TestDockerMonitorRegistration(unittest.TestCase):

    """
    Test the DockerMonitor object and it's registration related functions.
    """

    def test_register_vm(self):
        mock_vm = MagicMock()

        dm = DockerMonitor()
        dm.register(mock_vm)
        registered = dm.get_registered()

        # Asserts
        self.assertEqual(len(registered), 1)
        self.assertEqual(registered.pop(), mock_vm)

    def test_unregister_vm(self):
        mock_vm = MagicMock()

        dm = DockerMonitor()
        dm.register(mock_vm)
        dm.deregister(mock_vm)
        registered = dm.get_registered()

        self.assertEqual(registered, [])

    def test_get_registered(self):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        n = 5
        for i in range(n):
            dm.register(MagicMock())
        registered = dm.get_registered()
        self.assertEqual(len(registered), n)

    def test_is_registered(self):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        self.assertEqual(dm.is_registered(mock_vm), False)
        dm.register(mock_vm)
        self.assertEqual(dm.is_registered(mock_vm), True)

    def test_registration_exception(self):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        self.assertRaises(Exception, dm.register(mock_vm))

    def test_deregistration_exception(self):
        mock_vm = MagicMock()
        dm = DockerMonitor()
        dm.deregister(mock_vm)
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
        mprocess_vmrecord.assert_called_with('test_rec', mvm_rec)

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

    @patch("xscontainer.util.log.info")
    @patch("xscontainer.api_helper.XenAPIClient")
    @patch("thread.start_new_thread")
    def test_start_monitoring(self, mstart_new_thread, mxenapiclient, log_info):
        client = MagicMock()
        mvm_ref = MagicMock()
        dm = DockerMonitor(host=MagicMock())
        mvmwithpid = MagicMock()

        dm.start_monitoring(mvm_ref)
        registered = dm.get_registered()[0]

        mstart_new_thread.assert_called_with(dm.monitor_vm, (registered,))

    @patch("xscontainer.util.log.info")
    @patch("os.kill")
    def test_stop_monitoring(self, mos_kill, log_info):
        mvm_ref = MagicMock()
        dm = DockerMonitor()
        thevm = DockerMonitor.VMWithPid(MagicMock(), ref=mvm_ref)
        pid = 1200
        thevm.pid = pid
        dm.register(thevm)

        dm.stop_monitoring(mvm_ref)

        mos_kill.assert_called_with(pid, signal.SIGTERM)
