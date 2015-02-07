from xscontainer import api_helper
from xscontainer import docker
from xscontainer import util
from xscontainer.util import log

import os
import subprocess
import simplejson
import thread
import time
import signal
import socket
import sys
import XenAPI

MONITORRETRYSLEEPINS = 15
REGISTRATION_KEY = "xscontainer-monitor"
EVENT_FROM_TIMEOUT_S = 3600.0
XAPIRETRYSLEEPINS = 10

DOCKER_MONITOR = None


class RegistrationError(Exception):
    pass


class DeregistrationError(Exception):
    pass


class DockerMonitor(object):

    """
    Object responsible for keeping track of the VMs being monitored.
    """

    host = None

    class VMWithPid(api_helper.VM):

        pid = None
        teardown_requested = False

    def __init__(self, host=None):
        self.vms = {}

        self.set_host(host)

    def set_host(self, host):
        self.host = host

    def register(self, thevm):
        if not self.is_registered(thevm):
            self.vms[thevm.get_id()] = thevm
        else:
            return RegistrationError("VM is already registered.")

    def deregister(self, thevm):
        if self.is_registered(thevm):
            self.vms.pop(thevm.get_id())
        else:
            return DeregistrationError("VM was not previously registered.")

    def get_registered(self):
        return self.vms.values()

    def get_vmwithpid_by_ref(self, vm_ref):
        return self.vms.get(vm_ref)

    def is_registered(self, thevm):
        """
        Return True if VM has already been registered.
        """
        return self.is_registered_vm_ref(thevm.get_id())

    def is_registered_vm_ref(self, vm_ref):
        return vm_ref in self.vms.keys()

    def start_monitoring(self, vm_ref):
        log.info("Starting to monitor VM: %s" % vm_ref)
        vmwithpid = DockerMonitor.VMWithPid(self.host.client,
                                            ref=vm_ref)
        self.register(vmwithpid)
        thread.start_new_thread(self.monitor_vm, (vmwithpid,))
        return

    def stop_monitoring(self, vm_ref):
        log.info("Removing monitor for VM ref: %s"
                 % vm_ref)
        vmwithpid = self.get_vmwithpid_by_ref(vm_ref)
        if vmwithpid:
            pid = vmwithpid.pid
            if pid:
                try:
                    util.log.info("Trying to sigterm %d" % (pid))
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    util.log.exception("Error when running os.kill for %d"
                                       %(pid))
            vmwithpid.teardown_requested = True

    def refresh(self):
        vm_records = self.host.client.get_all_vm_records()
        for (vm_ref, vm_rec) in vm_records.items():
            self.process_vmrecord(vm_ref, vm_rec)
        return

    def _should_monitor(self, vmrecord):
        # Check the VM is registered for monitoring
        if (REGISTRATION_KEY not in vmrecord['other_config'] or
                vmrecord['other_config'][REGISTRATION_KEY] != 'True'):
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

        else:
            # If conditions above are met, we should process the event.
            return True

    def process_vmrecord(self, vmref, vmrecord):
        """
        This function is for processing a vmrecord and determining the course
        of action that should be taken.
        """
        is_monitored = self.is_registered_vm_ref(vmref)
        should_monitor = self._should_monitor(vmrecord)
        if not is_monitored and should_monitor:
            self.start_monitoring(vmref)
        elif is_monitored and not should_monitor:
            self.stop_monitoring(vmref)

    def tear_down_all(self):
        for entry in self.get_registered():
            pid = entry.pid
            if pid:
                util.log.debug("Trying to sigterm %d" % (pid))
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    util.log.exception("Error when running os.kill for %d"
                                       %(pid))
            entry.teardown_requested = True
        # Wait for children
        time.sleep(2)
        # If Any are left - force them
        for entry in self.get_registered():
            pid = entry.pid
            if pid:
                util.log.warning("Trying to sigkill %d" % (pid))
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    util.log.exception("Error when running os.kill for %d"
                                       %(pid))

    def monitor_vm(self, thevm):
        session = thevm.get_session()
        vmuuid = thevm.get_uuid()
        while not thevm.teardown_requested:
            try:
                docker.update_docker_ps(thevm)
                docker.update_docker_info(thevm)
                docker.update_docker_version(thevm)
            except (XenAPI.Failure, util.XSContainerException):
                log.info("Could not connect to VM %s, retry" % (vmuuid))
            try:
                monitor_vm_events(session, thevm)
            except (XenAPI.Failure, util.XSContainerException):
                log.exception("monitor_vm_events threw an exception, retry")
            if not thevm.teardown_requested:
                time.sleep(MONITORRETRYSLEEPINS)
        self.deregister(thevm)
        docker.wipe_docker_other_config(thevm)
        log.info("monitor_vm returns from handling vm %s" % (vmuuid))


def monitor_vm_events(session, thevm):
    vmuuid = thevm.get_uuid()
    request_cmds = docker.prepare_request_cmds('GET', '/events')
    cmds = api_helper.prepare_ssh_cmd(session, vmuuid, request_cmds)
    log.debug('monitor_vm is running: %s' % (cmds))
    process = subprocess.Popen(cmds,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE,
                               shell=False)
    thevm.pid = process.pid
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
                results = simplejson.loads(data)
                if 'status' in results:
                    log.debug("Received %s" %(results['status']))
                    if results['status'] in ['create', 'destroy', 'die',
                                             'kill', 'pause', 'restart',
                                             'start', 'stop', 'unpause']:
                        try:
                            docker.update_docker_ps(thevm)
                        except util.XSContainerException, exception:
                            # This can happen, when the docker daemon stops
                            log.exception(exception)
                    elif results['status'] in ['create', 'destroy', 'delete']:
                        try:
                            docker.update_docker_info(thevm)
                        except util.XSContainerException, exception:
                            # This can happen, when the docker daemon stops
                            log.exception(exception)
                    # ignore untag for now
                data = ""
        if len(data) >= 2048:
            raise(util.XSContainerException('monitor_vm buffer is full'))
        lastread = process.stdout.read(1)
    thevm.pid = None
    process.poll()
    returncode = process.returncode
    log.debug('monitor_vm (%s) exited with rc %s' % (cmds, str(returncode)))


def interrupt_handler(signum, frame):
    """
    This function handles SIGTERM and SIGINT. It does by tearing down the
    monitoring. We need to do this as we don't want threads to be hanging
    around, after the docker_monitor has quit.
    """
    if DOCKER_MONITOR:
        util.log.warning("Signal %d received  - Tearing down monitoring"
                         % (signum))
        DOCKER_MONITOR.tear_down_all()
    sys.exit(0)


def monitor_host():
    global DOCKER_MONITOR
    session = None
    host = None

    signal.signal(signal.SIGTERM, interrupt_handler)
    signal.signal(signal.SIGINT, interrupt_handler)

    while True:
        try:
            session = api_helper.get_local_api_session()
            client = api_helper.LocalXenAPIClient()
            # need to refresh the host, in case we just joined a pool
            host = api_helper.Host(client,
                                   api_helper.get_this_host_ref(session))
            if not DOCKER_MONITOR:
                DOCKER_MONITOR = DockerMonitor(host)
            else:
                DOCKER_MONITOR.set_host(host)
            try:
                # Avoid race conditions - get a current event token
                event_from = session.xenapi.event_from(["vm"], '',  0.0)
                token_from = event_from['token']
                # Now load the VMs that are enabled for monitoring
                DOCKER_MONITOR.refresh()
                while True:
                    event_from = session.xenapi.event_from(["vm"], token_from,
                                                           EVENT_FROM_TIMEOUT_S)
                    token_from = event_from['token']
                    events = event_from['events']
                    for event in events:
                        if (event['operation'] == 'mod'
                                and 'snapshot' in event):
                            # At this point the monitor may need to
                            # refresh it's monitoring state of a particular
                            # vm.
                            DOCKER_MONITOR.process_vmrecord(event['ref'],
                                                            event['snapshot'])
            finally:
                try:
                    session.xenapi.session.logout()
                except XenAPI.Failure:
                    log.exception("Failed when trying to logout")
        except (socket.error, XenAPI.Failure):
            if session is not None:
                log.info("Could not connect to XAPI - Is XAPI running? " +
                         "Will retry in %d" % (XAPIRETRYSLEEPINS))
            else:
                log.exception("Recovering from XAPI failure - Is XAPI " +
                              "restarting? Will retry in %d."
                              % (XAPIRETRYSLEEPINS))
            time.sleep(XAPIRETRYSLEEPINS)
