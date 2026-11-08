import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from file_recovery import create_bundle,restore_bundle


class FileRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='qa-file-recovery-',dir=Path(__file__).resolve().parents[1]);self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.sources={'team_chat':self.root/'chat','catalog_uploads':self.root/'catalog'}
        self.sources['catalog_uploads'].mkdir()
        (self.sources['catalog_uploads']/'نمونه.pdf').write_bytes(b'%PDF-synthetic')
        self.archive=self.root/'backup.zip'

    def test_private_backup_and_fresh_restore_keep_bytes_and_missing_root(self):
        manifest=create_bundle(self.sources,self.archive)
        self.assertFalse(manifest['roots']['team_chat']['exists'])
        restore_bundle(self.archive,self.root/'restored')
        self.assertEqual((self.root/'restored/catalog_uploads/نمونه.pdf').read_bytes(),b'%PDF-synthetic')

    def test_existing_backup_and_existing_destination_are_never_overwritten(self):
        create_bundle(self.sources,self.archive)
        before=self.archive.read_bytes()
        with self.assertRaises(ValueError):create_bundle(self.sources,self.archive)
        self.assertEqual(self.archive.read_bytes(),before)
        with self.assertRaises(ValueError):restore_bundle(self.archive,self.sources['catalog_uploads'])

    def test_corruption_is_rejected_before_creating_destination(self):
        create_bundle(self.sources,self.archive)
        bad=self.root/'bad.zip'
        with zipfile.ZipFile(self.archive) as source,zipfile.ZipFile(bad,'w') as target:
            for name in source.namelist():target.writestr(name,b'corrupt' if name!='manifest.json' else source.read(name))
        with self.assertRaises(ValueError):restore_bundle(bad,self.root/'restore-bad')
        self.assertFalse((self.root/'restore-bad').exists())

    def test_traversal_and_extra_members_are_rejected(self):
        manifest=create_bundle(self.sources,self.archive)
        for key in ('../escape','catalog_uploads/../../escape','catalog_uploads/..\\escape','C:/escape'):
            bad=self.root/'bad.zip'
            manifest['files'][0]['path']=key
            with zipfile.ZipFile(bad,'w') as target:
                target.writestr('manifest.json',json.dumps(manifest));target.writestr(key,b'synthetic')
            with self.assertRaises(ValueError):restore_bundle(bad,self.root/'restore-bad')
        self.assertFalse((self.root/'escape').exists())

    def test_unlisted_extra_file_is_rejected(self):
        create_bundle(self.sources,self.archive)
        with zipfile.ZipFile(self.archive,'a') as target:target.writestr('unexpected',b'x')
        with self.assertRaises(ValueError):restore_bundle(self.archive,self.root/'restore-bad')

    def test_existing_partial_and_source_files_are_preserved(self):
        partial=self.archive.with_suffix('.zip.partial');partial.write_bytes(b'previous backup')
        with self.assertRaises(FileExistsError):create_bundle(self.sources,self.archive)
        self.assertEqual(partial.read_bytes(),b'previous backup')
        self.assertEqual((self.sources['catalog_uploads']/'نمونه.pdf').read_bytes(),b'%PDF-synthetic')

    def test_archive_cannot_be_created_inside_a_source_tree(self):
        with self.assertRaises(ValueError):create_bundle(self.sources,self.sources['catalog_uploads']/'backup.zip')
