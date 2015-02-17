"""
API Entry points for interacting with the DockerMonitor service.
"""
from xscontainer import docker
from xscontainer import docker_monitor
from xscontainer.api_helper import VM
from xscontainer.api_helper import XenAPIClient


def register_vm(vm_uuid, session):
    client = XenAPIClient(session)
    thevm = VM(client, uuid=vm_uuid)
    thevm.update_other_config(docker_monitor.REGISTRATION_KEY,
                              docker_monitor.REGISTRATION_KEY_ON)
    return


def deregister_vm(vm_uuid, session):
    client = XenAPIClient(session)
    thevm = VM(client, uuid=vm_uuid)
    thevm.update_other_config(docker_monitor.REGISTRATION_KEY,
                              docker_monitor.REGISTRATION_KEY_OFF)
    docker.wipe_docker_other_config(thevm)
    return


def mark_monitorable_vm(vm_uuid, session):
    """ Ensure the VM has a REGISTRATION_KEY in vm:other_config. This key is
        used by XC to know whether monitoring is an option for this VM """

    client = XenAPIClient(session)
    thevm = VM(client, uuid=vm_uuid)
    other_config = thevm.get_other_config()
    if (docker_monitor.REGISTRATION_KEY not in other_config):
        deregister_vm(vm_uuid, session)
