from xscontainer import api_helper
from xscontainer import docker
from xscontainer import util
from xscontainer.util import log

import errno
import fcntl
import os
import select
import subprocess
import simplejson
import thread
import time
import signal
import socket
import sys
import XenAPI
import xmlrpclib

MONITORRETRYSLEEPINS = 15
MONITOR_EVENTS_POLL_INTERVAL = 0.5
MONITOR_TIMEOUT_WARNING_S = 75.0
REGISTRATION_KEY = "xscontainer-monitor"
EVENT_FROM_TIMEOUT_S = 3600.0
XAPIRETRYSLEEPINS = 10

DOCKER_MONITOR = None


class RegistrationError(Exception):
    pass


class DeregistrationError(Exception):
    pass


class MonitoredVM(api_helper.VM):

    """A VM class that can be monitored."""
    __stop_monitoring_request = False
    __children_pid = None


    def start_monitoring(self):
        thread.start_new_thread(self.__monitoring_loop, tuple())

    def stop_monitoring(self, force=False):
        self.__stop_monitoring_request = True
        if force:
            pid = self.__children_pid
            if pid:
                util.log.warning("Trying to sigkill %d" % (pid))
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    util.log.exception("Error when running os.kill for %d"
                                       % (pid))

    def __monitoring_loop(self):
        # ToDo: not needed and not safe - doesn't survive XAPI restarts
        vmuuid = self.get_uuid()
        start_time = time.time()
        error_message = None
        while not self.__stop_monitoring_request:
            docker.wipe_docker_other_config(self)
            try:
                docker.update_docker_ps(self)
                docker.update_docker_info(self)
                docker.update_docker_version(self)
                if error_message:
                    # if we got past the above, it's about time to delete the
                    # error message, as all appears to be working again
                    try:
                        api_helper.destroy_message(self.get_session(),
                                                   error_message)
                    except XenAPI.Failure:
                        # this can happen if the user deleted the message in the
                        # meantime manually, or if XAPI is down
                        pass
                    error_message = None
            except (XenAPI.Failure, util.XSContainerException):
                passed_time = time.time() - start_time
                if (not error_message
                        and passed_time >= MONITOR_TIMEOUT_WARNING_S):
                    try:
                        session = self.get_session()
                        cause = docker.determine_error_cause(session, vmuuid)
                        error_message = api_helper.send_message(
                            session,
                            self.get_uuid(),
                            "Cannot monitor containers on VM",
                            cause)
                    except (XenAPI.Failure):
                        # this can happen when XAPI is not running
                        pass
                log.info("Could not connect to VM %s, retry" % (vmuuid))
            try:
                self.__monitor_vm_events()
            except (XenAPI.Failure, util.XSContainerException):
                log.exception("monitor_vm_events threw an exception, retry")
            if not self.__stop_monitoring_request:
                time.sleep(MONITORRETRYSLEEPINS)
        docker.wipe_docker_other_config(self)
        log.info("monitor_vm returns from handling vm %s" % (vmuuid))

    def __monitor_vm_events(self):
        session = self.get_session()
        vmuuid = self.get_uuid()
        request_cmds = docker.prepare_request_cmds('GET', '/events')
        cmds = api_helper.prepare_ssh_cmd(session, vmuuid, request_cmds)
        log.debug('monitor_vm is running: %s' % (cmds))
        process = subprocess.Popen(cmds,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   stdin=subprocess.PIPE,
                                   shell=False)
        self.__children_pid = process.pid
        process.stdin.write("\n")
        data = ""
        # set unblocking io for select.select
        process_fd = process.stdout.fileno()
        fcntl.fcntl(process_fd,
                    fcntl.F_SETFL,
                    os.O_NONBLOCK | fcntl.fcntl(process_fd, fcntl.F_GETFL))
        # @todo: should make this more sane
        skippedheader = False
        openbrackets = 0
        while not self.__stop_monitoring_request:
            rlist, _, _ = select.select([process_fd], [], [],
                                        MONITOR_EVENTS_POLL_INTERVAL)
            if not rlist:
                continue
            try:
                # @todo: should read more than one char at once
                lastread = process.stdout.read(1)
            except IOError, e:
                if e[0] not in (errno.EAGAIN, errno.EINTR):
                    raise
                sys.exc_clear()
                continue
            if lastread == '':
                break
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
                    event = simplejson.loads(data)
                    self.handle_docker_event(event)
                    data = ""
            if len(data) >= 2048:
                raise util.XSContainerException('monitor_vm buffer is full')
        if self.__stop_monitoring_request:
            try:
                if getattr(process, 'kill', None):
                    # Only availiable on newer version of python
                    process.kill()
                else:
                    log.debug("I kill")
                    os.kill(process.pid, signal.SIGTERM)
            except OSError:
                util.log.exception("Error when running os.kill for %d"
                                   % (process.pid))
        process.wait()
        returncode = process.returncode
        log.debug('monitor_vm (%s) exited with rc %s' %
                  (cmds, str(returncode)))

    def handle_docker_event(self, event):
        if 'status' in event:
            if event['status'] in ['create', 'destroy', 'die',
                                   'kill', 'pause', 'restart',
                                   'start', 'stop', 'unpause']:
                try:
                    docker.update_docker_ps(self)
                except util.XSContainerException, exception:
                    # This can happen, when the docker daemon stops
                    log.exception(exception)
            elif event['status'] in ['create', 'destroy', 'delete']:
                try:
                    docker.update_docker_info(self)
                except util.XSContainerException, exception:
                    # This can happen, when the docker daemon stops
                    log.exception(exception)


class DockerMonitor(object):

    """
    Object responsible for keeping track of the VMs being monitored.
    """

    host = None

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
            self.vms.pop(thevm.get_id(), None)
        else:
            return DeregistrationError("VM was not previously registered.")

    def get_registered(self):
        return self.vms.values()

    def get_vm_by_ref(self, vm_ref):
        return self.vms.get(vm_ref)

    def is_registered(self, thevm):
        """
        Return True if VM has already been registered.
        """
        return self.is_registered_vm_ref(thevm.get_id())

    def is_registered_vm_ref(self, vm_ref):
        return vm_ref in self.vms.keys()

    def _start_monitoring(self, vm_ref):
        log.info("Starting to monitor VM: %s" % vm_ref)
        thevm = MonitoredVM(self.host.client, ref=vm_ref)
        self.register(thevm)
        thevm.start_monitoring()
        return

    def _stop_monitoring(self, vm_ref):
        log.info("Removing monitor for VM ref: %s"
                 % vm_ref)
        thevm = self.get_vm_by_ref(vm_ref)
        if thevm:
            self.deregister(thevm)
            thevm.stop_monitoring()

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
            self._start_monitoring(vmref)
        elif is_monitored and not should_monitor:
            self._stop_monitoring(vmref)

    def tear_down_all(self):
        for entry in self.get_registered():
            entry.stop_monitoring()
        # Wait for children
        time.sleep(2)
        # If Any are left - force them
        for entry in self.get_registered():
            entry.stop_monitoring(force=True)


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
        except (socket.error, XenAPI.Failure, xmlrpclib.ProtocolError):
            if session is not None:
                log.info("Could not connect to XAPI - Is XAPI running? " +
                         "Will retry in %d" % (XAPIRETRYSLEEPINS))
            else:
                log.exception("Recovering from XAPI failure - Is XAPI " +
                              "restarting? Will retry in %d."
                              % (XAPIRETRYSLEEPINS))
            time.sleep(XAPIRETRYSLEEPINS)
