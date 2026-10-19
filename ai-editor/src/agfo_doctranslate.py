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
BATCH_CHARS = 2500        # 1.4.8: paralel gonderimde daha kucuk gruplar daha erken biter

INSTRUCTION = (
    'Translate every numbered segment into {lang}. Each segment starts with a marker like ⟦12⟧. '
    'Return ALL segments in the same order, each starting with its unchanged marker, one segment per paragraph, '
    'with a blank line between segments. Translate only the text after the marker; do not merge, split, skip or '
    'renumber segments, do not add notes. Keep inline Markdown markers (**bold**, *italic*, <u>underline</u>) around '
    'the corresponding translated words. Keep dot leaders (......) and trailing page numbers of table-of-contents '
    'lines. Keep numbers, clause references, codes, units, names, URLs and e-mail '
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


def _translate_group(group, call, instruction, cancelled):
    """Bir grubu cevirir; eksik donen parcalari tek tek yeniden ister. {n: ceviri} dondurur."""
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
    elif lost and len(group) == 1:
        # hic isaret gelmediyse: grup tek parcaysa yaniti dogrudan kullan
        raw = call(group[0][2], instruction)
        got = {group[0][0]: re.sub(r'\s*\n\s*', ' ', MARK_RX.sub('', raw)).strip()}
    return got


_NUM_RX = re.compile(r'(?<![\d.,])\d+(?:[.,]\d+)*(?![\d])')


def plan_reuse(segs):
    """1.4.9: ayni metin bir kez cevrilir (sayfa ustbilgi/altbilgileri, tekrar eden hucreler); yalniz sayilari farkli
    kisa metinler ("Page 3 of 20") tek ornekten sayilar yerlestirilerek uretilir. Donus: (gonderilecek parca
    numaralari, {parca: (ornek_parca, [(ornek_sayi, sayi), ...] | None)})."""
    reuse, by_text, tmpl = {}, {}, {}
    for n, (_key, md) in enumerate(segs):
        norm = re.sub(r'\s+', ' ', md).strip()
        if norm in by_text:
            reuse[n] = (by_text[norm], None)
            continue
        by_text[norm] = n
        if len(norm) <= 80 and _NUM_RX.search(norm):
            tmpl.setdefault(_NUM_RX.sub('#', norm), []).append(n)
    for ns in tmpl.values():
        if len(ns) < 2:
            continue
        nums = {n: _NUM_RX.findall(segs[n][1]) for n in ns}
        rep = next((n for n in ns if len(set(nums[n])) == len(nums[n])), None)
        if rep is None:
            continue
        for m in ns:
            if m != rep and len(nums[m]) == len(nums[rep]):
                reuse[m] = (rep, list(zip(nums[rep], nums[m])))
    return [n for n in range(len(segs)) if n not in reuse], reuse


def _derive(text, mapping):
    """Ornek ceviriye bu parcanin sayilarini yerlestirir; her ornek sayi ceviride tam bir kez gecmiyorsa None."""
    if not mapping:
        return text
    found = _NUM_RX.findall(text)
    sub = dict(mapping)
    if any(found.count(a) != 1 for a, _b in mapping):
        return None
    if any(re.search(r'(?<![\d.,])%s(?![\d])\s*[\'’]' % re.escape(a), text) for a, b in mapping if a != b):
        return None                     # Turkce ek sayiya bagli (1'de / 3'te): ayrica cevrilir
    return _NUM_RX.sub(lambda m: sub.get(m.group(0), m.group(0)), text)


def translate_blocks(blocks, call, lang, progress=None, cancelled=None, limit=BATCH_CHARS, workers=1, on_event=None):
    """call(metin, talimat) -> ceviri metni. (yeni_bloklar, istatistik) dondurur.

    1.4.8: workers > 1 ise gruplar ayni anda gonderilir (sira korunur). on_event(tur, parcalar) her grup basladiginda
    ('start') ve bittiginde ('done', ceviriler {anahtar: md} ile) cagrilir - canli vurgulama icin; is parcaciginda
    calisir, arayuze kendisi aktarmalidir.
    1.4.9: tekrar eden metinler bir kez cevrilir (tutarli ve daha hizli); bkz. plan_reuse."""
    import concurrent.futures as cf
    segs = segments(blocks)
    send, reuse = plan_reuse(segs)
    followers = {}
    for m, (rep, _mp) in reuse.items():
        followers.setdefault(rep, []).append(m)
    workers = max(1, min(int(workers or 1), 8))
    items = [(n, segs[n][0], segs[n][1]) for n in send]
    if workers > 1:
        # kucuk belgede bile isler paylasilsin: her istek icin ~3 grup, grup en az 800 karakter
        total = sum(len(md) for _n, _k, md in items)
        limit = max(800, min(limit, -(-total // (workers * 3))))
    groups = _batches_items(items, limit)
    done = {}
    instruction = INSTRUCTION.format(lang=lang)
    finished = [0]

    def run(group):
        if cancelled and cancelled():
            raise InterruptedError('Çeviri durduruldu.')
        keys = [key for n, key, _m in group] + [segs[m][0] for n, _k, _m in group for m in followers.get(n, [])]
        if on_event:
            on_event('start', keys, None)
        got = _translate_group(group, call, instruction, cancelled)
        if on_event:
            res = {key: got[n] for n, key, _m in group if n in got}
            for n, _k, _m in group:
                for m in followers.get(n, []):
                    if n in got:
                        res[segs[m][0]] = got[n]
            on_event('done', keys, res)
        return got

    def run_all(groups):
        if workers == 1 or len(groups) < 2:
            out = []
            for g in groups:
                out.append(run(g))
                finished[0] += 1
                if progress:
                    progress(finished[0], total_groups[0])
            return out
        out = [None] * len(groups)
        with cf.ThreadPoolExecutor(max_workers=min(workers, len(groups)), thread_name_prefix='agfo-tr') as ex:
            futs = {ex.submit(run, g): k for k, g in enumerate(groups)}
            try:
                for f in cf.as_completed(futs):
                    out[futs[f]] = f.result()
                    finished[0] += 1
                    if progress:
                        progress(finished[0], total_groups[0])
            except BaseException:
                for f in futs:
                    f.cancel()
                raise
        return out

    total_groups = [len(groups)]
    if progress:
        progress(0, len(groups))
    results = run_all(groups)
    for got in results:
        done.update(got)
    # tekrar eden parcalar: ornek ceviriden; sayilar yerlestirilemezse ayrica cevrilir
    again = []
    for m, (rep, mapping) in sorted(reuse.items()):
        if rep in done:
            t = _derive(done[rep], mapping)
            if t is not None:
                done[m] = t
                continue
        if rep in done or mapping:
            again.append((m, segs[m][0], segs[m][1]))
    if again:
        extra = _batches_items(again, limit)
        total_groups[0] += len(extra)
        for got in run_all(extra):
            done.update(got)
        groups = groups + extra
    missing_total = len([n for n in range(len(segs)) if n not in done])
    return apply(blocks, segs, done), {'segments': len(segs), 'batches': len(groups), 'missing': missing_total,
                                       'reused': len(reuse) - len(again)}


def _batches_items(items, limit):
    out, cur, size = [], [], 0
    for it in items:
        if cur and size + len(it[2]) > limit:
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += len(it[2]) + 8
    if cur:
        out.append(cur)
    return out


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
