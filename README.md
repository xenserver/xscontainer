xscontainer
===========
xscontainer is the backend of XenServer's docker integration.

xscontainer has three main entry points:
    * src/xscontainer-monitor
      Will watch DomUs on the same host, if they are registered for container
      englightenment.
    * src/xscontainer-prepare-vm
      Run inside Dom0 to prepares an Ubuntu 14.04 or RHEL7 DOMU for container
      enlightenment
    * src/overlay/etc/xapi.d/plugins/xscontainer
      The primary means for XenCenter and other components to interact with
      xscontainer
