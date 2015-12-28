import simplejson

from xscontainer import util
import ssh


def execute_docker(session, vmuuid, request):
    connector = ssh
    return connector.execute_docker(session, vmuuid, request)


def execute_docker_event_listen(session, vmuuid, stoprequest):
    connector = ssh

    skippedheader = False
    data = ""
    openbrackets = 0
    request = "GET /events HTTP/1.0\r\n\r\n"
    for character in connector.execute_docker_listen_charbychar(session,
                                                                vmuuid,
                                                                request,
                                                                stoprequest):
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
    if len(data) >= 2048:
        raise util.XSContainerException('__monitor_vm_events' +
                                        'is full')


def determine_error_cause(session, vmuuid):
    connector = ssh
    return connector.determine_error_cause(session, vmuuid)
