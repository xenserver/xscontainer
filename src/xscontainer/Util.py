import logging
import os
import pprint
import re
import signal
import subprocess
import sys
import xml.dom.minidom
import xml.sax.saxutils

# ToDo: Should use a special key
IDRSAPATH = os.path.join(os.path.expanduser('~'), '.ssh/id_rsa')

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
            pass


def ensure_idrsa():
    if not os.path.exists(IDRSAPATH):
        cmd = ['ssh-keygen', '-f', IDRSAPATH, '-N', '']
        runlocal(cmd)


def get_idrsa_pub():
    ensure_idrsa()
    filehandler = open("%s.pub" % (IDRSAPATH), 'r')
    contents = filehandler.read().split(' ')[1]
    filehandler.close()
    return contents


def execute_ssh(host, cmd):
    ensure_idrsa()
    cmd = ['ssh', '-o', 'UserKnownHostsFile=/dev/null',
           '-o', 'StrictHostKeyChecking=no',
           '-o', 'PasswordAuthentication=no',
           '-o', 'LogLevel=quiet',
           '-o', 'ConnectTimeout=10',
           '-i', IDRSAPATH, 'core@%s' % (host)] + cmd
    (rcode, stdout, stderr) = runlocal(cmd)
    return str(stdout)
