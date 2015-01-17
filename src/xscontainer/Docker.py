import ApiHelper
import Log
import Util

import re
import simplejson


def _api_execute(session, vmuuid, request_type, request):
    # ToDo: Must really not pipe (!!!)
    cmd = ['echo -e "%s %s HTTP/1.0\r\n"' % (request_type, request) +
           '| ncat -U /var/run/docker.sock']
    stdout = Util.execute_ssh(session, vmuuid, cmd)
    headerend = stdout.index('\r\n\r\n')
    header = stdout[:headerend]
    body = stdout[headerend + 4:]
    # ToDo: Should use re
    headersplits = header.split('\r\n', 2)[0].split(' ')
    #protocol = headersplits[0]
    statuscode = headersplits[1]
    if statuscode[0] != '2':
        status = ' '.join(headersplits[2:])
        raise Util.XSContainerException("Request %s led to bad status %s %s"
                                        % (cmd, statuscode, status))
    return body


def _verify_or_throw_invalid_container(container):
    if not re.match('^[a-z0-9]+$', container):
        raise Util.XSContainerException("Invalid container")


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


# ToDo: Must drop this, really
def passthrough(session, vmuuid, command):
    cmd = [command]
    result = Util.execute_ssh(session, vmuuid, cmd)
    return result


def _get_inspect_dict(session, vmuuid, container):
    _verify_or_throw_invalid_container(container)
    result = _api_get_json_on_vm(session, vmuuid,
                                 '/containers/%s/json' % (container))
    return result


def get_inspect_xml(session, vmuuid, container):
    _verify_or_throw_invalid_container(container)
    result = _get_inspect_dict(session, vmuuid, container)
    return Util.converttoxml({'docker_inspect': result})


def _run_container_cmd(session, vmuuid, container, command):
    result = _api_post_on_vm(session, vmuuid,
                             '/containers/%s/%s' % (container, command))
    return result


def start(session, vmuuid, container):
    _verify_or_throw_invalid_container(container)
    result = _run_container_cmd(session, vmuuid, container, 'start')
    return result


def stop(session, vmuuid, container):
    _verify_or_throw_invalid_container(container)
    result = _run_container_cmd(session, vmuuid, container, 'stop')
    return result


def restart(session, vmuuid, container):
    _verify_or_throw_invalid_container(container)
    result = _run_container_cmd(session, vmuuid, container, 'restart')
    return result


def pause(session, vmuuid, container):
    _verify_or_throw_invalid_container(container)
    result = _run_container_cmd(session, vmuuid, container, 'pause')
    return result


def unpause(session, vmuuid, container):
    _verify_or_throw_invalid_container(container)
    result = _run_container_cmd(session, vmuuid, container, 'unpause')
    return result
