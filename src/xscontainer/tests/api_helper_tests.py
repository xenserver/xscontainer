from xscontainer import api_helper
import unittest
from mock import MagicMock, patch, call

class TestRefreshSessionOnFailureDecorator(unittest.TestCase):
    """
    Test class for validating the refresh decorator responds correctly under
    a series of exceptions.
    """

    @patch("xscontainer.api_helper.reinit_global_xapi_session")
    def test_session_gets_updated(self, mreinit_func):
        test_func = MagicMock()
        test_func.side_effect = [Exception("foo"), "foo"]
        api_helper.refresh_session_on_failure(test_func)()
        mreinit_func.assert_called_once()
        test_func.assert_has_calls([call(), call()])

    @patch("xscontainer.api_helper.reinit_global_xapi_session")
    def test_returns_value(self, mreinit_func):
        rv = "foo"
        test_func = MagicMock()
        test_func.return_value = rv
        result = api_helper.refresh_session_on_failure(test_func)()
        assert not mreinit_func.called
        self.assertEqual(result, rv)

    @patch("xscontainer.api_helper.reinit_global_xapi_session")
    def test_session_is_not_refresh_if_func_is_good(self, mreinit_func):
        rv = "bar"
        test_func = MagicMock()
        test_func.return_value = rv
        api_helper.refresh_session_on_failure(test_func)()
        assert not mreinit_func.called

    @patch("xscontainer.api_helper.reinit_global_xapi_session")
    def test_exception_is_passed_back_if_raised_twice(self, mreinit_func):
        rv = "bar"
        test_func = MagicMock()
        test_func.side_effect = Exception("bar")
        with self.assertRaises(Exception):
            api_helper.refresh_session_on_failure(test_func)()



class TestLocalXenAPIClient(unittest.TestCase):

    @patch("xscontainer.api_helper.get_local_api_session")
    def test_init_session(self, mget_local_api_session):
        client = api_helper.LocalXenAPIClient()
        mget_local_api_session.assert_called_once()

    @patch("xscontainer.api_helper.get_local_api_session")
    def test_get_session(self, mget_local_api_session):
        client = api_helper.LocalXenAPIClient()
        client.get_session()
        # Make sure it get's the local session and doesn't cache it
        mget_local_api_session.assert_has_calls([call(),call()])
