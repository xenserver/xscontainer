from xscontainer.api_helper import VM, XenAPIClient, LocalXenAPIClient
from xscontainer.docker_monitor import REGISTRATION_KEY
import xscontainer.docker as docker

"""
API Entry points for interacting with the DockerMonitor service.
"""

def register_vm(vm_uuid, session):
    client = XenAPIClient(session)
    thevm = VM(client, uuid=vm_uuid)
    thevm.update_other_config(REGISTRATION_KEY, "True")
    return


def deregister_vm(vm_uuid, session):
    client = XenAPIClient(session)
    thevm = VM(client, uuid=vm_uuid)
    thevm.update_other_config(REGISTRATION_KEY, "False")
    docker.wipe_docker_other_config(thevm)
    return
