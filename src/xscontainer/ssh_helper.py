from xscontainer import api_helper
from xscontainer import util
from xscontainer.util import log

import os
import paramiko
import paramiko.rsakey
import socket
import StringIO
import sys
import time

IDRSAFILENAME = '/opt/xensource/packages/files/xscontainer/xscontainer-idrsa'


class SshException(util.XSContainerException):
    pass


class VmHostKeyException(SshException):
    pass


class AuthenticationException(SshException):
    pass


def ensure_idrsa(session):
    neednewfile = False
    if os.path.exists(IDRSAFILENAME):
        mtime = os.path.getmtime(IDRSAFILENAME)
        if time.time() - mtime > 60:
            neednewfile = True
    else:
        neednewfile = True
    if neednewfile:
        util.write_file(IDRSAFILENAME,
                        api_helper.get_idrsa_secret_private(session))


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
                message = ("Key for VM %s does not match the knwon public key."
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
    host = api_helper.get_suitable_vm_ip(session, vmuuid)
    ensure_idrsa(session)
    client = paramiko.SSHClient()
    pkey = paramiko.rsakey.RSAKey.from_private_key(
        StringIO.StringIO(api_helper.get_idrsa_secret_private(session)))
    client.get_host_keys().clear()
    client.set_missing_host_key_policy(MyHostKeyPolicy(session, vmuuid))
    try:
        client.connect(host, port=22, username=username, pkey=pkey,
                       look_for_keys=False)
    except SshException:
        # This exception is already improved - leave it as it is
        raise
    except paramiko.AuthenticationException, exception:
        log.exception(exception)
        raise AuthenticationException("Failed to authenticate with private key"
                                      " on VM %s." % (vmuuid))
    except (paramiko.SSHException, socket.error), exception:
        # reraise as SshException
        raise SshException, "prepare_ssh_client: %s" % exception, (
            sys.exc_info()[2])
    return client


def execute_ssh(session, vmuuid, cmd):
    log.info(" ".join(cmd))
    max_read_size = 4 * 1024
    client = None
    try:
        try:
            client = prepare_ssh_client(session, vmuuid)
            if isinstance(cmd, list):
                cmd = ' '.join(cmd)
            _, stdout, _ = client.exec_command(cmd)
            output = stdout.read(max_read_size)
            if stdout.read(1) != "":
                raise SshException("too much data was returned when executing"
                                "'%s'" % (cmd))
            return output
        except SshException:
            # This exception is already improved - leave it as it is
            raise
        except Exception, exception:
            # reraise as SshException
            raise SshException, "execute_ssh: %s" % exception, (
                sys.exc_info()[2])
    finally:
        if client:
            client.close()
