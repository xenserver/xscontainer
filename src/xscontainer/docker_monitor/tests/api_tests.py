import unittest
from xscontainer.docker_monitor import DockerMonitor, api
from xscontainer.docker_monitor.api import *
from mock import patch, MagicMock


class TestAPIRegistration(unittest.TestCase):

    @patch.object(DockerMonitor, 'register')
    def test_register_vm(self, mock_register):
        pass
