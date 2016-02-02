from xscontainer import api_helper
from xscontainer import util
from xscontainer.util import log

import os
import XenAPI

XSCONTAINER_TLS_CLIENT_CERT = 'xscontainer-tls-client-cert'
XSCONTAINER_TLS_CLIENT_KEY = 'xscontainer-tls-client-key'
XSCONTAINER_TLS_CA_CERT = 'xscontainer-tls-ca-cert'
XSCONTAINER_TLS_KEYS = [XSCONTAINER_TLS_CLIENT_CERT,
                        XSCONTAINER_TLS_CLIENT_KEY,
                        XSCONTAINER_TLS_CA_CERT]

TEMP_FILE_PATH = '/tmp/xscontainer/tls/'


def remove_if_refcount_less_or_equal(session, tls_secret_uuid,
                                     refcount_threshold):
    """ removes TLS secrets if there is fewer VMs using a secret as specified
        in refcount_threshold """
    refcount = _get_refcount(session, tls_secret_uuid)
    if refcount > refcount_threshold:
        log.info("refcount for secret uuid %s is larger than threshold with %d"
                 % (tls_secret_uuid, refcount))
        # There's still more references than the threshold - keep
        return
    try:
        tls_secret_ref = session.xenapi.secret.get_by_uuid(tls_secret_uuid)
        session.xenapi.secret.destroy(tls_secret_ref)
        log.info("Deleted secret uuid %s with refcount %d"
                 % (tls_secret_uuid, refcount))
    except XenAPI.Failure:
        log.exception("Failed to delete secret uuid %s, moving on..."
                      % (tls_secret_uuid))


def _get_refcount(session, secret_uuid):
    """ Returns how many VMs use a certain secret_uuid """
    refcount = 0
    vm_records = api_helper.get_vm_records(session)
    for vm_record in vm_records.values():
        for keyname in XSCONTAINER_TLS_KEYS:
            if ((keyname in vm_record['other_config'] and
                 vm_record['other_config'][keyname] == secret_uuid)):
                refcount = refcount + 1
    return refcount


def set_for_vm(session, vm_uuid, client_cert_content,
               client_key_content, ca_cert_content):
    _destroy_for_vm(session, vm_uuid)
    log.info("set_vm_tls_secrets is updating certs and keys for %s" %
             (vm_uuid))
    content = {
        XSCONTAINER_TLS_CLIENT_CERT:
            api_helper.create_secret_return_uuid(session,
                                                 client_cert_content),
        XSCONTAINER_TLS_CLIENT_KEY:
            api_helper.create_secret_return_uuid(session,
                                                 client_key_content),
        XSCONTAINER_TLS_CA_CERT:
            api_helper.create_secret_return_uuid(session,
                                                 ca_cert_content),
    }
    api_helper.update_vm_other_config(session, vm_uuid, content)


def export_for_vm(session, vm_uuid):
    other_config = api_helper.get_vm_other_config(session, vm_uuid)
    secretdict = {}
    for key, value in other_config.items():
        if key in XSCONTAINER_TLS_KEYS:
            secret_uuid = value
            secret_ref = session.xenapi.secret.get_by_uuid(secret_uuid)
            secret_record = session.xenapi.secret.get_record(secret_ref)
            secretdict[key] = secret_record['value']
    temptlspaths = _get_temptlspaths(vm_uuid)
    if util.file_old_or_none_existent(temptlspaths['client_cert']):
        if not os.path.exists(temptlspaths['parent']):
            os.makedirs(temptlspaths['parent'])
        os.chmod(temptlspaths['parent'], 400)
        util.write_file(
            temptlspaths['client_cert'],
            secretdict[XSCONTAINER_TLS_CLIENT_CERT])
        util.write_file(
            temptlspaths['client_key'],
            secretdict[XSCONTAINER_TLS_CLIENT_KEY])
        util.write_file(
            temptlspaths['ca_cert'],
            secretdict[XSCONTAINER_TLS_CA_CERT])
    return temptlspaths


def _get_temptlspaths(vm_uuid):
    temptlsfolder = os.path.join(TEMP_FILE_PATH, vm_uuid)
    return {'parent': temptlsfolder,
            'client_cert': os.path.join(temptlsfolder,
                                        XSCONTAINER_TLS_CLIENT_CERT),
            'client_key': os.path.join(temptlsfolder,
                                       XSCONTAINER_TLS_CLIENT_KEY),
            'ca_cert': os.path.join(temptlsfolder,
                                    XSCONTAINER_TLS_CA_CERT)}


def _destroy_for_vm(session, vm_uuid):
    log.info("destroy_tls_secrets is wiping certs and keys for %s" % (vm_uuid))
    other_config = api_helper.get_vm_other_config(session, vm_uuid)
    for key in XSCONTAINER_TLS_KEYS:
        if key in other_config:
            tls_secret_uuid = other_config[key]
            # remove if there is no VMs other than this one who use the secret
            remove_if_refcount_less_or_equal(session, tls_secret_uuid, 1)
    temptlspaths = _get_temptlspaths(vm_uuid)
    for path in temptlspaths:
        if os.path.exists(path):
            if os.path.isdir(path):
                os.rmdir(path)
            else:
                os.remove(path)
