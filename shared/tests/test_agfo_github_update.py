"""agfo_github_update birim testleri (ag gerektirmez).  python -I shared/tests/test_agfo_github_update.py <modul klasoru>"""
import hashlib
import io
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])))
import agfo_github_update as g  # noqa: E402

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


def rel(tag, assets=(), draft=False, pre=False, body='notlar'):
    return {'tag_name': tag, 'name': tag, 'draft': draft, 'prerelease': pre, 'body': body, 'html_url': 'https://github.com/x/' + tag,
            'published_at': '2026-10-17T20:00:00Z', 'assets': list(assets)}


def asset(name, data=b'', digest=True):
    a = {'name': name, 'browser_download_url': 'https://github.com/downtownck/agfo-windows-apps/releases/download/t/' + name, 'size': len(data)}
    if digest:
        a['digest'] = 'sha256:' + hashlib.sha256(data).hexdigest()
    return a


RELS = [rel('supertools-v1.7.0', [asset('AGFO-SuperTools-v1.7.0.update.zip', b'zip170')]),
        rel('supertools-v1.10.0', [asset('AGFO-SuperTools-v1.10.0.update.zip', b'zip1100')], draft=True),
        rel('supertools-v1.9.0', [asset('AGFO-SuperTools-v1.9.0.update.zip', b'zip190')], pre=True),
        rel('supertools-v1.8.1', [asset('AGFO-SuperTools-v1.8.1.update.zip', b'zip181'), asset('SHA256SUMS.txt', b'', digest=False)]),
        rel('system-care-v3.9.0', [asset('AGFO-System-Care-v3.9.0.zip', b'sc')]),
        rel('backupsync-v2.3.0', [asset('AGFO-BackupSync-Setup.exe', b'exe')]),
        rel('supertools-vX', []), {'junk': 1}]


@test
def tags_and_versions():
    assert g.parse_tag('supertools-v1.7.0', 'supertools-v') == '1.7.0'
    assert g.parse_tag('system-care-v3.4.0', 'supertools-v') is None and g.parse_tag('supertools-v1.7.0-rc', 'supertools-v') is None
    assert g.is_newer('1.10.0', '1.9.9') and not g.is_newer('1.7', '1.7.0') and g.is_newer('3.4.0', '3.3.0')


@test
def latest_filters():
    r = g.latest_release('supertools-v', RELS)
    assert r['version'] == '1.8.1' and r['tag'] == 'supertools-v1.8.1', r      # taslak 1.10 ve on surum 1.9 haric
    assert g.latest_release('supertools-v', RELS, include_prerelease=True)['version'] == '1.9.0'
    assert g.latest_release('system-care-v', RELS)['version'] == '3.9.0'
    assert g.latest_release('nothing-v', RELS) is None
    assert g.pick_asset(r, r'AGFO-SuperTools-v[\d.]+\.update\.zip')['name'] == 'AGFO-SuperTools-v1.8.1.update.zip'
    try:
        g.latest_release('x', {'message': 'Not Found'}); raise AssertionError
    except g.GHUpdateError:
        pass


@test
def sha_sources():
    r = g.latest_release('supertools-v', RELS)
    a = g.pick_asset(r, r'.*\.update\.zip')
    good = hashlib.sha256(b'zip181').hexdigest()
    assert g.expected_sha256(r, a, fetch=lambda u, **k: '%s  %s\n' % (good, a['name'])) == good
    try:
        g.expected_sha256(r, a, fetch=lambda u, **k: '%s  %s\n' % ('0' * 64, a['name'])); raise AssertionError
    except g.GHUpdateError as e:
        assert 'uyusmuyor' in str(e)
    a2 = dict(a, sha256=None)
    assert g.expected_sha256(r, a2, fetch=lambda u, **k: '%s *%s\n' % (good, a['name'])) == good        # yalniz SHA256SUMS
    r3 = dict(r, assets=[a2])
    try:
        g.expected_sha256(r3, a2); raise AssertionError                                                    # hic ozet yok -> kullanilmaz
    except g.GHUpdateError as e:
        assert 'dogrulanamayan' in str(e)


@test
def hosts():
    assert g.host_allowed('https://api.github.com/repos/x') and g.host_allowed('https://objects.githubusercontent.com/a')
    assert g.host_allowed('https://release-assets.githubusercontent.com/a')
    assert not g.host_allowed('http://github.com/x') and not g.host_allowed('https://evilgithub.com/x') and not g.host_allowed('https://github.com.evil.io/')


@test
def download():
    data = b'A' * 600000
    a = {'name': 'p.zip', 'url': 'https://github.com/x/p.zip', 'size': len(data)}

    class R(io.BytesIO):
        def __init__(self, b, n=None):
            super().__init__(b); self.headers = {'Content-Length': str(len(b) if n is None else n)}
        def __enter__(self): return self
        def __exit__(self, *x): return False
    old = g._open
    t = pathlib.Path(tempfile.mkdtemp())
    try:
        g._open = lambda url, **k: R(data)
        seen = []
        p = g.download_asset(a, t / 'p.zip', hashlib.sha256(data).hexdigest(), progress=lambda d, n: seen.append(d))
        assert p.read_bytes() == data and seen[-1] == len(data)
        for bad_sha, bad_size in (('0' * 64, None), (hashlib.sha256(data).hexdigest(), len(data) + 1)):
            aa = dict(a, size=bad_size or a['size'])
            try:
                g.download_asset(aa, t / 'q.zip', bad_sha); raise AssertionError
            except g.GHUpdateError:
                assert not (t / 'q.zip').exists() and not (t / 'q.zip.part').exists()
        g._open = lambda url, **k: R(b'', n=g.MAX_ASSET_BYTES + 1)
        try:
            g.download_asset(a, t / 'z.zip', 'x'); raise AssertionError
        except g.GHUpdateError as e:
            assert 'buyuk' in str(e) and not (t / 'z.zip.part').exists()
    finally:
        g._open = old
    try:
        g.fetch_json('https://example.com/x'); raise AssertionError
    except g.GHUpdateError as e:
        assert 'Izin verilmeyen' in str(e)


@test
def check_flow():
    t = pathlib.Path(tempfile.mkdtemp())
    sp = t / 'state.json'
    pat = r'AGFO-SuperTools-v[\d.]+\.update\.zip'
    r = g.check_for_update('supertools-v', '1.6.0', sp, pat, releases=RELS, now=1000)
    assert r['status'] == 'update' and r['version'] == '1.8.1' and r['asset']['name'].endswith('.update.zip')
    r2 = g.check_for_update('supertools-v', '1.6.0', sp, pat, releases=[], now=1000 + 60)      # sik denetim -> onbellek
    assert r2['status'] == 'update' and r2.get('cached')
    g.skip_version(sp, '1.8.1')
    assert g.check_for_update('supertools-v', '1.6.0', sp, pat, releases=[], now=1000 + 120)['status'] == 'throttled'
    assert g.check_for_update('supertools-v', '1.6.0', sp, pat, releases=RELS, now=1000 + g.CHECK_INTERVAL + 1)['status'] == 'skipped'
    assert g.check_for_update('supertools-v', '1.6.0', sp, pat, releases=RELS, force=True, now=99999)['status'] == 'update'   # elle denetim atlamayi yok sayar
    assert g.check_for_update('supertools-v', '1.8.1', sp, pat, releases=RELS, force=True)['status'] == 'current'
    assert g.check_for_update('nothing-v', '1', t / 's2.json', pat, releases=RELS, force=True)['status'] == 'none'
    assert g.check_for_update('system-care-v', '1', t / 's3.json', r'nomatch', releases=RELS, force=True)['status'] == 'error'
    old = g.fetch_json
    g.fetch_json = lambda *a, **k: (_ for _ in ()).throw(g.GHUpdateError('ag yok'))
    try:
        e = g.check_for_update('supertools-v', '1.6.0', t / 's4.json', pat, force=True)
        assert e['status'] == 'error' and 'ag yok' in e['message']
    finally:
        g.fetch_json = old


print('PASS github-update: %d test (%s)' % (len(PASSED), ', '.join(PASSED)))
