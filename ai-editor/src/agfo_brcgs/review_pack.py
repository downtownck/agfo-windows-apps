# -*- coding: utf-8 -*-
"""AGFO AI Editor - BRCGS teknik gozden gecirme kaynaklari (brcgs_data/review/<profil>.txt).

Her dosya uc bolumdur: 1) teknik gozden gecirme skill talimati (rapor yazim kurallari), 2) resmi "How to complete the
audit report" rehberi (F910 / P702 / CP417 / AB309 / SD408), 3) standardin gereklilik metinleri.
Bu modul dosyayi bolumlere ayirir; rehberde sablon alanlarinin kurallarini (MANDATORY, aciklama) ve bolum bazli
beklentileri ("1. Senior management commitment ... Outcome ...") bulur.
"""
from __future__ import annotations

import functools
import re

from . import data

_SEP = re.compile(r'^={20,}\s*$', re.M)
_PART = re.compile(r'^B[ÖO]L[ÜU]M\s+(\d)\s*-\s*(.*)$', re.M | re.I)
_PAGE_FOOT = re.compile(r'^\s*(?:\x0c)?(?:[A-Z]{1,3}\d{3,4}\s*:|Version \d+:|Page \d+ of \d+|.*BRCGS Global Standard .*Issue \d+\s*$)', re.I)
TAG_WORDS = re.compile(r'^(FREE TEXT TAG|MANDATORY(?: TEXT)?|TEXT|UNTAGGED|TAGGED|DROP ?DOWN(?: TAG| LIST)?|DATE(?: TAG)?|TAG|'
                       r'TICK ?BOX|CHECK ?BOX|NUMERIC|NUMBER|OPTIONAL|LIST)\b')      # buyuk harf: 'date' etiket sozcugu degil


def _compact(s):
    return re.sub(r'[^a-z0-9]+', '', str(s or '').lower())


@functools.lru_cache(maxsize=None)
def pack(profile):
    """{'skill': str, 'guide': str, 'requirements': str, 'title': str} - dosya yoksa bos dizeler."""
    p = data.norm_profile(profile)
    path = data.data_root() / 'review' / ('%s.txt' % p)
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return {'skill': '', 'guide': '', 'requirements': '', 'title': ''}
    parts = {}
    marks = list(_PART.finditer(text))
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        body = _SEP.sub('', text[m.end():end]).strip('\n')
        parts[m.group(1)] = body
    return {'skill': parts.get('1', '').strip(), 'guide': parts.get('2', ''), 'requirements': parts.get('3', ''),
            'title': text.split('\n', 1)[0].strip()}


@functools.lru_cache(maxsize=None)
def guide_lines(profile):
    return [ln.replace('\x0c', '').rstrip() for ln in pack(profile)['guide'].split('\n')]


def _column_tokens(line, col):
    """line'da col konumundan baslayan, 2+ bosluga kadar olan parca."""
    if col >= len(line) or (col > 0 and line[col - 1] not in ' \t'):
        return ''
    seg = line[col:]
    m = re.match(r'(\S+(?: \S+)*)', seg)
    return m.group(1) if m else ''


_INLINE_TAGS = r'(?:FREE TEXT TAG|DROP ?DOWN TAG|DROP ?DOWN|DATE TAG|UNTAGGED|TAGGED|MANDATORY TEXT|MANDATORY|TEXT|TAG)'
_NEXT_FIELD = re.compile(r'(?:\b[A-Z][\w’\'/()&.,-]*(?: [\w’\'/()&.,-]+){0,8}\s+(?:FREE TEXT TAG|DROP ?DOWN TAG|DATE TAG|UNTAGGED)\b)')


def _label_rx(label):
    words = [re.escape(w) for w in re.findall(r'[\w’\'/&.()-]+', str(label)) if w.strip('.')]
    return r'\s+'.join(words)


@functools.lru_cache(maxsize=None)
def _flat(profile):
    lines = [ln for ln in guide_lines(profile) if not _PAGE_FOOT.match(ln)]
    return '\n'.join(lines)


def _inline_rule(profile, label):
    """Duz metin rehberler (P702, AB309, CP417): 'Label FREE TEXT TAG MANDATORY TEXT' ya da 'Label – aciklama'."""
    flat = _flat(profile)
    lrx = _label_rx(label)
    if not lrx:
        return None
    m = re.search(r'(?<![\w-])' + lrx + r'\.?\s+((?:' + _INLINE_TAGS + r'\s*)+)', flat, re.I)
    if m and re.search(r'[A-Z]{3}', m.group(1)):
        tags = re.findall(_INLINE_TAGS, m.group(1))
        rest = flat[m.end():m.end() + 900]
        nxt = _NEXT_FIELD.search(rest)
        desc = rest[:nxt.start()] if nxt else rest[:600]
        return {'mandatory': any('MANDATORY' in t.upper() for t in tags), 'text': re.sub(r'\s+', ' ', desc).strip(),
                'line': flat[:m.start()].count('\n'), 'tags': [t.upper() for t in tags]}
    m = re.search(r'(?:^|\n)\s*(?:•\s*)?' + lrx + r'\s*[–—:-]\s*(.+(?:\n(?!\s*\n).+){0,6})', flat, re.I)
    if m:
        return {'mandatory': False, 'text': re.sub(r'\s+', ' ', m.group(1)).strip()[:700], 'line': flat[:m.start()].count('\n'),
                'tags': []}
    m = re.search(r'(?:^|\n)\s*' + lrx + r'\s*\n(.+(?:\n(?!\s*\n).+){0,6})', flat, re.I)
    if m:
        return {'mandatory': False, 'text': re.sub(r'\s+', ' ', m.group(1)).strip()[:700], 'line': flat[:m.start()].count('\n'),
                'tags': []}
    return None


@functools.lru_cache(maxsize=None)
def field_rule(profile, label):
    """Rehberdeki alan kurali: {'mandatory', 'text', 'line', 'tags'} ya da None. Once sutunlu tablo (F910, SD408),
    sonra duz metin bicimleri denenir; etiketi (TAG/MANDATORY) olan sonuc tercih edilir."""
    col = _column_rule(profile, label)
    if col and col['tags'] and col['text']:
        return col
    cands = [c for c in (col, _inline_rule(profile, label)) if c]
    if not cands:
        return None
    return max(cands, key=lambda c: (bool(c['tags']) and bool(c['text']), bool(c['text']), bool(c['tags'])))


def _column_rule(profile, label):
    """Rehberde alan etiketini bulur. {'mandatory', 'text', 'line'} ya da None.
    Etiket, tablo hucresinde birkac satira bolunmus olabilir ('Exclusions from' / 'scope'); ayni sutunda devam eder."""
    want = _compact(label)
    if len(want) < 4:
        return None
    lines = guide_lines(profile)
    first = re.escape(str(label).split()[0])
    best = None
    for i, ln in enumerate(lines):
        for m in re.finditer(r'(?:(?<=\s)|^)' + first + r'\b', ln, re.I):
            col = m.start()
            acc, used = '', 0
            for k in range(i, min(i + 4, len(lines))):
                tok = _column_tokens(lines[k], col)
                if not tok or TAG_WORDS.match(tok):
                    break
                acc += _compact(tok)
                used = k - i + 1
                if acc.startswith(want) or want.startswith(acc) is False:
                    break
            if not acc.startswith(want):
                continue
            # aciklama: etiketin sagindaki sutun (ilk satirda etiketten sonra gelen metnin baslangici)
            rest = lines[i][col:]
            mm = re.match(r'\S+(?: \S+)*(\s{2,})', rest)
            dcol = col + mm.end() if mm else None
            desc, tags, blank = [], [], 0
            for k in range(i, min(i + 40, len(lines))):
                ln2 = lines[k]
                if _PAGE_FOOT.match(ln2):
                    continue
                if not ln2.strip():
                    blank += 1
                    if blank >= 2 and desc:
                        break
                    continue
                blank = 0
                left = _column_tokens(ln2, col)
                if k >= i + used and left and not TAG_WORDS.match(left) and _compact(left) != want and k > i + 1 and \
                        not (dcol and len(ln2) > dcol and ln2[:col].strip() == '' and len(left) > 30):
                    # yeni bir etiket ayni sutunda basladi
                    if not ln2[col:].upper().startswith(('MANDATORY', 'TEXT', 'TAG', 'FREE', 'DROP', 'UNTAG')):
                        break
                if left and TAG_WORDS.match(left):
                    tags.append(left.upper())
                if dcol is not None and len(ln2) > dcol:
                    seg = ln2[dcol:]
                    seg = re.split(r'\s{3,}', seg.strip(), maxsplit=1)[0] if ln2[dcol:dcol + 1] != ' ' else ''
                    if seg:
                        desc.append(seg)
            text = re.sub(r'\s+', ' ', ' '.join(desc)).strip()
            if re.search(r'\.{4,}', lines[i]) or re.search(r'\s\d{1,3}\s*$', lines[i]):
                continue                                    # icindekiler satiri
            cand = {'mandatory': any('MANDATORY' in t for t in tags), 'text': text, 'line': i, 'tags': tags}
            score = (bool(tags), bool(text))
            if best is None or score > (bool(best['tags']), bool(best['text'])):
                best = cand
    return best


@functools.lru_cache(maxsize=None)
def chapter_guidance(profile):
    """Rehberin 'How to complete the Detailed Section' kismindaki bolum beklentileri: {'1': metin, '2': ...}."""
    lines = guide_lines(profile)
    start = next((i for i, ln in enumerate(lines) if re.match(r'^\s*(Section 3|How to complete the Detailed)', ln, re.I)
                  and i > 150), None)
    out, cur, buf = {}, None, []
    for ln in lines[start or 0:]:
        if _PAGE_FOOT.match(ln):
            continue
        m = re.match(r'^(\d{1,2})\.\s+([A-Z][^.]{3,90})$', ln.strip())
        if m and not re.search(r'\.{4,}|\s\d+$', ln):
            if cur and buf:
                out.setdefault(cur, '\n'.join(buf).strip())
            cur, buf = m.group(1), [ln.strip()]
            continue
        if cur:
            buf.append(ln.rstrip())
        if re.match(r'^\s*Appendix\s+\d', ln) and cur:
            break
    if cur and buf:
        out.setdefault(cur, '\n'.join(buf).strip())
    return {k: re.sub(r'\n{3,}', '\n\n', v) for k, v in out.items()}


def skill_rules(profile):
    """Skill talimatindaki madde isaretli kurallar: [(baslik, kural)]."""
    out, head = [], ''
    for ln in pack(profile)['skill'].split('\n'):
        m = re.match(r'^#{2,3}\s+(.*)', ln)
        if m:
            head = m.group(1).strip()
            continue
        m = re.match(r'^\s*(?:-|\d+\.)\s+(.*)', ln)
        if m and head:
            out.append((head, m.group(1).strip()))
    return out
