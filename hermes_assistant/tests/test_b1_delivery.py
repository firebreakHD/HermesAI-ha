import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'b1' / 'apply.py'
SOURCE = Path(os.environ.get('B1_TEST_WEBUI_SOURCE', '/data/hermes/webui-app'))


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / 'webui-app'
        shutil.copytree(SOURCE, self.target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

    def run_patch(self, update=False):
        return subprocess.run(['python3', str(SCRIPT), str(self.target), '--update' if update else '--no-update'],
                              capture_output=True, text=True)

    def test_clean_installed_commit_accepts_patch_and_reapplication(self):
        subprocess.run(['git', '-C', str(self.target), 'restore', 'api/auth.py', 'server.py'], check=True)
        for name in ('api/ha_person.py', 'tests/test_ha_person_assignment.py'):
            (self.target / name).unlink()
        first = self.run_patch()
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_patch()
        self.assertEqual(second.returncode, 0, second.stderr)

    def test_different_git_abbreviation_does_not_invalidate_identical_patch(self):
        subprocess.run(['git', '-C', str(self.target), 'config', 'core.abbrev', '8'], check=True)
        self.assertEqual(self.run_patch().returncode, 0)

    def test_installed_dirty_b1_is_idempotent(self):
        first = self.run_patch()
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_patch()
        self.assertEqual(second.returncode, 0, second.stderr)

    def test_incompatible_checkout_fails_closed_without_modification(self):
        (self.target / 'server.py').write_text('incompatible\n')
        result = self.run_patch()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.target / 'server.py').read_text(), 'incompatible\n')

    def test_compatible_upstream_is_patched_before_swap(self):
        subprocess.run(['git', '-C', str(self.target), 'restore', 'api/auth.py', 'server.py'], check=True)
        for name in ('api/ha_person.py', 'tests/test_ha_person_assignment.py'):
            (self.target / name).unlink()
        upstream = Path(self.tmp.name) / 'upstream'
        shutil.copytree(self.target, upstream)
        subprocess.run(['git', '-C', str(upstream), 'checkout', '-B', 'master'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.target), 'remote', 'set-url', 'origin', str(upstream)], check=True)
        result = self.run_patch(update=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.target / 'api/ha_person.py').exists())
        self.assertTrue(self.target.with_name('webui-app.b1-previous').exists())

    def test_incompatible_upstream_does_not_replace_installed_checkout(self):
        subprocess.run(['git', '-C', str(self.target), 'restore', 'api/auth.py', 'server.py'], check=True)
        for name in ('api/ha_person.py', 'tests/test_ha_person_assignment.py'):
            (self.target / name).unlink()
        upstream = Path(self.tmp.name) / 'upstream'
        shutil.copytree(self.target, upstream)
        subprocess.run(['git', '-C', str(upstream), 'checkout', '-B', 'master'], check=True, capture_output=True)
        (upstream / 'server.py').write_text('incompatible upstream\n')
        subprocess.run(['git', '-C', str(upstream), 'add', 'server.py'], check=True)
        subprocess.run(['git', '-C', str(upstream), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        'commit', '-m', 'incompatible'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.target), 'remote', 'set-url', 'origin', str(upstream)], check=True)
        before = (self.target / 'server.py').read_bytes()
        result = self.run_patch(update=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.target / 'server.py').read_bytes(), before)
        self.assertFalse(self.target.with_name('webui-app.b1-previous').exists())

    def test_unrelated_dirty_file_blocks_update_without_discarding_changes(self):
        file = self.target / 'requirements.txt'
        file.write_text(file.read_text() + '\n# local\n')
        result = self.run_patch(update=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('# local', file.read_text())


if __name__ == '__main__':
    unittest.main()
