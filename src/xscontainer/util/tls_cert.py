from xscontainer import util
from xscontainer.util import tls_secret

import os
import shutil
import socket
import sys
import tempfile


CERTIFICATE_DAYSTOBEVALID = 2 * 365
CERTIFICATE_FILES = ['server/ca.pem', 'server/server-cert.pem',
                     'server/server-key.pem', 'client/ca.pem',
                     'client/cert.pem', 'client/key.pem']


def _generate_ca(parent_path):
    util.runlocal(['openssl', 'genrsa',
                   '-out', os.path.join(parent_path, 'ca-key.pem'), '4096'])
    # ToDo: we may want to ask the user for his organisation?
    util.runlocal(['openssl', 'req', '-new', '-x509', '-sha256',
                   '-days', "%d" % (CERTIFICATE_DAYSTOBEVALID),
                   '-key', os.path.join(parent_path, 'ca-key.pem'),
                   '-out', os.path.join(parent_path, 'ca.pem'),
                   '-subj', '/O=%s.xscontainer/' % socket.gethostname()])


def _generate_client(parent_path):
    prefix = os.path.join(parent_path, "client")
    os.makedirs(prefix)
    util.runlocal(['openssl', 'genrsa',
                   '-out', os.path.join(prefix, 'key.pem'), '4096'])
    try:
        util.runlocal(['openssl', 'req', '-subj', '/CN=client',
                       '-new', '-key', os.path.join(prefix, 'key.pem'),
                       '-out', os.path.join(prefix, 'client.csr')])
        util.write_file(os.path.join(prefix, './extfile.cnf'),
                        'extendedKeyUsage = clientAuth')
        util.runlocal(['openssl', 'x509', '-req', '-sha256',
                       '-days', "%d" % (CERTIFICATE_DAYSTOBEVALID),
                       '-in', os.path.join(prefix, 'client.csr'),
                       '-CA', os.path.join(parent_path, 'ca.pem'),
                       '-CAkey', os.path.join(parent_path, 'ca-key.pem'),
                       '-CAcreateserial',
                       '-out', os.path.join(prefix, 'cert.pem'),
                       '-extfile', os.path.join(prefix, 'extfile.cnf')])
    finally:
        _delete_if_exists(prefix, ['extfile.cnf', 'client.csr'])
    shutil.copyfile(
        os.path.join(parent_path, 'ca.pem'), os.path.join(prefix, 'ca.pem'))


def _generate_server(parent_path, ips):
    prefix = os.path.join(parent_path, "server")
    os.makedirs(prefix)
    util.runlocal(['openssl', 'genrsa',
                   '-out', os.path.join(prefix, 'server-key.pem'), '4096'])
    # hostname is ignored as XS will connect using the IPs
    hostname = "_ignored_"
    util.runlocal(['openssl', 'req', '-subj', '/CN=%s' % (hostname),
                   '-days', "%d" % (CERTIFICATE_DAYSTOBEVALID),
                   '-sha256', '-new', '-key', os.path.join(
                       prefix, 'server-key.pem'),
                   '-out', os.path.join(prefix, 'server.csr')])
    ipstring = ""
    for ip in ips:
        ipstring = ipstring + "IP:" + ip + ","
    # remove trailing comma
    ipstring = ipstring[:-1]
    try:
        util.write_file(
            os.path.join(prefix, './extfile.cnf'),
            'subjectAltName = ' + (ipstring))
        util.runlocal(['openssl', 'x509', '-req', '-sha256',
                       '-in', os.path.join(prefix, 'server.csr'),
                       '-CA', os.path.join(parent_path, 'ca.pem'),
                       '-CAkey', os.path.join(parent_path, 'ca-key.pem'),
                       '-CAcreateserial',
                       '-out', os.path.join(prefix, 'server-cert.pem'),
                       '-extfile', os.path.join(prefix, 'extfile.cnf')])
    finally:
        _delete_if_exists(prefix, ['extfile.cnf', 'server.csr'])
        _delete_if_exists(parent_path, ['ca.srl'])
    shutil.copyfile(
        os.path.join(parent_path, 'ca.pem'), os.path.join(prefix, 'ca.pem'))


def _delete_if_exists(prefix, filenames):
    for filename in filenames:
        path = os.path.join(prefix, filename)
        if os.path.exists(path):
            os.remove(path)


def _wipe_ca(parent_path):
    _delete_if_exists(parent_path, ['ca.pem', 'ca-key.pem'])


def _wipe_certificates(parent_path):
    _delete_if_exists(parent_path, ['configure_tls.cmd'])
    _delete_if_exists(parent_path, CERTIFICATE_FILES)
    for folder in ['client', 'server']:
        path = os.path.join(parent_path, folder)
        if os.path.exists(path):
            os.rmdir(path)


def generate_certs_and_return_iso(session, vm_uuid, ips):
    tempdir = tempfile.mkdtemp()
    try:
        os.chmod(tempdir, 400)
        sys.stdout.write("Generating TLS certificates")
        sys.stdout.flush()
        try:
            _generate_ca(tempdir)
            sys.stdout.write(".")
            sys.stdout.flush()
            _generate_client(tempdir)
            sys.stdout.write(".")
            sys.stdout.flush()
            _generate_server(tempdir, ips)
            print(". Done")
        finally:
            # We don't need the CA anymore
            _wipe_ca(tempdir)
        path_ca_cert = os.path.join(tempdir, "client", "ca.pem")
        path_client_cert = os.path.join(tempdir, "client", "cert.pem")
        path_client_key = os.path.join(tempdir, "client", "key.pem")
        tls_secret.set_for_vm(
            session,
            vm_uuid,
            client_cert_content=util.read_file(path_client_cert),
            client_key_content=util.read_file(path_client_key),
            ca_cert_content=util.read_file(path_ca_cert))
        shutil.copy2(
            '/usr/lib/python2.7/site-packages/xscontainer/data/' +
            'configure_tls.cmd',
            os.path.join(tempdir, 'configure_tls.cmd'))
        targetiso = tempfile.mkstemp()[1]
        try:
            util.make_iso("Container TLS", tempdir, targetiso)
        except:
            os.remove(targetiso)
            raise
    finally:
        _wipe_certificates(tempdir)
        os.rmdir(tempdir)
    return targetiso
