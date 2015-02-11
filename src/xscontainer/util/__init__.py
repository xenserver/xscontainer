import log

import os
import socket
import subprocess
import tempfile
import xml.dom.minidom
import xml.sax.saxutils



class XSContainerException(Exception):

    def customised(self):
        pass


def runlocal(cmd, shell=False, canfail=False):
    log.debug('Running: %s' % (cmd))
    process = subprocess.Popen(cmd,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE,
                               shell=shell)
    stdout, stderr = process.communicate('')
    returncode = process.returncode
    log.debug('Command %s exited with rc %d: Stdout: %s Stderr: %s' %
              (cmd, returncode, stdout, stderr))
    if returncode != 0 and not canfail:
        raise(XSContainerException('Command failed'))
    return (returncode, stdout, stderr)


def converttoxml(node, parentelement=None, dom=None):
    if not dom or not parentelement:
        dom = xml.dom.minidom.Document()
        converttoxml(node, parentelement=dom, dom=dom)
        return dom.toxml()

    if type(node) == list:
        for item in node:
            converttoxml(item, parentelement=parentelement, dom=dom)
    elif type(node) == dict:
        for key, value in node.iteritems():
            # Workaround: XML element names may not
            # - start with numbers, may
            # - contain slashes
            # - start with punctuations, or 'xml'.
            # Package these in a special element 'SPECIAL_XS_ENCODED_ELEMENT'
            # and take the name as a key instead
            # @todo: add a faster regular expression for this
            if (key[0].isdigit()
                or '/' in key
                or key[0] in ['.', ':', '!', '?']
                or key.lower().startswith('xml')):
                element = dom.createElement('SPECIAL_XS_ENCODED_ELEMENT')
                element.setAttribute('name', key)
            else:
                element = dom.createElement(xml.sax.saxutils.escape(key))
            parentelement.appendChild(element)
            converttoxml(value, parentelement=element, dom=dom)
    elif type(node) in [str, bool, float, int] or node == None:
        textnode = dom.createTextNode(xml.sax.saxutils.escape(str(node)))
        parentelement.appendChild(textnode)
    else:
        # ignore
        pass


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
    dirpath, _ = os.path.split(filepath)
    if not os.path.exists(dirpath):
        os.makedirs(dirpath)
    filehandle = open(filepath, "w+")
    filehandle.write(content)
    filehandle.close()
    os.chmod(filepath, 0600)


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


