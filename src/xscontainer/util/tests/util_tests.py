import unittest
from mock import MagicMock, patch
import simplejson
import os


import xscontainer.util as util
import xscontainer.util.log as log
import xml


class TestUtil(unittest.TestCase):

    def test_convertoxml(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "docker_inspect_json.xml")
        with open(path) as filehandler:
            filecontents = simplejson.load(filehandler)

        xmloutput = util.converttoxml({'docker_inspect': filecontents})

        xml.dom.minidom.parseString(xmloutput)
        # we can assert that no exception is thrown because of invalid xml

