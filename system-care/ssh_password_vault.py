# -*- coding: utf-8 -*-
"""Per-Windows-user, time-limited SSH password cache using Windows DPAPI.

This module stores only DPAPI-protected blobs, not passwords or master keys.
No fallback to plaintext is provided on non-Windows platforms.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import time
import uuid
from typing import Optional

from ssh_profiles import SSHProfile, clean_profile, storage_path

HOURS = (1, 3, 4, 8, 24)
FORMAT = "agfo-ssh-dpapi-v1"
ENTROPY = b"AGFO-SuperTools/SSH-Password-Cache/v1"
MAX_ENTRIES = 100
MAX_FILE_BYTES = 131072


class VaultError(RuntimeError):
    pass


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob_from_bytes(data: bytes):
    buf = ctypes.create_string_buffer(data, max(len(data), 1))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))), buf


def _dpapi(data: bytes, protect: bool) -> bytes:
    if os.name != "nt":
        raise VaultError("DPAPI parola kasası yalnızca Windows'ta kullanılabilir.")
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    name = "CryptProtectData" if protect else "CryptUnprotectData"
    fn = getattr(crypt, name)
    fn.argtypes = [ctypes.POINTER(_BLOB), ctypes.c_void_p, ctypes.POINTER(_BLOB),
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_BLOB)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    incoming, incoming_buf = _blob_from_bytes(data)
    entropy, entropy_buf = _blob_from_bytes(ENTROPY)
    result = _BLOB()
    try:
        # CRYPTPROTECT_UI_FORBIDDEN: no external credential dialogs or persistence.
        if protect:
            ok = fn(ctypes.byref(incoming), ctypes.c_wchar_p("AGFO SSH (temporary)"),
                    ctypes.byref(entropy), None, None, 0x1, ctypes.byref(result))
        else:
            ok = fn(ctypes.byref(incoming), None, ctypes.byref(entropy),
                    None, None, 0x1, ctypes.byref(result))
        if not ok:
            raise VaultError("Windows DPAPI işlemi başarısız (Windows hata %s)." % ctypes.get_last_error())
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        if result.pbData:
            kernel.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))
        # Keep input buffers referenced until the Windows function returns.
        del incoming_buf, entropy_buf


def protect(data: bytes) -> bytes:
    return _dpapi(data, True)


def unprotect(data: bytes) -> bytes:
    return _dpapi(data, False)


def vault_path() -> Path:
    return storage_path().with_name("ssh-password-cache.dpapi.json")


def _binding(profile: SSHProfile) -> dict:
    p = clean_profile(profile)
    return {"id": p.id, "host": p.host.casefold(), "port": p.port, "user": p.username}


class SSHPasswordVault:
    def __init__(self, path: Optional[Path] = None, encrypt=protect, decrypt=unprotect, clock=time.time):
        self.path = Path(path) if path else vault_path()
        self.encrypt = encrypt
        self.decrypt = decrypt
        self.clock = clock

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            if self.path.stat().st_size > MAX_FILE_BYTES:
                raise VaultError("Şifreli kasa dosyası boyutu geçersiz.")
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("format") != FORMAT:
                raise VaultError("Şifreli kasa biçimi tanınmadı.")
            entries = raw.get("entries")
            if not isinstance(entries, dict) or len(entries) > MAX_ENTRIES:
                raise VaultError("Şifreli kasa içeriği geçersiz.")
            for key, record in entries.items():
                if not (isinstance(key, str) and len(key) == 32 and
                        isinstance(record, dict) and set(record) == {"expires", "blob"} and
                        type(record["expires"]) is int and isinstance(record["blob"], str) and
                        len(record["blob"]) <= 8192):
                    raise VaultError("Şifreli kasa kaydı geçersiz.")
            return entries
        except (OSError, ValueError, UnicodeError) as exc:
            raise VaultError("Şifreli kasa okunamadı: " + str(exc)) from exc

    def _write(self, entries: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Only encrypted payload and timestamps are serialized.
        serialized = json.dumps({"format": FORMAT, "entries": entries}, ensure_ascii=True,
                                separators=(",", ":"))
        temp = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("x", encoding="utf-8") as fd:
                fd.write(serialized)
            try:
                os.chmod(temp, 0o600)
            except OSError:
                pass
            os.replace(temp, self.path)
        finally:
            if temp.exists():
                temp.unlink()

    def prune(self) -> int:
        entries = self._read()
        now = int(self.clock())
        cleaned = {key: val for key, val in entries.items() if val["expires"] > now}
        if cleaned != entries:
            self._write(cleaned)
        return len(entries) - len(cleaned)

    def get(self, profile: SSHProfile) -> Optional[str]:
        p = clean_profile(profile)
        entries = self._read()
        item = entries.get(p.id)
        if not item:
            return None
        if item["expires"] <= int(self.clock()):
            self.forget(p.id)
            return None
        try:
            payload = json.loads(self.decrypt(base64.b64decode(item["blob"], validate=True)).decode("utf-8"))
            if (payload.get("binding") != _binding(p) or
                    payload.get("expires") != item["expires"] or
                    not isinstance(payload.get("password"), str)):
                self.forget(p.id)
                return None
            return payload["password"]
        except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
            raise VaultError("Kaydedilmiş SSH parolası çözülemedi; Windows hesabı değişmiş olabilir.") from exc

    def remember(self, profile: SSHProfile, password: str, hours: int) -> int:
        p = clean_profile(profile)
        if hours not in HOURS or type(hours) is not int:
            raise ValueError("Hatırlama süresi 1, 3, 4, 8 veya 24 saat olmalı.")
        if not isinstance(password, str) or not password or len(password) > 4096:
            raise ValueError("SSH parolası boş veya geçersiz.")
        expires = int(self.clock()) + hours * 3600
        payload = {"binding": _binding(p), "expires": expires, "password": password}
        token = base64.b64encode(self.encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))).decode("ascii")
        entries = self._read()
        entries[p.id] = {"expires": expires, "blob": token}
        self._write(entries)
        return expires

    def forget(self, profile_id: str) -> bool:
        entries = self._read()
        if profile_id in entries:
            del entries[profile_id]
            self._write(entries)
            return True
        return False

    def forget_all(self) -> None:
        # Deleting an existing encrypted blob is enough; do not overwrite/erase unrelated data.
        self._write({})

    def expires_at(self, profile: SSHProfile) -> Optional[int]:
        p = clean_profile(profile)
        item = self._read().get(p.id)
        if not item:
            return None
        if item["expires"] <= int(self.clock()):
            self.forget(p.id)
            return None
        return item["expires"]
