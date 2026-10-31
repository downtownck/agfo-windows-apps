import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from organizer_core import CATEGORIES, classify, parse_ai_response, topical_folder, TOPIC_FOLDERS
from update_checker import check_release, download_verified, version_tuple


def release(tag, assets=True):
    base = f'https://github.com/downtownck/agfo-windows-apps/releases/download/{tag}/'
    name = f'AGFO-Smart-Organizer-v{tag.removeprefix("smart-organizer-v")}.zip'
    return {'tag_name': tag, 'draft': False, 'prerelease': False,
            'assets': [{'name': n, 'browser_download_url': base + n}
                       for n in (name, name + '.sha256')] if assets else []}


def fake_zip():
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        for name in ('organizer_core.py', 'smart_organizer.pyw', 'update_checker.py', 'GUNCELLE-KUR.ps1'):
            z.writestr(name, 'test')
    return out.getvalue()


class TopicAndUpdateTests(unittest.TestCase):
    def test_topics(self):
        cases = {'AGFO_ATeCQ_MOU.pdf': 'ATECQ', 'BRCGS Food Safety.pdf': 'BRCGS',
                 'AGFO_SP_Invoice.pdf': 'AGFO SP', 'IFS Food audit.pdf': 'IFS',
                 'CyberPanel-notes.txt': 'CYBERPANEL', 'panlektik.md': 'FELSEFE',
                 'novel-roman.txt': 'ROMAN', 'GLOBALG.A.P. Chain of Custody.pdf': 'GLOBALGAP',
                 'GLOBALGAP-audit.pdf': 'GLOBALGAP', 'GGAP-2026.xlsx': 'GLOBALGAP',
                 'IAS-accreditation.pdf': 'IAS', 'ASI-assessment.pdf': 'ASI'}
        for name, target in cases.items():
            with self.subTest(name=name):
                self.assertEqual(topical_folder(name), target)
        self.assertEqual(len(TOPIC_FOLDERS), 20)

    def test_globalgap_ias_asi_are_distinct(self):
        self.assertIn('GLOBALGAP', CATEGORIES)
        self.assertIn('IAS', CATEGORIES)
        self.assertNotEqual(topical_folder('IAS Accreditation 2026.pdf'),
                            topical_folder('ASI Accreditation 2026.pdf'))
        self.assertEqual(parse_ai_response('{"category":"GLOBALG.A.P."}')[0], 'GLOBALGAP')
        self.assertEqual(parse_ai_response('{"category":"IAS"}')[0], 'IAS')
        self.assertEqual(parse_ai_response('{"category":"ASI"}')[0], 'ASI')

    def test_classification_prefers_topic(self):
        with tempfile.TemporaryDirectory() as d:
            for name, expected in [('AGFO_ATeCQ_MOU.pdf', 'ATECQ'),
                                   ('GLOBALG.A.P. 2026.pdf', 'GLOBALGAP'),
                                   ('IAS Certificate.pdf', 'IAS')]:
                p = Path(d) / name
                p.write_bytes(b'%PDF-1.5\n')
                self.assertEqual(classify(p, include_content=False).folder, expected)

    def test_versions_and_release_asset_requirement(self):
        self.assertEqual(version_tuple('v1.1.0'), (1, 1, 0))
        self.assertIsNone(version_tuple('latest'))
        with patch('update_checker._read', return_value=json.dumps([release('smart-organizer-v1.2.0', False)]).encode()):
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                check_release('1.1.0')

    def test_only_smart_organizer_releases_count(self):
        items = [release('ai-editor-v9.9.9'), release('smart-organizer-v1.1.1'),
                 release('smart-organizer-v1.2.0'), release('smart-organizer-v1.3.0')]
        items[3]['draft'] = True
        with patch('update_checker._read', return_value=json.dumps(items).encode()):
            result = check_release('1.1.0')
            self.assertEqual(result['version'], '1.2.0')
        with patch('update_checker._read', return_value=json.dumps([release('ai-editor-v9.9.9')]).encode()):
            self.assertIsNone(check_release('1.1.0'))

    def test_download_checks_hash_and_zip_structure(self):
        data = fake_zip()
        release_info = {'sha_url': 'https://github.com/a', 'zip_url': 'https://github.com/b',
                        'name': 'update.zip'}
        with tempfile.TemporaryDirectory() as d:
            with patch('update_checker._read', side_effect=[hashlib.sha256(data).hexdigest().encode(), data]):
                p = download_verified(release_info, d)
            self.assertEqual(p.read_bytes(), data)
            self.assertTrue((Path(d) / 'update.zip.sha256').is_file())
            with patch('update_checker._read', side_effect=[b'0'*64, data]):
                with self.assertRaisesRegex(ValueError, 'SHA-256'):
                    download_verified(release_info, d)
            with patch('update_checker._read', side_effect=[hashlib.sha256(b'PK\x03\x04fake').hexdigest().encode(), b'PK\x03\x04fake']):
                with self.assertRaisesRegex(ValueError, 'ZIP'):
                    download_verified(release_info, d)


if __name__ == '__main__':
    unittest.main()
