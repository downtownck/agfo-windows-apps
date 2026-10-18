# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4.6 - form XObject icindeki metni duzenleme, sayfa duzeni cikarma ve duzeni koruyan PDF cevirisi."""
import os
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


if __name__ == '__main__':
    unittest.main()
