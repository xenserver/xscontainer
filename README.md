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

## Context

This plugin is a XAPI plugin, which can be called through the `host.call_plugin` method.

Reminder from the XAPI documentation:

`string call_plugin (session ref, host ref, string, string, (string → string) map)`

Parameters:

* session ref session_id	Reference to a valid session
* host ref host	The host
* string plugin	The name of the plugin
* string fn	The name of the function within the plugin
* (string → string) map args	Arguments for the function

Result:	Result from the plugin

## Usage

In this case, a typical call should look like this:

`host.call_plugin(sessionRef,hostRef,'xscontainer',function,args)`

Example for starting a container:

`host.call_plugin(sessionRef,hostRef,'xscontainer','start',(vmuuid: '<VM.UUID>', container: '<Container.UUID>'))`

### Docker container life cycle

All the life cycle operation are defined in the `function` parameters from the prototype given above. It could take those values:

* start
* stop
* restart
* pause
* unpause

`args` is be a map with `vmuuid: '<VM.UUID>', container: '<Container.UUID>'`

### Register/unregister a VM

The plugin returns data on a VM if it's registered.

The `function` parameter could be:

* register
* deregister

`args` is a map with only the VM: `vmuuid: '<VM.UUID>'`

### VM creation

#### CoreOS template

You need to get the config drive default configuration for a specific template, by calling:

`host.call_plugin(sessionRef,hostRef,'xscontainer','get_config_drive_default',(templateuuid: '<template.UUID>'))`

You can modify this configuration (e.g by adding your SSH public key). You should store this configuration somewhere.

Then, after the VM is created in XenServer, you can call the config drive creation:

`host.call_plugin(sessionRef,hostRef,'xscontainer','create_config_drive',(vmuuid: '<VM.UUID>', sruuid: <SR.UUID>, configuration: 'Your whole CloudConfig configuration'))`

> Which SR should I use? XenCenter and Xen Orchestra both use the SR of the first VDI created on the VM.
