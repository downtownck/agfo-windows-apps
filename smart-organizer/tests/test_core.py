import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from organizer_core import (
    APP_FOLDER, TOPIC_FOLDERS, MoveJournal, classify, destination, execute_approved,
    validate_destination_root, create_topic_folders,
    sample_text, scan, valid_subfolder,
)


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.roots = {'Masaüstü': root / 'Desktop', 'Belgeler': root / 'Documents',
                      'Hedef': root / 'Work'}
        for p in self.roots.values():
            p.mkdir()
        self.journal = MoveJournal(root / 'state' / 'journal.db')

    def test_filenames_and_content(self):
        f = self.roots['Masaüstü'] / 'Invoice_2026.pdf'
        f.write_bytes(b'%PDF-file-placeholder')
        item = classify(f)
        self.assertEqual(item.category, 'Faturalar')
        self.assertGreater(item.confidence, 0.9)
        self.assertEqual(item.decision, 'Bekliyor')
        link = self.roots['Masaüstü'] / 'Firefox.lnk'
        link.write_text('dummy')
        self.assertEqual(classify(link).root, 'Masaüstü')
        self.assertEqual(classify(link).folder, 'İncelenecek')

    def test_docx_text_snippet(self):
        f = self.roots['Belgeler'] / 'belge.docx'
        with zipfile.ZipFile(f, 'w') as z:
            z.writestr('word/document.xml',
                       '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                       '<w:body><w:p><w:r><w:t>denetim raporu test</w:t></w:r></w:p></w:body></w:document>')
        self.assertIn('denetim raporu test', sample_text(f))
        self.assertEqual(classify(f).category, 'Denetimler')
        self.assertEqual(classify(f).folder, 'İncelenecek')

    def test_scan_skips_managed_link_and_metadata(self):
        base = self.roots['Masaüstü']
        (base / APP_FOLDER).mkdir()
        (base / 'desktop.ini').write_text('ignored')
        (base / 'readme.txt').write_text('hello')
        (base / 'shortcut.url').write_text('https://example.com')
        (base / 'nested').mkdir()
        (base / 'nested' / 'inside.txt').write_text('inside')
        (base / 'sym').symlink_to(base / 'readme.txt')
        results, errors = scan(self.roots, ['Masaüstü'])
        self.assertFalse(errors)
        self.assertEqual(sorted(item.path.name for item in results), ['nested', 'readme.txt', 'shortcut.url'])

    def test_custom_folder_validation(self):
        self.assertEqual(valid_subfolder('Denetim/BRCGS/2026'), 'Denetim/BRCGS/2026')
        for value in ('../Windows', 'C:/Windows', 'foo/../bar', '/absolute', 'CON', 'foo//bar', 'foo\\..\\bar'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                valid_subfolder(value)
        dest = destination(self.roots, 'Belgeler', 'Faturalar/2026', 'test.pdf')
        self.assertEqual(dest.parent.name, '2026')
        self.assertEqual(dest, self.roots['Hedef'] / 'Faturalar' / '2026' / 'test.pdf')
        self.assertNotIn(APP_FOLDER, str(dest))

    def test_approval_move_and_undo(self):
        file = self.roots['Masaüstü'] / 'contract_agreement.docx'
        file.write_text('confidential')
        item = classify(file, False)
        item.folder = 'ATECQ'  # Explicit user topic choice for generic file.
        item.decision = 'Kabul'
        done, errs, batch = execute_approved([item], self.roots, self.journal)
        self.assertEqual((done, errs), (1, []))
        self.assertFalse(file.exists())
        target = item.target(self.roots)
        self.assertTrue(target.exists())
        self.assertEqual(item.decision, 'Taşındı')
        count, errors = self.journal.undo(batch)
        self.assertEqual((count, errors), (1, []))
        self.assertTrue(file.exists())
        self.assertFalse(target.exists())
        self.assertIsNone(self.journal.latest_batch())

    def test_rejected_and_pending_are_not_moved(self):
        file = self.roots['Masaüstü'] / 'draft.txt'
        file.write_text('x')
        item = classify(file)
        for decision in ('Bekliyor', 'Red'):
            item.decision = decision
            count, errors, _ = execute_approved([item], self.roots, self.journal)
            self.assertEqual((count, errors), (0, []))
            self.assertTrue(file.exists())

    def test_collision_skips_without_overwrite(self):
        file = self.roots['Masaüstü'] / 'notes.txt'
        file.write_text('SOURCE')
        item = classify(file)
        item.folder = 'ATECQ'  # Explicit user topic choice for generic file.
        item.decision = 'Kabul'
        target = item.target(self.roots)
        target.parent.mkdir(parents=True)
        target.write_text('OLD DATA')
        done, errors, _ = execute_approved([item], self.roots, self.journal)
        self.assertEqual(done, 0)
        self.assertTrue(errors)
        self.assertEqual(target.read_text(), 'OLD DATA')
        self.assertEqual(file.read_text(), 'SOURCE')

    def test_changed_file_is_not_moved(self):
        file = self.roots['Masaüstü'] / 'notes.txt'
        file.write_text('ORIGINAL')
        item = classify(file)
        item.folder = 'ATECQ'  # Explicit user topic choice for generic file.
        item.decision = 'Kabul'
        file.write_text('CHANGED DATA')
        done, errors, _ = execute_approved([item], self.roots, self.journal)
        self.assertEqual(done, 0)
        self.assertTrue(errors)
        self.assertTrue(file.exists())

    def test_undo_preserves_conflicting_original(self):
        file = self.roots['Masaüstü'] / 'test.txt'
        file.write_text('A')
        item = classify(file)
        item.folder = 'ATECQ'  # Explicit user topic choice for generic file.
        item.decision = 'Kabul'
        _, _, batch = execute_approved([item], self.roots, self.journal)
        file.write_text('NEW')
        count, errors = self.journal.undo(batch)
        self.assertEqual(count, 0)
        self.assertTrue(errors)
        self.assertEqual(file.read_text(), 'NEW')
        self.assertTrue(item.target(self.roots).exists())


    def test_requires_explicit_destination_root(self):
        roots = {k: v for k, v in self.roots.items() if k != 'Hedef'}
        f = roots['Masaüstü'] / 'BRCGS_2026.pdf'
        f.write_text('sample')
        item = classify(f, False)
        item.decision = 'Kabul'
        with self.assertRaisesRegex(ValueError, 'Hedef kök klasörü seçilmedi'):
            item.target(roots)
        done, errors, _ = execute_approved([item], roots, self.journal)
        self.assertEqual(done, 0)
        self.assertTrue(errors)
        self.assertTrue(f.exists())

    def test_rejects_doc_cop_trash_and_source_root(self):
        trash = self.roots['Belgeler'].parent / 'DOC-COP' / 'Belgeler'
        trash.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'DOC-COP'):
            validate_destination_root(trash, self.roots)
        with self.assertRaisesRegex(ValueError, 'kendisini veya üst dizinini hedef'):
            validate_destination_root(self.roots['Belgeler'], self.roots)
        self.assertEqual(validate_destination_root(self.roots['Hedef'], self.roots), self.roots['Hedef'])

    def test_generic_file_is_not_moved_into_generic_folder(self):
        f = self.roots['Masaüstü'] / 'invoice_2026.pdf'
        f.write_bytes(b'%PDF')
        item = classify(f, False)
        self.assertEqual(item.category, 'Faturalar')
        self.assertEqual(item.folder, 'İncelenecek')
        item.decision = 'Kabul'
        done, errors, _ = execute_approved([item], self.roots, self.journal)
        self.assertEqual(done, 0)
        self.assertTrue(errors)
        self.assertTrue(f.exists())
        self.assertFalse((self.roots['Hedef'] / 'Faturalar').exists())

    def test_destination_inside_source_is_excluded_from_scan(self):
        dest = self.roots['Belgeler'] / 'AGFO'
        dest.mkdir()
        (dest / 'old.pdf').write_text('x')
        roots = dict(self.roots, Hedef=dest)
        (self.roots['Belgeler'] / 'BRCGS.pdf').write_text('x')
        items, _ = scan(roots, ['Belgeler'])
        self.assertEqual([it.path.name for it in items], ['BRCGS.pdf'])
        self.assertEqual(items[0].target(roots), dest / 'BRCGS' / 'BRCGS.pdf')

    def test_explicit_folder_creation_matches_handwritten_hierarchy(self):
        created = create_topic_folders(self.roots)
        self.assertEqual(len(created), 20)
        self.assertTrue((self.roots['Hedef'] / 'GLOBALGAP').is_dir())
        self.assertTrue((self.roots['Hedef'] / 'IAS').is_dir())
        self.assertTrue((self.roots['Hedef'] / 'ASI').is_dir())
        self.assertFalse((self.roots['Hedef'] / 'Belgeler').exists())
        self.assertFalse((self.roots['Hedef'] / 'Denetimler').exists())
        self.assertEqual(set(p.name for p in created), set(TOPIC_FOLDERS))


if __name__ == '__main__':
    unittest.main()
