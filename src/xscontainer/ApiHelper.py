import os
import tempfile
import Util
import XenAPI


def get_local_api_session():
    session = XenAPI.xapi_local()
    session.xenapi.login_with_password('root', '')
    return session


def get_hi_mgmtnet_ref(session):
    networkrecords = session.xenapi.network.get_all_records()
    for networkref, networkrecord in networkrecords.iteritems():
        if networkrecord['bridge'] == 'xenapi':
            return networkref


def disable_gateway_of_hi_mgmtnet_ref(session):
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


def get_this_host_uuid():
    # ToDo: There must be a better way?!?
    uuid = None
    filehandler = open("/etc/xensource-inventory", 'r')
    for line in filehandler.readlines():
        if line.startswith("INSTALLATION_UUID"):
            uuid = line.split("'")[1]
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
            if failure.details[0] != 'DEVICE_ALREADY_EXISTS' or devicenumber > 20:
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
    return _retry_device_exists(session.xenapi.VBD.create, vbdconf, 'userdevice')


# ToDo: Ugly - this function may modify the file specified as filename
def import_disk(session, sruuid, filename, fileformat, namelabel):
    targetsr = session.xenapi.SR.get_by_uuid(sruuid)
    sizeinb = None
    if fileformat == "vhd":
        cmd = ['vhd-util', 'query', '-n', filename, '-v']
        sizeinmb = Util.runlocal(cmd)[1]
        sizeinb = int(sizeinmb) * 1024 * 1024
    elif fileformat == "raw":
        sizeinb = os.path.getsize(filename)
        # Workaround: can't otherwise import disks that aren't aligned to 2MB
        newsizeinb = sizeinb + \
            ((2 * 1024 * 1024) - sizeinb % (2 * 1024 * 1024))
        if sizeinb < newsizeinb:
            Util.log('Resizing raw disk from size %d to %d' %
                     (sizeinb, newsizeinb))
            filehandle = open(filename, "r+b")
            filehandle.seek(newsizeinb - 1)
            filehandle.write("\0")
            filehandle.close()
            sizeinb = os.path.getsize(filename)
    else:
        raise Exception('Invalid fileformat: %s ' % fileformat)
    Util.log("Preparing vdi of size %d" % (sizeinb))
    vdiconf = {'SR': targetsr, 'virtual_size': str(sizeinb), 'type': 'system',
               'sharable': False, 'read_only': False, 'other_config': {},
               'name_label': namelabel}
    vdiref = session.xenapi.VDI.create(vdiconf)
    vdiuuid = session.xenapi.VDI.get_record(vdiref)['uuid']
    cmd = ['curl', '-k', '--upload', filename,
           'https://localhost/import_raw_vdi?session_id=%s&vdi=%s&format=%s'
           % (session._session, vdiuuid, fileformat)]
    Util.runlocal(cmd)
    return vdiref


def export_disk(session, vdiuuid):
    filename = tempfile.mkstemp(suffix='.raw')[1]
    cmd = ['curl', '-k', '-o', filename,
           'https://localhost/export_raw_vdi?session_id=%s&vdi=%s&format=raw'
           % (session._session, vdiuuid)]
    Util.runlocal(cmd)
    return filename


def get_default_sr(session):
    pool = session.xenapi.pool.get_all()[0]
    default_sr = session.xenapi.pool.get_default_SR(pool)
    return default_sr


def update_vm_other_config(session, vmref, name, value):
    session.xenapi.VM.remove_from_other_config(vmref, name)
    session.xenapi.VM.add_to_other_config(vmref, name, value)


def get_idrsa_secret(session):
    poolref = session.xenapi.pool.get_all()[0]
    other_config = session.xenapi.pool.get_other_config(poolref)
    if 'xscontainersecretuuid' not in other_config:
        set_idrsa_secret(session)
        other_config = session.xenapi.pool.get_other_config(poolref)
    secretuuid = other_config['xscontainersecretuuid']
    secretref = session.xenapi.secret.get_by_uuid(secretuuid)
    secretrecord = session.xenapi.secret.get_record(secretref)
    return secretrecord['value'].split('<seperator>')


def get_idrsa_secret_private(session):
    return get_idrsa_secret(session)[0]


def get_idrsa_secret_public(session):
    return get_idrsa_secret(session)[1].split(' ')[1]


def set_idrsa_secret(session):
    (privateidrsa, publicidrsa) = Util.create_idrsa()
    secretref = session.xenapi.secret.create(
        {'value': '%s<seperator>%s' % (privateidrsa, publicidrsa)})
    secretrecord = session.xenapi.secret.get_record(secretref)
    poolref = session.xenapi.pool.get_all()[0]
    other_config = session.xenapi.pool.get_other_config(poolref)
    other_config['xscontainersecretuuid'] = secretrecord['uuid']
    session.xenapi.pool.set_other_config(poolref, other_config)
    #session.xenapi.pool.add_to_other_config(poolref, 'xscontainersecretuuid', secretrecord['uuid'])
