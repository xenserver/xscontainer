import ApiHelper
import Log

import os
import socket
import subprocess
import tempfile
import time
import xml.dom.minidom
import xml.sax.saxutils

IDRSAFILENAME = '/tmp/xscontainer-idrsa'


class XSContainerException(Exception):

    def customised(self):
        pass


def runlocal(cmd, shell=False, canfail=False):
    Log.debug('Running: %s' % (cmd))
    process = subprocess.Popen(cmd,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE,
                               shell=shell)
    stdout, stderr = process.communicate('')
    returncode = process.returncode
    Log.debug('Command %s exited with rc %d: Stdout: %s Stderr: %s' %
              (cmd, returncode, stdout, stderr))
    if returncode != 0 and not canfail:
        raise(XSContainerException('Command failed'))
    return (returncode, stdout, stderr)


def converttoxml(node, parentelement=None, dom=None):
    if not dom or not parentelement:
        dom = xml.dom.minidom.Document()
        converttoxml(node, parentelement=dom, dom=dom)
        return dom.toxml()

    if type(node) == type([]):
        for item in node:
            converttoxml(item, parentelement=parentelement, dom=dom)
    elif type(node) in [type(''), type(1), type(1.1)]:
        textnode = dom.createTextNode(xml.sax.saxutils.escape(str(node)))
        parentelement.appendChild(textnode)
    elif type(node) == type({}):
        for key, value in node.iteritems():
            element = dom.createElement(xml.sax.saxutils.escape(key))
            parentelement.appendChild(element)
            converttoxml(value, parentelement=element, dom=dom)


def create_idrsa():
    idrsafile = tempfile.mkstemp()[1]
    os.remove(idrsafile)
    cmd = ['ssh-keygen', '-f', idrsafile, '-N', '']
    runlocal(cmd)
    idrsapriv = read_file("%s" % (idrsafile))
    idrsapub = read_file("%s.pub" % (idrsafile))
    os.remove(idrsafile)
    return (idrsapriv, idrsapub)


def read_file(filepath):
    filehandle = open(filepath, 'r')
    content = filehandle.read()
    filehandle.close()
    return content


def write_file(filepath, content):
    filehandle = open(filepath, "w+")
    filehandle.write(content)
    filehandle.close()
    os.chmod(filepath, 0600)


def ensure_idrsa(session):
    neednewfile = False
    if os.path.exists(IDRSAFILENAME):
        mtime = os.path.getmtime(IDRSAFILENAME)
        if time.time() - mtime > 60:
            neednewfile = True
    else:
        neednewfile = True
    if neednewfile:
        write_file(IDRSAFILENAME, ApiHelper.get_idrsa_secret_private(session))


def prepare_ssh_cmd(session, vmuuid, cmd):
    user = 'core'
    host = get_suitable_vm_ip(session, vmuuid)
    ensure_idrsa(session)
    complete_cmd = ['ssh', '-o', 'UserKnownHostsFile=/dev/null',
                    '-o', 'StrictHostKeyChecking=no',
                    '-o', 'PasswordAuthentication=no',
                    '-o', 'LogLevel=quiet',
                    '-o', 'ConnectTimeout=10',
                    '-i', IDRSAFILENAME, '%s@%s' % (user, host)] + cmd
    return complete_cmd


def execute_ssh(session, vmuuid, cmd):
    complete_cmd = prepare_ssh_cmd(session, vmuuid, cmd)
    stdout = runlocal(complete_cmd)[1]
    return str(stdout)


def test_connection(address, port):
    try:
        asocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow the connection to block for 2 seconds
        asocket.settimeout(2)
        asocket.connect((address, port))
        asocket.close()
        return True
    except (socket.error, socket.timeout):
        return False


def get_suitable_vm_ip(session, vmuuid):
    ips = ApiHelper.get_vm_ips(session, vmuuid)
    stage1filteredips = []
    for address in ips.itervalues():
        if ':' not in address:
            # If we get here - it's ipv4
            if address.startswith('169.254.'):
                # we prefer host internal networks and put them at the front
                stage1filteredips.insert(0, address)
            else:
                stage1filteredips.append(address)
        else:
            # Ignore ipv6 as Dom0 won't be able to use it
            pass
    for address in stage1filteredips:
        if test_connection(address, 22):
            return address
    raise XSContainerException(
        "No valid IP found for vmuuid %s" % (vmuuid))
