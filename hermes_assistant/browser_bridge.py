"""Home Assistant Ingress adapter for Hermes' own Bot Screen.

No browser automation or second agent lives here. Runtime, persistent profile,
control lease and RFB input filtering are provided by the installed Hermes.
"""
import argparse
import asyncio
import contextlib
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

from aiohttp import web, WSMsgType


class NativeDesktop:
    def __init__(self):
        sys.path.insert(0, os.environ.get('HERMES_INSTALL_DIR', '/data/hermes/agent-code'))
        from tools.bot_desktop import runtime, lease, browser
        from tools.bot_desktop.rfb_filter import RfbClientFilter
        self.runtime, self.lease, self.browser, self.filter_type = runtime, lease, browser, RfbClientFilter

    def status(self):
        status = self.runtime.status().as_dict()
        # Filesystem paths and viewer capabilities never leave the server.
        return {key: status.get(key) for key in ('supported', 'installed', 'running', 'geometry', 'blocker', 'memory_available_mb', 'missing')} | {
            'browser_installed': bool(status.get('browser')),
            'lease': self.lease.public_view(self.lease.get()),
        }

    def start(self):
        self.runtime.start()
        launch = self.browser.dock_launch()
        if launch is None:
            raise RuntimeError('Headed Chromium is missing')
        executable, profile = launch
        if self.browser.running_instance_cdp_port(profile) is None:
            # Native shared-profile discovery is also used by agent-browser. Never
            # create an isolated Playwright context or a second browser profile.
            clean = {key: os.environ[key] for key in ('PATH', 'HOME', 'LANG') if key in os.environ}
            environment = self.runtime.desktop_env(clean)
            subprocess.Popen(self.browser.dock_argv(executable, profile) + ['--restore-last-session'],
                             env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)

    def take(self, viewer, reason='manual'):
        self.lease.acquire(viewer, reason=reason)

    def release(self, viewer, force=False):
        current = self.lease.get()
        owner = 'paused:' + viewer if current.viewer_id == 'paused:' + viewer else viewer
        self.lease.release(None if force else owner)

    def may_input(self, viewer):
        return self.lease.viewer_may_send_input(viewer)

    def client_filter(self, viewer):
        return self.filter_type(lambda: self.may_input(viewer))

    async def connect(self):
        # This HA integration deliberately serves the gateway-hosted native screen.
        sock = self.runtime.rfb_socket_path()
        if sock is None:
            raise OSError('Native screen is not running on this gateway')
        return await asyncio.open_unix_connection(str(sock))

    def touch(self):
        self.runtime.touch_activity()


def create_app(native, view_root=Path('/browser_view'), novnc_root=Path('/browser_novnc')):
    viewers = {}
    jobs = asyncio.Lock()

    @web.middleware
    async def authenticate(request, handler):
        # Bound to loopback; nginx accepts /browser/ only from Supervisor ingress,
        # strips client headers, and sets this marker itself. No public VNC/CDP/API.
        if request.remote not in ('127.0.0.1', '::1') or request.headers.get('X-Hermes-Browser-Ingress') != '1':
            raise web.HTTPForbidden(text='Home Assistant ingress required')
        return await handler(request)

    app = web.Application(middlewares=[authenticate], client_max_size=32 * 1024)

    def viewer(request, body=None):
        value = (body or {}).get('viewer_id') or request.query.get('viewer_id', '')
        if not isinstance(value, str) or viewers.get(value, 0) < time.monotonic():
            raise web.HTTPForbidden(text='Viewer expired; reopen the browser view')
        viewers[value] = time.monotonic() + 12 * 3600
        return value

    async def status(request):
        result = await asyncio.to_thread(native.status)
        ident = request.query.get('viewer_id')
        result['mine'] = bool(ident and viewers.get(ident, 0) > time.monotonic() and native.may_input(ident))
        return web.json_response(result, headers={'Cache-Control': 'no-store'})

    async def observe(request):
        now = time.monotonic()
        for ident in list(viewers):
            if viewers[ident] < now:
                del viewers[ident]
        if len(viewers) > 128:
            raise web.HTTPServiceUnavailable(text='Too many viewers')
        ident = secrets.token_urlsafe(32)
        viewers[ident] = now + 12 * 3600
        return web.json_response({'viewer_id': ident}, headers={'Cache-Control': 'no-store'})

    async def control(request):
        body = await request.json()
        ident = viewer(request, body)
        action = body.get('action')
        async with jobs:
            try:
                if action == 'start':
                    await asyncio.to_thread(native.start)
                elif action == 'take':
                    await asyncio.to_thread(native.take, ident)
                elif action == 'pause':
                    await asyncio.to_thread(native.take, 'paused:' + ident, 'paused')
                elif action in ('return', 'force_return'):
                    # An explicit force button is required after a lost viewer identity.
                    await asyncio.to_thread(native.release, ident, action == 'force_return')
                else:
                    raise web.HTTPBadRequest(text='Unknown action')
            except web.HTTPException:
                raise
            except Exception:
                return web.json_response({'error': 'Bildschirm konnte nicht gestartet oder umgeschaltet werden. Freien RAM und /data/hermes/bot-desktop/launcher.log prüfen.'}, status=503)
        return await status(request)

    async def ws(request):
        ident = viewer(request)
        try:
            reader, writer = await native.connect()
        except OSError:
            raise web.HTTPServiceUnavailable(text='Start the Hermes screen first')
        socket = web.WebSocketResponse(max_msg_size=512 * 1024, heartbeat=20)
        await socket.prepare(request)
        gate = native.client_filter(ident)

        async def inbound():
            async for message in socket:
                if message.type != WSMsgType.BINARY:
                    if message.type == WSMsgType.ERROR:
                        break
                    continue
                # Hermes' native stateful RFB parser rejects all unauthorized input,
                # including pointer, keyboard, clipboard and framebuffer resize.
                allowed = gate.feed(message.data)
                if allowed:
                    writer.write(allowed)
                    await writer.drain()

        async def outbound():
            stamped = 0
            while True:
                chunk = await reader.read(64 * 1024)
                if not chunk:
                    break
                if time.monotonic() - stamped > 30:
                    native.touch()
                    stamped = time.monotonic()
                await socket.send_bytes(chunk)

        tasks = [asyncio.create_task(inbound()), asyncio.create_task(outbound())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            await socket.close()
            # Never auto-release on disconnect: the user may be mid-login.
        return socket

    async def index(request):
        return web.FileResponse(view_root / 'index.html', headers={'Cache-Control': 'no-store'})

    app.router.add_get('/', index)
    app.router.add_get('/status', status)
    app.router.add_post('/viewer', observe)
    app.router.add_post('/control', control)
    app.router.add_get('/ws', ws)
    app.router.add_static('/assets/', view_root)
    app.router.add_static('/novnc/', novnc_root)
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=9010)
    args = parser.parse_args()
    native = NativeDesktop()
    app = create_app(native)

    async def start_screen(app):
        try:
            await asyncio.to_thread(native.start)
        except Exception:
            print('Bot Screen could not autostart; open Browser to check memory/packages.', flush=True)

    app.on_startup.append(start_screen)
    web.run_app(app, host='127.0.0.1', port=args.port, access_log=None)


if __name__ == '__main__':
    main()
