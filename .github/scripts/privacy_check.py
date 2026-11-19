# -*- coding: utf-8 -*-
"""Acik depo gizlilik denetimi: kisisel kayitlar (SSH profilleri, parola kasasi, anahtarlar, yerel ayarlar) ve bilinen
kisisel adresler depoya giremez. CI ve System Care testleri calistirir; bulgu varsa cikis kodu 1 olur ve surum cikmaz.

Bilinen kisisel adres / kullanici / makine adlari burada acik yazilmaz: yalnizca SHA-256 ozetleri tutulur, metindeki
IP adresleri, kullanici@adres bicimleri ve kelimeler ozetlenip bu listeyle karsilastirilir.
Kullanim: python -I .github/scripts/privacy_check.py [depo klasoru]
"""
import hashlib
import pathlib
import re
import subprocess
import sys

# Kisisel kayit dosyalari (uygulamalar bunlari yalnizca %LOCALAPPDATA% altinda tutar)
FORBIDDEN_NAMES = re.compile(r'(^|/)(ssh-profiles[^/]*\.json|[^/]*\.dpapi[^/]*|known_hosts[^/]*|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|'
                             r'[^/]*\.(pem|ppk|key|kdbx|ovpn\.auth)|\.env(\.[^/]*)?|credentials[^/]*\.json)$', re.I)
FORBIDDEN_DIRS = re.compile(r'(^|/)(AGFO-MultiSubnet-Scanner|AGFO/SystemCare|AGFO/DriverCare)/', re.I)
PRIVATE_KEY = re.compile(r'-----BEGIN (?:RSA |DSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----')
# Bilinen kisisel degerlerin SHA-256 ozetleri (kucuk harfle). Yeni bir deger eklemek icin: sha256(deger.lower())
KNOWN = {
    '205301ef6a9dd96ea3873384b13b7690bd401dea4df97b12be27c8cc1d1aa5f6',
    'b8936aa391aedfcb4e9333732a68fd57bc3bb489c790e8651ad6ba5868223071',
    '5ebf3233bf75485c4b1b9a46f68fd9c482754f0b54e1623f020c6c5ab971ee4f',
    '2ca8d1b9c0e35cd929d33e347dfb210ec83b110e3e6466ef578ca9349415600a',
}
TOKEN = re.compile(r'[\w.-]+@[\w.-]+|\b\d{1,3}(?:\.\d{1,3}){3}\b|[A-Za-z0-9][A-Za-z0-9-]{5,}')
TEXT_EXT = {'.py', '.pyw', '.ps1', '.psm1', '.cmd', '.bat', '.md', '.txt', '.json', '.yml', '.yaml', '.toml', '.ini', '.cfg',
            '.html', '.js', '.css', '.php', '.sh', '.xml', '.csv', '.iss', '.spec', ''}


def tracked_files(root):
    try:
        out = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], capture_output=True, check=True).stdout
        return [p for p in out.decode('utf-8', 'replace').split('\0') if p]
    except (OSError, subprocess.CalledProcessError):
        return [str(p.relative_to(root)).replace('\\', '/') for p in root.rglob('*')
                if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts]


def scan(root):
    root = pathlib.Path(root).resolve()
    problems = []
    me = pathlib.Path(__file__).resolve()
    for rel in tracked_files(root):
        path = root / rel
        if FORBIDDEN_NAMES.search(rel) or FORBIDDEN_DIRS.search(rel):
            problems.append('%s: kişisel kayıt dosyası depoda olamaz' % rel)
            continue
        if path.resolve() == me or path.suffix.lower() not in TEXT_EXT or not path.is_file():
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        if PRIVATE_KEY.search(text):
            problems.append('%s: özel anahtar içeriyor' % rel)
        for tok in set(TOKEN.findall(text)):
            if hashlib.sha256(tok.lower().encode('utf-8')).hexdigest() in KNOWN:
                problems.append('%s: bilinen kişisel adres/ad içeriyor' % rel)
                break
    return problems


if __name__ == '__main__':
    found = scan(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[2])
    for p in found:
        print('GİZLİLİK: ' + p)
    print('privacy-check: %s' % ('TEMİZ' if not found else '%d bulgu' % len(found)))
    sys.exit(1 if found else 0)
