"""2.7.0: sekme x, klasor sohbeti, denetim sohbeti, ust/alt bilgi tablolarinin korunmasi ve Word gorunumu."""
from __future__ import annotations

import io
import os
import pathlib
import sys
import tempfile
import time
import unittest
import zipfile
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
TMP = tempfile.mkdtemp(prefix='agfo-v27-')
os.environ['LOCALAPPDATA'] = TMP

import agfo_richdoc as rdoc  # noqa: E402
import agfo_sources as srcs  # noqa: E402

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00'
       b'\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82')
HDR_TABLE = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
             'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
             '<w:tbl><w:tblPr><w:tblStyle w:val="AgfoGrid"/></w:tblPr><w:tr><w:tc><w:p><w:r><w:drawing>'
             '<a:blip xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" r:embed="rIdLogo"/></w:drawing></w:r></w:p></w:tc>'
             '<w:tc><w:p><w:r><w:t>PROSEDUR PR-07</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:p/></w:hdr>')
HDR_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdLogo" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            'Target="media/image1.png"/></Relationships>')
STYLE = ('<w:style w:type="table" w:styleId="AgfoGrid"><w:name w:val="Agfo Grid"/><w:tblPr><w:tblBorders>'
         '<w:top w:val="single" w:sz="4"/></w:tblBorders></w:tblPr></w:style>')


def header_table_docx(path):
    """Ust bilgisinde tablo + logo olan Word belgesi (editorun kendi yazicisiyla baslayip ust bilgi degistirilir)."""
    page = rdoc.normalize_page({'header': 'PROSEDUR PR-07'})
    base = rdoc.docx_bytes([rdoc.para(text='Govde metni.')], page)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as zi, zipfile.ZipFile(out, 'w') as zo:
        for item in zi.infolist():
            data = zi.read(item.filename)
            if item.filename == 'word/header1.xml':
                data = HDR_TABLE.encode('utf-8')
            elif item.filename == 'word/styles.xml':
                data = data.replace(b'</w:styles>', STYLE.encode('utf-8') + b'</w:styles>')
            elif item.filename == '[Content_Types].xml':
                data = data.replace(b'</Types>', b'<Default Extension="png" ContentType="image/png"/></Types>') \
                    if b'Extension="png"' not in data else data
            zo.writestr(item, data)
        zo.writestr('word/_rels/header1.xml.rels', HDR_RELS)
        zo.writestr('word/media/image1.png', PNG)
    pathlib.Path(path).write_bytes(out.getvalue())
    return path


class HeaderFooterKeepTests(unittest.TestCase):
    def setUp(self):
        self.path = header_table_docx(os.path.join(tempfile.mkdtemp(dir=TMP), 'hf.docx'))

    def test_read_marks_complex_and_save_keeps_table_logo_and_styles(self):
        hf = rdoc.read_docx_hf(self.path)
        self.assertTrue(hf['complex'])
        self.assertEqual([r[0] for r in hf['refs']], ['header'])
        self.assertIn('word/media/image1.png', hf['media'])
        page = rdoc.read_docx_page(self.path)
        blocks = rdoc.read_docx_blocks(self.path) + [rdoc.para(text='Yeni paragraf.')]
        data = rdoc.docx_bytes(blocks, page, hf)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            hdr = next(n for n in names if n.startswith('word/header') and n.endswith('.xml'))
            self.assertIn(b'<w:tbl>', z.read(hdr))
            rels = z.read('word/_rels/%s.rels' % hdr.rsplit('/', 1)[1]).decode('utf-8')
            target = rels.split('Target="', 1)[1].split('"', 1)[0]
            self.assertIn('word/' + target, names)                      # logo yeni adiyla pakette
            self.assertEqual(z.read('word/' + target), PNG)
            self.assertIn(b'AgfoGrid', z.read('word/styles.xml'))       # tablo stili korunur
            self.assertIn(b'w:styleId="Heading1"', z.read('word/styles.xml'))   # editorun stilleri de var
            self.assertIn(b'Yeni paragraf.', z.read('word/document.xml'))
            self.assertIn(b'image/png', z.read('[Content_Types].xml'))
        again = os.path.join(os.path.dirname(self.path), 'again.docx')
        pathlib.Path(again).write_bytes(data)
        hf2 = rdoc.read_docx_hf(again)                                  # ikinci kayitta da korunur
        self.assertTrue(hf2['complex'])
        self.assertEqual(len(hf2['media']), 1)

    def test_edited_header_falls_back_to_text(self):
        hf = rdoc.read_docx_hf(self.path)
        page = rdoc.read_docx_page(self.path)
        page['header'] = 'Yeni ust bilgi'
        self.assertFalse(rdoc.hf_unchanged(page, hf))
        with zipfile.ZipFile(io.BytesIO(rdoc.docx_bytes([rdoc.para(text='x')], page, hf))) as z:
            hdr = z.read('word/header1.xml')
            self.assertNotIn(b'<w:tbl>', hdr)
            self.assertIn(b'Yeni ust bilgi', hdr)

    def test_plain_document_has_no_hf(self):
        p = os.path.join(os.path.dirname(self.path), 'plain.docx')
        pathlib.Path(p).write_bytes(rdoc.docx_bytes([rdoc.para(text='x')]))
        self.assertIsNone(rdoc.read_docx_hf(p))


class FolderScanTests(unittest.TestCase):
    def test_scan_walks_subfolders_and_skips_temp_hidden_unsupported(self):
        root = tempfile.mkdtemp(dir=TMP)
        for rel, body in (('a.txt', 'Alerjen planı.'), ('Alt/b.md', '# HACCP'), ('Alt/Derin/c.csv', 'x,y\n1,2'),
                          ('~$gecici.docx', 'x'), ('.gizli/d.txt', 'x'), ('resim.jpg', 'x'), ('node_modules/e.txt', 'x')):
            p = os.path.join(root, *rel.split('/'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            pathlib.Path(p).write_text(body, encoding='utf-8')
        paths, skipped = srcs.scan_folder(root)
        rels = sorted(srcs.rel_name(p, root).split('/', 1)[1] for p in paths)
        self.assertEqual(rels, ['Alt/Derin/c.csv', 'Alt/b.md', 'a.txt'])
        self.assertEqual(skipped['temp'], 1)
        self.assertEqual(skipped['type'], 1)
        self.assertTrue(srcs.rel_name(paths[0], root).startswith(os.path.basename(root) + '/'))
        paths, skipped = srcs.scan_folder(root, max_files=2)
        self.assertEqual((len(paths), skipped['limit']), (2, 1))

    def test_inventory_fits_budget_with_hundreds_of_documents(self):
        docs = {'d%d' % i: {'name': 'Klasor/belge%03d.docx' % i, 'kind': 'docx', 'chars': 5000, 'path': 'p%d' % i,
                            'units': [{'loc': 's.1', 'page': 1, 'text': 'Prosedür metni %d. ' % i * 200}]} for i in range(300)}
        text, labels = srcs.inventory_context(docs)
        self.assertLess(len(text), srcs.CONTEXT_BUDGET + 2500)
        self.assertEqual(len(labels), 300)
        self.assertIn('belge299.docx', text)
        chunks, mode = srcs.select_context(docs, 'Prosedür 17')          # yuzlerce belge: her belgeden parca zorlanmaz
        self.assertEqual(mode, 'arama')
        self.assertLessEqual(sum(len(c['text']) for c in chunks), srcs.CONTEXT_BUDGET + srcs.CHUNK_CHARS)


def _display():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(_display(), 'ekran gerekli')
class GuiV27Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('agfo_ai_editor', str(SRC / 'agfo_ai_editor.pyw'))
        spec = importlib.util.spec_from_loader('agfo_ai_editor', loader)
        cls.m = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.m)

    def setUp(self):
        self.app = self.m.App(smoke=True)
        self.app.geometry('1200x800')
        self.app.update()
        self.calls = []

    def tearDown(self):
        self.app.destroy()

    def pump(self, until=lambda: False, n=400):
        for _ in range(n):
            self.app.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def fake_ai(self, answer='Yanıt [K1].'):
        def fake(backends, fn, *args):
            self.calls.append((fn, args))
            return {'text': answer, 'via': 'Test', 'model': 'test-model'}
        return mock.patch.multiple(self.m.ai, run_with_fallback=fake), mock.patch.object(self.app, 'backends', return_value=[])

    def test_tab_close_button(self):
        self.assertEqual(self.app.nb.cget('style'), 'Docs.TNotebook')
        a = self.app.new_doc('bir', 'A')
        a.text.undo.mark_saved()
        self.app.new_doc('iki', 'B')
        self.pump(n=10)
        idx = self.app.nb.index(a.frame)
        spot = None
        for y in range(2, 40):
            for x in range(0, 700):
                if 'agfoclose' in self.app.nb.identify(x, y) and self.app.nb.index('@%d,%d' % (x, y)) == idx:
                    spot = (x, y)
                    break
            if spot:
                break
        self.assertIsNotNone(spot, 'sekmede x yok')

        class E:
            x, y = spot
        self.assertEqual(self.app._tab_x_press(E), 'break')
        self.app._tab_x_release(E)
        self.assertNotIn(a, self.app.docs)                              # kaydedilmis: sormadan kapandi
        self.assertIsNone(self.app._tab_x_press(type('E', (), {'x': 1, 'y': 300})))   # x disi: normal tiklama

    def test_folder_sources_scope_and_analysis(self):
        root = tempfile.mkdtemp(dir=TMP)
        os.makedirs(os.path.join(root, 'Alt'))
        pathlib.Path(root, 'plan.txt').write_text('Alerjen yönetim planı: susam ayrı depolanır.', encoding='utf-8')
        pathlib.Path(root, 'Alt', 'egitim.md').write_text('# Eğitim\nPersonel alerjen eğitimi aldı.', encoding='utf-8')
        fid = self.app.add_source_folder(root)
        self.assertTrue(self.pump(lambda: len(self.app.src_docs) == 2 and not self.app.jobs))
        tree = self.app.src_tree
        self.assertEqual(len(tree.get_children(fid)), 2)
        self.assertIn(root, self.app.settings['source_folders'])
        self.assertEqual(self.app.settings['sources'], [])
        names = sorted(d['name'] for d in self.app.src_docs.values())
        self.assertEqual(names, sorted([os.path.basename(root) + '/Alt/egitim.md', os.path.basename(root) + '/plan.txt']))
        tree.selection_set(fid)
        self.pump(n=5)
        self.assertEqual(set(self.app._scope_ids()), set(tree.get_children(fid)))
        p1, p2 = self.fake_ai('Klasörde iki belge var [K1] [K2].')
        with p1, p2:
            self.app.analyze_sources()
            self.assertTrue(self.pump(lambda: not self.app.jobs))
        fn, args = self.calls[-1]
        self.assertEqual(fn, 'chat')
        self.assertIn('Folder inventory: 2 documents.', args[1])
        self.assertIn('Klasörde iki belge var', self.app.src_view.get('1.0', 'end'))
        self.app.remove_sources()                                       # klasor secili: icindekilerle birlikte
        self.assertEqual(self.app.src_docs, {})
        self.assertEqual(self.app.settings['source_folders'], [])

    def test_audit_is_a_chat_and_does_not_stop_without_editable_document(self):
        p1, p2 = self.fake_ai('Observation: no record of allergen training.\nEksik kanıt / dikkat: eğitim kaydı.')
        with p1, p2:
            for d in list(self.app.docs):
                self.app.close_doc(d, ask=False)
            self.app.audit_in.insert('1.0', 'Personel alerjen eğitimi almamış, kayıt yok.')
            self.app.run_audit()                                         # belge yok: yazilan metin denetlenir
            self.assertTrue(self.pump(lambda: not self.app.jobs))
            self.assertIn('no record', self.app.audit_view.get('1.0', 'end'))
            self.assertIn('uygulanamıyor', self.app.audit_view.get('1.0', 'end'))
            self.assertEqual(str(self.app.audit_apply_btn.cget('state')), 'disabled')
            self.app.audit_to_tab()                                      # yeni sekmede kullanilir
            self.assertTrue(self.app.cur().title.startswith('✔ '))
            # duzenlenebilir belge: tur baslar, soru ayni belgeyle surer, belgeye uygulanabilir
            self.app.clear_audit()
            d = self.app.new_doc('Depoda susam ayrı rafta tutuluyor. Etiket yok.', 'Kanit')
            self.app.run_audit()
            self.assertTrue(self.pump(lambda: not self.app.jobs))
            first = self.calls[-1][1]
            self.assertIn('susam', first[1])                             # belge metni baglamda
            self.assertIn('Task:', first[0][-1]['content'])
            self.assertEqual(str(self.app.audit_apply_btn.cget('state')), 'normal')
            self.app.audit_in.insert('1.0', 'Bu bulgu major mı?')
            self.app.run_audit()
            self.assertTrue(self.pump(lambda: not self.app.jobs))
            follow = self.calls[-1][1]
            self.assertEqual(follow[0][-1]['content'], 'Bu bulgu major mı?')
            self.assertEqual(len(follow[0]), 3)                          # gecmis + yeni soru
            self.assertIn('susam', follow[1])                            # ayni belge
            with mock.patch.object(self.app, 'review') as rv:
                self.app.apply_audit()
            rv.assert_called_once()
            self.assertIs(rv.call_args[0][0], d)

    def test_audit_uses_sources_with_citations_and_ignores_empty_tab(self):
        src = os.path.join(tempfile.mkdtemp(dir=TMP), 'egitim_kaydi.txt')
        pathlib.Path(src).write_text('Alerjen eğitimi 12.03.2026 tarihinde 14 personele verildi. Katılım formu imzalı.',
                                     encoding='utf-8')
        self.app._load_sources([src])
        self.assertTrue(self.pump(lambda: len(self.app.src_docs) == 1 and not self.app.jobs))
        for d in list(self.app.docs):
            self.app.close_doc(d, ask=False)
        self.app.new_doc('', 'Bos')                                      # bos sekme kanit sayilmaz
        self.app.std_var.set('IFS Food 8')
        self.app.clause_var.set('2.3.4.1')
        p1, p2 = self.fake_ai('Personel alerjen eğitimi almıştır [K1].')
        with p1, p2:
            self.app.run_audit()                                         # Otomatik: acik belge bos -> yalniz Kaynaklar
            self.assertTrue(self.pump(lambda: not self.app.jobs))
            fn, args = self.calls[-1]
            self.assertIn('[K1]', args[1])
            self.assertIn('EVIDENCE EXCERPTS', args[1])
            self.assertNotIn('AUDITED TEXT', args[1])
            self.assertIn('cite the label', args[0][-1]['content'])
            self.assertIn('IFS Food 8', args[0][-1]['content'])
            view = self.app.audit_view.get('1.0', 'end')
            self.assertIn('egitim_kaydi.txt', view)                      # atif baglanti olarak yazildi
            self.assertNotIn('Denetlenecek metin yok', view)
            self.assertTrue(self.app.audit_view.tag_ranges('cite'))
            # soru: ayni parcalar ayni etiketlerle gider
            self.app.audit_in.insert('1.0', 'Katılım kaydı var mı?')
            self.app.run_audit()
            self.assertTrue(self.pump(lambda: not self.app.jobs))
            self.assertIn('[K1] egitim_kaydi.txt', self.calls[-1][1][1])
            self.app.audit_to_tab()
            self.assertIn('Kaynaklar', self.app.cur().text.get('1.0', 'end'))   # kaynak listesi eklendi
            # yalniz Kaynaklar secili ama Kaynaklar bos: bilgi verir, istek gitmez
            self.app.src_docs.clear()
            self.app.clear_audit()
            self.app.audit_src.set(self.m.AUDIT_EVIDENCE[2])
            n = len(self.calls)
            self.app.run_audit()
            self.assertEqual(len(self.calls), n)
            self.assertIn('Kaynaklar\'da belge yok', self.app.audit_view.get('1.0', 'end'))

    def test_word_view_for_document_tab(self):
        from test_brcgs_wordview import FakeRenderer
        self.app._doc_renderer = FakeRenderer()
        path = header_table_docx(os.path.join(tempfile.mkdtemp(dir=TMP), 'hf.docx'))
        d = self.app.open_path(path)
        self.assertTrue(d.hf['complex'])
        self.assertIsNone(d.wordv)                                       # testte (smoke) kendiliginden acilmaz
        self.app.toggle_word_view(d)
        self.assertTrue(self.pump(lambda: d.wordv and not d.wordv['busy'] and d.wordv['view'].doc is not None))
        self.assertIn('kayıtlı dosya', d.wordv['status'].cget('text'))
        self.assertFalse(d.desk.winfo_ismapped())
        self.app.toggle_word_view(d)                                     # duzenlemeye don
        self.pump(n=5)
        self.assertIsNone(d.wordv)
        self.assertTrue(d.desk.winfo_ismapped())
        d.text.insert('end', ' Eklendi.')
        self.app.show_word_view(d)                                       # degisti: editordeki hali cizilir
        self.assertTrue(self.pump(lambda: d.wordv and not d.wordv['busy'] and d.wordv['view'].doc is not None))
        self.assertIn('kaydedilmemiş', d.wordv['status'].cget('text'))
        self.assertTrue(self.app._write(d, path))                        # kayit ust bilgi tablosunu korur
        with zipfile.ZipFile(path) as z:
            hdr = next(n for n in z.namelist() if n.startswith('word/header') and n.endswith('.xml'))
            self.assertIn(b'<w:tbl>', z.read(hdr))


if __name__ == '__main__':
    unittest.main()
