# -*- coding: utf-8 -*-
"""AGFO Multi-Subnet Scanner local, consent-based, rollback-capable updater.

Only user-selected update ZIPs are accepted. The included SHA-256 checks are
integrity checks, not publisher signatures: never use untrusted update files.
No downloaded content, shell hooks or network operation is executed here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

APP_ID = "agfo-multisubnet-scanner"
FORMAT = "agfo-scanner-update-v1"
BACKUP_FORMAT = "agfo-scanner-backup-v1"
INSTALL_ROOT = Path(r"C:\agfo-backutil\MultiSubnetScanner")
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_PAYLOAD_BYTES = 75 * 1024 * 1024
MAX_FILES = 60
ALLOWED_FILE = re.compile(r"(?:[A-Za-z][A-Za-z0-9_-]*\.pyw?|assets/[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:png|ico|gif))\Z")
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){2}\Z")
REQUIRED = {"app.pyw", "scanner_core.py", "agfo_updater.py", "agfo_github_update.py", "supertools_core.py", "supertools_ui.py", "ssh_profiles.py", "modern_shell.py", "ssh_password_vault.py", "ssh_password_transport.py", "ssh_workspace.py"}


class UpdateError(Exception):
    pass


def data_folder() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".agfo-tools")) / "AGFO-MultiSubnet-Scanner"


def version_tuple(s: str) -> tuple[int, ...]:
    if not isinstance(s, str) or not VERSION.fullmatch(s):
        raise UpdateError("Gecersiz surum numarasi: " + str(s))
    return tuple(int(x) for x in s.split("."))


def current_version(install_dir: Path) -> str:
    file = install_dir / "scanner_core.py"
    try:
        value = file.read_text(encoding="utf-8")
    except OSError as exc:
        raise UpdateError("Kurulu scanner_core.py okunamadi.") from exc
    m = re.search(r'^APP_VERSION\s*=\s*[\'"]([0-9]+\.[0-9]+\.[0-9]+)[\'"]\s*$', value, re.M)
    if not m:
        raise UpdateError("Mevcut surum tespit edilemedi.")
    return m.group(1)


def valid_name(name: str) -> bool:
    """Strict relative paths only; no folders, drive letters, or symlinks."""
    if not isinstance(name, str) or not ALLOWED_FILE.fullmatch(name):
        return False
    p = PurePosixPath(name)
    return not p.is_absolute() and not any(part in (".", "..") for part in p.parts)


def _safe_target(root: Path, name: str) -> Path:
    if not valid_name(name):
        raise UpdateError("Izin verilmeyen dosya yolu: " + str(name))
    root = Path(root)
    if root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction()):
        raise UpdateError("Kurulum klasoru bir baglanti (junction/symlink) olamaz.")
    target = root.joinpath(*PurePosixPath(name).parts)
    for item in (root, *list(target.parents)[:-1], target):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise UpdateError("Baglanti uzerinden dosya degistirme reddedildi: " + name)
    if not target.resolve(strict=False).is_relative_to(root.resolve(strict=False)):
        raise UpdateError("Kurulum klasoru disina erisim reddedildi: " + name)
    return target


def _manifest_from_zip(z: zipfile.ZipFile) -> dict:
    raw = z.read("update-manifest.json")
    if len(raw) > 65536:
        raise UpdateError("Manifest fazla buyuk.")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise UpdateError("Guncelleme manifesti gecersiz.") from exc
    if not isinstance(result, dict) or result.get("format") != FORMAT or result.get("app_id") != APP_ID:
        raise UpdateError("Bu ZIP AGFO Multi-Subnet Scanner guncellemesi degil.")
    version_tuple(result.get("version", ""))
    if not isinstance(result.get("notes", ""), str) or len(result.get("notes", "")) > 2500:
        raise UpdateError("Guncelleme aciklamasi gecersiz.")
    files = result.get("files")
    if not isinstance(files, dict) or not (REQUIRED <= set(files)) or len(files) > MAX_FILES:
        raise UpdateError("Manifest dosya listesi eksik veya fazla buyuk.")
    for name, entry in files.items():
        if not valid_name(name) or not isinstance(entry, dict):
            raise UpdateError("Manifest icindeki dosya adi gecersiz.")
        if set(entry) != {"sha256", "size"}:
            raise UpdateError("Manifest dosya bilgileri gecersiz.")
        if not isinstance(entry["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", entry["sha256"]):
            raise UpdateError("Manifest SHA-256 gecersiz.")
        if type(entry["size"]) is not int or not (0 <= entry["size"] <= MAX_PAYLOAD_BYTES):
            raise UpdateError("Manifest dosya boyutu gecersiz.")
    if sum(f["size"] for f in files.values()) > MAX_PAYLOAD_BYTES:
        raise UpdateError("Guncelleme cok buyuk.")
    return result


def inspect_package(zip_path: Path, installed_version: str | None = None) -> dict:
    """Verify ZIP entries, checksums and target version, without extracting anything."""
    zip_path = Path(zip_path)
    if not zip_path.is_file() or zip_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise UpdateError("Guncelleme ZIP'i bulunamadi veya siniri asti.")
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            infos = z.infolist()
            names = [e.filename for e in infos]
            if not names or len(names) > MAX_FILES + 1 or len(names) != len(set(n.lower() for n in names)):
                raise UpdateError("ZIP icinde yinelenen veya fazla dosya var.")
            if "update-manifest.json" not in names:
                raise UpdateError("update-manifest.json eksik. Tam kurulum ZIP'i degil, AGFO update ZIP'i secin.")
            for item in infos:
                if item.is_dir() or item.flag_bits & 0x1 or ((item.external_attr >> 16) & 0o170000) == stat.S_IFLNK:
                    raise UpdateError("ZIP icinde dizin, sembolik baglanti veya sifreli dosya yasak.")
                if item.filename != "update-manifest.json" and not item.filename.startswith("payload/"):
                    raise UpdateError("ZIP icinde beklenmeyen dosya: " + item.filename)
                if item.file_size > MAX_PAYLOAD_BYTES:
                    raise UpdateError("ZIP icinde asiri buyuk dosya var.")
            if sum(i.file_size for i in infos) > MAX_PAYLOAD_BYTES + 65536:
                raise UpdateError("ZIP toplam boyut siniri asildi.")
            manifest = _manifest_from_zip(z)
            expected = {"payload/" + path for path in manifest["files"]} | {"update-manifest.json"}
            if set(names) != expected:
                raise UpdateError("ZIP dosyalari manifest ile uyusmuyor.")
            if installed_version and version_tuple(manifest["version"]) <= version_tuple(installed_version):
                raise UpdateError("Daha yeni surum gerekli. Kurulu: %s, paket: %s" %
                                  (installed_version, manifest["version"]))
            for path, record in manifest["files"].items():
                info = z.getinfo("payload/" + path)
                if info.file_size != record["size"]:
                    raise UpdateError("Boyut dogrulamasi basarisiz: " + path)
                digest = hashlib.sha256()
                with z.open(info) as stream:
                    for chunk in iter(lambda: stream.read(262144), b""):
                        digest.update(chunk)
                if digest.hexdigest() != record["sha256"]:
                    raise UpdateError("SHA-256 dogrulamasi basarisiz: " + path)
            return manifest
    except (OSError, zipfile.BadZipFile, RuntimeError, KeyError, ValueError) as exc:
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError("ZIP dogrulanamadi: " + str(exc)) from exc


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = path.with_name(path.name + ".new")
    t.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(t, path)


def _digest(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(262144), b""):
            digest.update(block)
    return digest.hexdigest()


def _snapshot(install_dir: Path, paths: list[str], home: Path, version: str) -> Path:
    backups = home / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    folder = backups / ("v%s_%s_%s" % (version, datetime.now().strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:8]))
    folder.mkdir()
    files = {}
    try:
        for name in paths:
            old = _safe_target(install_dir, name)
            if old.is_file():
                target = folder / "files" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, target)
                files[name] = {"exists": True, "sha256": _digest(target)}
            elif old.exists():
                raise UpdateError("Beklenmeyen kurulum dosyasi turu: " + name)
            else:
                files[name] = {"exists": False}
        _write_json(folder / "backup.json", {"format": BACKUP_FORMAT, "app_id": APP_ID,
                                             "version": version, "created": datetime.now(timezone.utc).isoformat(),
                                             "files": files})
        return folder
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def list_backups(home: Path | None = None) -> list[dict]:
    backups = (home or data_folder()) / "backups"
    result = []
    if not backups.is_dir():
        return result
    for folder in backups.iterdir():
        if not folder.is_dir() or folder.is_symlink():
            continue
        try:
            data = json.loads((folder / "backup.json").read_text(encoding="utf-8"))
            if data.get("format") == BACKUP_FORMAT and data.get("app_id") == APP_ID:
                result.append({"folder": str(folder), "version": data["version"],
                               "created": data["created"]})
        except (ValueError, OSError, KeyError):
            continue
    return sorted(result, key=lambda item: item["created"], reverse=True)


def _validated_backup(folder: Path, home: Path) -> tuple[dict, dict[str, bytes]]:
    backups = (home / "backups").resolve()
    folder = folder.resolve()
    if folder.parent != backups or folder.is_symlink():
        raise UpdateError("Yedek kaynagi taninan yedekler klasorunde degil.")
    try:
        data = json.loads((folder / "backup.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UpdateError("Yedek manifesti okunamadi.") from exc
    if data.get("format") != BACKUP_FORMAT or data.get("app_id") != APP_ID:
        raise UpdateError("Yedek manifesti uygulamaya ait degil.")
    version_tuple(data.get("version", ""))
    files = data.get("files")
    if not isinstance(files, dict) or not files or len(files) > MAX_FILES:
        raise UpdateError("Yedek dosya listesi gecersiz.")
    originals = {}
    for name, record in files.items():
        if not valid_name(name) or not isinstance(record, dict) or type(record.get("exists")) is not bool:
            raise UpdateError("Yedek icinde gecersiz dosya.")
        if record["exists"]:
            f = folder / "files" / name
            if f.is_symlink() or not f.is_file():
                raise UpdateError("Yedek dosyasi eksik veya baglanti.")
            raw = f.read_bytes()
            if hashlib.sha256(raw).hexdigest() != record.get("sha256"):
                raise UpdateError("Yedek dosya SHA-256 hatasi: " + name)
            originals[name] = raw
    return data, originals


def _replace_files(install_dir: Path, changes: dict[str, bytes | None]) -> None:
    for name, raw in changes.items():
        dest = _safe_target(install_dir, name)
        if raw is None:
            if dest.exists():
                dest.unlink()
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        temporary = dest.with_name(dest.name + ".agfo-new-" + uuid.uuid4().hex[:8])
        try:
            temporary.write_bytes(raw)
            os.replace(temporary, dest)
        finally:
            if temporary.exists():
                temporary.unlink()


def perform_update(zip_path: Path, install_dir: Path = INSTALL_ROOT, home: Path | None = None) -> dict:
    """Transactional local update. On error, attempt to restore every touched file."""
    install_dir = Path(install_dir)
    home = home or data_folder()
    old_version = current_version(install_dir)
    manifest = inspect_package(zip_path, old_version)
    incoming: dict[str, bytes] = {}
    with zipfile.ZipFile(zip_path) as z:
        for name in manifest["files"]:
            incoming[name] = z.read("payload/" + name)
    for name in incoming:
        _safe_target(install_dir, name)
    backup = _snapshot(install_dir, list(incoming), home, old_version)
    try:
        _replace_files(install_dir, incoming)
        if current_version(install_dir) != manifest["version"]:
            raise UpdateError("Surum kontrolu basarisiz; onceki surume donuluyor.")
    except Exception as exc:
        try:
            _, old = _validated_backup(backup, home)
            _replace_files(install_dir, {n: old.get(n) for n in incoming})
        except Exception as rollback_exc:
            raise UpdateError("Guncelleme hatasi; otomatik geri alma DA basarisiz! Yedek: %s; %s" %
                              (backup, rollback_exc)) from exc
        raise UpdateError("Guncelleme basarisiz; onceki dosyalar geri getirildi: " + str(exc)) from exc
    return {"before": old_version, "after": manifest["version"], "backup": str(backup)}


def perform_restore(backup_folder: Path, install_dir: Path = INSTALL_ROOT, home: Path | None = None) -> dict:
    install_dir = Path(install_dir)
    home = home or data_folder()
    data, restored = _validated_backup(Path(backup_folder), home)
    names = list(data["files"])
    for name in names:
        _safe_target(install_dir, name)
    safety = _snapshot(install_dir, names, home, current_version(install_dir))
    try:
        _replace_files(install_dir, {n: restored.get(n) for n in names})
        if current_version(install_dir) != data["version"]:
            raise UpdateError("Geri yuklenen surum uyusmadi.")
    except Exception as exc:
        try:
            _, previous = _validated_backup(safety, home)
            _replace_files(install_dir, {n: previous.get(n) for n in names})
        except Exception as second:
            raise UpdateError("Geri donus hatasi ve acil kurtarma hatasi! %s" % second) from exc
        raise UpdateError("Geri donus yapilamadi; onceki kurulum korundu: %s" % exc) from exc
    return {"after": data["version"], "safety_backup": str(safety)}


def _wait_for_pid(pid: int):
    if pid <= 0 or os.name != "nt":
        return
    import ctypes
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    h = kernel.OpenProcess(0x00100000, False, pid)
    if h:
        try:
            rc = kernel.WaitForSingleObject(h, 30000)
            if rc == 0x102:
                raise UpdateError("Eski uygulama 30 saniyede kapanmadi.")
        finally:
            kernel.CloseHandle(h)
    else:
        time.sleep(2)


def _restart(executable: str, app_file: Path):
    if os.name != "nt":
        return
    # Never silently reopen the network scanner with elevated UAC permissions.
    # Users can relaunch it from Start if the updater needed admin rights.
    import ctypes
    if bool(ctypes.windll.shell32.IsUserAnAdmin()):
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([executable, str(app_file)], cwd=str(app_file.parent),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags)


def _report(home: Path, status: str, message: str, result=None):
    _write_json(home / "updates" / "last-result.json", {
        "time": datetime.now(timezone.utc).isoformat(), "status": status,
        "message": message, "result": result or {},
    })
    path = home / "updates" / "update-history.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write("[%s] %s: %s\n" % (datetime.now().isoformat(timespec="seconds"), status, message))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--apply", type=Path)
    operation.add_argument("--restore", type=Path)
    operation.add_argument("--backup-existing", action="store_true")
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--pythonw", default=sys.executable)
    args = parser.parse_args(argv)
    home = data_folder()
    if args.backup_existing:
        paths = ["app.pyw", "scanner_core.py", "agfo_updater.py", "agfo_github_update.py",
                 "supertools_core.py", "supertools_ui.py", "ssh_profiles.py", "modern_shell.py",
                 "ssh_password_vault.py", "ssh_password_transport.py", "ssh_workspace.py",
                 "assets/agfo-scanner.ico", "assets/agfo-scanner.png"]
        try:
            result = _snapshot(INSTALL_ROOT, paths, home, current_version(INSTALL_ROOT))
            print("Guncelleme oncesi surum yedeklendi:", result)
            return 0
        except Exception as exc:
            print("Surum yedeklenemedi:", exc)
            return 1
    try:
        _wait_for_pid(args.parent_pid)
        if args.apply:
            result = perform_update(args.apply, INSTALL_ROOT, home)
            _report(home, "success", "Guncelleme %s -> %s" % (result["before"], result["after"]), result)
        else:
            result = perform_restore(args.restore, INSTALL_ROOT, home)
            _report(home, "success", "Yedekten geri donuldu: " + result["after"], result)
        try:
            _restart(args.pythonw, INSTALL_ROOT / "app.pyw")
        except Exception as restart_exc:
            _report(home, "success_restart_pending", "Guncelleme tamam; yeniden acilis olmadi: " + str(restart_exc), result)
        return 0
    except Exception as exc:
        _report(home, "error", str(exc))
        # Relaunch the original installation (or restored one) when possible.
        if (INSTALL_ROOT / "app.pyw").is_file():
            try:
                _restart(args.pythonw, INSTALL_ROOT / "app.pyw")
            except Exception:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
