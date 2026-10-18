# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4.6 - PDF sayfa duzeni: paragraf cikarma, duzeni koruyan ceviri ve bicimli belgeye donusturme.

* extract_layout(): sayfadaki metin nesnelerini (form XObject icindekiler dahil) satirlara, satirlari paragraflara
  ayirir; her paragrafin kutusu, yazi tipi, boyutu, rengi, hizasi ve satir araligi bilinir.
* translate_pdf(): paragraflar cevrilir; ozgun metin icerikten cikarilir (sayfanin geri kalani aynen kalir) ve ceviri
  ayni kutuya, ayni yazi tipi/renk/hizayla, gerekirse kucultulerek yazilir. Icerik eslenemeyen sayfada ozgun paragraf
  zemin rengiyle ortulup ceviri ustune yazilir.
* layout_blocks(): PDF'i basliklari (yazi boyutuna gore), kalinlari ve resimleriyle bicimli belgeye cevirir.
"""
from __future__ import annotations

import ctypes
import io
import re
from collections import Counter

import agfo_pdf_edit as E
import agfo_richdoc as R


# ----------------------------------------------------------------------------- cikarma
def extract_layout(pdf, index):
    _pdfium, raw = E._lib()
    page = pdf[index]
    try:
        width, height = page.get_size()
        tp = page.get_textpage()
        objs, kids = E.text_objects(page, tp)
        blank = E.blank_paths(objs, kids)
        # bosluk nesneleri de tutulur: tarayici ciktilarinda sozcuk araliklari ayri nesnelerdir
        live = {k: o for k, o in objs.items() if o['mode'] not in (3, 7) and o['text']}
        lines = []
        remaining = {k for k in live if live[k]['text'].strip()}
        while remaining:
            seed = max(remaining, key=lambda k: (live[k]['origin'][1], -live[k]['box'][0]))
            pool = {k: live[k] for k in live if k in remaining or not live[k]['text'].strip()}
            grp = E.group_line(pool, seed)
            remaining -= grp
            grp = {k for k in grp if live[k]['text'].strip()} | {k for k in grp if not live[k]['text'].strip()}
            ink = [k for k in grp if live[k]['text'].strip()]
            if not ink:
                continue
            for k in grp:
                if not live[k]['text'].strip():
                    live[k] = dict(live[k], mode=7)    # bir kez kullanilsin
            boxes = [live[k]['box'] for k in ink]
            first = min(ink, key=lambda k: live[k]['box'][0])
            fi = E._char_info(raw, tp, live[first]['chars'][0])
            text = E.line_text(live, grp, blank)
            if not text:
                continue
            lines.append({'objects': sorted(grp), 'text': text,
                          'rect': (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)),
                          'origin': live[first]['origin'], 'size': live[first]['size'], 'font': fi['font'], 'bold': fi['bold'],
                          'italic': fi['italic'], 'serif': fi['serif'], 'color': fi['color'],
                          'rotated': abs(fi['angle']) > 0.02 and abs(fi['angle'] - 6.2832) > 0.02})
        for L in lines:   # ayni taban cizgisinde baska satir var: tablo satiri (hiza tahmini yapilmaz)
            L['sib'] = any(M is not L and abs(M['origin'][1] - L['origin'][1]) < 0.3 * L['size'] for M in lines)
            L['row'] = L['sib'] and (L['rect'][2] - L['rect'][0]) < 0.3 * width
        for L in lines:   # satirin yatayda ne kadar genisleyebilecegi (ayni hizadaki komsulara kadar)
            same = [M for M in lines if M is not L and abs(M['origin'][1] - L['origin'][1]) < 0.6 * L['size']]
            L['lim'] = (max([M['rect'][2] + 6 for M in same if M['rect'][2] <= L['rect'][0] + 1] + [8.0]),
                        min([M['rect'][0] - 6 for M in same if M['rect'][0] >= L['rect'][2] - 1] + [width - 8.0]))
        paras = _paragraphs(lines, width)
        return {'width': width, 'height': height, 'paras': paras}
    finally:
        page.close()


def t_low(text):
    c = text.lstrip()[:1]
    return c.isalpha() and c.islower()


def _paragraphs(lines, page_w):
    lines = sorted(lines, key=lambda L: (-L['origin'][1], L['rect'][0]))
    paras = []
    for L in lines:
        target = None
        for P in reversed(paras[-6:]):
            last = P['lines'][-1]
            s = max(3.0, P['size'])
            if L['rotated'] or last['rotated'] or L.get('row'):
                continue
            if abs(L['size'] - P['size']) > 0.12 * s or L['bold'] != P['bold'] or L['color'] != P['color']:
                continue
            gap = last['origin'][1] - L['origin'][1]
            if not (0.75 * s <= gap <= 1.9 * s):
                continue
            l1, r1 = P['rect'][0], P['rect'][2]
            l2, r2 = L['rect'][0], L['rect'][2]
            overlap = min(r1, r2) - max(l1, l2)
            same_left = abs(l2 - l1) < 1.5 * s
            same_center = abs((l2 + r2) / 2 - (l1 + r1) / 2) < 1.5 * s
            # tablo/etiket sutunlari: kisa, buyuk harfle baslayan alt alta satirlar ayri paragraftir; yalniz
            # sarilmis metin (uzun satirlar ya da devam eden cumle) birlestirilir
            wrapped = min(last['rect'][2] - last['rect'][0], r2 - l2) >= 0.3 * page_w or (t_low(L['text']) and not L.get('sib')) \
                or (last['rect'][2] - last['rect'][0] >= 0.22 * page_w and last['text'].rstrip()[-1:] in ',;-–(&')
            if overlap > 0 and (same_left or same_center) and wrapped:
                target = P
                break
        if target is None:
            paras.append({'lines': [L], 'size': L['size'], 'bold': L['bold'], 'color': L['color'], 'font': L['font'],
                          'italic': L['italic'], 'serif': L['serif'], 'rect': L['rect'], 'rotated': L['rotated']})
        else:
            target['lines'].append(L)
            r = target['rect']
            target['rect'] = (min(r[0], L['rect'][0]), min(r[1], L['rect'][1]), max(r[2], L['rect'][2]), max(r[3], L['rect'][3]))
    for P in paras:
        ls = P['lines']
        text = ''
        for L in ls:
            t = L['text']
            if text.endswith('-') and t[:1].islower():
                text = text[:-1] + t
            else:
                text = (text + ' ' + t).strip()
        P['text'] = text
        P['objects'] = [o for L in ls for o in L['objects']]
        P['lead'] = (ls[0]['origin'][1] - ls[-1]['origin'][1]) / (len(ls) - 1) if len(ls) > 1 else P['size'] * 1.2
        lefts = [L['rect'][0] for L in ls]
        centers = [(L['rect'][0] + L['rect'][2]) / 2 for L in ls]
        rights = [L['rect'][2] for L in ls]
        s = P['size']
        if len(ls) > 1:
            spread = lambda v: max(v) - min(v)  # noqa: E731
            if spread(lefts) < 0.8 * s:
                P['align'] = 'left'
            elif spread(centers) < 0.8 * s:
                P['align'] = 'center'
            elif spread(rights) < 0.8 * s:
                P['align'] = 'right'
            else:
                P['align'] = 'left'
        else:
            c = centers[0]
            P['align'] = 'center' if abs(c - page_w / 2) < 0.02 * page_w and lefts[0] > 0.12 * page_w and not ls[0].get('row') else 'left'
        P['origin'] = ls[0]['origin']
        P['center'] = sum(centers) / len(centers)
        P['right'] = max(rights)
    # paragrafin altindaki bos alan: ceviri uzarsa kucultmeden once bu alana tasabilir
    for P in paras:
        below = [P['rect'][1] - Q['rect'][3] for Q in paras if Q is not P and Q['rect'][3] <= P['rect'][1] + 1
                 and min(P['rect'][2], Q['rect'][2]) - max(P['rect'][0], Q['rect'][0]) > 0]
        P['below'] = max(0.0, min(below) if below else P['rect'][1] - 24)
    # tek satirlik paragraflarda hiza, ayni bicimdeki komsu satirlardan (etiket sutunlari) anlasilir
    singles = [P for P in paras if len(P['lines']) == 1 and not P['rotated']]
    for P in singles:
        s = max(3.0, P['size'])
        votes = Counter()
        for Q in singles:
            if Q is P or abs(Q['size'] - P['size']) > 0.1 * s or Q['color'] != P['color'] or Q['bold'] != P['bold']:
                continue
            if abs(Q['origin'][1] - P['origin'][1]) > 6 * s:
                continue
            dl, dr = abs(Q['rect'][0] - P['rect'][0]), abs(Q['rect'][2] - P['rect'][2])
            dc = abs(Q['center'] - P['center'])
            if dl < 0.3 * s and dr > s:
                votes['left'] += 1
            elif dr < 0.3 * s and dl > s:
                votes['right'] += 1
            elif dc < 0.3 * s and dl > s:
                votes['center'] += 1
        if votes:
            P['align'] = votes.most_common(1)[0][0]
    return paras


# ----------------------------------------------------------------------------- yerlestirme
def _wrap(text, font_path, size, width):
    words = text.split(' ')
    lines, cur = [], ''
    for wd in words:
        trial = (cur + ' ' + wd).strip()
        if not cur or E.text_width(trial, font_path, size) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines or ['']


def fit_paragraph(P, text, font_path, page_w):
    """(boyut, satirlar) - ceviri paragrafin kutusuna sigacak sekilde sarilir, gerekirse %60'a kadar kucultulur."""
    size = P['size']
    lines_n = len(P['lines'])
    width = max(P['rect'][2] - P['rect'][0], 1.0)
    lo = max(L.get('lim', (8.0, page_w - 8.0))[0] for L in P['lines'])
    hi = min(L.get('lim', (8.0, page_w - 8.0))[1] for L in P['lines'])
    if P['align'] == 'center':
        room = 2 * min(P['center'] - lo, hi - P['center'])
    elif P['align'] == 'right':
        room = P['right'] - lo
    else:
        room = hi - P['rect'][0]
    room = max(room, width)
    if lines_n == 1:
        width_cap = min(width * 1.12 + 4 * size, room)
        for k in (1.0, 0.94, 0.88, 0.82, 0.76, 0.7, 0.64, 0.6):
            if E.text_width(text, font_path, size * k) <= width_cap:
                return size * k, [text]
        # cok uzun tek satir: en kucuk boyutta iki satira bol
        return size * 0.6, _wrap(text, font_path, size * 0.6, width_cap)
    extra = int(max(0.0, P.get('below', 0.0) - 0.6 * P['lead']) // max(1.0, P['lead']))
    avail = (lines_n + min(extra, max(1, lines_n // 2))) * P['lead'] * 1.06
    for k in (1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6):
        wrapped = _wrap(text, font_path, size * k, min(width * 1.02, room))
        if len(wrapped) * P['lead'] * k <= avail:
            return size * k, wrapped
    return size * 0.6, _wrap(text, font_path, size * 0.6, width * 1.02)


def place(P, text, font_path, page_w):
    size, lines = fit_paragraph(P, text, font_path, page_w)
    k = size / max(0.1, P['size'])
    lead = P['lead'] * k if len(P['lines']) > 1 else size * 1.2
    x0, y0 = P['origin']
    items = []
    for n, line in enumerate(lines):
        w = E.text_width(line, font_path, size)
        if P['align'] == 'center':
            x = P['center'] - w / 2
        elif P['align'] == 'right':
            x = P['right'] - w
        else:
            x = x0
        items.append({'x': x, 'y': y0 - n * lead, 'text': line, 'size': size, 'color': P['color'], 'font': font_path})
    return items


def layer_pdf(width, height, items, boxes=()):
    """Birden cok yazi tipi/boyut/renkte metin (ve istenirse ortu kutulari) iceren tek sayfalik katman PDF'i."""
    pdfium, raw = E._lib()
    doc = pdfium.PdfDocument.new()
    keep, fonts, names = [], {}, set()
    try:
        page = doc.new_page(width, height)
        for (l, b, r, t, color) in boxes:
            path = raw.FPDFPageObj_CreateNewRect(ctypes.c_float(l), ctypes.c_float(b), ctypes.c_float(r - l), ctypes.c_float(t - b))
            cr, cg, cb = (int(color[k:k + 2], 16) for k in (0, 2, 4))
            raw.FPDFPageObj_SetFillColor(path, cr, cg, cb, 255)
            raw.FPDFPath_SetDrawMode(path, 1, 0)          # FPDF_FILLMODE_ALTERNATE, cizgi yok
            raw.FPDFPage_InsertObject(page.raw, path)
        for it in items:
            if not it['text'].strip():
                continue
            fp = it['font']
            if fp not in fonts:
                with open(fp, 'rb') as f:
                    data = f.read()
                fbuf = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
                keep.append(fbuf)
                font = raw.FPDFText_LoadFont(doc.raw, fbuf, len(data), raw.FPDF_FONT_TRUETYPE, 1)
                if not font:
                    raise E.EditError('Yazı tipi yüklenemedi: %s' % fp)
                nbuf = ctypes.create_string_buffer(256)
                raw.FPDFFont_GetBaseFontName(font, nbuf, 256)
                names.add(nbuf.value.decode('latin-1', 'replace'))
                fonts[fp] = font
            obj = raw.FPDFPageObj_CreateTextObj(doc.raw, fonts[fp], ctypes.c_float(it['size']))
            ws = (it['text'] + '\x00').encode('utf-16-le')
            wbuf = ctypes.create_string_buffer(ws, len(ws))
            keep.append(wbuf)
            raw.FPDFText_SetText(obj, ctypes.cast(wbuf, raw.FPDF_WIDESTRING))
            c = (it.get('color') or '000000').lstrip('#')
            raw.FPDFPageObj_SetFillColor(obj, int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255)
            raw.FPDFPageObj_Transform(obj, 1, 0, 0, 1, it['x'], it['y'])
            raw.FPDFPage_InsertObject(page.raw, obj)
        page.gen_content()
        page.close()
        out = E._save(doc)
        for f in fonts.values():
            raw.FPDFFont_Close(f)
        for n in names:
            out = E._fix_space_mapping(out, n)
        return out
    finally:
        doc.close()


def _bg_colors(pdf, index, rects, page_h):
    """Her kutunun hemen disindaki halkadan zemin rengi (ortu yedegi icin)."""
    page = pdf[index]
    try:
        k = 2.0
        img = page.render(scale=k).to_pil().convert('RGB')
    finally:
        page.close()
    out = []
    for (l, b, r, t) in rects:
        A, B = int(l * k) - 4, int((page_h - t) * k) - 4
        C, D = int(r * k) + 4, int((page_h - b) * k) + 4
        A, B, C, D = max(0, A), max(0, B), min(img.width - 1, C), min(img.height - 1, D)
        ring = [img.getpixel((x, B)) for x in range(A, C, 2)] + [img.getpixel((x, D)) for x in range(A, C, 2)] + \
               [img.getpixel((A, y)) for y in range(B, D, 2)] + [img.getpixel((C, y)) for y in range(B, D, 2)]
        out.append('%02x%02x%02x' % (Counter(ring).most_common(1)[0][0] if ring else (255, 255, 255)))
    return out


def translate_page(reader, index, pdf_bytes, pdf, layout, translations):
    """Bir sayfanin paragraflarini ceviriyle degistirir. Donus: (tek sayfalik PDF baytlari, 'inplace'|'overlay')."""
    import pypdf
    todo = [(P, tr) for P, tr in zip(layout['paras'], translations) if tr and tr.strip() and not P['rotated']]
    if not todo:
        return None, None
    items = []
    for P, tr in todo:
        fp = E.pick_font(P['font'], P['bold'], P['italic'], P['serif'])
        if not fp:
            raise E.EditError('Uygun bir TrueType yazı tipi bulunamadı.')
        items.extend(place(P, tr.strip(), fp, layout['width']))
    mode = 'inplace'
    boxes = ()
    try:
        w, page = E.strip_ops(reader, index, pdf_bytes, [o for P, _ in todo for o in P['objects']], E.OBJ_TEXT)
    except E.EditError:
        mode = 'overlay'
        w = E._one_page_writer(reader, index)
        page = w.pages[0]
        rects = [(P['rect'][0] - 1, P['rect'][1] - 1.5, P['rect'][2] + 1, P['rect'][3] + 1) for P, _ in todo]
        boxes = [(*r, c) for r, c in zip(rects, _bg_colors(pdf, index, rects, layout['height']))]
    mb = page.mediabox
    layer = layer_pdf(max(1.0, float(mb.right)), max(1.0, float(mb.top)), items, boxes)
    page.merge_page(pypdf.PdfReader(io.BytesIO(layer)).pages[0], over=True)
    return E._writer_bytes(w), mode


# ----------------------------------------------------------------------------- bicimli belgeye donusturme
def page_images(pdf, index, min_pt=40):
    """Sayfadaki resimler (formlar dahil) sayfadan kesilerek: [(ust_y, png_baytlari, w_pt, h_pt)]."""
    _pdfium, raw = E._lib()
    page = pdf[index]
    try:
        width, height = page.get_size()
        _paths, kids = E.page_tree(page)
        rects = []

        def visit(prefix, ctm):
            for k, t, h in kids.get(prefix, []):
                if t == E.OBJ_FORM:
                    visit(prefix + (k,), E._compose(E._matrix(raw, h), ctm))
                elif t == E.OBJ_IMAGE:
                    l, b, r, tt = (ctypes.c_float() for _ in range(4))
                    if raw.FPDFPageObj_GetBounds(h, l, b, r, tt):
                        pts = [E._apply(ctm, px, py) for px, py in ((l.value, b.value), (r.value, tt.value), (l.value, tt.value), (r.value, b.value))]
                        rects.append((min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)))
        visit((), (1, 0, 0, 1, 0, 0))
        out = []
        rects = [r for r in rects if (r[2] - r[0]) >= min_pt and (r[3] - r[1]) >= min_pt
                 and (r[2] - r[0]) * (r[3] - r[1]) < 0.8 * width * height]
        if not rects:
            return []
        k = 2.0
        img = page.render(scale=k).to_pil().convert('RGB')
        for (l, b, r, t) in rects:
            box = (max(0, int(l * k)), max(0, int((height - t) * k)), min(img.width, int(r * k)), min(img.height, int((height - b) * k)))
            if box[2] - box[0] < 8 or box[3] - box[1] < 8:
                continue
            buf = io.BytesIO()
            img.crop(box).save(buf, 'PNG')
            out.append((t, buf.getvalue(), r - l, t - b))
        return out
    finally:
        page.close()


def layout_blocks(pages, title=None, layouts=None, translations=None, images=True):
    """PDF -> bicimli bloklar: buyuk yazilar baslik, kalinlar kalin, resimler yerinde. pages: [(pdfium_belgesi, sira)].
    translations verilirse paragraf metinleri onlarla degistirilir (sira: sayfa sayfa paragraflar)."""
    blocks = []
    if title:
        blocks.append(R.para(text=title, style='h1'))
    sizes = []
    layouts = layouts or [extract_layout(pdf, i) for pdf, i in pages]
    for lay in layouts:
        for P in lay['paras']:
            sizes.extend([P['size']] * max(1, len(P['text']) // 20))
    body = sorted(sizes)[len(sizes) // 2] if sizes else 11.0
    tr_iter = iter(translations) if translations is not None else None
    for n, ((pdf, pi), lay) in enumerate(zip(pages, layouts)):
        items = []
        for P in lay['paras']:
            text = next(tr_iter) if tr_iter is not None else P['text']
            text = (text or P['text']).strip()
            if not text:
                continue
            s = P['size'] / max(1.0, body)
            style = 'h1' if s >= 1.7 else 'h2' if s >= 1.35 else 'h3' if (s >= 1.15 and P['bold']) else 'normal'
            align = 'center' if P['align'] == 'center' else 'right' if P['align'] == 'right' else None
            color = P['color'].upper() if P['color'] not in ('000000', 'ffffff') and style == 'normal' else None
            blk = R.para(R.md_inline(R._esc_inline(text)), style, align=align)
            for r in blk['runs']:
                r['b'] = P['bold'] and style == 'normal'
                r['i'] = P['italic']
                r['color'] = color
            items.append((P['origin'][1], blk))
        for (top, data, w_pt, h_pt) in (page_images(pdf, pi) if images else ()):
            try:
                items.append((top + 0.01, R.image_block(data, min(w_pt, R.CONTENT_W_PT), h_pt * min(1.0, R.CONTENT_W_PT / max(1.0, w_pt)),
                                                        align='center')))
            except ValueError:
                pass
        items.sort(key=lambda t: -t[0])
        if n and items:
            first = items[0][1]
            if first['t'] == 'p':
                first['pb'] = True
        blocks.extend(b for _y, b in items)
    return blocks


def para_texts(layouts):
    return [P['text'] for lay in layouts for P in lay['paras']]


def strip_markup(text):
    return re.sub(r'\*\*|</?u>|(?<!\w)\*(?=\S)|(?<=\S)\*(?!\w)', '', text or '')
