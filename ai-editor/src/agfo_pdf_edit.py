# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4 - PDF icerigini yerinde duzenleme (pdfium).

* Metni duzenle: tiklanan satirin metin nesneleri bulunur, sayfadan GERCEKTEN cikarilir ve yerine ayni konuma, benzer
  yazi tipi / boyut / renkle yeni (aranabilir, secilebilir) metin yazilir. Turkce karakterler icin TrueType yazi tipi
  gomulur (Windows: Arial/Times/Calibri..., Linux: Liberation/DejaVu).
* Resmi sil: sayfadaki resim nesnesi icerikten kaldirilir (beyaz kutuyla ortulmez).

Duzenlenen sayfa, ozgun belgeden tek sayfalik yeni bir PDF'ye kopyalanir ve degisiklik orada yapilir; PdfProject bu
sayfayi yeni kaynaga baglar (geri al ile eski kaynaga doner). Form XObject icindeki metin/resim yerinde duzenlenemez.
"""
from __future__ import annotations

import ctypes
import io
import os
import re
import sys

OBJ_TEXT, OBJ_PATH, OBJ_IMAGE, OBJ_SHADING, OBJ_FORM = 1, 2, 3, 4, 5


class EditError(Exception):
    pass


def _lib():
    try:
        import pypdfium2 as pdfium
        import pypdfium2.raw as raw
        return pdfium, raw
    except ImportError as e:  # pragma: no cover
        raise EditError('PDF düzenleme bileşeni (pypdfium2) yüklü değil.') from e


def _addr(obj):
    return ctypes.cast(obj.raw, ctypes.c_void_p).value


def _top_objects(page):
    return list(page.get_objects(max_depth=1))


# ----------------------------------------------------------------------------- yazi tipleri
FONT_FAMILIES = [
    # (anahtar sozcukler, [normal, kalin, italik, kalin-italik] Windows, Linux yedekleri)
    (('times', 'serif', 'roman', 'georgia', 'cambria', 'garamond', 'book'),
     ['times.ttf', 'timesbd.ttf', 'timesi.ttf', 'timesbi.ttf'],
     ['LiberationSerif-Regular.ttf', 'LiberationSerif-Bold.ttf', 'LiberationSerif-Italic.ttf', 'LiberationSerif-BoldItalic.ttf',
      'DejaVuSerif.ttf', 'DejaVuSerif-Bold.ttf', 'DejaVuSerif-Italic.ttf', 'DejaVuSerif-BoldItalic.ttf']),
    (('calibri', 'carlito'),
     ['calibri.ttf', 'calibrib.ttf', 'calibrii.ttf', 'calibriz.ttf'],
     ['Carlito-Regular.ttf', 'Carlito-Bold.ttf', 'Carlito-Italic.ttf', 'Carlito-BoldItalic.ttf']),
    (('verdana',), ['verdana.ttf', 'verdanab.ttf', 'verdanai.ttf', 'verdanaz.ttf'], []),
    (('tahoma',), ['tahoma.ttf', 'tahomabd.ttf', 'tahoma.ttf', 'tahomabd.ttf'], []),
    (('segoe',), ['segoeui.ttf', 'segoeuib.ttf', 'segoeuii.ttf', 'segoeuiz.ttf'], []),
    (('courier', 'mono', 'consolas'),
     ['cour.ttf', 'courbd.ttf', 'couri.ttf', 'courbi.ttf'],
     ['LiberationMono-Regular.ttf', 'LiberationMono-Bold.ttf', 'LiberationMono-Italic.ttf', 'LiberationMono-BoldItalic.ttf',
      'DejaVuSansMono.ttf', 'DejaVuSansMono-Bold.ttf', 'DejaVuSansMono-Oblique.ttf', 'DejaVuSansMono-BoldOblique.ttf']),
    (('arial', 'helvetica', 'sans', ''),
     ['arial.ttf', 'arialbd.ttf', 'ariali.ttf', 'arialbi.ttf'],
     ['LiberationSans-Regular.ttf', 'LiberationSans-Bold.ttf', 'LiberationSans-Italic.ttf', 'LiberationSans-BoldItalic.ttf',
      'DejaVuSans.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans-Oblique.ttf', 'DejaVuSans-BoldOblique.ttf']),
]


def _font_dirs():
    dirs = []
    if sys.platform == 'win32':
        dirs.append(os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'))
        local = os.environ.get('LOCALAPPDATA')
        if local:
            dirs.append(os.path.join(local, 'Microsoft', 'Windows', 'Fonts'))
    for base in ('/usr/share/fonts', '/usr/local/share/fonts', os.path.expanduser('~/.fonts'), '/Library/Fonts'):
        if os.path.isdir(base):
            for root, _d, _f in os.walk(base):
                dirs.append(root)
    return dirs


_FONT_CACHE = {}


_FILE_INDEX = None
FAMILY_ALIASES = {'timesnewroman': 'times', 'couriernew': 'cour', 'arialnarrow': 'arialn', 'bookantiqua': 'bkant',
                  'centurygothic': 'gothic', 'trebuchetms': 'trebuc', 'lucidaconsole': 'lucon', 'comicsansms': 'comic',
                  'palatinolinotype': 'pala', 'garamond': 'gara', 'helvetica': 'arial', 'helveticaneue': 'arial'}


def _file_index():
    global _FILE_INDEX
    if _FILE_INDEX is None:
        idx = {}
        for d in _font_dirs():
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for fn in names:
                if fn.lower().endswith(('.ttf', '.otf')):
                    idx.setdefault(re.sub(r'[^a-z0-9]', '', os.path.splitext(fn)[0].lower()), os.path.join(d, fn))
        _FILE_INDEX = idx
    return _FILE_INDEX


def _family_file(name, bold, italic):
    """Ozgun yazi tipinin ailesi sistemde kuruluysa onun dosyasi (or. ABCDEF+DejaVuSans-Bold -> DejaVuSans-Bold.ttf,
    Arial-BoldMT -> arialbd.ttf, TimesNewRomanPSMT -> times.ttf, Calibri,Bold -> calibrib.ttf)."""
    n = name.split('+')[-1]
    n = re.split(r'[-,]', n)[0]
    fam = re.sub(r'[^a-z0-9]', '', n.lower())
    fam = re.sub(r'(psmt|mt|ps)$', '', fam)
    fam = re.sub(r'(regular|roman|book|medium)$', '', fam) or fam
    fam = FAMILY_ALIASES.get(fam, fam)
    if not fam:
        return None
    if bold and italic:
        suffixes = ['bolditalic', 'boldoblique', 'bi', 'z']
    elif bold:
        suffixes = ['bold', 'bd', 'b', 'semibold']
    elif italic:
        suffixes = ['italic', 'oblique', 'i', 'it']
    else:
        suffixes = ['', 'regular', 'roman', 'book', 'r']
    idx = _file_index()
    for suf in suffixes:
        p = idx.get(fam + suf)
        if p:
            return p
    return None


def pick_font(name='', bold=False, italic=False, serif=False):
    """Ozgun yazi tipine en yakin TrueType dosyasi: once ayni aile (kuruluysa), sonra benzer aile."""
    key = (name.lower(), bool(bold), bool(italic), bool(serif))
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    same = _family_file(name, bold, italic) if name else None
    if same and same.lower().endswith('.ttf'):
        _FONT_CACHE[key] = same
        return same
    n = name.lower().split('+')[-1]
    slot = (1 if bold else 0) + (2 if italic else 0)
    dirs = _font_dirs()
    order = []
    for words, win, lin in FONT_FAMILIES:
        if any(w and w in n for w in words):
            order.append((win, lin))
    serif_fam = FONT_FAMILIES[0]
    sans_fam = FONT_FAMILIES[-1]
    order.append((serif_fam[1], serif_fam[2]) if serif else (sans_fam[1], sans_fam[2]))
    order.append((sans_fam[1], sans_fam[2]))
    for win, lin in order:
        names = [win[slot], win[slot & 1], win[0]] if win else []
        if lin:
            names += [lin[slot], lin[slot & 1], lin[0]]
            if len(lin) > 4:
                names += [lin[4 + slot], lin[4 + (slot & 1)], lin[4]]
        for fn in names:
            for d in dirs:
                p = os.path.join(d, fn)
                if os.path.isfile(p):
                    _FONT_CACHE[key] = p
                    return p
    _FONT_CACHE[key] = None
    return None


# ----------------------------------------------------------------------------- bulma
def _textpage(page):
    return page.get_textpage()


def _char_info(raw, tp, ci):
    x, y = ctypes.c_double(), ctypes.c_double()
    raw.FPDFText_GetCharOrigin(tp.raw, ci, x, y)
    buf = ctypes.create_string_buffer(256)
    flags = ctypes.c_int()
    raw.FPDFText_GetFontInfo(tp.raw, ci, buf, 256, flags)
    name = buf.value.decode('latin-1', 'replace')
    r, g, b, a = (ctypes.c_uint() for _ in range(4))
    color = (0, 0, 0)
    if raw.FPDFText_GetFillColor(tp.raw, ci, r, g, b, a):
        color = (r.value, g.value, b.value)
    weight = raw.FPDFText_GetFontWeight(tp.raw, ci)
    low = name.lower()
    bold = weight >= 600 or any(k in low for k in ('bold', 'black', 'heavy', 'semibold', ',bd'))
    italic = bool(flags.value & 64) or 'italic' in low or 'oblique' in low
    serif = bool(flags.value & 2) or any(k in low for k in ('times', 'serif', 'roman', 'georgia', 'garamond', 'cambria'))
    return {'origin': (x.value, y.value), 'size': float(raw.FPDFText_GetFontSize(tp.raw, ci)) or 11.0, 'font': name,
            'bold': bold, 'italic': italic, 'serif': serif, 'color': '%02x%02x%02x' % color,
            'angle': float(raw.FPDFText_GetCharAngle(tp.raw, ci))}


def find_line(pdf, index, x, y):
    """(x, y) PDF kullanici koordinatinda tiklanan satirin bilgisi ya da None.
    Donus: {'rect': (l, b, r, t), 'text', 'objects': [ust duzey nesne sira no], 'size', 'bold', ... , 'nested': bool}"""
    pdfium, raw = _lib()
    page = pdf[index]
    try:
        tp = _textpage(page)
        ci = tp.get_index(x, y, 6, 6)
        if ci is None or ci < 0:
            return None
        tops = _top_objects(page)
        addr = {_addr(o): k for k, o in enumerate(tops)}
        info = _char_info(raw, tp, ci)
        if abs(info['angle']) > 0.02 and abs(info['angle'] - 6.2832) > 0.02:
            info['rotated'] = True
        anchor = tp.get_textobj(ci)
        k0 = addr.get(_addr(anchor)) if anchor is not None else None
        if k0 is None:
            return {'nested': True, 'rect': _box(tp, ci), 'text': '', 'objects': [], **info}
        l0, b0, r0, t0 = tops[k0].get_bounds()
        size = max(4.0, t0 - b0)
        mode = lambda o: raw.FPDFTextObj_GetTextRenderMode(o.raw)  # noqa: E731
        info['invisible'] = mode(tops[k0]) in (3, 7)         # taranmis sayfanin OCR katmani ya da kirpma metni
        chosen = {k0}
        # ayni satirda (taban cizgisi ortusen) ve yakin olan diger metin nesneleri: satir parcalanmis olabilir
        changed = True
        while changed:
            changed = False
            ls, rs = min(tops[k].get_bounds()[0] for k in chosen), max(tops[k].get_bounds()[2] for k in chosen)
            for k, o in enumerate(tops):
                if k in chosen or o.type != OBJ_TEXT or mode(o) in (3, 7):
                    continue
                l, b, r, t = o.get_bounds()
                vo = min(t, t0) - max(b, b0)
                if vo < 0.55 * min(t - b, size):
                    continue
                gap = l - rs if l >= rs else ls - r if r <= ls else 0
                if gap <= 1.2 * max(info['size'], size * 0.7):
                    chosen.add(k)
                    changed = True
        rect = [min(tops[k].get_bounds()[n] for k in chosen) if n < 2 else max(tops[k].get_bounds()[n] for k in chosen)
                for n in range(4)]
        # nesnelerin karakterlerini sira ile topla
        chars = []
        for c in range(tp.count_chars()):
            o = tp.get_textobj(c)
            if o is not None and addr.get(_addr(o)) in chosen:
                chars.append(c)
        text = ''
        if chars:
            text = tp.get_text_range(chars[0], chars[-1] - chars[0] + 1)
        first = _char_info(raw, tp, chars[0]) if chars else info
        out = dict(info)
        out.update(first)
        out.update({'nested': False, 'rect': tuple(rect), 'text': text.replace('\r\n', '\n').strip(),
                    'objects': sorted(chosen), 'line_height': rect[3] - rect[1]})
        return out
    finally:
        page.close()


def _box(tp, ci):
    l, r, b, t = tp.get_charbox(ci)
    return (l, b, r, t)


def find_image(pdf, index, x, y):
    """Tiklanan noktadaki resim: {'rect', 'objects': [sira no], 'nested': bool} ya da None."""
    pdfium, raw = _lib()
    page = pdf[index]
    try:
        tops = _top_objects(page)
        best = None
        for k, o in enumerate(tops):
            if o.type != OBJ_IMAGE:
                continue
            l, b, r, t = o.get_bounds()
            if l - 1 <= x <= r + 1 and b - 1 <= y <= t + 1:
                area = (r - l) * (t - b)
                if best is None or area < best[0]:
                    best = (area, k, (l, b, r, t))
        if best:
            return {'rect': best[2], 'objects': [best[1]], 'nested': False, 'kind': 'image'}
        # form XObject icindeki resim: form neredeyse yalniz resimse formu kaldirmaya izin ver
        for k, o in enumerate(tops):
            if o.type != OBJ_FORM:
                continue
            l, b, r, t = o.get_bounds()
            if not (l <= x <= r and b <= y <= t):
                continue
            inner = [c for c in page.get_objects(max_depth=4) if c.type == OBJ_IMAGE]
            for c in inner:
                il, ib, ir, it = c.get_bounds()
                if il - 1 <= x <= ir + 1 and ib - 1 <= y <= it + 1:
                    ratio = ((ir - il) * (it - ib)) / max(1.0, (r - l) * (t - b))
                    return {'rect': (il, ib, ir, it), 'objects': [k] if ratio > 0.8 else [], 'nested': ratio <= 0.8,
                            'kind': 'form'}
        return None
    finally:
        page.close()


# ----------------------------------------------------------------------------- degistirme
def _single_page(src_bytes, index):
    pdfium, raw = _lib()
    src = pdfium.PdfDocument(src_bytes)
    new = pdfium.PdfDocument.new()
    new.import_pages(src, [index])
    return src, new


def _save(doc):
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ----------------------------------------------------------------------------- 1.4.2: cerrahi icerik duzenleme
# 1.4.0/1.4.1 sayfayi pdfium ile yeniden uretiyordu (FPDFPage_GenerateContent). Gercek belgelerde bu; renk alanlarini
# (Separation/ICC), saydamlik (ExtGState, yumusak maske), kirpma yollarini ve yazi tipi kodlamalarini bozabiliyor:
# metin bozuk yazi tipiyle, siyah kutu icinde ya da beyaz uzerine beyaz gorunuyordu. Artik ozgun icerik akisi yeniden
# uretilmez: yalniz silinecek metin/resim operatorleri icerikten cikarilir, geri kalan her sey oldugu gibi kalir.
# Yeni metin ayri bir katman (yalniz o metni iceren sayfa) olarak sayfanin ustune birlestirilir.
SHOW_OPS = (b'Tj', b'TJ', b"'", b'"')
POS_OPS = (b'Td', b'TD', b'Tm', b'T*', b"'", b'"', b'ET', b'BT')


def _nonempty_show(operands, op):
    try:
        if op == b'Tj' or op == b"'":
            return len(operands[0]) > 0
        if op == b'"':
            return len(operands[2]) > 0
        if op == b'TJ':
            return any(not isinstance(x, (int, float)) and hasattr(x, '__len__') and len(x) > 0 for x in operands[0])
    except (IndexError, TypeError):
        return False
    return False


def _page_ops(page, pdf):
    from pypdf.generic import ContentStream
    contents = page.get_contents()
    if contents is None:
        return None
    return ContentStream(contents, pdf)


def _xobject_subtype(page, name):
    try:
        res = page['/Resources'].get_object()
        xo = res['/XObject'].get_object()
        return str(xo[name].get_object().get('/Subtype'))
    except Exception:
        return ''


def _pdfium_order(pdf_bytes, index, kind):
    """pdfium'un ust duzey nesne listesinde, verilen turdeki nesnelerin sira numaralari (icerik sirasi)."""
    pdfium, _raw = _lib()
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        page = doc[index]
        return [k for k, o in enumerate(page.get_objects(max_depth=1)) if o.type == kind]
    finally:
        doc.close()


def _one_page_writer(reader, index):
    import pypdf
    w = pypdf.PdfWriter()
    w.add_page(reader.pages[index])
    return w


def _writer_bytes(w):
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def strip_ops(reader, index, pdf_bytes, ordinals, kind):
    """Sayfadan secili ust duzey nesneleri (metin ya da resim) ICERIK AKISINDAN cikarir; baska hicbir sey degismez.
    Donus: (pypdf yazici, sayfa). Esleme dogrulanamazsa EditError."""
    from pypdf.generic import ArrayObject, FloatObject, NameObject, NumberObject
    order = _pdfium_order(pdf_bytes, index, kind)
    targets = {order.index(k) for k in ordinals if k in order}
    if len(targets) != len(set(ordinals)):
        raise EditError('Nesne eşlenemedi.')
    w = _one_page_writer(reader, index)
    page = w.pages[0]
    cs = _page_ops(page, w)
    if cs is None:
        raise EditError('Sayfada içerik yok.')
    ops = cs.operations
    # 1) icerikteki ilgili operatorleri say: pdfium ile birebir eslesmeli
    found = []
    for n, (operands, op) in enumerate(ops):
        if kind == OBJ_TEXT and op in SHOW_OPS and _nonempty_show(operands, op):
            found.append(n)
        elif kind == OBJ_IMAGE and ((op == b'Do' and operands and _xobject_subtype(page, operands[0]) == '/Image')
                                    or op == b'INLINE IMAGE'):
            found.append(n)
    if len(found) != len(order):
        raise EditError('Bu sayfanın içerik yapısı yerinde düzenlemeye uygun değil (%d / %d).' % (len(found), len(order)))
    kill = {found[t] for t in targets}
    # 2) yeniden yaz: silinen metin operatoru sonrakinin konumunu etkiliyorsa gorunmez yap (ilerleme korunur)
    out = []
    tr_stack, tr = [], 0
    for n, (operands, op) in enumerate(ops):
        if op == b'q':
            tr_stack.append(tr)
        elif op == b'Q':
            tr = tr_stack.pop() if tr_stack else 0
        elif op == b'Tr' and operands:
            try:
                tr = int(operands[0])
            except (TypeError, ValueError):
                pass
        if n not in kill:
            out.append((operands, op))
            continue
        if kind == OBJ_IMAGE:
            continue
        # silinen operatorden sonra, yeni konumlandirma olmadan, SILINMEYEN bir metin operatoru geliyorsa
        # (konumu bu operatorun ilerlemesine bagli) bu operatoru silmek yerine gorunmez yap
        follows = False
        for m in range(n + 1, len(ops)):
            op2 = ops[m][1]
            if op2 in SHOW_OPS and op2 not in (b"'", b'"'):
                if m not in kill and _nonempty_show(ops[m][0], op2):
                    follows = True
                    break
                continue
            if op2 in POS_OPS:
                break
        if op == b"'":
            out.append(([], b'T*'))
            if follows:
                out.extend([([NumberObject(3)], b'Tr'), ([operands[0]], b'Tj'), ([NumberObject(tr)], b'Tr')])
            continue
        if op == b'"':
            out.extend([([operands[0]], b'Tw'), ([operands[1]], b'Tc'), ([], b'T*')])
            if follows:
                out.extend([([NumberObject(3)], b'Tr'), ([operands[2]], b'Tj'), ([NumberObject(tr)], b'Tr')])
            continue
        if follows:
            out.extend([([NumberObject(3)], b'Tr'), (operands, op), ([NumberObject(tr)], b'Tr')])
    _ = (ArrayObject, FloatObject, NameObject)
    cs.operations = out
    page.replace_contents(cs)
    return w, page


METRIC_GROUPS = (('arial', 'helvetica', 'liberationsans', 'arimo'), ('times', 'liberationserif', 'tinos'),
                 ('cour', 'liberationmono', 'cousine'), ('calibri', 'carlito'), ('cambria', 'caladea'))


def _metric_compatible(orig_name, font_path):
    """Yedek yazi tipi ozgunle ayni aile ya da ayni olculere sahip (Arial/Helvetica/Liberation Sans gibi) mi?"""
    a = re.sub(r'[^a-z]', '', orig_name.split('+')[-1].lower())
    b = re.sub(r'[^a-z]', '', os.path.splitext(os.path.basename(font_path))[0].lower())
    if not a:
        return True
    fam_a = re.split(r'(bold|italic|oblique|regular|mt|ps)', a)[0]
    if fam_a and b.startswith(fam_a[:6]):
        return True
    return any(any(a.startswith(k) for k in g) and any(b.startswith(k) for k in g) for g in METRIC_GROUPS)


def text_width(text, font_path, size):
    try:
        from PIL import ImageFont
        return ImageFont.truetype(font_path, 100).getlength(text) * size / 100.0
    except Exception:
        return 0.0


def text_layer(width, height, origin, lines, size, color, font_path, lead, hscale=1.0):
    """Yalniz yeni metni iceren tek sayfalik PDF (pdfium ile; ozgun sayfaya dokunmaz). (baytlar, yazi_tipi_adi)."""
    pdfium, raw = _lib()
    doc = pdfium.PdfDocument.new()
    keep = []
    try:
        page = doc.new_page(width, height)
        with open(font_path, 'rb') as f:
            data = f.read()
        fbuf = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
        keep.append(fbuf)
        font = raw.FPDFText_LoadFont(doc.raw, fbuf, len(data), raw.FPDF_FONT_TRUETYPE, 1)
        if not font:
            raise EditError('Yazı tipi yüklenemedi: %s' % os.path.basename(font_path))
        nbuf = ctypes.create_string_buffer(256)
        raw.FPDFFont_GetBaseFontName(font, nbuf, 256)
        base_name = nbuf.value.decode('latin-1', 'replace')
        r, g, b = (int(color[k:k + 2], 16) for k in (0, 2, 4))
        x0, y0 = origin
        for n, line in enumerate(lines):
            if not line.strip():
                continue
            obj = raw.FPDFPageObj_CreateTextObj(doc.raw, font, ctypes.c_float(size))
            ws = (line + '\x00').encode('utf-16-le')
            wbuf = ctypes.create_string_buffer(ws, len(ws))
            keep.append(wbuf)
            raw.FPDFText_SetText(obj, ctypes.cast(wbuf, raw.FPDF_WIDESTRING))
            raw.FPDFPageObj_SetFillColor(obj, r, g, b, 255)
            raw.FPDFPageObj_Transform(obj, hscale, 0, 0, 1, x0, y0 - n * lead)
            raw.FPDFPage_InsertObject(page.raw, obj)
        page.gen_content()
        page.close()
        out = _save(doc)
        raw.FPDFFont_Close(font)
        return _fix_space_mapping(out, base_name), base_name
    finally:
        doc.close()


def remove_objects(reader, index, pdf_bytes, ordinals, kind=OBJ_IMAGE):
    """Ust duzey resim (ya da metin) nesnelerini icerikten cikarir; tek sayfalik PDF baytlari."""
    w, _page = strip_ops(reader, index, pdf_bytes, ordinals, kind)
    return _writer_bytes(w)


def replace_text(reader, index, pdf_bytes, info, new_text, size=None, bold=None, color=None, italic=None):
    """Satirin metin operatorlerini icerikten cikarir, yeni metni ayni taban cizgisine ayri katman olarak yazar."""
    import pypdf
    if info.get('nested'):
        raise EditError('Bu metin bir form/şablon nesnesinin içinde; yerinde düzenlenemez. "Üstüne yaz" aracını kullanın.')
    if info.get('rotated'):
        raise EditError('Döndürülmüş (eğik) metin yerinde düzenlenemez. "Üstüne yaz" aracını kullanın.')
    size = float(size or info.get('size') or 11)
    bold = info.get('bold') if bold is None else bold
    italic = info.get('italic') if italic is None else italic
    color = (color or info.get('color') or '000000').lstrip('#')
    lines = (new_text or '').replace('\r\n', '\n').split('\n')
    w, page = strip_ops(reader, index, pdf_bytes, info['objects'], OBJ_TEXT)
    if any(ln.strip() for ln in lines):
        font_path = pick_font(info.get('font', ''), bold, italic, info.get('serif'))
        if not font_path:
            raise EditError('Uygun bir TrueType yazı tipi bulunamadı (Arial / Liberation / DejaVu).')
        mb = page.mediabox
        # katman sayfasi ozgun sayfanin kullanici uzayiyla ayni koordinatlari kullansin (orijin 0,0'da degilse)
        x0, y0 = float(mb.left), float(mb.bottom)
        width, height = float(mb.right), float(mb.top)
        lead = max(size * 1.2, info.get('line_height') or 0)
        # yedek aile kullaniliyorsa: eski metnin ozgun genisligiyle yedek yazi tipindeki genisligini oranla, yeni metni
        # ayni oranda yatay olcekle (satir uzunlugu ve gorunum ozgune yakin kalir)
        hscale = 1.0
        old = (info.get('text') or '').split('\n')[0]
        w_old = (info.get('rect') or (0, 0, 0, 0))[2] - (info.get('rect') or (0, 0, 0, 0))[0]
        w_sub = text_width(old, font_path, size)
        if old.strip() and w_old > 4 and w_sub > 4 and not _metric_compatible(info.get('font', ''), font_path):
            hscale = max(0.9, min(1.12, w_old / w_sub))
            if abs(hscale - 1.0) < 0.03:
                hscale = 1.0
        layer, _name = text_layer(max(width, 1), max(height, 1), info['origin'], lines, size, color, font_path, lead, hscale)
        lp = pypdf.PdfReader(io.BytesIO(layer)).pages[0]
        _ = (x0, y0)
        page.merge_page(lp, over=True)         # kullanici uzayinda birlesir; /Rotate'li sayfada da dogru konum
    return _writer_bytes(w)


def _cmap_nbsp_to_space(cmap):
    """ToUnicode CMap'te bosluk glifini U+00A0 yerine U+0020'ye esler.
    pdfium ayni glifi once bfchar ile 0020'ye, sonra dizi bicimli bfrange ile 00A0'a esleyebiliyor; bu durumda dizideki
    o glife denk gelen 00A0 duzeltilir. Tekil "<g> <00A0>" eslemeleri de duzeltilir."""
    space = {int(g, 16) for g in re.findall(rb'(?m)^\s*<([0-9A-Fa-f]+)>\s+<0020>\s*$', cmap)}

    def arr(m):
        start = int(m.group(1), 16)
        items = re.findall(rb'<[0-9A-Fa-f]+>', m.group(3))
        out = [b'<0020>' if it.upper() == b'<00A0>' and (start + k in space or not space) else it for k, it in enumerate(items)]
        return m.group(0)[:m.start(3) - m.start(0)] + b' '.join(out) + m.group(0)[m.end(3) - m.start(0):]
    cmap = re.sub(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[([^\]]*)\]', arr, cmap)
    return re.sub(rb'(?m)^(\s*<([0-9A-Fa-f]+)>\s+(?:<\2>\s+)?)<00[aA]0>(\s*)$', rb'\1<0020>\3', cmap)


def _fix_space_mapping(data, base_name):
    """Arial gibi yazi tiplerinde bosluk ve bolunmez bosluk ayni glifi kullanir; pdfium ToUnicode'da glifi U+00A0'a
    esler ve kopyalanan / aranan metinde bosluklar NBSP olur. Yalniz eklenen yazi tipinin eslemesini U+0020 yapar."""
    try:
        import pypdf
        from pypdf.generic import NameObject
        w = pypdf.PdfWriter(clone_from=pypdf.PdfReader(io.BytesIO(data)))
        changed = False
        for page in w.pages:
            fonts = (page.get('/Resources') or {}).get('/Font') or {}
            fonts = fonts.get_object() if hasattr(fonts, 'get_object') else fonts
            for _k, ref in fonts.items():
                f = ref.get_object()
                if str(f.get('/BaseFont', '')).lstrip('/').split('+')[-1] != base_name.split('+')[-1] or '/ToUnicode' not in f:
                    continue
                cmap = f['/ToUnicode'].get_object()
                raw_cmap = cmap.get_data()
                fixed = _cmap_nbsp_to_space(raw_cmap)
                if fixed != raw_cmap:
                    cmap.set_data(fixed)
                    changed = True
        if not changed:
            return data
        _ = NameObject
        buf = io.BytesIO()
        w.write(buf)
        return buf.getvalue()
    except Exception:
        return data
