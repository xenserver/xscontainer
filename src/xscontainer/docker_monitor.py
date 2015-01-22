import api_helper
import docker
import xscontainer.util as util
from xscontainer.util import log

import os
import subprocess
import simplejson
import thread
import time
import socket
import XenAPI

MONITORRETRYSLEEPINS = 10
MONITORVMRETRYTIMEOUTINS = 100
MONITORDICT = {}


def monitor_vm(session, vmuuid):
    vmref = api_helper.get_vm_ref_by_uuid(session, vmuuid)
    done = False
    starttime = time.time()
    while not done:
        try:
            update_docker_ps(session, vmuuid, vmref)
            update_docker_info(session, vmuuid, vmref)
            update_docker_version(session, vmuuid, vmref)
            done = True
        except util.XSContainerException, exception:
            log.info("Could not connect to VM %s, will retry" %(vmuuid))
            time.sleep(MONITORRETRYSLEEPINS)
            if time.time() - starttime > MONITORVMRETRYTIMEOUTINS:
                log.warning("Could not connect to VM within %ds - aborting"
                            % (MONITORRETRYSLEEPINS))
                log.exception(exception)
                done = True
    try:
        monitor_vm_events(session, vmuuid, vmref)
    except (XenAPI.Failure, util.XSContainerException, exception):
        log.warning("monitor_vm threw an an exception")
        log.exception(exception)
    # Todo: make this threadsafe
    del MONITORDICT[vmuuid]
    session.xenapi.VM.remove_from_other_config(vmref, 'docker_ps')
    session.xenapi.VM.remove_from_other_config(vmref, 'docker_info')
    session.xenapi.VM.remove_from_other_config(vmref, 'docker_version')


def monitor_vm_events(session, vmuuid, vmref):
    request_cmds = docker.prepare_request_cmds('GET', '/events')
    cmds = api_helper.prepare_ssh_cmd(session, vmuuid, request_cmds)
    log.debug('monitor_vm is running: %s' % (cmds))
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


def process_vmrecord(session, hostref, vmrecord):
    if (vmrecord['power_state'] == 'Running'
        and vmrecord['resident_on'] == hostref
        and 'Control domain on host: ' not in vmrecord['name_label']
        and vmrecord['uuid'] not in MONITORDICT):
        # ToDo: Should also filter for monitoring enabled
        log.info("Adding monitor for VM name: %s, UUID: %s"
                 % (vmrecord['name_label'], vmrecord['uuid']))
        MONITORDICT[vmrecord['uuid']] = "starting"
        thread.start_new_thread(monitor_vm, (session, vmrecord['uuid'],))
    elif (vmrecord['power_state'] == 'Halted' and
          vmrecord['uuid'] in MONITORDICT):
        log.info("Removing monitor for VM name: %s, UUID: %s"
                 % (vmrecord['name_label'], vmrecord['uuid']))
        try:
            os.close(MONITORDICT[vmrecord['uuid']])
        except:
            pass
        del MONITORDICT[vmrecord['uuid']]


def monitor_host_oneshot(session, hostref):
    vmrecords = api_helper.get_vm_records(session)
    for vmrecord in vmrecords.itervalues():
        process_vmrecord(session, hostref, vmrecord)


def monitor_host():
    while True:
        try:
            session = api_helper.get_local_api_session()
            hostref = api_helper.get_this_host_ref(session)
            try:
                session.xenapi.event.register(["vm"])
                monitor_host_oneshot(session, hostref)
                while True:
                    try:
                        events = session.xenapi.event.next()
                        for event in events:
                            if (event['operation'] == 'mod'
                                and 'snapshot' in event):
                                    process_vmrecord(session, hostref,
                                                     event['snapshot'])
                    except XenAPI.Failure, exception:
                        if exception.details != "EVENTS_LOST":
                            raise
                        # handle EVENTS_LOST API failure
                        log.warning("Recovering from EVENTS_LOST")
                        session.xenapi.event.unregister(["vm"])
                        session.xenapi.event.register(["vm"])
                        monitor_host_oneshot(session, hostref)
            finally:
                try:
                    session.xenapi.XAPISESSION.logout()
                except XenAPI.Failure:
                    log.warning("Failed when trying to logout")
        except (socket.error, XenAPI.Failure), exception:
            log.warning("Recovering from XAPI failure" +
                        "- Possibly a XAPI toolstack restart.")
            log.exception(exception)
            time.sleep(5)

def update_docker_info(session, vmuuid, vmref):
    api_helper.update_vm_other_config(
        session, vmref, 'docker_info', docker.get_info_xml(session, vmuuid))


def update_docker_version(session, vmuuid, vmref):
    api_helper.update_vm_other_config(
        session, vmref, 'docker_version',
        docker.get_version_xml(session, vmuuid))


def update_docker_ps(session, vmuuid, vmref):
    api_helper.update_vm_other_config(
        session, vmref, 'docker_ps', docker.get_ps_xml(session, vmuuid))
