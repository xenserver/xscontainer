import unittest
from xscontainer import docker


class TestPatchPsStatus(unittest.TestCase):

    def test_patch_up_status_in_seconds(self):
        test_dict = {"Status": "Up 40 seconds"}
        docker.patch_docker_ps_status(test_dict)
        self.assertEqual(test_dict["Status"], "Up")

    def test_patch_no_time_in_status(self):
        test_dict = {"Status": "exit 0"}
        docker.patch_docker_ps_status(test_dict)
        self.assertEqual(test_dict["Status"], "exit 0")
