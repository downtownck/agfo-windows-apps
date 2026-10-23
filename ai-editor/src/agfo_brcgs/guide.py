# -*- coding: utf-8 -*-
"""AGFO AI Editor - alt madde kilavuz formlari.

Kaynak: AGFO BRCGS Report Studio 5.2.1 assets/editor.js (v5.0.2 bolumu: howtoFieldsExact, resolveClause, formFor,
assembleText, structOf). Kural: her alt madde YALNIZ kendi kilavuz maddelerini gosterir; ust/bolum yedegi yoktur,
birlesik kutudaki maddeler ortak form paylasmaz. Rapor metni = doldurulan kutular kilavuz sirasiyla.
Alan kaynagi (yalniz birebir madde):
  1. AgfoBrsGuideFields._curated[profil][madde]
  2. knowledge/*_howto.json'daki bu maddenin kural maddeleri (expected_content + must_include)
  3. AgfoBrsGuideFields[profil][madde]
"""
from __future__ import annotations

import functools
import re

from . import coverage as cov
from . import data
from . import i18n

GENERIC_GUIDE_RX = re.compile(r'^Bu bölüm için kılavuzda belirtilen', re.I)
LEGACY_KEY = '_legacy'


def _howto_fields_exact(profile, clause):
    rule = cov.guide_rule_for(profile, clause)
    if not rule or str(rule.get('clause', '')).strip() != str(clause):
        return None
    out = []
    for line in rule.get('expected_content') or []:
        line = str(line or '').strip()
        if line and not GENERIC_GUIDE_RX.match(line):
            out.append({'key': cov.guide_key('g', line), 'label': line, 'type': 'textarea', 'rows': 2})
    for line in rule.get('must_include') or []:
        line = str(line or '').strip()
        if line:
            out.append({'key': cov.guide_key('k', line), 'label': 'Kanıt: ' + line, 'type': 'textarea', 'rows': 2})
    return out or None


@functools.lru_cache(maxsize=None)
def _resolve(profile, clause):
    g = data.guide_fields_all()
    p = data.norm_profile(profile)
    cur = (g.get('_curated') or {}).get(p) or {}
    old = g.get(p) or {}
    c = str(clause or '')
    if cur.get(c):
        return {'fields': cur[c], 'source': 'curated'}
    h = _howto_fields_exact(p, c)
    if h:
        return {'fields': h, 'source': 'guide'}
    if old.get(c):
        return {'fields': old[c], 'source': 'fields'}
    return None


def form_for(profile, clause):
    """{'fields', 'source', 'rule', 'rule_exact'} ya da None (kilavuz icerigi yoksa tek serbest metin kutusu)."""
    r = _resolve(data.norm_profile(profile), str(clause))
    if not r:
        return None
    rule = cov.guide_rule_for(profile, clause)
    return {'fields': r['fields'], 'source': r['source'], 'rule': rule,
            'rule_exact': bool(rule and str(rule.get('clause', '')).strip() == str(clause))}


def struct_of(row):
    """Kayitli yanitlar; 5.0 oncesi duz metin tek 'onceki metin' kutusu olarak tutulur."""
    flags = row.get('flags') or {}
    if isinstance(flags.get('struct'), dict):
        return flags['struct']
    s = {}
    if str(row.get('value') or '').strip():
        s[LEGACY_KEY] = str(row['value'])
    return s


def option_value(opt):
    return opt.get('value') if isinstance(opt, dict) else opt


def option_label(opt):
    return opt.get('label') if isinstance(opt, dict) else opt


def label_of(fd):
    """Ekranda gosterilen soru (Ingilizce)."""
    return i18n.guide(fd.get('label') or fd.get('key') or '')


def report_label_of(fd):
    return i18n.guide(fd.get('report_label') or fd.get('label') or fd.get('key') or '')


def display_value(fd, value):
    """Secim kutusunda saklanan deger (Turkce veri) -> raporda/ekranda gorunen Ingilizce secenek."""
    for o in fd.get('options') or []:
        if str(option_value(o)) == str(value):
            return i18n.guide(option_label(o))
    return i18n.guide(value)


def report_text(row):
    """AI ile yazilmis ya da elle duzeltilmis Ingilizce rapor metni (varsa kutulardan kurulan metnin yerine gecer)."""
    t = (row.get('flags') or {}).get('report_text')
    return t if isinstance(t, str) and t.strip() else ''


def set_report_text(profile, row, text):
    """Rapor metnini elle/AI ile belirler; bos birakilirsa kutulardan kurulan metne doner."""
    flags = row.setdefault('flags', {})
    if str(text or '').strip():
        flags['report_text'] = text
        flags.pop('report_stale', None)
        row['value'] = text
    else:
        flags.pop('report_text', None)
        flags.pop('report_stale', None)
        row['value'] = assemble_text(profile, row, struct_of(row)) if isinstance(flags.get('struct'), dict) else ''
    return row['value']


def assemble_text(profile, row, struct):
    """Rapor metni = dolu kutular kilavuz sirasiyla (varsa once onceki serbest metin)."""
    if not isinstance(struct, dict):
        return ''
    d = form_for(profile, row['clause'])
    parts = []
    legacy = str(struct.get(LEGACY_KEY) or '').strip()
    if legacy:
        parts.append(legacy)
    if d:
        for fd in d['fields']:
            val = str(struct.get(fd['key']) or '').strip()
            if not val:
                continue
            if fd.get('type') == 'select':
                # yalniz "Evet"/"Uygulanamaz" raporda anlamsiz: sorusuyla birlikte yazilir
                val = re.sub(r'[\s?:.]+$', '', report_label_of(fd)) + ': ' + display_value(fd, val)
            parts.append(val)
    else:
        for k, v in struct.items():
            if k == LEGACY_KEY:
                continue
            v = str(v or '').strip()
            if v:
                parts.append(v)
    return '\n\n'.join(parts)


def set_answer(profile, row, key, value):
    """Bir kutuyu yazar ve bolum metnini yeniden kurar."""
    flags = row.setdefault('flags', {})
    struct = flags.get('struct') if isinstance(flags.get('struct'), dict) else struct_of(row)
    flags['struct'] = struct
    struct[key] = value
    if report_text(row):
        # Ingilizce rapor metni korunur; kanit degisti, yeniden yazilmasi gerekebilir
        flags['report_stale'] = True
        row['value'] = flags['report_text']
    else:
        row['value'] = assemble_text(profile, row, struct)
    return row['value']


def fill_counts(profile, row):
    """(dolu, toplam) kilavuz kutusu sayisi; formu olmayan bolumde (dolu?1:0, 1)."""
    d = form_for(profile, row['clause'])
    if not d:
        return (1 if str(row.get('value') or '').strip() else 0), 1
    st = struct_of(row)
    filled = sum(1 for fd in d['fields'] if str(st.get(fd['key']) or '').strip())
    return filled, len(d['fields'])
