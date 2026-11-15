"""Prevent mislabelled or secret-bearing CI archives before any release write."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.publish_ci_package import create_archive, verify_kit

SHA = 'a' * 40


class CIPackageArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'kit'
        self.root.mkdir()
        self.metadata = {'source_commit': SHA, 'includes_company_data': False,
                         'company_acceptance_complete': False, 'includes_images': False}
        self.write_release()
        (self.root / 'source-files.json').write_text('[]')
        with zipfile.ZipFile(self.root / 'source.zip', 'w') as archive:
            archive.writestr('app.py', 'print("synthetic")')
        self.checksums()

    def write_release(self):
        (self.root / 'release.json').write_text(json.dumps(self.metadata))

    def checksums(self):
        records = [{'path': p.name, 'bytes': p.stat().st_size,
                    'sha256': hashlib.sha256(p.read_bytes()).hexdigest().upper()}
                   for p in self.root.iterdir() if p.name != 'checksums.json']
        (self.root / 'checksums.json').write_text(json.dumps(records))

    def test_valid_kit_archive_preserves_exact_manifest_bytes(self):
        output = Path(self.temp.name) / 'delivery.zip'
        create_archive(self.root, output, SHA)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read('release.json'), (self.root / 'release.json').read_bytes())
            self.assertEqual(set(archive.namelist()), {p.name for p in self.root.iterdir()})

    def test_different_commit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'commit mismatch'):
            verify_kit(self.root, 'b' * 40)

    def test_company_payload_or_acceptance_claim_is_rejected(self):
        for key in ('includes_company_data', 'company_acceptance_complete'):
            with self.subTest(key=key):
                original = dict(self.metadata)
                self.metadata[key] = True
                self.write_release()
                with self.assertRaisesRegex(ValueError, 'company-data-free'):
                    verify_kit(self.root, SHA)
                self.metadata = original

    def test_changed_source_is_rejected_before_upload(self):
        with (self.root / 'source.zip').open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'size mismatch'):
            verify_kit(self.root, SHA)

    def test_unlisted_env_file_is_rejected(self):
        (self.root / '.env').write_text('synthetic-secret')
        with self.assertRaisesRegex(ValueError, 'Unlisted'):
            verify_kit(self.root, SHA)

    def test_listed_source_secret_is_rejected(self):
        with zipfile.ZipFile(self.root / 'source.zip', 'a') as archive:
            archive.writestr('.env', 'synthetic-secret')
        self.checksums()
        with self.assertRaisesRegex(ValueError, 'Runtime material'):
            verify_kit(self.root, SHA)

    def test_listed_runtime_secret_is_rejected(self):
        (self.root / '.env').write_text('synthetic-secret')
        self.checksums()
        with self.assertRaisesRegex(ValueError, 'Runtime material'):
            verify_kit(self.root, SHA)

    def test_traversal_inventory_is_rejected(self):
        (self.root / 'checksums.json').write_text('[{"path":"../outside"}]')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            verify_kit(self.root, SHA)

    def test_archive_cannot_be_created_inside_kit(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            create_archive(self.root, self.root / 'delivery.zip', SHA)
