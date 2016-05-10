from xscontainer import api_helper
from xscontainer import util
from xscontainer.util import tls_secret
from xscontainer.util import log
import constants

import errno
import select
import ssl
import socket
import sys

DOCKER_TLS_PORT = 2376
TLS_CIPHER = "AES128-SHA"

ERROR_CAUSE_NETWORK = (
    "Error: Cannot find a valid IP that allows TLS connections to Docker "
    "on the VM. Please make sure that Tools are installed, a "
    "network route is set up, Docker is running and configured for TLS "
    "and TLS is reachable from Dom0 on port %d. Please " % (DOCKER_TLS_PORT) +
    "particularly check the firewall configuration inside the VM.")


class TlsException(util.XSContainerException):
    pass


def _get_socket(session, vm_uuid):
    temptlspaths = tls_secret.export_for_vm(session, vm_uuid)
    thesocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Force TLSv1.2 - as it is the safest choice
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    context.set_ciphers(TLS_CIPHER)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(certfile=temptlspaths['client_cert'],
                            keyfile=temptlspaths['client_key'])
    context.load_verify_locations(cafile=temptlspaths['ca_cert'])
    return context.wrap_socket(thesocket,
                               server_side=False,
                               do_handshake_on_connect=True)


def execute_docker(session, vm_uuid, request):
    host = api_helper.get_suitable_vm_ip(session, vm_uuid, DOCKER_TLS_PORT)
    log.info("tls.execute_docker for VM %s, via %s" % (vm_uuid, host))
    asocket = _get_socket(session, vm_uuid)
    try:
        asocket.connect((host, DOCKER_TLS_PORT))
        asocket.send(request)
        result = ""
        while len(result) < constants.MAX_BUFFER_SIZE:
            result_iteration = asocket.recv(
                constants.MAX_BUFFER_SIZE - len(result))
            if result_iteration == "":
                break
            result += result_iteration
    except ssl.SSLError, exception:
        raise TlsException("Failed to communicate with Docker via TLS: %s"
                           % exception, (sys.exc_info()[2]))
    finally:
        try:
            asocket.close()
        except Exception:
            log.exception("Failed to close socket. Moving on.")
    return result


def execute_docker_data_listen(session, vm_uuid, request,
                               stop_monitoring_request):
    host = api_helper.get_suitable_vm_ip(session, vm_uuid, DOCKER_TLS_PORT)
    log.info("tls.execute_docker_listen_charbychar for VM %s, via %s"
             % (vm_uuid, host))
    asocket = _get_socket(session, vm_uuid)
    try:
        asocket.connect((host, DOCKER_TLS_PORT))
        if hasattr(asocket, 'version'):
            # Newer python versions provide the TLS version
            log.info("Connected VM %s using %s" % (vm_uuid,
                                                   asocket.version()))
        asocket.send(request)
        asocket.setblocking(0)
        while not stop_monitoring_request:
            rlist, _, _ = select.select(
                [asocket.fileno()], [], [],
                constants.MONITOR_EVENTS_POLL_INTERVAL)
            if not rlist:
                continue
            try:
                read_data = asocket.recv(1024)
                if read_data == "":
                    break
                yield read_data
            except IOError, exception:
                if exception[0] not in (errno.EAGAIN, errno.EINTR):
                    raise
                sys.exc_clear()
                continue
    except ssl.SSLError, exception:
        raise TlsException("Failed to communicate with Docker via TLS: %s"
                           % exception, (sys.exc_info()[2]))
    except socket.error, exception:
        raise TlsException("The connection failed: %s"
                           % exception, (sys.exc_info()[2]))
    finally:
        try:
            asocket.close()
        except:
            log.exception("Failed to close socket. Moving on.")


def determine_error_cause(session, vm_uuid):
    cause = ""
    try:
        api_helper.get_suitable_vm_ip(session, vm_uuid, DOCKER_TLS_PORT)
    except util.XSContainerException:
        cause = ERROR_CAUSE_NETWORK
        # No reason to continue, if there is no network connection
        return cause
    try:
        request = "GET '/info' HTTP/1.0\r\n\r\n"
        execute_docker(session, vm_uuid, request)
    except TlsException:
        cause = (cause + "Unable to connect to the VM using TLS. Please "
                 "check the logs inside the VM and also try "
                 "connecting manually. The cause may be a problem "
                 "with the TLS certificates.")
    if cause == "":
        cause = "Unable to determine cause of failure."
    return cause
