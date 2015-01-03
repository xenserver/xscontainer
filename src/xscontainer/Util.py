import ApiHelper

import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import xml.dom.minidom
import xml.sax.saxutils

logger = logging.getLogger()
loggerconfigured = False


def configurelogging():
    global loggerconfigured
    loggerconfigured = True
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def log(message):
    if not loggerconfigured:
        configurelogging()
    logger.info("%s" % (message))


def runlocal(cmd, shell=False, canfail=False):
    log("Running: %s" % (cmd))
    process = subprocess.Popen(cmd,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE,
                               shell=shell)
    stdout, stderr = process.communicate('')
    rc = process.returncode
    log("Command exited with rc %d: Stdout: %s Stderr: %s" %
        (rc, stdout, stderr))
    if rc != 0 and not canfail:
        raise(Exception("Command failed"))
    return (rc, stdout, stderr)


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
    (filehandle, idrsafile) = tempfile.mkstemp()
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


def ensure_idrsa(session, idrsafilename):
    neednewfile = False
    if os.path.exists(idrsafilename):
        mtime = os.path.getmtime(idrsafilename)
        if time.time() - mtime > 60:
            neednewfile = True
    else:
        neednewfile = True
    if neednewfile:
        write_file(idrsafilename, ApiHelper.get_idrsa_secret_private(session))


def execute_ssh(session, host, cmd):
    idrsafilename = '/tmp/xscontainer-idrsa'
    ensure_idrsa(session, idrsafilename)
    cmd = ['ssh', '-o', 'UserKnownHostsFile=/dev/null',
           '-o', 'StrictHostKeyChecking=no',
           '-o', 'PasswordAuthentication=no',
           '-o', 'LogLevel=quiet',
           '-o', 'ConnectTimeout=10',
           '-i', idrsafilename, 'core@%s' % (host)] + cmd
    stdout = runlocal(cmd)[1]
    return str(stdout)
