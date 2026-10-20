"""AGFO Phantom Shot 1.0.0 - GUI'den bagimsiz cekirdek (test edilebilir, yalnizca standart kutuphane).

Phantom Shot, belirlenen bir klavye ya da fare tusuna basildiginda ekran goruntusunu alip
ayarlanan klasore kaydeder; ekranda hicbir pencere, bildirim ya da ses gostermez. Yakalamanin
kendisi (mss) ve tus dinleme (pynput) GUI tarafindadir; bu cekirdek yalnizca ayar yonetimi ve
uygulama ici / GitHub guncelleme hattini icerir (yalnizca standart kutuphane ile test edilebilir).

Guncelleme hatti AGFO System Care ile ayni sozlesmeyi kullanir: paket diske acilmadan denetlenir
(yapi, surum, MANIFEST/SHA-256), mevcut surum yedeklenir, dosyalar atomik yerlestirilir ve herhangi
bir adim basarisiz olursa onceki surume otomatik donulur.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import time

VERSION = '1.0.0'
IS_WIN = sys.platform == 'win32'
CREATIONFLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

LOCALAPPDATA = os.environ.get('LOCALAPPDATA', str(pathlib.Path.home()))
APP_DATA_DIR = pathlib.Path(LOCALAPPDATA) / 'AGFO' / 'PhantomShot'
SETTINGS_FILE = APP_DATA_DIR / 'config.json'
LOG_DIR = APP_DATA_DIR / 'logs'

# config.json varsayilanlari (kullanici verisi; kurulum klasorune degil APP_DATA_DIR'a yazilir).
DEFAULT_CONFIG = {
    'save_dir': '',          # bos -> ~/Pictures/PhantomShots
    'key': 'f9',             # tetik tusu adi; '(yok)'/bos -> klavye dinlenmez
    'mouse_button': '',      # 'middle' / 'x1' / 'x2' / 'right' / bos
    'monitor': 0,            # 0=tum ekranlar, 1=birincil, 2=ikincil...
    'prefix': 'shot',
    'format': 'png',         # png | jpg
    'jpg_quality': 90,
    'autostart': False,      # acilista dinlemeye hemen basla
    'minimize_to_tray': True,
    'auto_update_check': True,
}


# --------------------------------------------------------------------------- ayarlar
def load_settings():
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            out = dict(DEFAULT_CONFIG)
            out.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
            return out
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)


def save_settings(data):
    try:
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        clean = {k: v for k, v in (data or {}).items() if k in DEFAULT_CONFIG}
        tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + '.new')
        tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(tmp, SETTINGS_FILE)
        return True
    except OSError:
        return False


def resolve_save_dir(raw):
    """Bos ise ~/Pictures(Resimler)/PhantomShots; aksi halde mutlak yol."""
    raw = (raw or '').strip()
    if not raw:
        pics = pathlib.Path.home() / 'Pictures'
        if not pics.is_dir():
            alt = pathlib.Path.home() / 'Resimler'
            pics = alt if alt.is_dir() else pathlib.Path.home()
        raw = str(pics / 'PhantomShots')
    return os.path.abspath(os.path.expanduser(raw))


def screenshot_name(prefix='shot', fmt='png', now=None):
    """Zaman damgali, cakismayan dosya adi (milisaniye dahil)."""
    now = now or time.time()
    lt = time.localtime(now)
    ms = int((now - int(now)) * 1000)
    base = (prefix or 'shot').strip() or 'shot'
    ext = (fmt or 'png').lower().lstrip('.')
    if ext in ('jpeg',):
        ext = 'jpg'
    if ext not in ('png', 'jpg'):
        ext = 'png'
    return '%s_%s_%03d.%s' % (base, time.strftime('%Y%m%d_%H%M%S', lt), ms, ext)


# =========================================================================== GUNCELLEME HATTI
UPDATE_APP_ID = 'agfo-phantom-shot'
UPDATE_REQUIRED = ('app.pyw', 'phantom_core.py', 'agfo_github_update.py')
UPDATE_MAX_BYTES = 30 * 1024 * 1024
UPDATE_KEEP_BACKUPS = 3
UPDATE_LOG = LOG_DIR / 'updates.log'


def _is_runtime_file(rel):
    """Kurulum klasorune girecek dosyalar: kok dizindeki .py/.pyw/.ps1/.md/.txt ve assets/ altindakiler.
    tests/, packaging/, .cmd, config.json, MANIFEST ve bildirim dosyalari kuruluma kopyalanmaz."""
    rel = rel.replace('\\', '/')
    parts = rel.split('/')
    if any(p in ('', '.', '..') for p in parts) or '__pycache__' in parts:
        return False
    if parts[0] == 'assets' and len(parts) >= 2:
        return True
    if len(parts) != 1:
        return False
    name = parts[0].lower()
    if name in ('manifest.json', 'config.json'):
        return False
    return name.endswith(('.py', '.pyw', '.ps1', '.md', '.txt'))


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r'\d+', v or '')) or (0,)


def build_manifest(root, version=None):
    """Paket koku icin MANIFEST.json icerigi: uygulama kimligi, surum, calisma dosyalarinin SHA-256 ozetleri."""
    import hashlib
    root = pathlib.Path(root)
    files = {}
    for p in sorted(root.rglob('*')):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if _is_runtime_file(rel):
                files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    if version is None:
        m = re.search(r"^VERSION = '([\d.]+)'", (root / 'phantom_core.py').read_text(encoding='utf-8'), re.M)
        version = m.group(1) if m else ''
    return {'app': UPDATE_APP_ID, 'version': version, 'files': files}


def inspect_update(zip_path, current_version):
    """ZIP'i diske acmadan denetler. Donus: {'ok','version','prefix','files':{rel:arcname},'manifest','downgrade','same','errors','warnings'}"""
    import hashlib
    import zipfile
    info = {'ok': False, 'version': '', 'prefix': '', 'files': {}, 'manifest': None,
            'downgrade': False, 'same': False, 'errors': [], 'warnings': []}
    err, warn = info['errors'].append, info['warnings'].append
    try:
        if os.path.getsize(zip_path) > UPDATE_MAX_BYTES:
            err('Paket cok buyuk (sinir %d MB).' % (UPDATE_MAX_BYTES // 1048576)); return info
        z = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as e:
        err('ZIP acilamadi: %s' % e); return info
    with z:
        names = [n for n in z.namelist() if not n.endswith('/')]
        for n in names:
            norm = n.replace('\\', '/')
            if norm.startswith('/') or re.match(r'^[A-Za-z]:', norm) or '..' in norm.split('/'):
                err('Guvensiz dosya yolu reddedildi: %s' % n); return info
        total = sum(i.file_size for i in z.infolist())
        if total > UPDATE_MAX_BYTES * 4:
            err('Acilmis boyut cok buyuk (%d MB).' % (total // 1048576)); return info
        cands = sorted((n for n in names if n.replace('\\', '/').split('/')[-1] == 'app.pyw'), key=lambda n: n.count('/'))
        if not cands:
            err('Pakette app.pyw yok - bu bir AGFO Phantom Shot guncelleme paketi degil.'); return info
        prefix = cands[0].replace('\\', '/')[:-len('app.pyw')]
        info['prefix'] = prefix
        for n in names:
            norm = n.replace('\\', '/')
            if norm.startswith(prefix):
                rel = norm[len(prefix):]
                if _is_runtime_file(rel):
                    info['files'][rel] = n
        missing = [f for f in UPDATE_REQUIRED if f not in info['files']]
        if missing:
            err('Zorunlu dosyalar eksik: %s' % ', '.join(missing)); return info
        core_src = z.read(info['files']['phantom_core.py']).decode('utf-8', 'replace')
        m = re.search(r"^VERSION = '([\d.]+)'", core_src, re.M)
        if not m or 'AGFO Phantom Shot' not in core_src:
            err('phantom_core.py icinde AGFO Phantom Shot surum bilgisi bulunamadi.'); return info
        info['version'] = m.group(1)
        cv, nv = version_tuple(current_version), version_tuple(info['version'])
        info['downgrade'], info['same'] = nv < cv, nv == cv
        man_name = prefix + 'MANIFEST.json'
        man_arc = next((n for n in names if n.replace('\\', '/') == man_name), None)
        if man_arc:
            try:
                man = json.loads(z.read(man_arc).decode('utf-8'))
            except ValueError:
                err('MANIFEST.json okunamadi.'); return info
            if man.get('app') != UPDATE_APP_ID:
                err('MANIFEST baska bir uygulamaya ait: %s' % man.get('app')); return info
            if man.get('version') != info['version']:
                err('MANIFEST surumu (%s) ile phantom_core.py surumu (%s) uyusmuyor.' % (man.get('version'), info['version'])); return info
            mf = man.get('files') or {}
            for rel, arc in info['files'].items():
                if rel not in mf:
                    err("MANIFEST'te olmayan dosya: %s" % rel); return info
                if hashlib.sha256(z.read(arc)).hexdigest() != str(mf[rel]).lower():
                    err('SHA-256 uyusmuyor (paket bozuk ya da degistirilmis): %s' % rel); return info
            gone = [r for r in mf if r not in info['files']]
            if gone:
                err("MANIFEST'teki dosyalar pakette yok: %s" % ', '.join(gone[:5])); return info
            info['manifest'] = True
        else:
            info['manifest'] = False
            warn('Pakette MANIFEST.json yok: dosya butunlugu dogrulanamiyor (eski paket bicimi).')
    info['ok'] = True
    return info


def stage_update(zip_path, info, stage_dir):
    import shutil
    import zipfile
    stage = pathlib.Path(stage_dir)
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    root = stage.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for rel, arc in info['files'].items():
            dest = (stage / rel).resolve()
            if root not in dest.parents:
                raise OSError('Guvensiz yol: %s' % rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(arc))
    return stage


def preflight(stage_dir, ps_parser=True):
    """Yeni surumu kurmadan once denetler: tum .py/.pyw dosyalari derlenir, .ps1 dosyalari PowerShell AST ile ayristirilir.
    Donus: [(baslik, 'ok'|'fail'|'skip', ayrinti)]"""
    stage = pathlib.Path(stage_dir)
    checks = []
    for p in sorted(stage.glob('*.py*')):
        if p.suffix not in ('.py', '.pyw'):
            continue
        try:
            compile(p.read_text(encoding='utf-8'), p.name, 'exec')
            checks.append(('Python derleme: ' + p.name, 'ok', ''))
        except (SyntaxError, UnicodeDecodeError, ValueError) as e:
            checks.append(('Python derleme: ' + p.name, 'fail', str(e)))
    for p in sorted(stage.glob('*.ps1')):
        exe = None
        if ps_parser:
            import shutil
            exe = shutil.which('powershell.exe') or shutil.which('powershell') or shutil.which('pwsh')
        if not exe:
            checks.append(('PowerShell sozdizimi: ' + p.name, 'skip', 'PowerShell bulunamadi'))
            continue
        script = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e); "
                  "if($e.Count){ $e | ForEach-Object { $_.Message }; exit 3 } else { 'OK' }") % str(p).replace("'", "''")
        try:
            r = subprocess.run([exe, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
                               capture_output=True, text=True, timeout=60, creationflags=CREATIONFLAGS, stdin=subprocess.DEVNULL)
            ok = r.returncode == 0 and 'OK' in r.stdout
            checks.append(('PowerShell sozdizimi: ' + p.name, 'ok' if ok else 'fail', '' if ok else (r.stdout + r.stderr).strip()[:300]))
        except Exception as e:
            checks.append(('PowerShell sozdizimi: ' + p.name, 'skip', str(e)))
    return checks


def _installed_runtime_files(install_dir):
    d = pathlib.Path(install_dir)
    return [p.relative_to(d).as_posix() for p in d.rglob('*') if p.is_file() and _is_runtime_file(p.relative_to(d).as_posix())]


def list_backups(backup_root):
    root = pathlib.Path(backup_root)
    if not root.is_dir():
        return []
    out = []
    for d in root.iterdir():
        meta = d / 'backup.json'
        if d.is_dir() and meta.is_file():
            try:
                m = json.loads(meta.read_text(encoding='utf-8'))
                out.append({'path': str(d), 'version': m.get('version', ''), 'time': m.get('time', ''), 'files': m.get('files', [])})
            except ValueError:
                pass
    out.sort(key=lambda b: (b['time'], os.path.getmtime(b['path'])), reverse=True)
    return out


def _copy_tree_files(src_root, rels, dst_root):
    import shutil
    for rel in rels:
        s, d = pathlib.Path(src_root) / rel, pathlib.Path(dst_root) / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        tmp = d.with_name(d.name + '.agfo-new')
        shutil.copy2(s, tmp)
        os.replace(tmp, d)


def _log_update(text):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(UPDATE_LOG, 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), text))
    except OSError:
        pass


def apply_update(stage_dir, install_dir, backup_root, old_version, new_version, fail_after=None):
    """Mevcut calisma dosyalarini yedekler, yeni dosyalari atomik olarak yerlestirir. Herhangi bir adim basarisiz
    olursa yedekten otomatik geri doner ve hatayi yeniden firlatir. Donus: yedek klasoru."""
    import shutil
    install, stage = pathlib.Path(install_dir), pathlib.Path(stage_dir)
    probe = install / '.agfo-write-test'
    try:
        probe.write_text('x'); probe.unlink()
    except OSError as e:
        raise OSError('Kurulum klasorune yazilamiyor (%s). Uygulamayi yonetici olarak acin.' % e)
    old_files = _installed_runtime_files(install)
    new_files = [p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file()]
    base = '%s_%s' % (time.strftime('%Y%m%d-%H%M%S'), re.sub(r'[^0-9A-Za-z._-]', '_', old_version or 'bilinmiyor'))
    pathlib.Path(backup_root).mkdir(parents=True, exist_ok=True)
    for n in range(100):
        bdir = pathlib.Path(backup_root) / (base if n == 0 else '%s-%d' % (base, n))
        try:
            bdir.mkdir(exist_ok=False)
            break
        except FileExistsError:
            continue
    else:
        raise OSError('Yedek klasoru olusturulamadi')
    _copy_tree_files(install, old_files, bdir)
    (bdir / 'backup.json').write_text(json.dumps({'version': old_version, 'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'files': old_files},
                                                 ensure_ascii=False), encoding='utf-8')
    done = []
    try:
        for n, rel in enumerate(new_files):
            if fail_after is not None and n >= fail_after:
                raise OSError('test: yapay hata')
            _copy_tree_files(stage, [rel], install)
            done.append(rel)
        # yeni surumde artik olmayan eski calisma dosyalari temizlenir; yedekte duruyor
        for rel in old_files:
            if rel not in new_files:
                try:
                    (install / rel).unlink()
                except OSError:
                    pass
        (install / 'VERSION').write_text(new_version, encoding='ascii')
        shutil.rmtree(install / '__pycache__', ignore_errors=True)
    except BaseException as e:
        _restore(bdir, install, old_files, new_files, old_version)
        _log_update('BASARISIZ %s -> %s, geri alindi: %s' % (old_version, new_version, e))
        raise OSError('Guncelleme uygulanamadi, onceki surum geri yuklendi: %s' % e)
    for b in list_backups(backup_root)[UPDATE_KEEP_BACKUPS:]:
        shutil.rmtree(b['path'], ignore_errors=True)
    _log_update('GUNCELLENDI %s -> %s (yedek: %s)' % (old_version, new_version, bdir))
    return str(bdir)


def _restore(bdir, install, old_files, new_files, old_version=''):
    import shutil
    for rel in new_files:
        if rel not in old_files:
            try:
                (pathlib.Path(install) / rel).unlink()
            except OSError:
                pass
    _copy_tree_files(bdir, old_files, install)
    if old_version:
        try:
            (pathlib.Path(install) / 'VERSION').write_text(old_version, encoding='ascii')
        except OSError:
            pass
    shutil.rmtree(pathlib.Path(install) / '__pycache__', ignore_errors=True)


def rollback_update(backup_path, install_dir, current_version):
    """Secilen yedege doner (mevcut surum de once yedeklenir, boylece geri donus de geri alinabilir)."""
    import shutil
    b = pathlib.Path(backup_path)
    meta = json.loads((b / 'backup.json').read_text(encoding='utf-8'))
    target = meta.get('version', '')
    stage = b.parent / '_rollback_stage'
    shutil.rmtree(stage, ignore_errors=True)
    _copy_tree_files(b, meta.get('files', []), stage)
    try:
        bdir = apply_update(stage, install_dir, b.parent, current_version, target)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    _log_update('GERI DONULDU %s -> %s' % (current_version, target))
    return target, bdir


def update_history(limit=10):
    try:
        lines = UPDATE_LOG.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    return lines[-limit:]


# --------------------------------------------------------------------------- GitHub surum denetimi
GH_PREFIX = 'phantom-shot-v'
GH_ASSET = r'AGFO-Phantom-Shot-v\d+(?:\.\d+)+\.zip'
GH_STATE = APP_DATA_DIR / 'github-update.json'
GH_DOWNLOAD_DIR = APP_DATA_DIR / 'update-download'
