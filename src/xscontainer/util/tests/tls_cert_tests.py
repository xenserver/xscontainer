import os
import unittest
from mock import patch

from xscontainer.util import tls_cert


class TestTlsCert(unittest.TestCase):

    @patch("xscontainer.util.tls_secret.set_for_vm")
    @patch("shutil.copyfile")
    @patch("shutil.copy2")
    @patch("xscontainer.util.runlocal")
    @patch("xscontainer.util.read_file")
    def test_generate_certs_and_return_iso(self, read_file, runlocal,
                                           copyfile, copy2, set_for_vm):
        isofile = tls_cert.generate_certs_and_return_iso(session="",
                                                         vm_uuid="",
                                                         ips=['127.0.0.1'])

        assert os.path.exists(isofile)

        os.remove(isofile)
