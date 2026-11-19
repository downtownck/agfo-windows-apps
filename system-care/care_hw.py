# -*- coding: utf-8 -*-
"""System Care 4.0 — Donanim (Everest/AIDA64 tarzi ozet), aygit yoneticisi, disk sagligi ve genel bakis icin
ayristirma, siniflandirma ve rapor. Arayuzden bagimsizdir (testler dogrudan cagirir).

Veriler care_tasks.ps1'in hw-inventory / disk-health / pnp-list / overview / sensors eylemlerinden '@@' JSON satirlari
olarak gelir. Hepsi Windows'un kendi WMI/CIM verisidir; sensorler disinda ek surucu kurulmaz.
"""
from __future__ import annotations

import datetime
import html
import json

LHM_PKG = 'LibreHardwareMonitor.LibreHardwareMonitor'       # istege bagli sensorler (MPL-2.0); PawnIO surucusunu kendisi ister
LHM_NAMESPACE = 'root\\LibreHardwareMonitor'

MEDIA = {0: 'Bilinmiyor', 3: 'HDD', 4: 'SSD', 5: 'SCM'}
BUS = {1: 'SCSI', 2: 'ATAPI', 3: 'ATA', 4: 'IEEE 1394', 5: 'SSA', 6: 'Fibre Channel', 7: 'USB', 8: 'RAID', 9: 'iSCSI', 10: 'SAS',
       11: 'SATA', 12: 'SD', 13: 'MMC', 15: 'Dosya destekli sanal', 16: 'Depolama alanları', 17: 'NVMe'}
HEALTH = {0: 'Sağlıklı', 1: 'Uyarı', 2: 'Sağlıksız', 5: 'Bilinmiyor'}
HEALTH_TXT = {'Healthy': 'Sağlıklı', 'Warning': 'Uyarı', 'Unhealthy': 'Sağlıksız', 'Unknown': 'Bilinmiyor'}
MEM_TYPE = {20: 'DDR', 21: 'DDR2', 24: 'DDR3', 26: 'DDR4', 29: 'LPDDR', 30: 'LPDDR2', 31: 'LPDDR3', 32: 'LPDDR4', 34: 'DDR5', 35: 'LPDDR5'}
PC_TYPE = {1: 'Masaüstü', 2: 'Dizüstü / taşınabilir', 3: 'İş istasyonu', 4: 'Kurumsal sunucu', 5: 'SOHO sunucu', 8: 'Tablet'}
BATTERY_STATUS = {1: 'Pilde çalışıyor', 2: 'Prize takılı', 3: 'Tam dolu', 4: 'Düşük', 5: 'Kritik', 6: 'Şarj oluyor', 7: 'Şarj oluyor (yüksek)',
                  8: 'Şarj oluyor (düşük)', 9: 'Şarj oluyor (kritik)', 11: 'Kısmen dolu'}

# Aygit yoneticisi sinif adlari (Windows PNPClass -> Turkce baslik); listede olmayan sinif kendi adiyla gorunur.
PNP_CLASS_TR = {
    'Display': 'Ekran bağdaştırıcıları', 'Net': 'Ağ bağdaştırıcıları', 'DiskDrive': 'Disk sürücüleri', 'Processor': 'İşlemciler',
    'System': 'Sistem aygıtları', 'USB': 'USB denetleyicileri', 'HIDClass': 'İnsan arabirim aygıtları', 'Keyboard': 'Klavyeler',
    'Mouse': 'Fareler ve işaret aygıtları', 'Monitor': 'Monitörler', 'MEDIA': 'Ses, video ve oyun denetleyicileri',
    'AudioEndpoint': 'Ses girişleri ve çıkışları', 'Bluetooth': 'Bluetooth', 'Camera': 'Kameralar', 'Image': 'Görüntüleme aygıtları',
    'Printer': 'Yazıcılar', 'PrintQueue': 'Yazdırma kuyrukları', 'SCSIAdapter': 'Depolama denetleyicileri', 'HDC': 'IDE ATA/ATAPI denetleyicileri',
    'Volume': 'Birimler', 'VolumeSnapshot': 'Birim gölge kopyaları', 'SoftwareDevice': 'Yazılım aygıtları', 'SoftwareComponent': 'Yazılım bileşenleri',
    'Battery': 'Piller', 'Computer': 'Bilgisayar', 'Firmware': 'Üretici yazılımı', 'SecurityDevices': 'Güvenlik aygıtları',
    'Biometric': 'Biyometrik aygıtlar', 'Ports': 'Bağlantı noktaları (COM ve LPT)', 'WPD': 'Taşınabilir aygıtlar', 'SmartCardReader': 'Akıllı kart okuyucular',
    'Sensor': 'Algılayıcılar', 'Extension': 'Uzantılar', 'CDROM': 'DVD/CD-ROM sürücüleri', 'MTD': 'Bellek teknolojisi aygıtları',
    'XboxComposite': 'Xbox aygıtları', 'XnaComposite': 'Xbox 360 çevre birimleri', 'Infrared': 'Kızılötesi aygıtlar', '': 'Diğer aygıtlar',
}

# Aygit yoneticisi hata kodlari (ConfigManagerErrorCode) — en sik gorulenler
CM_PROBLEM = {
    1: 'Doğru yapılandırılmamış', 3: 'Sürücü bozuk ya da bellek yetersiz', 10: 'Aygıt başlatılamıyor', 12: 'Yeterli kaynak bulunamıyor',
    14: 'Yeniden başlatma gerekiyor', 18: 'Sürücüler yeniden yüklenmeli', 19: 'Kayıt defteri bilgisi bozuk', 21: 'Windows aygıtı kaldırıyor',
    22: 'Devre dışı', 24: 'Aygıt yok ya da düzgün çalışmıyor', 28: 'Sürücü yüklü değil', 29: 'Üretici yazılımı aygıtı kapatmış',
    31: 'Sürücü yüklenemedi', 32: 'Sürücü hizmeti devre dışı', 37: 'Sürücü başlatılamadı', 39: 'Sürücü bozuk ya da eksik',
    41: 'Aygıt donanımı bulunamadı', 43: 'Aygıt bir sorun bildirdi', 45: 'Bağlı değil', 48: 'Sürücü uyumsuz olduğu için engellendi',
    52: 'Sürücü imzası doğrulanamadı',
}

OV_TITLES = {'uptime': 'Çalışma süresi', 'memory': 'Bellek', 'reboot': 'Yeniden başlatma', 'defender': 'Microsoft Defender',
             'firewall': 'Güvenlik duvarı', 'bitlocker': 'BitLocker', 'winupdate': 'Windows Update', 'devices': 'Aygıtlar',
             'disks': 'Disk sağlığı', 'vpn': 'VPN / Tailscale', 'apps': 'Uygulama güncellemeleri'}
OV_ORDER = ['disks', 'devices', 'defender', 'firewall', 'winupdate', 'reboot', 'memory', 'uptime', 'bitlocker', 'vpn']
STATE_RANK = {'bad': 0, 'warn': 1, 'info': 2, 'ok': 3}

# Hata/uyari metinleri ASCII Turkce gelir (PowerShell); arayuzde duzgun Turkceye cevrilir.
_ASCII_TR = [('gun', 'gün'), ('Gercek zamanli koruma acik', 'Gerçek zamanlı koruma açık'), ('Gercek zamanli koruma KAPALI', 'Gerçek zamanlı koruma KAPALI'),
             ('Imza yasi', 'İmza yaşı'), ('Okunamadi', 'Okunamadı'), ('Baska bir antivirus kullaniliyor olabilir', 'Başka bir antivirüs kullanılıyor olabilir'),
             ('Kapali profil', 'Kapalı profil'), ('Tum profiller acik', 'Tüm profiller açık'), ('Sistem diski sifreli degil', 'Sistem diski şifreli değil'),
             ('Sistem diski sifreli', 'Sistem diski şifreli'), ('Yonetici gerekir', 'Yönetici gerekir'), ('Son guncelleme', 'Son güncelleme'),
             ('once', 'önce'), ('sorunlu aygit', 'sorunlu aygıt'), ('Sorunlu aygit yok', 'Sorunlu aygıt yok'), ('saglikli degil', 'sağlıklı değil'),
             ('saglikli', 'sağlıklı'), ('Yeniden baslatma bekliyor', 'Yeniden başlatma bekliyor'), ('Gerekmiyor', 'Gerekmiyor'), ('bos', 'boş'),
             ('saat', 'saat')]


def tr_text(s):
    s = str(s or '')
    for a, b in _ASCII_TR:
        if a in s and b not in s:
            s = s.replace(a, b)
    return s


def parse_records(lines, kind=None):
    """'@@{...}' satirlarini sozluk listesine cevirir; kind verilirse yalnizca o 'type'."""
    out = []
    for ln in lines or []:
        ln = ln.strip()
        if not ln.startswith('@@'):
            continue
        try:
            r = json.loads(ln[2:])
        except ValueError:
            continue
        if isinstance(r, dict) and (kind is None or r.get('type') == kind):
            out.append(r)
    return out


def fmt_bytes(n, unit_base=1024):
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return '-'
    if n <= 0:
        return '-'
    for u in ('B', 'KB', 'MB', 'GB', 'TB', 'PB'):
        if n < unit_base or u == 'PB':
            return ('%.0f %s' % (n, u)) if u in ('B', 'KB') or n >= 100 else ('%.1f %s' % (n, u))
        n /= unit_base
    return '-'


def fmt_speed(bps):
    try:
        bps = int(bps or 0)
    except (TypeError, ValueError):
        return ''
    if bps <= 0 or bps >= 9_000_000_000_000:
        return ''
    return '%g Gbps' % (bps / 1e9) if bps >= 1e9 else '%g Mbps' % (bps / 1e6)


def _v(r, k, default=''):
    v = r.get(k)
    return default if v in (None, '') else v


def inventory_sections(recs):
    """hw kayitlari -> [(baslik, [(etiket, deger), ...]), ...] (Sistem ozeti agaci)."""
    by = {}
    for r in recs:
        if r.get('type') == 'hw':
            by.setdefault(r.get('kind'), []).append(r)
    S = []

    def add(title, rows):
        rows = [(a, str(b)) for a, b in rows if b not in (None, '', '-', 0)]
        if rows:
            S.append((title, rows))
    for c in by.get('computer', []):
        add('Bilgisayar', [('Ad', c['name']), ('Üretici', _v(c, 'maker')), ('Model', _v(c, 'model')),
                           ('Tür', PC_TYPE.get(c.get('type'), '')), ('Etki alanı / çalışma grubu', _v(c, 'domain'))])
    for o in by.get('os', []):
        add('İşletim sistemi', [('Sürüm', o['name']), ('Derleme', '%s (%s)' % (_v(o, 'version'), _v(o, 'build'))), ('Mimari', _v(o, 'arch')),
                                ('Kurulum tarihi', _v(o, 'installed')), ('Son açılış', _v(o, 'boot'))])
    rows = []
    for b in by.get('board', []):
        rows += [('Anakart', ('%s %s' % (_v(b, 'maker'), b['name'])).strip()), ('Anakart sürümü', _v(b, 'version'))]
    for b in by.get('bios', []):
        rows += [('BIOS / UEFI', ('%s %s' % (_v(b, 'maker'), b['name'])).strip()), ('BIOS tarihi', _v(b, 'date'))]
    add('Anakart ve BIOS', rows)
    for i, p in enumerate(by.get('cpu', []), 1):
        add('İşlemci' + (' %d' % i if len(by['cpu']) > 1 else ''),
            [('Model', p['name']), ('Çekirdek / iş parçacığı', '%s / %s' % (_v(p, 'cores', '?'), _v(p, 'threads', '?'))),
             ('Azami hız', ('%d MHz' % p['mhz']) if p.get('mhz') else ''), ('Yuva', _v(p, 'socket')),
             ('L2 / L3 önbellek', ('%s / %s' % (fmt_bytes((p.get('l2') or 0) * 1024), fmt_bytes((p.get('l3') or 0) * 1024))) if p.get('l3') or p.get('l2') else ''),
             ('Anlık yük', ('%%%d' % p['load']) if p.get('load') is not None else ''), ('Sanallaştırma (BIOS)', 'Açık' if p.get('virt') else 'Kapalı')])
    mods = by.get('ram', [])
    if mods:
        total = sum(int(m.get('size') or 0) for m in mods)
        types = sorted({MEM_TYPE.get(m.get('smbtype'), '') for m in mods} - {''})
        rows = [('Toplam', '%s (%d modül%s)' % (fmt_bytes(total), len(mods), (', ' + '/'.join(types)) if types else ''))]
        for m in mods:
            mhz = m.get('mhz') or m.get('speed')
            rows.append((m['name'] or _v(m, 'bank', 'Yuva'), ' · '.join(x for x in (fmt_bytes(m.get('size')), ('%d MT/s' % mhz) if mhz else '',
                                                                                    _v(m, 'maker'), _v(m, 'part')) if x and x != '-')))
        add('Bellek', rows)
    for g in by.get('gpu', []):
        add('Ekran kartı: ' + g['name'], [('Sürücü', ('%s (%s)' % (_v(g, 'driver'), _v(g, 'date'))).strip(' ()')),
                                          ('Bellek (bildirilen)', fmt_bytes(g.get('vram')) if (g.get('vram') or 0) > 0 else ''),
                                          ('Çözünürlük', ('%s @ %s Hz' % (g['res'], g['hz'])) if g.get('hz') and g.get('res') not in ('x', '0x0') else '')])
    rows = [(d['name'], ' · '.join(x for x in (fmt_bytes(d.get('size'), 1000), MEDIA.get(d.get('media'), ''), BUS.get(d.get('bus'), ''),
                                               HEALTH.get(d.get('health'), '')) if x and x not in ('-', 'Bilinmiyor')))
            for d in by.get('disk', [])]
    add('Diskler', rows)
    add('Bölümler', [('%s %s' % (v['name'], _v(v, 'label')), '%s boş / %s (%s)' % (fmt_bytes(v.get('free')), fmt_bytes(v.get('size')), _v(v, 'fs')))
                     for v in by.get('volume', [])])
    add('Ağ bağdaştırıcıları', [(n['name'], ' · '.join(x for x in ('Bağlı' if n.get('connected') else 'Bağlı değil', fmt_speed(n.get('speed')),
                                                                    _v(n, 'conn')) if x)) for n in by.get('net', [])])
    add('Ses aygıtları', [(a['name'], _v(a, 'maker')) for a in by.get('audio', [])])
    add('Monitörler', [(m['name'] or 'Monitör', ' · '.join(x for x in (_v(m, 'maker'), str(m['year']) if m.get('year') else '') if x)) for m in by.get('monitor', [])])
    for b in by.get('battery', []):
        wear = ''
        if b.get('design') and b.get('full'):
            wear = '%%%d (tasarım kapasitesine göre)' % round(100 * b['full'] / b['design'])
        add('Pil', [('Ad', b['name']), ('Doluluk', ('%%%d' % b['charge']) if b.get('charge') is not None else ''),
                    ('Durum', BATTERY_STATUS.get(b.get('status'), '')), ('Pil sağlığı', wear)])
    return S


def disk_verdict(d):
    """disk-health kaydi -> (durum, aciklama). durum: ok | warn | bad | info."""
    h = str(d.get('health') or '')
    notes, state = [], 'ok'

    def worse(s):
        nonlocal state
        if STATE_RANK[s] < STATE_RANK[state]:
            state = s
    if h and h != 'Healthy':
        worse('bad' if h == 'Unhealthy' else 'warn')
        notes.append('Windows durumu: ' + HEALTH_TXT.get(h, h))
    wear = d.get('wear')
    if isinstance(wear, (int, float)) and wear > 0:
        if wear >= 90:
            worse('bad')
        elif wear >= 70:
            worse('warn')
        notes.append('aşınma %%%d' % wear)
    t = d.get('temp')
    if isinstance(t, (int, float)) and t > 0:
        if t >= 70:
            worse('bad')
        elif t >= 60:
            worse('warn')
        notes.append('%d °C' % t)
    errs = sum(int(d.get(k) or 0) for k in ('rerr', 'werr'))
    if errs:
        worse('warn')
        notes.append('%d düzeltilemeyen okuma/yazma hatası' % errs)
    if d.get('hours'):
        notes.append('%s saat çalışma' % format(int(d['hours']), ',').replace(',', '.'))
    if d.get('temp') is None and d.get('wear') is None and not d.get('admin'):
        notes.append('sıcaklık/aşınma için yönetici gerekir')
    label = {'ok': 'Sağlıklı', 'warn': 'Dikkat', 'bad': 'Kötü', 'info': 'Bilinmiyor'}[state]
    if not h:
        state, label = 'info', 'Bilinmiyor'
    return state, label + (' — ' + ', '.join(notes) if notes else '')


def pnp_class_title(cls):
    return PNP_CLASS_TR.get(cls or '', cls or 'Diğer aygıtlar')


def pnp_problem(code):
    if not code:
        return ''
    return CM_PROBLEM.get(int(code), 'Sorun kodu %s' % code)


def pnp_groups(recs, show_hidden=False, only_problems=False, query=''):
    """pnp kayitlari -> [(sinif_basligi, [kayit, ...]), ...]; sorunlu sinif once, sonra alfabetik."""
    q = (query or '').casefold().strip()
    groups = {}
    for r in recs:
        if r.get('type') != 'pnp':
            continue
        if not show_hidden and r.get('present') is False:
            continue
        if only_problems and not r.get('code'):
            continue
        if q and q not in ' '.join(str(r.get(k, '')) for k in ('name', 'maker', 'id', 'cls')).casefold():
            continue
        groups.setdefault(pnp_class_title(r.get('cls')), []).append(r)
    out = []
    for title, items in groups.items():
        items.sort(key=lambda r: (not r.get('code'), str(r.get('name', '')).casefold()))
        out.append((title, items))
    out.sort(key=lambda g: (not any(r.get('code') for r in g[1]), g[0].casefold()))
    return out


def overview_cards(recs, extra=None):
    """ov kayitlari (+ uygulamanin kendi kartlari) -> siralanmis kart listesi [{key,title,state,value,detail}]."""
    cards, vols = {}, []
    for r in recs:
        if r.get('type') != 'ov':
            continue
        c = {'key': r['key'], 'state': r.get('state', 'info'), 'value': tr_text(r.get('value')), 'detail': tr_text(r.get('detail'))}
        if r['key'].startswith('volume:'):
            c['title'] = 'Disk ' + r['key'].split(':', 1)[1] + ':'
            vols.append(c)
        else:
            c['title'] = OV_TITLES.get(r['key'], r['key'])
            cards[r['key']] = c
    for c in extra or []:
        cards[c['key']] = dict(c, title=c.get('title') or OV_TITLES.get(c['key'], c['key']))
    order = [k for k in OV_ORDER if k in cards] + sorted(k for k in cards if k not in OV_ORDER)
    out = [cards[k] for k in order]
    out[2:2] = sorted(vols, key=lambda c: c['title'])
    return out


def overview_score(cards):
    """Basit saglik puani (0-100): her 'bad' 25, her 'warn' 8 puan duser."""
    s = 100 - 25 * sum(c['state'] == 'bad' for c in cards) - 8 * sum(c['state'] == 'warn' for c in cards)
    return max(0, min(100, s))


def parse_sensors(recs):
    """sensors kayitlari -> {donanim: [(sensor, tur, deger_metni)]}."""
    unit = {'Temperature': '°C', 'Fan': 'RPM', 'Voltage': 'V', 'Load': '%', 'Clock': 'MHz', 'Power': 'W', 'Control': '%', 'Data': 'GB', 'Throughput': 'B/s'}
    out = {}
    for r in recs:
        if r.get('type') != 'sensor':
            continue
        try:
            val = float(r.get('value'))
        except (TypeError, ValueError):
            continue
        st = r.get('stype', '')
        txt = ('%.0f' % val if st in ('Fan', 'Clock', 'Temperature', 'Load', 'Control') else '%.2f' % val) + ' ' + unit.get(st, '')
        out.setdefault(r.get('hardware') or '?', []).append((r.get('name', ''), st, txt.strip()))
    return out


def report_text(sections, disks=(), groups=(), cards=()):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    L = ['AGFO System Care — Donanım raporu (%s)' % now, '=' * 60]
    if cards:
        L += ['', 'GENEL BAKIŞ', '-' * 60] + ['%-24s %s%s' % (c['title'], c['value'], ('  (' + c['detail'] + ')') if c.get('detail') else '') for c in cards]
    for title, rows in sections:
        L += ['', title.upper(), '-' * 60] + ['%-28s %s' % (a, b) for a, b in rows]
    if disks:
        L += ['', 'DİSK SAĞLIĞI', '-' * 60] + ['%-28s %s' % (d.get('name', ''), disk_verdict(d)[1]) for d in disks]
    probs = [(t, r) for t, items in groups for r in items if r.get('code')]
    if probs:
        L += ['', 'SORUNLU AYGITLAR', '-' * 60] + ['%s | %s | %s' % (t, r.get('name', ''), pnp_problem(r.get('code'))) for t, r in probs]
    return '\n'.join(L) + '\n'


def report_html(sections, disks=(), groups=(), cards=()):
    e = html.escape
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    css = ('body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1d2433;background:#f6f7fb}h1{font-size:20px}'
           'h2{font-size:15px;margin:22px 0 6px;color:#2b5fab}table{border-collapse:collapse;width:100%;background:#fff}'
           'td{padding:5px 10px;border-bottom:1px solid #e6e8ef;vertical-align:top}td.k{width:32%;color:#5b6475}'
           '.ok{color:#17803d}.warn{color:#9a6200}.bad{color:#b42323}a{text-decoration:none}')
    out = ['<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8"><title>Donanım raporu</title><style>%s</style></head><body>' % css,
           '<h1>AGFO System Care — Donanım raporu</h1><p>%s</p>' % e(now)]

    def table(title, rows, cls=None):
        out.append('<h2>%s</h2><table>' % e(title))
        for i, (a, b) in enumerate(rows):
            c = (' class="%s"' % cls[i]) if cls else ''
            out.append('<tr><td class="k">%s</td><td%s>%s</td></tr>' % (e(str(a)), c, e(str(b))))
        out.append('</table>')
    if cards:
        table('Genel bakış', [(c['title'], c['value'] + ((' — ' + c['detail']) if c.get('detail') else '')) for c in cards], [c['state'] for c in cards])
    for title, rows in sections:
        table(title, rows)
    if disks:
        v = [disk_verdict(d) for d in disks]
        table('Disk sağlığı', [(d.get('name', ''), x[1]) for d, x in zip(disks, v)], [x[0] for x in v])
    probs = [(t, r) for t, items in groups for r in items if r.get('code')]
    if probs:
        table('Sorunlu aygıtlar', [('%s — %s' % (r.get('name', ''), t), pnp_problem(r.get('code'))) for t, r in probs], ['warn'] * len(probs))
    out.append('</body></html>')
    return '\n'.join(out)
