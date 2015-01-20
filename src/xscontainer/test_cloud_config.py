#!/usr/bin/env python

"""
Test cases for CloudConfig.py
"""

import unittest

from CloudConfig import CloudConfigDrive

class TestCloudConfigDrive(unittest.TestCase):

    def test_init(self):
        ccd = CloudConfigDrive()
        self.assertEqual(ccd.FILES, [])

    def test_add_file_assert_exists(self):
        ccd = CloudConfigDrive()
        ccd.add_file("foo.bar", "/foo.bar")
        self.assertEqual(ccd.FILES, ["/foo.so"])

    def test_read_file_assert_data_exists(self):
        ccd = CloudConfigDrive()
        ccd.add_file("foo.bar", "data data", "/foo.so")
        self.assertequal(ccd.read_file("/foo.so"), "data data")


### Test manifest matches created ISO

### Test that mkisofs is properly

### Test that the created ISO 
