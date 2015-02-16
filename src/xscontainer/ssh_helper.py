from xscontainer import api_helper
from xscontainer import util
from xscontainer.util import log

import os
import time
import paramiko
import paramiko.rsakey
import StringIO

IDRSAFILENAME = '/opt/xensource/packages/files/xscontainer/xscontainer-idrsa'


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
                log.error("Key for %s does not match the public key on record"
                          % (hostname))
                raise util.XSContainerException("SSH key provided by VM does "
                                                "not match key on record.")
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
    client.connect(host, port=22, username=username, pkey=pkey,
                   look_for_keys=False)
    return client


def execute_ssh(session, vmuuid, cmd):
    max_read_size = 4 * 1024
    client = None
    try:
        client = prepare_ssh_client(session, vmuuid)
        if isinstance(cmd, list):
            cmd = ' '.join(cmd)
        _, stdout, _ = client.exec_command(cmd)
        output = stdout.read(max_read_size)
        if stdout.read(1) != "":
            raise Exception("too much data was returned when executing '%s'"
                            % (cmd))
        client.close()
        return output
    except Exception, exception:
        if client:
            client.close()
        raise util.XSContainerException("execute_ssh error: %r" % exception)
