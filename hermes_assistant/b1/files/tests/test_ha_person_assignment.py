"""B1 regression checks. Run with python3 -m unittest discover -s tests -p test_ha_person_assignment.py."""
import io
import os
import sys
import types
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode

from api import ha_person
from api import auth
import api


class Handler:
    def __init__(self, user, method='GET', form=None):
        body = urlencode(form or {}).encode()
        self.headers = {'X-Remote-User-Id': user, 'X-Ingress-Path': '/ingress/test',
                        'Content-Length': str(len(body)),
                        'Content-Type': 'application/x-www-form-urlencoded'}
        self.client_address = ('127.0.0.1', 4567)
        self.command = method
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = None
        self.response_headers = {}

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.response_headers[key] = value

    def end_headers(self):
        pass


class PersonAssignmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = str(Path(self.tmp.name) / 'people.json')
        self.env = patch.dict(os.environ, {'HERMES_WEBUI_HA_PERSON_MAP': p,
                         'HERMES_WEBUI_TRUSTED_AUTH_HEADER': 'X-Remote-User-Id'})
        self.env.start()
        self.addCleanup(self.env.stop)
        # The identity form only needs the proxy-peer predicate from routes.
        # Stub the giant route module so this test runs without WebUI deps.
        routes = types.ModuleType('api.routes')
        routes._raw_peer_is_trusted_proxy = lambda handler: True
        api.routes = routes
        self.addCleanup(delattr, api, 'routes')
        stub = patch.dict(sys.modules, {'api.routes': routes})
        stub.start()
        self.addCleanup(stub.stop)

    def test_two_accounts_are_distinct_and_reassignment_denied(self):
        self.assertIsNone(ha_person.lookup('person-a'))
        self.assertEqual(ha_person.assign('person-a', 'Marcel', 'default')['profile'], 'default')
        self.assertEqual(ha_person.assign('person-b', 'Haushalt', 'friday')['profile'], 'friday')
        self.assertEqual(ha_person.lookup('person-a')['profile'], 'default')
        self.assertEqual(ha_person.lookup('person-b')['profile'], 'friday')
        with self.assertRaises(ValueError):
            ha_person.assign('person-a', 'Anders', 'friday')
        self.assertEqual(Path(os.getenv('HERMES_WEBUI_HA_PERSON_MAP')).stat().st_mode & 0o777, 0o600)

    def test_missing_invalid_mapping_never_guesses(self):
        self.assertIsNone(ha_person.lookup('unknown'))
        Path(os.getenv('HERMES_WEBUI_HA_PERSON_MAP')).write_text('broken')
        self.assertIsNone(ha_person.lookup('unknown'))

    def test_one_time_form_and_csrf(self):
        info = {'token': 'private-test-token', 'auth_type': 'trusted', 'username': 'person-a'}
        with patch('api.routes._raw_peer_is_trusted_proxy', return_value=True):
            get = Handler('person-a')
            ha_person.handle(get, info)
            self.assertEqual(get.status, 200)
            self.assertIn(b'Einmalige Zuordnung', get.wfile.getvalue())
            bad = Handler('person-a', 'POST', {'role': 'marcel', 'csrf': 'wrong'})
            ha_person.handle(bad, info)
            self.assertEqual(bad.status, 403)
            self.assertIsNone(ha_person.lookup('person-a'))
            good = Handler('person-a', 'POST', {'role': 'marcel', 'csrf': ha_person._csrf(info, 'person-a')})
            ha_person.handle(good, info)
            self.assertEqual(good.status, 303)
            self.assertEqual(ha_person.lookup('person-a')['profile'], 'default')

    def test_untrusted_socket_or_changed_identity_denied(self):
        info = {'token': 'private-test-token', 'auth_type': 'trusted', 'username': 'person-a'}
        with patch('api.routes._raw_peer_is_trusted_proxy', return_value=False):
            h = Handler('person-a')
            ha_person.handle(h, info)
            self.assertEqual(h.status, 403)
        with patch('api.routes._raw_peer_is_trusted_proxy', return_value=True):
            h = Handler('person-b')
            ha_person.handle(h, info)
            self.assertEqual(h.status, 403)

    def test_native_profile_binding_uses_only_explicit_id(self):
        with patch.dict(os.environ, {'HERMES_WEBUI_GROUP_PROFILE_MAP': '{"other":"default"}',
                    'HERMES_WEBUI_TRUSTED_GROUPS_HEADER': 'X-Remote-User-Groups'}):
            h = Handler('person-a')
            h.headers['X-Remote-User-Groups'] = 'other'
            self.assertIsNone(auth._trusted_auth_bound_profile(h))
            ha_person.assign('person-a', 'Haushalt', 'friday')
            self.assertEqual(auth._trusted_auth_bound_profile(h), 'friday')


if __name__ == '__main__':
    unittest.main()
