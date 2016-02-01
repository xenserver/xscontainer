import unittest
import types
from mock import MagicMock
from mock import patch

from xscontainer.util import tls_secret


def _add_vm_other_config_record(vm_records, vm_uuid, other_config_key,
                                other_config_value):
    if not isinstance(vm_records, types.DictType):
        vm_records = {}
    if vm_uuid not in vm_records:
        vm_records[vm_uuid] = {}
    if 'other_config' not in vm_records[vm_uuid]:
        vm_records[vm_uuid]['other_config'] = {}
    vm_records[vm_uuid]['other_config'][other_config_key] = other_config_value


class TestTlsSecret(unittest.TestCase):

    @patch("xscontainer.api_helper.get_vm_records")
    def remove_if_refcount_less_or_equal_below(self, get_vm_records):
        vm_records = {}
        _add_vm_other_config_record(vm_records,
                                    'myvmuuid',
                                    tls_secret.XSCONTAINER_TLS_CLIENT_KEY,
                                    'mysecretuuid')
        get_vm_records.return_value = vm_records
        session = MagicMock()

        tls_secret.remove_if_refcount_less_or_equal(session, 'mysecretuuid', 2)

        assert session.xenapi.secret.destroy.call_count == 1

    @patch("xscontainer.api_helper.get_vm_records")
    def emove_if_refcount_less_or_equal_above(self, get_vm_records):
        vm_records = {}
        _add_vm_other_config_record(vm_records,
                                    'myvmuuid',
                                    tls_secret.XSCONTAINER_TLS_CLIENT_KEY,
                                    'mysecretuuid')
        get_vm_records.return_value = vm_records
        session = MagicMock()

        tls_secret.remove_if_refcount_less_or_equal(session, 'mysecretuuid', 0)

        assert session.xenapi.secret.destroy.call_count == 0
