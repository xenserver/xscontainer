from xscontainer import api_helper
from xscontainer import util
from xscontainer.util import log
import constants

import fcntl
import errno
import os
import paramiko
import paramiko.rsakey
import select
import socket
import StringIO
import sys

DOCKER_SOCKET_PATH = '/var/run/docker.sock'
SSH_PORT = 22

ERROR_CAUSE_NETWORK = (
    "Error: Cannot find a valid IP that allows SSH connections to "
    "the VM. Please make sure that Tools are installed, a "
    "network route is set up, there is a SSH server running inside "
    "the VM that is reachable from Dom0.")


class SshException(util.XSContainerException):
    pass


class VmHostKeyException(SshException):
    pass


class AuthenticationException(SshException):
    pass


def prepare_request_cmd():
    return ("ncat -U %s" % (DOCKER_SOCKET_PATH))


class MyHostKeyPolicy(paramiko.MissingHostKeyPolicy):

    _session = None
    _vm_uuid = None

    def __init__(self, session, vm_uuid):
        self._session = session
        self._vm_uuid = vm_uuid

    def missing_host_key(self, client, hostname, key):
        hostkey = key.get_base64()
        remembered_hostkey = api_helper.get_ssh_hostkey(self._session,
                                                        self._vm_uuid)
        if remembered_hostkey:
            # We have a key on record
            if hostkey == remembered_hostkey:
                # all good - continue
                return
            else:
                # bad - throw error because of mismatch
                message = ("Key for VM %s does not match the known public key."
                           % (self._vm_uuid))
                log.error(message)
                raise VmHostKeyException(message)
        else:
            # we don't have key on record. Let's remember this one for next
            # time
            log.debug("No public key on record found for %s. Will remember."
                      % hostkey)
            api_helper.set_ssh_hostkey(self._session, self._vm_uuid, hostkey)
            # all good - continue
            return


def prepare_ssh_client(session, vmuuid):
    username = api_helper.get_vm_xscontainer_username(session, vmuuid)
    host = api_helper.get_suitable_vm_ip(session, vmuuid, SSH_PORT)
    log.info("prepare_ssh_client for vm %s, via %s@%s"
             % (vmuuid, username, host))
    client = paramiko.SSHClient()
    pkey = paramiko.rsakey.RSAKey.from_private_key(
        StringIO.StringIO(api_helper.get_idrsa_secret_private(session)))
    client.get_host_keys().clear()
    client.set_missing_host_key_policy(MyHostKeyPolicy(session, vmuuid))
    try:
        client.connect(host, port=SSH_PORT, username=username,
                       pkey=pkey, look_for_keys=False, banner_timeout=300)
    except SshException:
        # This exception is already improved - leave it as it is
        raise
    except paramiko.AuthenticationException as exception:
        message = ("prepare_ssh_client failed to authenticate with private key"
                   " on VM %s" % (vmuuid))
        log.info(message)
        raise AuthenticationException(message)
    except (paramiko.SSHException, socket.error) as exception:
        # reraise as SshException
        raise SshException("prepare_ssh_client: %s" % exception,
                           (sys.exc_info()[2]))
    return client


def execute_docker(session, vmuuid, request):
    return execute_ssh(session, vmuuid, prepare_request_cmd(), request)


def execute_ssh(session, vmuuid, cmd, stdin_input=None):
    client = None
    try:
        try:
            client = prepare_ssh_client(session, vmuuid)
            if isinstance(cmd, list):
                cmd = ' '.join(cmd)
            stripped_stdin_input = stdin_input
            if stripped_stdin_input:
                stripped_stdin_input = stripped_stdin_input.strip()
            log.info("execute_ssh will run '%s' with stdin '%s' on vm %s"
                     % (cmd, stripped_stdin_input, vmuuid))
            stdin, stdout, _ = client.exec_command(cmd)
            if stdin_input:
                stdin.write(stdin_input)
                stdin.channel.shutdown_write()
            output = stdout.read(constants.MAX_BUFFER_SIZE)
            if stdout.read(1) != "":
                raise SshException("too much data was returned when executing"
                                   "'%s'" % (cmd))
            returncode = stdout.channel.recv_exit_status()
            if returncode != 0:
                log.info("execute_ssh '%s' on vm %s exited with rc %d: Stdout:"
                         " %s" % (cmd, vmuuid, returncode, stdout))
                raise SshException("Returncode for '%s' is not 0" % cmd)
            return output
        except SshException:
            # This exception is already improved - leave it as it is
            raise
        except Exception as exception:
            # reraise as SshException
            raise SshException("execute_ssh: %s" % exception,
                               (sys.exc_info()[2]))
    finally:
        if client:
            client.close()


def execute_docker_data_listen(session, vmuuid, request,
                               stop_monitoring_request):
    ssh_client = prepare_ssh_client(session, vmuuid)
    try:
        cmd = prepare_request_cmd()
        log.info("execute_docker_listen_charbychar is running '%s' on VM '%s'"
                 % (cmd, vmuuid))
        stdin, stdout, _ = ssh_client.exec_command(cmd)
        stdin.write(request)
        # set unblocking io for select.select
        stdout_fd = stdout.channel.fileno()
        fcntl.fcntl(stdout_fd,
                    fcntl.F_SETFL,
                    os.O_NONBLOCK | fcntl.fcntl(stdout_fd, fcntl.F_GETFL))
        while not stop_monitoring_request:
            rlist, _, _ = select.select([stdout_fd], [], [],
                                        constants.MONITOR_EVENTS_POLL_INTERVAL)
            if not rlist:
                continue
            try:
                read_data = stdout.read(1)
                if read_data == "":
                    break
                yield read_data
            except IOError as exception:
                log.info("IOError")
                if exception[0] not in (errno.EAGAIN, errno.EINTR):
                    log.info("Cleared")
                    raise
                sys.exc_clear()
    finally:
        try:
            ssh_client.close()
        except Exception:
            util.log.exception("Error when closing ssh_client for %r"
                               % ssh_client)
            log.info('execute_docker_listen_charbychar (%s) exited' % cmd)


def determine_error_cause(session, vmuuid):
    cause = ""
    try:
        api_helper.get_suitable_vm_ip(session, vmuuid, SSH_PORT)
    except util.XSContainerException:
        cause = ERROR_CAUSE_NETWORK
        # No reason to continue, if there is no network connection
        return cause
    try:
        execute_ssh(session, vmuuid, ['echo', 'hello world'])
    except AuthenticationException:
        cause = (cause + "Unable to verify key-based authentication. "
                 "Please prepare the VM to install a key.")
        # No reason to continue, if there is no SSH connection
        return cause
    except VmHostKeyException:
        cause = (cause + "The SSH host key of the VM has unexpectedly"
                 " changed, which could potentially be a security breach."
                 " If you think this is safe and expected, you"
                 " can reset the record stored in XS using xe"
                 " vm-param-remove uuid=<vm-uuid> param-name=other-config"
                 " param-key=xscontainer-sshhostkey")
        # No reason to continue, if there is no SSH connection
        return cause
    except SshException:
        cause = (cause + "Unable to connect to the VM using SSH. Please "
                 "check the logs inside the VM and also try manually.")
        # No reason to continue, if there is no SSH connection
        return cause
    # @todo: we could alternatively support socat
    # @todo: we could probably prepare this as part of xscontainer-prepare-vm
    try:
        execute_ssh(session, vmuuid, ['command -v ncat'])
    except util.XSContainerException:
        cause = (cause + "Unable to find ncat inside the VM. Please install "
                 "ncat. ")
    try:
        execute_ssh(session, vmuuid, ['test', '-S', DOCKER_SOCKET_PATH])
    except util.XSContainerException:
        cause = (cause + "Unable to find the Docker unix socket at %s."
                         % (DOCKER_SOCKET_PATH) +
                         " Please install and run Docker.")
        # No reason to continue, if there is no docker socket
        return cause
    try:
        execute_ssh(session, vmuuid, ['test -r "%s" && test -w "%s" '
                                      % (DOCKER_SOCKET_PATH,
                                         DOCKER_SOCKET_PATH)])
    except util.XSContainerException:
        cause = (cause + "Unable to access the Docker unix socket. "
                 "Please make sure the specified user account "
                 "belongs to the docker account group.")
    if cause == "":
        cause = "Unable to determine cause of failure."
    return cause
