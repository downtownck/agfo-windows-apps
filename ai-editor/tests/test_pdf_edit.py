# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4 - PDF metnini yerinde duzenleme ve resim silme."""
import io
import os
import pathlib
import sys
import tempfile
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
os.environ.setdefault('LOCALAPPDATA', tempfile.mkdtemp(prefix='agfo-pdfedit-test-'))

import agfo_pdf as P  # noqa: E402
import agfo_pdf_edit as E  # noqa: E402

try:
    import pypdf
    import pypdfium2 as pdfium
    from PIL import Image
    HAVE = E.pick_font() is not None
except ImportError:  # pragma: no cover
    HAVE = False

TMP = tempfile.mkdtemp(prefix='agfo-pdfedit-')


def text_of(path, i=0):
    doc = pdfium.PdfDocument(path)
    tp = doc[i].get_textpage()
    return tp.get_text_range(0, tp.count_chars())


def with_image(src, dst, rect=(300, 300, 400, 400)):
    w = pypdf.PdfWriter(clone_from=src)
    im = Image.new('RGBA', (60, 60), (220, 20, 20, 255))
    ov = pypdf.PdfReader(io.BytesIO(P.build_overlay_pdf((0, 0, 595, 842), [('img', im, rect)])))
    w.pages[0].merge_page(ov.pages[0])
    with open(dst, 'wb') as f:
        w.write(f)
    return dst


@unittest.skipUnless(HAVE, 'pypdf/pypdfium2/yazi tipi yok')
class PdfEditTests(unittest.TestCase):
    def setUp(self):
        self.src = P.write_simple_pdf(os.path.join(TMP, 'rapor.pdf'), [
            ['Denetim Raporu', 'Firma: Ornek Gida A.S.', 'Sonuc: Uygun degil'], ['Ikinci sayfa']])

    def disp(self, pr, i, ux, uy):
        p = pr.pages[i]
        return P.user_to_display(ux, uy, p['box'], pr.rotation(i))

    def test_edit_line_real_text_undo_and_save(self):
        pr = P.PdfProject(self.src)
        x, y = self.disp(pr, 0, 100, 752)
        info = pr.find_text_line(0, x, y)
        self.assertEqual(info['text'], 'Firma: Ornek Gida A.S.')
        self.assertFalse(info['nested'])
        a, b, c, d = info['drect']
        self.assertTrue(a < x < c and b < y < d)
        pr.edit_text(0, info, 'Firma: Örnek Gıda A.Ş. (düzeltildi)')
        self.assertTrue(pr.dirty)
        self.assertIn(pr.pages[0]['src'], pr.derived)
        out = pr.save(os.path.join(TMP, 'rapor (düzenlendi).pdf'))
        body = text_of(out)
        self.assertIn('Örnek Gıda A.Ş. (düzeltildi)', body)                 # gercek, aranabilir metin
        self.assertNotIn('Ornek Gida', body)                                  # eskisi icerikten cikti
        self.assertIn('Denetim Raporu', body)
        self.assertEqual(len(pypdf.PdfReader(out).pages), 2)
        self.assertIn('Ikinci sayfa', text_of(out, 1))
        # tekrar duzenleme ayni satiri bulur
        info2 = pr.find_text_line(0, x, y)
        self.assertIn('düzeltildi', info2['text'])
        pr.undo()
        self.assertEqual(pr.pages[0]['src'], pr.path)
        out2 = pr.save(os.path.join(TMP, 'geri.pdf'))
        self.assertIn('Ornek Gida', text_of(out2))

    def test_delete_line_and_style_match(self):
        pr = P.PdfProject(self.src)
        x, y = self.disp(pr, 0, 70, 783)                                       # buyuk kalin baslik
        info = pr.find_text_line(0, x, y)
        self.assertEqual(info['text'], 'Denetim Raporu')
        self.assertTrue(info['bold'])
        self.assertGreater(info['size'], 14)
        pr.edit_text(0, info, '')                                             # bos metin: satiri sil
        out = pr.save(os.path.join(TMP, 'silindi.pdf'))
        self.assertNotIn('Denetim Raporu', text_of(out))

    def test_remove_image(self):
        src = with_image(self.src, os.path.join(TMP, 'resimli.pdf'))
        pr = P.PdfProject(src)
        x, y = self.disp(pr, 0, 350, 350)
        info = pr.find_image(0, x, y)
        self.assertEqual(info['kind'], 'image')
        self.assertIsNone(pr.find_image(0, *self.disp(pr, 0, 50, 50)))
        pr.remove_image(0, info)
        self.assertIsNone(pr.find_image(0, x, y))
        out = pr.save(os.path.join(TMP, 'resimsiz.pdf'))
        doc = pdfium.PdfDocument(out)
        self.assertFalse([o for o in doc[0].get_objects() if o.type == E.OBJ_IMAGE])
        self.assertIn('Firma', text_of(out))                                   # metin yerinde

    def test_rotated_page_coordinates(self):
        pr = P.PdfProject(self.src)
        pr.rotate([0], 90)
        x, y = self.disp(pr, 0, 100, 752)
        info = pr.find_text_line(0, x, y)
        self.assertEqual(info['text'], 'Firma: Ornek Gida A.S.')
        pr.edit_text(0, info, 'Firma: Döndürülmüş')
        out = pr.save(os.path.join(TMP, 'donuk.pdf'))
        self.assertEqual(int(pypdf.PdfReader(out).pages[0].get('/Rotate', 0)), 90)
        self.assertIn('Döndürülmüş', text_of(out))

    def test_restricted_pdf_blocks_and_keeps_encryption(self):
        def enc(flags, name):
            w = pypdf.PdfWriter(clone_from=self.src)
            w.encrypt(user_password='', owner_password='o', algorithm='AES-128', permissions_flag=flags)
            p = os.path.join(TMP, name)
            with open(p, 'wb') as f:
                w.write(f)
            return p
        pr = P.PdfProject(enc(P.P_PRINT | P.P_EXTRACT, 'kisitli.pdf'))
        x, y = self.disp(pr, 0, 100, 752)
        info = pr.find_text_line(0, x, y)
        with self.assertRaises(P.PdfError):
            pr.edit_text(0, info, 'yeni')
        flags = P.P_PRINT | P.P_MODIFY | P.P_EXTRACT
        pr = P.PdfProject(enc(flags, 'izinli.pdf'))
        pr.edit_text(0, pr.find_text_line(0, x, y), 'Firma: Değişti')
        out = pr.save(os.path.join(TMP, 'izinli-out.pdf'))
        r = pypdf.PdfReader(out)
        self.assertTrue(r.is_encrypted)
        r.decrypt('')
        self.assertEqual(int(r.user_access_permissions) & P.ALL_PERMS, flags)  # duzenlenen sayfa izinleri tasir
        self.assertIn('Değişti', r.pages[0].extract_text())

    def test_font_picker(self):
        self.assertTrue(os.path.isfile(E.pick_font('ABCDEF+Helvetica-Bold', True)))
        self.assertTrue(os.path.isfile(E.pick_font('Times-Roman', serif=True)))


if __name__ == '__main__':
    unittest.main()
