from xscontainer import api_helper
from xscontainer import docker
from xscontainer import ssh_helper
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

MONITORRETRYSLEEPINS = 20
MONITOR_EVENTS_POLL_INTERVAL = 1
MONITOR_TIMEOUT_WARNING_S = 75.0
REGISTRATION_KEY = "xscontainer-monitor"
REGISTRATION_KEY_ON = 'True'
REGISTRATION_KEY_OFF = 'False'
EVENT_FROM_TIMEOUT_S = 3600.0
XAPIRETRYSLEEPINS = 10

DOCKER_MONITOR = None


class RegistrationError(Exception):
    pass


class DeregistrationError(Exception):
    pass


class MonitoredVM(api_helper.VM):

    """A VM class that can be monitored."""
    _stop_monitoring_request = False
    _ssh_client = None
    _error_message = None

    def start_monitoring(self):
        thread.start_new_thread(self._monitoring_loop, tuple())

    def stop_monitoring(self):
        self._stop_monitoring_request = True
        ssh_client = self._ssh_client
        if ssh_client:
            ssh_client.close()

    def _send_monitor_error_message(self):
        self._wipe_monitor_error_message_if_needed()
        try:
            session = self.get_session()
            vmuuid = self.get_uuid()
            cause = docker.determine_error_cause(session, vmuuid)
            log.info("_send_monitor_error_message for VM %s: %s"
                     % (vmuuid, cause))
            self._error_message = api_helper.send_message(
                session,
                vmuuid,
                "Container Management cannot monitor VM",
                cause)
        except (XenAPI.Failure):
            # this can happen when XAPI is not running.
            pass

    def _wipe_monitor_error_message_if_needed(self):
        if self._error_message:
            try:
                log.info("_wipe_monitor_error_message needed for VM %s: %s"
                         % (self.get_uuid(), self._error_message))
                api_helper.destroy_message(self.get_session(),
                                           self._error_message)
            except XenAPI.Failure:
                # this can happen if the user deleted the message in the
                # meantime manually, or if XAPI is down
                pass
            self._error_message = None

    def _monitoring_loop(self):
        vmuuid = self.get_uuid()
        log.info("monitor_loop handles VM %s" % (vmuuid))
        start_time = time.time()
        docker.wipe_docker_other_config(self)
        # keep track of when to wipe other_config to safe CPU-time
        while not self._stop_monitoring_request:
            try:
                docker.update_docker_info(self)
                docker.update_docker_version(self)
                # if we got past the above, it's about time to delete the
                # error message, as all appears to be working again
                self._wipe_monitor_error_message_if_needed()
                try:
                    try:
                        self.__monitor_vm_events()
                    finally:
                        docker.wipe_docker_other_config(self)
                except (XenAPI.Failure, util.XSContainerException):
                    log.exception("__monitor_vm_events threw an exception, "
                                  "will retry")
                    raise
            except (XenAPI.Failure, util.XSContainerException):
                passed_time = time.time() - start_time
                if (not self._error_message
                        and passed_time >= MONITOR_TIMEOUT_WARNING_S):
                    self._send_monitor_error_message()
                log.info("Could not connect to VM %s, will retry" % (vmuuid))
            if not self._stop_monitoring_request:
                time.sleep(MONITORRETRYSLEEPINS)
        log.info("monitor_loop returns from handling vm %s" % (vmuuid))

    def __monitor_vm_events(self):
        session = self.get_session()
        vmuuid = self.get_uuid()
        ssh_client = ssh_helper.prepare_ssh_client(session, vmuuid)
        try:
            cmd = docker.prepare_request_cmd()
            log.info("__monitor_vm_events is running '%s' on VM '%s'"
                     % (cmd, vmuuid))
            stdin, stdout, _ = ssh_client.exec_command(cmd)
            stdin.write(docker.prepare_request_stdin('GET', '/events'))
            stdin.channel.shutdown_write()
            self._ssh_client = ssh_client
            # Not that we are listening for events, get the latest state
            docker.update_docker_ps(self)
            # set unblocking io for select.select
            stdout_fd = stdout.channel.fileno()
            fcntl.fcntl(stdout_fd,
                        fcntl.F_SETFL,
                        os.O_NONBLOCK | fcntl.fcntl(stdout_fd, fcntl.F_GETFL))
            # @todo: should make this more sane
            skippedheader = False
            openbrackets = 0
            data = ""
            while not self._stop_monitoring_request:
                rlist, _, _ = select.select([stdout_fd], [], [],
                                            MONITOR_EVENTS_POLL_INTERVAL)
                if not rlist:
                    continue
                try:
                    # @todo: should read more than one char at once
                    lastread = stdout.read(1)
                except IOError, exception:
                    if exception[0] not in (errno.EAGAIN, errno.EINTR):
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
                    raise util.XSContainerException('__monitor_vm_events' +
                                                    'is full')
        finally:
            try:
                ssh_client.close()
            except Exception:
                util.log.exception("Error when closing ssh_client for %r"
                                   % ssh_client)
        log.info('__monitor_vm_events (%s) exited' % cmd)

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

    def start_monitoring(self, vm_ref):
        log.info("Starting to monitor VM: %s" % vm_ref)
        thevm = MonitoredVM(self.host.client, ref=vm_ref)
        self.register(thevm)
        thevm.start_monitoring()
        return

    def stop_monitoring(self, vm_ref):
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
                (vmrecord['other_config'][REGISTRATION_KEY] !=
                 REGISTRATION_KEY_ON)):
            return False

        # Only process events for running machines.
        elif vmrecord['power_state'] != 'Running':
            return False

        # Ensure we only monitor VMs on this host.
        elif vmrecord['resident_on'] != self.host.ref:
            return False

        # We can't get the IP if the guest tools don't run
        elif vmrecord['guest_metrics'] == api_helper.NULLREF:
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
            entry.stop_monitoring()
        # @todo: we could have wait for thread.join with timeout here
        # Wait for children
        time.sleep(2)


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

    # container monitoring can get a smaller slice of the CPU time
    os.nice(10)

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
            log.info("Monitoring host %s" % (host.get_id()))
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
                log.error("Could not connect to XAPI - Is XAPI running? " +
                          "Will retry in %d" % (XAPIRETRYSLEEPINS))
            else:
                log.exception("Recovering from XAPI failure - Is XAPI " +
                              "restarting? Will retry in %d."
                              % (XAPIRETRYSLEEPINS))
            time.sleep(XAPIRETRYSLEEPINS)
