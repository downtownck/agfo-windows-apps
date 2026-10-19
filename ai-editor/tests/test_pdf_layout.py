# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4.6 - form XObject icindeki metni duzenleme, sayfa duzeni cikarma ve duzeni koruyan PDF cevirisi."""
import os
import re
import pathlib
import sys
import tempfile
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
os.environ.setdefault('LOCALAPPDATA', tempfile.mkdtemp(prefix='agfo-pdflayout-test-'))

import agfo_pdf as P  # noqa: E402
import agfo_pdf_edit as E  # noqa: E402

try:
    import pypdf
    import pypdfium2 as pdfium
    import agfo_pdf_layout as L
    HAVE = E.pick_font() is not None
except ImportError:  # pragma: no cover
    HAVE = False

TMP = tempfile.mkdtemp(prefix='agfo-pdflayout-')

FORM = (b'BT /F1 30 Tf 0.19 0.35 0.3 rg 1 0 0 1 200 740 Tm (SERTIFIKA) Tj ET\n'
        b'BT /F2 13 Tf 0.1 0.42 0.29 rg 1 0 0 1 150 690 Tm (Ornek) Tj ET\n'
        b'BT /F2 13 Tf 0.1 0.42 0.29 rg 1 0 0 1 188 690 Tm ( ) Tj ET\n'           # tarayici: bosluk ayri nesne
        b'BT /F2 13 Tf 0.1 0.42 0.29 rg 1 0 0 1 192 690 Tm (Gida Uretim A.S.) Tj ET\n'
        b'BT /F1 10 Tf 0 0 0 rg 1 0 0 1 60 640 Tm (Bu belge kapsaminda yapilan denetimde firmanin uretim tesisinin tum) Tj ET\n'
        b'BT /F1 10 Tf 0 0 0 rg 1 0 0 1 60 627 Tm (gerekliliklere uygun oldugu ve belgelendirme kosullarini saglamaya devam) Tj ET\n'
        b'BT /F1 10 Tf 0 0 0 rg 1 0 0 1 60 614 Tm (ettigi gorulmustur.) Tj ET\n'
        b'BT /F1 10 Tf 0.33 0.33 0.33 rg 1 0 0 1 60 570 Tm (Sertifika no) Tj ET\n'
        b'BT /F1 10 Tf 0.33 0.33 0.33 rg 1 0 0 1 200 570 Tm (AGFO-001) Tj ET\n'
        b'BT /F1 10 Tf 0.33 0.33 0.33 rg 1 0 0 1 60 552 Tm (Denetim tarihi) Tj ET\n'
        b'BT /F1 10 Tf 0.33 0.33 0.33 rg 1 0 0 1 200 552 Tm (13.08.2026) Tj ET\n')


def form_pdf(path, pages=1):
    """Tarayicidan yazdirilmis sertifika gibi: tum metin bir form XObject'in icinde (sayfa: q ... /X1 Do Q)."""
    page_content = b'q 0 0 1 rg 0 0 595 30 re f Q q 1 0 0 1 0 0 cm /X1 Do Q\n'
    objs = ['<< /Type /Catalog /Pages 2 0 R >>',
            '<< /Type /Pages /Kids [%s] /Count %d >>' % (' '.join('%d 0 R' % (8 + 2 * k) for k in range(pages)), pages),
            None,     # 3: form
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>',
            None, None]
    out = b'%PDF-1.5\n'
    offs = []

    def add(i, body):
        nonlocal out
        while len(offs) < i:
            offs.append(0)
        offs[i - 1] = len(out)
        out += b'%d 0 obj\n' % i + body + b'\nendobj\n'
    add(1, objs[0].encode())
    add(2, objs[1].encode())
    add(3, b'<< /Type /XObject /Subtype /Form /BBox [0 0 595 842] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Length %d >>\nstream\n'
        % len(FORM) + FORM + b'\nendstream')
    add(4, objs[3].encode())
    add(5, objs[4].encode())
    add(6, b'<< /Length %d >>\nstream\n' % len(page_content) + page_content + b'\nendstream')
    add(7, b'<< /Font << >> >>')
    for k in range(pages):
        add(8 + 2 * k, b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 6 0 R /Resources << /XObject << /X1 3 0 R >> >> >>')
        add(9 + 2 * k, b'<< >>')
    x = len(out)
    out += ('xref\n0 %d\n0000000000 65535 f \n' % (len(offs) + 1)).encode() + b''.join(('%010d 00000 n \n' % o).encode() for o in offs)
    out += ('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(offs) + 1, x)).encode()
    pathlib.Path(path).write_bytes(out)
    return path


LIST_PAGE = (b'BT /F1 10 Tf 0 0 0 rg 60 790 Td (The certification body shall assess the background of every auditor before the first audit.) Tj ET\n'
             b'BT /F1 10 Tf 0 0 0 rg 60 760 Td (Evaluation methods could for example include:) Tj ET\n'
             b'BT /F3 10 Tf 60 745 Td (\\267) Tj ET BT /F1 10 Tf 80 745 Td (Alpha item) Tj ET\n'
             b'BT /F3 10 Tf 60 733 Td (\\267) Tj ET BT /F1 10 Tf 80 733 Td (Beta item) Tj ET\n'
             b'BT /F3 10 Tf 60 721 Td (\\267) Tj ET BT /F1 10 Tf 80 721 Td (Gamma item) Tj ET\n'
             b'BT /F1 10 Tf 60 680 Td (1) Tj ET BT /F1 10 Tf 100 680 Td (Introduction........................................3) Tj ET\n'
             b'BT /F1 10 Tf 60 668 Td (2) Tj ET BT /F1 10 Tf 100 668 Td (Requirements........................................3) Tj ET\n'
             b'BT /F1 10 Tf 60 620 Td (A1 Chemicals and Formulated Chemicals and Mixtures) Tj ET\n'
             b'BT /F1 10 Tf 60 608 Td (A2 Fabricated paper) Tj ET\n'
             b'0 0 0 RG 60 500 150 30 re S\n'
             b'q 60 500 150 30 re W n BT /F1 10 Tf 65 510 Td (Inside box) Tj ET BT /F1 10 Tf 65 490 Td (hidden line) Tj ET Q\n'
             # 1.4.9 zor durumlar: ust simge dipnot, alti cizili baglanti, dondurulmus kenar yazisi, a) isaretleri,
             # sayfa numarasi ayri nesne olan icindekiler satiri
             b'BT /F1 10 Tf 60 440 Td (A major finding) Tj ET BT /F1 6 Tf 126.6 444 Td (1) Tj ET BT /F1 10 Tf 130 440 Td ( shall be closed.) Tj ET\n'
             b'BT /F1 10 Tf 0 0 1 rg 60 420 Td (Write to audits@example.org today) Tj ET 0 0 1 RG 0.6 w 60 418.5 m 213 418.5 l S\n'
             b'BT /F1 8 Tf 0 0 0 rg 0 1 -1 0 30 300 Tm (Uncontrolled when printed) Tj ET\n'
             b'BT /F1 10 Tf 80 380 Td (a\\)) Tj ET BT /F1 10 Tf 98 380 Td (observe the cleaning;) Tj ET\n'
             b'BT /F1 10 Tf 80 367 Td (b\\)) Tj ET BT /F1 10 Tf 98 367 Td (check the devices.) Tj ET\n'
             b'BT /F1 10 Tf 100 340 Td (Records......................................) Tj ET BT /F1 10 Tf 500 340 Td (3) Tj ET\n'
             b'BT /F1 10 Tf 100 327 Td (Grading......................................) Tj ET BT /F1 10 Tf 500 327 Td (2) Tj ET\n'
             # 1.4.14: iki sutun basligi tek TJ icinde, arada buyuk bosluk (Tenda kurulum kilavuzu)
             b'BT /F1 14 Tf 60 280 Td [(I Connect the router) -15000 (II Connect to the internet)] TJ ET\n')


def list_pdf(path):
    """Madde imleri Symbol yazi tipinde ayri nesne, icindekiler satirlari, kirpilmis (gorunmeyen) metin, kutu."""
    w = pypdf.PdfWriter()
    w.add_blank_page(595, 842)
    from pypdf.generic import ContentStream, DecodedStreamObject, DictionaryObject, NameObject
    page = w.pages[0]
    stream = DecodedStreamObject()
    stream.set_data(LIST_PAGE)
    page[NameObject('/Contents')] = w._add_object(stream)
    fonts = DictionaryObject({NameObject('/F1'): DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                                                                   NameObject('/BaseFont'): NameObject('/Helvetica')}),
                              NameObject('/F3'): DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                                                                   NameObject('/BaseFont'): NameObject('/Symbol')})})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): fonts})
    _ = ContentStream
    with open(path, 'wb') as f:
        w.write(f)
    return path


def text_of(data, i=0):
    doc = pdfium.PdfDocument(data)
    tp = doc[i].get_textpage()
    return tp.get_text_range(0, tp.count_chars())


@unittest.skipUnless(HAVE, 'pypdf/pypdfium2/yazi tipi yok')
class FormTextTests(unittest.TestCase):
    def test_edit_text_inside_form_xobject(self):
        # 1.4.5: "Bu metin yerinde düzenlenemiyor (şablon/form nesnesinin içinde)" (BRCGS CP sertifikasi)
        src = form_pdf(os.path.join(TMP, 'sertifika.pdf'))
        pr = P.PdfProject(src)
        p = pr.pages[0]
        x, y = P.user_to_display(170, 694, p['box'], pr.rotation(0))
        info = pr.find_text_line(0, x, y)
        self.assertEqual(info['text'], 'Ornek Gida Uretim A.S.')
        self.assertFalse(info['nested'])
        self.assertTrue(all(len(o) == 2 for o in info['objects']))              # formun icindeki nesneler
        self.assertTrue(info['bold'])
        self.assertEqual(pr.edit_text(0, info, 'Ornek Gida Uretim A.S. (REVIZE)'), 'inplace')
        out = pr.save(os.path.join(TMP, 'sertifika (düzenlendi).pdf'))
        body = text_of(out)
        self.assertIn('(REVIZE)', body)
        self.assertEqual(body.count('Ornek'), 1)                                # eskisi formdan cikti
        self.assertIn('SERTIFIKA', body)
        self.assertIn('AGFO-001', body)
        pr2 = P.PdfProject(out)
        info2 = pr2.find_text_line(0, x, y)
        self.assertIn('REVIZE', info2['text'])
        self.assertAlmostEqual(info2['size'], 13.0, places=0)
        self.assertEqual(info2['color'], info['color'])


@unittest.skipUnless(HAVE, 'pypdf/pypdfium2/yazi tipi yok')
class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.src = form_pdf(os.path.join(TMP, 'duzen.pdf'), pages=2)
        self.data = pathlib.Path(self.src).read_bytes()
        self.pdf = pdfium.PdfDocument(self.data)

    def test_paragraphs(self):
        lay = L.extract_layout(self.pdf, 0)
        texts = [P_['text'] for P_ in lay['paras']]
        self.assertIn('Ornek Gida Uretim A.S.', texts)
        body = [P_ for P_ in lay['paras'] if P_['text'].startswith('Bu belge')]
        self.assertEqual(len(body), 1)
        self.assertEqual(len(body[0]['lines']), 3)                              # sarilmis metin tek paragraf
        self.assertTrue(body[0]['text'].endswith('ettigi gorulmustur.'))
        for t in ('Sertifika no', 'AGFO-001', 'Denetim tarihi', '13.08.2026'):  # tablo hucreleri ayri
            self.assertIn(t, texts)
        title = [P_ for P_ in lay['paras'] if P_['text'] == 'SERTIFIKA'][0]
        self.assertAlmostEqual(title['size'], 30, places=0)

    def test_translate_page_keeps_layout(self):
        lay = L.extract_layout(self.pdf, 0)
        trs = [('[EN] ' + P_['text']) if P_['text'] != 'AGFO-001' else None for P_ in lay['paras']]
        out, mode = L.translate_page(pypdf.PdfReader(self.src), 0, self.data, self.pdf, lay, trs)
        self.assertEqual(mode, 'inplace')
        body = text_of(out)
        self.assertIn('[EN] SERTIFIKA', body)
        self.assertIn('[EN] Ornek Gida Uretim A.S.', body)
        self.assertEqual(body.count('Denetim tarihi'), 1)
        self.assertEqual(body.count('AGFO-001'), 1)                             # cevrilmeyen paragraf yerinde
        lay2 = L.extract_layout(pdfium.PdfDocument(out), 0)
        t2 = {P_['text']: P_ for P_ in lay2['paras']}
        self.assertIn('[EN] SERTIFIKA', t2)
        self.assertAlmostEqual(t2['[EN] SERTIFIKA']['origin'][1], 740, delta=1.5)
        self.assertLess(t2['[EN] SERTIFIKA']['size'], 30.5)
        img = pdfium.PdfDocument(out)[0].render(scale=1).to_pil().convert('RGB')
        self.assertEqual(img.getpixel((300, 842 - 10)), (0, 0, 255))            # sayfanin geri kalani aynen

    def test_project_translated_pdf_and_blocks(self):
        pr = P.PdfProject(self.src)
        lays = pr.layouts()
        n = sum(len(x['paras']) for x in lays)
        texts = ['TR %d' % k for k in range(n)]
        data, st = pr.translated_pdf(lays, texts)
        self.assertEqual(st['inplace'], 2)
        self.assertEqual(len(pypdf.PdfReader(__import__('io').BytesIO(data)).pages), 2)
        self.assertIn('TR 0', text_of(data, 0))
        self.assertNotIn('SERTIFIKA', text_of(data, 1))
        blocks = L.layout_blocks(pr.layout_pages(), 'Sertifika', lays)
        styles = [(b.get('style'), ''.join(r['text'] for r in b.get('runs', []))) for b in blocks if b['t'] == 'p']
        self.assertEqual(styles[0], ('h1', 'Sertifika'))
        self.assertIn(('h1', 'SERTIFIKA'), styles)                              # buyuk yazi baslik
        self.assertTrue(any(b.get('pb') for b in blocks))                       # ikinci sayfa yeni sayfada
        tb = L.layout_blocks(pr.layout_pages(), None, lays, texts)
        self.assertEqual(''.join(r['text'] for r in tb[0]['runs']), 'TR 0')



@unittest.skipUnless(HAVE, 'pypdf/pypdfium2/yazi tipi yok')
class LayoutDetailTests(unittest.TestCase):
    """1.4.9: CP410 cevirisinde gorulen kucuk hatalar."""

    def setUp(self):
        self.src = list_pdf(os.path.join(TMP, 'liste.pdf'))
        self.data = pathlib.Path(self.src).read_bytes()
        self.pdf = pdfium.PdfDocument(self.data)
        self.lay = L.extract_layout(self.pdf, 0)
        self.texts = [P_['text'] for P_ in self.lay['paras']]

    def test_bullets_stay_and_items_are_separate(self):
        for t in ('Alpha item', 'Beta item', 'Gamma item'):
            self.assertIn(t, self.texts)                                   # her madde ayri paragraf, imi yok
        self.assertTrue(all('•' not in t and '\uf0b7' not in t for t in self.texts))
        P_ = [x for x in self.lay['paras'] if x['text'] == 'Alpha item'][0]
        self.assertTrue(P_['lines'][0]['bullet'])
        self.assertNotRegex(P_['font'], '(?i)symbol')

    def test_symbol_font_never_used_for_text(self):
        fp = E.pick_font('ABCDEF+SymbolMT')
        self.assertIsNotNone(fp)
        self.assertNotRegex(os.path.basename(fp), '(?i)symbol')

    def test_toc_lines_and_short_list_lines_not_merged(self):
        self.assertIn('Introduction........................................3', self.texts)
        self.assertIn('Requirements........................................3', self.texts)
        self.assertIn('A1 Chemicals and Formulated Chemicals and Mixtures', self.texts)
        self.assertIn('A2 Fabricated paper', self.texts)

    def test_clipped_text_is_ignored(self):
        self.assertIn('Inside box', self.texts)
        self.assertFalse(any('hidden' in t for t in self.texts))

    def test_translate_keeps_bullets_and_fits_toc(self):
        tr = {'Alpha item': 'Birinci madde', 'Beta item': 'Ikinci madde', 'Gamma item': 'Ucuncu madde',
              'Introduction........................................3': 'Giris ve cok daha uzun bir baslik metni.........3',
              'Inside box': 'Kutunun icinde\tsekme'}
        out, mode = L.translate_page(pypdf.PdfReader(self.src), 0, self.data, self.pdf, self.lay,
                                     [tr.get(t) for t in self.texts])
        self.assertEqual(mode, 'inplace')
        body = text_of(out)
        self.assertIn('Birinci madde', body)
        self.assertEqual(len(re.findall('[•\uf0b7]', body)), 3)                # Symbol madde imleri yerinde
        lay2 = L.extract_layout(pdfium.PdfDocument(out), 0)
        toc = [x for x in lay2['paras'] if x['text'].startswith('Giris')]
        self.assertEqual(len(toc), 1)
        self.assertEqual(len(toc[0]['lines']), 1)                               # tek satir, noktalar ayarlandi
        self.assertTrue(toc[0]['text'].endswith('3'))
        self.assertLessEqual(toc[0]['rect'][2], 100 + 260)
        self.assertIn('Kutunun icinde sekme', body)                             # sekme kutu olmadi

    def test_hard_cases_extraction(self):
        t = self.texts
        self.assertIn('A major finding¹ shall be closed.', t)                   # ust simge satira katildi
        self.assertIn('observe the cleaning;', t)                               # a) b) isaretleri yerinde kalir
        self.assertIn('check the devices.', t)
        self.assertIn('Records......................................', t)       # icindekiler satirlari ayri
        self.assertIn('Grading......................................', t)
        rot = [x for x in self.lay['paras'] if x['text'] == 'Uncontrolled when printed']
        self.assertEqual(len(rot), 1)
        self.assertTrue(rot[0]['rotated'])
        link = [x for x in self.lay['paras'] if x['text'].startswith('Write to')][0]
        self.assertEqual(len(link['underlines']), 1)                            # alti cizgisi bulundu

    def test_hard_cases_translation(self):
        tr = {'A major finding¹ shall be closed.': 'Majör bulgu¹ kapatılmalıdır.',
              'Write to audits@example.org today': 'Bugün audits@example.org adresine yazın',
              'Uncontrolled when printed': 'Basıldığında kontrolsüzdür',
              'observe the cleaning;': 'temizliği gözlemlemek;'}
        out, _mode = L.translate_page(pypdf.PdfReader(self.src), 0, self.data, self.pdf, self.lay, [tr.get(x) for x in self.texts])
        body = text_of(out)
        self.assertIn('Majör bulgu¹ kapatılmalıdır.', body)
        self.assertIn('Basıldığında kontrolsüzdür', body)
        self.assertIn('a)', body)
        doc = pdfium.PdfDocument(out)
        lay2 = L.extract_layout(doc, 0)
        rot = [x for x in lay2['paras'] if x['text'] == 'Basıldığında kontrolsüzdür']
        self.assertTrue(rot and rot[0]['rotated'])                              # ceviri de dondurulmus
        _v, _h, thin = L._walls(doc[0], 595, 842)
        self.assertFalse(any(abs(y - 418.5) < 1 for _p, y, _a, _b in thin))   # eski alti cizgisi kaldirildi
        items = {it['text'] for it in []}
        _ = items

    def test_toc_leaders_rebuilt_when_model_drops_them(self):
        # gercek model (DeepSeek-R1-Distill) icindekiler satirlarinin noktalarini atiyordu; satir ortalaniyordu
        tr = {'Records......................................': 'Kayıtlar', 'Grading......................................': 'Derecelendirme'}
        out, _m = L.translate_page(pypdf.PdfReader(self.src), 0, self.data, self.pdf, self.lay, [tr.get(x) for x in self.texts])
        lay2 = L.extract_layout(pdfium.PdfDocument(out), 0)
        rec = [x for x in lay2['paras'] if x['text'].startswith('Kayıtlar')][0]
        self.assertTrue(rec['text'].endswith('....'))
        self.assertAlmostEqual(rec['rect'][0], 100, delta=1.5)                  # sola yasli, ayni girinti

    def test_fonts_are_subset_and_output_stays_small(self):
        # 1.4.11: 50 KB'lik belge ceviriden sonra 1,8 MB oluyordu (her yazi tipi dosyasinin tamami gomuluyordu)
        fp = E.pick_font('Helvetica')
        self.assertLess(len(E.font_data(fp, 'Kayıtlar ve çeviri')), os.path.getsize(fp) / 3)
        pr = P.PdfProject(self.src)
        lays = pr.layouts()
        texts = ['Çeviri %d ğüşİ' % k for k in range(sum(len(x['paras']) for x in lays))]
        data, _st = pr.translated_pdf(lays, texts)
        self.assertLess(len(data), len(self.data) + 3 * 60000)
        self.assertIn('Çeviri 0 ğüşİ', text_of(data))

    def test_wide_object_split_into_columns(self):
        self.assertIn('I Connect the router', self.texts)
        self.assertIn('II Connect to the internet', self.texts)
        tr = {'I Connect the router': 'I Yönlendiriciyi bağlayın'}            # yalniz biri cevrilse de digeri kaybolmaz
        out, _m = L.translate_page(pypdf.PdfReader(self.src), 0, self.data, self.pdf, self.lay, [tr.get(x) for x in self.texts])
        body = text_of(out)
        self.assertIn('I Yönlendiriciyi bağlayın', body)
        self.assertIn('II Connect to the internet', body)
        self.assertNotIn('I Connect the router', body)
        lay2 = L.extract_layout(pdfium.PdfDocument(out), 0)
        second = [x for x in lay2['paras'] if x['text'].startswith('II Connect')][0]
        first = [x for x in self.lay['paras'] if x['text'].startswith('II Connect')][0]
        self.assertAlmostEqual(second['rect'][0], first['rect'][0], delta=2)  # ikinci baslik yerinde

    def test_broken_unicode_text_left_alone(self):
        self.assertTrue(L.BROKEN_TEXT_RX.search('\x1b\x1a\x19-\x14: abc'))
        self.assertFalse(L.BROKEN_TEXT_RX.search('Türkçe metin – ğüşİ'))

    def test_clean_text(self):
        self.assertEqual(L.clean_text('a\tb\u200b c\u00a0d \uf0b7 e'), 'a b c d • e')


if __name__ == '__main__':
    unittest.main()
