import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BeeperIntegrationTest(unittest.TestCase):
    def test_persistent_existing_installation_is_started_without_debug_port(self):
        script = (ROOT / 'beeper-desktop.sh').read_text(encoding='utf-8')
        self.assertIn('/data/hermes/beeper-cli', script)
        self.assertIn('apps/desktop/extracted/squashfs-root/AppRun', script)
        self.assertIn('profiles/desktop/linux-desktop', script)
        self.assertIn("jq -r '.desktop.path // empty'", script)
        self.assertIn('[ ! -f "${BEEPER_IMAGE}" ]', script)
        self.assertIn('Xvfb :98', script)
        self.assertIn('-screen 0 1920x1200x24', script)
        self.assertIn('xfwm4 --compositor=off', script)
        self.assertIn('xdotool windowsize "${BEEPER_WINDOW}" 1840 1120', script)
        self.assertIn('"${WM_PID}"', script)
        self.assertIn('-nolisten tcp', script)
        self.assertIn('x11vnc -display :98 -localhost', script)
        self.assertIn('websockify --web=/browser_novnc 127.0.0.1:9011 127.0.0.1:5901', script)
        self.assertNotIn('remote-debugging-port', script)
        self.assertNotIn('install desktop', script)

    def test_beeper_screen_is_only_exposed_through_ingress(self):
        nginx = (ROOT / 'nginx.conf').read_text(encoding='utf-8')
        config = (ROOT / 'config.yaml').read_text(encoding='utf-8')
        dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('location /beeper/', nginx)
        self.assertIn('proxy_pass http://127.0.0.1:9011/', nginx)
        self.assertIn('allow 172.30.32.2;', nginx)
        self.assertIn('deny all;', nginx)
        self.assertIn("window.location.pathname.split('/').slice(1,-1).join('/') + '/websockify'", nginx)
        self.assertIn('Beeper Linux', nginx)
        self.assertNotIn('5901/tcp', config)
        self.assertNotIn('9011/tcp', config)
        self.assertNotIn('19375', config)
        expose = next(line for line in dockerfile.splitlines() if line.startswith('EXPOSE '))
        self.assertNotIn('5901', expose)
        self.assertNotIn('9011', expose)
        self.assertNotIn('19375', expose)

    def test_existing_options_default_beeper_on(self):
        startup = (ROOT / 'run.sh').read_text(encoding='utf-8')
        self.assertIn("jq -r '.beeper_enabled // true'", startup)
        self.assertIn('/usr/local/bin/hermes-beeper-desktop', startup)


if __name__ == '__main__':
    unittest.main()
