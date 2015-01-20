import api_helper
import docker
import log
import util

import os
import subprocess
import simplejson
import thread
import time
import XenAPI

MONITORINTERVALLINS = 60
MONITORDICT = {}


def monitor_vm(session, vmuuid):
    vmref = api_helper.get_vm_ref_by_uuid(session, vmuuid)
    try:
        update_docker_ps(session, vmuuid, vmref)
        update_docker_info(session, vmuuid, vmref)
        update_docker_version(session, vmuuid, vmref)
        monitor_vm_events(session, vmuuid, vmref)
    except util.XSContainerException, exception:
        log.exception(exception)
    # Todo: make this threadsafe
    del MONITORDICT[vmuuid]
    session.xenapi.VM.remove_from_other_config(vmref, 'docker_ps')
    session.xenapi.VM.remove_from_other_config(vmref, 'docker_info')
    session.xenapi.VM.remove_from_other_config(vmref, 'docker_version')


def monitor_vm_events(session, vmuuid, vmref):
    request_cmds = docker.prepare_request_cmds('GET', '/events')
    cmds = util.prepare_ssh_cmd(session, vmuuid, request_cmds)
    log.debug('monitor_vm is unning: %s' % (cmds))
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
                and len(data) >= 4 and data[-4:] == "\r\n\r\n"):
            data = ""
            skippedheader = True
        elif lastread == '{':
            openbrackets = openbrackets + 1
        elif lastread == '}':
            openbrackets = openbrackets - 1
            if openbrackets == 0:
                log.debug("monitor_vm received Event: %s" % data)
                results = simplejson.loads(data)
                if 'status' in results:
                    if results['status'] in ['create', 'destroy', 'die',
                                             'kill', 'pause', 'restart',
                                             'start', 'stop', 'unpause']:
                        try:
                            update_docker_ps(session, vmuuid, vmref)
                        except util.XSContainerException, exception:
                            # This can happen, when the docker daemon stops
                            log.exception(exception)
                    elif results['status'] in ['create', 'destroy', 'delete']:
                        try:
                            update_docker_info(session, vmuuid, vmref)
                        except util.XSContainerException, exception:
                            # This can happen, when the docker daemon stops
                            log.exception(exception)
                    # ignore untag for now
                data = ""
        if len(data) >= 2048:
            raise(util.XSContainerException('monitor_vm buffer is full'))
        lastread = process.stdout.read(1)
    # Todo: make this threadsafe
    process.poll()
    returncode = process.returncode
    log.debug('monitor_vm (%s) exited with rc %d' % (cmds, returncode))


def update_vmuuids_to_monitor(session):
    # Make sure that we can talk to XAPI
    vmrecords = None
    try:
        if session == None:
            session = api_helper.get_local_api_session()
        vmrecords = api_helper.get_vm_records(session)
    except XenAPI.Failure:
        if None != session:
            # Something is seriously wrong, let's re-connect to XAPI
            try:
                session.xenapi.session.logout()
            except XenAPI.Failure:
                pass
            session = None
        return
    hostref = api_helper.get_this_host_ref(session)
    for vmref, vmrecord in vmrecords.iteritems():
        if ('xscontainer-monitor' in vmrecord['other_config']
            or ('base_template_name' in vmrecord['other_config']
                and 'CoreOS'
                in vmrecord['other_config']['base_template_name'])):
            if vmrecord['power_state'] == 'Running':
                if (hostref == vmrecord['resident_on']
                        and vmrecord['uuid'] not in MONITORDICT):
                    log.info("Adding monitor for VM name: %s, UUID: %s"
                             % (vmrecord['name_label'], vmrecord['uuid']))
                    MONITORDICT[vmrecord['uuid']] = "starting"
                    thread.start_new_thread(monitor_vm,
                                            (session, vmrecord['uuid']))
            else:
                if vmrecord['uuid'] in MONITORDICT:
                    log.info("Removing monitor for VM name: %s, UUID: %s"
                             % (vmrecord['name_label'], vmrecord['uuid']))
                    # ToDo: need to make this threadsafe and more specific
                    try:
                        os.close(MONITORDICT[vmrecord['uuid']])
                    except:
                        pass


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


def update_docker_info(session, vmuuid, vmref):
    api_helper.update_vm_other_config(
        session, vmref, 'docker_info', docker.get_info_xml(session, vmuuid))


def update_docker_version(session, vmuuid, vmref):
    api_helper.update_vm_other_config(
        session, vmref, 'docker_version', docker.get_version_xml(session, vmuuid))


def update_docker_ps(session, vmuuid, vmref):
    api_helper.update_vm_other_config(
        session, vmref, 'docker_ps', docker.get_ps_xml(session, vmuuid))
