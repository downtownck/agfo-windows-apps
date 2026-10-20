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
