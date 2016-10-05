#!/usr/bin/env python

from distutils.core import setup
import os
import sys

ROOTDIR_ENV_KEY = "ROOTDIR"

OVERLAY_FILES = {
    'etc/xapi.d/plugins': ['xscontainer'],
    'etc/xensource/bugtool': ['xscontainer.xml'],
    'etc/xensource/bugtool/xscontainer': ['xscontainer_logs.xml'],
    'usr/lib/systemd/system/': ['xscontainer-monitor.service']
}


def datapath(path):
    if not os.path.exists(path):
        if 'REPO' in os.environ:
            path = os.path.join(os.environ['REPO'], path)
    return path


def map_overlay_files(overlay_files):
    """
    A utility function for creating the map required for 'data_files'.
    """
    mapping = []

    root_dir = ""
    # Root directory override (used by tox)
    if ROOTDIR_ENV_KEY in os.environ:
        root_dir = os.environ[ROOTDIR_ENV_KEY]

    for dest, files in overlay_files.iteritems():
        file_locs = [datapath("src/overlay/%s/%s" % (dest, f)) for f in files]
        mapping.append(("%s/%s" % (root_dir, dest), file_locs))

    return mapping

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
          packages=['xscontainer', 'xscontainer.docker_monitor',
                    'xscontainer.remote_helper', 'xscontainer.util'],
          package_dir={'xscontainer': 'src/xscontainer'},
          package_data={'xscontainer': ['data/*.template', 'data/*.README',
                                        'data/configure_tls.cmd', 'daemon.json']},
          scripts=['src/xscontainer-prepare-vm',
                   'src/xscontainer-monitor',
                   # 'src/scripts/xscontainer-pluginexample',
                   # 'src/scripts/xscontainer-devsystemtest',
                   ],
          data_files=map_overlay_files(OVERLAY_FILES),
          options={'bdist_rpm': {'post_install': 'mk/post-install-script',
                                 'pre_uninstall': 'mk/pre-uninstall-script',
                                 'requires': 'mkisofs python-paramiko'}},
          )
