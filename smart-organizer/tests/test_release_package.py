import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from build_release import FILES, build
from update_checker import _verify_zip


class ReleasePackageTests(unittest.TestCase):
    def test_source_release_contains_required_files_and_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in FILES:
                (root / name).write_text("VERSION = '1.1.1'" if name == 'smart_organizer.pyw' else 'test')
            target = build(root, '1.1.1', include_exe=False)
            with zipfile.ZipFile(target) as z:
                self.assertEqual(set(z.namelist()), set(FILES))
            _verify_zip(target.read_bytes())
            digest = target.with_name(target.name + '.sha256').read_text().split()[0]
            self.assertEqual(digest, hashlib.sha256(target.read_bytes()).hexdigest())

    def test_tag_version_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'smart_organizer.pyw').write_text("VERSION = '1.1.1'")
            with self.assertRaisesRegex(ValueError, 'differ'):
                build(root, '1.2.0', include_exe=False)


if __name__ == '__main__':
    unittest.main()
