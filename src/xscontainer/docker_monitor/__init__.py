from xscontainer import api_helper
from xscontainer import docker
from xscontainer import util
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
REGISTRATION_KEY = "monitor_docker"


docker_monitor = None


class RegistrationError(Exception):
    pass

class DeregistrationError(Exception):
    pass

class DockerMonitor(object):
    """
    Object responsible for keeping track of the VMs being monitored.
    """


    def __init__(self, host=None):
        self.VMS = {}

        if host:
            self.host = host

    def register(self, vm):
        if not self.is_registered(vm):
            try:
                self.set_registration_key(vm)
                self.start_monitoring(vm)
            except Exception, e:
                return RegistrationError(str(e))

            self.VMS[vm.get_id()] = vm
        else:
            return RegistrationError("VM is already registered.")

    def deregister(self, vm):
        if self.is_registered(vm):
            try:
                self.remove_registration_key(vm)
                self.stop_monitoring(vm)
            except Exception, e:
                return DeregistrationError(str(e))

            self.VMS.pop(vm.get_id())
            return
        else:
            return DeregistrationError("VM was not previously registered.")

    def set_registration_key(self, vm):
        vm.set_other_config_key(REGISTRATION_KEY, 'True')

    def remove_registration_key(self, vm):
        vm.remove_other_config_key(REGISTRATION_KEY)

    def get_registered(self):
        return self.VMS.values()

    def is_registered(self, vm):
        """
        Return True if VM has already been registered.
        """
        return vm.get_id() in self.VMS.keys()

    def start_monitoring(self, vm):
        log.info("Starting to monitor VM: %s" % vm)
        thread.start_new_thread(monitor_vm, (vm.get_session(), vm.get_uuid()))
        return

    def stop_monitoring(self, vm):
        # @todo: refactor this code to handle tunnels, so the fh is not longer
        # required to communicate with docker.
        # @todo: need to make the threads interruptible.
        try:
            os.close(MONITORDICT[vm.get_id()])
        except:
            pass

    def refresh(self):
        # @todo: switch from vmrecord to cacheable VM objects
        vm_records = self.host.client.get_all_vm_records()
        for vm_rec in vm_records.values():
            self.process_vmrecord(vm_rec)

        return

    def _should_start_monitoring(self, vmrecord):

        # Check the VM is registered for monitoring
        if REGISTRATION_KEY not in vmrecord['other_config']:
            return False

        # Only process events for running machines.
        elif vmrecord['power_state'] != 'Running':
            return False

        # Ensure we only monitor VMs on this host.
        elif vmrecord['resident_on'] != self.host.ref:
            return False

        # Ignore Dom0.
        elif vmrecord['is_control_domain']:
            return False

        # Ignore events for VMs being monitored.
        elif vmrecord['uuid'] in MONITORDICT:
            return False

        else:
            # If conditions above are met, we should process the event.
            return True

    def _should_stop_monitoring(self, vmrecord):

        # Only process events when the Halted state is reached.
        if vmrecord['power_state'] != 'Halted':
            return False

        # Check whether the VM is being actively monitored.
        elif vmrecord['uuid'] not in MONITORDICT:
            return False

        else:
            return True

    def process_vmrecord(self, vmrecord):
        """
        This function is for processing a vmrecord and determining the course
        of action that should be taken.
        """
        ## Checking that the VM is:
        ##   * Running
        ##   * Not Dom0
        ##   * Is not already being monitored
        if self._should_start_monitoring(vmrecord):
            log.info("Adding monitor for VM name: %s, UUID: %s"
                 % (vmrecord['name_label'], vmrecord['uuid']))
            ## Keeping the status of the VM
            MONITORDICT[vmrecord['uuid']] = "starting"
            ## Kicks off the monitoring thread
            thread.start_new_thread(monitor_vm, (self.host.get_session(), vmrecord['uuid'],))
        ## If the VM is:
        ##    * Off
        ##    * not in MONITORDICT
        ## Then try to 'close' the monitor dict thread (?) and delete from register
        elif self._should_stop_monitoring(vmrecord):
            log.info("Removing monitor for VM name: %s, UUID: %s"
                 % (vmrecord['name_label'], vmrecord['uuid']))
            try:
                os.close(MONITORDICT[vmrecord['uuid']])
            except:
                pass
            del MONITORDICT[vmrecord['uuid']]


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


def monitor_host():

    client = api_helper.XenAPIClient()
    session = client.session
    host = api_helper.Host(client, api_helper.get_this_host_ref(session))

    # Initialise the DockerMonitor
    global docker_monitor
    docker_monitor = DockerMonitor(host)

    while True:
        try:
            session = api_helper.get_local_api_session()
            hostref = api_helper.get_this_host_ref(session)
            try:
                session.xenapi.event.register(["vm"])
                # Load the VMs that are enabled for monitoring
                docker_monitor.refresh()
                while True:
                    try:
                        events = session.xenapi.event.next()
                        for event in events:
                            if (event['operation'] == 'mod'
                                and 'snapshot' in event):
                                    # At this point the monitor may need to
                                    # refresh it's monitoring state of a particular
                                    # vm.
                                    docker_monitor.process_vmrecord(event['snapshot'])
                    except XenAPI.Failure, exception:
                        if exception.details != "EVENTS_LOST":
                            raise
                        # handle EVENTS_LOST API failure
                        log.warning("Recovering from EVENTS_LOST")
                        session.xenapi.event.unregister(["vm"])
                        session.xenapi.event.register(["vm"])
                        # Work around if we suffer an EVENTS_LOST XAPI exception
                        # ensure we kick off a full refresh.
                        docker_monitor.refresh()
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
