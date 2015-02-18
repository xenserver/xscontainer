xscontainer
===========
xscontainer is the back-end of XenServer's Container Management feature.

xscontainer has three main entry points:
    * src/xscontainer-monitor
      Watches DomUs on the same host, if they are registered for container
      management. Responsible for keeping various fields in vm:other_config
      up to date.
    * src/xscontainer-prepare-vm
      Runs inside Dom0 and prepares Ubuntu 14.04, RHEL/CentOS/OEL/7 DOMUs for
      container management.
    * src/overlay/etc/xapi.d/plugins/xscontainer
      The primary entry point for XenCenter and other components to interact
      with xscontainer directly.
