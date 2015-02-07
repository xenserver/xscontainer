import api_helper
import xscontainer.util as util
from xscontainer.util import log
from xscontainer import api_helper

import re
import simplejson

def prepare_request_cmds(request_type, request):
    # ToDo: Must really not pipe (!!!)
    request_cmds = ['echo -e "%s %s HTTP/1.0\r\n"' % (request_type, request) +
                    '| ncat -U /var/run/docker.sock']
    return request_cmds


def _interact_with_api(session, vmuuid, request_type, request):
    request_cmds = prepare_request_cmds(request_type, request)
    stdout = api_helper.execute_ssh(session, vmuuid, request_cmds)
    headerend = stdout.index('\r\n\r\n')
    header = stdout[:headerend]
    body = stdout[headerend + 4:]
    # ToDo: Should use re
    headersplits = header.split('\r\n', 2)[0].split(' ')
    #protocol = headersplits[0]
    statuscode = headersplits[1]
    if statuscode[0] != '2':
        status = ' '.join(headersplits[2:])
        raise util.XSContainerException("Request %s led to bad status %s %s"
                                        % (request_cmds, statuscode, status))
    return body


def _get_api_json(session, vmuuid, request):
    stdout = _interact_with_api(session, vmuuid, 'GET', request)
    results = simplejson.loads(stdout)
    return results


def _post_api(session, vmuuid, request):
    stdout = _interact_with_api(session, vmuuid, 'POST', request)
    return stdout


def _verify_or_throw_invalid_container(container):
    if not re.match('^[a-z0-9]+$', container):
        raise util.XSContainerException("Invalid container")

def patch_docker_ps_status(ps_dict):
    """
    Patch the status returned by Docker PS in order to avoid a stale
    value being presented to the user. Due to the fact that xscontainer
    only updates docker info when a docker event happens, it does not
    register the regular status updates for the increase in container
    run time. E.g. "Up 40 seconds" ... "Up 4 hours".

    The tempoary solution is to just return "Up".
    """
    log.debug("Container Rec: %s" % ps_dict)
    status = ps_dict["Status"]
    if status.startswith("Up"):
        ps_dict["Status"] = "Up"
    return

def get_ps_dict(session, vmuuid):
    container_results = _get_api_json(session, vmuuid,
                                      '/containers/json?all=1&size=1')
    return_results = []
    for container_result in container_results:
        container_result['Names'] = container_result['Names'][0][1:]
        # Do some patching for XC - ToDo: patch XC to not require these
        container_result['Container'] = container_result['Id'][:10]
        patch_docker_ps_status(container_result)
        patched_result = {}
        for (key, value) in container_result.iteritems():
            patched_result[key.lower()] = value
        return_results.append({'entry': patched_result})
    return return_results


def get_ps_xml(session, vmuuid):
    result = {'docker_ps': get_ps_dict(session, vmuuid)}
    return util.converttoxml(result)


def get_info_dict(session, vmuuid):
    return _get_api_json(session, vmuuid, '/info')


def get_info_xml(session, vmuuid):
    result = {'docker_info': get_info_dict(session, vmuuid)}
    return util.converttoxml(result)


def get_version_dict(session, vmuuid):
    return _get_api_json(session, vmuuid, '/version')


def get_version_xml(session, vmuuid):
    result = {'docker_version': get_version_dict(session, vmuuid)}
    return util.converttoxml(result)


# ToDo: Must remove this cmd, really
def passthrough(session, vmuuid, command):
    cmd = [command]
    result = api_helper.execute_ssh(session, vmuuid, cmd)
    return result


def get_inspect_dict(session, vmuuid, container):
    _verify_or_throw_invalid_container(container)
    result = _get_api_json(session, vmuuid, '/containers/%s/json'
                                            % (container))
    return result


def get_inspect_xml(session, vmuuid, container):
    result = {'docker_inspect': get_inspect_dict(session, vmuuid, container)}
    # ToDo: util.converttoxml doesn't quite produce valid xml for inspect
    return util.converttoxml(result)


def get_top_dict(session, vmuuid, container):
    _verify_or_throw_invalid_container(container)
    result = _get_api_json(session, vmuuid, '/containers/%s/top'
                                            % (container))
    titles = result['Titles']
    psentries = []
    for process in result['Processes']:
        process_dict = {}
        item = 0
        if len(titles) > len(process):
            raise util.XSContainerException("Can't parse top output")
        for title in titles:
            process_dict.update({title: process[item]})
            item = item + 1
        psentries.append({'Process': process_dict})
    return psentries


def get_top_xml(session, vmuuid, container):
    result = {'docker_top': get_top_dict(session, vmuuid, container)}
    return util.converttoxml(result)


def _run_container_cmd(session, vmuuid, container, command):
    _verify_or_throw_invalid_container(container)
    result = _post_api(session, vmuuid,
                       '/containers/%s/%s' % (container, command))
    return result


def start(session, vmuuid, container):
    result = _run_container_cmd(session, vmuuid, container, 'start')
    return result


def stop(session, vmuuid, container):
    result = _run_container_cmd(session, vmuuid, container, 'stop')
    return result


def restart(session, vmuuid, container):
    result = _run_container_cmd(session, vmuuid, container, 'restart')
    return result


def pause(session, vmuuid, container):
    result = _run_container_cmd(session, vmuuid, container, 'pause')
    return result


def unpause(session, vmuuid, container):
    result = _run_container_cmd(session, vmuuid, container, 'unpause')
    return result


def update_docker_info(vm):
    vm.update_other_config('docker_info', get_info_xml(vm.get_session(),
                                                       vm.get_uuid()))


def update_docker_version(vm):
    vm.update_other_config('docker_version', get_version_xml(vm.get_session(),
                                                             vm.get_uuid()))


def update_docker_ps(vm):
    vm.update_other_config('docker_ps', get_ps_xml(vm.get_session(),
                                                   vm.get_uuid()))


def wipe_docker_other_config(vm):
    vm.remove_from_other_config('docker_ps')
    vm.remove_from_other_config('docker_info')
    vm.remove_from_other_config('docker_version')
