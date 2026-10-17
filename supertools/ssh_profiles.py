# -*- coding: utf-8 -*-
"""AGFO SSH bookmarks. No password storage, no unattended SSH authorization.

The native OpenSSH client manages private keys and known_hosts. Password-based
login is always prompted by the native interactive terminal, if requested.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import re
import shutil
import socket
import subprocess
import uuid
from typing import Optional

from supertools_core import normalize_host, DiagnosticError

MAX_PROFILES = 100
USER = re.compile(r"[a-zA-Z_][a-zA-Z0-9_.-]{0,63}\$?\Z")
LABEL = re.compile(r"[^\x00-\x1f\x7f]{1,80}\Z")


@dataclass(frozen=True)
class SSHProfile:
    id: str
    name: str
    host: str
    port: int
    username: str
    key_file: str = ""
    note: str = ""


def storage_path() -> Path:
    """Per-user, outside installation and update tree."""
    home = os.getenv("LOCALAPPDATA", "").strip() or str(Path.home() / ".agfo-tools")
    return Path(home) / "AGFO-MultiSubnet-Scanner" / "ssh-profiles.json"


def clean_profile(value: SSHProfile) -> SSHProfile:
    if not isinstance(value, SSHProfile):
        raise ValueError("SSH profili geçersiz.")
    if not value.id or not re.fullmatch(r"[a-f0-9]{32}", value.id):
        raise ValueError("Geçersiz profil kimliği.")
    name = value.name.strip()
    note = value.note.strip()
    if not LABEL.fullmatch(name):
        raise ValueError("Profil adı 1-80 karakter olmalı.")
    if len(note) > 200 or any(ord(c) < 32 and c not in ("\n", "\t") for c in note):
        raise ValueError("Not çok uzun veya geçersiz.")
    host = normalize_host(value.host)
    if type(value.port) is not int or not 1 <= value.port <= 65535:
        raise ValueError("SSH portu 1 ile 65535 arasında olmalı.")
    username = value.username.strip()
    if not USER.fullmatch(username):
        raise ValueError("SSH kullanıcı adı hatalı (harf, rakam, nokta, tire, alt çizgi).")
    key_file = str(value.key_file).strip()
    if len(key_file) > 1024 or any(c in key_file for c in "\r\n\x00"):
        raise ValueError("Özel anahtar yolu geçersiz.")
    return SSHProfile(value.id, name, host, value.port, username, key_file, note)


def new_profile(name: str, host: str, port: int, username: str, key_file: str = "", note: str = "") -> SSHProfile:
    return clean_profile(SSHProfile(uuid.uuid4().hex, name, host, int(port), username, key_file, note))


def load_profiles(path: Optional[Path] = None) -> list[SSHProfile]:
    file = Path(path) if path else storage_path()
    if not file.exists():
        return []
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("format") != "agfo-ssh-profiles-v1":
            raise ValueError("SSH profil dosyası biçimi tanınmadı.")
        data = raw.get("profiles", [])
        if not isinstance(data, list) or len(data) > MAX_PROFILES:
            raise ValueError("SSH profil sayısı geçersiz.")
        out = []
        ids = set()
        for x in data:
            if not isinstance(x, dict) or set(x) != set(asdict(SSHProfile("", "", "", 22, ""))):
                raise ValueError("SSH profil alanları geçersiz.")
            item = clean_profile(SSHProfile(**x))
            if item.id in ids:
                raise ValueError("Tekrarlanan profil kimliği.")
            ids.add(item.id)
            out.append(item)
        return out
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ValueError("SSH profil dosyası okunamadı: " + str(exc)) from exc


def save_profiles(profiles: list[SSHProfile], path: Optional[Path] = None) -> Path:
    file = Path(path) if path else storage_path()
    if len(profiles) > MAX_PROFILES:
        raise ValueError("En fazla 100 SSH profili kaydedilebilir.")
    items = [clean_profile(x) for x in profiles]
    if len({x.id for x in items}) != len(items):
        raise ValueError("Tekrarlanan profil ID'si.")
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_name(file.name + "." + uuid.uuid4().hex + ".tmp")
    payload = {"format": "agfo-ssh-profiles-v1", "updated": datetime.now(timezone.utc).isoformat(),
               "profiles": [asdict(x) for x in items]}
    # No passwords/tokens are persisted; profile file is scoped to local user.
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, file)
    finally:
        if temp.exists():
            temp.unlink()
    return file


def ssh_executable() -> str:
    path = shutil.which("ssh.exe") or shutil.which("ssh")
    if not path:
        raise FileNotFoundError("Windows OpenSSH istemcisi (ssh.exe) bulunamadı. Ayarlar > İsteğe bağlı özellikler > OpenSSH İstemcisi")
    return path


def build_ssh_argv(profile: SSHProfile, command: Optional[str] = None, batch: bool = False,
                   executable: Optional[str] = None) -> list[str]:
    p = clean_profile(profile)
    exe = executable or ssh_executable()
    args = [exe, "-p", str(p.port), "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=20"]
    if p.key_file:
        key = Path(p.key_file).expanduser()
        if not key.is_file():
            raise ValueError("SSH özel anahtar dosyası bulunamadı: " + str(key))
        args.extend(["-i", str(key), "-o", "IdentitiesOnly=yes"])
    if batch:
        # Never hang headless waiting for a password/host-key confirmation.
        args.extend(["-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"])
    args.append("%s@%s" % (p.username, p.host))
    if command is not None:
        if not command.strip() or len(command) > 2048 or "\r" in command or "\n" in command:
            raise ValueError("Uzak SSH komutu boş, çok uzun veya birden fazla satır içeriyor.")
        args.append(command)
    return args


def test_ssh_port(profile: SSHProfile, timeout=3.0) -> str:
    p = clean_profile(profile)
    try:
        with socket.create_connection((p.host, p.port), timeout=timeout):
            return "%s:%d bağlantısı açık (SSH oturumu henüz doğrulanmadı)." % (p.host, p.port)
    except OSError as exc:
        raise ConnectionError("%s:%d erişilemedi: %s" % (p.host, p.port, exc)) from exc


def execute_remote(profile: SSHProfile, command: str, timeout: float = 20.0) -> tuple[int, str]:
    args = build_ssh_argv(profile, command, batch=True)
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("SSH komutu %s saniyede tamamlanmadı." % timeout) from exc
    raw = (result.stdout or b"")[:192 * 1024]
    text = raw.decode("utf-8", errors="replace")
    return result.returncode, text


def open_interactive_terminal(profile: SSHProfile) -> str:
    """Deliberately opens *one* interactive terminal for full SSH TTY and password prompts."""
    args = build_ssh_argv(profile)
    terminal = shutil.which("wt.exe") or shutil.which("wt")
    if terminal:
        command = [terminal, "new-tab", "--title", "AGFO SSH - " + profile.name, *args]
        subprocess.Popen(command, close_fds=True)
        return "Windows Terminal içinde SSH oturumu açıldı."
    if os.name == "nt":
        # Native ssh.exe + new console, without passing through cmd.exe / PowerShell.
        subprocess.Popen(args, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0), close_fds=True)
        return "OpenSSH için etkileşimli terminal penceresi açıldı."
    raise OSError("Etkileşimli SSH terminali Windows üzerinde kullanılabilir.")
