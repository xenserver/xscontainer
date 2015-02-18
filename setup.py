#!/usr/bin/env python

from distutils.core import setup
import os
import sys


def datapath(path):
    if not os.path.exists(path):
        if 'REPO' in os.environ:
            path = os.path.join(os.environ['REPO'], path)
    return path

if __name__ == "__main__":
    version = '0.1'
    # Add forceversion option to specify the version via the command line
    matchingarg = None
    for arg in sys.argv:
        if '--forceversion=' in arg:
            version = arg.replace('--forceversion=', '')
            matchingarg = arg
    sys.argv[:] = [arg for arg in sys.argv if matchingarg != arg]

    setup(name='xscontainer',
          version=version,
          description='XenServer Container Management.',
          author='Citrix Systems, Inc.',
          license='BSD',
          url='http://github.com/xenserver/xscontainer',
          packages=['xscontainer', 'xscontainer.util',
                    'xscontainer.docker_monitor'],
          package_dir={'xscontainer': 'src/xscontainer'},
          package_data={'xscontainer': ['data/*.template', 'data/*.README']},
          scripts=['src/xscontainer-prepare-vm',
                   'src/xscontainer-monitor',
                   #'src/scripts/xscontainer-pluginexample',
                   #'src/scripts/xscontainer-devsystemtest',
                   ],
          data_files=[('/etc/xapi.d/plugins',
                       [datapath(
                        'src/overlay/etc/xapi.d/plugins/xscontainer')]),
                      ('/etc/rc.d/init.d',
                       [datapath(
                        'src/overlay/etc/rc.d/init.d/xscontainer-monitor')])],
          options={'bdist_rpm': {'post_install': 'mk/post-install-script',
                                 'pre_uninstall': 'mk/pre-uninstall-script',
                                 'requires': 'mkisofs gmp python-crypto python-paramiko'}},
          )
