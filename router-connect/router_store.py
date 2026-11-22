# -*- coding: utf-8 -*-
"""AGFO Router Connect - router listesi ve ayarlar (yalniz %APPDATA% altinda; depoya girmez)."""
from __future__ import annotations

import json
import os
import pathlib
import shutil

DEFAULTS = {'auto': False, 'interval': 60, 'margin': 10, 'autostart': False}
LIMITS = {'interval': (30, 600), 'margin': (3, 40)}


def data_dir() -> pathlib.Path:
    base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), '.config')
    p = pathlib.Path(base) / 'AGFO' / 'RouterConnect'
    p.mkdir(parents=True, exist_ok=True)
    return p


class Store:
    def __init__(self, path=None):
        self.path = pathlib.Path(path) if path else data_dir() / 'config.json'
        self.routers: list = []
        self.settings: dict = dict(DEFAULTS)
        self.load()

    def load(self):
        for p in (self.path, self.path.with_name(self.path.name + '.bak')):
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            self.routers = [self._clean(r) for r in data.get('routers', []) if isinstance(r, dict) and r.get('ssid')]
            self.settings = dict(DEFAULTS)
            self.settings.update({k: v for k, v in (data.get('settings') or {}).items() if k in DEFAULTS})
            self._clamp()
            return

    @staticmethod
    def _clean(r):
        return {'name': str(r.get('name') or r['ssid']), 'ssid': str(r['ssid']), 'bssid': str(r.get('bssid') or '')}

    def _clamp(self):
        for k, (lo, hi) in LIMITS.items():
            try:
                self.settings[k] = max(lo, min(hi, int(self.settings[k])))
            except (TypeError, ValueError):
                self.settings[k] = DEFAULTS[k]
        self.settings['auto'] = bool(self.settings['auto'])
        self.settings['autostart'] = bool(self.settings['autostart'])

    def save(self):
        self._clamp()
        tmp = self.path.with_name(self.path.name + '.tmp')
        tmp.write_text(json.dumps({'routers': self.routers, 'settings': self.settings}, ensure_ascii=False, indent=2),
                       encoding='utf-8')
        if self.path.exists():
            shutil.copyfile(self.path, self.path.with_name(self.path.name + '.bak'))
        os.replace(tmp, self.path)

    def add(self, ssid, bssid='', name=''):
        """Ayni (ssid, bssid) varsa eklemez; eklenen kaydi ya da None dondurur."""
        from router_wifi import norm_mac
        for r in self.routers:
            if r['ssid'] == ssid and norm_mac(r['bssid']) == norm_mac(bssid):
                return None
        r = self._clean({'name': name or ssid, 'ssid': ssid, 'bssid': bssid})
        self.routers.append(r)
        self.save()
        return r

    def remove(self, router):
        self.routers = [r for r in self.routers if r != router]
        self.save()

    def rename(self, router, name):
        for r in self.routers:
            if r == router:
                r['name'] = name.strip() or r['ssid']
                break
        self.save()

    def set(self, key, value):
        self.settings[key] = value
        self.save()
