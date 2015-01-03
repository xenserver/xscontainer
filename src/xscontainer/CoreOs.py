import xml.dom.minidom
import os
import random
import re
import tempfile

import ApiHelper
import Util

CLOUDCONFIG = """#cloud-config

hostname: %XSVMTOHOST%
ssh_authorized_keys:
  # - ssh-rsa <Your Key>
  - ssh-rsa %XSRSAPUB%
coreos:
  units:
    - name: etcd.service
      command: start
    - name: fleet.service
      command: start
    - name: 00-eth%XSHIN%.network
      runtime: true
      content: |
        [Match]
        Name=eth%XSHIN%

        [Network]
        DHCP=yes

        [DHCP]
        UseRoutes=false
  etcd:
    name: %XSVMTOHOST%
    # generate a new token for each unique cluster at https://discovery.etcd.io/new
    # discovery: https://discovery.etcd.io/<token>
write_files:
  - path: /etc/sysctl.d/10-disable-ipv6.conf
    permissions: 0644
    owner: root
    content: |
      net.ipv6.conf.eth0.disable_ipv6 = 1
"""


def remove_disks_from_vm_provisioning(session, vm_ref):
    """Re-write the xml for provisioning disks to set a SR"""
    other_config = session.xenapi.VM.get_other_config(vm_ref)
    del other_config['disks']
    session.xenapi.VM.set_other_config(vm_ref, other_config)

# ToDo: Simplify this function
# Todo: update template name label


def install_vm(session, urlvhdbz2, sruuid,
               vmname='CoreOs-%d' % (random.randint(0, 1000)),
               templatename='CoreOS (experimental)'):
    atempfile = tempfile.mkstemp(suffix='.vhd.bz2')[1]
    atempfileunpacked = atempfile.replace('.bz2', '')
    # ToDo: pipe the file, so it never actually touches Dom0
    cmd = ['curl', '-o', atempfile, urlvhdbz2]
    Util.runlocal(cmd)
    cmd = ['bzip2', '-d', atempfile]
    Util.runlocal(cmd)
    vdiref = ApiHelper.import_disk(session, sruuid, atempfileunpacked, 'vhd',
                                   'Disk')
    os.remove(atempfileunpacked)
    templateref = session.xenapi.VM.get_by_name_label(templatename)[0]
    vmref = session.xenapi.VM.clone(templateref, vmname)
    vmuuid = session.xenapi.VM.get_record(vmref)['uuid']
    remove_disks_from_vm_provisioning(session, vmref)
    session.xenapi.VM.provision(vmref)
    ApiHelper.create_vbd(session, vmref, vdiref, 'rw', True)
    # Setup networking on the lowest pif
    pifs = session.xenapi.PIF.get_all_records()
    lowest = None
    for pifref in pifs.keys():
        if ((lowest is None)
                or (pifs[pifref]['device'] < pifs[lowest]['device'])):
            lowest = pifref
    if lowest:
        networkref = session.xenapi.PIF.get_network(lowest)
        ApiHelper.create_vif(session, networkref, vmref)
    return vmuuid


def prepare_vm_for_config_drive(session, vmref, vmuuid):
    # Setup host internal network
    ApiHelper.disable_gateway_of_hi_mgmtnet_ref(session)
    mgmtnet_device = ApiHelper.get_hi_mgmtnet_device(session, vmuuid)
    if not mgmtnet_device:
        ApiHelper.create_vif(session,
                             ApiHelper.get_hi_mgmtnet_ref(session), vmref)


def customize_userdata(session, userdata, vmuuid):
    vmname = ApiHelper.get_vm_record_by_uuid(session, vmuuid)['name_label']
    vmname = re.sub(r'[\W_]+', '', vmname).lower()
    userdata = userdata.replace('%XSVMTOHOST%', vmname)
    userdata = userdata.replace(
        '%XSRSAPUB%', ApiHelper.get_idrsa_secret_public(session))
    mgmtnet_device = ApiHelper.get_hi_mgmtnet_device(session, vmuuid)
    userdata = userdata.replace('%XSHIN%', mgmtnet_device)
    return userdata


def workaround_dependencies():
    # ToDo: Install rpm with hotfix/supp-pack
    cmd = ['yum', '--disablerepo', 'citrix',
           '--enablerepo', 'base', '-y', 'install', 'mkisofs']
    Util.runlocal(cmd)
    # ToDo: create spec file instead
    cmd = ['chkconfig', '--add', 'xscontainer']
    Util.runlocal(cmd)
    cmd = ['service', 'xscontainer', 'restart']
    Util.runlocal(cmd, canfail=True)


def create_config_drive_iso(session, userdata, vmuuid):
    workaround_dependencies()
    tempisodir = tempfile.mkdtemp()
    tempisofile = tempfile.mkstemp()[1]
    openstackfolder = os.path.join(tempisodir, 'openstack')
    latestfolder = os.path.join(openstackfolder, 'latest')
    os.makedirs(latestfolder)
    userdatafile = os.path.join(latestfolder, 'user_data')
    userdata = customize_userdata(session, userdata, vmuuid)
    Util.write_file(userdatafile, userdata)
    cmd = ['mkisofs', '-R', '-V', 'config-2', '-o', tempisofile, tempisodir]
    Util.runlocal(cmd)
    os.remove(userdatafile)
    os.rmdir(latestfolder)
    os.rmdir(openstackfolder)
    os.rmdir(tempisodir)
    return tempisofile


def remove_config_drive(session, vmrecord, configdisk_namelabel):
    for vbd in vmrecord['VBDs']:
        vbdrecord = session.xenapi.VBD.get_record(vbd)
        vdirecord = session.xenapi.VDI.get_record(vbdrecord['VDI'])
        if vdirecord['name_label'] == configdisk_namelabel:
            if vbdrecord['currently_attached']:
                session.xenapi.VBD.unplug(vbd)
            session.xenapi.VBD.destroy(vbd)
            session.xenapi.VDI.destroy(vbdrecord['VDI'])


def create_config_drive(session, vmuuid, sruuid, userdata):
    vmref = session.xenapi.VM.get_by_uuid(vmuuid)
    vmrecord = session.xenapi.VM.get_record(vmref)
    prepare_vm_for_config_drive(session, vmref, vmuuid)
    isofile = create_config_drive_iso(session, userdata, vmuuid)
    configdisk_namelabel = 'Automatic Config Drive'
    vdiref = ApiHelper.import_disk(session, sruuid, isofile, 'raw',
                                   configdisk_namelabel)
    os.remove(isofile)
    remove_config_drive(session, vmrecord, configdisk_namelabel)
    vbdref = ApiHelper.create_vbd(session, vmref, vdiref, 'ro', False)
    if vmrecord['power_state'] == 'Running':
        session.xenapi.VBD.plug(vbdref)
    vdirecord = session.xenapi.VDI.get_record(vdiref)
    vbdrecord = session.xenapi.VBD.get_record(vbdref)
    return vdirecord['uuid']


def get_config_drive_configuration(session, vdiuuid):
    filename = ApiHelper.export_disk(session, vdiuuid)
    tempdir = tempfile.mkdtemp()
    # ToDo: is this always safe?
    cmd = ['mount', '-o', 'loop', '-t', 'iso9660', filename, tempdir]
    Util.runlocal(cmd)
    userdatapath = os.path.join(tempdir, 'openstack', 'latest', 'user_data')
    content = Util.read_file(userdatapath)
    cmd = ['umount', tempdir]
    Util.runlocal(cmd)
    os.rmdir(tempdir)
    os.remove(filename)
    return content
