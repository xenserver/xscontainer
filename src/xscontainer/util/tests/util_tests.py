import unittest
import json
import os


import xscontainer.util as util
import xml


class TestUtil(unittest.TestCase):

    def test_convertoxml(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "docker_inspect_json.xml")
        with open(path) as filehandler:
            filecontents = util.convert_dict_to_ascii(json.load(filehandler))

        xmloutput = util.converttoxml({'docker_inspect': filecontents})

        xml.dom.minidom.parseString(xmloutput)
        # we can assert that no exception is thrown because of invalid xml

    def test_nested_list_convert(self):
        rec = {'ports': [
            {'IP': '0.0.0.0'},
            {'IP': '0.0.0.1'},
        ]}
        expected_xml = ('<?xml version="1.0" ?><ports><item><IP>0.0.0.0</IP>' +
                        '</item><item><IP>0.0.0.1</IP></item></ports>')

        xmloutput = util.converttoxml(rec)

        print xmloutput
        self.assertEqual(xmloutput, expected_xml)
