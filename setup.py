#!/usr/bin/env python

from distutils.core import setup
import os

def datapath(path):
    if 'HOME' in os.environ:
        path = os.path.join(os.environ['HOME'], path)
    return path

setup(name='xscontainer',
      version='0.1',
      description='Container integration for XenServer.',
      author='Citrix Systems Inc., Robert Breker',
      #author_email='',
      license = "BSD",
      url='http://github.com/xenserver/xscontainer',
      packages=['xscontainer'],
      package_dir = {'xscontainer': 'src/xscontainer'},
      scripts = ['src/xscontainer-monitor', 'src/xscontainer-pluginexample',
                 'src/xscontainer-devsystemtest',],
      data_files = [('/etc/xapi.d/plugins',
                     [datapath('src/etc/xapi.d/plugins/xscontainer')]),
                     ('/etc/init.d',
                     [datapath('src/etc/init.d/xscontainer')])],
    )
