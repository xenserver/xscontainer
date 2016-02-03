import simplejson

from xscontainer import api_helper
from xscontainer import util
import ssh
import tls


def _get_connector(session, vmuuid):
    connectionmode = api_helper.get_vm_xscontainer_mode(session, vmuuid)
    if connectionmode == 'ssh':
        return ssh
    elif connectionmode == 'tls':
        return tls
    else:
        assert 0


def execute_docker(session, vmuuid, request):
    connector = _get_connector(session, vmuuid)
    return connector.execute_docker(session, vmuuid, request)


def execute_docker_event_listen(session, vmuuid, stoprequest):
    skippedheader = False
    data = ""
    openbrackets = 0
    request = "GET /events HTTP/1.0\r\n\r\n"
    connector = _get_connector(session, vmuuid)
    for read_data in connector.execute_docker_data_listen(session,
                                                          vmuuid,
                                                          request,
                                                          stoprequest):
        for character in read_data:
            data = data + character
            if (not skippedheader and character == "\n" and
                    len(data) >= 4 and data[-4:] == "\r\n\r\n"):
                data = ""
                skippedheader = True
            elif character == '{':
                openbrackets = openbrackets + 1
            elif character == '}':
                openbrackets = openbrackets - 1
                if openbrackets == 0:
                    event = simplejson.loads(data)
                    yield event
                    data = ""
            if len(read_data) >= 2048:
                raise util.XSContainerException('execute_docker_event_listen' +
                                                'is full')


def determine_error_cause(session, vmuuid):
    connector = _get_connector(session, vmuuid)
    return connector.determine_error_cause(session, vmuuid)
