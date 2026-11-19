"""AGFO System Care - Ince ayarlar motoru (GUI'den bagimsiz, yalnizca standart kutuphane, test edilebilir).

Katalog (care_catalog.py) -> okuma plani (care_tasks.ps1 -Action tweak-read) -> durum tespiti ->
yazma plani (-Action tweak-write) -> PowerShell her islemden ONCEKI durumu '@@' kaydi olarak dondurur ->
gunluk (journal) -> geri alma plani. Geri alma, katalogdaki "varsayilan" degerlere degil, degisiklikten
onceki gercek degerlere doner (kayit degeri hic yoksa siler, yeni olusturulan anahtari bos kaldiysa temizler).

Islem turleri (yazma plani ogeleri):
  reg   {hive, path, name, kind, value (None: degeri sil), sub, delkey, prune}
  svc   {name, start: Automatic|AutomaticDelayed|Manual|Disabled}
  task  {path, enabled}
  power {guid}
  dns   {alias, guid, servers: [] (bos: DHCP)}
"""
import datetime
import json
import pathlib
import re

import care_catalog as cat

CATEGORIES = [('privacy', 'Gizlilik ve telemetri'), ('game', 'Oyun ve performans'), ('visual', 'Görünüm ve Gezgin'),
              ('win11', 'Windows 11 arayüzü'), ('net', 'Ağ'), ('system', 'Sistem ve Windows Update'), ('services', 'Hizmetler')]
CATEGORY_NAME = dict(CATEGORIES)
RISK_NAME = {'safe': 'Güvenli', 'caution': 'Dikkat', 'danger': 'Tehlikeli', 'blocked': 'Engelli'}
START_NAME = {'Automatic': 'Otomatik', 'AutomaticDelayed': 'Otomatik (gecikmeli)', 'Manual': 'El ile', 'Disabled': 'Devre dışı',
              'Boot': 'Önyükleme', 'System': 'Sistem', '': '—'}
SERVICE_GROUP = {'Telemetry': 'Telemetri', 'Privacy': 'Gizlilik', 'Xbox': 'Xbox', 'Printing': 'Yazdırma', 'Bluetooth': 'Bluetooth',
                 'Cloud': 'Bulut / eşitleme', 'Diagnostic': 'Tanılama', 'Network': 'Ağ', 'Security': 'Güvenlik', 'Other': 'Diğer'}
STATE_NAME = {'applied': 'Uygulanmış', 'partial': 'Kısmen', 'not': 'Uygulanmamış', 'unknown': 'Bilinmiyor', 'missing': 'Bu sistemde yok'}
ADMIN_HIVES = ('HKLM', 'HKU')
VALID_HIVES = ('HKCU', 'HKLM', 'HKU')
VALID_KINDS = ('DWord', 'QWord', 'String', 'ExpandString', 'MultiString', 'Binary')
VALID_STARTS = ('Automatic', 'AutomaticDelayed', 'Manual', 'Disabled')
BALANCED_PLAN = '381b4222-f694-41f0-9685-ff5bb260df2e'
JOURNAL_KEEP = 60

DNS_PRESETS = [
    ('dhcp', 'Otomatik (DHCP / modem)', []),
    ('cloudflare', 'Cloudflare 1.1.1.1', ['1.1.1.1', '1.0.0.1']),
    ('google', 'Google 8.8.8.8', ['8.8.8.8', '8.8.4.4']),
    ('quad9', 'Quad9 9.9.9.9 (zararlı alan adı engelli)', ['9.9.9.9', '149.112.112.112']),
    ('adguard', 'AdGuard 94.140.14.14 (reklam engelli)', ['94.140.14.14', '94.140.15.15']),
]
_IPV4 = re.compile(r'^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$')


# --------------------------------------------------------------------------- katalog
def tweak_by_id():
    return {t['id']: t for t in cat.TWEAKS}


def service_by_id():
    return {s['id']: s for s in cat.SERVICES}


def item_by_id():
    d = {t['id']: dict(t, kind='tweak') for t in cat.TWEAKS}
    d.update({s['id']: dict(s, kind='service', cat='services') for s in cat.SERVICES})
    return d


def os_compatible(item, build):
    """win11 / min_build kapilari. build=0: bilinmiyor -> izin ver (ust katman uyarir)."""
    if not build:
        return True
    if item.get('win11') and build < 22000:
        return False
    if item.get('min_build') and build < item['min_build']:
        return False
    return True


def needs_admin_item(item):
    if item.get('kind') == 'service' or 'svc' in item or 'task' in item:
        return True
    return any(r['hive'] in ADMIN_HIVES for r in item.get('reg', ()))


def needs_admin_ops(ops):
    for o in ops:
        if o['t'] in ('svc', 'task', 'dns'):
            return True
        if o['t'] == 'reg' and o['hive'] in ADMIN_HIVES:
            return True
    return False


def preset_items(preset_id):
    p = next((p for p in cat.PRESETS if p['id'] == preset_id), None)
    return (list(p['tweaks']) + list(p['services'])) if p else []


# --------------------------------------------------------------------------- okuma plani / durum tespiti
def _reg_key(hive, path, name, sub=False):
    return 'reg|%s|%s|%s|%d' % (hive, path.lower(), name.lower(), 1 if sub else 0)


def read_plan(items):
    """Katalog ogelerinden tekillestirilmis okuma hedefleri: [{'ref', 't', ...}]."""
    out, seen = [], set()

    def add(key, obj):
        if key not in seen:
            seen.add(key)
            obj['ref'] = key
            out.append(obj)
    for it in items:
        for r in it.get('reg', ()):
            add(_reg_key(r['hive'], r['path'], r['name'], r.get('sub')), {'t': 'reg', 'hive': r['hive'], 'path': r['path'], 'name': r['name'], 'sub': bool(r.get('sub'))})
        if 'task' in it:
            add('task|' + it['task'].lower(), {'t': 'task', 'path': it['task']})
        if 'svc' in it:
            name = it['svc']['name'] if isinstance(it['svc'], dict) else it['svc']
            add('svc|' + name.lower(), {'t': 'svc', 'name': name})
        if 'power' in it:
            add('power', {'t': 'power'})
    return out


def reads_by_ref(records):
    return {r['ref']: r for r in records if r.get('type') == 'read' and 'ref' in r}


def _same(cur, want, kind):
    if cur is None:
        return False
    if kind in ('DWord', 'QWord'):
        try:
            return int(str(cur), 0) == int(str(want), 0)
        except (TypeError, ValueError):
            return False
    return str(cur) == str(want)


def _reg_matches(state, want, kind):
    """state: {'key_exists','exists','value'}; want None -> deger yok olmali."""
    if want is None:
        return not state.get('exists')
    return bool(state.get('exists')) and _same(state.get('value'), want, kind)


def item_state(item, reads):
    """'applied' | 'partial' | 'not' | 'unknown' | 'missing'"""
    results = []
    for r in item.get('reg', ()):
        rd = reads.get(_reg_key(r['hive'], r['path'], r['name'], r.get('sub')))
        if rd is None or rd.get('error'):
            return 'unknown'
        if r.get('sub'):
            subs = rd.get('subs') or []
            ok = bool(subs) and all(_reg_matches(s, r['on'], r['kind']) for s in subs)
        else:
            ok = _reg_matches(rd, r['on'], r['kind'])
        if r.get('optional') and not ok:
            continue
        results.append(ok)
    if 'task' in item:
        rd = reads.get('task|' + item['task'].lower())
        if rd is None or rd.get('error'):
            return 'unknown'
        if not rd.get('exists'):
            return 'missing'
        results.append(rd.get('enabled') is False)
    if 'svc' in item:
        name = item['svc']['name'] if isinstance(item['svc'], dict) else item['svc']
        want = item['svc']['start'] if isinstance(item['svc'], dict) else item['start']
        rd = reads.get('svc|' + name.lower())
        if rd is None or rd.get('error'):
            return 'unknown'
        if not rd.get('exists'):
            return 'missing'
        results.append(rd.get('start') == want)
    if 'power' in item:
        rd = reads.get('power')
        if rd is None or rd.get('error'):
            return 'unknown'
        results.append(str(rd.get('active', '')).lower() == item['power'].lower())
    if not results:
        return 'unknown'
    if all(results):
        return 'applied'
    return 'partial' if any(results) else 'not'


def current_text(item, reads):
    """Hizmetler icin gecerli baslangic turu (liste sutunu)."""
    if item.get('kind') == 'service':
        rd = reads.get('svc|' + item['svc'].lower()) or {}
        return START_NAME.get(rd.get('start', ''), rd.get('start', '')) if rd.get('exists') else ('yok' if rd else '')
    return ''


# --------------------------------------------------------------------------- yazma plani
def item_ops(item, mode):
    """mode 'apply' (onerilen degerler) veya 'default' (Windows varsayilani). Hizmetlerin katalogda
    varsayilani yoktur: 'default' icin bos liste doner (gecmisten geri alinir)."""
    ops = []
    if item.get('kind') == 'service':
        if mode == 'apply':
            ops.append({'t': 'svc', 'name': item['svc'], 'start': item['start']})
        return ops
    for r in item.get('reg', ()):
        base = {'t': 'reg', 'hive': r['hive'], 'path': r['path'], 'name': r['name'], 'kind': r['kind'], 'sub': bool(r.get('sub'))}
        if mode == 'apply':
            ops.append(dict(base, value=r['on']))
        elif r.get('off_delkey'):
            ops.append(dict(base, value=None, delkey=r['off_delkey']))
        else:
            ops.append(dict(base, value=r['off']))
    if 'task' in item:
        ops.append({'t': 'task', 'path': item['task'], 'enabled': mode != 'apply'})
    if 'svc' in item:
        if mode == 'apply':
            ops.append({'t': 'svc', 'name': item['svc']['name'], 'start': item['svc']['start']})
    if 'power' in item:
        ops.append({'t': 'power', 'guid': item['power'] if mode == 'apply' else BALANCED_PLAN})
    return ops


def build_write_plan(items, mode):
    """[(item, ops)] -> PowerShell'e gidecek duz liste; her islem 'label' ve sira 'ref' tasir."""
    plan = []
    for it in items:
        for op in item_ops(it, mode):
            op = dict(op, label=it['name'], item=it['id'], ref=len(plan))
            plan.append(op)
    return plan


def dns_plan(adapters, servers):
    out = []
    for a in adapters:
        out.append({'t': 'dns', 'alias': a['alias'], 'guid': a.get('guid', ''), 'servers': list(servers),
                    'label': 'DNS: %s' % a['alias'], 'item': 'dns', 'ref': len(out)})
    return out


def valid_ipv4_list(text):
    parts = [p for p in re.split(r'[\s,;]+', text or '') if p]
    if not parts or len(parts) > 4 or not all(_IPV4.match(p) for p in parts):
        return None
    return parts


def validate_ops(ops):
    """PowerShell'e gitmeden once yapisal denetim; sorun listesi doner."""
    errs = []
    for o in ops:
        t = o.get('t')
        if t == 'reg':
            if o.get('hive') not in VALID_HIVES or not o.get('path') or '..' in o['path'] or o['path'].startswith('\\'):
                errs.append('kayit yolu gecersiz: %r' % o)
            if o.get('value') is not None and o.get('kind') not in VALID_KINDS:
                errs.append('deger turu gecersiz: %r' % o)
            if o.get('delkey') and not o['delkey'].lower().startswith('software\\classes\\clsid\\{'):
                errs.append('anahtar silme yalnizca CLSID altinda: %r' % o)
            if o.get('prune') and not o['path'].lower().startswith(o['prune'].lower()):
                errs.append('temizleme koku yolun ustunde olmali: %r' % o)
        elif t == 'svc':
            if o.get('start') not in VALID_STARTS or not re.match(r'^[A-Za-z0-9_.\-]+$', o.get('name', '')):
                errs.append('hizmet gecersiz: %r' % o)
        elif t == 'task':
            if not str(o.get('path', '')).startswith('\\Microsoft\\Windows\\'):
                errs.append('gorev yolu gecersiz: %r' % o)
        elif t == 'power':
            if not re.match(r'^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$', o.get('guid', '')):
                errs.append('guc plani gecersiz: %r' % o)
        elif t == 'dns':
            if any(not _IPV4.match(s) for s in o.get('servers', [])) or not o.get('alias'):
                errs.append('DNS gecersiz: %r' % o)
        else:
            errs.append('bilinmeyen islem: %r' % o)
    return errs


# --------------------------------------------------------------------------- gunluk ve geri alma
def write_results(records):
    return [r for r in records if r.get('type') == 'write']


def _undo_reg(op, before, path=None):
    path = path or op['path']
    base = {'t': 'reg', 'hive': op['hive'], 'path': path, 'name': op['name'], 'sub': False}
    if before.get('exists'):
        return [dict(base, kind=before.get('kind') or op.get('kind'), value=before.get('value'))]
    if not before.get('key_exists'):
        if op.get('value') is None:
            return []                                              # silme islemiydi ve anahtar zaten yoktu
        # Anahtar islemden once yoktu: degeri sil, PowerShell'in bildirdigi yeni kok anahtara kadar bosalan anahtarlari temizle.
        root = before.get('created_root') or path
        return [dict(base, kind=op.get('kind'), value=None, prune=root)]
    if op.get('value') is None and not op.get('delkey'):
        return []                                                  # zaten yoktu ve silindi: yapilacak bir sey yok
    return [dict(base, kind=op.get('kind'), value=None)]


def undo_ops(entries):
    """Gunluk kayitlarindan (islem + onceki durum) ters sirada geri alma plani."""
    out = []
    for e in reversed(entries):
        op, before = e['op'], e.get('before') or {}
        if not e.get('ok'):
            continue
        t = op['t']
        start = len(out)
        if t == 'reg':
            if op.get('sub'):
                for s in reversed(before.get('subs') or []):
                    out.extend(_undo_reg(op, s, s['path']))
            else:
                out.extend(_undo_reg(op, before))
        elif t == 'svc' and before.get('start') in VALID_STARTS:
            out.append({'t': 'svc', 'name': op['name'], 'start': before['start']})
        elif t == 'task' and before.get('exists') and isinstance(before.get('enabled'), bool):
            out.append({'t': 'task', 'path': op['path'], 'enabled': before['enabled']})
        elif t == 'power' and before.get('active'):
            out.append({'t': 'power', 'guid': before['active']})
        elif t == 'dns' and 'servers' in before:
            out.append({'t': 'dns', 'alias': op['alias'], 'guid': op.get('guid', ''), 'servers': list(before['servers'])})
        for o in out[start:]:
            o['item'] = op.get('item', '')
            o['label'] = 'Geri al: ' + op.get('label', '')
    for n, o in enumerate(out):
        o['ref'] = n
        o.setdefault('label', 'Geri al')
    return out


def journal_path(app_dir):
    return pathlib.Path(app_dir) / 'tweaks-journal.json'


def load_journal(app_dir):
    try:
        data = json.loads(journal_path(app_dir).read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_journal(app_dir, sessions):
    p = journal_path(app_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(sessions[-JOURNAL_KEEP:], ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(p)


def record_session(app_dir, title, plan, records, now=None):
    """PowerShell yazma kayitlarini plandaki islemlerle eslestirip oturum olarak gunluge ekler."""
    by_ref = {r.get('ref'): r for r in write_results(records)}
    entries = []
    for op in plan:
        r = by_ref.get(op['ref'])
        if r is None:
            continue
        clean = {k: v for k, v in op.items() if k not in ('ref',)}
        entries.append({'op': clean, 'ok': bool(r.get('ok')), 'before': r.get('before') or {}, 'error': r.get('error', '')})
    if not any(e['ok'] for e in entries):
        return None
    sessions = load_journal(app_dir)
    sid = (now or datetime.datetime.now()).strftime('%Y%m%d-%H%M%S')
    while any(s['id'] == sid for s in sessions):
        sid += '+'
    sess = {'id': sid, 'time': (now or datetime.datetime.now()).strftime('%Y-%m-%d %H:%M'), 'title': title,
            'entries': entries, 'undone': False}
    sessions.append(sess)
    save_journal(app_dir, sessions)
    return sess


def mark_undone(app_dir, sid):
    sessions = load_journal(app_dir)
    for s in sessions:
        if s['id'] == sid:
            s['undone'] = True
    save_journal(app_dir, sessions)


def session_summary(sess):
    labels = []
    for e in sess['entries']:
        lb = e['op'].get('label', '')
        if lb and lb not in labels:
            labels.append(lb)
    ok = sum(1 for e in sess['entries'] if e['ok'])
    return '%s — %s (%d işlem%s): %s' % (sess['time'], sess['title'], ok, ', geri alındı' if sess.get('undone') else '',
                                         ', '.join(labels[:4]) + (' …' if len(labels) > 4 else ''))


# --------------------------------------------------------------------------- profil (disa / ice aktarma)
PROFILE_APP = 'agfo-system-care-tweaks'


def export_profile(ids, name=''):
    known = item_by_id()
    return {'app': PROFILE_APP, 'schema': 1, 'name': name, 'items': [i for i in ids if i in known]}


def import_profile(data):
    """Kendi bicimimiz ya da WinCleaner ozel profili (tweakIds / serviceIds). Donus: (ids, bilinmeyenler)."""
    if not isinstance(data, dict):
        raise ValueError('Profil dosyası bir JSON nesnesi değil.')
    if data.get('app') == PROFILE_APP:
        ids = data.get('items') or []
    elif 'tweakIds' in data or 'serviceIds' in data:
        ids = list(data.get('tweakIds') or []) + list(data.get('serviceIds') or [])
    else:
        raise ValueError('Tanınmayan profil biçimi.')
    known = item_by_id()
    ids = [i for i in ids if isinstance(i, str)]
    return [i for i in ids if i in known], [i for i in ids if i not in known]


# --------------------------------------------------------------------------- WinGet kurulum katalogu
def install_groups():
    groups = {}
    for a in cat.INSTALL_APPS:
        groups.setdefault(a['cat'], []).append(a)
    return groups


def installed_ids(winget_rows):
    return {r['id'].lower() for r in winget_rows if r.get('id')}


def is_installed(app_id, ids):
    """WinGet tablosu uzun kimlikleri '…' ile keser; kesik kimlik onek olarak eslesir."""
    a = app_id.lower()
    if a in ids:
        return True
    for i in ids:
        if i.endswith('…') and len(i) > 4 and a.startswith(i[:-1]):
            return True
    return False


def windows_build():
    try:
        import sys
        return int(sys.getwindowsversion().build) if hasattr(sys, 'getwindowsversion') else 0
    except Exception:
        return 0
