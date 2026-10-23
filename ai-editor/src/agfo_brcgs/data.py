# -*- coding: utf-8 -*-
"""AGFO AI Editor - BRCGS rapor verisi (Report Studio 5.2.1 veri dosyalari, degistirilmeden).

brcgs_data/ altindaki dosyalar AGFO BRCGS Report Studio eklentisinden birebir kopyalanmistir:
  standards/*_standard.json   standart maddeleri ve kapsam ogeleri (lamba sistemi)
  knowledge/*_howto.json      "How to complete the audit report" kilavuz kurallari
  report-boxes/*_boxes.json   resmi DOCX sablonlarindan uretilmis kutu haritasi (tek otorite)
  guide_fields.json           assets/guide-fields.js nesnesinin node ile alinmis kopyasi
  templates/*.docx            5 resmi BRCGS rapor sablonu
  excel/*.xlsx                cevrimdisi doldurma sablonlari
Elle yazilmis madde listesi yoktur; her sey bu dosyalardan turetilir.
"""
from __future__ import annotations

import functools
import json
import os
import pathlib
import sys

PROFILES = ('fs', 'pm', 'cp', 'ab', 'sd')
PROFILE_LABELS = {
    'pm': 'BRCGS Packaging Materials Issue 7',
    'fs': 'BRCGS Food Safety Issue 9',
    'cp': 'BRCGS Consumer Products Issue 4',
    'ab': 'BRCGS Agents & Brokers Issue 3',
    'sd': 'BRCGS Storage & Distribution Issue 4',
}
PROFILE_SHORT = {'fs': 'FS', 'pm': 'PM', 'cp': 'CP', 'ab': 'AB', 'sd': 'SD'}
STANDARD_FILES = {'fs': 'fs_i9', 'pm': 'pm_i7', 'cp': 'cp_i4', 'ab': 'ab_i3', 'sd': 'sd_i4'}


def data_root() -> pathlib.Path:
    base = getattr(sys, '_MEIPASS', None)
    if base and (pathlib.Path(base) / 'brcgs_data').is_dir():
        return pathlib.Path(base) / 'brcgs_data'
    return pathlib.Path(__file__).resolve().parent.parent / 'brcgs_data'


def _json(rel):
    with open(data_root() / rel, encoding='utf-8') as fh:
        return json.load(fh)


def norm_profile(p) -> str:
    p = str(p or '').strip().lower()
    return p if p in PROFILES else 'pm'


@functools.lru_cache(maxsize=None)
def standard(profile):
    return _json('standards/%s_standard.json' % STANDARD_FILES[norm_profile(profile)])


@functools.lru_cache(maxsize=None)
def knowledge(profile):
    return _json('knowledge/%s_howto.json' % STANDARD_FILES[norm_profile(profile)])


@functools.lru_cache(maxsize=None)
def boxes_spec(profile):
    return _json('report-boxes/%s_boxes.json' % norm_profile(profile))


@functools.lru_cache(maxsize=None)
def guide_fields_all():
    return _json('guide_fields.json')


def template_path(profile) -> pathlib.Path:
    return data_root() / 'templates' / boxes_spec(profile)['template']


def excel_template_path(profile) -> pathlib.Path:
    return data_root() / 'excel' / ('AGFO_BRCGS_%s_Rapor_Sablonu.xlsx' % PROFILE_SHORT[norm_profile(profile)])


def guide_fields(profile, clause):
    """editor.js ile ayni oncelik: _curated[profil][madde], yoksa profil[madde]. Bulunamazsa []."""
    g = guide_fields_all()
    p = norm_profile(profile)
    cur = (g.get('_curated') or {}).get(p) or {}
    if clause in cur:
        return cur[clause]
    return (g.get(p) or {}).get(clause) or []


def profile_from_template_name(name) -> str:
    """class-docx-content-controls.php infer_template_profile() ile ayni kural."""
    n = os.path.basename(str(name or '')).lower()
    if 'f908' in n or 'food' in n:
        return 'fs'
    if 'p703' in n or 'packaging' in n:
        return 'pm'
    if 'cp415' in n or 'consumer' in n:
        return 'cp'
    if 'ab306' in n or 'agents' in n or 'brokers' in n:
        return 'ab'
    if 'sd406' in n or 'storage' in n or 'distribution' in n:
        return 'sd'
    return ''
