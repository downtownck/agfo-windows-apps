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
    low = name.lower()
    if any(k in low for k in ('black', 'heavy', 'extrabold', 'ultrabold')) and not serif:
        for p in (_file_index().get('ariblk'), _file_index().get('arialblack')):
            if p:
                _FONT_CACHE[key] = p
                return p
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


def _h(handle):
    return ctypes.cast(handle, ctypes.c_void_p).value


def page_tree(page):
    """Sayfanin nesne agaci (form XObject'lerin ici dahil).
    Donus: (paths: {tutamac_adresi: yol}, kids: {ust_yol: [(sira, tur, tutamac), ...]}).
    Yol, ust duzeyden itibaren sira numaralari dizisidir: (12,) ust duzey; (3, 40) 3. nesne olan formun 40. cocugu."""
    _pdfium, raw = _lib()
    paths, kids = {}, {}

    def walk(handles, prefix):
        lst = []
        for k, h in enumerate(handles):
            t = raw.FPDFPageObj_GetType(h)
            path = prefix + (k,)
            paths[_h(h)] = path
            lst.append((k, t, h))
            if t == OBJ_FORM:
                n = raw.FPDFFormObj_CountObjects(h)
                walk([raw.FPDFFormObj_GetObject(h, i) for i in range(max(0, n))], path)
        kids[prefix] = lst

    n = raw.FPDFPage_CountObjects(page.raw)
    walk([raw.FPDFPage_GetObject(page.raw, i) for i in range(max(0, n))], ())
    return paths, kids


def _char_size(raw, tp, ci, fallback=11.0):
    """Gorunen yazi boyutu (pt) = Tf boyutu x karakterin etkin matrisi (CTM, Tm, form matrisleri dahil).
    Tasarim programlari '1 Tf' + olcekli matris; tarayici ciktilari form icinde olcekli matris kullanir."""
    try:
        m = raw.FS_MATRIX()
        fs = float(raw.FPDFText_GetFontSize(tp.raw, ci))
        if raw.FPDFText_GetMatrix(tp.raw, ci, ctypes.byref(m)):
            fs *= abs(m.a * m.d - m.b * m.c) ** 0.5
        return round(fs, 2) if fs > 0.5 else fallback
    except Exception:
        return fallback


def text_objects(page, tp=None):
    """Sayfadaki (formlar dahil) her metin nesnesi: {yol: {'chars', 'box' (sayfa koordinati), 'origin', 'size', 'text', 'mode'}}."""
    _pdfium, raw = _lib()
    tp = tp or page.get_textpage()
    paths, kids = page_tree(page)
    handles = {path: h for prefix, lst in kids.items() for (k, t, h) in lst for path in [prefix + (k,)]}
    objs = {}
    for c in range(tp.count_chars()):
        o = tp.get_textobj(c)
        if o is None:
            continue
        path = paths.get(_h(o.raw))
        if path is None:
            continue
        e = objs.setdefault(path, {'chars': [], 'box': None})
        e['chars'].append(c)
        l, b, r, t = tp.get_charbox(c)        # pypdfium2: (sol, alt, sag, ust)
        if r > l or t > b:
            e['box'] = [l, b, r, t] if e['box'] is None else [min(e['box'][0], l), min(e['box'][1], b),
                                                                max(e['box'][2], r), max(e['box'][3], t)]
    for path, e in objs.items():
        c0 = e['chars'][0]
        x, y = ctypes.c_double(), ctypes.c_double()
        raw.FPDFText_GetCharOrigin(tp.raw, c0, x, y)
        e['origin'] = (x.value, y.value)
        e['size'] = _char_size(raw, tp, c0)
        e['text'] = ''.join(chr(raw.FPDFText_GetUnicode(tp.raw, c)) for c in e['chars'])
        h = handles.get(path)
        e['mode'] = raw.FPDFTextObj_GetTextRenderMode(h) if h else 0
        if e['box'] is None:
            e['box'] = [x.value, y.value, x.value, y.value + e['size']]
    return objs, kids


def group_line(objs, seed):
    """seed nesnesiyle ayni satirda (taban cizgisi ortusen) ve yatay olarak bitisik metin nesneleri."""
    s0 = objs[seed]
    size = max(3.0, s0['size'])
    y0 = s0['origin'][1]
    chosen = {seed}
    changed = True
    while changed:
        changed = False
        ls = min(objs[k]['box'][0] for k in chosen)
        rs = max(objs[k]['box'][2] for k in chosen)
        for k, o in objs.items():
            if k in chosen or o['mode'] in (3, 7) or not o['text'].strip() and False:
                continue
            if abs(o['origin'][1] - y0) > 0.35 * size or abs(o['size'] - size) > 0.45 * size:
                continue
            l, r = o['box'][0], o['box'][2]
            gap = l - rs if l >= rs else ls - r if r <= ls else 0
            if gap <= 1.3 * size:
                chosen.add(k)
                changed = True
    return chosen


def blank_paths(objs, kids):
    """Metin sayfasinda karakteri olmayan metin nesneleri (tarayici ciktilarinda sozcuk araliklari boyledir)."""
    return {prefix + (k,) for prefix, lst in kids.items() for (k, t, _h) in lst if t == OBJ_TEXT and prefix + (k,) not in objs}


def line_text(objs, chosen, blank=()):
    """Satir metni. Bosluk: acik bosluk nesnesi ya da satirdaki olagan harf araligindan belirgin buyuk bosluk
    (aralikli yazilmis basliklarda sabit esik sozcukleri birlestiriyordu)."""
    order = sorted(chosen, key=lambda k: objs[k]['box'][0])
    gaps = []
    for a, b in zip(order, order[1:]):
        if objs[a]['text'].strip() and objs[b]['text'].strip():
            gaps.append(objs[b]['box'][0] - objs[a]['box'][2])
    base = sorted(gaps)[len(gaps) // 3] if len(gaps) >= 4 else 0.0
    parts, prev, prev_k = [], None, None
    for k in order:
        o = objs[k]
        sz = max(3.0, (prev or o)['size'])
        if prev is not None and parts and not parts[-1].endswith(' ') and not o['text'].startswith(' '):
            gap = o['box'][0] - prev['box'][2]
            a, b = prev_k, k
            between = blank and a[:-1] == b[:-1] and any(a[:-1] + (j,) in blank for j in range(min(a[-1], b[-1]) + 1, max(a[-1], b[-1])))
            if between or gap > max(0.22 * sz, base + 0.17 * sz):
                parts.append(' ')
        parts.append(o['text'])
        prev, prev_k = o, k
    return re.sub(r'\s+', ' ', ''.join(parts)).strip()


_OBJ_CACHE = {}


def _cached_objects(pdf, index, page, tp):
    """text_objects sonucu belge+sayfa basina saklanir: fare gezinirken her 70 ms'de tum karakterler taranmasin.
    Duzenlenen sayfa yeni bir kaynak (yeni belge nesnesi) oldugundan eski kayit kendiliginden gecersiz kalir."""
    key = (id(pdf), index)
    hit = _OBJ_CACHE.get(key)
    if hit is not None and hit[0] is pdf:
        return hit[1:]
    objs, kids = text_objects(page, tp)
    char_path = {c: path for path, e in objs.items() for c in e['chars']}
    if len(_OBJ_CACHE) > 16:
        _OBJ_CACHE.clear()
    _OBJ_CACHE[key] = (pdf, objs, blank_paths(objs, kids), char_path)
    return objs, _OBJ_CACHE[key][2], char_path


def find_line(pdf, index, x, y):
    """(x, y) PDF kullanici koordinatinda tiklanan satirin bilgisi ya da None. Form XObject icindeki metin de bulunur
    (tarayicidan yazdirilmis PDF'ler, sertifikalar). Donus: {'rect', 'text', 'objects': [yol], 'size', 'bold', ...}"""
    _pdfium, raw = _lib()
    page = pdf[index]
    try:
        tp = _textpage(page)
        ci = tp.get_index(x, y, 6, 6)
        if ci is None or ci < 0:
            return None
        objs, blank, char_path = _cached_objects(pdf, index, page, tp)
        anchor = None
        for c in (ci, ci - 1, ci + 1):
            if c in char_path:
                anchor, ci = char_path[c], c
                break
        if anchor is None:
            return None
        info = _char_info(raw, tp, ci)
        if abs(info['angle']) > 0.02 and abs(info['angle'] - 6.2832) > 0.02:
            info['rotated'] = True
        info['invisible'] = objs[anchor]['mode'] in (3, 7)
        chosen = group_line(objs, anchor) if not info['invisible'] else {anchor}
        boxes = [objs[k]['box'] for k in chosen]
        rect = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        first = min(chosen, key=lambda k: objs[k]['box'][0])
        out = dict(info)
        out.update(_char_info(raw, tp, objs[first]['chars'][0]))
        out['size'] = objs[first]['size']
        out['origin'] = objs[first]['origin']
        out.update({'nested': False, 'rect': rect, 'text': line_text(objs, chosen, blank), 'objects': sorted(chosen),
                    'line_height': rect[3] - rect[1], 'invisible': info['invisible'], 'rotated': info.get('rotated', False)})
        return out
    finally:
        page.close()


def _box(tp, ci):
    return tuple(tp.get_charbox(ci))


def _matrix(raw, h):
    m = raw.FS_MATRIX()
    if raw.FPDFPageObj_GetMatrix(h, ctypes.byref(m)):
        return (m.a, m.b, m.c, m.d, m.e, m.f)
    return (1, 0, 0, 1, 0, 0)


def _apply(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def _compose(m1, m2):
    """m1 sonra m2 (PDF satir-vektor kurali)."""
    a, b, c, d, e, f = m1
    A, B, C, D, E, F = m2
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D, e * A + f * C + E, e * B + f * D + F)


def find_image(pdf, index, x, y):
    """Tiklanan noktadaki resim (form XObject icindekiler dahil): {'rect', 'objects': [yol], 'kind'} ya da None."""
    _pdfium, raw = _lib()
    page = pdf[index]
    try:
        _paths, kids = page_tree(page)
        best = None

        def visit(prefix, ctm):
            nonlocal best
            for k, t, h in kids.get(prefix, []):
                path = prefix + (k,)
                if t == OBJ_FORM:
                    visit(path, _compose(_matrix(raw, h), ctm))
                    continue
                if t != OBJ_IMAGE:
                    continue
                l, b, r, tt = (ctypes.c_float() for _ in range(4))
                if not raw.FPDFPageObj_GetBounds(h, l, b, r, tt):
                    continue
                pts = [_apply(ctm, px, py) for px, py in ((l.value, b.value), (r.value, b.value), (l.value, tt.value), (r.value, tt.value))]
                L, R = min(p[0] for p in pts), max(p[0] for p in pts)
                B, T = min(p[1] for p in pts), max(p[1] for p in pts)
                if L - 1 <= x <= R + 1 and B - 1 <= y <= T + 1:
                    area = (R - L) * (T - B)
                    if best is None or area < best[0]:
                        best = (area, path, (L, B, R, T))
        visit((), (1, 0, 0, 1, 0, 0))
        if best:
            return {'rect': best[2], 'objects': [best[1]], 'nested': len(best[1]) > 1, 'kind': 'image'}
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


def _one_page_writer(reader, index):
    import pypdf
    w = pypdf.PdfWriter()
    w.add_page(reader.pages[index])
    return w


def _writer_bytes(w):
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _xsub(res, name):
    try:
        return str(res['/XObject'].get_object()[name].get_object().get('/Subtype'))
    except Exception:
        return ''


def _count_ops(ops, res, kind):
    found = []
    for n, (operands, op) in enumerate(ops):
        if kind == OBJ_TEXT and op in SHOW_OPS and _nonempty_show(operands, op):
            found.append(n)
        elif kind == OBJ_IMAGE and ((op == b'Do' and operands and _xsub(res, operands[0]) == '/Image') or op == b'INLINE IMAGE'):
            found.append(n)
        elif kind == OBJ_FORM and op == b'Do' and operands and _xsub(res, operands[0]) == '/Form':
            found.append(n)
    return found


def _resolve(w, page, kids, prefix, cache):
    """Yolun icerik akisi: () sayfa; (k,) k. ust duzey nesne olan formun akisi ... Donus: (sahip, ContentStream, kaynaklar)."""
    from pypdf.generic import ContentStream
    if prefix in cache:
        return cache[prefix]
    if prefix == ():
        contents = page.get_contents()
        if contents is None:
            raise EditError('Sayfada içerik yok.')
        res = page.get('/Resources')
        out = ('page', ContentStream(contents, w), res.get_object() if res is not None else {})
    else:
        _owner, pcs, pres = _resolve(w, page, kids, prefix[:-1], cache)
        forms = [k for k, t, _h in kids[prefix[:-1]] if t == OBJ_FORM]
        dos = _count_ops(pcs.operations, pres, OBJ_FORM)
        if len(dos) != len(forms) or prefix[-1] not in forms:
            raise EditError('Form nesneleri eşlenemedi (%d / %d).' % (len(dos), len(forms)))
        name = pcs.operations[dos[forms.index(prefix[-1])]][0][0]
        stream = pres['/XObject'].get_object()[name].get_object()
        fres = stream.get('/Resources')
        out = (stream, ContentStream(stream, w), fres.get_object() if fres is not None else pres)
    cache[prefix] = out
    return out


def _rewrite(ops, kill, kind):
    from pypdf.generic import NumberObject
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
    return out


def strip_ops(reader, index, pdf_bytes, paths, kind):
    """Secili nesneleri (metin ya da resim; ust duzey ya da form XObject icinde) ICERIK AKISINDAN cikarir; baska
    hicbir sey degismez. paths: yol listesi (eski surumlerle uyum icin tamsayi = ust duzey sira no).
    Donus: (pypdf yazici, sayfa). Esleme dogrulanamazsa EditError."""
    pdfium, _raw = _lib()
    paths = [(p,) if isinstance(p, int) else tuple(p) for p in paths]
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        pg = doc[index]
        _paths, kids_h = page_tree(pg)
        kids = {k: [(o, t, None) for (o, t, _h) in v] for k, v in kids_h.items()}
        pg.close()
    finally:
        doc.close()
    w = _one_page_writer(reader, index)
    page = w.pages[0]
    groups = {}
    for p in paths:
        groups.setdefault(p[:-1], set()).add(p[-1])
    cache = {}
    # derin akislari once coz (ust akis degismeden once Do sayimi yapilsin)
    resolved = {pre: _resolve(w, page, kids, pre, cache) for pre in sorted(groups, key=len)}
    for prefix, ords in groups.items():
        owner, cs, res = resolved[prefix]
        same = [k for k, t, _h in kids.get(prefix, []) if t == kind]
        if not ords <= set(same):
            raise EditError('Nesne eşlenemedi.')
        found = _count_ops(cs.operations, res, kind)
        if len(found) != len(same):
            raise EditError('Bu sayfanın içerik yapısı yerinde düzenlemeye uygun değil (%d / %d).' % (len(found), len(same)))
        kill = {found[same.index(k)] for k in ords}
        cs.operations = _rewrite(cs.operations, kill, kind)
        if owner == 'page':
            page.replace_contents(cs)
        else:
            data = cs.get_data()
            try:
                owner.set_data(data)
            except Exception:
                from pypdf.generic import NameObject
                for key in ('/Filter', '/DecodeParms'):
                    if NameObject(key) in owner:
                        del owner[NameObject(key)]
                owner._data = data
                owner[NameObject('/Length')] = __import__('pypdf').generic.NumberObject(len(data))
            if 'decoded_self' in getattr(owner, '__dict__', {}):
                owner.decoded_self = None
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


def text_layer(width, height, origin, lines, size, color, font_path, lead, hscale=1.0, tc=0.0):
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
        if abs(tc) > 0.01:
            out = _add_char_spacing(out, tc)
        return _fix_space_mapping(out, base_name), base_name
    finally:
        doc.close()


def _add_char_spacing(data, tc):
    """Katman sayfasindaki her yazi tipi secimine (Tf) harf araligi (Tc) ekler."""
    try:
        import pypdf
        from pypdf.generic import FloatObject
        w = pypdf.PdfWriter(clone_from=pypdf.PdfReader(io.BytesIO(data)))
        page = w.pages[0]
        cs = _page_ops(page, w)
        ops = []
        for operands, op in cs.operations:
            ops.append((operands, op))
            if op == b'Tf':
                ops.append(([FloatObject(round(tc, 4))], b'Tc'))
        cs.operations = ops
        page.replace_contents(cs)
        return _writer_bytes(w)
    except Exception:
        return data


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
        # eski metnin sayfadaki genisligi ile secilen yazi tipindeki genisligi farkini harf araligi (Tc) olarak uygula:
        # tasarim belgelerindeki genis harf araligi (tracking) ve yedek yazi tipi farki boylece korunur, glif bozulmaz
        # Ayni aile / ayni olculu yazi tipinde fark harf araligidir (tracking) -> Tc. Farkli aileye dusulduyse (ozgun
        # yazi tipi kurulu degil) fark glif genisligidir -> yatay olcek; boylece satir ozgun genislige ve gorunume yakin kalir.
        tc, hscale = 0.0, 1.0
        old = (info.get('text') or '').split('\n')[0]
        w_old = (info.get('rect') or (0, 0, 0, 0))[2] - (info.get('rect') or (0, 0, 0, 0))[0]
        w_sub = text_width(old, font_path, size)
        if len(old.strip()) > 2 and w_old > 4 and w_sub > 4 and '\t' not in old:
            if _metric_compatible(info.get('font', ''), font_path):
                tc = (w_old - w_sub) / max(1, len(old) - 1)
                tc = max(-0.06 * size, min(0.3 * size, tc))
                if abs(tc) < 0.015 * size:
                    tc = 0.0
            else:
                hscale = max(0.85, min(1.35, w_old / w_sub))
                if abs(hscale - 1.0) < 0.03:
                    hscale = 1.0
        layer, _name = text_layer(max(width, 1), max(height, 1), info['origin'], lines, size, color, font_path, lead, hscale, tc)
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
