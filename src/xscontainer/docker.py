from xscontainer import api_helper
from xscontainer import remote_helper
from xscontainer import util
from xscontainer.util import log

import re
import json


def prepare_request_stdin(request_type, request):
    return ("%s %s HTTP/1.0\r\n\r\n" % (request_type, request))


def _interact_with_api(session, vmuuid, request_type, request,
                       message_error=False):
    request = prepare_request_stdin(request_type, request)
    stdout = remote_helper.execute_docker(session, vmuuid, request)
    headerend = stdout.index('\r\n\r\n')
    header = stdout[:headerend]
    body = stdout[headerend + 4:]
    # ToDo: Should use re
    headersplits = header.split('\r\n', 2)[0].split(' ')
    # protocol = headersplits[0]
    statuscode = headersplits[1]
    if statuscode[0] != '2':
        # this did not work
        status = ' '.join(headersplits[2:])
        failure_title = "Container Management Error"
        failure_body = body.strip()
        if failure_body == "":
            if statuscode == "304":
                # 304 does not have a body and is quite common.
                failure_body = ("The requested operation is currently not "
                                "possible. Please try again later.")
            else:
                failure_body = ("The requested operation failed.")
        failure_body = failure_body + " (" + statuscode + ")"
        if ":" in failure_body:
            (failure_title, failure_body) = failure_body.split(":", 1)
        if message_error:
            api_helper.send_message(session, vmuuid, failure_title,
                                    failure_body)
        message = ("Request '%s' led to status %s - %s: %s"
                   % (request, status, failure_title, failure_body))
        log.info(message)
        raise util.XSContainerException(message)
    return body


def _get_api_json(session, vmuuid, request):
    stdout = _interact_with_api(session, vmuuid, 'GET', request)
    results = util.convert_dict_to_ascii(json.loads(stdout))
    return results


def _post_api(session, vmuuid, request):
    stdout = _interact_with_api(session, vmuuid, 'POST', request,
                                message_error=True)
    return stdout


def _verify_or_throw_container(container):
    if not re.match('^[a-z0-9_.-]+$', container):
        raise util.XSContainerException("Invalid container")


def patch_docker_ps_status(ps_dict):
    """
    Patch the status returned by Docker PS in order to avoid a stale
    value being presented to the user. Due to the fact that xscontainer
    only updates docker info when a docker event happens, it does not
    register the regular status updates for the increase in container
    run time. E.g. "Up 40 seconds" ... "Up 4 hours".

    The tempoary solution is to just return "Up", "Up (Paused)" or Exited (rc).
    """
    status = ps_dict["Status"]
    if status.startswith("Up"):
        if status.endswith("(Paused)"):
            ps_dict["Status"] = "Up (Paused)"
        else:
            ps_dict["Status"] = "Up"
    elif status.startswith("Exited ("):
        closing_bracket_index = status.rfind(')')
        if closing_bracket_index:
            ps_dict["Status"] = ps_dict["Status"][0:closing_bracket_index + 1]
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
    result = remote_helper.ssh.execute_ssh(session, vmuuid, cmd)
    return result


def get_inspect_dict(session, vmuuid, container):
    _verify_or_throw_container(container)
    result = _get_api_json(session, vmuuid, '/containers/%s/json'
                                            % (container))
    return result


def get_inspect_xml(session, vmuuid, container):
    result = {'docker_inspect': get_inspect_dict(session, vmuuid, container)}
    return util.converttoxml(result)


def get_top_dict(session, vmuuid, container):
    _verify_or_throw_container(container)
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
    _verify_or_throw_container(container)
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
    update_docker_ps_workaround(session, vmuuid)
    return result


def unpause(session, vmuuid, container):
    result = _run_container_cmd(session, vmuuid, container, 'unpause')
    update_docker_ps_workaround(session, vmuuid)
    return result


def update_docker_info(thevm):
    thevm.update_other_config('docker_info', get_info_xml(thevm.get_session(),
                                                          thevm.get_uuid()))


def update_docker_version(thevm):
    thevm.update_other_config('docker_version',
                              get_version_xml(thevm.get_session(),
                                              thevm.get_uuid()))


def update_docker_ps(thevm):
    thevm.update_other_config('docker_ps', get_ps_xml(thevm.get_session(),
                                                      thevm.get_uuid()))


def update_docker_ps_workaround(session, vm_uuid):
    """
    Only recent docker versions support sending events for pause and unpause.
    This works around this - at least when we post the command.
    """
    client = api_helper.XenAPIClient(session)
    thevm = api_helper.VM(client, uuid=vm_uuid)
    record = thevm.get_other_config()
    if 'docker_ps' in record:
        update_docker_ps(thevm)


def wipe_docker_other_config(thevm):
    thevm.remove_from_other_config('docker_ps')
    thevm.remove_from_other_config('docker_info')
    thevm.remove_from_other_config('docker_version')
