# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.5 - seslendirme (AI Manager 17.12+ / EMA Lightning).

Arayuzden bagimsiz mantik: belge metnini seslendirilecek duz metne cevirme, uzun metni AI Manager'in tek is
sinirina gore bolme ve is akisi (gonder -> durumu izle -> MP3'u indir). Ag cagrilari ManagerBackend uzerinden.
"""
from __future__ import annotations

import os
import re
import time
import uuid

PART_LIMIT = 55_000          # AI Manager / EMA tek iste 60.000 karakter kabul eder; okuma metni uzayabilir
POLL_SECONDS = 2.0

_IMG = re.compile(r'!\[[^\]]*\](\([^)]*\))?')
_LINK = re.compile(r'\[([^\]]+)\]\([^)]+\)')
_EMPH = re.compile(r'(\*\*|__|\*|_|~~|`)(?=\S)(.+?)(?<=\S)\1', re.S)
_TAGS = re.compile(r'</?(u|b|i|em|strong|span|mark|sub|sup)\b[^>]*>', re.I)
_TERMINAL = ('.', '!', '?', '…', ':', ';')


def _finish(line: str) -> str:
    """Baslik/madde gibi noktalamasiz satira nokta koyar ki EMA cumle sonunda dursun."""
    line = line.rstrip()
    if not line or line.rstrip('"”’\')»').endswith(_TERMINAL):
        return line
    return line + '.'


def markdown_to_speech(md: str) -> str:
    """Editorun Markdown'ini okunacak duz metne cevirir: basliklar, maddeler ve tablo hucreleri cumle olur,
    resimler ve bicim isaretleri duser, paragraf aralari (EMA'da paragraf duraklamasi) korunur."""
    out = []
    for raw in (md or '').replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = _IMG.sub('', raw).strip()
        if not line:
            out.append('')
            continue
        if re.fullmatch(r'\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?', line):      # tablo ayirici satiri
            continue
        if line.startswith('|') or line.count('|') >= 2:
            cells = [c.strip() for c in line.strip('|').split('|')]
            line = ', '.join(c for c in cells if c)
        heading = re.match(r'^#{1,6}\s+(.*)$', line)
        if heading:
            line = heading.group(1)
        line = re.sub(r'^>\s?', '', line)                                      # alinti
        line = re.sub(r'^(\s*[-*+•]\s+|\s*\d+[.)]\s+)', '', line)              # madde isaretleri
        # Markdown kacislari (1\\. \\* \\#): bicim isareti sanilmasin diye once saklanir, sonda geri konur
        line = re.sub(r'\\([\\`*_{}\[\]()#+\-.!|>~])', lambda m: '\x00%d\x00' % ord(m.group(1)), line)
        line = _LINK.sub(r'\1', line)
        line = _TAGS.sub('', line)
        for _ in range(3):
            line = _EMPH.sub(r'\2', line)
        line = re.sub(r'\x00(\d+)\x00', lambda m: chr(int(m.group(1))), line)
        line = re.sub(r'[ \t]+', ' ', line).strip()
        if not line:
            continue
        is_block = bool(heading) or raw.lstrip().startswith(('-', '*', '+', '•', '|', '>')) or re.match(r'^\s*\d+[.)]\s', raw)
        out.append(_finish(line) if is_block else line)
    text = '\n'.join(out)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text


def split_parts(text: str, limit: int = PART_LIMIT) -> list:
    """Paragraf sinirinda en fazla `limit` karakterlik parcalar (tek paragraf cok uzunsa cumle sinirinda)."""
    text = (text or '').strip()
    if len(text) <= limit:
        return [text] if text else []
    parts, cur = [], ''
    for para in re.split(r'\n\s*\n', text):
        para = para.strip()
        if not para:
            continue
        pieces = [para]
        if len(para) > limit:
            pieces, buf = [], ''
            for sent in re.split(r'(?<=[.!?…])\s+', para):
                if buf and len(buf) + len(sent) + 1 > limit:
                    pieces.append(buf)
                    buf = ''
                buf = (buf + ' ' + sent).strip()
            if buf:
                pieces.append(buf)
        for piece in pieces:
            if cur and len(cur) + len(piece) + 2 > limit:
                parts.append(cur)
                cur = ''
            cur = piece if not cur else cur + '\n\n' + piece
    if cur:
        parts.append(cur)
    return parts


class Cancelled(Exception):
    pass


def narrate(backend, text: str, dest: str, *, reading_script=True, script_ready=False, speed=1.0, pause_ms=None,
            paragraph_pause_ms=None, title='', progress=None, cancel=None, sleep=time.sleep, poll=None) -> dict:
    """Metni seslendirir ve MP3'u `dest`e yazar. Uzun metin birden cok ise bolunur, parcalar sirayla birlestirilir.
    progress(mesaj) ilerleme bildirir; cancel() True donerse durur. Donus: {'path', 'parts', 'duration_ms', 'scripts'}."""
    poll = POLL_SECONDS if poll is None else poll
    parts = split_parts(text)
    if not parts:
        raise ValueError('Seslendirilecek metin boş.')
    tmp_files, durations, scripts = [], [], []
    run_id = uuid.uuid4().hex[:12]
    try:
        for i, part in enumerate(parts, 1):
            label = 'Bölüm %d/%d: ' % (i, len(parts)) if len(parts) > 1 else ''
            if cancel and cancel():
                raise Cancelled()
            job = backend.speech_submit(part, reading_script=reading_script, script_ready=script_ready, speed=speed,
                                        pause_ms=pause_ms, paragraph_pause_ms=paragraph_pause_ms, fmt='mp3',
                                        title=title, request_id='editor-%s-%d' % (run_id, i))
            jid = job.get('job') or ''
            if not jid:
                raise RuntimeError('AI Manager iş kimliği döndürmedi.')
            status = job.get('status') or 'queued'
            started = time.time()
            limit = max(900, len(part) // 1000 * 40 + 300)
            while status not in ('complete', 'failed', 'cancelled'):
                if cancel and cancel():
                    raise Cancelled()
                if time.time() - started > limit:
                    raise RuntimeError('Seslendirme %d dakikada bitmedi; AI Manager › İşler sayfasından durumuna bakın.' % (limit // 60))
                if progress:
                    progress(label + {'queued': 'sırada…', 'retry': 'yeniden deneniyor…', 'processing': 'okuma metni ve ses hazırlanıyor…',
                                      'storing': 'ses kaydediliyor…'}.get(status, status + '…'))
                sleep(poll)
                job = backend.speech_status(jid)
                status = job.get('status') or ''
            if status != 'complete':
                raise RuntimeError(job.get('error') or 'Seslendirme başarısız oldu.')
            if progress:
                progress(label + 'ses indiriliyor…')
            part_path = dest + '.%d.part.mp3' % i
            backend.speech_download(jid, part_path)
            tmp_files.append(part_path)
            if job.get('duration_ms'):
                durations.append(int(job['duration_ms']))
            if isinstance(job.get('script'), dict):
                scripts.append(job['script'])
        with open(dest + '.tmp', 'wb') as out:
            for p in tmp_files:
                with open(p, 'rb') as fh:
                    out.write(fh.read())
        os.replace(dest + '.tmp', dest)
    finally:
        for p in tmp_files + [dest + '.tmp']:
            try:
                os.unlink(p)
            except OSError:
                pass
    return {'path': dest, 'parts': len(parts), 'duration_ms': sum(durations) if durations else None, 'scripts': scripts}


def script_note(scripts: list) -> str:
    """Okuma metni ozetini kullaniciya okunur yazar."""
    if not scripts:
        return ''
    done = [s for s in scripts if s.get('status') == 'done']
    if not done:
        st = scripts[0].get('status')
        if st == 'skipped':
            return 'okuma metni hazırlanamadı (%s); metin olduğu gibi okundu' % (scripts[0].get('reason') or 'model yok')
        if st == 'ready':
            return 'önizlenen okuma metni kullanıldı'
        return ''
    chunks = sum(int(s.get('chunks') or 0) for s in done)
    kept = sum(int(s.get('kept_original') or 0) for s in done)
    note = 'okuma metni: %d bölüm (%s)' % (chunks, done[0].get('model') or 'AI')
    if kept:
        note += ', %d bölüm denetimden geçmediği için özgün okundu' % kept
    return note


# --------------------------------------------------------------------------- 1.6: bolum plani
SECTION_MAX = 15_000          # ~11 dk ses; daha uzun bolum mantikli parcalara ayrilir
SECTION_MIN = 300             # bundan kisa bolum (or. hemen alt basliga gecen baslik) sonrakiyle birlesir
CHARS_PER_SECOND = 22.0       # EMA olcumu: ~450 karakter = 19-20 sn


def _headings(lines):
    out = []
    for i, line in enumerate(lines):
        m = re.match(r'^(#{1,6})\s+(.+?)\s*#*\s*$', line.strip())
        if m:
            out.append((i, len(m.group(1)), markdown_to_speech(m.group(2)).rstrip('.') or m.group(2)))
    return out


def _balanced_parts(text: str, limit: int) -> list:
    """Metni paragraf sinirlarinda, boyu birbirine yakin ve `limit`i asmayan parcalara boler."""
    paras = [p for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]
    if len(text) <= limit or len(paras) < 2:
        return split_parts(text, limit)
    n = -(-len(text) // limit)                       # gereken en az parca
    target = len(text) / n
    parts, cur = [], ''
    for p in paras:
        if cur and (len(cur) + len(p) + 2 > limit or (len(cur) >= target and len(parts) < n - 1)):
            parts.append(cur)
            cur = ''
        cur = p if not cur else cur + '\n\n' + p
    if cur:
        parts.append(cur)
    out = []
    for p in parts:                                  # tek paragrafi limitten uzun olanlar cumle sinirinda
        out.extend(split_parts(p, limit) if len(p) > limit else [p])
    return out


def plan_sections(md: str, max_chars: int = SECTION_MAX, min_chars: int = SECTION_MIN, untitled: str = 'Bölüm') -> list:
    """Belgeyi seslendirme bolumlerine ayirir. Once baslik yapisi: en az iki kez kullanilan en ust baslik duzeyi bolum
    sinirlaridir (tek bir belge basligi H1 ise H2'ler bolum olur). Cok uzun bolum once kendi alt basliklarina, sonra
    paragraf sinirinda dengeli parcalara ayrilir. Cok kisa bolum sonrakine katilir.
    Donus: [{'title', 'level', 'text' (okunacak metin), 'chars', 'seconds'}]."""
    lines = (md or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    heads = _headings(lines)
    levels = sorted({lv for _i, lv, _t in heads})
    split_level = next((lv for lv in levels if sum(1 for h in heads if h[1] == lv) >= 2), None)

    def build(start, end, title, level):
        text = markdown_to_speech('\n'.join(lines[start:end]))
        return {'title': title, 'level': level, 'text': text, 'start': start, 'end': end}

    raw = []
    if split_level is None:
        title = heads[0][2] if heads else ''
        raw.append(build(0, len(lines), title, heads[0][1] if heads else 0))
    else:
        cuts = [h for h in heads if h[1] <= split_level]
        first = cuts[0][0]
        if any(l.strip() for l in lines[:first]):
            pre = [h for h in heads if h[0] < first]
            raw.append(build(0, first, pre[0][2] if pre else 'Giriş', pre[0][1] if pre else 0))
        for k, (i, lv, title) in enumerate(cuts):
            end = cuts[k + 1][0] if k + 1 < len(cuts) else len(lines)
            raw.append(build(i, end, title, lv))

    merged = []
    for s in raw:
        if not s['text']:
            continue
        if merged and len(merged[-1]['text']) < min_chars:
            prev = merged.pop()
            title = ' – '.join(t for t in (prev['title'], s['title']) if t)
            s = {'title': title, 'level': prev['level'], 'text': prev['text'] + '\n\n' + s['text'],
                 'start': prev['start'], 'end': s['end']}
        merged.append(s)
    if len(merged) > 1 and len(merged[-1]['text']) < min_chars:     # sondaki kisa bolum (or. "Sonuc") oncekine katilir
        last = merged.pop()
        merged[-1] = dict(merged[-1], text=merged[-1]['text'] + '\n\n' + last['text'], end=last['end'])

    out = []
    for s in merged:
        if len(s['text']) <= max_chars:
            out.append(s)
            continue
        sub = [h for h in heads if s['start'] < h[0] < s['end']]
        pieces = []
        if sub:                                      # once alt basliklar
            bounds = [s['start']] + [h[0] for h in sub] + [s['end']]
            for a, b in zip(bounds, bounds[1:]):
                t = markdown_to_speech('\n'.join(lines[a:b]))
                if t:
                    pieces.extend(_balanced_parts(t, max_chars) if len(t) > max_chars else [t])
            # cok kisa alt bolumleri komsuyla birlestir
            packed = []
            for p in pieces:
                if packed and len(packed[-1]) + len(p) + 2 <= max_chars and (len(packed[-1]) < min_chars * 4 or len(p) < min_chars * 4):
                    packed[-1] += '\n\n' + p
                else:
                    packed.append(p)
            pieces = packed
        else:
            pieces = _balanced_parts(s['text'], max_chars)
        for n, p in enumerate(pieces, 1):
            out.append({'title': ('%s (%d/%d)' % (s['title'], n, len(pieces))) if s['title'] else '', 'level': s['level'], 'text': p})

    if len(out) > 1 or not (out and out[0]['title']):
        for n, s in enumerate(out, 1):
            if not s['title']:
                s['title'] = '%s %d' % (untitled, n)
    for s in out:
        s.pop('start', None)
        s.pop('end', None)
        s['chars'] = len(s['text'])
        s['seconds'] = int(round(s['chars'] / CHARS_PER_SECOND))
    return out


def safe_name(title: str, n: int) -> str:
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', ' ', title)
    base = re.sub(r'\s+', ' ', base).strip(' .') or 'Bölüm'
    return '%02d - %s.mp3' % (n, base[:80].rstrip(' .'))


def narrate_sections(backend, sections: list, dest: str, mode: str = 'single', status=None, cancel=None,
                     sleep=time.sleep, **opts) -> dict:
    """Secili bolumleri sirayla seslendirir. mode='single': `dest` tek MP3; mode='files': `dest` klasor, her bolum
    'NN - Baslik.mp3' ve bir .m3u calma listesi. status(i, durum, bilgi) her bolumun durumunu bildirir
    (bekliyor / hazırlanıyor / tamam / hata). Donus: {'paths', 'duration_ms', 'scripts', 'failed'}."""
    if not sections:
        raise ValueError('Seçili bölüm yok.')
    if mode == 'files':
        os.makedirs(dest, exist_ok=True)
    tmp_dir = (dest if mode == 'files' else os.path.dirname(dest) or '.')
    produced, durations, scripts, failed = [], [], [], []
    for i, s in enumerate(sections):
        if cancel and cancel():
            raise Cancelled()
        if status:
            status(i, 'hazırlanıyor', '')
        target = os.path.join(dest, safe_name(s['title'], i + 1)) if mode == 'files' else os.path.join(tmp_dir, '.agfo-bolum-%d.mp3' % i)

        def prog(msg, _i=i):
            if status:
                status(_i, 'hazırlanıyor', msg)
        try:
            res = narrate(backend, s['text'], target, title=s['title'], progress=prog, cancel=cancel, sleep=sleep, **opts)
        except Cancelled:
            raise
        except Exception as e:  # bir bolumun hatasi digerlerini durdurmaz
            failed.append((i, str(e)))
            if status:
                status(i, 'hata', str(e))
            continue
        produced.append(target)
        if res.get('duration_ms'):
            durations.append(res['duration_ms'])
        scripts.extend(res.get('scripts') or [])
        if status:
            secs = (res.get('duration_ms') or 0) / 1000.0
            status(i, 'tamam', '%d:%02d' % (secs // 60, secs % 60) if secs else '')
    if not produced:
        raise RuntimeError('Hiçbir bölüm seslendirilemedi: ' + (failed[0][1] if failed else ''))
    if mode == 'files':
        with open(os.path.join(dest, '00 - çalma listesi.m3u'), 'w', encoding='utf-8') as fh:
            fh.write('#EXTM3U\n' + ''.join(os.path.basename(p) + '\n' for p in produced))
        paths = produced
    else:
        with open(dest + '.tmp', 'wb') as out:
            for p in produced:
                with open(p, 'rb') as fh:
                    out.write(fh.read())
        os.replace(dest + '.tmp', dest)
        for p in produced:
            try:
                os.unlink(p)
            except OSError:
                pass
        paths = [dest]
    return {'paths': paths, 'duration_ms': sum(durations) if durations else None, 'scripts': scripts, 'failed': failed}
