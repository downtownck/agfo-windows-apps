# -*- coding: utf-8 -*-
"""AGFO AI Editor 2.0 - yazim denetimi.

Windows 8+ ile gelen Yazim Denetimi API'si (ISpellCheckerFactory, COM) ctypes ile kullanilir; ek indirme ya da sozluk
dosyasi gerekmez. Turkce icin Windows'ta Turkce dil paketi (yazim denetimi bileseni) yuklu olmalidir.

Arayuz (uygulama ve testler icin):
    sp = WinSpeller('tr-TR')      # sp.available, sp.error
    sp.check(metin) -> [(baslangic, uzunluk, eylem, oneri)]   # Python karakter konumlari
    sp.suggest(kelime) -> [oneri, ...]
    sp.add(kelime) / sp.ignore(kelime)
eylem: 'suggest' (oneri al), 'replace' (oneri ile degistir), 'delete' (sil, or. yinelenen kelime)
"""
from __future__ import annotations

import ctypes
import re
import sys

CLSID_SpellCheckerFactory = '{7AB36653-1796-484B-BDFA-E74F1DB7C1DC}'
IID_ISpellCheckerFactory = '{8E018A9D-2415-4677-BF08-794EA61F94BB}'
ACTIONS = {0: None, 1: 'suggest', 2: 'replace', 3: 'delete'}
LANG_HELP = ('Windows\'ta bu dil için yazım denetimi yüklü değil. Ayarlar › Zaman ve dil › Dil ve bölge › Türkçe › '
             'Dil seçenekleri bölümünden "Yazım denetimi" bileşenini (dil paketi) yükleyin.')


class GUID(ctypes.Structure):
    _fields_ = [('Data1', ctypes.c_ulong), ('Data2', ctypes.c_ushort), ('Data3', ctypes.c_ushort), ('Data4', ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, s):
        g = cls()
        if sys.platform == 'win32':
            ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
        return g


def _method(ptr, index, *argtypes):
    """COM vtable yontemi: (this, *args) -> HRESULT (int)."""
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return proto(vtbl[index])


def _release(ptr):
    if ptr:
        try:
            _method(ptr, 2)(ptr)
        except OSError:
            pass


def utf16_map(text):
    """UTF-16 konumundan Python konumuna cevirici (BMP disi karakter yoksa kimlik)."""
    if all(ord(c) < 0x10000 for c in text):
        return lambda k: k
    table = []
    for i, c in enumerate(text):
        table.append(i)
        if ord(c) >= 0x10000:
            table.append(i)
    table.append(len(text))
    return lambda k: table[min(k, len(table) - 1)]


class WinSpeller:
    def __init__(self, lang='tr-TR'):
        self.lang = lang
        self.available = False
        self.error = ''
        self._checker = None
        self._ignored = set()
        if sys.platform != 'win32':
            self.error = 'Yazım denetimi yalnız Windows\'ta çalışır.'
            return
        try:
            ole = ctypes.oledll.ole32
            try:
                ole.CoInitializeEx(None, 2)          # COINIT_APARTMENTTHREADED; zaten baslatildiysa sorun degil
            except OSError:
                pass
            factory = ctypes.c_void_p()
            clsid, iid = GUID.parse(CLSID_SpellCheckerFactory), GUID.parse(IID_ISpellCheckerFactory)
            ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(factory))
        except OSError as e:
            self.error = 'Windows yazım denetleyicisi açılamadı (%s).' % e
            return
        try:
            ok = ctypes.c_int(0)
            hr = _method(factory, 4, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int))(factory, lang, ctypes.byref(ok))
            if hr < 0 or not ok.value:
                self.error = LANG_HELP
                return
            chk = ctypes.c_void_p()
            hr = _method(factory, 5, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p))(factory, lang, ctypes.byref(chk))
            if hr < 0 or not chk:
                self.error = 'Yazım denetleyicisi oluşturulamadı (0x%08X).' % (hr & 0xFFFFFFFF)
                return
            self._checker = chk
            self.available = True
        finally:
            _release(factory)

    def close(self):
        _release(self._checker)
        self._checker = None
        self.available = False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def check(self, text):
        if not self.available or not text.strip():
            return []
        enum = ctypes.c_void_p()
        hr = _method(self._checker, 4, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p))(self._checker, text, ctypes.byref(enum))
        if hr < 0 or not enum:
            return []
        conv = utf16_map(text)
        out = []
        try:
            nxt = _method(enum, 3, ctypes.POINTER(ctypes.c_void_p))
            for _ in range(5000):
                err = ctypes.c_void_p()
                hr = nxt(enum, ctypes.byref(err))
                if hr != 0 or not err:
                    break
                try:
                    st, ln, act = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_int()
                    _method(err, 3, ctypes.POINTER(ctypes.c_ulong))(err, ctypes.byref(st))
                    _method(err, 4, ctypes.POINTER(ctypes.c_ulong))(err, ctypes.byref(ln))
                    _method(err, 5, ctypes.POINTER(ctypes.c_int))(err, ctypes.byref(act))
                    rep = ''
                    if act.value == 2:
                        p = ctypes.c_void_p()
                        if _method(err, 6, ctypes.POINTER(ctypes.c_void_p))(err, ctypes.byref(p)) >= 0 and p.value:
                            rep = ctypes.wstring_at(p.value)
                            ctypes.windll.ole32.CoTaskMemFree(p)
                    a, b = conv(st.value), conv(st.value + ln.value)
                    word = text[a:b]
                    if word.lower() not in self._ignored and ACTIONS.get(act.value):
                        out.append((a, b - a, ACTIONS[act.value], rep))
                finally:
                    _release(err)
        finally:
            _release(enum)
        return out

    def suggest(self, word, limit=8):
        if not self.available or not word:
            return []
        enum = ctypes.c_void_p()
        hr = _method(self._checker, 5, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p))(self._checker, word, ctypes.byref(enum))
        if hr < 0 or not enum:
            return []
        out = []
        try:
            nxt = _method(enum, 3, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_ulong))
            while len(out) < limit:
                p, got = ctypes.c_void_p(), ctypes.c_ulong()
                hr = nxt(enum, 1, ctypes.byref(p), ctypes.byref(got))
                if hr != 0 or not got.value or not p.value:
                    break
                out.append(ctypes.wstring_at(p.value))
                ctypes.windll.ole32.CoTaskMemFree(p)
        finally:
            _release(enum)
        return out

    def add(self, word):
        """Kullanici sozlugune ekler (Windows'ta tum uygulamalar icin kalici)."""
        if self.available and word:
            _method(self._checker, 6, ctypes.c_wchar_p)(self._checker, word)

    def ignore(self, word):
        """Bu oturum boyunca yoksayar."""
        if word:
            self._ignored.add(word.lower())
            if self.available:
                _method(self._checker, 7, ctypes.c_wchar_p)(self._checker, word)


WORD_RX = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)


class ListSpeller:
    """Test ve yedek: bilinen kelime listesine gore denetler (Windows disi ortamlar icin)."""

    def __init__(self, words, suggestions=None):
        self.words = {w.lower() for w in words}
        self.sugg = suggestions or {}
        self.available = True
        self.error = ''
        self._ignored = set()

    def check(self, text):
        out = []
        for m in WORD_RX.finditer(text):
            w = m.group(0)
            if w.lower() not in self.words and w.lower() not in self._ignored:
                out.append((m.start(), len(w), 'suggest', ''))
        return out

    def suggest(self, word, limit=8):
        return list(self.sugg.get(word.lower(), []))[:limit]

    def add(self, word):
        self.words.add(word.lower())

    def ignore(self, word):
        self._ignored.add(word.lower())

    def close(self):
        pass


def create(lang='tr-TR'):
    return WinSpeller(lang)
