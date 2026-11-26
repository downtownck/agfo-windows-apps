# -*- coding: utf-8 -*-
"""AGFO System Care 4.4 — internet hizi / ping taramasi ve DNS yonetimi (salt mantik; arayuz sc_netopt.py).

Ag taramasi (care_tasks.ps1 net-scan / dns-bench) kayitlarindan bulgular uretir. Her bulgu ne gordugunu, ne onerdigini, riskini ve
uygulanabilir bir eylemi (varsa) tasir. Eylemler: dns (DNS sunucusu degistir), nic (baglanti hizi/cift yon otomatik), do (Windows Update
P2P paylasimini kapat), page (ilgili System Care sayfasini ac), tool (Windows aracini ac). Windows Update hizmetini kapatmak bilincli
olarak onerilmez: guvenlik yamalari gelmez.
"""
from __future__ import annotations

import ipaddress
import re

try:
    import care_tweaks as _tweaks
    DNS_PRESETS = _tweaks.DNS_PRESETS
except Exception:  # testler
    DNS_PRESETS = [('dhcp', 'Otomatik (DHCP / modem)', []), ('cloudflare', 'Cloudflare 1.1.1.1', ['1.1.1.1', '1.0.0.1']),
                   ('google', 'Google 8.8.8.8', ['8.8.8.8', '8.8.4.4']), ('quad9', 'Quad9 9.9.9.9 (zararlı alan adı engelli)', ['9.9.9.9', '149.112.112.112']),
                   ('adguard', 'AdGuard 94.140.14.14 (reklam engelli)', ['94.140.14.14', '94.140.15.15'])]

# DNS testine giren genel sunucular (birincil adres; uygulanirken ikincisi de yazilir)
BENCH_PRESETS = [p for p in DNS_PRESETS if p[2]]
TAILSCALE_DNS = '100.100.100.100'
MIN_GAIN_MS = 8.0          # DNS degisikligini onermek icin en az kazanc
MIN_GAIN_RATIO = 0.15


def _ip(s):
    try:
        return ipaddress.ip_address(str(s).strip())
    except ValueError:
        return None


def is_private(s):
    a = _ip(s)
    return bool(a and (a.is_private or a.is_link_local or (a.version == 4 and a in ipaddress.ip_network('100.64.0.0/10'))))


def preset_for(server):
    for key, label, servers in DNS_PRESETS:
        if server in servers:
            return key, label, servers
    return None


def by_type(records, typ):
    return [r for r in records or [] if isinstance(r, dict) and r.get('type') == typ]


def physical_adapters(records):
    """Gercek internet baglantisi tasiyan (sanal/VPN olmayan) bagli bagdastiricilar."""
    return [a for a in by_type(records, 'net-adapter') if not a.get('virtual') and a.get('kind') in ('ethernet', 'wifi', 'other')]


def probe_ok(p, need=4):
    return p.get('median') is not None and int(p.get('ok') or 0) >= need


def dns_ranking(records):
    """DNS testi sonuclari, en hizlidan (ortanca cozumleme suresi); basarisiz olanlar sonda."""
    probes = by_type(records, 'dns-probe')
    return sorted(probes, key=lambda p: (0 if probe_ok(p) else 1, p.get('median') if p.get('median') is not None else 1e9))


def describe_server(ip, adapters=()):
    pr = preset_for(ip)
    if pr:
        return pr[1]
    if ip == TAILSCALE_DNS:
        return 'Tailscale MagicDNS'
    if any(ip == a.get('gateway') for a in adapters):
        return 'Modem / yönlendirici (%s)' % ip
    if is_private(ip):
        return 'Yerel ağ DNS\'i (%s)' % ip
    return ip


def current_dns(adapters):
    cur = []
    for a in adapters:
        for d in a.get('dns_current') or []:
            if d not in cur:
                cur.append(d)
    return cur


def dns_finding(records):
    adapters = physical_adapters(records)
    ranking = [p for p in dns_ranking(records) if p.get('server') != TAILSCALE_DNS]
    cur = current_dns(adapters)
    good = [p for p in ranking if probe_ok(p)]
    if not adapters:
        return None
    rank_txt = ', '.join('%s %s' % (describe_server(p['server'], adapters).split(' (')[0], ('%.0f ms' % p['median']) if p.get('median') is not None else 'yanıt yok')
                         for p in ranking[:5])
    cur_probe = next((p for p in ranking if p.get('server') in cur[:1]), None)
    base = {'id': 'dns', 'title': 'DNS sunucusu', 'detail': 'Test (ortanca çözümleme süresi): ' + rank_txt}
    if TAILSCALE_DNS in cur:
        return dict(base, current='Tailscale MagicDNS', advice='Tailscale DNS\'i yönetiyor; değiştirilmez.', risk='bilgi', action=None)
    if not good:
        return dict(base, current=', '.join(describe_server(c, adapters) for c in cur) or '—',
                    advice='DNS testi tamamlanamadı (internet bağlantısını denetleyin).', risk='bilgi', action=None)
    best = good[0]
    cur_txt = ', '.join(describe_server(c, adapters) for c in cur) or 'otomatik'
    if cur_probe is None or not probe_ok(cur_probe):
        gain = None
    else:
        gain = cur_probe['median'] - best['median']
    if cur and best['server'] == cur[0]:
        return dict(base, current=cur_txt, advice='Zaten en hızlı DNS kullanılıyor (%.0f ms).' % best['median'], risk='tamam', action=None)
    if gain is not None and (gain < MIN_GAIN_MS or gain < cur_probe['median'] * MIN_GAIN_RATIO):
        return dict(base, current=cur_txt, advice='Mevcut DNS yeterince hızlı (fark %.0f ms); değiştirmeye gerek yok.' % max(gain, 0), risk='tamam', action=None)
    pr = preset_for(best['server'])
    servers = pr[2] if pr else [best['server']]
    name = pr[1] if pr else best['server']
    filtered = any(is_private(c) and not any(c == a.get('gateway') for a in adapters) for c in cur)
    risk = 'dikkat' if filtered else 'güvenli'
    note = (' Mevcut DNS yerel ağdaki bir sunucu (Pi-hole / şirket DNS\'i olabilir); değiştirirseniz onun filtrelemesi devre dışı kalır.'
            if filtered else ' Geri almak: DNS yönetimi > Otomatik (DHCP) ya da İnce ayarlar > Geçmiş.')
    adv = '%s kullan (%.0f ms%s).%s' % (name, best['median'], (', %.0f ms daha hızlı' % gain) if gain is not None else '', note)
    return dict(base, current=cur_txt, advice=adv, risk=risk,
                action={'kind': 'dns', 'servers': list(servers), 'label': name,
                        'adapters': [{'alias': a['alias'], 'guid': a.get('guid', '')} for a in adapters]})


def nic_findings(records):
    out = []
    for a in physical_adapters(records):
        sd = a.get('speed_duplex') or {}
        if not sd:
            continue
        valid = [str(v) for v in sd.get('valid_values') or []]
        disp = [str(v) for v in sd.get('valid_display') or []]
        auto_val = '0' if (not valid or '0' in valid) else None
        if auto_val is None:
            for v, d in zip(valid, disp):
                if re.search(r'(?i)auto|otomatik', d):
                    auto_val = v
                    break
        if auto_val is None:
            continue
        cur = str(sd.get('value') or '')
        if cur != auto_val:
            out.append({'id': 'nic-' + a['alias'], 'title': 'Bağlantı hızı ve çift yön — %s' % a['alias'], 'current': sd.get('display') or cur,
                        'advice': 'Otomatik algılamaya alın: elle sınırlanmış hız (ör. 10/100 Mbps, yarım çift yön) paketinizi tam kullandırmaz. '
                                  'Bağdaştırıcı birkaç saniye kopar.', 'risk': 'dikkat',
                        'action': {'kind': 'nic', 'alias': a['alias'], 'value': auto_val, 'old': cur}})
        elif a.get('kind') == 'ethernet' and a.get('link_bps') and float(a['link_bps']) < 1e9 and any(re.search(r'(?i)1(\.0)?\s*G', d) for d in disp):
            out.append({'id': 'link-' + a['alias'], 'title': 'Kablolu bağlantı hızı — %s' % a['alias'], 'current': a.get('link') or '',
                        'advice': 'Kart 1 Gbps destekliyor ama bağlantı daha düşük kuruldu: kabloyu (Cat5e/Cat6) ve modem portunu denetleyin.',
                        'risk': 'bilgi', 'action': None})
    return out


def wifi_finding(records):
    adapters = physical_adapters(records)
    wifi = by_type(records, 'net-wifi')
    uses_wifi = any(a.get('kind') == 'wifi' for a in adapters) and not any(a.get('kind') == 'ethernet' for a in adapters)
    if not uses_wifi:
        return None
    sig = wifi[0].get('signal') if wifi else None
    if sig is not None and sig < 60:
        return {'id': 'wifi', 'title': 'Wi-Fi sinyali', 'current': '%%%d %s' % (sig, wifi[0].get('radio') or ''),
                'advice': 'Sinyal zayıf: modeme yaklaşın, 5 GHz ağı seçin ya da mümkünse kablo (Ethernet) kullanın; ping dalgalanması büyük ölçüde kaybolur.',
                'risk': 'bilgi', 'action': None}
    return {'id': 'wifi', 'title': 'Bağlantı türü', 'current': 'Wi-Fi' + (' (%%%d)' % sig if sig is not None else ''),
            'advice': 'Oyun ve görüntülü görüşme için kablolu (Ethernet) bağlantı ping dalgalanmasını en çok azaltan adımdır.', 'risk': 'bilgi', 'action': None}


def ping_findings(records):
    out = []
    for p in by_type(records, 'net-ping'):
        tgt = 'Modem' if p.get('target') == 'gateway' else 'İnternet (1.1.1.1)'
        sent, lost = int(p.get('sent') or 0), int(p.get('lost') or 0)
        avg, jit = p.get('avg'), p.get('jitter')
        cur = ('%s ms, dalgalanma %s ms, kayıp %d/%d' % (avg, jit, lost, sent)) if avg is not None else 'yanıt yok (%d/%d kayıp)' % (lost, sent)
        bad = avg is None or (sent and lost / sent > 0.05) or (jit is not None and jit > 20) or \
            (p.get('target') == 'gateway' and avg is not None and avg > 15)
        if p.get('target') == 'gateway':
            adv = ('Modeme kadar gecikme/kayıp var: sorun evdeki ağda (Wi-Fi sinyali, kablo, modem). Modemi yeniden başlatmayı ve kabloyu deneyin.'
                   if bad else 'Ev ağı sağlıklı.')
        else:
            adv = ('İnternette kayıp veya yüksek dalgalanma var. Modem tarafı temizse sorun servis sağlayıcıda olabilir; arka planda indirme '
                   'yapan uygulamaları kapatıp yeniden ölçün.' if bad else 'İnternet gecikmesi normal.')
        out.append({'id': 'ping-' + str(p.get('target')), 'title': 'Gecikme — ' + tgt, 'current': cur, 'advice': adv,
                    'risk': 'bilgi' if bad else 'tamam', 'action': None})
    return out


def do_mode(rec):
    """Etkin Delivery Optimization modu: ilke > Config > Ayarlar; hicbiri yoksa Windows varsayilani (1: yalniz yerel ag)."""
    for k in ('policy', 'config', 'settings'):
        if rec.get(k) is not None:
            return int(rec[k]), k
    return 1, 'varsayılan'


def do_finding(records):
    recs = by_type(records, 'net-do')
    if not recs:
        return None
    mode, src = do_mode(recs[0])
    base = {'id': 'do', 'title': 'Windows Update paylaşımı (Teslim İyileştirme)'}
    if mode in (0, 99, 100):
        return dict(base, current='kapalı', advice='Güncellemeler başka bilgisayarlara yüklenmiyor.', risk='tamam', action=None)
    if mode == 1:
        return dict(base, current='yalnız yerel ağ', advice='İnternet üzerinden yükleme yapmıyor; isterseniz tamamen kapatabilirsiniz.', risk='güvenli',
                    action={'kind': 'do'}, checked=False)
    return dict(base, current='internet üzerinden paylaşım açık (mod %d)' % mode,
                advice='Kapatın: Windows indirdiği güncellemeleri internetinizden başka kullanıcılara yüklüyor ve bant genişliğini kullanıyor. '
                       'Güncellemeler yine Microsoft\'tan gelir.', risk='güvenli', action={'kind': 'do'})


def startup_finding(startups):
    if startups is None:
        return None
    en = [r for r in startups if r.get('enabled')]
    return {'id': 'startup', 'title': 'Başlangıç uygulamaları', 'current': '%d etkin / %d' % (len(en), len(startups)),
            'advice': 'Açılışta internete bağlanan gereksiz uygulamaları kapatın (Microsoft ve tanımadıklarınıza dokunmayın). AI asistan '
                      '"Açılışı hızlandır" hangilerinin güvenle kapatılabileceğini söyler.',
            'risk': 'bilgi' if len(en) > 8 else 'tamam', 'action': {'kind': 'page', 'page': 'Başlangıç'}, 'checked': False}


def proc_finding(records):
    procs = by_type(records, 'net-proc')
    if not procs:
        return None
    top = ', '.join('%s (%d)' % (p.get('name') or p.get('pid'), p.get('connections') or 0) for p in procs[:6])
    return {'id': 'procs', 'title': 'İnterneti kullanan uygulamalar', 'current': top,
            'advice': 'Parantez içi: açık bağlantı sayısı. Anlık bant genişliği için Kaynak İzleyicisi > Ağ; gereksiz olanı Çalışan uygulamalar\'dan '
                      'kapatın, hiç kullanmadığınızı Programlar / Bloatware\'den kaldırın.', 'risk': 'bilgi',
            'action': {'kind': 'tool', 'tool': 'resmon'}, 'checked': False}


WU_NOTE = {'id': 'wu', 'title': 'Windows Update hizmeti', 'current': 'dokunulmadı',
           'advice': 'Hizmeti kapatmak önerilmez: güvenlik yamaları gelmez. Oyun/yayın sırasında güncelleme indirmesini istemiyorsanız '
                     'Ayarlar > Windows Update > Güncellemeleri duraklat ya da Etkin saatler kullanın.', 'risk': 'bilgi',
           'action': {'kind': 'settings', 'uri': 'ms-settings:windowsupdate'}, 'checked': False}


def analyze(records, startups=None):
    """Ag taramasi kayitlarindan bulgular (onem sirasiyla)."""
    out = []
    for f in [dns_finding(records)] + nic_findings(records) + [do_finding(records), wifi_finding(records)] + ping_findings(records) + \
            [startup_finding(startups), proc_finding(records), WU_NOTE]:
        if f:
            f.setdefault('checked', bool(f.get('action')) and f.get('risk') == 'güvenli' and f['action'].get('kind') in ('dns', 'do'))
            out.append(f)
    return out


def bench_servers(adapters):
    """DNS yonetimi testi: genel DNS'ler + bagdastiricilardaki mevcut sunucular."""
    out = [p[2][0] for p in BENCH_PRESETS]
    for d in current_dns(adapters):
        if d not in out and d != TAILSCALE_DNS and _ip(d) and _ip(d).version == 4:
            out.append(d)
    return out
