# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.3 - PDF duzenleyici cekirdegi testleri (pypdf + pypdfium2)."""
import io
import os
import pathlib
import sys
import tempfile
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
os.environ.setdefault('LOCALAPPDATA', tempfile.mkdtemp(prefix='agfo-pdf-test-'))

import agfo_pdf as P  # noqa: E402

try:
    import pypdf
    import pypdfium2 as pdfium
    from PIL import Image
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

TMP = tempfile.mkdtemp(prefix='agfo-pdf-')


def red_png(w=40, h=20, split=False):
    im = Image.new('RGBA', (w, h), (0, 0, 255, 255) if split else (255, 0, 0, 255))
    if split:
        for x in range(w // 2):
            for y in range(h):
                im.putpixel((x, y), (255, 0, 0, 255))
    b = io.BytesIO()
    im.save(b, 'PNG')
    return b.getvalue()


def render(path, i=0):
    return pdfium.PdfDocument(path)[i].render(scale=1).to_pil().convert('RGB')


def form_pdf(path):
    """Tek metin alani (Ad) ve onay kutusu (Onay) olan elle yazilmis AcroForm PDF."""
    objs = ['<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [4 0 R 5 0 R] >> >>',
            '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Annots [4 0 R 5 0 R] >>',
            '<< /Type /Annot /Subtype /Widget /FT /Tx /T (Ad) /V (eski) /Rect [100 700 300 720] /P 3 0 R >>',
            '<< /Type /Annot /Subtype /Widget /FT /Btn /T (Onay) /V /Off /AS /Off /Rect [100 650 115 665] /P 3 0 R >>']
    out = b'%PDF-1.4\n'
    offs = []
    for i, o in enumerate(objs, start=1):
        offs.append(len(out))
        out += ('%d 0 obj\n%s\nendobj\n' % (i, o)).encode()
    x = len(out)
    out += ('xref\n0 %d\n0000000000 65535 f \n' % (len(objs) + 1)).encode() + b''.join(('%010d 00000 n \n' % o).encode() for o in offs)
    out += ('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objs) + 1, x)).encode()
    pathlib.Path(path).write_bytes(out)


@unittest.skipUnless(HAVE, 'pypdf/pypdfium2/Pillow yok')
class PdfCoreTests(unittest.TestCase):
    def setUp(self):
        self.src = P.write_simple_pdf(os.path.join(TMP, 'kaynak.pdf'), [['Page one', 'body'], ['Page two'], ['Page three']])

    def test_coordinates_roundtrip(self):
        box = (10, 20, 595, 842)
        for rot in (0, 90, 180, 270):
            for pt in ((0, 0), (100, 50), (300, 500)):
                ux, uy = P.display_to_user(pt[0], pt[1], box, rot)
                self.assertEqual(tuple(round(v, 6) for v in P.user_to_display(ux, uy, box, rot)), pt)

    def test_image_overlay_position_and_orientation_all_rotations(self):
        for rot in (0, 90, 180, 270):
            pr = P.PdfProject(self.src)
            if rot:
                pr.rotate([0], rot)
            pr.add_overlay(0, {'type': 'image', 'rect': (100, 100, 300, 200), 'data': red_png(split=True)})
            out = os.path.join(TMP, 'rot%d.pdf' % rot)
            pr.save(out)
            img = render(out)
            self.assertEqual(img.size, tuple(int(v) for v in pr.display_size(0)), rot)
            self.assertEqual(img.getpixel((150, 150)), (255, 0, 0), rot)     # sol yari kirmizi: goruntu dik
            self.assertEqual(img.getpixel((250, 150)), (0, 0, 255), rot)
            self.assertEqual(img.getpixel((50, 50))[:3], (255, 255, 255), rot)
            self.assertEqual(pr.render(0).size, img.size)                       # canli gorunum = kaydedilen

    def test_intrinsic_rotate_page(self):
        w = pypdf.PdfWriter()
        for pg in pypdf.PdfReader(self.src).pages:
            w.add_page(pg)
        w.pages[0].rotate(90)
        rp = os.path.join(TMP, 'intrinsic.pdf')
        with open(rp, 'wb') as f:
            w.write(f)
        pr = P.PdfProject(rp)
        self.assertEqual(pr.display_size(0), (842.0, 595.0))
        pr.add_overlay(0, {'type': 'image', 'rect': (100, 100, 300, 200), 'data': red_png(split=True)})
        out = os.path.join(TMP, 'intrinsic-out.pdf')
        pr.save(out)
        img = render(out)
        self.assertEqual((img.getpixel((150, 150)), img.getpixel((250, 150))), ((255, 0, 0), (0, 0, 255)))

    def test_annotations_text_whiteout_and_box(self):
        pr = P.PdfProject(self.src)
        pr.add_overlay(0, {'type': 'highlight', 'rect': (55, 50, 200, 70), 'color': 'ffeb3b', 'text': 'önemli'})
        pr.add_overlay(0, {'type': 'note', 'rect': (400, 100, 418, 118), 'text': 'Kontrol edilecek'})
        pr.add_overlay(1, {'type': 'text', 'rect': (50, 40, 400, 80), 'text': 'Düzeltildi: ĞÜŞİÖÇ ğüşıöç', 'size': 14,
                           'color': '000000', 'whiteout': True})
        pr.add_overlay(2, {'type': 'box', 'rect': (100, 300, 300, 400), 'color': 'e03131', 'width': 3})
        out = os.path.join(TMP, 'ann.pdf')
        pr.save(out)
        r = pypdf.PdfReader(out)
        subtypes = [a.get_object()['/Subtype'] for a in r.pages[0]['/Annots']]
        self.assertEqual(sorted(subtypes), ['/Highlight', '/Text'])
        hl = next(a.get_object() for a in r.pages[0]['/Annots'] if a.get_object()['/Subtype'] == '/Highlight')
        self.assertEqual(hl['/Contents'], 'önemli')
        note = next(a.get_object() for a in r.pages[0]['/Annots'] if a.get_object()['/Subtype'] == '/Text')
        self.assertEqual(note['/Contents'], 'Kontrol edilecek')
        img = render(out, 1)
        # beyaz kutu eski basligi ("Page two", y~62) kapatti, ustune koyu metin yazildi
        dark = sum(1 for x in range(55, 395, 2) for y in range(44, 76, 2) if sum(img.getpixel((x, y))) < 300)
        self.assertGreater(dark, 30)
        self.assertEqual(render(out, 2).getpixel((100, 350))[0] > 180 and render(out, 2).getpixel((100, 350))[1] < 120, True)

    def test_page_operations_and_undo(self):
        pr = P.PdfProject(self.src)
        other = P.write_simple_pdf(os.path.join(TMP, 'ek.pdf'), [['Inserted A'], ['Inserted B']])
        self.assertEqual(pr.insert_pdf(other, 1), 2)
        self.assertEqual([p['src'] == other for p in pr.pages], [False, True, True, False, False])
        self.assertEqual(pr.move([4], -1), [3])
        pr.rotate([0], 90)
        pr.delete([2])
        self.assertEqual(len(pr.pages), 4)
        with self.assertRaises(P.PdfError):
            pr.delete([0, 1, 2, 3])
        out = os.path.join(TMP, 'ops.pdf')
        pr.save(out)
        r = pypdf.PdfReader(out)
        texts = [pg.extract_text().strip().split('\n')[0] for pg in r.pages]
        self.assertEqual(texts, ['Page one', 'Inserted A', 'Page three', 'Page two'])
        self.assertEqual(int(r.pages[0].get('/Rotate', 0)), 90)
        part = os.path.join(TMP, 'part.pdf')
        pr.save(part, pages=[1, 2])
        self.assertEqual([pg.extract_text().strip() for pg in pypdf.PdfReader(part).pages], ['Inserted A', 'Page three'])
        self.assertTrue(pr.undo())                         # delete geri
        self.assertEqual(len(pr.pages), 5)
        self.assertTrue(pr.redo())
        self.assertEqual(len(pr.pages), 4)
        orig = pathlib.Path(self.src).read_bytes()
        pr.save(os.path.join(TMP, 'x.pdf'))
        self.assertEqual(pathlib.Path(self.src).read_bytes(), orig)   # ozgun dosya degismez

    def test_overlay_moves_with_rotation(self):
        pr = P.PdfProject(self.src)
        ov = pr.add_overlay(0, {'type': 'image', 'rect': (100, 100, 300, 200), 'data': red_png(split=True)})
        before = render(pr.save(os.path.join(TMP, 'before.pdf')))
        pr.rotate([0], 90)
        self.assertEqual(tuple(round(v) for v in ov['rect']), (642, 100, 742, 300))
        img = render(pr.save(os.path.join(TMP, 'after.pdf')))
        self.assertEqual(img.getpixel((690, 150)), (255, 0, 0))   # dondurulmus sayfada ayni icerik ayni yerde
        self.assertEqual(before.getpixel((150, 150)), (255, 0, 0))

    def test_forms(self):
        fp = os.path.join(TMP, 'form.pdf')
        form_pdf(fp)
        pr = P.PdfProject(fp)
        self.assertEqual(pr.fields['Ad']['type'], 'text')
        self.assertEqual(pr.fields['Ad']['value'], 'eski')
        self.assertEqual(pr.fields['Onay']['type'], 'check')
        pr.set_field('Ad', 'Cemal Gürkan')
        out = os.path.join(TMP, 'form-out.pdf')
        pr.save(out)
        self.assertEqual(pypdf.PdfReader(out).get_fields()['Ad']['/V'], 'Cemal Gürkan')

    def test_errors(self):
        bad = os.path.join(TMP, 'bad.pdf')
        pathlib.Path(bad).write_text('not a pdf')
        with self.assertRaises(P.PdfError):
            P.PdfProject(bad)
        w = pypdf.PdfWriter()
        w.add_blank_page(200, 200)
        w.encrypt('gizli')
        enc = os.path.join(TMP, 'enc.pdf')
        with open(enc, 'wb') as f:
            w.write(f)
        with self.assertRaises(P.PdfError):
            P.PdfProject(enc)
        self.assertEqual(P.suggest_name(r'C:\a\rapor.pdf'), r'C:\a\rapor (düzenlendi).pdf')


def encrypt_copy(src, dst, flags, algorithm='AES-128'):
    """BRCGS benzeri: acma parolasi yok, sahip parolali, AES, kisitli izinler."""
    w = pypdf.PdfWriter(clone_from=src)
    w.encrypt(user_password='', owner_password='sahip', algorithm=algorithm, permissions_flag=flags)
    with open(dst, 'wb') as f:
        w.write(f)
    return dst


@unittest.skipUnless(HAVE, 'pypdf/pypdfium2/Pillow yok')
class EncryptedPdfTests(unittest.TestCase):
    """1.3.1: AES sifreli, sahip izinleri kisitli PDF'ler (or. BRCGS yayinlari)."""

    def setUp(self):
        self.src = P.write_simple_pdf(os.path.join(TMP, 'acik.pdf'), [['Clause 1', 'text'], ['Clause 2']])

    def test_restricted_aes_opens_renders_and_blocks_edits(self):
        enc = encrypt_copy(self.src, os.path.join(TMP, 'brcgs.pdf'), P.P_PRINT | P.P_EXTRACT_ACCESS)
        pr = P.PdfProject(enc)
        self.assertTrue(pr.encrypted)
        self.assertEqual(len(pr.pages), 2)
        img = pr.render(0, 0.5)
        self.assertGreater(img.size[0], 100)
        self.assertIn('Clause 1', pr.page_text(0))         # erisilebilirlik icin metin cikarma izni var
        self.assertFalse(pr.can('annotate'))
        self.assertFalse(pr.can('modify'))
        self.assertFalse(pr.can('assemble'))
        self.assertEqual(len(pr.restrictions()), 4)
        for fn in (lambda: pr.rotate([0], 90), lambda: pr.delete([0]), lambda: pr.move([1], -1),
                   lambda: pr.add_overlay(0, {'type': 'highlight', 'rect': (10, 10, 50, 30)}),
                   lambda: pr.add_overlay(0, {'type': 'text', 'rect': (10, 10, 50, 30), 'text': 'x'}),
                   lambda: pr.insert_pdf(self.src), lambda: pr.save(os.path.join(TMP, 'x.pdf'), pages=[0]),
                   lambda: pr.set_field('Ad', 'y')):
            with self.assertRaises(P.PdfError) as cm:
                fn()
            self.assertIn('izni vermemiş', str(cm.exception))
        self.assertFalse(pr.dirty)
        self.assertEqual(len(pr.pages), 2)
        self.assertEqual(pr.undo_stack, [])

    def test_annotation_only_permission_and_reencrypted_output(self):
        flags = P.P_PRINT | P.P_ANNOTATE | P.P_EXTRACT
        enc = encrypt_copy(self.src, os.path.join(TMP, 'not-izinli.pdf'), flags, 'AES-256')
        pr = P.PdfProject(enc)
        pr.add_overlay(0, {'type': 'highlight', 'rect': (40, 40, 200, 60)})
        pr.add_overlay(0, {'type': 'note', 'rect': (40, 80, 58, 98), 'text': 'Denetim notu'})
        with self.assertRaises(P.PdfError):
            pr.add_overlay(0, {'type': 'box', 'rect': (10, 10, 50, 30)})
        out = pr.save(os.path.join(TMP, 'not-izinli (düzenlendi).pdf'))
        r = pypdf.PdfReader(out)
        self.assertTrue(r.is_encrypted)
        self.assertTrue(r.decrypt(''))                      # acma parolasi yok
        self.assertEqual(int(r.user_access_permissions) & P.ALL_PERMS, flags)   # izinler korunur
        self.assertNotEqual(r.decrypt('sahip'), 2)          # ozgun sahip parolasi kopyalanmaz
        subs = [a.get_object()['/Subtype'] for a in r.pages[0]['/Annots']]
        self.assertEqual(sorted(subs), ['/Highlight', '/Text'])
        self.assertEqual(len(P.PdfProject(out).pages), 2)   # tekrar acilabilir

    def test_mixed_sources_use_most_restrictive_flags(self):
        enc = encrypt_copy(self.src, os.path.join(TMP, 'birlestir.pdf'), P.P_PRINT | P.P_ASSEMBLE | P.P_EXTRACT)
        pr = P.PdfProject(self.src)                         # sifresiz ana belge: her sey serbest
        self.assertFalse(pr.encrypted)
        self.assertEqual(pr.restrictions(), [])
        pr.insert_pdf(enc)
        self.assertEqual(len(pr.pages), 4)
        with self.assertRaises(P.PdfError):                 # eklenen kisitli sayfaya icerik eklenemez
            pr.add_overlay(3, {'type': 'image', 'rect': (10, 10, 50, 30), 'data': red_png()})
        pr.add_overlay(0, {'type': 'image', 'rect': (10, 10, 50, 30), 'data': red_png()})
        out = pr.save(os.path.join(TMP, 'birlesik.pdf'))
        r = pypdf.PdfReader(out)
        self.assertTrue(r.is_encrypted)
        r.decrypt('')
        self.assertEqual(int(r.user_access_permissions) & P.ALL_PERMS, P.P_PRINT | P.P_ASSEMBLE | P.P_EXTRACT)
        plain = pr.save(os.path.join(TMP, 'yalniz-acik.pdf'), pages=[0, 1])
        self.assertFalse(pypdf.PdfReader(plain).is_encrypted)

    def test_no_text_extraction_permission(self):
        enc = encrypt_copy(self.src, os.path.join(TMP, 'kopyalanamaz.pdf'), P.P_PRINT)
        pr = P.PdfProject(enc)
        with self.assertRaises(P.PdfError):
            pr.page_text(0)
        self.assertIn('metin çıkarma', ', '.join(pr.restrictions()))

    def test_missing_crypto_message(self):
        enc = encrypt_copy(self.src, os.path.join(TMP, 'aes-eksik.pdf'), P.P_PRINT)
        from unittest import mock
        from pypdf.errors import DependencyError
        err = DependencyError('cryptography>=3.1 is required for AES algorithm')
        with mock.patch.object(pypdf.PdfReader, 'decrypt', side_effect=err):
            with self.assertRaises(P.PdfError) as cm:
                P.PdfProject(enc)
        self.assertIn('cryptography', str(cm.exception))
        self.assertIn('güncelleyin', str(cm.exception))

if __name__ == '__main__':
    unittest.main()
