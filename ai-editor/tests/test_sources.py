# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.2 - kaynak belgeler testleri (ag gerektirmez)."""
import email.message
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
TMP = tempfile.mkdtemp(prefix='agfo-src-test-')
os.environ.setdefault('LOCALAPPDATA', TMP)

import agfo_editor_core as core  # noqa: E402
import agfo_sources as srcs  # noqa: E402


def make_pdf(path, pages):
    """Elle yazilmis kucuk bir PDF (Helvetica, ASCII metin, her sayfada satirlar)."""
    objs = ['<< /Type /Catalog /Pages 2 0 R >>', None, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids = []
    for lines in pages:
        content = 'BT /F1 11 Tf 50 780 Td 14 TL ' + ' '.join('(%s) Tj T*' % l.replace('(', '\\(').replace(')', '\\)') for l in lines) + ' ET'
        objs.append('<< /Length %d >>\nstream\n%s\nendstream' % (len(content), content))
        cid = len(objs)
        objs.append('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>' % cid)
        kids.append('%d 0 R' % len(objs))
    objs[1] = '<< /Type /Pages /Kids [%s] /Count %d >>' % (' '.join(kids), len(kids))
    out = b'%PDF-1.4\n'
    offs = []
    for i, o in enumerate(objs, start=1):
        offs.append(len(out))
        out += ('%d 0 obj\n%s\nendobj\n' % (i, o)).encode('latin-1')
    x = len(out)
    out += ('xref\n0 %d\n0000000000 65535 f \n' % (len(objs) + 1)).encode()
    for o in offs:
        out += ('%010d 00000 n \n' % o).encode()
    out += ('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objs) + 1, x)).encode()
    pathlib.Path(path).write_bytes(out)


def make_xlsx(path):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   '<sheet name="Bulgular" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/sharedStrings.xml', '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<si><t>Madde</t></si><si><t>Bulgu</t></si><si><t>Soğuk oda sıcaklık kaydı eksik</t></si></sst>')
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                   '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                   '<row r="2"><c r="A2"><v>4.11</v></c><c r="B2" t="s"><v>2</v></c></row></sheetData></worksheet>')


def make_pptx(path):
    a = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    with zipfile.ZipFile(path, 'w') as z:
        for n, txt in ((1, 'Alerjen yönetimi'), (2, 'Çapraz bulaşma kontrolü'), (10, 'Sonuç')):
            z.writestr('ppt/slides/slide%d.xml' % n, '<p:sld xmlns:p="x" xmlns:a="%s"><a:p><a:r><a:t>%s</a:t></a:r></a:p></p:sld>' % (a, txt))
        z.writestr('ppt/notesSlides/notesSlide2.xml', '<n xmlns:a="%s"><a:p><a:r><a:t>Temizlik doğrulaması anlatılacak</a:t></a:r></a:p></n>' % a)


class ExtractTests(unittest.TestCase):
    def test_pdf_pages_and_empty_page(self):
        p = os.path.join(TMP, 'std.pdf')
        make_pdf(p, [['Clause 4.11.2 Cleaning procedures', 'Cleaning shall be validated.'], [], ['Clause 5.3 Allergen management']])
        d = srcs.extract(p)
        self.assertEqual([u['loc'] for u in d['units']], ['s. 1', 's. 2', 's. 3'])
        self.assertIn('4.11.2', d['units'][0]['text'])
        self.assertEqual(d['empty_pages'], [2])

    def test_encrypted_pdf_permissions(self):
        import pypdf
        from pypdf.constants import UserAccessPermissions as U
        src = os.path.join(TMP, 'aes-src.pdf')
        make_pdf(src, [['Hazard analysis', 'CCP']])
        for flags, ok in ((U.PRINT | U.EXTRACT_TEXT_AND_GRAPHICS, True), (U.PRINT, False)):
            w = pypdf.PdfWriter(clone_from=src)
            w.encrypt(user_password='', owner_password='o', algorithm='AES-128', permissions_flag=flags)
            dst = os.path.join(TMP, 'aes-%d.pdf' % int(flags))
            with open(dst, 'wb') as f:
                w.write(f)
            if ok:
                self.assertIn('Hazard analysis', srcs.read_pdf(dst)[0]['text'])
            else:
                with self.assertRaises(srcs.SourceError) as cm:
                    srcs.read_pdf(dst)
                self.assertIn('izin vermiyor', str(cm.exception))

    def test_office_and_text_formats(self):
        x = os.path.join(TMP, 'b.xlsx')
        make_xlsx(x)
        d = srcs.extract(x)
        self.assertEqual(d['units'][0]['loc'], 'sayfa "Bulgular"')
        self.assertIn('4.11 | Soğuk oda sıcaklık kaydı eksik', d['units'][0]['text'])
        pp = os.path.join(TMP, 'c.pptx')
        make_pptx(pp)
        d = srcs.extract(pp)
        self.assertEqual([u['loc'] for u in d['units']], ['slayt 1', 'slayt 2', 'slayt 10'])
        self.assertIn('Konuşmacı notu: Temizlik doğrulaması', d['units'][1]['text'])
        w = os.path.join(TMP, 'd.docx')
        core.write_docx(w, '# Giriş\n\nBirinci bölüm metni.\n\n# Kapsam\n\nİkinci bölüm.')
        d = srcs.extract(w)
        self.assertEqual([u['loc'] for u in d['units']], ['Giriş', 'Kapsam'])
        c = os.path.join(TMP, 'e.csv')
        pathlib.Path(c).write_text('Madde;Durum\n4.1;Uygun\n4.2;Uygunsuz\n', encoding='utf-8')
        self.assertIn('4.2 | Uygunsuz', srcs.extract(c)['units'][0]['text'])
        m = email.message.EmailMessage()
        m['From'], m['Subject'] = 'denetci@agfo.test', 'Rapor'
        m.set_content('Ekteki raporu inceleyin.')
        m.add_attachment(b'x', maintype='application', subtype='pdf', filename='rapor.pdf')
        e = os.path.join(TMP, 'f.eml')
        pathlib.Path(e).write_bytes(bytes(m))
        t = srcs.extract(e)['units'][0]['text']
        self.assertIn('Subject: Rapor', t)
        self.assertIn('Ekler: rapor.pdf', t)
        with self.assertRaises(srcs.SourceError):
            srcs.extract(os.path.join(TMP, 'x.exe')) if pathlib.Path(TMP, 'x.exe').write_bytes(b'MZ') else None
        bad = os.path.join(TMP, 'bad.docx')
        pathlib.Path(bad).write_bytes(b'not a zip')
        with self.assertRaises(srcs.SourceError):
            srcs.extract(bad)

    def test_cache(self):
        p = os.path.join(TMP, 'cache.txt')
        pathlib.Path(p).write_text('ilk sürüm', encoding='utf-8')
        self.assertEqual(srcs.load(p)['units'][0]['text'], 'ilk sürüm')
        with mock.patch.object(srcs, 'extract', side_effect=AssertionError('cache miss')):
            self.assertEqual(srcs.load(p)['units'][0]['text'], 'ilk sürüm')
        time.sleep(1.1)
        pathlib.Path(p).write_text('ikinci sürüm', encoding='utf-8')
        self.assertEqual(srcs.load(p)['units'][0]['text'], 'ikinci sürüm')


class SearchTests(unittest.TestCase):
    def test_normalize_turkish(self):
        self.assertEqual(srcs.normalize('İSTANBUL Isparta'), ['istan', 'ıspar'])
        self.assertEqual(srcs.normalize('alerjenlerin')[0], srcs.normalize('Alerjen')[0])
        self.assertIn('4.11.2', srcs.normalize('Madde 4.11.2 gereği'))
        self.assertNotIn('ve', srcs.normalize('temizlik ve dezenfeksiyon'))

    def _docs(self, n=40):
        filler = 'Genel gereklilikler ve yönetim taahhüdü hakkında açıklama metni. ' * 20
        a = {'name': 'standart.pdf', 'units': [{'loc': 's. %d' % i, 'page': i, 'text': filler} for i in range(1, n)]
             + [{'loc': 's. %d' % n, 'page': n, 'text': 'Madde 4.11.2: Temizlik prosedürleri doğrulanmalı ve kayıt altına alınmalıdır.'}]}
        b = {'name': 'rapor.docx', 'units': [{'loc': 'Bulgular', 'page': None, 'text': 'Temizlik doğrulaması yapılmamış. ' + filler}]}
        for d in (a, b):
            d['chars'] = sum(len(u['text']) for u in d['units'])
        return {'a': a, 'b': b}

    def test_index_ranks_relevant(self):
        docs = self._docs()
        chunks = srcs.chunk_units('a', docs['a'])
        top = srcs.Index(chunks).search('temizlik prosedürü doğrulama 4.11.2', k=3)
        self.assertEqual(top[0]['loc'], 's. 40')

    def test_select_context(self):
        small = {'x': {'name': 'k.txt', 'chars': 20, 'units': [{'loc': 'bölüm 1', 'page': None, 'text': 'kısa metin'}]}}
        ch, mode = srcs.select_context(small, 'herhangi')
        self.assertEqual((mode, len(ch)), ('tam', 1))
        docs = self._docs()
        ch, mode = srcs.select_context(docs, 'temizlik doğrulaması 4.11.2', budget=12000)
        self.assertEqual(mode, 'arama')
        self.assertLessEqual(sum(len(c['text']) for c in ch), 12000 + srcs.CHUNK_CHARS * 2)
        self.assertEqual({c['doc'] for c in ch}, {'a', 'b'})                # her belge temsil edilir
        self.assertTrue(any(c['loc'] == 's. 40' for c in ch))
        ch2, _ = srcs.select_context(docs, '', budget=12000)                  # sorgusuz uretim: dengeli ornek
        self.assertEqual({c['doc'] for c in ch2}, {'a', 'b'})

    def test_context_citations_mask(self):
        chunks = [{'doc': 'a', 'name': 'std.pdf', 'loc': 's. 3', 'page': 3, 'text': 'İletişim: ali@firma.com 0532 123 45 67'},
                  {'doc': 'b', 'name': 'r.docx', 'loc': 'Bulgular', 'page': None, 'text': 'TC 12345678901 IBAN TR12 0006 1005 1978 6457 8413 26'}]
        ctx, labels = srcs.build_context(chunks, mask=True)
        self.assertIn('[K1] std.pdf — s. 3', ctx)
        for secret in ('ali@firma.com', '0532 123 45 67', '12345678901', 'TR12'):
            self.assertNotIn(secret, ctx)
        self.assertIn('[e-posta]', ctx)
        ans = 'Doğrulama gerekir [K1]. Kayıt eksik [K2, K1]. Yok [K9].'
        self.assertEqual([lab for lab, _c in srcs.citations(ans, labels)], ['K1', 'K2'])
        out = srcs.append_source_list('## Başlık\n\nMetin [K2].', labels)
        self.assertTrue(out.endswith('## Kaynaklar\n- [K2] r.docx, Bulgular'))
        self.assertEqual(srcs.append_source_list('Atıfsız metin', labels), 'Atıfsız metin')

    def test_prompts(self):
        m = srcs.ask_message('4.11.2 ne der?', 'Türkçe')
        self.assertIn('<agfo_document>', m)
        self.assertIn('do not guess', m)
        self.assertTrue(m.endswith('Question: 4.11.2 ne der?'))
        c = srcs.create_message('checklist', 'Alerjen', 'English', 'Denetçi', 'kısa')
        self.assertIn('audit checklist', c)
        self.assertIn('Write in English', c)
        self.assertIn('Topic / goal set by the user: Alerjen', c)
        self.assertEqual(len({t[0] for t in srcs.CREATE_TYPES}), len(srcs.CREATE_TYPES))
        self.assertTrue(all(256 <= t[3] <= 8000 for t in srcs.CREATE_TYPES))


if __name__ == '__main__':
    unittest.main()
