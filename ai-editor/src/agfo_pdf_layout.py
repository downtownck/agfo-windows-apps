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
BULLET_CHARS = set('•●▪■◦○‣∙·–—-*►▶➢✓✔') | {chr(c) for c in range(0xF000, 0xF100)}
SYMBOL_FONT_RX = re.compile(r'symbol|wingding|webding|dingbat|marlett|mtextra|zapf', re.I)
TOC_LINE_RX = re.compile(r'^(.*?)\s*(?:\.{3,}|…+|(?:\.\s){3,}|_{3,})[\s.…]*(\d+)\s*$')
TOC_RX = re.compile(r'(\.{4,}|…{2,}|(\.\s){4,}|_{4,})\s*\d+\s*$')


def _is_bullet(o, font=''):
    t = o['text'].strip()
    return len(t) == 1 and (t in BULLET_CHARS or SYMBOL_FONT_RX.search(font or '') is not None)


def _path_segments(raw, h, ctm, add):
    """Yol nesnesinin duz kenarlari tek tek (bir tablo izgarasinin tamami tek yol olabilir; kutusu tum tablo olur).
    Yalniz duz cizgilerden olusan yollar islenir; egri iceren yolda False (sinir kutusu kullanilir)."""
    n = raw.FPDFPath_CountSegments(h)
    if n <= 1 or n > 4000:
        return False
    m = E._compose(E._matrix(raw, h), ctm)
    pts, start, prev = [], None, None
    segs = []
    for i in range(n):
        seg = raw.FPDFPath_GetPathSegment(h, i)
        typ = raw.FPDFPathSegment_GetType(seg)
        if typ == 3:                       # Bezier: duz kenar degil
            return False
        x, y = ctypes.c_float(), ctypes.c_float()
        raw.FPDFPathSegment_GetPoint(seg, x, y)
        p = E._apply(m, x.value, y.value)
        if typ == 2 or prev is None:       # moveto
            start = p
        else:
            segs.append((prev, p))
        if raw.FPDFPathSegment_GetClose(seg) and start is not None and p != start:
            segs.append((p, start))
        prev = p
    for (x0, y0), (x1, y1) in segs:
        add(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1), edge=True)
    _ = pts
    return True


def _walls(page, width, height):
    """Sayfadaki cizgiler ve kutular (formlar dahil): (dikey [(x, y0, y1)], yatay [(y, x0, x1)]). Ceviri bu sinirlari
    asmasin diye kullanilir: tablo hucresi, akis semasi kutusu, cerceve."""
    _pdfium, raw = E._lib()
    _paths, kids = E.page_tree(page)
    vert, horiz = [], []

    def add(l, b, r, t, edge=False):
        w, h = r - l, t - b
        if edge:                                       # tek kenar: yalniz dikey ya da yatay olanlar
            if w < 2.5 and h > 6:
                vert.append(((l + r) / 2, b, t))
            elif h < 2.5 and w > 6:
                horiz.append(((b + t) / 2, l, r))
            return
        if w * h > 0.6 * width * height:              # zemin / sayfa cercevesi
            return
        if w < 2.5 and h > 6:
            vert.append(((l + r) / 2, b, t))
        elif h < 2.5 and w > 6:
            horiz.append(((b + t) / 2, l, r))
        elif w > 6 and h > 6:
            vert.extend([(l, b, t), (r, b, t)])
            horiz.extend([(b, l, r), (t, l, r)])

    def visit(prefix, ctm):
        for k, typ, h in kids.get(prefix, []):
            if typ == E.OBJ_FORM:
                visit(prefix + (k,), E._compose(E._matrix(raw, h), ctm))
            elif typ == E.OBJ_PATH:
                if _path_segments(raw, h, ctm, add):
                    continue
                l, b, r, t = (ctypes.c_float() for _ in range(4))
                if raw.FPDFPageObj_GetBounds(h, l, b, r, t):
                    pts = [E._apply(ctm, px, py) for px, py in ((l.value, b.value), (r.value, t.value), (l.value, t.value), (r.value, b.value))]
                    add(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    visit((), (1, 0, 0, 1, 0, 0))
    return vert, horiz


def _clip_hidden(raw, kids, objs):
    """Kirpma yolunun disinda kalan (gorunmeyen) metin nesneleri. Akis semalarinda kutunun disina tasan metin
    kirpilir; ceviri katmani kirpilmadigi icin bu metin cevrilince birden gorunur oluyordu."""
    handles = {pre + (k,): (t, h) for pre, lst in kids.items() for k, t, h in lst}
    hidden = set()
    for path, o in objs.items():
        th = handles.get(path)
        if not th or not o.get('box'):
            continue
        cp = raw.FPDFPageObj_GetClipPath(th[1])
        if not cp:
            continue
        ctm = (1, 0, 0, 1, 0, 0)
        for d in range(len(path) - 1, 0, -1):                 # form icindeyse form matrisleri
            ft = handles.get(path[:d])
            if ft:
                ctm = E._compose(ctm, E._matrix(raw, ft[1]))
        xs, ys = [], []
        for i in range(max(0, raw.FPDFClipPath_CountPaths(cp))):
            for j in range(max(0, raw.FPDFClipPath_CountPathSegments(cp, i))):
                seg = raw.FPDFClipPath_GetPathSegment(cp, i, j)
                x, y = ctypes.c_float(), ctypes.c_float()
                if seg and raw.FPDFPathSegment_GetPoint(seg, x, y):
                    px, py = E._apply(ctm, x.value, y.value)
                    xs.append(px)
                    ys.append(py)
        if not xs:
            continue
        l, b, r, t = o['box']
        ix = max(0.0, min(r, max(xs)) - max(l, min(xs)))
        iy = max(0.0, min(t, max(ys)) - max(b, min(ys)))
        area = max(1e-6, (r - l) * (t - b))
        if ix * iy < 0.3 * area:
            hidden.add(path)
    return hidden


def _make_line(raw, tp, live, info, grp, ink, blank):
    grp = set(grp)
    # 1.4.9: madde imi (•, Symbol yazi tipindeki ozel karakter) ayri nesneyse yerinde kalir, cevrilmez
    bullet = False
    if len(ink) > 1 and _is_bullet(live[ink[0]], info.get(ink[0], {}).get('font')) \
            and live[ink[1]]['box'][0] - live[ink[0]]['box'][2] > 0.15 * max(3.0, live[ink[1]]['size']):
        grp.discard(ink[0])
        ink = ink[1:]
        bullet = True
    boxes = [live[k]['box'] for k in ink]
    first = ink[0]
    # baskin yazi tipi (karakter sayisina gore): Symbol gibi madde imi yazi tipleri paragrafin yazi tipi olmaz
    weight = Counter()
    for k in ink:
        fi_k = info.get(k)
        if fi_k and not SYMBOL_FONT_RX.search(fi_k['font'] or ''):
            weight[k] += len(live[k]['text'].strip())
    dom = weight.most_common(1)[0][0] if weight else first
    fi = info.get(dom) or E._char_info(raw, tp, live[first]['chars'][0])
    text = E.line_text(live, grp, blank)
    if not text:
        return None
    return {'objects': sorted(grp), 'text': text,
            'rect': (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)),
            'origin': live[first]['origin'], 'size': live[dom]['size'], 'font': fi['font'], 'bold': fi['bold'],
            'italic': fi['italic'], 'serif': fi['serif'], 'color': fi['color'], 'bullet': bullet,
            'toc': bool(TOC_RX.search(text)),
            'rotated': abs(fi['angle']) > 0.02 and abs(fi['angle'] - 6.2832) > 0.02}


def extract_layout(pdf, index):
    _pdfium, raw = E._lib()
    page = pdf[index]
    try:
        width, height = page.get_size()
        tp = page.get_textpage()
        objs, kids = E.text_objects(page, tp)
        blank = E.blank_paths(objs, kids)
        try:
            vert, horiz = _walls(page, width, height)
        except Exception:
            vert, horiz = [], []
        # bosluk nesneleri de tutulur: tarayici ciktilarinda sozcuk araliklari ayri nesnelerdir
        try:
            hidden = _clip_hidden(raw, kids, objs)
        except Exception:
            hidden = set()
        live = {k: o for k, o in objs.items() if o['mode'] not in (3, 7) and o['text'] and k not in hidden}
        info = {k: E._char_info(raw, tp, o['chars'][0]) for k, o in live.items() if o['chars']}
        lines = []
        remaining = {k for k in live if live[k]['text'].strip()}
        while remaining:
            seed = max(remaining, key=lambda k: (live[k]['origin'][1], -live[k]['box'][0]))
            pool = {k: live[k] for k in live if k in remaining or not live[k]['text'].strip()}
            grp = E.group_line(pool, seed)
            remaining -= grp
            ink = sorted((k for k in grp if live[k]['text'].strip()), key=lambda k: live[k]['box'][0])
            if not ink:
                continue
            for k in grp:
                if not live[k]['text'].strip():
                    live[k] = dict(live[k], mode=7)    # bir kez kullanilsin
            # 1.4.9: sekmeyle ayrilmis sutunlar (icindekiler numarasi | baslik, etiket | deger) ayri satir parcalaridir
            parts, cur = [], [ink[0]]
            for a, b in zip(ink, ink[1:]):
                if live[b]['box'][0] - live[a]['box'][2] > 1.2 * max(3.0, live[a]['size']) \
                        and not re.match(r'^[\s.…_]{3,}', live[b]['text']):       # icindekiler nokta dizisi baslikla kalir
                    parts.append(cur)
                    cur = []
                cur.append(b)
            parts.append(cur)
            blanks = [k for k in grp if not live[k]['text'].strip()]
            pending_bullet = False
            for n, part in enumerate(parts):
                if len(part) == 1 and n + 1 < len(parts) and _is_bullet(live[part[0]], info.get(part[0], {}).get('font')):
                    pending_bullet = True                   # sekmeyle ayrilmis madde imi: yerinde kalir
                    continue
                l0, r0 = live[part[0]]['box'][0], live[part[-1]]['box'][2]
                sub = set(part) | {k for k in blanks if l0 - 1 <= (live[k]['box'][0] + live[k]['box'][2]) / 2 <= r0 + 1}
                line = _make_line(raw, tp, live, info, sub, part, blank)
                if line:
                    line['bullet'] = line['bullet'] or pending_bullet
                    lines.append(line)
                pending_bullet = False
        # tek basina madde imi olan satir (im ile metin ayri satira dusmus): im yerinde kalir, sagindaki satir madde olur
        for L in [x for x in lines if len(x['text']) == 1 and x['text'] in BULLET_CHARS or
                  (len(x['text']) == 1 and SYMBOL_FONT_RX.search(x['font'] or ''))]:
            right = [M for M in lines if M is not L and abs(M['origin'][1] - L['origin'][1]) < 0.5 * max(3.0, M['size'])
                     and M['rect'][0] >= L['rect'][2] and M['rect'][0] - L['rect'][2] < 6 * max(3.0, M['size'])]
            if right:
                min(right, key=lambda M: M['rect'][0])['bullet'] = True
                lines.remove(L)
        flat = [L for L in lines if not L['rotated']]
        margin_r = max([L['rect'][2] for L in flat] + [0.0])
        margin_l = min([L['rect'][0] for L in flat] + [width])
        for L in lines:   # ayni taban cizgisinde baska satir var: tablo satiri (hiza tahmini yapilmaz)
            L['sib'] = any(M is not L and abs(M['origin'][1] - L['origin'][1]) < 0.3 * L['size'] for M in lines)
            L['row'] = L['sib'] and (L['rect'][2] - L['rect'][0]) < 0.3 * width
        for L in lines:   # satirin yatayda ne kadar genisleyebilecegi: komsu metin, cizgi/kutu ve sayfa kenar boslugu
            same = [M for M in lines if M is not L and abs(M['origin'][1] - L['origin'][1]) < 0.6 * L['size']]
            lo = max([M['rect'][2] + 6 for M in same if M['rect'][2] <= L['rect'][0] + 1] + [8.0, min(margin_l, L['rect'][0]) - 2])
            hi = min([M['rect'][0] - 6 for M in same if M['rect'][0] >= L['rect'][2] - 1] + [width - 8.0, max(margin_r, L['rect'][2]) + 2])
            y0, y1 = L['rect'][1], L['rect'][3]
            for x, b, t in vert:
                if b <= y1 - 0.5 and t >= y0 + 0.5:       # cizgi satirla ayni yukseklikte
                    if x <= L['rect'][0] + 1:
                        lo = max(lo, x + 3)
                    elif x >= L['rect'][2] - 1:
                        hi = min(hi, x - 3)
            L['lim'] = (lo, hi)
        paras = _paragraphs(lines, width, margin_r)
        for P in paras:   # paragrafin altindaki ilk cizgi/kutu kenari: ceviri asagi tasarken bunu gecmez
            l, b, r, _t = P['rect']
            floors = [y for y, x0, x1 in horiz if y <= b + 1 and min(r, x1) - max(l, x0) > 2]
            if floors:
                P['below'] = max(0.0, min(P['below'], b - max(floors) - 1.5))
        return {'width': width, 'height': height, 'paras': paras}
    finally:
        page.close()


def t_low(text):
    c = text.lstrip()[:1]
    return c.isalpha() and c.islower()


def _paragraphs(lines, page_w, margin_r=None):
    margin_r = margin_r or page_w
    lines = sorted(lines, key=lambda L: (-L['origin'][1], L['rect'][0]))
    paras = []
    for L in lines:
        target = None
        for P in reversed(paras[-6:]):
            last = P['lines'][-1]
            s = max(3.0, P['size'])
            if L['rotated'] or last['rotated'] or L.get('row') or L.get('bullet') or L.get('toc') or last.get('toc'):
                continue
            if last['text'].rstrip().endswith(':'):          # liste girisi: ardindan yeni oge gelir
                continue
            if abs(L['size'] - P['size']) > 0.12 * s or L['bold'] != P['bold'] or L['color'] != P['color']:
                continue
            gap = last['origin'][1] - L['origin'][1]
            if not (0.75 * s <= gap <= 1.9 * s):
                continue
            if len(P['lines']) > 1:                          # paragraf ici satir araligi sabit; fazlasi yeni paragraf
                lead = P['lines'][-2]['origin'][1] - last['origin'][1]
                if abs(gap - lead) > 0.22 * s:
                    continue
            elif gap > 1.95 * s:
                continue
            l1, r1 = P['rect'][0], P['rect'][2]
            l2, r2 = L['rect'][0], L['rect'][2]
            overlap = min(r1, r2) - max(l1, l2)
            same_left = abs(l2 - l1) < 1.5 * s
            same_center = abs((l2 + r2) / 2 - (l1 + r1) / 2) < 1.5 * s
            # tablo/etiket sutunlari: kisa, buyuk harfle baslayan alt alta satirlar ayri paragraftir; yalniz
            # sarilmis metin (uzun satirlar ya da devam eden cumle) birlestirilir
            last_w = last['rect'][2] - last['rect'][0]
            widest = max(M['rect'][2] - M['rect'][0] for M in P['lines'])
            # onceki satir dolu mu: L'nin ilk sozcugu onceki satira sigardiysa satir sonu bilincli (liste, adres, A1/A2...)
            col_r = min(last.get('lim', (0, margin_r))[1] + 3, margin_r + 2)
            word = (L['text'].split() or [''])[0]
            fits = last['rect'][2] + (len(word) + 1) * 0.5 * s <= col_r
            full = not fits and last_w >= 0.5 * widest
            if len(P['lines']) == 1 and gap > 1.5 * s and not full:
                continue                                     # genis aralik + bilincli satir sonu: yeni paragraf
            wrapped = full or (t_low(L['text']) and not L.get('sib')) \
                or (last_w >= 0.22 * page_w and last['text'].rstrip()[-1:] in ',;-–(&')
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
    # tesaduf eseri sayfa ortasina dusen tek satir: sola hizali paragraflarla ayni soldan basliyorsa sola hizalidir
    left_edges = [Q['lines'][0]['rect'][0] for Q in paras if len(Q['lines']) > 1 and Q.get('align') == 'left']
    for P in paras:
        if len(P['lines']) == 1 and P['align'] == 'center' and any(abs(P['rect'][0] - x) < 1.5 for x in left_edges):
            P['align'] = 'left'
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
    """(boyut, satirlar, satir_araligi_carpani) - ceviri paragrafin kutusuna sigacak sekilde sarilir. Sira: ayni boyut;
    biraz sikistirilmis satir araligi; paragrafin altindaki bos alana (cizgi/kutu kenarina kadar) tasma; en son
    kucultme (en fazla %60'a)."""
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
    below = max(0.0, P.get('below', 0.0))
    tw = lambda t, k: E.text_width(t, font_path, size * k)  # noqa: E731
    m = TOC_LINE_RX.match(text) if P['lines'][0].get('toc') else None
    if m and lines_n == 1:
        # icindekiler satiri: nokta dizisi, ceviri ozgun satir genisligine sigacak kadar kisaltilir/uzatilir
        title, num = m.group(1).rstrip(), m.group(2)
        target = max(width, min(room, width * 1.02))
        for k in (1.0, 0.94, 0.88, 0.82, 0.76, 0.7):
            base = tw(title + ' ' + num, k)
            dot = max(0.1, tw('.', k))
            if base + 3 * dot <= target:
                n = int((target - base) // dot)
                return size * k, ['%s%s%s' % (title, '.' * n, num)], 1.0
        return size * 0.7, [title + '...' + num], 1.0
    if lines_n == 1:
        width_cap = min(width * 1.12 + 4 * size, room)
        for k in (1.0, 0.94, 0.88):
            if tw(text, k) <= width_cap:
                return size * k, [text], 1.0
        # 1.4.9: kucultmeden once alttaki bos alana sar (tek satirlik paragraf cok kuculup okunmaz oluyordu)
        for k in (1.0, 0.94, 0.88, 0.82, 0.76):
            lead = size * k * 1.18
            max_lines = 1 + int(max(0.0, below - 0.2 * size) // lead)
            if max_lines < 2:
                break
            wrapped = _wrap(text, font_path, size * k, room)
            if len(wrapped) <= max_lines and all(tw(x, k) <= room + 0.5 for x in wrapped):
                return size * k, wrapped, 1.0
        for k in (0.82, 0.76, 0.7, 0.64, 0.6):
            if tw(text, k) <= width_cap:
                return size * k, [text], 1.0
        return size * 0.6, _wrap(text, font_path, size * 0.6, room), 1.0
    lead = P['lead']
    extra = int(max(0.0, below - 0.6 * lead) // max(1.0, lead))
    # son satirin taban cizgisi, ozgun son satirdan (ve alttaki bos alandan) asagi inmesin
    span = (lines_n - 1 + min(extra, max(1, lines_n // 2))) * lead + 0.12 * lead
    if not extra:                    # paragraf araliginin bir kismi kullanilabilir; gozle gorulur bosluk kalir
        span += max(0.0, min(below - 0.5 * lead, 0.25 * lead))
    wrap_w = min(width * 1.02, room)
    for k in (1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6):
        wrapped = _wrap(text, font_path, size * k, wrap_w)
        for lf in (1.0, 0.94):
            if (len(wrapped) - 1) * lead * k * lf <= span:
                return size * k, wrapped, lf
    return size * 0.6, _wrap(text, font_path, size * 0.6, wrap_w), 0.93


_PUA_BULLET = {'\uf0b7': '•', '\uf0a7': '▪', '\uf0d8': '►', '\uf076': '❖', '\uf0fc': '✓', '\uf0a8': '•'}


def clean_text(text):
    """Model ciktisindaki gorunmez/kontrol karakterleri ve sekmeler yazi tipinde kutu (□) olarak cikiyordu."""
    text = ''.join(_PUA_BULLET.get(c, c) for c in (text or ''))
    text = re.sub(r'[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u00ad\u200b-\u200f\u2060\ufeff]', '', text)
    text = re.sub(r'[\s\u00a0\u2000-\u200a\u2028\u2029\u202f\u3000]+', ' ', text)
    text = re.sub(r'[\ue000-\uf8ff]', '', text)
    return text.strip()


def place(P, text, font_path, page_w):
    text = clean_text(text)
    size, lines, lf = fit_paragraph(P, text, font_path, page_w)
    k = size / max(0.1, P['size'])
    lead = (P['lead'] * k if len(P['lines']) > 1 else size * 1.18) * lf
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
