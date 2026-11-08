# -*- coding: utf-8 -*-
"""AGFO AI Editor 2.12 - Metin islemleri (secime ya da imlecin bulundugu paragrafa uygulanir).

Harf donusumleri karakter sayisini degistirmez; bicimli belgede her parcanin bicimi (kalin, renk, yazi tipi...)
korunur. Satir islemleri (siralama, tekrar silme...) satirlari bicimleriyle birlikte tasir. Turkce harfler (i/I/ı/İ)
dogru donusturulur; siralama Turkce alfabeye gore yapilir.
"""
from __future__ import annotations

import datetime
import re
import tkinter as tk

TR_ALPHA = 'aâbcçdefgğhıiîjklmnoöpqrsştuûüvwxyz'
_ORDER = {ch: k for k, ch in enumerate(TR_ALPHA)}


# ------------------------------------------------------------------------------------------- Turkce harf donusumu
def tr_upper(s: str) -> str:
    return s.replace('i', 'İ').replace('ı', 'I').upper()


def tr_lower(s: str) -> str:
    return s.replace('I', 'ı').replace('İ', 'i').lower()


def _same_len(fn):
    """Uzunlugu degistiren ozel durumlarda (ß -> SS gibi) harfi oldugu gibi birakir: bicim parcalari kaymasin."""
    def run(s):
        out = fn(s)
        if len(out) == len(s):
            return out
        return ''.join(fn(ch) if len(fn(ch)) == 1 else ch for ch in s)
    return run


def title_case(s: str) -> str:
    """Her kelimenin ilk harfi buyuk, kalani kucuk ('ve', 'ile' gibi baglaclar kucuk kalir, cumle basi haric)."""
    small = {'ve', 'ile', 'veya', 'ya', 'da', 'de', 'ki', 'mi', 'için', 'gibi', 'ama', 'fakat',
             'and', 'or', 'of', 'the', 'a', 'an', 'in', 'on', 'for', 'to'}
    out, first = [], True
    for m in re.finditer(r"\w+|\W+", s):
        w = m.group(0)
        if w[0].isalnum() or w[0] == '_':
            low = tr_lower(w)
            if not first and low in small:
                out.append(low)
            else:
                out.append(tr_upper(low[0]) + low[1:])
            first = False
        else:
            out.append(w)
            if re.search(r'[.!?:\n]', w):
                first = True
    return ''.join(out)


def sentence_case(s: str) -> str:
    """Cumle duzeni: her cumlenin ilk harfi buyuk, gerisi kucuk."""
    low = tr_lower(s)
    out, cap = [], True
    for ch in low:
        if cap and ch.isalpha():
            out.append(tr_upper(ch))
            cap = False
        else:
            out.append(ch)
            if ch in '.!?\n':
                cap = True
    return ''.join(out)


def toggle_case(s: str) -> str:
    return ''.join(tr_lower(ch) if ch.isupper() else tr_upper(ch) for ch in s)


CASE_OPS = {
    'upper': ('BÜYÜK HARF', _same_len(tr_upper)),
    'lower': ('küçük harf', _same_len(tr_lower)),
    'title': ('Başlık Düzeni', _same_len(title_case)),
    'sentence': ('Cümle düzeni', _same_len(sentence_case)),
    'toggle': ('bÜYÜK/kÜÇÜK değiştir', _same_len(toggle_case)),
}


# ------------------------------------------------------------------------------------------- satir islemleri
def tr_key(s: str):
    """Turkce alfabe sirasi (buyuk/kucuk harf duyarsiz), sayilar sayi olarak."""
    key = []
    for part in re.split(r'(\d+)', tr_lower(s.strip())):
        if part.isdigit():
            key.append((0, int(part), ''))
        elif part:
            key.append((1, 0, tuple(_ORDER.get(ch, 1000 + ord(ch)) for ch in part)))
    return key


def order_lines(lines, op):
    """lines: herhangi bir nesne listesi, metni key ile alinir. Donus: yeni sira (indeksler)."""
    idx = list(range(len(lines)))
    if op == 'sort_az':
        return sorted(idx, key=lambda k: tr_key(lines[k]))
    if op == 'sort_za':
        return sorted(idx, key=lambda k: tr_key(lines[k]), reverse=True)
    if op == 'reverse':
        return idx[::-1]
    if op == 'dedupe':
        seen, out = set(), []
        for k in idx:
            key = re.sub(r'\s+', ' ', lines[k].strip())
            if key and key in seen:
                continue
            seen.add(key)
            out.append(k)
        return out
    if op == 'drop_empty':
        return [k for k in idx if lines[k].strip()]
    raise ValueError(op)


LINE_OPS = {
    'sort_az': 'Satırları sırala (A → Z)',
    'sort_za': 'Satırları sırala (Z → A)',
    'reverse': 'Satır sırasını ters çevir',
    'dedupe': 'Tekrarlanan satırları kaldır',
    'drop_empty': 'Boş satırları kaldır',
}


# ------------------------------------------------------------------------------------------- metin temizligi
def squeeze_spaces(s: str) -> str:
    s = re.sub(r'[ \t\u00a0]{2,}', ' ', s)
    s = re.sub(r'[ \t]+\n', '\n', s)
    return re.sub(r'[ \t]+$', '', s)


def join_wrapped(s: str) -> str:
    """PDF'ten kopyalanmis metindeki satir kirilmalarini birlestirir: bos satir paragraf sinirli kalir, satir sonu
    tirelemesi (kelime-\\nler) birlesir, madde satirlari ayri kalir."""
    paras = re.split(r'\n\s*\n', s)
    out = []
    bullet = re.compile(r'^\s*([-•▪◦*]|\d+[.)])\s+')
    for p in paras:
        lines = [ln.strip() for ln in p.split('\n')]
        buf = ''
        merged = []
        for ln in lines:
            if not ln:
                continue
            if buf and bullet.match(ln):
                merged.append(buf)
                buf = ln
            elif buf.endswith('-') and len(buf) > 1 and buf[-2].isalpha() and ln[:1].islower():
                buf = buf[:-1] + ln
            elif buf:
                buf += ' ' + ln
            else:
                buf = ln
        if buf:
            merged.append(buf)
        out.append('\n'.join(merged))
    return '\n\n'.join(out)


def smart_quotes(s: str) -> str:
    s = re.sub(r'(^|[\s(\[{\u2014-])"', '\\1\u201c', s)
    s = s.replace('"', '\u201d')
    s = re.sub(r"(^|[\s(\[{\u2014-])'", '\\1\u2018', s)
    return s.replace("'", '\u2019')


def straight_quotes(s: str) -> str:
    return s.translate({0x201c: '"', 0x201d: '"', 0x201e: '"', 0x2018: "'", 0x2019: "'", 0x201a: "'", 0xab: '"',
                        0xbb: '"'})


def number_lines(s: str) -> str:
    n = 0
    out = []
    for ln in s.split('\n'):
        if ln.strip():
            n += 1
            out.append('%d. %s' % (n, re.sub(r'^\s*(\d+[.)]|[-•▪◦*])\s+', '', ln)))
        else:
            out.append(ln)
    return '\n'.join(out)


def strip_markers(s: str) -> str:
    return '\n'.join(re.sub(r'^(\s*)(\d+[.)]|[-•▪◦*])\s+', r'\1', ln) for ln in s.split('\n'))


TEXT_OPS = {
    'squeeze': ('Fazla boşlukları temizle', squeeze_spaces),
    'join': ('Kırık satırları birleştir (PDF metni)', join_wrapped),
    'smartq': ('Tırnakları “akıllı” yap', smart_quotes),
    'straightq': ('Tırnakları düz yap', straight_quotes),
    'number': ('Satırları numaralandır', number_lines),
    'unmark': ('Numara / madde işaretlerini kaldır', strip_markers),
}


def stats(s: str) -> dict:
    words = re.findall(r'\w+', s)
    sentences = [x for x in re.split(r'(?<=[.!?])\s+', s.strip()) if x.strip()]
    paras = [x for x in re.split(r'\n\s*\n|\n', s) if x.strip()]
    return {'chars': len(s), 'chars_nospace': len(re.sub(r'\s', '', s)), 'words': len(words),
            'sentences': len(sentences), 'paragraphs': len(paras),
            'minutes': round(len(words) / 200.0, 1)}


def now_text(kind='date'):
    d = datetime.datetime.now()
    return {'date': d.strftime('%d.%m.%Y'), 'datetime': d.strftime('%d.%m.%Y %H:%M'),
            'long': '%d %s %d' % (d.day, ('Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos',
                                           'Eylül', 'Ekim', 'Kasım', 'Aralık')[d.month - 1], d.year)}[kind]


# ------------------------------------------------------------------------------------------- belgeye uygulama
def target_range(t):
    """Secim varsa secim; yoksa imlecin bulundugu paragraf (satir)."""
    try:
        return t.index('sel.first'), t.index('sel.last'), True
    except tk.TclError:
        line = t.index('insert').split('.')[0]
        return '%s.0' % line, '%s.0 lineend' % line, False


def _begin(t):
    u = getattr(t, 'undo', None)
    if u is not None and hasattr(u, 'begin'):
        u.begin()
    else:
        t.edit_separator()


def _end(t):
    u = getattr(t, 'undo', None)
    if u is not None and hasattr(u, 'end'):
        u.end()
    else:
        t.edit_separator()
    ch = getattr(t, 'changed', None)
    if ch:
        ch()


def _segments(t, s, e):
    """[(indeks, metin, etiketler)] - bicim degismeyen parcalar."""
    dump = getattr(t, '_dump', None)
    if dump is None:
        return [(s, t.get(s, e), ())]
    out, pos = [], t.index(s)
    for kind, val, tags in dump(s, e):
        if kind == 't':
            out.append((pos, val, tags))
            pos = t.index('%s+%dc' % (pos, len(val)))
        else:
            pos = t.index('%s+1c' % pos)
    return out


def apply_case(t, op):
    """Harf donusumu; bicim parca parca korunur. Donus: degisen karakter sayisi."""
    fn = CASE_OPS[op][1]
    s, e, _sel = target_range(t)
    segs = _segments(t, s, e)
    changed = 0
    _begin(t)
    try:
        for pos, txt, tags in reversed(segs):
            new = fn(txt)
            if new == txt or len(new) != len(txt):
                continue
            end = '%s+%dc' % (pos, len(txt))
            if tags or getattr(t, '_dump', None) is None:
                t.delete(pos, end)
                t.insert(pos, new, tags)
            else:
                t.delete(pos, end)
                t.insert(pos, new)
            changed += sum(1 for a, b in zip(txt, new) if a != b)
    finally:
        _end(t)
    if _sel:
        t.tag_add('sel', s, e)
    return changed


def apply_lines(t, op):
    """Satir islemi; her satir bicimiyle tasinir. Secim yoksa butun belge. Donus: (once, sonra) satir sayisi."""
    try:
        s, e = t.index('sel.first linestart'), t.index('sel.last')
        if t.compare(e, '==', '%s linestart' % e) and t.compare(e, '>', s):
            e = t.index('%s -1c' % e)
        e = t.index('%s lineend' % e)
    except tk.TclError:
        s, e = '1.0', t.index('end-1c')
    a, b = int(s.split('.')[0]), int(e.split('.')[0])
    dump = getattr(t, '_dump', None)
    rows = []
    for ln in range(a, b + 1):
        txt = t.get('%d.0' % ln, '%d.0 lineend' % ln)
        items = dump('%d.0' % ln, '%d.0 lineend+1c' % ln) if dump else None
        if items and any(k == 'i' for k, _v, _t in items):
            raise ValueError('Seçimde resim var; satır işlemleri resimli satırlarda yapılmaz.')
        rows.append((txt, items))
    order = order_lines([r[0] for r in rows], op)
    if order == list(range(len(rows))):
        return len(rows), len(rows)
    _begin(t)
    try:
        end_all = t.index('%d.0 lineend+1c' % b) if t.compare('%d.0 lineend' % b, '<', 'end-1c') else t.index('end-1c')
        last_has_nl = t.compare('%d.0 lineend' % b, '<', 'end-1c')
        t.delete('%d.0' % a, end_all)
        pos = '%d.0' % a
        for n, k in enumerate(order):
            txt, items = rows[k]
            need_nl = n < len(order) - 1 or last_has_nl
            if items:
                for kind, val, tags in items:
                    if kind != 't':
                        continue
                    if val.endswith('\n') and not need_nl:
                        val = val[:-1]
                    if not val:
                        continue
                    t.insert(pos, val, tags)
                    pos = t.index('%s+%dc' % (pos, len(val)))
                if need_nl and not items[-1][1].endswith('\n'):
                    t.insert(pos, '\n')
                    pos = t.index('%s+1c' % pos)
            else:
                piece = txt + ('\n' if need_nl else '')
                t.insert(pos, piece)
                pos = t.index('%s+%dc' % (pos, len(piece)))
    finally:
        _end(t)
    return len(rows), len(order)


def apply_text(t, op):
    """Metni toptan donusturen islemler (bicim yalniz ilk parcanin bicimiyle kalir). Donus: degisti mi."""
    fn = TEXT_OPS[op][1]
    s, e, sel = target_range(t)
    old = t.get(s, e)
    new = fn(old)
    if new == old:
        return False
    tags = ()
    if getattr(t, '_dump', None):
        segs = _segments(t, s, e)
        tags = segs[0][2] if segs else ()
    _begin(t)
    try:
        t.delete(s, e)
        t.insert(s, new, tags)
    finally:
        _end(t)
    if sel:
        t.tag_add('sel', s, '%s+%dc' % (s, len(new)))
    return True
