from xscontainer.docker_monitor import REGISTRATION_KEY
from xscontainer.api_helper import VM, XenAPIClient

"""
API Entry points for interacting with the DockerMonitor service.
"""

def register_vm(vm_uuid):
    client = XenAPIClient()
    vm = VM(client, uuid=vm_uuid)
    vm.remove_from_other_config(REGISTRATION_KEY) # safe to call if key not present
    vm.add_to_other_config(REGISTRATION_KEY, "True")
    return

def deregister_vm(vm_uuid):
    client = XenAPIClient()
    vm = VM(client, uuid=vm_uuid)
    vm.remove_from_other_config(REGISTRATION_KEY)
    return
