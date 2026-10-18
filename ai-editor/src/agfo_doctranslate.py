# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4 - bicim koruyan belge cevirisi (Tk yok).

Belge bloklara ayrilir; metin tasiyan her paragraf ve tablo hucresi numarali bir parca olur (⟦12⟧ metin).
Parcalar karakter sinirina gore gruplanip yapay zekaya gonderilir; yanit isaretlerden geri ayrilir. Satir ici
bicim (** * <u>) Markdown olarak gider ve geri gelir; baslik, liste, hizalama, tablo yapisi ve resimler hic
yapay zekaya gitmeden yerinde kalir. Eksik donen parcalar tek tek yeniden istenir; yine gelmezse ozgun kalir.
"""
from __future__ import annotations

import copy
import re

import agfo_richdoc as R

MARK_RX = re.compile(r'(?:⟦|\[\[|【)\s*(\d{1,5})\s*(?:⟧|\]\]|】)')
BATCH_CHARS = 3500

INSTRUCTION = (
    'Translate every numbered segment into {lang}. Each segment starts with a marker like ⟦12⟧. '
    'Return ALL segments in the same order, each starting with its unchanged marker, one segment per paragraph, '
    'with a blank line between segments. Translate only the text after the marker; do not merge, split, skip or '
    'renumber segments, do not add notes. Keep inline Markdown markers (**bold**, *italic*, <u>underline</u>) around '
    'the corresponding translated words. Keep numbers, clause references, codes, units, names, URLs and e-mail '
    'addresses exactly. Use the established professional terminology of the field (for example food safety, '
    'certification and audit terms).')


def segments(blocks):
    """[(anahtar, markdown)] - anahtar: (blok_no,) paragraf icin, (blok_no, satir, sutun) tablo hucresi icin."""
    out = []
    for bi, b in enumerate(blocks):
        if b['t'] == 'p':
            md = R.runs_to_md(b['runs']).strip()
            if re.search(r'\w', md):
                out.append(((bi,), md))
        elif b['t'] == 'table':
            for ri, row in enumerate(b['rows']):
                for ci, cell in enumerate(row):
                    md = R.runs_to_md(cell).strip()
                    if re.search(r'\w', md):
                        out.append(((bi, ri, ci), md))
    return out


def batches(segs, limit=BATCH_CHARS):
    out, cur, size = [], [], 0
    for n, (key, md) in enumerate(segs):
        if cur and size + len(md) > limit:
            out.append(cur)
            cur, size = [], 0
        cur.append((n, key, md))
        size += len(md) + 8
    if cur:
        out.append(cur)
    return out


def batch_text(batch):
    return '\n\n'.join('⟦%d⟧ %s' % (n, md.replace('\n', ' ')) for n, _key, md in batch)


def parse(text, wanted=None):
    """Yanittaki ⟦n⟧ isaretlerine gore {n: metin}. wanted verilirse yalniz o numaralar alinir."""
    out = {}
    text = text or ''
    marks = list(MARK_RX.finditer(text))
    for k, m in enumerate(marks):
        n = int(m.group(1))
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        seg = text[m.end():end].strip()
        seg = re.sub(r'\s*\n\s*', ' ', seg).strip()
        if wanted is not None and n not in wanted:
            continue
        if seg and n not in out:
            out[n] = seg
    return out


def apply(blocks, segs, done):
    """done: {parca_no: ceviri_md}. Yeni blok listesi (derin kopya) dondurur."""
    new = copy.deepcopy(blocks)
    for n, (key, _md) in enumerate(segs):
        if n not in done:
            continue
        runs = R.md_inline(done[n])
        if len(key) == 1:
            new[key[0]]['runs'] = runs
        else:
            new[key[0]]['rows'][key[1]][key[2]] = runs
    return new


def translate_blocks(blocks, call, lang, progress=None, cancelled=None, limit=BATCH_CHARS):
    """call(metin, talimat) -> ceviri metni. (yeni_bloklar, istatistik) dondurur."""
    segs = segments(blocks)
    groups = batches(segs, limit)
    done = {}
    instruction = INSTRUCTION.format(lang=lang)
    missing_total = 0
    for gi, group in enumerate(groups):
        if cancelled and cancelled():
            raise InterruptedError('Çeviri durduruldu.')
        if progress:
            progress(gi, len(groups))
        wanted = {n for n, _k, _m in group}
        got = parse(call(batch_text(group), instruction), wanted)
        lost = [g for g in group if g[0] not in got]
        if lost and len(lost) < len(group):
            for item in lost:                       # eksik parcalari tek tek iste
                if cancelled and cancelled():
                    raise InterruptedError('Çeviri durduruldu.')
                one = parse(call(batch_text([item]), instruction), {item[0]})
                if not one:
                    raw = call(item[2], instruction.replace('Each segment starts with a marker like ⟦12⟧. ', ''))
                    one = {item[0]: re.sub(r'\s*\n\s*', ' ', MARK_RX.sub('', raw)).strip()} if raw.strip() else {}
                got.update(one)
        elif lost:
            # hic isaret gelmediyse: grup tek parcaysa yaniti dogrudan kullan
            if len(group) == 1:
                raw = call(group[0][2], instruction)
                got = {group[0][0]: re.sub(r'\s*\n\s*', ' ', MARK_RX.sub('', raw)).strip()}
        missing_total += len([g for g in group if g[0] not in got])
        done.update(got)
    if progress:
        progress(len(groups), len(groups))
    return apply(blocks, segs, done), {'segments': len(segs), 'batches': len(groups), 'missing': missing_total}


def pairs(orig, new):
    """Yan yana gorunum icin (ozgun_blok, ceviri_blok) ciftleri."""
    return list(zip(orig, new))


# ----------------------------------------------------------------------------- PDF metni -> bloklar
_END_RX = re.compile(r'[.:;!?…)"”»]$')
_BULLET_RX = re.compile(r'^\s*([•●▪◦\-–*]|\d{1,3}[.)]|\d+(\.\d+)+\.?|[a-z][.)])\s+')


def reflow(text):
    """PDF'ten gelen sabit satirlari paragraflara birlestirir (madde ve madde numaralari yeni paragraf baslatir)."""
    paras = []
    for chunk in re.split(r'\n\s*\n', (text or '').replace('\r', '')):
        cur = ''
        for line in chunk.split('\n'):
            s = line.strip()
            if not s:
                continue
            if not cur:
                cur = s
                continue
            starts_new = bool(_BULLET_RX.match(s)) or (bool(_END_RX.search(cur)) and s[:1].isupper())
            if starts_new or len(cur) < 3:
                paras.append(cur)
                cur = s
            elif cur.endswith('-') and s[:1].islower():
                cur = cur[:-1] + s
            else:
                cur += ' ' + s
        if cur:
            paras.append(cur)
    return paras


def pdf_units_to_blocks(units, title=None):
    blocks = []
    if title:
        blocks.append(R.para(text=title, style='h1'))
    for u in units:
        body = reflow(u.get('text') or '')
        if not body:
            continue
        blocks.append(R.para(text=str(u.get('loc') or ''), style='h3'))
        for p in body:
            m = _BULLET_RX.match(p)
            if m and m.group(1) in ('•', '●', '▪', '◦', '-', '–', '*'):
                blocks.append(R.para(text=p[m.end():], lst='bullet'))
            else:
                blocks.append(R.para(text=p))
    return blocks
