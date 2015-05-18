from mock import patch
import unittest

from xscontainer import coreos
from xscontainer import util


class TestFindLatestToolsIsoPath(unittest.TestCase):

    @patch("glob.glob")
    def test_cannot_find_tools(self, m_glob):
        m_glob.return_value = []

        self.assertRaises(util.XSContainerException,
                          coreos.find_latest_tools_iso_path)

    @patch("glob.glob")
    def test_can_find_right_tools(self, m_glob):
        m_glob.return_value = [
            '/opt/xensource/packages/iso/xs-tools-6.5.0.iso',
            '/opt/xensource/packages/iso/xs-tools-6.5.0-2001.iso',
            '/opt/xensource/packages/iso/xs-tools-6.5.0-1001.iso']

        tools_path = coreos.find_latest_tools_iso_path()

        self.assertEquals(tools_path, m_glob.return_value[1])
