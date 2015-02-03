from xscontainer.docker_monitor import REGISTRATION_KEY
from xscontainer.api_helper import VM, XenAPIClient, LocalXenAPIClient

"""
API Entry points for interacting with the DockerMonitor service.
"""

def register_vm(vm_uuid, session=None):
    if not session:
        client = LocalXenAPIClient()
    else:
        client = XenAPIClient(session)
    vm = VM(client, uuid=vm_uuid)
    # safe to call if key not present
    vm.remove_from_other_config(REGISTRATION_KEY)
    vm.add_to_other_config(REGISTRATION_KEY, "True")
    return


def deregister_vm(vm_uuid, session=None):
    if not session:
        client = LocalXenAPIClient()
    else:
        client = XenAPIClient(session)
    vm = VM(client, uuid=vm_uuid)
    vm.remove_from_other_config(REGISTRATION_KEY)
    return
