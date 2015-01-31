import os
import tempfile
import time
import xscontainer.util as util
from xscontainer.util import log
import XenAPI

XSCONTAINER_SECRET_UUID = 'xscontainer-secret-uuid'
XSCONTAINER_SECRET_SEPARATOR = '<xscontainer-secret-separator>'

IDRSAFILENAME = '/tmp/xscontainer-idrsa'

NULLREF = 'OpaqueRef:NULL'


class XenAPIClient(object):

    def __init__(self):
        self.session = get_local_api_session()

    def get_session(self):
        return self.session

    def get_session_handle(self):
        return self.get_session().handle

    def get_all_vms(self):
        vm_refs = self.session.xenapi.VM.get_all()
        return [VM(self, vm_ref) for vm_ref in vm_refs]

    def get_all_vm_records(self):
        return self.session.xenapi.VM.get_all_records()

    def _api_call(self, object_name, method, *args):
        method_args = (self.get_session_handle(),) + args
        method_name = "%s.%s" % (object_name, method)
        res = getattr(self.get_session(), method_name)(*method_args)
        return XenAPI._parse_result(res)

    def add_to_other_config(self, object_name, ref, key, value):
        method = "%s.add_to_other_config" % object_name
        return self._api_call(object_name, "add_to_other_config", ref, key, value)

class XenAPIObject(object):

    OBJECT = None

    def __init__(self, client, ref=None, uuid=None):
        if not ref and not uuid:
            raise Exception("XenAPI object requires either a ref or a uuid.")

        self.client = client

        if uuid and not ref:
            ref = self.client._api_call(self.OBJECT, "get_by_uuid", uuid)

        self.ref = ref
        self.uuid = uuid

    def get_id(self):
        return self.ref

    def get_session(self):
        return self.client.get_session()

    def get_session_handle(self):
        return self.get_session().handle

    def get_record(self):
        return self.rec

    def _api_call(self, method, *args):
        method_args = (self.get_session_handle(), self.ref) + args
        method_name = "%s.%s" % (self.OBJECT, method)
        res = getattr(self.get_session(), method_name)(*method_args)
        return XenAPI._parse_result(res)

    def remove_from_other_config(self, key):
        return self._api_call("remove_from_other_config", key)

    def add_to_other_config(self, key, value):
        return self._api_call("add_to_other_config", key, value)

class Host(XenAPIObject):

    OBJECT = "Host"

    # Return VMs running on the host _not_ the pool
    def get_vms(self):
        return [vm for vm in self.client.get_all_vms() if vm.is_on_host(self)]

class VM(XenAPIObject):

    OBJECT = "VM"

    def get_uuid(self):
        return self.get_session().xenapi.VM.get_uuid(self.ref)

    def is_on_host(self, host):
        return host.ref == self.get_host().ref

    def get_host(self):
        host_ref = self.client.session.xenapi.VM.get_resident_on(self.ref)
        return Host(self.client, host_ref)

    def get_other_config(self):
        return self.client.session.xenapi.VM.get_other_config(self.ref)


def get_local_api_session():
    session = XenAPI.xapi_local()
    session.xenapi.login_with_password('root', '', '1.0', 'xscontainer')
    return session


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
    if ('xscontainer-use-hostinternalnetwork' in other_config
        and (other_config['xscontainer-use-hostinternalnetwork'].lower()
             in ['1', 'yes', 'true', 'on'])):
        return True
    # Return the default
    return False


def get_this_host_ref(session):
    host_ref = session.xenapi.session.get_this_host(session.handle)
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
            if (failure.details[0] != 'DEVICE_ALREADY_EXISTS'
                    or devicenumber > 20):
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


def create_vbd(session, vmref, vdiref, vbdmode, bootable):
    vbdconf = {'VDI': vdiref,
               'VM': vmref,
               'userdevice': '1',
               'type': 'Disk',
               'mode': vbdmode,
               'bootable': bootable,
               'empty': False,
               'other_config': {},
               'qos_algorithm_type': '',
               'qos_algorithm_params': {}, }
    return _retry_device_exists(session.xenapi.VBD.create, vbdconf,
                                'userdevice')


# ToDo: Ugly - this function may modify the file specified as filename
def import_disk(session, sruuid, filename, fileformat, namelabel):
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
    vdiuuid = session.xenapi.VDI.get_record(vdiref)['uuid']
    cmd = ['curl', '-k', '--upload', filename,
           'https://localhost/import_raw_vdi?session_id=%s&vdi=%s&format=%s'
           % (session.handle, vdiuuid, fileformat)]
    util.runlocal(cmd)
    return vdiref


def export_disk(session, vdiuuid):
    filename = tempfile.mkstemp(suffix='.raw')[1]
    cmd = ['curl', '-k', '-o', filename,
           'https://localhost/export_raw_vdi?session_id=%s&vdi=%s&format=raw'
           % (session.handle, vdiuuid)]
    util.runlocal(cmd)
    return filename


def get_default_sr(session):
    pool = session.xenapi.pool.get_all()[0]
    default_sr = session.xenapi.pool.get_default_SR(pool)
    return default_sr


def update_vm_other_config(session, vmref, name, value):
    #session.xenapi.VM.remove_from_other_config(vmref, name)
    #session.xenapi.VM.add_to_other_config(vmref, name, value)
    other_config = session.xenapi.VM.get_other_config(vmref)
    other_config[name] = value
    session.xenapi.VM.set_other_config(vmref, other_config)


def get_value_from_vm_other_config(session, vmuuid, name):
    vmref = get_vm_ref_by_uuid(session, vmuuid)
    other_config = session.xenapi.VM.get_other_config(vmref)
    if name in other_config:
        return other_config[name]
    else:
        return None


def get_idrsa_secret(session):
    poolref = session.xenapi.pool.get_all()[0]
    other_config = session.xenapi.pool.get_other_config(poolref)
    if XSCONTAINER_SECRET_UUID not in other_config:
        set_idrsa_secret(session)
        other_config = session.xenapi.pool.get_other_config(poolref)
    secretuuid = other_config[XSCONTAINER_SECRET_UUID]
    secretref = session.xenapi.secret.get_by_uuid(secretuuid)
    secretrecord = session.xenapi.secret.get_record(secretref)
    return secretrecord['value'].split(XSCONTAINER_SECRET_SEPARATOR)


def get_idrsa_secret_private(session):
    return get_idrsa_secret(session)[0].strip()


def get_idrsa_secret_public(session):
    return get_idrsa_secret(session)[1].strip()

def get_idrsa_secret_public_keyonly(session):
    return get_idrsa_secret_public(session).split(' ')[1]


def set_idrsa_secret(session):
    (privateidrsa, publicidrsa) = util.create_idrsa()
    secretref = session.xenapi.secret.create(
        {'value': '%s%s%s'
                  % (privateidrsa, XSCONTAINER_SECRET_SEPARATOR, publicidrsa)})
    secretrecord = session.xenapi.secret.get_record(secretref)
    poolref = session.xenapi.pool.get_all()[0]
    other_config = session.xenapi.pool.get_other_config(poolref)
    other_config[XSCONTAINER_SECRET_UUID] = secretrecord['uuid']
    session.xenapi.pool.set_other_config(poolref, other_config)


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


def ensure_idrsa(session):
    neednewfile = False
    if os.path.exists(IDRSAFILENAME):
        mtime = os.path.getmtime(IDRSAFILENAME)
        if time.time() - mtime > 60:
            neednewfile = True
    else:
        neednewfile = True
    if neednewfile:
        util.write_file(IDRSAFILENAME, get_idrsa_secret_private(session))


def get_vm_xscontainer_username(session, vmuuid):
    username = get_value_from_vm_other_config(session, vmuuid,
                                              'xscontainer_username')
    if username == None:
        username = 'core'
    return username

def set_vm_xscontainer_username(session, vmuuid, newusername):
    vmref = get_vm_ref_by_uuid(session, vmuuid)
    update_vm_other_config(session, vmref, 'xscontainer_username', newusername)


def prepare_ssh_cmd(session, vmuuid, cmd):
    username = get_vm_xscontainer_username(session, vmuuid)
    host = get_suitable_vm_ip(session, vmuuid)
    ensure_idrsa(session)
    complete_cmd = ['ssh', '-o', 'UserKnownHostsFile=/dev/null',
                    '-o', 'StrictHostKeyChecking=no',
                    '-o', 'PasswordAuthentication=no',
                    '-o', 'LogLevel=quiet',
                    '-o', 'ConnectTimeout=10',
                    '-i', IDRSAFILENAME, '%s@%s' % (username, host)] + cmd
    return complete_cmd


def execute_ssh(session, vmuuid, cmd):
    complete_cmd = prepare_ssh_cmd(session, vmuuid, cmd)
    stdout = util.runlocal(complete_cmd)[1]
    return str(stdout)
