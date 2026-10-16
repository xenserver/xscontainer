from xscontainer import api_helper
from xscontainer import util
from xscontainer.util import log
import constants

import base64
import errno
import fcntl
import os
import select
import shutil
import socket
import struct
import subprocess
import sys
import tempfile

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
    # Keep the Unix-socket read side open after request EOF.  Without this,
    # current ncat closes the socket before modern Docker daemons finish the
    # response, which Docker reports as HTTP status 499.
    return ("ncat --no-shutdown -U %s" % (DOCKER_SOCKET_PATH))


def _key_type(hostkey):
    """Return the SSH key type embedded in a base64 public key blob."""
    try:
        blob = base64.b64decode(hostkey)
        if len(blob) < 4:
            raise ValueError("short SSH key blob")
        length = struct.unpack(">I", blob[:4])[0]
        keytype = blob[4:4 + length]
        if not keytype or len(keytype) != length:
            raise ValueError("invalid SSH key blob")
        return keytype
    except (TypeError, ValueError, struct.error) as exception:
        raise SshException("Unable to decode remembered SSH host key: %s"
                           % exception)


class OpenSshConnection(object):
    """Temporary OpenSSH configuration for one VM connection.

    OpenSSH is used instead of the bundled Python 2 Paramiko.  The latter no
    longer shares a key exchange algorithm with current OpenSSH servers.
    """

    def __init__(self, session, vmuuid):
        self.session = session
        self.vmuuid = vmuuid
        self.username = api_helper.get_vm_xscontainer_username(session,
                                                               vmuuid)
        self.host = api_helper.get_suitable_vm_ip(session, vmuuid, SSH_PORT)
        self.directory = None
        self.private_key = None
        self.known_hosts = None
        self.remembered_hostkey = api_helper.get_ssh_hostkey(session, vmuuid)

    def __enter__(self):
        self.directory = tempfile.mkdtemp(prefix="xscontainer-ssh-")
        try:
            os.chmod(self.directory, 0700)
            self.private_key = os.path.join(self.directory, "id_rsa")
            self.known_hosts = os.path.join(self.directory, "known_hosts")
            with open(self.private_key, "w") as keyfile:
                keyfile.write(
                    api_helper.get_idrsa_secret_private(self.session))
            os.chmod(self.private_key, 0600)
            if self.remembered_hostkey:
                with open(self.known_hosts, "w") as hostfile:
                    hostfile.write("%s %s %s\n" %
                                   (self.host,
                                    _key_type(self.remembered_hostkey),
                                    self.remembered_hostkey))
                os.chmod(self.known_hosts, 0600)
            return self
        except Exception:
            shutil.rmtree(self.directory)
            self.directory = None
            raise

    def __exit__(self, _exception_type, _exception, _traceback):
        if self.directory:
            shutil.rmtree(self.directory)

    def command(self, remote_command):
        strict_host_key = "yes" if self.remembered_hostkey else "accept-new"
        command = [
            "/usr/bin/ssh",
            "-p", str(SSH_PORT),
            "-i", self.private_key,
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "HashKnownHosts=no",
            "-o", "StrictHostKeyChecking=%s" % strict_host_key,
            "-o", "UserKnownHostsFile=%s" % self.known_hosts,
            "-o", "ConnectTimeout=300",
        ]
        if self.remembered_hostkey:
            keytype = _key_type(self.remembered_hostkey)
            if keytype == "ssh-rsa":
                # An RSA key can use SHA-2 signatures even though its key blob
                # is identified by the historical ssh-rsa name.
                algorithms = "rsa-sha2-512,rsa-sha2-256,ssh-rsa"
            else:
                algorithms = keytype
            command.extend(["-o", "HostKeyAlgorithms=%s" % algorithms])
        command.extend(["%s@%s" % (self.username, self.host),
                        remote_command])
        return command

    def remember_host_key(self):
        if self.remembered_hostkey:
            return
        try:
            with open(self.known_hosts, "r") as hostfile:
                fields = hostfile.readline().strip().split()
            if len(fields) < 3:
                raise ValueError("invalid known_hosts entry")
            hostkey = fields[2]
            _key_type(hostkey)
        except (IOError, ValueError) as exception:
            raise SshException("Unable to read the accepted SSH host key: %s"
                               % exception)
        log.debug("No public key on record found for %s. Will remember."
                  % hostkey)
        api_helper.set_ssh_hostkey(self.session, self.vmuuid, hostkey)
        self.remembered_hostkey = hostkey


def _raise_process_error(vmuuid, returncode, stderr):
    if "Permission denied" in stderr:
        message = ("OpenSSH failed to authenticate with the private key on "
                   "VM %s" % vmuuid)
        log.info(message)
        raise AuthenticationException(message)
    if ("REMOTE HOST IDENTIFICATION HAS CHANGED" in stderr or
            "Host key verification failed" in stderr):
        message = ("Key for VM %s does not match the known public key."
                   % vmuuid)
        log.error(message)
        raise VmHostKeyException(message)
    raise SshException("OpenSSH connection to VM %s failed with rc %d: %s"
                       % (vmuuid, returncode, stderr.strip()))


def execute_docker(session, vmuuid, request):
    return execute_ssh(session, vmuuid, prepare_request_cmd(), request)


def execute_ssh(session, vmuuid, cmd, stdin_input=None):
    if isinstance(cmd, list):
        cmd = ' '.join(cmd)
    stripped_stdin_input = stdin_input
    if stripped_stdin_input:
        stripped_stdin_input = stripped_stdin_input.strip()
    log.info("execute_ssh will run '%s' with stdin '%s' on vm %s"
             % (cmd, stripped_stdin_input, vmuuid))
    try:
        with OpenSshConnection(session, vmuuid) as connection:
            process = subprocess.Popen(connection.command(cmd),
                                       stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(stdin_input)
            if process.returncode != 0:
                _raise_process_error(vmuuid, process.returncode, stderr)
            connection.remember_host_key()
            if len(stdout) > constants.MAX_BUFFER_SIZE:
                raise SshException("too much data was returned when executing"
                                   "'%s'" % cmd)
            return stdout
    except SshException:
        raise
    except (IOError, OSError, socket.error) as exception:
        raise SshException("execute_ssh: %s" % exception,
                           (sys.exc_info()[2]))


def execute_docker_data_listen(session, vmuuid, request,
                               stop_monitoring_request):
    cmd = prepare_request_cmd()
    log.info("execute_docker_listen_charbychar is running '%s' on VM '%s'"
             % (cmd, vmuuid))
    with OpenSshConnection(session, vmuuid) as connection:
        process = subprocess.Popen(connection.command(cmd),
                                   stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        try:
            process.stdin.write(request)
            process.stdin.close()
            stdout_fd = process.stdout.fileno()
            fcntl.fcntl(stdout_fd, fcntl.F_SETFL,
                        os.O_NONBLOCK |
                        fcntl.fcntl(stdout_fd, fcntl.F_GETFL))
            while not stop_monitoring_request:
                rlist, _, _ = select.select(
                    [stdout_fd], [], [],
                    constants.MONITOR_EVENTS_POLL_INTERVAL)
                if not rlist:
                    continue
                try:
                    read_data = process.stdout.read(1)
                    if read_data == "":
                        break
                    yield read_data
                except IOError as exception:
                    if exception[0] not in (errno.EAGAIN, errno.EINTR):
                        raise
                    sys.exc_clear()
            returncode = process.poll()
            if returncode is not None and returncode != 0:
                _raise_process_error(vmuuid, returncode,
                                     process.stderr.read())
            connection.remember_host_key()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait()
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
