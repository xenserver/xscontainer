import ApiHelper
import Docker
import Log
import Util

import os
import subprocess
import simplejson
import thread
import time
import XenAPI

MONITORINTERVALLINS = 60
MONITORDICT = {}


def monitor_events(session, vmuuid):
    request_cmds = Docker.prepare_request_cmds('GET', '/events')
    cmds = Util.prepare_ssh_cmd(session, vmuuid, request_cmds)
    Log.debug('Running: %s' % (cmds))
    process = subprocess.Popen(cmds,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE,
                               shell=False)
    MONITORDICT[vmuuid] = process.stdout
    process.stdin.write("\n")
    data = ""
    # ToDo: Got to make this sane
    skippedheader = False
    openbrackets = 0
    lastread = process.stdout.read(1)
    while lastread != '':
        data = data + lastread
        if (not skippedheader and lastread == "\n"
                and len(data) > 4 and data[-4:] == "\r\n\r\n"):
            data = ""
            skippedheader = True
        elif lastread == '{':
            openbrackets = openbrackets + 1
        elif lastread == '}':
            openbrackets = openbrackets - 1
            if openbrackets == 0:
                Log.debug("received Event: %s" % data)
                results = simplejson.loads(data)
                if 'status' in results and (results['status']
                                            in ['create', 'destroy', 'die',
                                                'export', 'kill', 'pause',
                                                'restart', 'start', 'stop',
                                                'unpause']):
                    monitor_vm(session, vmuuid)
                data = ""
        if len(data) >= 2048:
            raise(Util.XSContainerException('monitor_events buffer is full'))
        lastread = process.stdout.read(1)
    del MONITORDICT[vmuuid]
    process.poll()
    returncode = process.returncode
    if returncode != 0:
        Log.error('Docker monitor (%s) exited with rc %d' % (cmds, returncode))


def update_vmuuids_to_monitor(session):
    # Make sure that we can talk to XAPI
    vmrecords = None
    try:
        if session == None:
            session = ApiHelper.get_local_api_session()
        vmrecords = ApiHelper.get_vm_records(session)
    except XenAPI.Failure:
        if None != session:
            # Something is seriously wrong, let's re-connect to XAPI
            try:
                session.xenapi.session.logout()
            except XenAPI.Failure:
                pass
            session = None
        return
    hostref = ApiHelper.get_this_host_ref(session)
    for vmref, vmrecord in vmrecords.iteritems():
        if ('xscontainer-monitor' in vmrecord['other_config']
            or ('base_template_name' in vmrecord['other_config']
                and 'CoreOS'
                in vmrecord['other_config']['base_template_name'])):
            if vmrecord['power_state'] == 'Running':
                if (hostref == vmrecord['resident_on']
                        and vmrecord['uuid'] not in MONITORDICT):
                    Log.info("Adding monitor for VM name: %s, UUID: %s"
                             % (vmrecord['name_label'], vmrecord['uuid']))
                    MONITORDICT[vmrecord['uuid']] = "starting"
                    thread.start_new_thread(monitor_events,
                                            (session, vmrecord['uuid']))
            else:
                if vmrecord['uuid'] in MONITORDICT:
                    Log.info("Removing monitor for VM name: %s, UUID: %s"
                             % (vmrecord['name_label'], vmrecord['uuid']))
                    os.close(MONITORDICT[vmrecord['uuid']])
                    session.xenapi.VM.remove_from_other_config(vmref,
                                                               'docker_ps')


def monitor_host(returninstantly=False):
    session = None
    passedtime = MONITORINTERVALLINS
    iterationstarttime = time.time() - MONITORINTERVALLINS
    while True:
        # Do throttle
        passedtime = time.time() - iterationstarttime
        iterationstarttime = time.time()
        if passedtime < MONITORINTERVALLINS:
            time.sleep(MONITORINTERVALLINS - passedtime)
        update_vmuuids_to_monitor(session)
        if returninstantly:
            break


def monitor_vm(session, vmuuid, vmref=None):
    # ToDo: must make this so much more efficient!
    Log.debug("Monitor %s" % vmuuid)
    if vmref == None:
        vmref = ApiHelper.get_vm_ref_by_uuid(session, vmuuid)
    ApiHelper.update_vm_other_config(
        session, vmref, 'docker_ps', Docker.get_ps_xml(session, vmuuid))
