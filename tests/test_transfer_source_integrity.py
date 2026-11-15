"""Release bytes must belong to the advertised commit, even in a dirty checkout."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from scripts.build_transfer_kit import build, git_snapshot


class TransferSourceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.test')
        self.git('config', 'user.name', 'Release fixture')
        paths = ['transfer/01-Inspect-Server.ps1', 'transfer/README-fa.md',
                 'docs/General_Debug_20261112.md', 'docs/Completion_Validation_20261113.md',
                 'docs/Traccar_Bridge_Handoff_20261113.md', 'docs/Software_Finalization_20261114.md']
        for name in paths:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('committed ' + name + '\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Fixture release')
        self.snapshot = git_snapshot(self.root)

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True).strip()

    def output(self):
        return Path(self.temp.name) / 'kit'

    def test_staged_changes_do_not_change_advertised_commit_inventory(self):
        (self.root / 'transfer/README-fa.md').write_text('uncommitted staged content')
        self.git('add', '.')
        self.assertEqual(git_snapshot(self.root), self.snapshot)

    def test_dirty_and_untracked_tools_cannot_enter_release(self):
        (self.root / 'transfer/01-Inspect-Server.ps1').write_text('uncommitted tool')
        (self.root / 'transfer/untracked.ps1').write_text('untracked tool')
        (self.root / 'docs/General_Debug_20261112.md').write_text('uncommitted report')
        build(self.root, self.snapshot, self.output(), Path(self.temp.name) / 'absent')
        with zipfile.ZipFile(self.output() / 'source.zip') as archive:
            for name in ('transfer/01-Inspect-Server.ps1', 'docs/General_Debug_20261112.md'):
                self.assertEqual((self.output() / Path(name).name).read_bytes(), archive.read(name))
        self.assertFalse((self.output() / 'untracked.ps1').exists())
        for record in json.loads((self.output() / 'checksums.json').read_text()):
            self.assertEqual(record['sha256'], hashlib.sha256(
                (self.output() / record['path']).read_bytes()).hexdigest().upper())

    def test_snapshot_cannot_mislabel_content_from_another_commit(self):
        (self.root / 'transfer/README-fa.md').write_text('next version')
        self.git('add', '.')
        self.git('commit', '-qm', 'Next version')
        forged = git_snapshot(self.root)
        forged['commit'] = self.snapshot['commit']
        with self.assertRaisesRegex(ValueError, 'commit'):
            build(self.root, forged, self.output(), Path(self.temp.name) / 'absent')
        self.assertFalse(self.output().exists())

    def test_historical_validation_is_not_current_release_evidence(self):
        historical = self.root / 'transfer/validation/summary.json'
        historical.parent.mkdir()
        historical.write_text('{"passed": true, "tests": 999}')
        self.git('add', '.')
        self.git('commit', '-qm', 'Historical evidence')
        build(self.root, git_snapshot(self.root), self.output())
        self.assertFalse((self.output() / 'validation/summary.json').exists())
        scope = json.loads((self.output() / 'validation/kit-scope.json').read_text())
        self.assertFalse(scope['evidence_explicitly_supplied'])
        self.assertFalse(scope['company_acceptance_complete'])


if __name__ == '__main__':
    unittest.main()
