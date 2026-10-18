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


def designed_pdf(path):
    """Gercek belgelerdeki ozellikler: ozel renk (Separation), saydamlik (ExtGState), kirpma yolu, beyaz yazi.
    1.4.0/1.4.1 bu sayfayi yeniden uretip bozuyordu (siyah kutu, beyaz uzerine beyaz)."""
    content = (b'q /CS0 cs 1 scn 40 760 515 50 re f Q\n'
               b'BT /F1 20 Tf 1 1 1 rg 55 778 Td (Baslik beyaz) Tj ET\n'
               b'q /GS0 gs 1 0.5 0 rg 40 600 300 120 re f Q\n'
               b'BT /F1 11 Tf 0 0 0 rg 55 700 Td (Satir bir) Tj 0 -18 Td (Duzenlenecek satir) Tj 0 -18 Td [(Kern)-250(li)] TJ ET\n'
               b'q 420 590 100 100 re W n /CS0 cs 0.6 scn 400 580 140 120 re f Q\n'
               b'q 0.5 0 0 0.5 30 280 cm BT 0.08 Tc 48 0 0 48 50 560 Tm /F1 1 Tf (BUYUK BASLIK) Tj ET Q\n')
    objs = ['<< /Type /Catalog /Pages 2 0 R >>',
            '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> '
            '/ColorSpace << /CS0 [/Separation /AGFOBlue /DeviceCMYK 6 0 R] >> /ExtGState << /GS0 << /ca 0.35 /CA 0.35 >> >> >> >>',
            None,
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
            '<< /FunctionType 2 /Domain [0 1] /C0 [0 0 0 0] /C1 [0.9 0.5 0 0.1] /N 1 >>']
    out = b'%PDF-1.5\n'
    offs = []
    for i, o in enumerate(objs, start=1):
        offs.append(len(out))
        if o is None:
            out += b'%d 0 obj\n<< /Length %d >>\nstream\n' % (i, len(content)) + content + b'\nendstream\nendobj\n'
        else:
            out += ('%d 0 obj\n%s\nendobj\n' % (i, o)).encode()
    x = len(out)
    out += ('xref\n0 %d\n0000000000 65535 f \n' % (len(objs) + 1)).encode() + b''.join(('%010d 00000 n \n' % o).encode() for o in offs)
    out += ('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objs) + 1, x)).encode()
    pathlib.Path(path).write_bytes(out)
    return path


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

    def test_space_not_mapped_to_nbsp(self):
        # Arial'de bosluk ve bolunmez bosluk ayni glif: pdfium ToUnicode'u 00A0 yapiyordu (Windows CI'da yakalandi)
        cmap = (b'1 beginbfchar\n<0003> <0020>\nendbfchar\n2 beginbfrange\n<0003> <0005> [<00A0> <0021> <00A0>]\n'
                b'<00A0> <00FF> <0100>\nendbfrange\n<0009> <00A0>\n')
        out = E._cmap_nbsp_to_space(cmap)
        self.assertIn(b'<0003> <0005> [<0020> <0021> <00A0>]', out)     # yalniz bosluk glifi duzelir
        self.assertIn(b'<00A0> <00FF> <0100>', out)                      # aralik kaynaklari dokunulmaz
        self.assertIn(b'<0009> <0020>', out)

    def test_designed_page_untouched_outside_edit(self):
        from PIL import ImageChops
        src = designed_pdf(os.path.join(TMP, 'tasarim.pdf'))
        pr = P.PdfProject(src)
        x, y = self.disp(pr, 0, 60, 683)
        info = pr.find_text_line(0, x, y)
        self.assertEqual(info['text'], 'Duzenlenecek satir')
        self.assertEqual(pr.edit_text(0, info, 'Düzeltilmiş satır'), 'inplace')
        out = pr.save(os.path.join(TMP, 'tasarim-out.pdf'))
        before = pdfium.PdfDocument(src)[0].render(scale=1).to_pil().convert('RGB')
        after = pdfium.PdfDocument(out)[0].render(scale=1).to_pil().convert('RGB')
        diff = ImageChops.difference(before, after).convert('L').point(lambda v: 255 if v > 30 else 0).getbbox()
        a, b, c, d = info['drect']
        self.assertIsNotNone(diff)
        self.assertTrue(diff[1] >= b - 4 and diff[3] <= d + 6, (diff, info['drect']))   # yalniz duzenlenen satir degisti
        self.assertEqual(before.getpixel((300, 60)), after.getpixel((300, 60)))          # ozel renkli serit siyahlasmadi
        self.assertGreater(sum(after.getpixel((300, 60))), 200)
        body = text_of(out)
        self.assertIn('Baslik beyaz', body)
        self.assertIn('Düzeltilmiş satır', body)
        self.assertNotIn('Duzenlenecek', body)
        # kerning'li TJ satiri (Word/InDesign PDF'leri) da yerinde degisir
        pr2 = P.PdfProject(out)
        info2 = pr2.find_text_line(0, *self.disp(pr2, 0, 60, 665))
        self.assertEqual(pr2.edit_text(0, info2, 'Kernsiz'), 'inplace')
        out2 = pr2.save(os.path.join(TMP, 'tasarim-out2.pdf'))
        self.assertNotIn('Kern li', text_of(out2).replace('Kernsiz', ''))

    def test_white_text_keeps_colour_and_fallback(self):
        src = designed_pdf(os.path.join(TMP, 'tasarim2.pdf'))
        pr = P.PdfProject(src)
        info = pr.find_text_line(0, *self.disp(pr, 0, 60, 782))
        self.assertEqual(info['text'], 'Baslik beyaz')
        pr.edit_text(0, info, 'Yeni başlık')
        out = pr.save(os.path.join(TMP, 'tasarim2-out.pdf'))
        img = pdfium.PdfDocument(out)[0].render(scale=2).to_pil().convert('RGB')
        a, b, c, d = info['drect']
        px = [img.getpixel((int(xx * 2), int(yy * 2))) for xx in range(int(a), int(a) + 60) for yy in range(int(b), int(d))]
        self.assertTrue(any(sum(p) > 700 for p in px))                                    # beyaz yazi beyaz kaldi
        # yapisi eslenemeyen sayfa: ustune yazma yedegi devreye girer, hata vermez
        pr3 = P.PdfProject(self.src)
        info3 = pr3.find_text_line(0, *self.disp(pr3, 0, 100, 752))
        import unittest.mock as um
        with um.patch.object(E, 'strip_ops', side_effect=E.EditError('uyumsuz')):
            self.assertEqual(pr3.edit_text(0, info3, 'Yedek yol'), 'overlay')
        self.assertEqual(pr3.pages[0]['overlays'][-1]['text'], 'Yedek yol')

    def test_matrix_scaled_text_keeps_size_and_tracking(self):
        # tasarim programlari '1 Tf' + olcekli matris kullanir; 1.4.2 yeni metni 1 pt yaziyordu (Skill Leap PDF'i)
        src = designed_pdf(os.path.join(TMP, 'olcekli.pdf'))
        pr = P.PdfProject(src)
        info = pr.find_text_line(0, *self.disp(pr, 0, 70, 563))
        self.assertEqual(info['text'], 'BUYUK BASLIK')
        self.assertAlmostEqual(info['size'], 24.0, places=1)                              # 1 x 48 x 0.5
        pr.edit_text(0, info, 'BUYUK BASLIK')
        out = pr.save(os.path.join(TMP, 'olcekli-out.pdf'))
        pr2 = P.PdfProject(out)
        info2 = pr2.find_text_line(0, *self.disp(pr2, 0, 70, 563))
        self.assertEqual(info2['text'], 'BUYUK BASLIK')
        self.assertAlmostEqual(info2['size'], 24.0, places=1)
        w1 = info['rect'][2] - info['rect'][0]
        w2 = info2['rect'][2] - info2['rect'][0]
        self.assertLess(abs(w1 - w2) / w1, 0.04, (w1, w2))                                # harf araligi da korundu

    def test_font_picker(self):
        self.assertTrue(os.path.isfile(E.pick_font('ABCDEF+Helvetica-Bold', True)))
        self.assertTrue(os.path.isfile(E.pick_font('Times-Roman', serif=True)))


if __name__ == '__main__':
    unittest.main()
