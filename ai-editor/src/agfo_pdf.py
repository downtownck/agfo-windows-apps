# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.3 - PDF duzenleme cekirdegi (Tk yok).

Model: duzenlenen PDF bir 'sayfa listesi'dir. Her sayfa bir kaynak dosyadaki bir sayfaya isaret eder
(birlestirme, siralama, silme, dondurme bu listede yapilir) ve uzerinde katmanlar (overlay) tasir:
  highlight  - gercek PDF vurgu notu (Highlight annotation; her goruntuleyicide gorunur, silinebilir)
  note       - yapiskan not (Text annotation)
  text       - metin kutusu; 'whiteout' ile alttaki alani beyazla kapatip ustune yazar (Turkce karakter destekli)
  image      - resim / imza (PNG, JPG)
  box        - cerceve / dikdortgen
Katman koordinatlari 'gorunen sayfa' uzerinde, sol-ust kokenli PDF noktasi (1/72 inc) cinsindendir;
kaydederken sayfanin donmesine gore PDF kullanici koordinatina cevrilir.
Metin/resim katmanlari Pillow ile goruntuye cizilip saydamlik maskesiyle (SMask) sayfaya gomulur; boylece
yazi tipi gommeden her dilde dogru gorunur. Ozgun dosyanin uzerine sessizce yazilmaz.
Render: pypdfium2 (BSD/Apache). Yazma: pypdf (BSD).
"""
from __future__ import annotations

import copy
import io
import os
import sys
import zlib

HIGHLIGHT_COLORS = {'Sarı': 'ffeb3b', 'Yeşil': '8ce99a', 'Mavi': '74c0fc', 'Pembe': 'faa2c1', 'Turuncu': 'ffc078'}


class PdfError(Exception):
    pass


def _pdfium():
    try:
        import pypdfium2
        return pypdfium2
    except ImportError as e:  # pragma: no cover
        raise PdfError('PDF görüntüleyici (pypdfium2) yüklü değil.') from e


def _pypdf():
    try:
        import pypdf
        return pypdf
    except ImportError as e:  # pragma: no cover
        raise PdfError('PDF yazıcı (pypdf) yüklü değil.') from e


# ---------------------------------------------------------------------------- koordinatlar
def display_size(w: float, h: float, rotation: int):
    return (h, w) if rotation % 180 else (w, h)


def display_to_user(x: float, y: float, box, rotation: int):
    """Gorunen sayfadaki (sol-ust koken, asagi dogru y) noktayi PDF kullanici uzayina cevirir.
    box = (x0, y0, W, H) donmemis MediaBox; rotation = saat yonunde 0/90/180/270."""
    x0, y0, w, h = box
    r = rotation % 360
    if r == 0:
        ux, uy = x, h - y
    elif r == 90:
        ux, uy = y, x
    elif r == 180:
        ux, uy = w - x, y
    else:  # 270
        ux, uy = w - y, h - x
    return x0 + ux, y0 + uy


def rect_to_user(rect, box, rotation):
    """Gorunen dikdortgen (x1,y1,x2,y2) -> kullanici uzayi (llx, lly, urx, ury)."""
    (ax, ay), (bx, by) = display_to_user(rect[0], rect[1], box, rotation), display_to_user(rect[2], rect[3], box, rotation)
    return min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)


def norm_rect(r):
    return min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3])


# ---------------------------------------------------------------------------- yazi tipi + metin goruntusu
def find_font(bold=False):
    names = (['segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'] if bold else ['segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf'])
    dirs = []
    if sys.platform == 'win32':
        dirs.append(os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'))
    dirs += ['/usr/share/fonts/truetype/dejavu', '/usr/share/fonts/dejavu', '/Library/Fonts']
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return None


def hex_rgb(h: str):
    h = (h or '000000').lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def wrap_lines(draw, font, text, max_w):
    out = []
    for para in (text or '').split('\n'):
        words, line = para.split(' '), ''
        for w in words:
            cand = (line + ' ' + w).strip() if line else w
            if draw.textlength(cand, font=font) <= max_w or not line:
                line = cand
            else:
                out.append(line)
                line = w
        out.append(line)
    return out


def render_text_image(text, w_pt, h_pt, size=11, color='000000', whiteout=False, bold=False, dpi=200):
    """Metin kutusunu RGBA goruntu olarak cizer (noktalar -> piksel, dpi cozunurlukte)."""
    from PIL import Image, ImageDraw, ImageFont
    k = dpi / 72.0
    W, H = max(1, int(w_pt * k)), max(1, int(h_pt * k))
    img = Image.new('RGBA', (W, H), (255, 255, 255, 255 if whiteout else 0))
    d = ImageDraw.Draw(img)
    fp = find_font(bold)
    font = ImageFont.truetype(fp, max(4, int(size * k))) if fp else ImageFont.load_default()
    pad = int(2 * k)
    y = pad
    lh = int(size * k * 1.25)
    for line in wrap_lines(d, font, text, W - 2 * pad):
        if y + lh > H + lh * 0.3:
            break
        d.text((pad, y), line, font=font, fill=hex_rgb(color) + (255,))
        y += lh
    return img


# ---------------------------------------------------------------------------- goruntu XObject'li bindirme sayfasi
def _image_streams(img):
    """PIL RGBA -> (RGB FlateDecode, Gray SMask FlateDecode, w, h)."""
    img = img.convert('RGBA')
    w, h = img.size
    rgb = zlib.compress(img.convert('RGB').tobytes(), 6)
    alpha = zlib.compress(img.getchannel('A').tobytes(), 6)
    return rgb, alpha, w, h


def build_overlay_pdf(page_box, items):
    """items: [('img', PIL.Image, (llx,lly,urx,ury))  |  ('rect', (llx,lly,urx,ury), stroke_hex, width)]
    Kullanici uzayinda, verilen MediaBox ile tek sayfalik PDF baytlari uretir."""
    x0, y0, w, h = page_box
    objs = {}
    content = []
    xobjs = []
    n = 4
    for it in items:
        if it[0] == 'img':
            _t, img, (a, b, c, d) = it
            rgb, alpha, iw, ih = _image_streams(img)
            smask_id, img_id = n, n + 1
            n += 2
            objs[smask_id] = (b'<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray '
                              b'/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>' % (iw, ih, len(alpha)), alpha)
            objs[img_id] = (b'<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB '
                            b'/BitsPerComponent 8 /Filter /FlateDecode /SMask %d 0 R /Length %d >>' % (iw, ih, smask_id, len(rgb)), rgb)
            name = 'Im%d' % img_id
            xobjs.append('/%s %d 0 R' % (name, img_id))
            content.append('q %.3f 0 0 %.3f %.3f %.3f cm /%s Do Q' % (c - a, d - b, a, b, name))
        elif it[0] == 'rect':
            _t, (a, b, c, d), stroke, width = it
            r, g, bl = (v / 255.0 for v in hex_rgb(stroke))
            content.append('q %.3f %.3f %.3f RG %.2f w %.3f %.3f %.3f %.3f re S Q' % (r, g, bl, width, a, b, c - a, d - b))
    stream = '\n'.join(content).encode('latin-1')
    res = '<< /XObject << %s >> >>' % ' '.join(xobjs) if xobjs else '<< >>'
    head = [
        (1, b'<< /Type /Catalog /Pages 2 0 R >>', None),
        (2, b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>', None),
        (3, ('<< /Type /Page /Parent 2 0 R /MediaBox [%.3f %.3f %.3f %.3f] /Resources %s /Contents %d 0 R >>'
             % (x0, y0, x0 + w, y0 + h, res, n)).encode('latin-1'), None),
    ]
    all_objs = [(i, dct, data) for i, dct, data in head]
    for i in sorted(objs):
        all_objs.append((i, objs[i][0], objs[i][1]))
    all_objs.append((n, b'<< /Length %d >>' % len(stream), stream))
    out = io.BytesIO()
    out.write(b'%PDF-1.5\n%\xe2\xe3\xcf\xd3\n')
    offsets = {}
    for i, dct, data in all_objs:
        offsets[i] = out.tell()
        out.write(b'%d 0 obj\n' % i + dct)
        if data is not None:
            out.write(b'\nstream\n' + data + b'\nendstream')
        out.write(b'\nendobj\n')
    xref = out.tell()
    count = max(offsets) + 1
    out.write(b'xref\n0 %d\n0000000000 65535 f \n' % count)
    for i in range(1, count):
        out.write(b'%010d 00000 n \n' % offsets.get(i, 0) if i in offsets else b'0000000000 65535 f \n')
    out.write(b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (count, xref))
    return out.getvalue()


# ---------------------------------------------------------------------------- model
class PdfProject:
    """Duzenlenen PDF: sayfa listesi + katmanlar + form degerleri + geri al yigini."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.sources = {}          # yol -> bytes (dosya kilitlenmesin diye bellekte)
        self.pages = []            # {'src', 'index', 'rot' (ek dondurme), 'base_rot', 'box', 'overlays': [...]}
        self.form_values = {}
        self.undo_stack, self.redo_stack = [], []
        self.dirty = False
        self._add_source_pages(self.path, None)
        self.fields = self._read_fields()

    # -- kaynaklar
    def _load_bytes(self, path):
        if path not in self.sources:
            with open(path, 'rb') as f:
                data = f.read()
            if not data.startswith(b'%PDF'):
                raise PdfError('Bu dosya bir PDF değil: %s' % os.path.basename(path))
            self.sources[path] = data
        return self.sources[path]

    def _reader(self, path):
        pypdf = _pypdf()
        r = pypdf.PdfReader(io.BytesIO(self._load_bytes(path)), strict=False)
        if r.is_encrypted:
            try:
                if not r.decrypt(''):
                    raise PdfError('PDF parola korumalı: %s' % os.path.basename(path))
            except PdfError:
                raise
            except Exception:
                raise PdfError('PDF parola korumalı veya şifresi çözülemiyor: %s' % os.path.basename(path))
        return r

    def _add_source_pages(self, path, at, indices=None):
        path = os.path.abspath(path)
        r = self._reader(path)
        new = []
        for i, pg in enumerate(r.pages):
            if indices is not None and i not in indices:
                continue
            mb = pg.mediabox
            box = (float(mb.left), float(mb.bottom), float(mb.width), float(mb.height))
            new.append({'src': path, 'index': i, 'rot': 0, 'base_rot': int(pg.get('/Rotate', 0) or 0) % 360,
                        'box': box, 'overlays': []})
        if not new:
            raise PdfError('PDF\'de sayfa yok.')
        if at is None:
            self.pages.extend(new)
        else:
            self.pages[at:at] = new
        return len(new)

    def _read_fields(self):
        try:
            r = self._reader(self.path)
            fields = r.get_fields() or {}
        except Exception:
            return {}
        out = {}
        for name, f in fields.items():
            ft = f.get('/FT')
            if ft not in ('/Tx', '/Btn', '/Ch'):
                continue
            val = f.get('/V')
            out[name] = {'type': {'/Tx': 'text', '/Btn': 'check', '/Ch': 'choice'}[ft], 'value': '' if val is None else str(val),
                         'options': [str(o[1] if isinstance(o, list) and len(o) > 1 else o) for o in (f.get('/Opt') or [])]}
        return out

    # -- geri al
    def snapshot(self):
        self.undo_stack.append(copy.deepcopy((self.pages, self.form_values)))
        self.undo_stack = self.undo_stack[-60:]
        self.redo_stack.clear()
        self.dirty = True

    def undo(self):
        if not self.undo_stack:
            return False
        self.redo_stack.append(copy.deepcopy((self.pages, self.form_values)))
        self.pages, self.form_values = self.undo_stack.pop()
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        self.undo_stack.append(copy.deepcopy((self.pages, self.form_values)))
        self.pages, self.form_values = self.redo_stack.pop()
        return True

    # -- sayfa islemleri
    def rotation(self, i):
        p = self.pages[i]
        return (p['base_rot'] + p['rot']) % 360

    def display_size(self, i):
        p = self.pages[i]
        return display_size(p['box'][2], p['box'][3], self.rotation(i))

    def rotate(self, idx, deg):
        self.snapshot()
        for i in idx:
            p = self.pages[i]
            old = self.rotation(i)
            p['rot'] = (p['rot'] + deg) % 360
            # katmanlar sayfayla birlikte doner: kullanici uzayina cevirip yeni gorunume geri hesapla
            for ov in p['overlays']:
                ov['rect'] = self._rerotate_rect(ov['rect'], p['box'], old, self.rotation(i))

    @staticmethod
    def _rerotate_rect(rect, box, old_rot, new_rot):
        ux1, uy1, ux2, uy2 = rect_to_user(rect, box, old_rot)
        # kullanici -> yeni gorunum: iki kosenin gorunum koordinatini bul (display_to_user'in tersi)
        pts = []
        for ux, uy in ((ux1, uy1), (ux2, uy2)):
            pts.append(user_to_display(ux, uy, box, new_rot))
        return norm_rect((pts[0][0], pts[0][1], pts[1][0], pts[1][1]))

    def delete(self, idx):
        if len(idx) >= len(self.pages):
            raise PdfError('Tüm sayfalar silinemez; en az bir sayfa kalmalı.')
        self.snapshot()
        for i in sorted(idx, reverse=True):
            del self.pages[i]

    def move(self, idx, delta):
        idx = sorted(idx, reverse=delta > 0)
        if not idx or (delta < 0 and idx[0] == 0) or (delta > 0 and idx[0] == len(self.pages) - 1):
            return [*idx]
        self.snapshot()
        new = []
        for i in idx:
            j = i + delta
            self.pages[i], self.pages[j] = self.pages[j], self.pages[i]
            new.append(j)
        return sorted(new)

    def insert_pdf(self, path, at=None):
        self.snapshot()
        try:
            return self._add_source_pages(path, at)
        except Exception:
            self.undo()
            self.redo_stack.clear()
            raise

    # -- katmanlar
    def add_overlay(self, i, ov):
        self.snapshot()
        ov = dict(ov)
        ov['rect'] = norm_rect(ov['rect'])
        self.pages[i]['overlays'].append(ov)
        return ov

    def remove_overlay(self, i, ov):
        self.snapshot()
        self.pages[i]['overlays'] = [o for o in self.pages[i]['overlays'] if o is not ov]

    def overlay_at(self, i, x, y):
        for ov in reversed(self.pages[i]['overlays']):
            a, b, c, d = ov['rect']
            if a - 3 <= x <= c + 3 and b - 3 <= y <= d + 3:
                return ov
        return None

    def set_field(self, name, value):
        self.snapshot()
        self.form_values[name] = value

    # -- metin
    def page_text(self, i):
        p = self.pages[i]
        try:
            return self._reader(p['src']).pages[p['index']].extract_text() or ''
        except Exception:
            return ''

    # -- goruntu
    def render(self, i, scale=1.0):
        """PIL.Image (RGB) - sayfanin gorunen hali (donmus), katmanlar haric."""
        pdfium = _pdfium()
        p = self.pages[i]
        doc = self._pdfium_doc(p['src'])
        page = doc[p['index']]
        try:
            return page.render(scale=scale, rotation=p['rot'] % 360).to_pil()
        finally:
            page.close()

    def _pdfium_doc(self, path):
        cache = getattr(self, '_pdfium_cache', None)
        if cache is None:
            cache = self._pdfium_cache = {}
        if path not in cache:
            cache[path] = _pdfium().PdfDocument(self._load_bytes(path))
        return cache[path]

    def close(self):
        for d in getattr(self, '_pdfium_cache', {}).values():
            try:
                d.close()
            except Exception:
                pass
        self._pdfium_cache = {}

    # -- kaydet
    def _attach_acroform(self, writer, readers):
        """Sayfalar tek tek kopyalandiginda AcroForm kaybolur: kopyalanan sayfalardaki alanlardan yeniden kur."""
        from pypdf.generic import ArrayObject, BooleanObject, DictionaryObject, NameObject
        fields, seen = ArrayObject(), set()
        for pg in writer.pages:
            for a in pg.get('/Annots') or []:
                ref = a
                obj = a.get_object()
                if obj.get('/Subtype') != '/Widget':
                    continue
                while '/Parent' in obj:
                    ref = obj.raw_get('/Parent')
                    obj = obj['/Parent'].get_object()
                key = getattr(ref, 'idnum', id(obj))
                if key not in seen and hasattr(ref, 'idnum'):
                    seen.add(key)
                    fields.append(ref)
        if not len(fields):
            return
        af = DictionaryObject()
        src = readers.get(self.path)
        try:
            src_af = src.trailer['/Root'].get('/AcroForm') if src is not None else None
            src_af = src_af.get_object() if src_af is not None else None
            for k in ('/DA', '/DR'):
                if src_af is not None and k in src_af:
                    af[NameObject(k)] = src_af[k].clone(writer)
        except Exception:
            pass
        af[NameObject('/Fields')] = fields
        af[NameObject('/NeedAppearances')] = BooleanObject(True)
        writer._root_object[NameObject('/AcroForm')] = writer._add_object(af)

    def save(self, out_path, pages=None):
        """Duzenlenmis PDF'yi yazar (atomik). pages: yalniz bu sira numaralari (sayfa ayirma/disari aktarma)."""
        pypdf = _pypdf()
        from pypdf.annotations import Highlight, Text
        from pypdf.generic import ArrayObject, FloatObject, NameObject, NumberObject
        writer = pypdf.PdfWriter()
        readers = {}
        sel = list(range(len(self.pages))) if pages is None else list(pages)
        for out_i, i in enumerate(sel):
            p = self.pages[i]
            if p['src'] not in readers:
                readers[p['src']] = self._reader(p['src'])
            page = writer.add_page(readers[p['src']].pages[p['index']])
            rot = self.rotation(i)
            baked = []
            for ov in p['overlays']:
                ur = rect_to_user(ov['rect'], p['box'], rot)
                t = ov['type']
                if t == 'highlight':
                    a, b, c, d = ur
                    qp = ArrayObject([FloatObject(v) for v in (a, d, c, d, a, b, c, b)])
                    ann = Highlight(rect=ur, quad_points=qp, highlight_color=ov.get('color', 'ffeb3b'))
                    if ov.get('text'):
                        ann[NameObject('/Contents')] = pypdf.generic.TextStringObject(ov['text'])
                    writer.add_annotation(out_i, ann)
                elif t == 'note':
                    a, b, c, d = ur
                    ann = Text(rect=(a, d - 20, a + 20, d), text=ov.get('text', ''), open=False)
                    ann[NameObject('/Name')] = NameObject('/Comment')
                    writer.add_annotation(out_i, ann)
                elif t in ('text', 'image'):
                    w_pt, h_pt = ov['rect'][2] - ov['rect'][0], ov['rect'][3] - ov['rect'][1]
                    if t == 'text':
                        img = render_text_image(ov.get('text', ''), w_pt, h_pt, ov.get('size', 11), ov.get('color', '000000'),
                                                ov.get('whiteout', False), ov.get('bold', False))
                    else:
                        from PIL import Image
                        img = Image.open(io.BytesIO(ov['data'])).convert('RGBA')
                    if rot:
                        img = img.rotate(rot, expand=True)        # gorunumde dik dursun diye ters yone cevir
                    baked.append(('img', img, ur))
                elif t == 'box':
                    baked.append(('rect', ur, ov.get('color', 'e03131'), ov.get('width', 1.5)))
            if baked:
                ov_pdf = pypdf.PdfReader(io.BytesIO(build_overlay_pdf(p['box'], baked)))
                page.merge_page(ov_pdf.pages[0])
            if p['rot']:
                page.rotate(p['rot'])
        if self.form_values or self.fields:
            self._attach_acroform(writer, readers)
        if self.form_values:
            try:
                for pg in writer.pages:
                    writer.update_page_form_field_values(pg, {k: v for k, v in self.form_values.items()}, auto_regenerate=False)
                writer.set_need_appearances_writer(True)
            except Exception as e:
                raise PdfError('Form alanları yazılamadı: %s' % e)
        writer.add_metadata({'/Producer': 'AGFO AI Editor'})
        out_path = os.path.abspath(out_path)
        tmp = out_path + '.agfo-tmp'
        with open(tmp, 'wb') as f:
            writer.write(f)
        os.replace(tmp, out_path)
        if pages is None:
            self.dirty = False
        return out_path


def user_to_display(ux, uy, box, rotation):
    x0, y0, w, h = box
    ux, uy = ux - x0, uy - y0
    r = rotation % 360
    if r == 0:
        return ux, h - uy
    if r == 90:
        return uy, ux
    if r == 180:
        return w - ux, uy
    return h - uy, w - ux


def suggest_name(path: str, suffix='düzenlendi') -> str:
    base, _ext = os.path.splitext(path)
    return '%s (%s).pdf' % (base, suffix)


def write_simple_pdf(path, pages, title_size=18):
    """Ornek/test icin basit PDF (Helvetica, ASCII). pages: [[satir, ...], ...]; ilk satir baslik olarak buyuk yazilir."""
    objs = ['<< /Type /Catalog /Pages 2 0 R >>', None, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>']
    kids = []
    for lines in pages:
        parts = ['BT']
        y = 780
        for k, line in enumerate(lines):
            esc = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            size = title_size if k == 0 else 11
            font = '/F2' if k == 0 else '/F1'
            parts.append('%s %d Tf 1 0 0 1 60 %d Tm (%s) Tj' % (font, size, y, esc))
            y -= 30 if k == 0 else 16
        parts.append('ET')
        content = ' '.join(parts)
        objs.append('<< /Length %d >>\nstream\n%s\nendstream' % (len(content), content))
        cid = len(objs)
        objs.append('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> '
                    '/Contents %d 0 R >>' % cid)
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
    with open(path, 'wb') as f:
        f.write(out)
    return path
