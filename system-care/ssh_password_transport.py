# -*- coding: utf-8 -*-
"""Optional Paramiko password SSH transport for AGFO SuperTools.

Never forwards passwords via shell commands, arguments, files or logs.
Host keys are checked against known_hosts or manually approved fingerprints.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from ssh_profiles import SSHProfile, clean_profile, storage_path


class SSHTransportError(RuntimeError):
    pass


# Concurrent sessions may approve different hosts. Serialise trust-store read/write
# so the second connection never overwrites the first connection's known_hosts.
_HOST_KEY_LOCK = threading.RLock()


def available() -> bool:
    try:
        import paramiko  # noqa: F401
        return True
    except ImportError:
        return False


def install_optional_dependency(timeout=240) -> tuple[bool, str]:
    """Run only after explicit user consent; prefer system Python without venv."""
    if getattr(sys, "frozen", False):
        return False, "EXE içine Paramiko eklenmeli; EXE-Derle.cmd ile yeniden derleyin."
    try:
        proc = subprocess.run([sys.executable, "-m", "pip", "install", "--user",
                               "--disable-pip-version-check", "paramiko"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, check=False, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                              env={**os.environ, "PIP_NO_INPUT": "1"})
        importlib.invalidate_caches()
        if proc.returncode:
            excerpt = proc.stdout.decode("utf-8", "replace")[-1400:]
            return False, "SSH Python kütüphanesi yüklenemedi (kod %d).\n%s" % (proc.returncode, excerpt)
        if not available():
            return False, "Paramiko kuruldu ancak bu Python oturumuna yüklenemedi. Uygulamayı yeniden başlatın."
        return True, "Paramiko kuruldu. Dahili SSH bağlantısını şimdi açabilirsiniz."
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, "Paramiko kurulumu başarısız: " + str(exc)


def fingerprint(key) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def known_hosts_path() -> Path:
    return storage_path().with_name("ssh-known-hosts")


class SSHSession:
    def __init__(self, client, channel, profile_id: str):
        self.client = client
        self.channel = channel
        self.profile_id = profile_id
        self.closed = threading.Event()

    def send(self, text: str) -> None:
        if self.closed.is_set() or getattr(self.channel, "closed", False):
            raise SSHTransportError("SSH oturumu kapalı.")
        if len(text) > 8192:
            raise ValueError("SSH terminal girdisi fazla uzun.")
        self.channel.sendall(text.encode("utf-8"))

    def run_receiver(self, callback):
        """Call callback(bytes) off the Tkinter thread; caller queues UI updates."""
        try:
            while not self.closed.is_set():
                if self.channel.recv_ready():
                    part = self.channel.recv(16384)
                    if not part:
                        break
                    callback(part)
                    continue
                if getattr(self.channel, "closed", False) or self.channel.exit_status_ready():
                    break
                time.sleep(0.08)
        finally:
            self.close()

    def close(self):
        if not self.closed.is_set():
            self.closed.set()
            try:
                self.channel.close()
            except Exception:
                pass
            try:
                self.client.close()
            except Exception:
                pass


def connect_password(profile: SSHProfile, password: str, approve_host_key,
                     trust_file: Path | None = None) -> SSHSession:
    """Connect with server fingerprint verification. Called from a worker thread.

    approve_host_key(hostname, algorithm, sha256fingerprint) -> bool. This is
    called only for *unknown* hosts, never for changed/mismatched host keys.
    """
    import paramiko
    p = clean_profile(profile)
    if not isinstance(password, str) or not password:
        raise ValueError("SSH parolası girilmedi.")
    trust = Path(trust_file) if trust_file else known_hosts_path()
    client = paramiko.SSHClient()
    try:
        # Observe existing OpenSSH known hosts; no AutoAddPolicy and no disabling checks.
        client.load_system_host_keys()
        if trust.is_file():
            client.load_host_keys(str(trust))

        class PromptNewKey(paramiko.MissingHostKeyPolicy):
            def missing_host_key(self, ssh_client, hostname, key):
                signature = fingerprint(key)
                with _HOST_KEY_LOCK:
                    # Other concurrent connections may have stored a host key
                    # after this client's initial load. Recheck before saving.
                    if trust.is_file():
                        ssh_client.load_host_keys(str(trust))
                        known = ssh_client.get_host_keys().lookup(hostname)
                        if known and key.get_name() in known:
                            prior = known[key.get_name()]
                            if prior != key:
                                raise paramiko.BadHostKeyException(hostname, key, prior)
                            return
                    if not approve_host_key(hostname, key.get_name(), signature):
                        raise paramiko.SSHException("Sunucu anahtarı onaylanmadı.")
                    ssh_client.get_host_keys().add(hostname, key.get_name(), key)
                    trust.parent.mkdir(parents=True, exist_ok=True)
                    ssh_client.save_host_keys(str(trust))
                    try:
                        os.chmod(trust, 0o600)
                    except OSError:
                        pass

        client.set_missing_host_key_policy(PromptNewKey())
        client.connect(p.host, port=p.port, username=p.username, password=password,
                       timeout=10, auth_timeout=18, banner_timeout=15,
                       allow_agent=False, look_for_keys=False)
        channel = client.invoke_shell(term="vt100", width=110, height=30)
        return SSHSession(client, channel, p.id)
    except Exception:
        client.close()
        raise
