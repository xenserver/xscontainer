from xscontainer import api_helper
from xscontainer import util
from xscontainer.util import log
from xscontainer.docker_monitor import api as docker_monitor_api

import distutils.version
import glob
import os
import random
import re
import shutil
import tempfile


CLOUD_CONFIG_OVERRIDE_PATH = (
    "/opt/xensource/packages/files/xscontainer/cloud-config.template")
XS_TOOLS_ISO_PATH = '/opt/xensource/packages/iso/xs-tools-*.iso'
OTHER_CONFIG_CONFIG_DRIVE_KEY = "config-drive"


def remove_disks_in_vm_provisioning(session, vm_ref):
    """Re-write the xml for provisioning disks to set a SR"""
    other_config = session.xenapi.VM.get_other_config(vm_ref)
    del other_config['disks']
    session.xenapi.VM.set_other_config(vm_ref, other_config)


def install_vm(session, urlvhdbz2, sruuid,
               vmname='CoreOs-%d' % (random.randint(0, 1000)),
               templatename='CoreOS'):
    # devmode only
    log.info("install_vm from url %s to sr %s" %(urlvhdbz2, sruuid))
    atempfile = tempfile.mkstemp(suffix='.vhd.bz2')[1]
    atempfileunpacked = atempfile.replace('.bz2', '')
    # @todo: pipe instead, so the file never actually touches Dom0
    cmd = ['curl', '-o', atempfile, urlvhdbz2]
    util.runlocal(cmd)
    cmd = ['bzip2', '-d', atempfile]
    util.runlocal(cmd)
    vdiref = api_helper.import_disk(session, sruuid, atempfileunpacked, 'vhd',
                                    'Disk')
    os.remove(atempfileunpacked)
    templateref = session.xenapi.VM.get_by_name_label(templatename)[0]
    vmref = session.xenapi.VM.clone(templateref, vmname)
    vmuuid = session.xenapi.VM.get_record(vmref)['uuid']
    log.info("install_vm created vm %s" %(vmuuid))
    remove_disks_in_vm_provisioning(session, vmref)
    session.xenapi.VM.provision(vmref)
    api_helper.create_vbd(session, vmref, vdiref, 'rw', True)
    setup_network_on_lowest_pif(session, vmref)
    return vmuuid


def setup_network_on_lowest_pif(session, vmref):
    # devmode only
    pifs = session.xenapi.PIF.get_all_records()
    lowest = None
    for pifref in pifs.keys():
        if ((lowest is None)
                or (pifs[pifref]['device'] < pifs[lowest]['device'])):
            lowest = pifref
    if lowest:
        networkref = session.xenapi.PIF.get_network(lowest)
        api_helper.create_vif(session, networkref, vmref)


def prepare_vm_for_config_drive(session, vmref, vmuuid):
    if api_helper.get_hi_preferene_on(session):
        # Setup host internal network
        api_helper.disable_gw_of_hi_mgmtnet_ref(session)
        mgmtnet_device = api_helper.get_hi_mgmtnet_device(session, vmuuid)
        if not mgmtnet_device:
            api_helper.create_vif(session,
                                  api_helper.get_hi_mgmtnet_ref(session), vmref)


def filterxshinexists(text):
    try:
        xshinexists = text.index('%XSHINEXISTS%')
        endxshinexists = text.index('%ENDXSHINEXISTS%')
        if xshinexists and endxshinexists:
            text = text[:xshinexists] + text[endxshinexists + 16:]
    except ValueError:
        pass
    return text


def customize_userdata(session, userdata, vmuuid):
    vmname = api_helper.get_vm_record_by_uuid(session, vmuuid)['name_label']
    vmname = re.sub(r'[\W_]+', '', vmname).lower()
    userdata = userdata.replace('%XSVMTOHOST%', vmname)
    userdata = userdata.replace(
        '%XSRSAPUB%', api_helper.get_idrsa_secret_public_keyonly(session))
    mgmtnet_device = api_helper.get_hi_mgmtnet_device(session, vmuuid)
    if mgmtnet_device:
        userdata = userdata.replace('%XSHIN%', mgmtnet_device)
    else:
        userdata = filterxshinexists(userdata)
    return userdata


def load_cloud_config_template(template_path=None):
    if template_path:
        # Do nothing, specifying the path takes precedence.
        pass
    elif os.path.exists(CLOUD_CONFIG_OVERRIDE_PATH):
        # Use the override file
        template_path = CLOUD_CONFIG_OVERRIDE_PATH
    else:
        # Use the inbuilt default template
        this_dir, _ = os.path.split(__file__)
        template_path = os.path.join(this_dir, "data", "cloud-config.template")

    log.info("load_cloud_config_template from %s" % (template_path))

    fh = open(template_path)
    template_data = fh.read()
    fh.close()

    # Append template location to make it clear where it was loaded from.
    template_data = ("%s\n\n# Template loaded from %s"
                     % (template_data, template_path))

    return template_data


def get_config_drive_default(session):
    userdata = load_cloud_config_template()
    if not api_helper.get_hi_preferene_on(session):
        userdata = filterxshinexists(userdata)
    return userdata


def create_config_drive_iso(session, userdata, vmuuid):
    log.info("create_config_drive_iso for vm %s" %(vmuuid))
    tempisodir = tempfile.mkdtemp()
    tempisofile = tempfile.mkstemp()[1]
    openstackfolder = os.path.join(tempisodir, 'openstack')
    latestfolder = os.path.join(openstackfolder, 'latest')
    os.makedirs(latestfolder)
    userdatafile = os.path.join(latestfolder, 'user_data')
    userdata = customize_userdata(session, userdata, vmuuid)
    util.write_file(userdatafile, userdata)
    log.debug("Userdata: %s" % (userdata))
    # Also add the Linux guest agent
    temptoolsisodir = tempfile.mkdtemp()
    # First find the latest tools ISO
    tools_iso_paths = glob.glob(XS_TOOLS_ISO_PATH)
    if len(tools_iso_paths) < 1:
        raise util.XSContainerException("Can't locate XS tools in %s."
                                        % (XS_TOOLS_ISO_PATH))
    tools_iso_paths.sort(key=distutils.version.LooseVersion)
    tools_iso_path = tools_iso_paths[-1]
    # Then copy it
    cmd = ['mount', '-o', 'loop',
           tools_iso_path,  temptoolsisodir]
    util.runlocal(cmd)
    agentpath = os.path.join(tempisodir, 'agent')
    os.makedirs(agentpath)
    agentfiles = ['xe-daemon', 'xe-linux-distribution',
                  'xe-linux-distribution.service', 'xe-update-guest-attrs',
                  'xen-vcpu-hotplug.rules', 'install.sh',
                  'versions.deb', 'versions.rpm']
    for filename in agentfiles:
        path = os.path.join(temptoolsisodir, 'Linux', filename)
        shutil.copy(path, agentpath)
    cmd = ['umount', temptoolsisodir]
    util.runlocal(cmd)
    os.rmdir(temptoolsisodir)
    # Finally wrap up the iso
    cmd = ['mkisofs', '-R', '-V', 'config-2', '-o', tempisofile, tempisodir]
    util.runlocal(cmd)
    # Tidy
    os.remove(userdatafile)
    os.rmdir(latestfolder)
    os.rmdir(openstackfolder)
    for filename in agentfiles:
        path = os.path.join(agentpath, filename)
        os.remove(path)
    os.rmdir(agentpath)
    os.rmdir(tempisodir)
    return tempisofile


def remove_config_drive(session, vmrecord, configdisk_namelabel):
    for vbd in vmrecord['VBDs']:
        vbdrecord = session.xenapi.VBD.get_record(vbd)
        vdirecord = None
        if vbdrecord['VDI'] != api_helper.NULLREF:
            vdirecord = session.xenapi.VDI.get_record(vbdrecord['VDI'])
            if OTHER_CONFIG_CONFIG_DRIVE_KEY in vdirecord['other_config']:
                log.info("remove_config_drive will destroy vdi %s"
                         %(vdirecord['uuid']))
                if vbdrecord['currently_attached']:
                    session.xenapi.VBD.unplug(vbd)
                session.xenapi.VBD.destroy(vbd)
                session.xenapi.VDI.destroy(vbdrecord['VDI'])


def create_config_drive(session, vmuuid, sruuid, userdata):
    log.info("create_config_drive for vm %s on sr %s" %(vmuuid, sruuid))
    vmref = session.xenapi.VM.get_by_uuid(vmuuid)
    vmrecord = session.xenapi.VM.get_record(vmref)
    prepare_vm_for_config_drive(session, vmref, vmuuid)
    isofile = create_config_drive_iso(session, userdata, vmuuid)
    configdisk_namelabel = 'Automatic Config Drive'
    other_config_keys = {OTHER_CONFIG_CONFIG_DRIVE_KEY: 'True'}
    vdiref = api_helper.import_disk(session, sruuid, isofile, 'raw',
                                    configdisk_namelabel,
                                    other_config_keys=other_config_keys)
    os.remove(isofile)
    remove_config_drive(session, vmrecord, configdisk_namelabel)
    vbdref = api_helper.create_vbd(session, vmref, vdiref, 'ro', False)
    if vmrecord['power_state'] == 'Running':
        session.xenapi.VBD.plug(vbdref)
    if re.search("\n\s*- ssh-rsa %XSRSAPUB%", userdata):
        # if %XSRSAPUB% isn't commented out, automatically mark the VM
        # as monitorable.
        docker_monitor_api.mark_monitorable_vm(vmuuid, session)
    vdirecord = session.xenapi.VDI.get_record(vdiref)
    return vdirecord['uuid']


def get_config_drive_configuration(session, vdiuuid):
    log.info("get_config_drive_configuration from vdi %s" % (vdiuuid))
    filename = api_helper.export_disk(session, vdiuuid)
    tempdir = tempfile.mkdtemp()
    cmd = ['mount', '-o', 'loop', '-t', 'iso9660', filename, tempdir]
    util.runlocal(cmd)
    userdatapath = os.path.join(tempdir, 'openstack', 'latest', 'user_data')
    content = util.read_file(userdatapath)
    cmd = ['umount', tempdir]
    util.runlocal(cmd)
    os.rmdir(tempdir)
    os.remove(filename)
    return content
