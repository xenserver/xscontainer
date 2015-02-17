import api_helper
import util

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


def prepare_ssh_client(session, vmuuid):
    username = api_helper.get_vm_xscontainer_username(session, vmuuid)
    host = api_helper.get_suitable_vm_ip(session, vmuuid)
    ensure_idrsa(session)
    client = paramiko.SSHClient()
    pkey = paramiko.rsakey.RSAKey.from_private_key(
        StringIO.StringIO(api_helper.get_idrsa_secret_private(session)))
    client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
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
