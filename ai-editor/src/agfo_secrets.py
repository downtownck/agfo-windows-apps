# -*- coding: utf-8 -*-
"""Gizli bilgileri (API anahtari, uygulama parolasi) Windows DPAPI ile kullanici hesabina bagli saklar.

Sifreli deger yalnizca ayni Windows kullanicisi tarafindan cozulebilir; ayarlar dosyasi baska bir
bilgisayara/kullaniciya kopyalanirsa anahtarlar kullanilamaz. Windows disinda (yalnizca testler)
acik metin saklanmaz; 'plain:' oneki yalnizca test ortami icindir ve uygulama bunu uyariyla gosterir.
"""
from __future__ import annotations

import base64
import sys

PREFIX = 'dpapi:'
TEST_PREFIX = 'plain:'
ENTROPY = b'AGFO-AI-Editor/1'


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

    def blob(b):
        buf = ctypes.create_string_buffer(b, len(b))
        return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    src, _k1 = blob(data)
    ent, _k2 = blob(ENTROPY)
    out = BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if protect:
        ok = fn(ctypes.byref(src), 'AGFO AI Editor', ctypes.byref(ent), None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))
    else:
        ok = fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))
    if not ok:
        raise OSError('DPAPI işlemi başarısız (kod %d).' % ctypes.GetLastError())
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def protect(secret: str) -> str:
    if not secret:
        return ''
    raw = secret.encode('utf-8')
    if sys.platform == 'win32':
        return PREFIX + base64.b64encode(_dpapi(raw, True)).decode('ascii')
    return TEST_PREFIX + base64.b64encode(raw).decode('ascii')


def unprotect(stored: str) -> str:
    if not stored:
        return ''
    try:
        if stored.startswith(PREFIX):
            if sys.platform != 'win32':
                return ''
            return _dpapi(base64.b64decode(stored[len(PREFIX):]), False).decode('utf-8')
        if stored.startswith(TEST_PREFIX):
            return base64.b64decode(stored[len(TEST_PREFIX):]).decode('utf-8')
    except (OSError, ValueError, UnicodeDecodeError):
        return ''
    return ''


def mask(secret: str) -> str:
    if not secret:
        return ''
    return ('•' * 8) + secret[-4:] if len(secret) > 8 else '•' * len(secret)
