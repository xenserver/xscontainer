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
    thevm.update_other_config(docker_monitor.REGISTRATION_KEY, "True")
    return


def deregister_vm(vm_uuid, session):
    client = XenAPIClient(session)
    thevm = VM(client, uuid=vm_uuid)
    thevm.update_other_config(docker_monitor.REGISTRATION_KEY, "False")
    docker.wipe_docker_other_config(thevm)
    return
