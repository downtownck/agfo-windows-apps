# -*- coding: utf-8 -*-
"""Kullanici verisinin nerede durdugu ve uygulama ayarlari.

Veri %APPDATA%\\AGFO\\Mihenk altinda tutulur; uygulama kaldirilinca silinmez.
Ayarlar JSON, kayitlar SQLite. MIHENK_DATA_DIR ortam degiskeni testlerde ve
tasinabilir kullanimda bu klasoru degistirir.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile

import mihenk_core as core

DEFAULT_SETTINGS = {
    'theme': 'light',
    'default_lead_days': 14,
    'date_format': '%Y-%m-%d',
    'confirm_destructive': True,
    'last_screen': 'dashboard',
    'operator': '',
    'scan_on_start': True,
    'window': '',
    'first_run_done': False,
    'modern_ui': True,
    'report_period': '365',
}


def ui_lib_dir():
    """Modern gorunum bileseninin kuruldugu klasor."""
    return data_dir() / 'ui-lib'


def data_dir() -> pathlib.Path:
    """Kullanici verisi klasoru. Yoksa olusturur."""
    override = os.environ.get('MIHENK_DATA_DIR')
    if override:
        p = pathlib.Path(override)
    else:
        base = os.environ.get('APPDATA') or os.environ.get('XDG_CONFIG_HOME') or str(pathlib.Path.home())
        p = pathlib.Path(base) / 'AGFO' / core.DATA_FOLDER
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> pathlib.Path:
    """Kayit veritabani dosyasi."""
    return data_dir() / 'mihenk.sqlite3'


def settings_path() -> pathlib.Path:
    return data_dir() / 'settings.json'


def backups_dir() -> pathlib.Path:
    p = data_dir() / 'backups'
    p.mkdir(parents=True, exist_ok=True)
    return p


def exports_dir() -> pathlib.Path:
    p = data_dir() / 'exports'
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_settings() -> dict:
    """Ayarlari okur; dosya bozuksa varsayilanlara doner, dosyayi silmez."""
    out = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(), encoding='utf-8') as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in DEFAULT_SETTINGS:
                    out[key] = value
    except (OSError, ValueError):
        pass
    return out


def save_settings(values: dict) -> None:
    """Ayarlari atomik yazar: yarim dosya birakmaz."""
    merged = load_settings()
    for key, value in (values or {}).items():
        if key in DEFAULT_SETTINGS:
            merged[key] = value
    target = settings_path()
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix='.settings-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def setting(key: str, default=None):
    """Tek bir ayari okur."""
    values = load_settings()
    if key in values:
        return values[key]
    return default
