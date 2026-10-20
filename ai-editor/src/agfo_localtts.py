# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.7 - bu bilgisayardaki AGFO Ses Servisi (EMA Lightning).

AGFO-Ses-Kur betigi servisi %LOCALAPPDATA%\\AGFO\\TTS altina kurar ve adresle anahtari oradaki .env dosyasina
yazar; editor servisi bu dosyadan kendiliginden bulur. LocalSpeechBackend, AI Manager'in seslendirme uclariyla
ayni arayuzu sunar (speech_submit/status/download, speech_quick, sozluk), boylece "Sesli oku", "Ses dosyasi"
ve sozluk penceresi hangi servisin kullanildigini bilmeden calisir.

AI okuma metni yerelde uretilmez: istenirse metin sitedeki AI Manager'a (/editor/speech-script) gonderilir,
donen okuma metni burada sozluk yeniden uygulanmadan seslendirilir. Site yoksa ya da hata verirse metin yerel
sozlukle okunur.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid

from agfo_ai_client import AIError, _error_message, _json

MP3_BITRATE = 96_000      # servis MP3'u 96 kbit/s yazar; onbellekten gelen sesin suresi buradan kestirilir


def install_dir() -> str:
    base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    return os.path.join(base, 'AGFO', 'TTS')


def read_config(path: str | None = None) -> dict | None:
    """Kurulu servisin {'endpoint', 'token', 'dir'} bilgisi ya da None."""
    path = path or os.path.join(install_dir(), '.env')
    env = {}
    try:
        with open(path, encoding='utf-8-sig') as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    except OSError:
        return None
    token = env.get('AGFO_TTS_TOKEN', '')
    if not token:
        return None
    port = env.get('AGFO_TTS_PORT', '8765')
    return {'endpoint': 'http://127.0.0.1:%s' % port, 'token': token, 'dir': os.path.dirname(path)}


class LocalSpeechBackend:
    kind = 'local'
    name = 'Bu bilgisayar'

    def __init__(self, endpoint: str, token: str, site=None, opener=None):
        self.endpoint = endpoint.rstrip('/')
        self.token = token
        self.site = site                     # AI Manager baglantisi (okuma metni ve ortak sozluk icin), yoksa None
        # Sistem proxy'si 127.0.0.1 isteklerini yoldan cikarmasin
        self._opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._jobs: dict[str, dict] = {}

    # ------------------------------------------------------------------ http
    def _raw(self, route, payload=None, timeout=600):
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
        hdrs = {'X-AGFO-Token': self.token, 'Accept': '*/*'}
        if data is not None:
            hdrs['Content-Type'] = 'application/json; charset=utf-8'
        req = urllib.request.Request(self.endpoint + route, data=data, headers=hdrs, method='POST' if data is not None else 'GET')
        try:
            with self._opener.open(req, timeout=timeout) as r:
                return r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            body = e.read(65536) or b''
            decoded = _json(body)
            if e.code == 401:
                raise AIError('Bu bilgisayardaki ses servisi anahtarı kabul etmedi; AGFO-Ses-Kur betiğini yeniden çalıştırın.')
            detail = decoded.get('detail') if isinstance(decoded, dict) else None
            raise AIError('Yerel ses servisi: %s' % (detail if isinstance(detail, str) else _error_message(decoded, e.code)))
        except (urllib.error.URLError, OSError) as e:
            raise AIError('Bu bilgisayardaki ses servisine ulaşılamadı (%s). Servis kapalı olabilir: oturumu kapatıp açın ya da '
                          'AGFO-Ses-Kur betiğini yeniden çalıştırın.' % getattr(e, 'reason', e))

    def _call(self, route, payload=None, timeout=120):
        body, _h = self._raw(route, payload, timeout)
        d = _json(body)
        if not isinstance(d, dict):
            raise AIError('Yerel ses servisi beklenmeyen yanıt döndürdü.')
        return d

    def health(self) -> dict:
        return self._call('/health', timeout=5)

    def tts(self, text: str, apply_lexicon: bool = True, speed: float = 1.0, pause_ms: int = 350,
            paragraph_pause_ms: int = 700, timeout=1800):
        """(mp3_bytes, saniye)."""
        payload = {'text': text, 'speed': round(max(0.7, min(1.4, float(speed))), 2), 'format': 'mp3',
                   'pause_ms': int(max(0, min(2000, pause_ms))), 'paragraph_pause_ms': int(max(0, min(3000, paragraph_pause_ms))),
                   'apply_lexicon': bool(apply_lexicon)}
        audio, headers = self._raw('/tts', payload, timeout)
        if not audio:
            raise AIError('Yerel ses servisi boş ses döndürdü.')
        secs = 0.0
        for k, v in headers.items():
            if k.lower() == 'x-agfo-seconds':
                try:
                    secs = float(v)
                except ValueError:
                    pass
        if not secs:
            secs = round(len(audio) * 8 / MP3_BITRATE, 2)
        return audio, secs

    # ------------------------------------------------------------------ okuma metni (sitedeki AI Manager)
    def _prepare(self, text, reading_script, script_ready):
        """(okunacak metin, sozluk uygulansin mi, okuma metni ozeti)."""
        if script_ready:
            return text, False, {'status': 'ready'}
        if not reading_script:
            return text, True, {'status': 'off'}
        if self.site is None:
            return text, True, {'status': 'skipped', 'reason': 'AI Manager bağlantısı yok'}
        try:
            d = self.site.speech_script(text)
        except AIError as e:
            return text, True, {'status': 'skipped', 'reason': str(e)[:160]}
        out = str(d.get('text') or '').strip()
        if not out:
            return text, True, {'status': 'skipped', 'reason': 'boş yanıt'}
        return out, False, {'status': 'done', 'chunks': d.get('chunks', 1), 'rewritten': d.get('rewritten', 0),
                            'kept_original': d.get('kept_original', 0), 'model': d.get('model', '')}

    # ------------------------------------------------------------------ AI Manager ile ayni arayuz
    def speech_submit(self, text: str, reading_script: bool = True, script_ready: bool = False, speed: float = 1.0,
                      pause_ms=None, paragraph_pause_ms=None, fmt: str = 'mp3', title: str = '', request_id: str = '') -> dict:
        """Yerelde is kuyrugu yok: ses hemen uretilir, sonuc 'complete' isi olarak saklanir."""
        spoken, lex, script = self._prepare(text, reading_script, script_ready)
        audio, secs = self.tts(spoken, apply_lexicon=lex, speed=speed,
                               pause_ms=350 if pause_ms is None else pause_ms,
                               paragraph_pause_ms=700 if paragraph_pause_ms is None else paragraph_pause_ms)
        jid = 'local-' + uuid.uuid4().hex[:12]
        job = {'job': jid, 'status': 'complete', 'duration_ms': int(secs * 1000), 'bytes': len(audio), 'script': script}
        self._jobs[jid] = dict(job, audio=audio)
        return job

    def speech_status(self, job: str) -> dict:
        j = self._jobs.get(job)
        if not j:
            return {'job': job, 'status': 'failed', 'error': 'İş bulunamadı.'}
        return {k: v for k, v in j.items() if k != 'audio'}

    def speech_download(self, job: str, dest: str, timeout=None) -> int:
        j = self._jobs.pop(job, None)
        if not j:
            raise AIError('Ses bulunamadı.')
        tmp = dest + '.part'
        with open(tmp, 'wb') as fh:
            fh.write(j['audio'])
        os.replace(tmp, dest)
        return len(j['audio'])

    def speech_quick(self, text: str, reading_script: bool = False, speed: float = 1.0, pause_ms: int = 300,
                     paragraph_pause_ms: int = 500, script_ready: bool = False):
        spoken, lex, _s = self._prepare(text, reading_script, script_ready)
        return self.tts(spoken, apply_lexicon=lex, speed=speed, pause_ms=pause_ms, paragraph_pause_ms=paragraph_pause_ms, timeout=300)

    def speech_script(self, text: str) -> dict:
        if self.site is None:
            raise AIError('Okuma metni sitedeki AI Manager ile hazırlanır; Ayarlar › Bağlantı bölümünden sitenizi ekleyin.')
        return self.site.speech_script(text)

    # ------------------------------------------------------------------ sozluk
    def lexicon_list(self) -> dict:
        d = self._call('/lexicon', timeout=60)
        d.setdefault('can_edit', True)
        d['local'] = True
        return d

    def lexicon_change(self, op: str, word: str, reading: str = '') -> dict:
        """Yerel sozlugu degistirir; site bagliysa ve yetki varsa ortak sozluge de yazar."""
        if op == 'save':
            d = self._call('/lexicon/entry', {'word': word, 'reading': reading})
        elif op == 'delete':
            d = self._call('/lexicon/delete', {'word': word, 'reading': ''})
        elif op == 'restore':
            d = self._call('/lexicon/delete', {'word': word, 'reading': '__restore__'})
        else:
            raise AIError('Geçersiz sözlük işlemi.')
        if self.site is not None:
            try:
                self.site.lexicon_change(op, word, reading)
                d['site'] = 'ok'
            except AIError as e:
                d['site'] = str(e)[:200]
        else:
            d['site'] = 'none'
        return d

    def lexicon_listen(self, reading: str) -> bytes:
        audio, _s = self.tts(reading, apply_lexicon=False, pause_ms=0, paragraph_pause_ms=0, timeout=120)
        return audio

    def sync_from_site(self) -> dict:
        """Sunucudaki ortak sozlukte eklenen/degistirilen/kaldirilan kelimeleri bu bilgisayara uygular."""
        if self.site is None:
            raise AIError('Eşitlemek için Ayarlar › Bağlantı bölümünden AI Manager sitenizi ekleyin.')
        remote = self.site.lexicon_list().get('entries') or []
        local = {r.get('word'): r for r in (self._call('/lexicon', timeout=60).get('entries') or [])}
        added = removed = same = 0
        errors = []
        for r in remote:
            w, src, rd = str(r.get('word') or ''), r.get('source'), str(r.get('reading') or '')
            if not w or src not in ('added', 'edited', 'removed'):
                continue
            mine = local.get(w)
            try:
                if src == 'removed':
                    if mine and mine.get('source') != 'removed':
                        self._call('/lexicon/delete', {'word': w, 'reading': ''})
                        removed += 1
                    else:
                        same += 1
                elif mine and mine.get('reading') == rd and mine.get('source') != 'removed':
                    same += 1
                else:
                    self._call('/lexicon/entry', {'word': w, 'reading': rd})
                    added += 1
            except AIError as e:
                errors.append('%s: %s' % (w, e))
        return {'added': added, 'removed': removed, 'same': same, 'errors': errors}
