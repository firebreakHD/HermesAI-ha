import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge = load('browser_bridge', ROOT / 'browser_bridge.py')
setup = load('browser_setup', ROOT / 'browser_setup.py')


class SettingsTest(unittest.TestCase):
    def test_settings_preserve_secrets_mcp_and_user_fields_and_restore(self):
        config = {'model': 'existing', 'mcp_servers': {'ha': {'headers': {'Authorization': 'private'}}},
                  'browser': {'headed': False, 'command_timeout': 45}, 'bot_desktop': {'geometry': '1280x800'}}
        updated, saved = setup.merge(config, True)
        self.assertEqual(updated['mcp_servers'], config['mcp_servers'])
        self.assertEqual(updated['model'], 'existing')
        self.assertEqual(updated['browser']['command_timeout'], 45)
        self.assertEqual(updated['bot_desktop']['geometry'], '1280x800')
        self.assertTrue(updated['browser']['headed'])
        self.assertEqual(updated['bot_desktop']['idle_stop_minutes'], 0)
        again, original = setup.merge(updated, True, saved)
        self.assertEqual(saved, original)
        restored, _ = setup.merge(again, False, original)
        self.assertEqual(restored, config)

    def test_disable_does_not_undo_operator_edits(self):
        config, original = setup.merge({}, True)
        config['browser']['cloud_provider'] = 'custom'
        restored, _ = setup.merge(config, False, original)
        self.assertEqual(restored['browser']['cloud_provider'], 'custom')


class FakeNative:
    def __init__(self):
        self.running = False
        self.owner = None
        self.reason = ''
        self.starts = 0
        self.connects = 0
        self.stream = asyncio.StreamReader()
        self.output = bytearray()
        self.closed = False

    def status(self):
        return {'supported': True, 'installed': True, 'browser_installed': True, 'running': self.running,
                'lease': {'holder': 'human' if self.owner else 'agent', 'reason': self.reason}}

    def start(self):
        self.starts += 1
        self.running = True

    def take(self, viewer, reason='manual'):
        self.owner = viewer
        self.reason = reason

    def release(self, viewer, force=False):
        if force or self.owner in (viewer, 'paused:' + viewer):
            self.owner = None
            self.reason = ''

    def may_input(self, viewer):
        return self.owner == viewer

    def client_filter(self, viewer):
        outer = self
        class Filter:
            def feed(self, chunk):
                return chunk if outer.may_input(viewer) else b''
        return Filter()

    async def connect(self):
        if not self.running:
            raise OSError()
        self.connects += 1
        outer = self
        class Writer:
            def write(self, data):
                outer.output.extend(data)
            async def drain(self):
                pass
            def close(self):
                outer.closed = True
            async def wait_closed(self):
                pass
        return self.stream, Writer()

    def touch(self):
        pass


class AdapterTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # All generated files stay under the authorized Hermes checkout.
        parent = ROOT / '.test-data'
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.native = FakeNative()
        root = Path(self.temp.name)
        (root / 'index.html').write_text('Native browser view', encoding='utf-8')
        self.client = TestClient(TestServer(bridge.create_app(self.native, view_root=root, novnc_root=root)))
        await self.client.start_server()
        self.headers = {'X-Hermes-Browser-Ingress': '1'}

    async def asyncTearDown(self):
        await self.client.close()
        self.temp.cleanup()

    async def call(self, path, data=None):
        response = await self.client.request('POST' if data is not None else 'GET', path, json=data, headers=self.headers)
        self.assertEqual(response.status, 200, await response.text())
        return await response.json()

    async def test_unauthenticated_access_and_forged_viewers_are_rejected(self):
        self.assertEqual((await self.client.get('/status')).status, 403)
        self.assertEqual((await self.client.post('/control', json={'viewer_id': 'invented', 'action': 'take'}, headers=self.headers)).status, 403)
        self.assertEqual((await self.client.get('/ws?viewer_id=invented', headers=self.headers)).status, 403)

    async def test_take_pause_return_and_explicit_recovery(self):
        first = (await self.call('/viewer', {}))['viewer_id']
        second = (await self.call('/viewer', {}))['viewer_id']
        await self.call('/control', {'viewer_id': first, 'action': 'start'})
        await self.call('/control', {'viewer_id': first, 'action': 'take'})
        self.assertTrue((await self.call('/status?viewer_id=' + first))['mine'])
        await self.call('/control', {'viewer_id': second, 'action': 'return'})
        self.assertEqual(self.native.owner, first, 'another viewer may not silently revoke a takeover')
        await self.call('/control', {'viewer_id': first, 'action': 'pause'})
        self.assertFalse(self.native.may_input(first))
        await self.call('/control', {'viewer_id': first, 'action': 'return'})
        self.assertIsNone(self.native.owner)
        await self.call('/control', {'viewer_id': first, 'action': 'take'})
        await self.call('/control', {'viewer_id': second, 'action': 'force_return'})
        self.assertIsNone(self.native.owner)

    async def test_live_stream_uses_one_native_screen_and_disconnect_keeps_lease(self):
        ident = (await self.call('/viewer', {}))['viewer_id']
        await self.call('/control', {'viewer_id': ident, 'action': 'start'})
        await self.call('/control', {'viewer_id': ident, 'action': 'take'})
        ws = await self.client.ws_connect('/ws?viewer_id=' + ident, headers=self.headers)
        self.native.stream.feed_data(b'RFB test frame')
        self.assertEqual((await ws.receive()).data, b'RFB test frame')
        await ws.send_bytes(b'manual-input')
        for _ in range(20):
            if self.native.output:
                break
            await asyncio.sleep(.01)
        self.assertEqual(self.native.output, b'manual-input')
        await self.call('/control', {'viewer_id': ident, 'action': 'return'})
        await ws.send_bytes(b'blocked-input')
        await asyncio.sleep(.03)
        self.assertEqual(self.native.output, b'manual-input')
        await self.call('/control', {'viewer_id': ident, 'action': 'take'})
        await ws.close()
        self.assertEqual(self.native.owner, ident, 'closing or losing the viewer must leave the agent blocked')
        self.assertEqual(self.native.connects, 1)


class MobileToolbarTest(unittest.TestCase):
    def test_tools_move_to_top_and_are_collapsed_by_default(self):
        nginx = (ROOT / 'nginx.conf').read_text(encoding='utf-8')
        self.assertIn('<details class="hermes-addon-tools">', nginx)
        self.assertNotIn('<details open', nginx)
        self.assertIn('top:max(8px,env(safe-area-inset-top))', nginx)
        self.assertNotIn('bottom:14px', nginx)
        self.assertIn('allow 172.30.32.2;', nginx)
        self.assertIn('proxy_set_header X-Hermes-Browser-Ingress "1";', nginx)


if __name__ == '__main__':
    unittest.main()
