# -*- coding: utf-8 -*-
"""AGFO ortak GitHub surum denetleyicisi (yalnizca Python standart kutuphanesi).

Uc AGFO Windows uygulamasi (System Care, SuperTools, BackupSync) ayni depodaki
GitHub Releases kayitlarini, kendi etiket onekleriyle (or. 'supertools-v1.7.0') denetler.

Guvenlik:
- Yalnizca HTTPS ve izinli alan adlari (api.github.com, github.com, *.githubusercontent.com);
  yonlendirmeler de denetlenir.
- Indirilen dosya, GitHub'in sundugu SHA-256 ozeti (asset 'digest') ya da surume eklenen
  SHA256SUMS.txt ile dogrulanir; ozet yoksa dosya kullanilmaz.
- Bu, dosyanin yolda bozulmadigini ve surumdeki dosyayla ayni oldugunu kanitlar; guven
  koku GitHub hesabinin guvenligidir (kod imzasi degildir).
Bu modul hicbir zaman indirdigi dosyayi kendisi calistirmaz; uygulamanin mevcut, dogrulamali
guncelleme yoluna teslim eder.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import time

GITHUB_REPO = 'downtownck/agfo-windows-apps'
RELEASES_URL = 'https://api.github.com/repos/%s/releases?per_page=50'
ALLOWED_HOSTS = ('api.github.com', 'github.com', 'githubusercontent.com')
MAX_ASSET_BYTES = 300 * 1024 * 1024
CHECK_INTERVAL = 6 * 3600
MODULE_VERSION = '1.0.0'


class GHUpdateError(Exception):
    pass


# --------------------------------------------------------------------------- ag
def host_allowed(url):
    from urllib.parse import urlsplit
    u = urlsplit(url or '')
    if u.scheme != 'https' or not u.hostname:
        return False
    h = u.hostname.lower()
    return any(h == d or h.endswith('.' + d) for d in ALLOWED_HOSTS)


def _open(url, accept='application/vnd.github+json', user_agent='AGFO-Updater', timeout=30):
    import urllib.request

    class Guard(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not host_allowed(newurl):
                raise GHUpdateError('Izin verilmeyen yonlendirme engellendi: %s' % newurl)
            new = super().redirect_request(req, fp, code, msg, headers, newurl)
            return new
    if not host_allowed(url):
        raise GHUpdateError('Izin verilmeyen adres: %s' % url)
    req = urllib.request.Request(url, headers={'User-Agent': user_agent, 'Accept': accept,
                                               'X-GitHub-Api-Version': '2022-11-28'})
    return urllib.request.build_opener(Guard()).open(req, timeout=timeout)


def fetch_json(url, user_agent='AGFO-Updater'):
    try:
        with _open(url, user_agent=user_agent) as r:
            return json.loads(r.read(5 * 1024 * 1024).decode('utf-8'))
    except GHUpdateError:
        raise
    except Exception as e:
        code = getattr(e, 'code', None)
        if code == 403:
            raise GHUpdateError('GitHub istek sinirina takildi; biraz sonra tekrar deneyin.')
        if code == 404:
            raise GHUpdateError('Surum deposu bulunamadi veya ozel (%s).' % GITHUB_REPO)
        raise GHUpdateError('GitHub\'a ulasilamadi: %s' % e)


def fetch_text(url, user_agent='AGFO-Updater', limit=1024 * 1024):
    try:
        with _open(url, accept='application/octet-stream', user_agent=user_agent) as r:
            return r.read(limit).decode('utf-8', 'replace')
    except GHUpdateError:
        raise
    except Exception as e:
        raise GHUpdateError('Dosya okunamadi: %s' % e)


# --------------------------------------------------------------------------- surum
def version_tuple(v):
    parts = re.findall(r'\d+', v or '')
    return tuple(int(x) for x in parts) if parts else (0,)


def parse_tag(tag, prefix):
    """'supertools-v1.7.0' + 'supertools-v' -> '1.7.0'; eslesmezse None."""
    if not isinstance(tag, str) or not tag.startswith(prefix):
        return None
    v = tag[len(prefix):]
    return v if re.fullmatch(r'\d+(?:\.\d+){1,3}', v) else None


def is_newer(latest, current):
    a, b = version_tuple(latest), version_tuple(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def latest_release(prefix, releases=None, include_prerelease=False, user_agent='AGFO-Updater'):
    """Etiket onekine uyan en yuksek surumlu yayinlanmis surum (taslak haric). Yoksa None."""
    if releases is None:
        releases = fetch_json(RELEASES_URL % GITHUB_REPO, user_agent)
    if not isinstance(releases, list):
        raise GHUpdateError('GitHub yaniti beklenmeyen bicimde.')
    best = None
    for r in releases:
        if not isinstance(r, dict) or r.get('draft') or (r.get('prerelease') and not include_prerelease):
            continue
        v = parse_tag(r.get('tag_name'), prefix)
        if not v:
            continue
        if best is None or is_newer(v, best['version']):
            assets = []
            for a in r.get('assets') or []:
                if isinstance(a, dict) and a.get('name') and a.get('browser_download_url'):
                    dg = a.get('digest') or ''
                    assets.append({'name': a['name'], 'url': a['browser_download_url'], 'size': int(a.get('size') or 0),
                                   'sha256': dg.split(':', 1)[1].lower() if isinstance(dg, str) and dg.startswith('sha256:') else None})
            best = {'version': v, 'tag': r.get('tag_name'), 'name': r.get('name') or r.get('tag_name'),
                    'notes': (r.get('body') or '')[:4000], 'url': r.get('html_url') or '', 'published': (r.get('published_at') or '')[:10],
                    'assets': assets}
    return best


def pick_asset(release, pattern):
    rx = re.compile(pattern, re.I)
    for a in release.get('assets', []):
        if rx.fullmatch(a['name']):
            return a
    return None


def parse_sha256sums(text, name):
    for line in (text or '').splitlines():
        m = re.match(r'\s*([0-9a-fA-F]{64})\s+\*?(\S+)\s*$', line)
        if m and m.group(2) == name:
            return m.group(1).lower()
    return None


def expected_sha256(release, asset, fetch=fetch_text, user_agent='AGFO-Updater'):
    """Once GitHub'in asset ozeti; yoksa ayni surumdeki SHA256SUMS.txt. Ikisi varsa ve uyusmazsa hata."""
    sums_asset = pick_asset(release, r'SHA256SUMS(\.txt)?')
    from_sums = None
    if sums_asset:
        try:
            from_sums = parse_sha256sums(fetch(sums_asset['url'], user_agent=user_agent), asset['name'])
        except GHUpdateError:
            from_sums = None
    if asset.get('sha256') and from_sums and asset['sha256'] != from_sums:
        raise GHUpdateError('GitHub ozeti ile SHA256SUMS uyusmuyor: %s' % asset['name'])
    sha = asset.get('sha256') or from_sums
    if not sha:
        raise GHUpdateError('%s icin SHA-256 ozeti yok; dogrulanamayan dosya kullanilmaz.' % asset['name'])
    return sha


def download_asset(asset, dest, sha256, progress=None, should_stop=None, user_agent='AGFO-Updater'):
    """Dosyayi indirir, boyut sinirini ve SHA-256'yi denetler. Basarisizlikta yarim dosyayi siler."""
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + '.part')
    h = hashlib.sha256()
    done = 0
    try:
        with _open(asset['url'], accept='application/octet-stream', user_agent=user_agent, timeout=60) as r, open(tmp, 'wb') as f:
            total = int(r.headers.get('Content-Length') or asset.get('size') or 0)
            if total > MAX_ASSET_BYTES:
                raise GHUpdateError('Dosya cok buyuk (%d MB).' % (total // 1048576))
            last = 0.0
            while True:
                if should_stop and should_stop():
                    raise GHUpdateError('Indirme durduruldu.')
                chunk = r.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if done > MAX_ASSET_BYTES:
                    raise GHUpdateError('Indirme boyut sinirini asti.')
                if progress and time.time() - last > 0.25:
                    progress(done, total)
                    last = time.time()
        if progress:
            progress(done, total)
        if asset.get('size') and done != asset['size']:
            raise GHUpdateError('Boyut uyusmuyor (beklenen %d, gelen %d).' % (asset['size'], done))
        if h.hexdigest() != sha256.lower():
            raise GHUpdateError('SHA-256 dogrulamasi basarisiz; dosya silindi.')
        os.replace(tmp, dest)
        return dest
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------- durum (denetim sikligi, atlanan surum)
def load_state(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    try:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + '.new')
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(tmp, p)
    except OSError:
        pass


def check_for_update(prefix, current, state_path, asset_pattern, force=False, interval=CHECK_INTERVAL,
                     releases=None, user_agent='AGFO-Updater', now=None):
    """Hata firlatmaz. Donus: {'status': 'update'|'current'|'skipped'|'throttled'|'error'|'none', ...}
    'update' ise 'release' ve 'asset' alanlari doludur."""
    now = now or time.time()
    st = load_state(state_path)
    last = st.get('last_check')
    if not force and last is not None and now - float(last) < interval:
        cached = st.get('last_result') or {}
        if cached.get('status') == 'update' and is_newer(cached.get('version', '0'), current) and cached.get('version') != st.get('skip_version'):
            return dict(cached, status='update', cached=True)
        return {'status': 'throttled'}
    try:
        rel = latest_release(prefix, releases, user_agent=user_agent)
    except GHUpdateError as e:
        st['last_check'] = now
        st['last_error'] = str(e)
        save_state(state_path, st)
        return {'status': 'error', 'message': str(e)}
    st['last_check'] = now
    st.pop('last_error', None)
    if not rel:
        st['last_result'] = {'status': 'none'}
        save_state(state_path, st)
        return {'status': 'none'}
    if not is_newer(rel['version'], current):
        st['last_result'] = {'status': 'current', 'version': rel['version']}
        save_state(state_path, st)
        return {'status': 'current', 'version': rel['version']}
    asset = pick_asset(rel, asset_pattern)
    if not asset:
        res = {'status': 'error', 'message': 'Surum %s icinde beklenen paket dosyasi yok.' % rel['version']}
        save_state(state_path, st)
        return res
    res = {'status': 'update', 'version': rel['version'], 'release': rel, 'asset': asset}
    st['last_result'] = res
    save_state(state_path, st)
    if not force and rel['version'] == st.get('skip_version'):
        return {'status': 'skipped', 'version': rel['version']}
    return res


def skip_version(state_path, version):
    st = load_state(state_path)
    st['skip_version'] = version
    save_state(state_path, st)
