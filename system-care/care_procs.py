# -*- coding: utf-8 -*-
"""System Care 4.2 — Calisan uygulamalar, servisler ve baslangic uygulamalari icin arayuzden bagimsiz yardimcilar.

Veriler care_tasks.ps1'in proc-list / svc-list / startup-list eylemlerinden gelir. Kritik Windows surecleri ve
servisleri listede gorunur ama durdurulamaz / devre disi birakilamaz (sistem kilitlenir ya da acilmaz).
Baslangic ogeleri Gorev Yoneticisi ile ayni yontemle (StartupApproved) etkinlestirilir/devre disi birakilir: kayit
silinmez, her zaman geri alinabilir.
"""
from __future__ import annotations

import base64
import json
import re

# Sonlandirilirsa Windows coker ya da oturum kapanir
CRITICAL_PROCS = {'system', 'idle', 'registry', 'smss', 'csrss', 'wininit', 'winlogon', 'services', 'lsass', 'lsaiso', 'svchost',
                  'fontdrvhost', 'dwm', 'memory compression', 'secure system', 'sgrmbroker', 'msmpeng', 'securityhealthservice',
                  'spoolsv', 'audiodg', 'conhost', 'sihost', 'ctfmon'}
# Durdurulamaz / devre disi birakilamaz (Windows calismaz, ag ya da guvenlik devre disi kalir)
CRITICAL_SERVICES = {'rpcss', 'dcomlaunch', 'rpceptmapper', 'lsm', 'samss', 'eventlog', 'plugplay', 'winmgmt', 'bfe', 'mpssvc', 'windefend',
                     'cryptsvc', 'dnscache', 'dhcp', 'nsi', 'profsvc', 'power', 'brokerinfrastructure', 'coremessagingregistrar',
                     'systemeventsbroker', 'gpsvc', 'schedule', 'audiosrv', 'audioendpointbuilder', 'usermanager', 'sense', 'wscsvc',
                     'staterepository', 'appinfo', 'lanmanworkstation', 'netprofm', 'nlasvc', 'wlansvc', 'eaphost', 'keyiso', 'vaultsvc',
                     'msiserver', 'trustedinstaller', 'wuauserv', 'sgrmbroker', 'securityhealthservice', 'wdnissvc', 'tokenbroker',
                     'cdpusersvc', 'themes', 'fontcache', 'sens', 'shellhwdetection', 'tabletinputservice', 'textinputmanagementservice'}
SVC_STATE = {'Running': 'Çalışıyor', 'Stopped': 'Durdu', 'Start Pending': 'Başlıyor', 'Stop Pending': 'Duruyor', 'Paused': 'Duraklatıldı',
             'Continue Pending': 'Sürdürülüyor', 'Pause Pending': 'Duraklatılıyor'}
SVC_START = {'Auto': 'Otomatik', 'Manual': 'El ile', 'Disabled': 'Devre dışı', 'Boot': 'Önyükleme', 'System': 'Sistem'}
SVC_OPS = ('start', 'stop', 'restart', 'auto', 'manual', 'disabled')
STARTUP_LOC = {'hkcu-run': 'Kullanıcı (HKCU Run)', 'hklm-run': 'Tüm kullanıcılar (HKLM Run)', 'hklm-run32': 'Tüm kullanıcılar (32 bit)',
               'user-folder': 'Başlangıç klasörü (kullanıcı)', 'common-folder': 'Başlangıç klasörü (tüm kullanıcılar)'}


def proc_name(rec):
    return (rec.get('name') or '').lower().removesuffix('.exe')


def is_critical_proc(rec):
    return proc_name(rec) in CRITICAL_PROCS or int(rec.get('pid') or 0) in (0, 4) or int(rec.get('session') or 1) == 0 and not rec.get('path')


def is_critical_service(rec_or_name):
    n = rec_or_name.get('name') if isinstance(rec_or_name, dict) else rec_or_name
    return (n or '').lower() in CRITICAL_SERVICES


def startup_needs_admin(rec):
    return (rec.get('scope') or '').startswith(('hklm', 'common'))


def human_mb(b):
    try:
        b = float(b or 0)
    except (TypeError, ValueError):
        return '-'
    return '%.0f MB' % (b / 1048576) if b < 10 * 1073741824 else '%.1f GB' % (b / 1073741824)


def is_microsoft_path(path):
    p = (path or '').strip('"').lower()
    return p.startswith(('c:\\windows\\', '%systemroot%', '\\systemroot\\', 'system32\\')) or '\\windowsapps\\microsoft.' in p


def command_exe(cmd):
    """Baslangic komutundan calistirilabilir yol: '"C:\\A B\\x.exe" -arg' -> 'C:\\A B\\x.exe'; 'rundll32 a.dll,f' -> 'rundll32'."""
    c = (cmd or '').strip()
    if not c:
        return ''
    if c.startswith('"'):
        end = c.find('"', 1)
        return c[1:end] if end > 0 else c.strip('"')
    m = re.match(r'(.+?\.(?:exe|bat|cmd|com|lnk|vbs|ps1))(?:\s|$)', c, re.I)
    return m.group(1) if m else c.split()[0]


def filter_procs(recs, query='', windowed_only=False, hide_system=False):
    q = (query or '').casefold().strip()
    out = []
    for r in recs:
        if r.get('type') != 'proc':
            continue
        if windowed_only and not r.get('title'):
            continue
        if hide_system and (is_critical_proc(r) or is_microsoft_path(r.get('path'))):
            continue
        if q and q not in ' '.join(str(r.get(k, '')) for k in ('name', 'title', 'path', 'company', 'pid')).casefold():
            continue
        out.append(r)
    out.sort(key=lambda r: (-(r.get('cpu') or 0), -(r.get('mem') or 0)))
    return out


def filter_services(recs, query='', running_only=False, third_party=False):
    q = (query or '').casefold().strip()
    out = []
    for r in recs:
        if r.get('type') != 'svc':
            continue
        if running_only and r.get('state') != 'Running':
            continue
        if third_party and is_microsoft_path(r.get('path')):
            continue
        if q and q not in ' '.join(str(r.get(k, '')) for k in ('name', 'display', 'path', 'desc')).casefold():
            continue
        out.append(r)
    out.sort(key=lambda r: (r.get('state') != 'Running', (r.get('display') or r.get('name') or '').casefold()))
    return out


def b64_items(items):
    """PowerShell'e guvenli aktarim (tek parametre, kacis sorunu yok)."""
    return base64.b64encode(json.dumps(items, ensure_ascii=False).encode('utf-8')).decode('ascii')


def split_by_admin(startups):
    user = [s for s in startups if not startup_needs_admin(s)]
    admin = [s for s in startups if startup_needs_admin(s)]
    return user, admin


def startup_item(rec):
    return {'scope': rec.get('scope'), 'name': rec.get('name')}
