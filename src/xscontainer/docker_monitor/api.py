from xscontainer.docker_monitor import REGISTRATION_KEY

"""
API Entry points for interacting with the DockerMonitor service.
"""

def register_vm(session, vm_uuid):
    return session.xenapi.VM.set_other_config(REGISTRATION_KEY, "True")

def deregister_vm(session, vm_uuid):
    return session.xenapi.VM.remove_from_other_config(REGISTRATION_KEY)
