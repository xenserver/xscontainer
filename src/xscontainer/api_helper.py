from xscontainer import util
from xscontainer.util import log

import os
import tempfile
import threading
import XenAPI

XSCONTAINER_PRIVATE_SECRET_UUID = 'xscontainer-private-secret-uuid'
XSCONTAINER_PUBLIC_SECRET_UUID = 'xscontainer-public-secret-uuid'
XSCONTAINER_SSH_HOSTKEY = 'xscontainer-sshhostkey'
XSCONTAINER_USERNAME = 'xscontainer-username'

IDRSAFILENAME = '/opt/xensource/packages/files/xscontainer/xscontainer-idrsa'

NULLREF = 'OpaqueRef:NULL'

GLOBAL_XAPI_SESSION = None
GLOBAL_XAPI_SESSION_LOCK = threading.Lock()


def refresh_session_on_failure(func):
    """
    Decorator method for refreshing the local session object if an exception
    is raised during the API call.
    """
    def decorated(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception, exception:
            log.error("Caught exception '%s'. Retrying with new session."
                      % (str(exception)))
            reinit_global_xapi_session()
            # Return the func undecorated
            return func(*args, **kwargs)
    return decorated


class XenAPIClient(object):

    def __init__(self, session):
        self.session = session

    def get_session(self):
        return self.session

    def get_session_handle(self):
        return self.get_session().handle

    def get_all_vms(self):
        vm_refs = self.get_session().xenapi.VM.get_all()
        return [VM(self, vm_ref) for vm_ref in vm_refs]

    def get_all_vm_records(self):
        return self.get_session().xenapi.VM.get_all_records()

    @refresh_session_on_failure
    def api_call(self, object_name, method, *args):
        method_args = (self.get_session_handle(),) + args
        method_name = "%s.%s" % (object_name, method)
        res = getattr(self.get_session(), method_name)(*method_args)
        return XenAPI._parse_result(res)


class LocalXenAPIClient(XenAPIClient):

    """
    Localhost XenAPI client that uses a globally shared session.
    """

    def __init__(self):
        session = get_local_api_session()
        super(LocalXenAPIClient, self).__init__(session)

    def get_session(self):
        return get_local_api_session()

    @refresh_session_on_failure
    def api_call(self, object_name, method, *args):
        return super(LocalXenAPIClient, self).api_call(object_name, method,
                                                       *args)


class XenAPIObject(object):

    OBJECT = None
    ref = None
    uuid = None

    def __init__(self, client, ref=None, uuid=None):
        if not ref and not uuid:
            raise Exception("XenAPI object requires either a ref or a uuid.")

        self.client = client

        if uuid and not ref:
            ref = self.client.api_call(self.OBJECT, "get_by_uuid", uuid)

        self.ref = ref
        self.uuid = uuid

    def get_id(self):
        return self.ref

    def get_session(self):
        return self.client.get_session()

    def get_session_handle(self):
        return self.get_session().handle

    # @todo: for the case when a non-local global session is being used,
    # this decorator unnecessarily retries on exception.
    @refresh_session_on_failure
    def api_call(self, method, *args):
        method_args = (self.get_session_handle(), self.ref) + args
        method_name = "%s.%s" % (self.OBJECT, method)
        res = getattr(self.get_session(), method_name)(*method_args)
        return XenAPI._parse_result(res)

    def remove_from_other_config(self, key):
        return self.api_call("remove_from_other_config", key)

    def add_to_other_config(self, key, value):
        return self.api_call("add_to_other_config", key, value)


class Host(XenAPIObject):

    OBJECT = "Host"

    # Return VMs running on the host _not_ the pool
    def get_vms(self):
        return [vm for vm in self.client.get_all_vms() if vm.is_on_host(self)]


class VM(XenAPIObject):

    OBJECT = "VM"

    def get_uuid(self):
        if self.uuid is None:
            self.uuid = self.get_session().xenapi.VM.get_uuid(self.ref)
        return self.uuid

    def is_on_host(self, host):
        return host.ref == self.get_host().ref

    def get_host(self):
        host_ref = self.client.get_session(
        ).xenapi.VM.get_resident_on(self.ref)
        return Host(self.client, host_ref)

    def get_other_config(self):
        return self.client.get_session().xenapi.VM.get_other_config(self.ref)

    def update_other_config(self, key, value):
        # session.xenapi.VM.remove_from_other_config(vmref, name)
        # session.xenapi.VM.add_to_other_config(vmref, name, value)
        other_config = self.get_other_config()
        other_config[key] = value
        self.client.get_session().xenapi.VM.set_other_config(self.ref,
                                                             other_config)


def get_local_api_session():
    global GLOBAL_XAPI_SESSION
    # Prefer to use a global session object to keep all communication
    # with the host on the same ref.
    if GLOBAL_XAPI_SESSION is None:
        GLOBAL_XAPI_SESSION = init_local_api_session()

    return GLOBAL_XAPI_SESSION


def init_local_api_session():
    session = XenAPI.xapi_local()
    session.xenapi.login_with_password("root", "", "1.0", "xscontainer")
    return session


def reinit_global_xapi_session():
    global GLOBAL_XAPI_SESSION

    # Make threadsafe
    GLOBAL_XAPI_SESSION_LOCK.acquire()

    GLOBAL_XAPI_SESSION = init_local_api_session()

    GLOBAL_XAPI_SESSION_LOCK.release()
    log.info("The Global XAPI session has been updated.")

    return GLOBAL_XAPI_SESSION


def get_hi_mgmtnet_ref(session):
    networkrecords = session.xenapi.network.get_all_records()
    for networkref, networkrecord in networkrecords.iteritems():
        if networkrecord['bridge'] == 'xenapi':
            return networkref


def disable_gw_of_hi_mgmtnet_ref(session):
    networkref = get_hi_mgmtnet_ref(session)
    other_config = session.xenapi.network.get_other_config(networkref)
    other_config['ip_disable_gw'] = 'true'
    session.xenapi.network.set_other_config(networkref, other_config)


def get_hi_mgmtnet_device(session, vmuuid):
    vmrecord = get_vm_record_by_uuid(session, vmuuid)
    mgmtnet_ref = get_hi_mgmtnet_ref(session)
    for vmvifref in vmrecord['VIFs']:
        vifrecord = session.xenapi.VIF.get_record(vmvifref)
        if vifrecord['network'] == mgmtnet_ref:
            return vifrecord['device']


def get_hi_mgmtnet_ip(session, vmuuid):
    ipaddress = None
    vmrecord = get_vm_record_by_uuid(session, vmuuid)
    mgmtnet_ref = get_hi_mgmtnet_ref(session)
    networkrecord = session.xenapi.network.get_record(mgmtnet_ref)
    for vifref in networkrecord['assigned_ips']:
        for vmvifref in vmrecord['VIFs']:
            if vifref == vmvifref:
                ipaddress = networkrecord['assigned_ips'][vifref]
                return ipaddress


def get_vm_ips(session, vmuuid):
    vmref = get_vm_ref_by_uuid(session, vmuuid)
    guest_metrics = session.xenapi.VM.get_guest_metrics(vmref)
    if guest_metrics != NULLREF:
        ips = session.xenapi.VM_guest_metrics.get_networks(guest_metrics)
    else:
        # The VM is probably shut-down
        ips = {}
    return ips


def get_hi_preferene_on(session):
    pool = session.xenapi.pool.get_all()[0]
    other_config = session.xenapi.pool.get_other_config(pool)
    if ('xscontainer-use-hostinternalnetwork' in other_config and
        (other_config['xscontainer-use-hostinternalnetwork'].lower()
         in ['1', 'yes', 'true', 'on'])):
        return True
    # Return the default
    return False


def get_this_host_uuid():
    # ToDo: There must be a better way that also works with plugins?!?
    uuid = None
    filehandler = open("/etc/xensource-inventory", 'r')
    try:
        for line in filehandler.readlines():
            if line.startswith("INSTALLATION_UUID"):
                uuid = line.split("'")[1]
                break
    finally:
        filehandler.close()
    return uuid


def get_this_host_ref(session):
    host_uuid = get_this_host_uuid()
    host_ref = session.xenapi.host.get_by_uuid(host_uuid)
    return host_ref


def call_plugin(session, hostref, plugin, function, args):
    result = session.xenapi.host.call_plugin(hostref, plugin, function, args)
    return result


def get_vm_record_by_uuid(session, vmuuid):
    vmref = get_vm_ref_by_uuid(session, vmuuid)
    vmrecord = session.xenapi.VM.get_record(vmref)
    return vmrecord


def get_vm_ref_by_uuid(session, vmuuid):
    vmref = session.xenapi.VM.get_by_uuid(vmuuid)
    return vmref


def get_vm_records(session):
    vmrecords = session.xenapi.VM.get_all_records()
    return vmrecords


def _retry_device_exists(function, config, devicenumberfield):
    devicenumber = 0
    config[devicenumberfield] = str(devicenumber)
    while True:
        try:
            ref = function(config)
            return ref
        except XenAPI.Failure, failure:
            if (failure.details[0] != 'DEVICE_ALREADY_EXISTS' or
                    devicenumber > 20):
                raise failure
            devicenumber = devicenumber + 1
            config[devicenumberfield] = str(devicenumber)


def create_vif(session, network, vmref):
    devicenumber = 0
    vifconfig = {'device': str(devicenumber),
                 'network': network,
                 'VM': vmref,
                 'MAC': "",
                 'MTU': "1500",
                 "qos_algorithm_type": "",
                 "qos_algorithm_params": {},
                 "other_config": {}
                 }
    return _retry_device_exists(session.xenapi.VIF.create, vifconfig, 'device')


def create_vbd(session, vmref, vdiref, vbdmode, bootable,
               other_config_keys={}):
    vbdconf = {'VDI': vdiref,
               'VM': vmref,
               'userdevice': '1',
               'type': 'Disk',
               'mode': vbdmode,
               'bootable': bootable,
               'empty': False,
               'other_config': other_config_keys,
               'qos_algorithm_type': '',
               'qos_algorithm_params': {}, }
    return _retry_device_exists(session.xenapi.VBD.create, vbdconf,
                                'userdevice')


# ToDo: Ugly - this function may modify the file specified as filename
def import_disk(session, sruuid, filename, fileformat, namelabel,
                other_config_keys={}):
    log.info("import_disk file %s on sr %s" % (filename, sruuid))
    targetsr = session.xenapi.SR.get_by_uuid(sruuid)
    sizeinb = None
    if fileformat == "vhd":
        cmd = ['vhd-util', 'query', '-n', filename, '-v']
        sizeinmb = util.runlocal(cmd)[1]
        sizeinb = int(sizeinmb) * 1024 * 1024
    elif fileformat == "raw":
        sizeinb = os.path.getsize(filename)
        # Workaround: can't otherwise import disks that aren't aligned to 2MB
        newsizeinb = sizeinb + \
            ((2 * 1024 * 1024) - sizeinb % (2 * 1024 * 1024))
        if sizeinb < newsizeinb:
            log.info('Resizing raw disk from size %d to %d' %
                     (sizeinb, newsizeinb))
            filehandle = open(filename, "r+b")
            filehandle.seek(newsizeinb - 1)
            filehandle.write("\0")
            filehandle.close()
            sizeinb = os.path.getsize(filename)
    else:
        raise Exception('Invalid fileformat: %s ' % fileformat)
    log.info("Preparing vdi of size %d" % (sizeinb))
    vdiconf = {'SR': targetsr, 'virtual_size': str(sizeinb), 'type': 'system',
               'sharable': False, 'read_only': False, 'other_config': {},
               'name_label': namelabel}
    vdiref = session.xenapi.VDI.create(vdiconf)

    other_config = session.xenapi.VDI.get_other_config(vdiref)
    for key, value in other_config_keys.iteritems():
        other_config[key] = value
    session.xenapi.VDI.set_other_config(vdiref, other_config)

    vdiuuid = session.xenapi.VDI.get_record(vdiref)['uuid']
    cmd = ['curl', '-k', '--upload', filename,
           'https://localhost/import_raw_vdi?session_id=%s&vdi=%s&format=%s'
           % (session.handle, vdiuuid, fileformat)]
    util.runlocal(cmd)
    return vdiref


def export_disk(session, vdiuuid):
    log.info("export_disk vdi %s" % (vdiuuid))
    filename = tempfile.mkstemp(suffix='.raw')[1]
    cmd = ['curl', '-L', '-k', '-o', filename,
           'https://localhost/export_raw_vdi?session_id=%s&vdi=%s&format=raw'
           % (session.handle, vdiuuid)]
    util.runlocal(cmd)
    return filename


def get_default_sr(session):
    pool = session.xenapi.pool.get_all()[0]
    default_sr = session.xenapi.pool.get_default_SR(pool)
    return default_sr


def get_value_from_vm_other_config(session, vmuuid, name):
    vmref = get_vm_ref_by_uuid(session, vmuuid)
    other_config = session.xenapi.VM.get_other_config(vmref)
    if name in other_config:
        return other_config[name]
    else:
        return None


def update_vm_other_config(session, vmref, name, value):
    # session.xenapi.VM.remove_from_other_config(vmref, name)
    # session.xenapi.VM.add_to_other_config(vmref, name, value)
    other_config = session.xenapi.VM.get_other_config(vmref)
    other_config[name] = value
    session.xenapi.VM.set_other_config(vmref, other_config)


def get_idrsa_secret(session, secret_type):
    poolref = session.xenapi.pool.get_all()[0]
    other_config = session.xenapi.pool.get_other_config(poolref)
    if (XSCONTAINER_PRIVATE_SECRET_UUID not in other_config or
            XSCONTAINER_PUBLIC_SECRET_UUID not in other_config):
        set_idrsa_secret(session)
        other_config = session.xenapi.pool.get_other_config(poolref)
    secret_uuid = other_config[secret_type]
    secret_ref = session.xenapi.secret.get_by_uuid(secret_uuid)
    secret_record = session.xenapi.secret.get_record(secret_ref)
    return secret_record['value']


def get_idrsa_secret_private(session):
    return get_idrsa_secret(session, XSCONTAINER_PRIVATE_SECRET_UUID)


def get_idrsa_secret_public(session):
    return get_idrsa_secret(session, XSCONTAINER_PUBLIC_SECRET_UUID)


def get_idrsa_secret_public_keyonly(session):
    return get_idrsa_secret_public(session).split(' ')[1]


def set_idrsa_secret(session):
    log.info("set_idrsa_secret is generating a new secret")
    (privateidrsa, publicidrsa) = util.create_idrsa()
    private_secret_ref = session.xenapi.secret.create(
        {'value': '%s' % (privateidrsa)})
    public_secret_ref = session.xenapi.secret.create(
        {'value': '%s' % (publicidrsa)})
    private_secret_record = session.xenapi.secret.get_record(
        private_secret_ref)
    public_secret_record = session.xenapi.secret.get_record(public_secret_ref)
    pool_ref = session.xenapi.pool.get_all()[0]
    other_config = session.xenapi.pool.get_other_config(pool_ref)
    other_config[XSCONTAINER_PRIVATE_SECRET_UUID] = private_secret_record[
        'uuid']
    other_config[XSCONTAINER_PUBLIC_SECRET_UUID] = public_secret_record['uuid']
    session.xenapi.pool.set_other_config(pool_ref, other_config)


def get_suitable_vm_ip(session, vmuuid):
    ips = get_vm_ips(session, vmuuid)
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
        if util.test_connection(address, 22):
            return address
    raise util.XSContainerException(
        "No valid IP found for vmuuid %s" % (vmuuid))


def get_vm_xscontainer_username(session, vmuuid):
    username = get_value_from_vm_other_config(session, vmuuid,
                                              XSCONTAINER_USERNAME)
    if username is None:
        # assume CoreOs's "core" by default
        username = 'core'
    return username


def set_vm_xscontainer_username(session, vmuuid, newusername):
    vmref = get_vm_ref_by_uuid(session, vmuuid)
    update_vm_other_config(session, vmref, XSCONTAINER_USERNAME, newusername)


def send_message(session, vm_uuid, title, body):
    message_prio_warning = "3"
    message_type_vm = "VM"
    message_ref = session.xenapi.message.create(title, message_prio_warning,
                                                message_type_vm, vm_uuid, body)
    return message_ref


def destroy_message(session, message_ref):
    session.xenapi.message.destroy(message_ref)


def get_ssh_hostkey(session, vm_uuid):
    return get_value_from_vm_other_config(session, vm_uuid,
                                          XSCONTAINER_SSH_HOSTKEY)


def set_ssh_hostkey(session, vm_uuid, host_key):
    vm_ref = get_vm_ref_by_uuid(session, vm_uuid)
    update_vm_other_config(session, vm_ref, XSCONTAINER_SSH_HOSTKEY, host_key)


def get_host_ref_for_sr_uuid(session, sr_uuid):
    sr_ref = session.xenapi.SR.get_by_uuid(sr_uuid)
    return get_host_ref_for_sr_ref(session, sr_ref)


def get_host_ref_for_sr_ref(session, sr_ref):
    pbd_refs = session.xenapi.SR.get_PBDs(sr_ref)
    host_ref = None
    for pbd_ref in pbd_refs:
        pbd_record = session.xenapi.PBD.get_record(pbd_ref)
        if pbd_record['currently_attached']:
            host_ref = pbd_record['host']
            break
    return host_ref


def get_host_ref_for_vdi_uuid(session, vdi_uuid):
    vdi_ref = session.xenapi.VDI.get_by_uuid(vdi_uuid)
    vdi_record = session.xenapi.VDI.get_record(vdi_ref)
    return get_host_ref_for_sr_ref(session, vdi_record['SR'])


def get_host_ref_for_vm_uuid(session, vm_uuid):
    vm_record = get_vm_record_by_uuid(session, vm_uuid)
    host_ref = None
    if 'resident_on' in vm_record and vm_record['resident_on'] != NULLREF:
        host_ref = vm_record['resident_on']
    return host_ref
