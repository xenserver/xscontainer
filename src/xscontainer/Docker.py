import ApiHelper
import Log

import Util
import time
import simplejson
import XenAPI

MONITORINTERVALLINS = 20


def _execute_cmd_on_vm(session, vmuuid, cmd):
    host = Util.get_suitable_vm_ip(session, vmuuid)
    result = Util.execute_ssh(session, host, 'core', cmd)
    return result


def _api_execute(session, vmuuid, request_type, request):
    # ToDo: Must really not pipe (!!!)
    cmd = ['echo -e "%s %s HTTP/1.1\r\n"' % (request_type, request) +
           '| ncat -U /var/run/docker.sock']
    stdout = _execute_cmd_on_vm(session, vmuuid, cmd)
    (header, body) = stdout.split("\r\n\r\n", 2)
    # ToDo: Should use re
    headersplits = header.split('\r\n', 2)[0].split(' ')
    #protocol = headersplits[0]
    statuscode = headersplits[1]
    if statuscode[0] != '2':
        status = ' '.join(headersplits[2:])
        raise Util.XSContainerException("Request %s led to bad status %s %s"
                                        % (cmd, statuscode, status))
    return body


def _api_get_json_on_vm(session, vmuuid, request):
    stdout = _api_execute(session, vmuuid, 'GET', request)
    results = simplejson.loads(stdout)
    return results


def _api_post_on_vm(session, vmuuid, request):
    stdout = _api_execute(session, vmuuid, 'POST', request)
    return stdout


def get_ps_dict(session, vmuuid):
    container_results = _api_get_json_on_vm(session, vmuuid,
                                            '/containers/json?all=1&size=1')
    return_results = []
    for container_result in container_results:
        container_result['Names'] = container_result['Names'][0][1:]
        # Do some patching for XC - ToDo: patch XC to not require these
        container_result['Container'] = container_result['Id'][:10]
        patched_result = {}
        for (key, value) in container_result.iteritems():
            patched_result[key.lower()] = value
        return_results.append({'entry': patched_result})
    return return_results


def get_ps_xml(session, vmuuid):
    result = {'docker_ps': get_ps_dict(session, vmuuid)}
    return Util.converttoxml(result)


def get_info_xml(session, vmuuid):
    result = {'docker_info': _api_get_json_on_vm(session, vmuuid, '/info')}
    return Util.converttoxml(result)


def get_version_xml(session, vmuuid):
    result = {'docker_version': _api_get_json_on_vm(session, vmuuid,
                                                    '/version')}
    return Util.converttoxml(result)


def passthrough(session, vmuuid, command):
    cmd = [command]
    result = _execute_cmd_on_vm(session, vmuuid, cmd)
    return result


def monitor_vm(session, vmuuid, vmref=None):
    # ToDo: must make this so much more efficient!
    Log.debug("Monitor %s" % vmuuid)
    if vmref == None:
        vmref = ApiHelper.get_vm_ref_by_uuid(session, vmuuid)
    ApiHelper.update_vm_other_config(
        session, vmref, 'docker_ps', get_ps_xml(session, vmuuid))


def update_vmuuids_to_monitor(session, vmrefstomonitor):
    # Make sure that we can talk to XAPI
    vmrecords = None
    removedvmrefs = {}
    try:
        if session == None:
            session = ApiHelper.get_local_api_session()
        vmrecords = ApiHelper.get_vm_records(session)
    except XenAPI.Failure:
        if None != session:
            # Something is seriously wrong, let's re-connect to XAPI
            try:
                session.xenapi.session.logout()
            except XenAPI.Failure:
                pass
            session = None
        return (session, vmrefstomonitor, removedvmrefs)
    hostref = ApiHelper.get_this_host_ref(session)
    for vmref, vmrecord in vmrecords.iteritems():
        if ('xscontainer-monitor' in vmrecord['other_config']
            or ('base_template_name' in vmrecord['other_config']
                and 'CoreOS'
                in vmrecord['other_config']['base_template_name'])):
            if vmrecord['power_state'] == 'Running':
                if (hostref == vmrecord['resident_on']
                        and vmref not in vmrefstomonitor):
                    Log.info("Adding monitor for VM name: %s, UUID: %s"
                             % (vmrecord['name_label'], vmrecord['uuid']))
                    vmrefstomonitor[vmref] = vmrecord['uuid']
            else:
                if vmref in vmrefstomonitor:
                    Log.info("Removing monitor for VM name: %s, UUID: %s"
                             % (vmrecord['name_label'], vmrecord['uuid']))
                    del(vmrefstomonitor[vmref])
                    removedvmrefs[vmref] = vmrecord['uuid']
    return (session, vmrefstomonitor, removedvmrefs)


def monitor_host(returninstantly=False):
    # ToDo: must make this so much more efficient!
    vmrefstomonitor = {}
    session = None
    passedtime = MONITORINTERVALLINS
    iterationstarttime = time.time() - MONITORINTERVALLINS
    while True:
        # Do throttle
        passedtime = time.time() - iterationstarttime
        iterationstarttime = time.time()
        if passedtime < MONITORINTERVALLINS:
            time.sleep(MONITORINTERVALLINS - passedtime)
        (session, vmrefstomonitor, removedvmrefs) = update_vmuuids_to_monitor(
            session, vmrefstomonitor)
        for vmref, vmuuid in vmrefstomonitor.iteritems():
            try:
                monitor_vm(session, vmuuid, vmref)
            except (XenAPI.Failure, Util.XSContainerException):
                # Ignore single VM failures and move on
                pass
        for vmref in removedvmrefs.iterkeys():
            session.xenapi.VM.remove_from_other_config(vmref, 'docker_ps')
        if returninstantly:
            break


def _get_inspect_dict(session, vmuuid, container):
    cmd = ['docker', 'inspect', container]
    result = _execute_cmd_on_vm(session, vmuuid, cmd)
    result = simplejson.loads(result)
    newresult = []
    for key, value in result[0].iteritems():
        newresult.append({'property': {'name': key, 'value': value}})
    return newresult


def get_inspect_xml(session, vmuuid, container):
    result = _get_inspect_dict(session, vmuuid, container)
    return Util.converttoxml({'docker_inspect': result})


def _run_container_cmd(session, vmuuid, container, command):
    result = _api_post_on_vm(session, vmuuid,
                             '/containers/%s/%s' % (container, command))
    return result


def start(session, vmuuid, container):
    result = _run_container_cmd(session, vmuuid, container, 'start')
    monitor_vm(session, vmuuid)
    return result


def stop(session, vmuuid, container):
    result = _run_container_cmd(session, vmuuid, container, 'stop')
    monitor_vm(session, vmuuid)
    return result


def restart(session, vmuuid, container):
    result = _run_container_cmd(session, vmuuid, container, 'restart')
    monitor_vm(session, vmuuid)
    return result


def pause(session, vmuuid, container):
    result = _run_container_cmd(session, vmuuid, container, 'pause')
    monitor_vm(session, vmuuid)
    return result


def unpause(session, vmuuid, container):
    result = _run_container_cmd(session, vmuuid, container, 'unpause')
    monitor_vm(session, vmuuid)
    return result
