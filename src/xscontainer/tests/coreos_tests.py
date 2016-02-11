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


class TestConfigDrive(unittest.TestCase):

    data = {
        'vm_name': 'testvm',
        'rsa_pub': 'supersecret',
        'mgmt_dev': '0',
    }

    def test_legacy_hostname(self):
        initial_template = "%XSVMNAMETOHOSTNAME%"
        template = coreos.customize_userdata(initial_template, self.data)
        self.assertEqual(template, self.data["vm_name"])

    def test_new_hostname(self):
        initial_template = "%VMNAMETOHOSTNAME%"
        template = coreos.customize_userdata(initial_template, self.data)
        self.assertEqual(template, self.data["vm_name"])

    def test_legacy_rsapub(self):
        initial_template = "%XSCONTAINERRSAPUB%"
        template = coreos.customize_userdata(initial_template, self.data)
        self.assertEqual(template, self.data["rsa_pub"])

    def test_new_rsapub(self):
        initial_template = "%CONTAINERRSAPUB%"
        template = coreos.customize_userdata(initial_template, self.data)
        self.assertEqual(template, self.data["rsa_pub"])

    def test_legacy_himn(self):
        initial_template = "%XSHIN%"
        template = coreos.customize_userdata(initial_template, self.data)
        self.assertEqual(template, self.data["mgmt_dev"])

    def test_new_himn(self):
        initial_template = "%HIN%"
        template = coreos.customize_userdata(initial_template, self.data)
        self.assertEqual(template, self.data["mgmt_dev"])

    def test_compound_template(self):

        initial_template = """
Hostname: %VMNAMETOHOSTNAME%

SSH_PUB_KEY: %CONTAINERRSAPUB%

HIMN: %HIN%
"""

        template_truth = """
Hostname: testvm

SSH_PUB_KEY: supersecret

HIMN: 0
"""

        result = coreos.customize_userdata(initial_template, self.data)
        self.assertEqual(result, template_truth)

    def test_filter_legacy_hin(self):
        initial_template = "this is a test %XSHINEXISTS% this should " + \
                           "disappear %XSENDHINEXISTS%more text"
        result = coreos.filterxshinexists(initial_template)
        self.assertEqual(result, "this is a test more text")

    def test_filter_hin(self):
        initial_template = "this is a test %HINEXISTS% this should " + \
                           "disappear %ENDHINEXISTS%more text"
        result = coreos.filterxshinexists(initial_template)
        self.assertEqual(result, "this is a test more text")

    def test_filter_hin_multiline(self):
        initial_template = """this is a test
%HINEXISTS%
some config here
that should be removed
%ENDHINEXISTS%
some more text"""

        template_truth = """this is a test

some more text"""
        result = coreos.filterxshinexists(initial_template)
        self.assertEqual(result, template_truth)
