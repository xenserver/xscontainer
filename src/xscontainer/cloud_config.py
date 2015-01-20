#!/usr/bin/env python


"""
A module for building cloud-config disks.
"""

MKISOFS = "/usr/bin/mkisofs"

class CloudConfigDrive(object):

    FILES = []
    CONFIG = {}

    def __init__(self):
        """Initialise root directory"""
        return

    def add_file(self, filename, data):
        
        pass

    def read_file(self, fileloc):
        pass

    def create_image(self, fmt="iso"):

        if fmt == "iso":
            return self.create_iso()


    def create_iso(self):
        pass 
