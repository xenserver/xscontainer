import base64
import os
import struct

from mock import patch
from nose.tools import assert_equal
from nose.tools import assert_in
from nose.tools import assert_raises

from xscontainer.remote_helper import ssh


VM_UUID = "00000000-0000-0000-0000-000000000000"


def key_blob(keytype):
    value = struct.pack(">I", len(keytype)) + keytype
    return base64.b64encode(value)


def test_key_type_is_read_from_key_blob():
    assert_equal("ssh-ed25519", ssh._key_type(key_blob("ssh-ed25519")))


def test_invalid_key_blob_is_rejected():
    assert_raises(ssh.SshException, ssh._key_type, "not base64")


@patch("xscontainer.remote_helper.ssh.api_helper.get_idrsa_secret_private")
@patch("xscontainer.remote_helper.ssh.api_helper.get_ssh_hostkey")
@patch("xscontainer.remote_helper.ssh.api_helper.get_suitable_vm_ip")
@patch("xscontainer.remote_helper.ssh.api_helper."
       "get_vm_xscontainer_username")
def test_remembered_rsa_key_uses_rsa_sha2(
        get_username, get_ip, get_hostkey, get_private_key):
    get_username.return_value = "root"
    get_ip.return_value = "192.0.2.10"
    get_hostkey.return_value = key_blob("ssh-rsa")
    get_private_key.return_value = "private key"

    with ssh.OpenSshConnection(object(), VM_UUID) as connection:
        command = connection.command("true")
        assert_in("HostKeyAlgorithms="
                  "rsa-sha2-512,rsa-sha2-256,ssh-rsa", command)
        assert_equal(0600, os.stat(connection.private_key).st_mode & 0777)
        assert_equal(0600, os.stat(connection.known_hosts).st_mode & 0777)


def test_ncat_keeps_response_side_open():
    assert_in("--no-shutdown", ssh.prepare_request_cmd())


def test_permission_denied_is_authentication_error():
    assert_raises(ssh.AuthenticationException,
                  ssh._raise_process_error,
                  VM_UUID, 255, "Permission denied (publickey).")


def test_changed_host_key_is_specific_error():
    assert_raises(ssh.VmHostKeyException,
                  ssh._raise_process_error,
                  VM_UUID, 255,
                  "REMOTE HOST IDENTIFICATION HAS CHANGED")
