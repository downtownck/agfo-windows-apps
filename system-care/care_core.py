"""AGFO System Care 3.0.0 - GUI'den bagimsiz cekirdek (test edilebilir, yalnizca standart kutuphane).

Motorlar (BleachBit, Bulk Crap Uninstaller, Snappy Driver Installer Origin) AGFO arayuzunun ICINDE calisir:
kurulum WinGet ile sessiz yapilir, motorlar komut satiri / betik kipinde arka planda kosar, sonuclar
AGFO listelerinde gosterilir. Hicbir islev web sayfasi acmaz.
"""
import ctypes
import glob
import json
import os
import pathlib
import re
import subprocess
import sys
import time

VERSION = '3.5.0'
IS_WIN = sys.platform == 'win32'
CREATIONFLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

LOCALAPPDATA = os.environ.get('LOCALAPPDATA', str(pathlib.Path.home()))
APP_DATA_DIR = pathlib.Path(LOCALAPPDATA) / 'AGFO' / 'SystemCare'
LOG_DIR = pathlib.Path(LOCALAPPDATA) / 'AGFO' / 'DriverCare' / 'logs'   # 2.x ile ayni (sozlesme)
SETTINGS_FILE = APP_DATA_DIR / 'settings.json'
# SDIO betik dili yollarda tirnak destegini belgelemiyor; bosluksuz bir kok kullanilir (C:\ProgramData).
SDIO_ROOT = pathlib.Path(os.environ.get('ProgramData', r'C:\ProgramData')) / 'AGFO' / 'SDIO'

ENGINES = {
    'bleachbit': {'name': 'BleachBit', 'winget': 'BleachBit.BleachBit', 'license': 'GPL-3.0',
                  'role': 'Gizlilik ve disk temizliği motoru (Temizlik sekmesi)'},
    'bcu': {'name': 'Bulk Crap Uninstaller', 'winget': 'Klocman.BulkCrapUninstaller', 'license': 'Apache-2.0',
            'role': 'Genişletilmiş program envanteri ve artık temizliği (Programlar sekmesi)'},
    'sdio': {'name': 'Snappy Driver Installer Origin', 'winget': 'GlennDelahoy.SnappyDriverInstallerOrigin', 'license': 'GPL-3.0',
             'role': 'Çevrimdışı sürücü veritabanı ile sürücü analizi/kurulumu (Sürücüler sekmesi)'},
}


# --------------------------------------------------------------------------- genel
def is_admin():
    if not IS_WIN:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def load_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_settings(data):
    try:
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    except Exception:
        pass


def file_version(path):
    """Windows dosya surum bilgisi (VS_FIXEDFILEINFO); ek surec acmadan."""
    if not IS_WIN or not path:
        return ''
    try:
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return ''
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(str(path), 0, size, buf):
            return ''
        ptr = ctypes.c_void_p()
        ln = ctypes.c_uint()
        if not ver.VerQueryValueW(buf, '\\', ctypes.byref(ptr), ctypes.byref(ln)):
            return ''
        ffi = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint32 * 4)).contents
        ms, ls = ffi[2], ffi[3]
        return '%d.%d.%d.%d' % (ms >> 16, ms & 0xffff, ls >> 16, ls & 0xffff)
    except Exception:
        return ''


def human_size(kb):
    try:
        kb = float(kb)
    except (TypeError, ValueError):
        return ''
    if kb <= 0:
        return ''
    if kb < 1024:
        return '%.0f KB' % kb
    if kb < 1024 * 1024:
        return '%.1f MB' % (kb / 1024)
    return '%.2f GB' % (kb / 1024 / 1024)


# --------------------------------------------------------------------------- motor bulma
def _env(name, default=''):
    return os.environ.get(name, default)


def winget_package_dirs(pkg_id):
    roots = [os.path.join(_env('LOCALAPPDATA'), 'Microsoft', 'WinGet', 'Packages'),
             os.path.join(_env('ProgramFiles', r'C:\Program Files'), 'WinGet', 'Packages'),
             os.path.join(_env('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'WinGet', 'Packages')]
    out = []
    for r in roots:
        if r and os.path.isdir(r):
            out.extend(sorted(glob.glob(os.path.join(glob.escape(r), glob.escape(pkg_id) + '_*'))))
    return out


def _first_file(paths):
    return next((p for p in paths if p and os.path.isfile(p)), None)


def _glob_depth(root, pattern, depth=3):
    found = []
    for d in range(depth + 1):
        found.extend(glob.glob(os.path.join(glob.escape(root), *(['*'] * d), pattern)))
    return found


def find_winget():
    import shutil
    w = shutil.which('winget.exe') or shutil.which('winget')
    if w:
        return w
    alias = os.path.join(_env('LOCALAPPDATA'), 'Microsoft', 'WindowsApps', 'winget.exe')
    return alias if os.path.isfile(alias) else None


ENGINE_DIR = APP_DATA_DIR / 'engines'


def registry_install_dirs(name_pattern, programs=None):
    """Kayit defterindeki kurulum kayitlarindan (InstallLocation / kaldirici / simge klasoru) motor klasorlerini bulur.
    WinGet 'zaten kurulu' dedigi halde dosya bulunamamasinin nedeni, standart disi kurulum konumlaridir."""
    if programs is None:
        try:
            programs = read_programs()
        except Exception:
            programs = []
    out = []
    for p in programs:
        if not re.search(name_pattern, p.get('name', ''), re.I):
            continue
        icon = (p.get('icon') or '').split(',')[0].strip().strip('"')
        for cand in (p.get('location'), os.path.dirname(split_command(p.get('uninstall', ''))[0]), os.path.dirname(icon) if icon else ''):
            cand = os.path.expandvars(cand or '')
            if cand and os.path.isdir(cand) and cand not in out:
                out.append(cand)
    return out


def find_bleachbit():
    import shutil
    cands = _glob_depth(str(ENGINE_DIR / 'BleachBit'), 'bleachbit_console.exe', 3) if (ENGINE_DIR / 'BleachBit').is_dir() else []
    cands += [shutil.which('bleachbit_console.exe'),
             os.path.join(_env('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'BleachBit', 'bleachbit_console.exe'),
             os.path.join(_env('ProgramFiles', r'C:\Program Files'), 'BleachBit', 'bleachbit_console.exe'),
             os.path.join(_env('LOCALAPPDATA'), 'Programs', 'BleachBit', 'bleachbit_console.exe'),
             os.path.join(_env('LOCALAPPDATA'), 'BleachBit', 'bleachbit_console.exe')]
    for d in winget_package_dirs(ENGINES['bleachbit']['winget']) + registry_install_dirs(r'^BleachBit'):
        cands.extend(_glob_depth(d, 'bleachbit_console.exe', 2))
    return _first_file(cands)


def find_bcu():
    """(BCUninstaller.exe, BCU-console.exe) - bulunamayan None."""
    import shutil
    dirs = [os.path.join(_env('ProgramFiles', r'C:\Program Files'), 'BCUninstaller'),
            os.path.join(_env('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'BCUninstaller'),
            os.path.join(_env('LOCALAPPDATA'), 'Programs', 'BCUninstaller')]
    dirs.extend(winget_package_dirs(ENGINES['bcu']['winget']))
    dirs.append(str(ENGINE_DIR / 'BCU'))
    dirs.extend(registry_install_dirs(r'BCUninstaller|Bulk Crap Uninstaller'))
    gui = [shutil.which('BCUninstaller.exe')] + [os.path.join(d, 'BCUninstaller.exe') for d in dirs]
    con = [shutil.which('BCU-console.exe')] + [os.path.join(d, 'BCU-console.exe') for d in dirs]
    for d in dirs[3:]:
        gui.extend(_glob_depth(d, 'BCUninstaller.exe', 2))
        con.extend(_glob_depth(d, 'BCU-console.exe', 2))
    return _first_file(gui), _first_file(con)


def _sdio_rank(path):
    m = re.search(r'_R(\d+)', os.path.basename(path), re.I)
    return int(m.group(1)) if m else 0


def find_sdio(settings=None):
    settings = settings or {}
    dirs = []
    if settings.get('sdio_dir'):
        dirs.append(settings['sdio_dir'])
    dirs.extend(winget_package_dirs(ENGINES['sdio']['winget']))
    dirs.insert(0, str(ENGINE_DIR / 'SDIO'))
    x64 = sys.maxsize > 2 ** 32 or _env('PROCESSOR_ARCHITEW6432') or _env('PROCESSOR_ARCHITECTURE').endswith('64')
    best = []
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        hits = _glob_depth(d, 'SDIO_x64_R*.exe', 3) if x64 else []
        hits = hits or [h for h in _glob_depth(d, 'SDIO_R*.exe', 3)]
        best.extend(hits)
    if not best:
        return None
    return max(best, key=_sdio_rank)


def engine_status(settings=None):
    bb = find_bleachbit()
    bcu_gui, bcu_con = find_bcu()
    sd = find_sdio(settings)
    def src(path):
        if not path:
            return ''
        try:
            return 'AGFO motor klasörü (taşınabilir)' if pathlib.Path(path).resolve().is_relative_to(ENGINE_DIR.resolve()) else ('WinGet' if 'WinGet' in path else 'Sistem kurulumu')
        except (AttributeError, OSError, ValueError):
            return 'AGFO motor klasörü (taşınabilir)' if str(ENGINE_DIR).lower() in str(path).lower() else 'Sistem kurulumu'
    return {
        'winget': {'path': find_winget()},
        'bleachbit': {'path': bb, 'version': file_version(bb), 'source': src(bb)},
        'bcu': {'path': bcu_gui, 'console': bcu_con, 'version': file_version(bcu_gui or bcu_con), 'source': src(bcu_gui or bcu_con)},
        'sdio': {'path': sd, 'version': ('R%d' % _sdio_rank(sd)) if sd else '', 'source': src(sd)},
    }


def winget_install_cmd(winget, pkg_id, upgrade=False):
    verb = 'upgrade' if upgrade else 'install'
    return [winget, verb, '--id', pkg_id, '--exact', '--source', 'winget', '--silent',
            '--accept-source-agreements', '--accept-package-agreements', '--disable-interactivity']


def winget_uninstall_cmd(winget, pkg_id):
    return [winget, 'uninstall', '--id', pkg_id, '--exact', '--source', 'winget', '--silent',
            '--accept-source-agreements', '--disable-interactivity']


def winget_code_text(code):
    """WinGet/kurulum cikis kodunu okunur hale getirir (negatif HRESULT -> 0x8A15....)."""
    if code is None:
        return ''
    # Kaynak: microsoft/winget-cli doc/windows/package-manager/winget/returnCodes.md
    known = {0x8A150006: 'kurulum programı başlatılamadı (ShellExecute)', 0x8A150011: 'kurulum dosyasının karması bildirimle uyuşmuyor',
             0x8A150014: 'paket bulunamadı', 0x8A15002B: 'uygulanabilir güncelleme yok', 0x8A150061: 'paketin bir sürümü zaten kurulu',
             0x8A150101: 'uygulama çalışıyor; kapatıp yeniden deneyin', 0x8A150102: 'başka bir kurulum sürüyor', 0x8A150103: 'dosya kullanımda',
             0x8A150104: 'eksik bağımlılık', 0x8A150105: 'disk dolu', 0x8A150106: 'bellek yetersiz', 0x8A150107: 'internet bağlantısı gerekli',
             0x8A150108: 'kurulum sırasında hata (yayıncı)', 0x8A150109: 'kurulumu bitirmek için yeniden başlatın',
             0x8A15010A: 'kurulum başarısız; yeniden başlatıp deneyin', 0x8A15010B: 'kurulum için bilgisayar yeniden başlatılacak',
             0x8A15010C: 'kurulumu iptal ettiniz', 0x8A15010D: 'başka bir sürüm zaten kurulu', 0x8A15010E: 'daha yeni sürüm zaten kurulu',
             0x8A15010F: 'kurum politikası kurulumu engelliyor', 0x8A150110: 'bağımlılıklar kurulamadı', 0x8A150111: 'uygulama başka bir uygulamaca kullanılıyor',
             0x8A150112: 'geçersiz parametre', 0x8A150113: 'paket bu sistemi desteklemiyor', 0x8A150114: 'kurulum programı yükseltmeyi desteklemiyor',
             0x8A150115: 'kurulum programına özgü hata'}
    u = code & 0xFFFFFFFF
    if u >= 0x80000000:
        return '0x%08X%s' % (u, (' — ' + known[u]) if u in known else '')
    return str(code)


# --------------------------------------------------------------------------- guvenli indirme + tasinabilir motorlar
# Motorlar resmi kaynaktan, yalnizca HTTPS ve izinli alan adlarindan indirilir; yonlendirmeler de denetlenir.
ALLOWED_HOSTS = {
    'bleachbit': ('bleachbit.org', 'sourceforge.net', 'sf.net'),
    'bcu': ('github.com', 'githubusercontent.com'),
    'sdio': ('glenn.delahoy.com',),
}
BLEACHBIT_PAGE = 'https://www.bleachbit.org/download/windows'
BLEACHBIT_FALLBACK = '6.0.4'
BCU_RELEASES_API = 'https://api.github.com/repos/Klocman/Bulk-Crap-Uninstaller/releases/latest'
SDIO_PAGE = 'https://www.glenn.delahoy.com/snappy-driver-installer-origin/'
MAX_DOWNLOAD = 700 * 1024 * 1024


def host_allowed(url, allowed):
    from urllib.parse import urlsplit
    u = urlsplit(url)
    if u.scheme != 'https' or not u.hostname:
        return False
    h = u.hostname.lower()
    return any(h == d or h.endswith('.' + d) for d in allowed)


def _opener(allowed):
    import urllib.request

    class Guard(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not host_allowed(newurl, allowed):
                raise OSError('İzin verilmeyen yönlendirme engellendi: %s' % newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    return urllib.request.build_opener(Guard())


def _request(url, allowed, accept=None):
    import urllib.request
    if not host_allowed(url, allowed):
        raise OSError('İzin verilmeyen adres: %s' % url)
    hdr = {'User-Agent': 'AGFO-System-Care/%s (+Windows)' % VERSION}
    if accept:
        hdr['Accept'] = accept
    return _opener(allowed).open(urllib.request.Request(url, headers=hdr), timeout=45)


def fetch_text(url, allowed, limit=3 * 1024 * 1024, accept=None):
    with _request(url, allowed, accept) as r:
        return r.read(limit).decode('utf-8', 'replace')


def download(url, dest, allowed, progress=None, should_stop=None, sha256=None):
    import hashlib
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + '.part')
    h = hashlib.sha256()
    try:
        return _download_to(url, dest, tmp, h, allowed, progress, should_stop, sha256)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _download_to(url, dest, tmp, h, allowed, progress, should_stop, sha256):
    done = 0
    with _request(url, allowed) as r, open(tmp, 'wb') as f:
        total = int(r.headers.get('Content-Length') or 0)
        if total > MAX_DOWNLOAD:
            raise OSError('Dosya beklenenden büyük (%d MB)' % (total // 1048576))
        last = 0.0
        while True:
            if should_stop and should_stop():
                raise OSError('Durduruldu')
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if done > MAX_DOWNLOAD:
                raise OSError('İndirme boyut sınırını aştı')
            if progress and time.time() - last > 0.25:
                progress(done, total)
                last = time.time()
    if progress:
        progress(done, total)
    if sha256 and h.hexdigest().lower() != sha256.lower():
        with open(tmp, 'rb') as f:
            head = f.read(200).lstrip().lower()
        why = ' Sunucu dosya yerine bir web sayfası döndürdü.' if head.startswith((b'<!doctype', b'<html', b'<')) else ''
        raise OSError('SHA-256 doğrulaması başarısız; dosya silindi.' + why)
    tmp.replace(dest)
    return dest, h.hexdigest()


def _vkey(v):
    return tuple(int(x) for x in re.findall(r'\d+', v or ''))


# Not: download.bleachbit.org/get/... bir 'indirme basliyor' HTML sayfasidir (indirmeyi JavaScript baslatir);
# dosyanin kendisi /get/ olmadan download.bleachbit.org/BleachBit-<surum>-portable.zip adresindedir.
BLEACHBIT_KNOWN_SHA256 = {'6.0.4': '3425195570e4d191695c45537065dc007a51efd4fd675a47f7b6da6d686a4660'}


def bleachbit_file_url(ver):
    return 'https://download.bleachbit.org/BleachBit-%s-portable.zip' % ver


def bleachbit_sums_url(ver):
    return 'https://download.bleachbit.org/bleachbit-%s-sha256sum.txt' % ver


def bleachbit_portable_url(html=None):
    """Resmi indirme sayfasindaki ILK (kararli, 'onerilen') tasinabilir paket surumu -> (surum, dogrudan dosya adresi)."""
    if html:
        m = re.search(r'BleachBit-(\d+(?:\.\d+){1,3})-portable\.zip', html)
        if m:
            return m.group(1), bleachbit_file_url(m.group(1))
    return BLEACHBIT_FALLBACK, bleachbit_file_url(BLEACHBIT_FALLBACK)


def parse_sha256sums(text, filename):
    for line in (text or '').splitlines():
        m = re.match(r'\s*([0-9a-fA-F]{64})\s+\*?(\S+)\s*$', line)
        if m and m.group(2).lower() == filename.lower():
            return m.group(1).lower()
    return None


def bcu_portable_asset(release_json):
    """GitHub 'latest release' JSON -> (surum, url, sha256|None)."""
    try:
        d = json.loads(release_json) if isinstance(release_json, str) else release_json
    except ValueError:
        return None
    for a in d.get('assets', []):
        n = a.get('name', '').lower()
        if n.endswith('.zip') and 'portable' in n:
            dg = a.get('digest') or ''
            return d.get('tag_name', '').lstrip('v'), a.get('browser_download_url'), (dg.split(':', 1)[1] if dg.startswith('sha256:') else None)
    return None


def sdio_zip_url(html, base=SDIO_PAGE):
    from urllib.parse import urljoin
    cands = re.findall(r'href=["\']([^"\']*SDIO_\d+(?:\.\d+)+\.zip)["\']', html or '', re.I)
    if not cands:
        return None
    best = max(cands, key=lambda u: _vkey(re.search(r'SDIO_([\d.]+)\.zip', u, re.I).group(1)))
    return urljoin(base, best)


def safe_extract(zip_path, target, must_contain):
    """ZIP'i once target.new'e acar (zip-slip korumali), aranan dosya varsa eskisinin yerine koyar. Dondurur: bulunan dosya yolu."""
    import shutil
    import zipfile
    target = pathlib.Path(target)
    new = target.with_name(target.name + '.new')
    old = target.with_name(target.name + '.old')
    shutil.rmtree(new, ignore_errors=True)
    new.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            raise OSError('ZIP bozuk: %s' % bad)
        root = new.resolve()
        for info in z.infolist():
            dest = (new / info.filename).resolve()
            if dest != root and root not in dest.parents:
                raise OSError('Güvensiz ZIP yolu reddedildi: %s' % info.filename)
        z.extractall(new)
    hits = [p for p in new.rglob('*') if p.name.lower() == must_contain.lower()]
    if not hits:
        shutil.rmtree(new, ignore_errors=True)
        raise OSError('Pakette %s bulunamadı' % must_contain)
    rel = hits[0].relative_to(new)
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        try:
            target.rename(old)
        except OSError:
            shutil.rmtree(new, ignore_errors=True)
            raise OSError('Eski motor klasörü kullanımda; motoru kapatıp tekrar deneyin: %s' % target)
    new.rename(target)
    shutil.rmtree(old, ignore_errors=True)
    return target / rel


def install_portable(key, say, progress=None, should_stop=None, fetch=fetch_text, dl=download):
    """Motoru resmi tasinabilir paketinden AGFO motor klasorune kurar (yonetici gerekmez). Dondurur: exe yolu."""
    allowed = ALLOWED_HOSTS[key]
    ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    sha = None
    if key == 'bleachbit':
        try:
            html = fetch(BLEACHBIT_PAGE, allowed)
        except Exception as e:
            say('İndirme sayfası okunamadı (%s); sabit sürüm %s kullanılıyor.' % (e, BLEACHBIT_FALLBACK))
            html = None
        ver, url = bleachbit_portable_url(html)
        try:
            sha = parse_sha256sums(fetch(bleachbit_sums_url(ver), allowed), 'BleachBit-%s-portable.zip' % ver)
        except Exception as e:
            say('Yayıncı özet dosyası okunamadı (%s).' % e)
            sha = None
        sha = sha or BLEACHBIT_KNOWN_SHA256.get(ver)
        if not sha:
            raise OSError('BleachBit %s için yayıncı SHA-256 özeti alınamadı; doğrulanamayan dosya kurulmaz.' % ver)
        exe, folder = 'bleachbit_console.exe', 'BleachBit'
    elif key == 'bcu':
        asset = bcu_portable_asset(fetch(BCU_RELEASES_API, allowed, accept='application/vnd.github+json'))
        if not asset:
            raise OSError('BCU sürüm sayfasında taşınabilir paket bulunamadı')
        ver, url, sha = asset
        exe, folder = 'BCU-console.exe', 'BCU'
    elif key == 'sdio':
        url = sdio_zip_url(fetch(SDIO_PAGE, allowed))
        if not url:
            raise OSError('SDIO indirme sayfasında ZIP bağlantısı bulunamadı')
        ver = re.search(r'SDIO_([\d.]+)\.zip', url, re.I).group(1)
        exe, folder = ('SDIO_x64_R*.exe', 'SDIO')
    else:
        raise ValueError(key)
    say('%s %s indiriliyor: %s' % (ENGINES[key]['name'], ver, url))
    zp = ENGINE_DIR / ('_%s-%s.zip' % (folder, ver))
    _, digest = dl(url, zp, allowed, progress, should_stop, sha)
    say('İndirildi (SHA-256 %s%s).' % (digest[:16] + '…', ', yayıncı özetiyle doğrulandı' if sha else ''))
    try:
        import zipfile
        if not zipfile.is_zipfile(zp):
            with open(zp, 'rb') as f:
                head = f.read(200).lstrip().lower()
            raise OSError('Sunucu ZIP yerine %s döndürdü (%s)' % ('bir web sayfası' if head.startswith((b'<!doctype', b'<html')) else 'geçersiz bir dosya', url))
        if key == 'sdio':
            import zipfile
            with zipfile.ZipFile(zp) as z:
                names = [n for n in z.namelist() if re.search(r'SDIO_(x64_)?R\d+\.exe$', n, re.I)]
            if not names:
                raise OSError('Pakette SDIO çalıştırılabilir dosyası yok')
            path = safe_extract(zp, ENGINE_DIR / folder, os.path.basename(sorted(names)[-1]))
        else:
            path = safe_extract(zp, ENGINE_DIR / folder, exe)
    finally:
        try:
            zp.unlink()
        except OSError:
            pass
    say('Kuruldu: %s' % path)
    return str(path)


# --------------------------------------------------------------------------- BleachBit
BB_CLEANER_TR = {
    'system': 'Windows sistemi', 'windows_explorer': 'Windows Gezgini', 'google_chrome': 'Google Chrome',
    'chromium': 'Chromium', 'microsoft_edge': 'Microsoft Edge', 'firefox': 'Mozilla Firefox', 'opera': 'Opera',
    'brave': 'Brave', 'vivaldi': 'Vivaldi', 'internet_explorer': 'Internet Explorer', 'deep_scan': 'Derin tarama',
    'adobe_reader': 'Adobe Reader', 'flash': 'Flash', 'java': 'Java', 'libreoffice': 'LibreOffice',
    'microsoft_office': 'Microsoft Office', 'vlc': 'VLC', 'winrar': 'WinRAR', '7zip': '7-Zip', 'gimp': 'GIMP',
    'paint': 'Paint', 'wordpad': 'WordPad', 'thunderbird': 'Thunderbird', 'skype': 'Skype', 'discord': 'Discord',
    'zoom': 'Zoom', 'teamviewer': 'TeamViewer', 'filezilla': 'FileZilla', 'vim': 'Vim', 'waterfox': 'Waterfox',
    'palemoon': 'Pale Moon', 'seamonkey': 'SeaMonkey', 'safari': 'Safari', 'windows_defender': 'Windows Defender',
    'windows_media_player': 'Windows Media Player', 'microsoft_teams': 'Microsoft Teams', 'slack': 'Slack',
}
BB_OPTION_TR = {
    'cache': 'Önbellek', 'cookies': 'Çerezler (oturumlar kapanır)', 'history': 'Geçmiş', 'passwords': 'KAYITLI PAROLALAR',
    'session': 'Açık sekme/oturum', 'form_history': 'Form geçmişi', 'vacuum': 'Veritabanı sıkıştırma', 'tmp': 'Geçici dosyalar',
    'logs': 'Günlükler', 'recycle_bin': 'Geri Dönüşüm Kutusu', 'thumbnails': 'Küçük resim önbelleği', 'mru': 'Son kullanılanlar',
    'recent_documents': 'Son belgeler', 'memory_dump': 'Bellek dökümleri', 'prefetch': 'Prefetch', 'updates': 'Windows Update önbelleği',
    'free_disk_space': 'Boş alanın üzerine yaz (SAATLER SÜRER)', 'clipboard': 'Pano', 'dom': 'DOM depolama', 'download_history': 'İndirme geçmişi',
    'search_history': 'Arama geçmişi', 'run': 'Çalıştır geçmişi', 'shellbags': 'Klasör görünüm geçmişi', 'muicache': 'MUI önbelleği',
    'custom': 'Özel yollar', 'backup': 'Yedek dosyaları', 'thumbs_db': 'Thumbs.db', 'ds_store': '.DS_Store', 'sync': 'Eşitleme verisi',
    'site_preferences': 'Site tercihleri', 'search_engines': 'Arama motorları', 'url_history': 'Adres geçmişi', 'crash_reports': 'Çökme raporları',
    'last_session': 'Son oturum', 'mime_types': 'MIME türleri', 'downloads': 'İndirilenler listesi', 'cookie': 'Çerezler',
}
# Kullanici verisi kaybi / oturum kapanmasi / cok uzun sure riski olanlar: varsayilan secilmez, onayda ayrica uyarilir.
BB_RISKY_OPTIONS = {'passwords', 'cookies', 'cookie', 'session', 'last_session', 'form_history', 'dom', 'sync', 'site_preferences',
                    'search_engines', 'free_disk_space', 'custom', 'recycle_bin', 'backup', 'downloads', 'history', 'url_history'}
BB_SLOW = {'system.free_disk_space', 'system.memory'}
BB_SAFE_PRESET_OPTIONS = {'cache', 'tmp', 'thumbnails', 'memory_dump', 'logs', 'crash_reports'}


def parse_bleachbit_cleaners(lines):
    """`bleachbit_console --list-cleaners` -> {cleaner: [option, ...]} (sirali)."""
    out = {}
    for raw in lines:
        s = raw.strip()
        if not re.fullmatch(r'[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+', s):
            continue
        cl, op = s.split('.', 1)
        out.setdefault(cl, [])
        if op not in out[cl]:
            out[cl].append(op)
    return out


def bb_label(cleaner, option=None):
    if option is None:
        return BB_CLEANER_TR.get(cleaner, cleaner.replace('_', ' ').title())
    return BB_OPTION_TR.get(option, option.replace('_', ' '))


def bb_is_risky(cleaner, option):
    return option in BB_RISKY_OPTIONS or (cleaner + '.' + option) in BB_SLOW


def bb_default_selected(cleaner, option):
    key = cleaner + '.' + option
    if key in BB_SLOW or bb_is_risky(cleaner, option):
        return False
    if cleaner == 'deep_scan':
        return False
    return option in BB_SAFE_PRESET_OPTIONS


_BB_SIZE = re.compile(r'(\d+(?:[.,]\d+)?)\s*([kKMGT]?i?B)\b')


def parse_bleachbit_summary(lines):
    """Onizleme/temizlik ciktisinin sonundaki ozet satirlari (dile bagimsiz: son 6 satirda boyut/sayi arar)."""
    tail = [l.strip() for l in lines if l.strip()][-6:]
    summary = [l for l in tail if _BB_SIZE.search(l) or re.search(r':\s*\d+\s*$', l)]
    return summary[-3:]


# --------------------------------------------------------------------------- WinGet tablo ayristirici
def parse_winget_table(lines):
    """`winget upgrade/list` tablo ciktisini dile bagimsiz ayristirir.

    Baslik satiri, '-----' ayirici satirinin hemen ustundeki satirdir; sutun baslangiclari basliktaki
    kelime baslangiclarindan alinir (TR: Ad Kimlik Surum Kullanilabilir Kaynak / EN: Name Id Version Available Source).
    """
    clean = [l.rstrip('\r\n') for l in lines]
    sep = None
    for i, l in enumerate(clean):
        s = l.strip()
        if len(s) >= 10 and set(s) == {'-'}:
            sep = i
            break
    if sep is None or sep == 0:
        return []
    header = clean[sep - 1]
    # ilerleme kalintilarini at (ornek: "   -  \\  Name   Id ...")
    starts = [m.start() for m in re.finditer(r'(?:(?<=\s)|^)\S', header)]
    if len(starts) < 3:
        return []
    # bosluk icermeyen baslik kelimeleri varsayilir; 'Kullanilabilir' gibi tek kelime.
    rows = []
    for l in clean[sep + 1:]:
        if not l.strip():
            break
        if len(l) < starts[1]:
            continue
        cols = []
        for j, st in enumerate(starts):
            en = starts[j + 1] if j + 1 < len(starts) else None
            cols.append(l[st:en].strip() if en else l[st:].strip())
        # Ozet satiri ("3 upgrades available." / "2 yukseltme kullanilabilir.") veya hizasi kaymis satir:
        # gercek satirda kimlik sutunu bir bosluktan sonra baslar ve surum sutunu doludur.
        if not cols[1] or ' ' in cols[1] or (starts[1] > 0 and l[starts[1] - 1] != ' ') or len(cols) < 3 or not cols[2]:
            continue
        rows.append(cols)
    out = []
    for c in rows:
        d = {'name': c[0], 'id': c[1], 'version': c[2] if len(c) > 2 else ''}
        if len(c) >= 5:
            d['available'], d['source'] = c[3], c[4]
        elif len(c) == 4:
            d['available'], d['source'] = c[3], ''
        out.append(d)
    return out


# --------------------------------------------------------------------------- program envanteri (BCU ile ayni kaynak: Uninstall kayit anahtarlari)
_GUID = re.compile(r'\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}')
UNINSTALL_SUB = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'


def split_command(cmd):
    """'"C:\\x y\\u.exe" /S' -> ('C:\\x y\\u.exe', '/S'); tirnaksiz '.exe' sinirina gore boler."""
    cmd = (cmd or '').strip()
    if not cmd:
        return '', ''
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        if end > 0:
            return cmd[1:end], cmd[end + 1:].strip()
    m = re.search(r'\.(exe|cmd|bat|com)\b', cmd, re.I)
    if m:
        return cmd[:m.end()].strip(), cmd[m.end():].strip()
    parts = cmd.split(' ', 1)
    return parts[0], parts[1] if len(parts) > 1 else ''


def uninstaller_exists(cmd, exists=os.path.isfile):
    exe, _ = split_command(cmd)
    if not exe:
        return False
    low = exe.lower()
    if low.endswith(('msiexec.exe', 'msiexec', 'rundll32.exe', 'rundll32')) or os.path.basename(low) in ('msiexec.exe', 'rundll32.exe'):
        return True
    exe = os.path.expandvars(exe)
    import ntpath
    if not ntpath.isabs(exe):
        return True  # PATH uzerinden cozulur; yetim sayma
    return exists(exe)


def read_programs():
    """Kurulu programlari kayit defterinden okur (HKLM 64/32 + HKCU). Ek surec acmaz; ~50 ms."""
    if not IS_WIN:
        return []
    import winreg
    views = [(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY, 'HKLM', 'Makine'),
             (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY, 'HKLM', 'Makine (32 bit)'),
             (winreg.HKEY_CURRENT_USER, 0, 'HKCU', 'Kullanıcı')]
    seen = set()
    out = []
    for hive, view, hive_name, scope in views:
        try:
            root = winreg.OpenKey(hive, UNINSTALL_SUB, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                k = winreg.OpenKey(root, name, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            vals = {}
            j = 0
            while True:
                try:
                    vn, vd, _ = winreg.EnumValue(k, j)
                except OSError:
                    break
                j += 1
                vals[vn] = vd
            winreg.CloseKey(k)
            p = program_from_values(vals, name)
            if not p:
                continue
            p.update({'hive': hive_name, 'view': view, 'key': UNINSTALL_SUB + '\\' + name, 'scope': scope})
            sig = (p['name'].lower(), p['version'], p['hive'])
            if sig in seen:
                continue
            seen.add(sig)
            out.append(p)
        winreg.CloseKey(root)
    out.sort(key=lambda x: x['name'].lower())
    return out


def program_from_values(vals, key_name):
    name = str(vals.get('DisplayName') or '').strip()
    if not name:
        return None
    if int(vals.get('SystemComponent') or 0) == 1 or vals.get('ParentKeyName'):
        return None
    if str(vals.get('ReleaseType') or '') in ('Update', 'Hotfix', 'Security Update', 'Service Pack'):
        return None
    uninst = str(vals.get('UninstallString') or '').strip()
    msi = int(vals.get('WindowsInstaller') or 0) == 1 or 'msiexec' in uninst.lower()
    code = ''
    if msi:
        m = _GUID.search(key_name) or _GUID.search(uninst)
        code = m.group(0) if m else ''
    if not uninst and not code:
        return None
    date = str(vals.get('InstallDate') or '')
    if re.fullmatch(r'\d{8}', date):
        date = '%s-%s-%s' % (date[:4], date[4:6], date[6:])
    size = vals.get('EstimatedSize') or 0
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 0
    return {
        'name': name, 'version': str(vals.get('DisplayVersion') or ''), 'publisher': str(vals.get('Publisher') or ''),
        'date': date, 'size_kb': size, 'uninstall': uninst, 'quiet': str(vals.get('QuietUninstallString') or '').strip(),
        'location': str(vals.get('InstallLocation') or '').strip().strip('"'), 'msi': msi, 'product_code': code,
        'icon': str(vals.get('DisplayIcon') or ''),
    }


def annotate_programs(programs, exists=os.path.isfile):
    for p in programs:
        p['orphan'] = bool(p['uninstall']) and not p['msi'] and not uninstaller_exists(p['uninstall'], exists)
        p['kind'] = 'MSI' if p['msi'] else ('Yetim kayıt' if p['orphan'] else 'EXE')
        p['silent'] = bool(p['quiet']) or bool(p['msi'] and p['product_code'])
    return programs


def build_uninstall(p, quiet=True):
    """(exe, params) - ShellExecuteEx ile calistirilir (UAC gerekirse Windows sorar)."""
    if p.get('msi') and p.get('product_code'):
        return 'msiexec.exe', '/x %s %s' % (p['product_code'], '/passive /norestart' if quiet else '/norestart')
    cmd = p.get('quiet') if (quiet and p.get('quiet')) else p.get('uninstall')
    exe, params = split_command(cmd)
    return os.path.expandvars(exe), params


def leftover_candidates(p, remaining_programs, isdir=os.path.isdir, env=None):
    """Kaldirilan programdan kalan klasorler - yalnizca guvenli/kesin eslesmeler.

    Kurallar: (1) InstallLocation hala varsa; (2) Program Files / ProgramData / AppData koklerinde programin
    TAM adiyla (veya Yayinci\\Ad) eslesen klasorler. Baska kurulu programin konumu/adiyla cakisan hicbir yol onerilmez.
    """
    env = env or os.environ
    name = re.sub(r'[\\/:*?"<>|]', '', p.get('name', '')).strip()
    names = {name}
    short = re.sub(r'\s+(\(?(x64|x86|64-bit|32-bit)\)?|v?\d+(\.\d+)+.*)$', '', name, flags=re.I).strip()
    if len(short) >= 3:
        names.add(short)
    pub = re.sub(r'[\\/:*?"<>|]', '', p.get('publisher', '')).strip()
    pub = re.sub(r',?\s+(Inc|LLC|Ltd|GmbH|Corp|Corporation|Co)\.?$', '', pub, flags=re.I).strip()
    roots = [env.get('ProgramFiles'), env.get('ProgramFiles(x86)'), env.get('ProgramData'), env.get('APPDATA'), env.get('LOCALAPPDATA'),
             os.path.join(env.get('LOCALAPPDATA', ''), 'Programs') if env.get('LOCALAPPDATA') else None]
    roots = [r for r in roots if r]
    cands = []
    loc = p.get('location')
    if loc and isdir(loc):
        cands.append(os.path.normpath(loc))
    for r in roots:
        for n in names:
            if len(n) < 3:
                continue
            cands.append(os.path.join(r, n))
            if pub and len(pub) >= 3 and pub.lower() != n.lower():
                cands.append(os.path.join(r, pub, n))
    others_loc = [os.path.normcase(os.path.normpath(o['location'])) for o in remaining_programs if o.get('location')]
    others_names = {o['name'].lower() for o in remaining_programs}
    protected = {os.path.normcase(os.path.normpath(r)) for r in roots}
    out = []
    for c in cands:
        nc = os.path.normcase(os.path.normpath(c))
        if nc in protected or nc in [os.path.normcase(x) for x in out]:
            continue
        if not isdir(c):
            continue
        if os.path.basename(c).lower() in others_names and os.path.basename(c).lower() != name.lower():
            continue
        if any(ol == nc or ol.startswith(nc + os.sep) or nc.startswith(ol + os.sep) for ol in others_loc):
            continue
        out.append(os.path.normpath(c))
    return out


def parse_bcu_export(xml_text):
    """`BCU-console export file.xml` -> program sozlukleri. Sema belgelenmedigi icin DisplayName iceren her dugum okunur."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []

    def local(tag):
        return tag.rsplit('}', 1)[-1]
    for node in root.iter():
        kids = {local(c.tag): (c.text or '').strip() for c in list(node)}
        if not kids.get('DisplayName') or len(kids) < 3:
            continue
        out.append(kids)
    return out


def merge_bcu_programs(programs, bcu_rows):
    """BCU'nun buldugu ama kayit taramasinda olmayan uygulamalari (Store, Steam, yetim vb.) ekler."""
    have = {p['name'].lower() for p in programs}
    added = 0
    for r in bcu_rows:
        nm = r.get('DisplayName', '').strip()
        if not nm or nm.lower() in have:
            continue
        uninst = r.get('UninstallString', '')
        if not uninst:
            continue
        size = 0
        for k in ('EstimatedSize', 'EstimatedSizeKB'):
            try:
                size = int(float(r.get(k, 0) or 0))
                break
            except ValueError:
                pass
        p = {'name': nm, 'version': r.get('DisplayVersion', ''), 'publisher': r.get('Publisher', ''), 'date': r.get('InstallDate', '')[:10],
             'size_kb': size, 'uninstall': uninst, 'quiet': r.get('QuietUninstallString', ''), 'location': r.get('InstallLocation', ''),
             'msi': 'msiexec' in uninst.lower(), 'product_code': '', 'hive': 'BCU', 'view': 0, 'key': '', 'scope': 'BCU: ' + r.get('UninstallerKind', '')}
        if p['msi']:
            m = _GUID.search(uninst)
            p['product_code'] = m.group(0) if m else ''
        programs.append(p)
        have.add(nm.lower())
        added += 1
    annotate_programs(programs)
    programs.sort(key=lambda x: x['name'].lower())
    return added


def registry_key_exists(p):
    if not IS_WIN or not p.get('key'):
        return False
    import winreg
    hive = winreg.HKEY_LOCAL_MACHINE if p['hive'] == 'HKLM' else winreg.HKEY_CURRENT_USER
    try:
        winreg.CloseKey(winreg.OpenKey(hive, p['key'], 0, winreg.KEY_READ | p.get('view', 0)))
        return True
    except OSError:
        return False


def remove_registry_entry(p, backup_dir):
    """Yetim kaldirma kaydini once .reg olarak yedekler, sonra siler. (ok, mesaj)"""
    if not IS_WIN or not p.get('key'):
        return False, 'Kayıt anahtarı yok'
    import winreg
    backup_dir = pathlib.Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[^A-Za-z0-9_.-]+', '_', p['name'])[:60]
    reg_file = backup_dir / ('%s-%s.reg' % (time.strftime('%Y%m%d-%H%M%S'), safe))
    full = '%s\\%s' % (p['hive'], p['key'])
    flag = ['/reg:64'] if p.get('view') == winreg.KEY_WOW64_64KEY else (['/reg:32'] if p.get('view') == winreg.KEY_WOW64_32KEY else [])
    r = subprocess.run(['reg', 'export', full, str(reg_file), '/y'] + flag, capture_output=True, creationflags=CREATIONFLAGS)
    if r.returncode != 0:
        return False, 'Yedek alınamadı; silinmedi.'
    hive = winreg.HKEY_LOCAL_MACHINE if p['hive'] == 'HKLM' else winreg.HKEY_CURRENT_USER

    def rdel(parent, sub):
        with winreg.OpenKey(parent, sub, 0, winreg.KEY_ALL_ACCESS | p.get('view', 0)) as k:
            while True:
                try:
                    child = winreg.EnumKey(k, 0)
                except OSError:
                    break
                rdel(k, child)
        winreg.DeleteKeyEx(parent, sub, p.get('view') or winreg.KEY_WOW64_64KEY, 0)
    try:
        parent_path, leaf = p['key'].rsplit('\\', 1)
        with winreg.OpenKey(hive, parent_path, 0, winreg.KEY_ALL_ACCESS | p.get('view', 0)) as parent:
            rdel(parent, leaf)
        return True, 'Kayıt silindi; yedek: %s' % reg_file
    except PermissionError:
        return False, 'Yönetici yetkisi gerekli (yedek alındı: %s)' % reg_file
    except OSError as e:
        return False, 'Silinemedi: %s (yedek: %s)' % (e, reg_file)


# --------------------------------------------------------------------------- Windows: ShellExecuteEx + bekleme
if IS_WIN:
    from ctypes import wintypes

    class _SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('fMask', wintypes.ULONG), ('hwnd', wintypes.HWND), ('lpVerb', wintypes.LPCWSTR),
                    ('lpFile', wintypes.LPCWSTR), ('lpParameters', wintypes.LPCWSTR), ('lpDirectory', wintypes.LPCWSTR),
                    ('nShow', ctypes.c_int), ('hInstApp', wintypes.HINSTANCE), ('lpIDList', ctypes.c_void_p),
                    ('lpClass', wintypes.LPCWSTR), ('hkeyClass', wintypes.HKEY), ('dwHotKey', wintypes.DWORD),
                    ('hIconOrMonitor', wintypes.HANDLE), ('hProcess', wintypes.HANDLE)]


def shell_execute(exe, params='', verb=None, cwd=None, show=1):
    """ShellExecuteEx; bildirim gerektiren (requireAdministrator) kaldiricilar icin UAC'yi Windows gosterir.
    Donus: surec tutamaci (int) veya None."""
    if not IS_WIN:
        raise OSError('Yalnızca Windows')
    sei = _SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = 0x00000040 | 0x00000400  # SEE_MASK_NOCLOSEPROCESS | SEE_MASK_FLAG_NO_UI
    sei.lpVerb = verb
    sei.lpFile = exe
    sei.lpParameters = params or None
    sei.lpDirectory = cwd
    sei.nShow = show
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        err = ctypes.GetLastError()
        if err == 1223:
            raise OSError('Kullanıcı UAC onayını iptal etti')
        raise OSError('Başlatılamadı (Win32 hata %d): %s' % (err, exe))
    return sei.hProcess


def wait_handle(handle, should_stop=lambda: False):
    """Tutamac kapanana kadar 0.5 sn araliklarla bekler; cikis kodunu dondurur."""
    if not handle:
        return 0
    k32 = ctypes.windll.kernel32
    try:
        while k32.WaitForSingleObject(handle, 500) == 0x102:  # WAIT_TIMEOUT
            if should_stop():
                return -1
        code = ctypes.c_ulong()
        k32.GetExitCodeProcess(handle, ctypes.byref(code))
        return int(code.value)
    finally:
        k32.CloseHandle(handle)


# NSIS (Au_.exe/Un_A.exe) ve Inno Setup (_iu14D2N.tmp) kaldiricilari kendini TEMP'e kopyalayip asil sureci bitirir.
_UNINSTALL_HELPERS = re.compile(r'^(au_|un_a|un_b|_iu14d2n|_unins|unins\d{3}|uninstall|uninst)', re.I)


def running_uninstall_helpers():
    if not IS_WIN:
        return []
    try:
        r = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, creationflags=CREATIONFLAGS, timeout=10)
    except Exception:
        return []
    names = []
    for line in r.stdout.splitlines():
        img = line.split('","', 1)[0].strip('"')
        if _UNINSTALL_HELPERS.match(img):
            names.append(img)
    return names


# --------------------------------------------------------------------------- SDIO betikleri (resmi Reference Manual komutlari)
SDIO_CATEGORIES = [('missing', 'Eksik sürücüler (aygıtın hiç sürücüsü yok)'), ('newer', 'Daha yeni sürüm'),
                   ('better', 'Daha iyi eşleşme'), ('current', 'Aynı sürüm (yeniden kur)'), ('older', 'Daha eski sürüm'), ('worse', 'Daha kötü eşleşme')]
SDIO_DEFAULT = {'missing', 'newer', 'better'}
SDIO_PACK_FILTERS = [('', 'Tüm paketler'), ('lan', 'Ağ (LAN)'), ('wlan', 'Kablosuz (WLAN)'), ('chipset', 'Yonga seti'), ('sound', 'Ses'),
                     ('video', 'Ekran kartı'), ('bluetooth', 'Bluetooth'), ('touchpad', 'Touchpad'), ('cardreader', 'Kart okuyucu'), ('misc', 'Diğer')]


def sdio_dirs(root=SDIO_ROOT):
    root = pathlib.Path(root)
    return {'root': root, 'logs': root / 'logs', 'drivers': root / 'drivers', 'indexes': root / 'indexes', 'extract': root / 'extract'}


def _sdio_path_ok(p):
    return ' ' not in str(p)


def sdio_script(mode, categories=None, packs=None, root=SDIO_ROOT, update_db=True):
    """mode: 'scan' (indirme yok, kurulum yok), 'install' (secili kategoriler).

    Komutlar SDIO Reference Manual 'Scripting' bolumunden: logdir, drpdir, indexdir, extractdir, logging, verbose,
    enableinstall, checkupdates, get indexes, init, writedevicelist, snapshot, restorepoint, select, install, onerror, goto, end, echo.
    """
    d = sdio_dirs(root)
    for k in ('logs', 'drivers', 'indexes', 'extract'):
        if not _sdio_path_ok(d[k]):
            raise ValueError('SDIO çalışma klasörü boşluk içeremez: %s' % d[k])
    cats = [c for c, _ in SDIO_CATEGORIES if c in (SDIO_DEFAULT if categories is None else categories)]
    if mode == 'install' and not cats:
        raise ValueError('En az bir sürücü kategorisi seçin')
    L = ['# AGFO System Care %s - otomatik uretilen SDIO betigi (%s)' % (VERSION, mode),
         'logdir %s' % d['logs'], 'drpdir %s' % d['drivers'], 'indexdir %s' % d['indexes'], 'extractdir %s' % d['extract'],
         'logging on', 'verbose 384', 'enableinstall %s' % ('on' if mode == 'install' else 'off')]
    if update_db:
        L += ['echo AGFO: surucu veritabani (indeksler) guncelleniyor', 'checkupdates', 'onerror goto offline',
              'get indexes', 'onerror goto offline']
    L += [':offline', 'echo AGFO: aygitlar taraniyor', 'init', 'writedevicelist %s' % (d['logs'] / 'agfo-devices.txt'), 'snapshot']
    if mode == 'scan':
        L += ['select %s' % ' '.join(cats or sorted(SDIO_DEFAULT)), 'echo AGFO: tarama tamamlandi (kurulum yapilmadi)', 'end']
    else:
        sel = 'select %s' % ' '.join(cats)
        fl = [p for p in (packs or []) if p]
        if fl:
            sel += ' ' + ' '.join(fl)
        L += ['restorepoint AGFO System Care - SDIO surucu kurulumu oncesi', sel, 'onerror goto nothing',
              'echo AGFO: secili suruculer kuruluyor (gerekli paketler indirilir)', 'install', 'onerror goto failed',
              'echo AGFO: kurulum tamamlandi', 'end', ':nothing', 'echo AGFO: secime uyan surucu yok', 'end',
              ':failed', 'echo AGFO: kurulum hatayla bitti; gunluge bakin', 'end']
    return '\n'.join(L) + '\n'


def write_sdio_script(mode, categories=None, packs=None, update_db=True):
    d = sdio_dirs()
    for k in ('logs', 'drivers', 'indexes', 'extract'):
        d[k].mkdir(parents=True, exist_ok=True)
    path = d['root'] / ('agfo-%s.txt' % mode)
    path.write_text(sdio_script(mode, categories, packs, update_db=update_db), encoding='ascii')
    return path


def newest_file(directory, since=0.0, patterns=('*.txt', '*.log')):
    best = None
    for pat in patterns:
        for p in pathlib.Path(directory).glob(pat):
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if m >= since and (best is None or m > best[0]):
                best = (m, p)
    return best[1] if best else None


# --------------------------------------------------------------------------- Surucu Merkezi (SDIO tarzi aygit -> aday surucu gorunumu)
# Veri: Win32_PnPEntity (aygit + HardwareID/CompatibleID + sorun kodu) + Win32_PnPSignedDriver (mevcut surucu)
# + Windows Update surucu katalogu (IWindowsDriverUpdate.DriverHardwareID ile eslenir).
PROBLEM_CODES = {
    1: 'Yapılandırma hatalı', 3: 'Sürücü bozuk veya bellek yetersiz', 10: 'Aygıt başlatılamıyor', 12: 'Yeterli kaynak yok',
    14: 'Yeniden başlatma gerekli', 18: 'Sürücü yeniden yüklenmeli', 19: 'Kayıt defteri bilgisi bozuk', 21: 'Windows aygıtı kaldırıyor',
    22: 'Aygıt devre dışı', 24: 'Aygıt yok veya düzgün çalışmıyor', 28: 'Sürücü yüklü değil', 29: 'Aygıt donanım yazılımında kapalı',
    31: 'Sürücü yüklenemedi', 32: 'Sürücü hizmeti devre dışı', 37: 'Sürücü başlatılamadı', 39: 'Sürücü bozuk veya eksik',
    41: 'Sürücü yüklendi ama donanım bulunamadı', 43: 'Aygıt sorun bildirdi ve durduruldu', 45: 'Aygıt şu an bağlı değil',
    48: 'Sürücü uyumsuzluk nedeniyle engellendi', 52: 'Sürücü imzası doğrulanamadı',
}
INFO_CODES = {22, 45}          # sorun degil, bilgi
MISSING_CODES = {1, 18, 28, 31, 39}  # SDIO'daki "eksik surucu" karsiligi
DRV_STATUS = {
    'missing': ('Eksik sürücü — kurulması önerilir', 'st_missing', True),
    'newer': ('Daha yeni sürüm', 'st_new', True),
    'current': ('Aynı sürüm (kurulu)', 'st_ok', False),
    'older': ('Daha eski sürüm', 'st_old', False),
    'unknown': ('Karşılaştırılamadı', 'st_warn', False),
    'worse': ('Daha zayıf eşleşme (genel uyumlu sürücü)', 'st_old', False),
}


def parse_version(text):
    m = re.search(r'(\d+(?:\.\d+){1,4})\s*$', (text or '').strip())
    return m.group(1) if m else ''


def _vt(v):
    return tuple(int(x) for x in v.split('.')) if v and re.fullmatch(r'\d+(?:\.\d+)*', v) else None


def compare_driver(cur_ver, cur_date, new_ver, new_date):
    """'newer' | 'current' | 'older' | 'unknown' — once surum, yoksa tarih karsilastirilir (SDIO da surum+tarih kullanir)."""
    a, b = _vt(cur_ver), _vt(new_ver)
    if a and b:
        n = max(len(a), len(b))
        a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
        return 'newer' if b > a else ('current' if b == a else 'older')
    if cur_date and new_date:
        return 'newer' if new_date > cur_date else ('current' if new_date == cur_date else 'older')
    return 'unknown'


def device_state(dev):
    code = int(dev.get('code') or 0)
    if code in MISSING_CODES or (not dev.get('ver') and code not in INFO_CODES and code != 0):
        return 'missing'
    if code and code not in INFO_CODES:
        return 'problem'
    return 'ok'


def build_driver_view(devs, wus):
    """-> (rows, unmatched, stats). rows: [{'dev':..., 'state':..., 'cands':[{'wu':..., 'status':..., 'ver':...}], 'best':status|None}]"""
    index = {}
    for i, d in enumerate(devs):
        for rank, key in ((0, 'hwids'), (1, 'compat')):
            for h in d.get(key) or []:
                index.setdefault(h.upper(), []).append((rank, i))
    cands = {i: [] for i in range(len(devs))}
    unmatched = []
    for w in wus:
        hw = (w.get('hwid') or '').upper()
        hits = sorted(index.get(hw, [])) if hw else []
        ver = parse_version(w.get('title', ''))
        if not hits:
            unmatched.append({'wu': w, 'ver': ver, 'status': 'unknown'})
            continue
        best_rank = hits[0][0]
        seen = set()
        for rank, i in hits:
            if rank != best_rank or i in seen:
                continue
            seen.add(i)
            d = devs[i]
            st = 'missing' if device_state(d) == 'missing' else compare_driver(d.get('ver', ''), d.get('date', ''), ver, w.get('date', ''))
            cands[i].append({'wu': w, 'ver': ver, 'status': st, 'match': 'HWID' if rank == 0 else 'Uyumlu kimlik'})
    order = {'missing': 0, 'newer': 1, 'unknown': 2, 'current': 3, 'older': 4, 'worse': 5}
    rows = []
    for i, d in enumerate(devs):
        # SDIO mantigi: aygitin kendi HWID'siyle eslesen aday varken yalnizca uyumlu kimlikle eslesen genel surucu 'daha zayif eslesme'dir.
        if any(c['match'] == 'HWID' for c in cands[i]):
            for c in cands[i]:
                if c['match'] != 'HWID':
                    c['status'] = 'worse'
        cs = sorted(cands[i], key=lambda c: (order[c['status']], c['wu'].get('date', '')), reverse=False)
        st = device_state(d)
        best = cs[0]['status'] if cs else None
        rows.append({'dev': d, 'state': st, 'cands': cs, 'best': best})
    rank_row = lambda r: (0 if r['best'] in ('missing', 'newer') else (1 if r['state'] in ('missing', 'problem') else 2), (r['dev'].get('cls') or '~').lower(), (r['dev'].get('name') or '').lower())
    rows.sort(key=rank_row)
    stats = {'devices': len(devs), 'updates': sum(1 for r in rows if r['best'] in ('missing', 'newer')),
             'missing': sum(1 for r in rows if r['state'] == 'missing'), 'problem': sum(1 for r in rows if r['state'] == 'problem'),
             'candidates': sum(len(r['cands']) for r in rows) + len(unmatched)}
    return rows, unmatched, stats


def device_label(row):
    d, st, best = row['dev'], row['state'], row['best']
    if best == 'missing' or (st == 'missing' and row['cands']):
        return 'Sürücü eksik — aday var', 'st_missing'
    if best == 'newer':
        return 'Güncelleme var', 'st_new'
    if st == 'missing':
        return 'Sürücü eksik — aday bulunamadı', 'st_problem'
    if st == 'problem':
        return 'Sorunlu: ' + PROBLEM_CODES.get(int(d.get('code') or 0), 'kod %s' % d.get('code')), 'st_problem'
    if int(d.get('code') or 0) in INFO_CODES:
        return PROBLEM_CODES.get(int(d['code']), ''), 'st_old'
    return 'Güncel', 'st_ok'


# --------------------------------------------------------------------------- Bloatware (Store/AppX + masaustu)
# Kategori: 'rec' = onerilen (varsayilan isaretli), 'caution' = kullaniliyor olabilir (isaretsiz),
# 'protected' = sistem/calisma zamani/surucu yardimcisi (secilemez; PowerShell tarafi da reddeder).
BLOAT_APPX = [
    # --- korunan (once eslesir)
    (r'^Microsoft\.(WindowsStore|StorePurchaseApp|DesktopAppInstaller|Winget\.Source)$', 'Microsoft Store / WinGet', 'protected', 'Uygulama kurulumu ve güncellemeleri için gerekli'),
    (r'^Microsoft\.(VCLibs|UI\.Xaml|NET\.|WindowsAppRuntime|Services\.Store\.Engagement|WidgetsPlatformRuntime)', 'Çalışma zamanı bileşeni', 'protected', 'Diğer uygulamalar buna bağlı'),
    (r'^Microsoft\.(SecHealthUI|AAD\.BrokerPlugin|AccountsControl|Windows\.(?!Photos$|DevHome$)|LanguageExperiencePack|MicrosoftEdge|ApplicationCompatibilityEnhancements|OneDriveSync)', 'Windows sistem bileşeni', 'protected', 'Windows işlevi; kaldırılmamalı'),
    (r'^(MicrosoftWindows\.|windows\.|NcsiUwpApp|Windows\.)', 'Windows sistem bileşeni', 'protected', 'Windows işlevi; kaldırılmamalı'),
    (r'^Microsoft\.(HEIFImage|HEVCVideo|VP9Video|WebMedia|WebpImage|RawImage|AV1Video|MPEG2Video|AVCEncoderVideo)Extension', 'Medya codec uzantısı', 'protected', 'Fotoğraf/video açmak için gerekli'),
    (r'^Microsoft\.(WindowsTerminal|WindowsNotepad|WindowsCalculator)$', 'Temel Windows aracı', 'protected', 'Terminal / Not Defteri / Hesap Makinesi'),
    (r'^(AppUp\.IntelGraphicsExperience|RealtekSemiconductorCorp\.|NVIDIACorp\.|AdvancedMicroDevicesInc|DolbyLaboratories\.|WavesAudio\.|SynapticsIncorporated\.|ELANMicroelectronics|IntelCorp\.|Intel\.)', 'Donanım/sürücü yardımcısı', 'protected', 'Sürücü ayar paneli; kaldırılırsa ses/ekran ayarları kaybolabilir'),
    # --- onerilen
    (r'^king\.com\.', 'King oyunları (Candy Crush vb.)', 'rec', 'Ön yüklü reklam oyunu'),
    (r'^Microsoft\.BingNews$', 'Microsoft Haberler', 'rec', ''),
    (r'^Microsoft\.BingSearch$', 'Bing Arama', 'rec', ''),
    (r'^Microsoft\.GetHelp$', 'Yardım Alın', 'rec', ''),
    (r'^Microsoft\.Getstarted$', 'İpuçları', 'rec', ''),
    (r'^Microsoft\.MicrosoftSolitaireCollection$', 'Solitaire Collection', 'rec', ''),
    (r'^Microsoft\.MicrosoftOfficeHub$', 'Microsoft 365 (Office) tanıtım uygulaması', 'rec', 'Office’in kendisi değildir'),
    (r'^Microsoft\.WindowsFeedbackHub$', 'Geri Bildirim Merkezi', 'rec', ''),
    (r'^Microsoft\.WindowsMaps$', 'Haritalar', 'rec', ''),
    (r'^Microsoft\.(Microsoft3DViewer|Print3D|MixedReality\.Portal)$', '3D Görüntüleyici / Karma Gerçeklik', 'rec', ''),
    (r'^Microsoft\.(SkypeApp|Messaging|OneConnect|Wallet)$', 'Skype / Mesajlaşma / eski uygulama', 'rec', ''),
    (r'^Microsoft\.549981C3F5F10$', 'Cortana', 'rec', ''),
    (r'^Clipchamp\.Clipchamp$', 'Clipchamp video düzenleyici', 'rec', ''),
    (r'^MicrosoftCorporationII\.MicrosoftFamily$', 'Microsoft Family Safety', 'rec', ''),
    (r'^Microsoft\.ZuneVideo$', 'Filmler ve TV', 'rec', ''),
    (r'^(Microsoft\.People|Microsoft\.windowscommunicationsapps)$', 'Kişiler / eski Posta ve Takvim', 'rec', 'Yeni Outlook kullanılıyorsa gereksiz'),
    # --- dikkat
    (r'^Microsoft\.BingWeather$', 'Hava Durumu', 'caution', ''),
    (r'^Microsoft\.ZuneMusic$', 'Medya Oynatıcı', 'caution', 'Windows 11’de varsayılan müzik/video oynatıcı'),
    (r'^Microsoft\.(GamingApp|XboxApp)$', 'Xbox uygulaması', 'caution', 'PC Game Pass kullananlar için gerekli'),
    (r'^Microsoft\.(XboxGamingOverlay|XboxGameOverlay|XboxSpeechToTextOverlay)$', 'Xbox Game Bar', 'caution', 'Ekran kaydı (Win+G) bunu kullanır'),
    (r'^Microsoft\.(Xbox\.TCUI|XboxIdentityProvider)$', 'Xbox kimlik bileşeni', 'caution', 'Kaldırılırsa bazı oyunlarda oturum açılamaz'),
    (r'^Microsoft\.YourPhone$', 'Telefon Bağlantısı', 'caution', ''),
    (r'^(MicrosoftTeams|MSTeams)$', 'Microsoft Teams', 'caution', 'İş için kullanılıyor olabilir'),
    (r'^Microsoft\.OutlookForWindows$', 'Yeni Outlook', 'caution', ''),
    (r'^Microsoft\.(Todos|PowerAutomateDesktop|MicrosoftStickyNotes|MicrosoftJournal|Office\.OneNote)$', 'Verimlilik uygulaması', 'caution', 'To Do / Power Automate / Yapışkan Notlar / OneNote'),
    (r'^Microsoft\.(WindowsAlarms|WindowsSoundRecorder|WindowsCamera|ScreenSketch|Paint|Windows\.Photos|MSPaint)$', 'Windows yardımcı uygulaması', 'caution', 'Saat / Ses Kaydedici / Kamera / Ekran Alıntısı / Paint / Fotoğraflar'),
    (r'^Microsoft\.(Windows\.DevHome|DevHome)$', 'Dev Home', 'caution', ''),
    (r'^(SpotifyAB\.SpotifyMusic|Disney\.|AmazonVideo\.PrimeVideo|4DF9E0F8\.Netflix|.*\.Netflix|Facebook\.|BytedancePte\.Ltd\.TikTok|.*Instagram|.*LinkedIn)', 'Ön yüklü üçüncü taraf uygulama', 'caution', 'Kullanıyorsanız işaretlemeyin'),
]
BLOAT_WIN32 = [
    (r'^McAfee WebAdvisor', 'McAfee WebAdvisor', 'rec', 'Tarayıcı eklentisi; genelde istemeden gelir'),
    (r'^McAfee', 'McAfee deneme sürümü', 'rec', 'Windows Güvenlik zaten koruma sağlar; abonelik varsa işaretlemeyin'),
    (r'^WildTangent', 'WildTangent oyunları', 'rec', ''),
    (r'^Booking\.com', 'Booking.com kısayolu', 'rec', ''),
    (r'^Norton (Security|360|AntiVirus|Internet Security)', 'Norton deneme sürümü', 'caution', 'Abonelik varsa işaretlemeyin'),
    (r'^(ExpressVPN|Avast Free|AVG (AntiVirus|Internet))', 'Ön yüklü güvenlik/VPN', 'caution', ''),
    (r'^CyberLink (PowerDVD|PowerDirector|YouCam|Power2Go|PhotoDirector)', 'CyberLink OEM yazılımı', 'caution', ''),
    (r'^(HP (JumpStart|Documentation|Wolf|Sure (Click|Sense))|HP Support Assistant)', 'HP OEM yazılımı', 'caution', 'Sürücü güncellemesi için HP Support Assistant kullanılıyor olabilir'),
    (r'^(Dell (SupportAssist|Digital Delivery|Customer Connect|Update))', 'Dell OEM yazılımı', 'caution', ''),
    (r'^(Lenovo (Now|Vantage Service|Welcome)|Lenovo Hotkeys)', 'Lenovo OEM yazılımı', 'caution', ''),
    (r'^(Microsoft 365|Microsoft OneNote) - [a-z]{2}-[a-z]{2}$', 'Ön yüklü Microsoft 365 dil paketi / deneme', 'caution', 'Kullandığınız Office ise işaretlemeyin'),
]
BLOAT_CAT = {'rec': 'Önerilen — güvenle kaldırılabilir', 'caution': 'Dikkat — kullanıyor olabilirsiniz', 'other': 'Diğer Store uygulamaları',
             'protected': 'Korunan — sistem bileşeni (kaldırılmaz)'}


def classify_appx(name):
    for rx, label, cat, note in BLOAT_APPX:
        if re.search(rx, name or ''):
            return cat, label, note
    return 'other', '', ''


def classify_win32(prog_name):
    for rx, label, cat, note in BLOAT_WIN32:
        if re.search(rx, prog_name or '', re.I):
            return cat, label, note
    return None


def appx_publisher(pub):
    m = re.search(r'(?:^|,\s*)O=("?)([^",]+)\1', pub or '') or re.search(r'(?:^|,\s*)CN=("?)([^",]+)\1', pub or '')
    return m.group(2).strip() if m else (pub or '')


def build_bloat_view(appx, programs=()):
    """-> {'rec': [...], 'caution': [...], 'other': [...], 'protected': [...]} her oge: dict(kind, name, label, note, ...)"""
    groups = {k: [] for k in ('rec', 'caution', 'other', 'protected')}
    for a in appx:
        cat, label, note = classify_appx(a.get('name', ''))
        if a.get('nonremovable') or (a.get('sig') == 'System' and cat != 'rec'):
            cat, note = 'protected', note or 'Windows bu paketi kaldırılamaz olarak işaretliyor'
        groups[cat].append(dict(a, kind='appx', label=label or a.get('name', ''), note=note, cat=cat, pub=appx_publisher(a.get('publisher', ''))))
    for p in programs:
        hit = classify_win32(p.get('name', ''))
        if hit and not p.get('orphan'):
            cat, label, note = hit
            groups[cat].append({'kind': 'win32', 'name': p['name'], 'label': p['name'], 'note': note or label, 'cat': cat, 'pub': p.get('publisher', ''),
                                'ver': p.get('version', ''), 'prog': p})
    for g in groups.values():
        g.sort(key=lambda x: (x['kind'] != 'appx', x['label'].lower()))
    return groups


# --------------------------------------------------------------------------- Uygulama ici guncelleme (paket yukleme)
# Akis: inspect_update (ZIP'i acmadan denetle) -> stage_update (yalnizca calisma dosyalarini gecici klasore ac)
# -> preflight (Python derleme + PowerShell sozdizimi) -> apply_update (yedekle, kopyala; hata olursa otomatik geri al)
# -> yeniden baslat. rollback_update ile yedeklerden geri donulur.
UPDATE_REQUIRED = ('app.pyw', 'care_core.py', 'care_tasks.ps1')
UPDATE_MAX_BYTES = 50 * 1024 * 1024
UPDATE_KEEP_BACKUPS = 3
UPDATE_APP_ID = 'agfo-system-care'
UPDATE_LOG = LOG_DIR / 'updates.log'


def _is_runtime_file(rel):
    """Kurulum klasorune girecek dosyalar: kok dizindeki .py/.pyw/.ps1/.md/.txt ve assets/ altindakiler.
    tests/, packaging/, .cmd, regresyon ve bildirim dosyalari kuruluma kopyalanmaz."""
    rel = rel.replace('\\', '/')
    parts = rel.split('/')
    if any(p in ('', '.', '..') for p in parts) or '__pycache__' in parts:
        return False
    if parts[0] == 'assets' and len(parts) >= 2:
        return True
    if len(parts) != 1:
        return False
    name = parts[0].lower()
    if name in ('manifest.json', 'regression.json', 'regression-report.json'):
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
        m = re.search(r"^VERSION = '([\d.]+)'", (root / 'care_core.py').read_text(encoding='utf-8'), re.M)
        version = m.group(1) if m else ''
    return {'app': UPDATE_APP_ID, 'version': version, 'files': files}


def inspect_update(zip_path, current_version):
    """ZIP'i diske acmadan denetler. Donus: {'ok', 'version', 'prefix', 'files': {rel: arcname}, 'manifest', 'downgrade', 'same', 'errors', 'warnings'}"""
    import hashlib
    import zipfile
    info = {'ok': False, 'version': '', 'prefix': '', 'files': {}, 'manifest': None, 'downgrade': False, 'same': False, 'errors': [], 'warnings': []}
    err, warn = info['errors'].append, info['warnings'].append
    try:
        if os.path.getsize(zip_path) > UPDATE_MAX_BYTES:
            err('Paket çok büyük (sınır %d MB).' % (UPDATE_MAX_BYTES // 1048576)); return info
        z = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as e:
        err('ZIP açılamadı: %s' % e); return info
    with z:
        names = [n for n in z.namelist() if not n.endswith('/')]
        for n in names:
            norm = n.replace('\\', '/')
            if norm.startswith('/') or re.match(r'^[A-Za-z]:', norm) or '..' in norm.split('/'):
                err('Güvensiz dosya yolu reddedildi: %s' % n); return info
        total = sum(i.file_size for i in z.infolist())
        if total > UPDATE_MAX_BYTES * 4:
            err('Açılmış boyut çok büyük (%d MB).' % (total // 1048576)); return info
        cands = sorted((n for n in names if n.replace('\\', '/').split('/')[-1] == 'app.pyw'), key=lambda n: n.count('/'))
        if not cands:
            err('Pakette app.pyw yok — bu bir AGFO System Care güncelleme paketi değil.'); return info
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
        core_src = z.read(info['files']['care_core.py']).decode('utf-8', 'replace')
        m = re.search(r"^VERSION = '([\d.]+)'", core_src, re.M)
        if not m or 'AGFO System Care' not in core_src:
            err('care_core.py içinde AGFO System Care sürüm bilgisi bulunamadı.'); return info
        info['version'] = m.group(1)
        cv, nv = version_tuple(current_version), version_tuple(info['version'])
        info['downgrade'], info['same'] = nv < cv, nv == cv
        man_name = prefix + 'MANIFEST.json'
        man_arc = next((n for n in names if n.replace('\\', '/') == man_name), None)
        if man_arc:
            try:
                man = json.loads(z.read(man_arc).decode('utf-8'))
            except ValueError:
                err('MANIFEST.json okunamadı.'); return info
            if man.get('app') != UPDATE_APP_ID:
                err('MANIFEST başka bir uygulamaya ait: %s' % man.get('app')); return info
            if man.get('version') != info['version']:
                err('MANIFEST sürümü (%s) ile care_core.py sürümü (%s) uyuşmuyor.' % (man.get('version'), info['version'])); return info
            mf = man.get('files') or {}
            for rel, arc in info['files'].items():
                if rel not in mf:
                    err('MANIFEST\'te olmayan dosya: %s' % rel); return info
                if hashlib.sha256(z.read(arc)).hexdigest() != str(mf[rel]).lower():
                    err('SHA-256 uyuşmuyor (paket bozuk ya da değiştirilmiş): %s' % rel); return info
            gone = [r for r in mf if r not in info['files']]
            if gone:
                err('MANIFEST\'teki dosyalar pakette yok: %s' % ', '.join(gone[:5])); return info
            info['manifest'] = True
        else:
            info['manifest'] = False
            warn('Pakette MANIFEST.json yok: dosya bütünlüğü doğrulanamıyor (eski paket biçimi).')
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
                raise OSError('Güvensiz yol: %s' % rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(arc))
    return stage


def preflight(stage_dir, ps_parser=True):
    """Yeni surumu kurmadan once denetler: tum .py/.pyw dosyalari derlenir, .ps1 dosyalari PowerShell AST ile ayristirilir.
    Donus: [(baslik, durum 'ok'|'fail'|'skip', ayrinti)]"""
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
            checks.append(('PowerShell sözdizimi: ' + p.name, 'skip', 'PowerShell bulunamadı'))
            continue
        script = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e); "
                  "if($e.Count){ $e | ForEach-Object { $_.Message }; exit 3 } else { 'OK' }") % str(p).replace("'", "''")
        try:
            r = subprocess.run([exe, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True, text=True,
                               timeout=60, creationflags=CREATIONFLAGS, stdin=subprocess.DEVNULL)
            ok = r.returncode == 0 and 'OK' in r.stdout
            checks.append(('PowerShell sözdizimi: ' + p.name, 'ok' if ok else 'fail', '' if ok else (r.stdout + r.stderr).strip()[:300]))
        except Exception as e:
            checks.append(('PowerShell sözdizimi: ' + p.name, 'skip', str(e)))
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
    """Mevcut calisma dosyalarini yedekler, yeni dosyalari atomik olarak yerlestirir. Herhangi bir adim basarisiz olursa
    yedekten otomatik geri doner ve hatayi yeniden firlatir. Donus: yedek klasoru."""
    import shutil
    install, stage = pathlib.Path(install_dir), pathlib.Path(stage_dir)
    probe = install / '.agfo-write-test'
    try:
        probe.write_text('x'); probe.unlink()
    except OSError as e:
        raise OSError('Kurulum klasörüne yazılamıyor (%s). Uygulamayı yönetici olarak açın.' % e)
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
        raise OSError('Yedek klasörü oluşturulamadı')
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
        # yeni surumde artik olmayan eski calisma dosyalari (or. kaldirilan modul) temizlenir; yedekte duruyor
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
        _log_update('BAŞARISIZ %s -> %s, geri alındı: %s' % (old_version, new_version, e))
        raise OSError('Güncelleme uygulanamadı, önceki sürüm geri yüklendi: %s' % e)
    for b in list_backups(backup_root)[UPDATE_KEEP_BACKUPS:]:
        shutil.rmtree(b['path'], ignore_errors=True)
    _log_update('GÜNCELLENDİ %s -> %s (yedek: %s)' % (old_version, new_version, bdir))
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
    """Secilen yedege doner (mevcut surum de once yedeklenir, boylece geri donus da geri alinabilir)."""
    b = pathlib.Path(backup_path)
    meta = json.loads((b / 'backup.json').read_text(encoding='utf-8'))
    target = meta.get('version', '')
    stage = b.parent / ('_rollback_stage')
    import shutil
    shutil.rmtree(stage, ignore_errors=True)
    _copy_tree_files(b, meta.get('files', []), stage)
    try:
        bdir = apply_update(stage, install_dir, b.parent, current_version, target)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    _log_update('GERİ DÖNÜLDÜ %s -> %s' % (current_version, target))
    return target, bdir


def update_history(limit=10):
    try:
        lines = UPDATE_LOG.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    return lines[-limit:]


# --------------------------------------------------------------------------- GitHub surum denetimi
GH_PREFIX = 'system-care-v'
GH_ASSET = r'AGFO-System-Care-v\d+(?:\.\d+)+\.zip'
GH_STATE = APP_DATA_DIR / 'github-update.json'
GH_DOWNLOAD_DIR = APP_DATA_DIR / 'update-download'


# --------------------------------------------------------------------------- Aygit temizligi (bagli olmayan / hayalet aygitlar)
# DeviceCleanup (Uwe Sieber) ile ayni olcutler: yalnizca su an bagli olmayan aygitlar; 'son gorulme' = son baglanma /
# ayrilma tarihi veya Enum kayit anahtarinin son yazma zamani. Kaldirilan aygit yeniden takilirsa Windows onu yeni aygit
# olarak tanir. Uygulama kendi kodunu kullanir; ucuncu taraf arac indirmez.
PHANTOM_CAUTION_CLASSES = {'softwaredevice', 'softwarecomponent', 'system', 'computer', 'processor', 'firmware', 'hdc', 'scsiadapter'}
PHANTOM_DEFAULT_DAYS = 30


def phantom_last_seen(d):
    vals = [v for v in (d.get('arrival'), d.get('removal'), d.get('regwrite')) if v]
    return max(vals) if vals else ''


def phantom_is_caution(d):
    iid = (d.get('id') or '').upper()
    return (d.get('cls') or '').lower() in PHANTOM_CAUTION_CLASSES or iid.startswith(('ROOT\\', 'SWD\\', 'HTREE\\', 'ACPI_HAL\\'))


def build_phantom_view(devs, today=None):
    """-> (gruplar {sinif: [aygit...]}, istatistik). Her aygita 'seen', 'age' (gun ya da None), 'caution', 'default' eklenir."""
    import datetime as _dt
    today = today or _dt.date.today()
    groups = {}
    stats = {'total': 0, 'old30': 0, 'old365': 0, 'caution': 0}
    for d in devs:
        d = dict(d)
        d['seen'] = phantom_last_seen(d)
        age = None
        if d['seen']:
            try:
                age = max(0, (today - _dt.date.fromisoformat(d['seen'][:10])).days)   # saat sapmasi: gelecek tarih -> 0
            except ValueError:
                age = None
        d['age'] = age
        d['caution'] = phantom_is_caution(d)
        d['default'] = (not d['caution']) and age is not None and age >= PHANTOM_DEFAULT_DAYS
        groups.setdefault(d.get('cls') or 'Diğer', []).append(d)
        stats['total'] += 1
        stats['old30'] += 1 if (age is not None and age >= 30) else 0
        stats['old365'] += 1 if (age is not None and age >= 365) else 0
        stats['caution'] += 1 if d['caution'] else 0
    for g in groups.values():
        g.sort(key=lambda x: (x['seen'] or '0000', (x.get('name') or '').lower()))
    return dict(sorted(groups.items(), key=lambda kv: kv[0].lower())), stats
