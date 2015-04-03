[![Build Status](https://travis-ci.org/xenserver/xscontainer.svg?branch=master)](https://travis-ci.org/xenserver/xscontainer)
[![Coverage Status](https://coveralls.io/repos/xenserver/xscontainer/badge.svg?branch=master)](https://coveralls.io/r/xenserver/xscontainer?branch=master)

xscontainer
===========
xscontainer is the back-end of XenServer's Container Management.

There are 3 main entry points:
* src/xscontainer-monitor:
  Monitors "container managed" DomUs on the same host.
* src/xscontainer-prepare-vm:
  Prepares Ubuntu 14.04, RHEL/CentOS/OEL 7 DomUs to be "container managed".
* src/overlay/etc/xapi.d/plugins/xscontainer:
  Means for XenCenter and other components to interact with xscontainer.

