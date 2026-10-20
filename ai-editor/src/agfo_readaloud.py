# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.6 - Sesli oku.

Belge paragraf paragraf okunur: siradaki paragraflarin sesi arka planda AI Manager'dan (/editor/speech-quick)
alinirken o anki paragraf calinir ve editorde vurgulanir. Duraklat / surdur / durdur. Calma Windows'un kendi MCI
oynaticisiyla yapilir (ek paket gerekmez); test ve diger sistemler icin oynatici degistirilebilir.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import time

PIECE_MAX = 1500          # bir istek; uzun paragraf cumle sinirinda bolunur (vurgu paragrafin tamaminda kalir)
PREFETCH = 2              # calinandan sonra hazir tutulacak parca sayisi


def group_paragraphs(lines: list, rich: bool) -> list:
    """Editor satirlarindan paragraf araliklari [(ilk_satir_indeksi, son_satir_indeksi)], 0 tabanli.
    Bicimli belgede her satir bir paragraftir; duz metinde bos satirlar paragraf ayirir."""
    out, start = [], None
    for i, line in enumerate(lines):
        empty = not line.strip()
        if rich:
            if not empty:
                out.append((i, i))
            continue
        if empty:
            if start is not None:
                out.append((start, i - 1))
                start = None
        elif start is None:
            start = i
    if start is not None:
        out.append((start, len(lines) - 1))
    return out


def split_piece(text: str, limit: int = PIECE_MAX) -> list:
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    out, buf = [], ''
    for sent in re.split(r'(?<=[.!?…:;])\s+', text):
        while len(sent) > limit:                       # noktalamasiz cok uzun cumle
            cut = sent.rfind(' ', 0, limit)
            cut = cut if cut > limit // 2 else limit
            if buf:
                out.append(buf)
                buf = ''
            out.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if buf and len(buf) + len(sent) + 1 > limit:
            out.append(buf)
            buf = ''
        buf = (buf + ' ' + sent).strip()
    if buf:
        out.append(buf)
    return [p for p in out if p]


class MciPlayer:
    """Windows MCI ile MP3 calar (winmm.dll; Windows'ta her zaman var)."""
    alias = 'agforead'

    def __init__(self):
        import ctypes
        self._mci = ctypes.windll.winmm.mciSendStringW
        self._buf = ctypes.create_unicode_buffer(128)
        self._open = False

    def _send(self, cmd):
        err = self._mci(cmd, self._buf, 127, 0)
        if err:
            raise OSError('MCI hata %d: %s' % (err, cmd.split(' ')[0]))
        return self._buf.value

    def play(self, path):
        self.stop()
        self._send('open "%s" type mpegvideo alias %s' % (path, self.alias))
        self._open = True
        self._send('play %s' % self.alias)

    def pause(self):
        if self._open:
            self._send('pause %s' % self.alias)

    def resume(self):
        if self._open:
            self._send('resume %s' % self.alias)

    def stop(self):
        if self._open:
            try:
                self._send('stop %s' % self.alias)
                self._send('close %s' % self.alias)
            except OSError:
                pass
            self._open = False

    def finished(self) -> bool:
        if not self._open:
            return True
        try:
            return self._send('status %s mode' % self.alias).strip().lower() == 'stopped'
        except OSError:
            return True


class TimerPlayer:
    """Ses cikisi olmayan ortam (test, Windows disi): sesin suresi kadar 'calar'."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.path = None
        self.ends = 0.0
        self.paused_left = None
        self.played = []

    def play(self, path, seconds=0.0):
        self.path = path
        self.played.append(path)
        self.ends = self.clock() + float(seconds or 0)
        self.paused_left = None

    def pause(self):
        if self.path and self.paused_left is None:
            self.paused_left = max(0.0, self.ends - self.clock())

    def resume(self):
        if self.paused_left is not None:
            self.ends = self.clock() + self.paused_left
            self.paused_left = None

    def stop(self):
        self.path = None
        self.paused_left = None

    def finished(self) -> bool:
        return self.path is None or (self.paused_left is None and self.clock() >= self.ends)


def default_player():
    if os.name == 'nt':
        try:
            return MciPlayer()
        except Exception:
            pass
    return TimerPlayer()


class ReadAloud:
    """Sesli okuma oturumu.

    segments: [{'id': herhangi, 'texts': [okunacak parca, ...]}]  (bir paragraf = bir segment)
    fetch(text) -> (mp3_bytes, saniye)          arka plan is parciginda cagrilir
    on_segment(segment_id)                      paragraf calmaya basladiginda (vurgu)
    on_state(durum, mesaj)                      'hazırlanıyor' | 'okuyor' | 'duraklatıldı' | 'bitti' | 'hata' | 'durdu'
    tick() ana is parciginda (Tk after) duzenli cagrilir; Tk nesnelerine yalniz oradan dokunulur."""

    def __init__(self, segments, fetch, cache_dir, player=None, on_segment=None, on_state=None, prefetch=PREFETCH):
        self.items = [(seg['id'], t) for seg in segments for t in seg['texts'] if t.strip()]
        self.fetch = fetch
        self.cache_dir = cache_dir
        self.player = player or default_player()
        self.on_segment = on_segment or (lambda _id: None)
        self.on_state = on_state or (lambda _s, _m='': None)
        self.prefetch = max(1, prefetch)
        self.ready = {}            # indeks -> (dosya, saniye)
        self.error = None
        self.pos = -1              # calinan parca
        self.paused = False
        self.done = False
        self._stop = threading.Event()
        self._wake = threading.Condition()
        self._last_seg = object()
        os.makedirs(cache_dir, exist_ok=True)
        self._worker = threading.Thread(target=self._fetch_loop, daemon=True)

    # -- arka plan: siradaki parcalari onceden indir
    def _fetch_loop(self):
        for i, (_sid, text) in enumerate(self.items):
            with self._wake:
                while not self._stop.is_set() and i > self.pos + self.prefetch:
                    self._wake.wait(0.2)
            if self._stop.is_set():
                return
            key = hashlib.sha1(text.encode('utf-8')).hexdigest()[:20]
            path = os.path.join(self.cache_dir, key + '.mp3')
            try:
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    secs = float(open(path + '.sec').read() or 0) if os.path.exists(path + '.sec') else 0.0
                else:
                    audio, secs = self.fetch(text)
                    if self._stop.is_set():
                        return
                    with open(path + '.tmp', 'wb') as fh:
                        fh.write(audio)
                    os.replace(path + '.tmp', path)
                    with open(path + '.sec', 'w') as fh:
                        fh.write(str(secs or 0))
            except Exception as e:  # ag/sunucu hatasi: oturum hata ile biter
                self.error = str(e)
                return
            self.ready[i] = (path, secs)

    def start(self):
        if not self.items:
            self.done = True
            self.on_state('bitti', 'Okunacak metin yok.')
            return
        self.on_state('hazırlanıyor', 'Ses hazırlanıyor…')
        self._worker.start()

    def tick(self):
        if self.done or self.paused:
            return
        if not self.player.finished():
            return
        nxt = self.pos + 1
        if nxt >= len(self.items):
            self._finish('bitti', 'Okuma bitti.')
            return
        if nxt not in self.ready:
            if self.error:
                self._finish('hata', self.error)
            elif self.pos >= 0:
                self.on_state('hazırlanıyor', 'Sonraki paragraf hazırlanıyor…')
            return
        path, secs = self.ready[nxt]
        self.pos = nxt
        with self._wake:
            self._wake.notify_all()
        sid = self.items[nxt][0]
        try:
            if isinstance(self.player, TimerPlayer):
                self.player.play(path, secs)
            else:
                self.player.play(path)
        except OSError as e:
            self._finish('hata', 'Ses çalınamadı: %s' % e)
            return
        if sid != self._last_seg:
            self._last_seg = sid
            self.on_segment(sid)
        self.on_state('okuyor', 'Okunuyor: %d / %d' % (nxt + 1, len(self.items)))

    def toggle_pause(self):
        if self.done:
            return
        if self.paused:
            self.paused = False
            self.player.resume()
            self.on_state('okuyor', 'Okunuyor: %d / %d' % (self.pos + 1, len(self.items)))
        else:
            self.paused = True
            self.player.pause()
            self.on_state('duraklatıldı', 'Duraklatıldı')

    def stop(self):
        self._finish('durdu', 'Okuma durduruldu.')

    def _finish(self, state, msg):
        if self.done:
            return
        self.done = True
        self._stop.set()
        with self._wake:
            self._wake.notify_all()
        try:
            self.player.stop()
        except Exception:
            pass
        self.on_state(state, msg)
