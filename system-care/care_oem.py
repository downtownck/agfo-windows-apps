# -*- coding: utf-8 -*-
"""System Care 4.1 — Uretici destegi (HP, Lenovo, Dell, ASUS, Acer, Sony/VAIO, MSI, Casper, Monster ...) ve NVIDIA surucu
kurma/kaldirma icin arayuzden bagimsiz yardimcilar (testler dogrudan cagirir).

Uretici: model ve seri numarasi Windows'tan okunur (care_tasks.ps1 oem-info); uygun oldugunda dogrudan urun sayfasi
(Dell servis etiketi, ASUS model sayfasi), degilse uretici resmi surucu sayfasi + seri/model panoya kopyalanir;
her durumda uretici alan adiyla sinirli web aramasi ve ureticinin kendi guncelleme araci (WinGet / Microsoft Store) sunulur.

NVIDIA: GPU modeli -> urun ailesi kimligi (ZenitH-AT/nvidia-data, kamu mali; assets/nvidia-data.json), NVIDIA'nin kendi
surucu arama servisi (AjaxDriverService, nvidia-update MIT betigindeki yontem) -> son surucu surumu ve indirme adresi.
Kurulum NVIDIA'nin belgelenmis sessiz parametreleriyle; kaldirma NVIDIA'nin kendi kaldiricisi, Windows surucu deposu
(pnputil) ya da acik kaynak Display Driver Uninstaller (MIT) ile.
"""
from __future__ import annotations

import json
import pathlib
import re
from urllib.parse import quote, quote_plus

# --------------------------------------------------------------------------- uretici tablosu
# key: (ad, eslesme kaliplari, surucu sayfasi, alan adi, dogrudan sayfa sablonu | None, araclar [(ad, kaynak, kimlik, not)])
VENDORS = {
    'dell': ('Dell', (r'\bdell\b', r'alienware'), 'https://www.dell.com/support/home/tr-tr', 'dell.com',
             'https://www.dell.com/support/home/tr-tr/product-support/servicetag/{serial}/drivers',
             [('Dell Command | Update', 'winget', 'Dell.CommandUpdate.Universal', 'Dell sürücü ve BIOS güncellemelerini otomatik bulur')]),
    'hp': ('HP', (r'^hp\b', r'hewlett', r'\bhp inc'), 'https://support.hp.com/tr-tr/drivers', 'hp.com', None,
           [('HP Support Assistant', 'winget', 'HP.SupportAssistant', 'ev ve küçük iş bilgisayarları'),
            ('HP Image Assistant', 'winget', 'HP.ImageAssistant', 'kurumsal (EliteBook, ProBook, Z) modeller')]),
    'lenovo': ('Lenovo', (r'lenovo',), 'https://pcsupport.lenovo.com/tr/tr', 'lenovo.com', None,
               [('Lenovo Vantage', 'msstore', '9WZDNCRFJ4MV', 'IdeaPad, Yoga, Legion, LOQ'),
                ('Lenovo System Update', 'winget', 'Lenovo.SystemUpdate', 'ThinkPad, ThinkCentre, ThinkBook')]),
    'asus': ('ASUS', (r'asus',), 'https://www.asus.com/tr/support/download-center/', 'asus.com',
             'https://www.asus.com/tr/supportonly/{model_l}/helpdesk_download/',
             [('MyASUS', 'msstore', '9N7R5S6B0ZZH', 'sürücü, BIOS ve sistem güncellemeleri')]),
    'acer': ('Acer', (r'\bacer\b', r'gateway', r'packard bell'), 'https://www.acer.com/tr-tr/support/drivers-and-manuals', 'acer.com', None, []),
    'sony': ('Sony VAIO', (r'\bsony\b',), 'https://www.sony.com.tr/electronics/support', 'sony.com.tr', None, []),
    'vaio': ('VAIO', (r'^vaio',), 'https://vaio.com/support/', 'vaio.com', None, []),
    'msi': ('MSI', (r'micro-star', r'\bmsi\b'), 'https://tr.msi.com/support/download', 'msi.com', None,
            [('MSI Center', 'winget', 'MSI.MSICenter', 'MSI dizüstü ve masaüstü')]),
    'microsoft': ('Microsoft Surface', (r'^microsoft',), 'https://support.microsoft.com/tr-tr/surface/surface-sürücüleri-ve-üretici-yazılımını-indirme-'
                  '05a278b6-0d4f-42e2-b1fa-c5c7b4f1d4ec', 'microsoft.com', None, []),
    'samsung': ('Samsung', (r'samsung',), 'https://www.samsung.com/tr/support/', 'samsung.com', None, []),
    'toshiba': ('Dynabook / Toshiba', (r'toshiba', r'dynabook'), 'https://support.dynabook.com/', 'dynabook.com', None, []),
    'fujitsu': ('Fujitsu', (r'fujitsu',), 'https://support.ts.fujitsu.com/', 'fujitsu.com', None, []),
    'huawei': ('Huawei', (r'huawei',), 'https://consumer.huawei.com/tr/support/', 'huawei.com', None, []),
    'gigabyte': ('GIGABYTE', (r'gigabyte',), 'https://www.gigabyte.com/tr/Support', 'gigabyte.com', None, []),
    'asrock': ('ASRock', (r'asrock',), 'https://www.asrock.com/support/index.asp', 'asrock.com', None, []),
    'casper': ('Casper', (r'casper',), 'https://www.casper.com.tr/', 'casper.com.tr', None, []),
    'monster': ('Monster Notebook', (r'monster',), 'https://www.monsternotebook.com.tr/', 'monsternotebook.com.tr', None, []),
    'medion': ('MEDION', (r'medion',), 'https://www.medion.com/tr/service/', 'medion.com', None, []),
    'razer': ('Razer', (r'razer',), 'https://mysupport.razer.com/', 'razer.com', None, []),
}
COMPONENT_TOOLS = [('Intel Driver & Support Assistant', 'winget', 'Intel.IntelDriverAndSupportAssistant', 'Intel işlemci, grafik, Wi-Fi ve Bluetooth')]
GENERIC_MAKERS = re.compile(r'^(system manufacturer|to be filled|default string|o\.?e\.?m\.?|not applicable|none|unknown|$)', re.I)
GENERIC_SERIAL = re.compile(r'^(to be filled|default string|system serial|0+|none|not specified|123456789|chassis serial)', re.I)


def vendor_key(maker):
    m = (maker or '').strip().lower()
    for key, v in VENDORS.items():
        if any(re.search(p, m) for p in v[1]):
            return key
    return None


def _asus_model(model):
    """ASUS WMI modeli 'VivoBook_ASUSLaptop X412FA_X412FA' / 'ASUS TUF Gaming F15 FX506HC_FX506HC' -> 'X412FA' / 'FX506HC'."""
    m = (model or '').strip()
    if '_' in m:
        m = m.rsplit('_', 1)[-1]
    else:
        m = m.split()[-1] if m.split() else m
    return re.sub(r'[^A-Za-z0-9-]', '', m)


def identify(rec):
    """oem-info kaydi -> {vendor, name, model, serial, sku, board, generic, notebook}. Ozel toplama masaustunde anakart ureticisi kullanilir."""
    maker = (rec.get('maker') or '').strip()
    model = (rec.get('model') or '').strip()
    friendly = (rec.get('family') or '').strip()       # Lenovo: Win32_ComputerSystemProduct.Version (ör. 'ThinkPad T14 Gen 3')
    serial = (rec.get('serial') or '').strip()
    board_maker, board = (rec.get('board_maker') or '').strip(), (rec.get('board') or '').strip()
    generic = bool(GENERIC_MAKERS.match(maker)) or vendor_key(maker) is None and bool(board_maker) and vendor_key(board_maker) is not None \
        and bool(GENERIC_MAKERS.match(model) or not model)
    key = vendor_key(maker)
    if generic or key is None:
        bk = vendor_key(board_maker)
        if bk:
            key, model, generic = bk, board, True
    if key == 'lenovo' and friendly and not friendly.lower().startswith('lenovo product'):
        model = '%s (%s)' % (friendly, model) if model and model not in friendly else friendly
    if GENERIC_SERIAL.match(serial):
        serial = ''
    v = VENDORS.get(key)
    return {'vendor': key, 'name': v[0] if v else (maker or 'Bilinmeyen üretici'), 'model': model, 'serial': serial,
            'sku': (rec.get('sku') or '').strip(), 'maker': maker, 'board': ('%s %s' % (board_maker, board)).strip(), 'generic': generic,
            'notebook': bool(rec.get('notebook'))}


def support_links(info):
    """-> {'direct': url|None, 'drivers': url, 'search': url, 'copy': metin (panoya), 'copy_label': str}"""
    v = VENDORS.get(info.get('vendor'))
    model, serial = info.get('model') or '', info.get('serial') or ''
    if not v:
        q = '%s %s driver download' % (info.get('maker') or '', model)
        return {'direct': None, 'drivers': 'https://www.google.com/search?q=' + quote_plus(q.strip()), 'search': None,
                'copy': model, 'copy_label': 'model'}
    name, _pats, drivers, domain, direct_t, _tools = v
    direct = None
    if direct_t:
        if '{serial}' in direct_t and serial and not info.get('generic'):
            direct = direct_t.format(serial=quote(serial))
        elif '{model_l}' in direct_t and not info.get('generic'):
            am = _asus_model(model)
            if am:
                direct = direct_t.format(model_l=quote(am.lower()))
    plain_model = re.sub(r'\s*\(.*\)$', '', model)
    search = 'https://www.google.com/search?q=' + quote_plus('%s %s sürücü site:%s' % (name.split(' /')[0], plain_model or serial, domain))
    if info.get('generic'):
        copy, label = model, 'anakart modeli'
    elif info.get('vendor') in ('hp', 'lenovo', 'acer', 'dell') and serial:
        copy, label = serial, 'seri numarası'
    else:
        copy, label = model or serial, 'model'
    return {'direct': direct, 'drivers': drivers, 'search': search, 'copy': copy, 'copy_label': label}


def vendor_tools(info):
    v = VENDORS.get(info.get('vendor'))
    tools = list(v[5]) if v else []
    return tools + COMPONENT_TOOLS


def tool_install_cmd(winget, source, pkg_id):
    """Microsoft Store uygulamalari yonetici baglaminda kurulamaz; uygulama normal kullaniciyla calistigi icin dogrudan winget."""
    if source == 'msstore':
        return [winget, 'install', '--id', pkg_id, '--source', 'msstore', '--accept-source-agreements', '--accept-package-agreements',
                '--disable-interactivity']
    return [winget, 'install', '--id', pkg_id, '--exact', '--source', 'winget', '--silent', '--accept-source-agreements',
            '--accept-package-agreements', '--disable-interactivity']


# --------------------------------------------------------------------------- NVIDIA
NV_LOOKUP = 'https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/AjaxDriverService.php?func=DriverManualLookup&pfid={pfid}&osID={os}&dch={dch}'
NV_DATA_URL = 'https://raw.githubusercontent.com/ZenitH-AT/nvidia-data/main/gpu-data.json'
NV_HOSTS = ('geforce.com', 'nvidia.com', 'githubusercontent.com')
NV_DRIVER_PAGE = 'https://www.nvidia.com/tr-tr/drivers/'
DDU_PKG = 'Wagnardsoft.DisplayDriverUninstaller'
SEVENZIP_PKG = '7zip.7zip'
MIN_FILES = ['Display.Driver', 'NVI2', 'EULA.txt', 'ListDevices.txt', 'setup.cfg', 'setup.exe']   # nvidia-update (MIT) ile ayni yalin kurulum
_CLEAN_NAME = re.compile(r'(?<=NVIDIA )(.*(?= \([A-Z]+\))|.*(?= [0-9]+GB)|.*(?= COLLECTORS EDITION)|.*(?= with Max-Q Design)|.*)')


def nv_version(windows_driver_version):
    """Windows surucu surumu '32.0.15.6094' -> NVIDIA surumu '560.94' (son 5 rakam)."""
    digits = (windows_driver_version or '').replace('.', '')
    if len(digits) < 5 or not digits.isdigit():
        return ''
    d = digits[-5:]
    return '%s.%s' % (d[:3].lstrip('0') or '0', d[3:])


def nv_clean_name(name):
    m = _CLEAN_NAME.search(name or '')
    return m.group(0).replace('Super', 'SUPER').strip() if m and (name or '').upper().startswith('NVIDIA') else ''


def load_nv_data(path=None):
    p = pathlib.Path(path) if path else pathlib.Path(__file__).resolve().parent / 'assets' / 'nvidia-data.json'
    return json.loads(p.read_text(encoding='utf-8'))


def nv_pfid(data, gpu_name, notebook):
    name = nv_clean_name(gpu_name) or gpu_name
    gpus = data.get('gpu', data)
    for kind in (('notebook', 'desktop') if notebook else ('desktop', 'notebook')):
        pid = (gpus.get(kind) or {}).get(name)
        if pid:
            return str(pid), kind
    return None, None


def nv_os_id(data, build, x64=True):
    """Windows 11 (derleme >= 22000) ve 10 64-bit ayni surucuyu kullanir; NVIDIA kimlikleri: 135 (Win 11), 57 (Win 10 64-bit)."""
    oss = data.get('os', [])
    want = 'Windows 11' if (build or 0) >= 22000 else ('Windows 10 64-bit' if x64 else 'Windows 10 32-bit')
    for o in oss:
        if o.get('name') == want:
            return str(o['id'])
    return '57'


def nv_lookup_url(pfid, os_id, dch=True):
    return NV_LOOKUP.format(pfid=pfid, os=os_id, dch=int(bool(dch)))


def nv_parse_lookup(payload):
    """AjaxDriverService yaniti -> {'version', 'url', 'name', 'date', 'details', 'size'} | None."""
    d = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
    if not isinstance(d, dict) or str(d.get('Success')) != '1' or not d.get('IDS'):
        return None
    info = (d['IDS'][0] or {}).get('downloadInfo') or {}
    url = info.get('DownloadURL') or ''
    if not url.startswith('https://') or not re.search(r'\.exe$', url, re.I):
        return None
    from urllib.parse import unquote
    return {'version': str(info.get('Version') or ''), 'url': url, 'name': unquote(str(info.get('Name') or '')).replace('+', ' '),
            'date': str(info.get('ReleaseDateTime') or ''), 'details': str(info.get('DetailsURL') or ''), 'size': str(info.get('DownloadURLFileSize') or '')}


def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split('.'))
    except ValueError:
        return ()


def nv_install_cmd(exe, clean=False, minimal_setup=None):
    """Tam paket: '<surucu>.exe -s -noreboot'; yalin kurulum (cikarilmis setup.exe): NVIDIA'nin belgelenmis sessiz parametreleri."""
    if minimal_setup:
        cmd = [str(minimal_setup), '-passive', '-noreboot', '-noeula', '-nofinish', '-s']
    else:
        cmd = [str(exe), '-s', '-noreboot']
    if clean:
        cmd.append('-clean')
    return cmd


def nv_extract_cmd(sevenzip, exe, dest):
    return [str(sevenzip), 'x', '-y', '-aoa', str(exe), '-o' + str(dest)] + MIN_FILES


def strip_setup_cfg(text):
    """Yalin kurulumda cikarilmayan EULA/gizlilik dosyalarina bagimliliklari setup.cfg'den kaldirir (nvidia-update ile ayni)."""
    return '\n'.join(l for l in text.splitlines() if not re.search(r'name="\$\{\{(EulaHtmlFile|FunctionalConsentFile|PrivacyPolicyFile)\}\}', l)) + '\n'


def ddu_cmd(exe, restart=True, physx=True, nvapp=True, restore_point=True):
    cmd = [str(exe), '-silent', '-cleannvidia', '-nosafemodemsg']
    if physx:
        cmd.append('-removephysx')
    if nvapp:
        cmd.append('-removegfe')
    if restore_point:
        cmd.append('-createsystemrestorepoint')
    if restart:
        cmd.append('-restart')
    return cmd
