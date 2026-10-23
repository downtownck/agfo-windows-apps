# -*- coding: utf-8 -*-
"""AGFO AI Editor - bolum bazinda NC / NA, sayim ve rapor kapanis cumleleri.

Tek veri kaynagi: NC'ler project.meta.action_plan.items, NA'lar project.meta.na_clauses (DOCX'in resmi tablolarina
giden listeler). Bir kayit, maddesinin (2.2.2) en uzun on-eki olan rapor bolumune (2.2) aittir; bolum ekraninda
eklenen kayitlarda 'section' alani bunu sabitler.

DOCX'e yazarken her bolum metninin sonuna, metinde zaten yoksa:
  - her NC icin  "Minor NC 2.2.2: <detay>"   (gercek raporlardaki bicim)
  - her NA icin  "Clause 4.9.2 is not applicable: <gerekce>."
  - bolumde NC yoksa ve metin varsa  "No non-conformities were raised against this clause."
eklenir. Bu satirlar kayitli metne yazilmaz; her disa aktarimda verilerden yeniden turetilir.
"""
from __future__ import annotations

import re

TYPES = ('critical', 'major', 'minor', 'fundamental')
TYPE_LABELS = {'critical': 'Critical', 'major': 'Major', 'minor': 'Minor', 'fundamental': 'Fundamental'}
NO_NC_SENTENCE = 'No non-conformities were raised against this clause.'
NA_SENTENCE = 'Clause %s is not applicable: %s'
COUNT_KEYS = {'critical': 'CRITICAL', 'major': 'MAJOR', 'minor': 'MINOR', 'fundamental': 'FUNDAMENTAL'}

# "Minor NC 2.2.2 : metin", "Major non-conformity 4.4.1 - metin", paragraf ortasinda da olabilir; metin satir sonuna
# ya da bir sonraki NC baslangicina kadar surer. Siradan "uygunsuzluk" gecen cumleler NC sayilmaz.
NC_RX = re.compile(r'\b(Fundamental|Critical|Major|Minor)\s+(?:NC|non[- ]?conformit(?:y|ies))\b\s*(\d+(?:\.\d+)*)?\s*[:\-–—]?\s*'
                   r'(.*?)(?=\s*\b(?:Fundamental|Critical|Major|Minor)\s+(?:NC|non[- ]?conformit)|\n|$)', re.I)


def _clause_key(c):
    return [int(x) if x.isdigit() else x for x in str(c or '').strip().split('.') if x != '']


def norm_clause(c):
    c = str(c or '').strip().rstrip('.')
    m = re.match(r'^\d+(?:\.\d+)*', c)
    return m.group(0) if m else c


def section_for_clause(sections, clause):
    """En uzun on-ek eslesmesi: 2.2.2 -> '2.2' bolumu (nokta sinirinda); yoksa None."""
    c = norm_clause(clause)
    best = None
    for row in sections:
        rc = str(row.get('clause') or '')
        if c == rc or c.startswith(rc + '.'):
            if best is None or len(rc) > len(best):
                best = rc
    return best


def item_section(sections, item, clause_field):
    sec = str(item.get('section') or '')
    if sec and any(str(r.get('clause')) == sec for r in sections):
        return sec
    return section_for_clause(sections, item.get(clause_field))


def section_ncs(project, clause):
    secs = project.get('sections') or []
    items = ((project.get('meta') or {}).get('action_plan') or {}).get('items') or []
    return [it for it in items if item_section(secs, it, 'clause') == clause]


def section_nas(project, clause):
    secs = project.get('sections') or []
    return [na for na in (project.get('meta') or {}).get('na_clauses') or [] if item_section(secs, na, 'clause_ref') == clause]


def nc_type(item):
    t = str(item.get('type') or 'minor').strip().lower()
    return t if t in TYPES else 'minor'


def nc_detail(item):
    t = str(item.get('nc_text') or item.get('detail') or '').strip()
    m = NC_RX.match(t)                          # "Minor NC 2.2.2 : x" bicimindeki tarama satirlarindan yalniz detay
    return (m.group(3).strip() if m and m.group(3).strip() else t)


def counts(project):
    out = {t: 0 for t in TYPES}
    for it in ((project.get('meta') or {}).get('action_plan') or {}).get('items') or []:
        if nc_detail(it):
            out[nc_type(it)] += 1
    out['na'] = sum(1 for na in (project.get('meta') or {}).get('na_clauses') or [] if str(na.get('clause_ref') or '').strip())
    out['total'] = sum(out[t] for t in TYPES)
    return out


def count_text(c, profile=None):
    types = list(TYPES) if profile in ('fs', 'pm', 'cp') or c.get('fundamental') else ['critical', 'major', 'minor']
    return ' · '.join('%s %d' % (TYPE_LABELS[t], c[t]) for t in types) + ' · NA %d' % c['na']


def apply_count_fields(values, project, field_keys):
    """Sablonda sayac alani varsa (CP/AB: CRITICAL/MAJOR/MINOR[/FUNDAMENTAL]) NC listesinden turetilen sayilari yazar."""
    c = counts(project)
    out = dict(values)
    for t, key in COUNT_KEYS.items():
        if key in field_keys:
            out[key] = str(c[t])
    return out


def nc_line(item):
    clause = norm_clause(item.get('clause')) or ''
    return ('%s NC %s: %s' % (TYPE_LABELS[nc_type(item)], clause, nc_detail(item))).replace('NC : ', 'NC: ')


def na_line(na):
    just = str(na.get('justification') or '').strip().rstrip('.')
    return (NA_SENTENCE % (norm_clause(na.get('clause_ref')), just) + '.') if just else \
        'Clause %s is not applicable.' % norm_clause(na.get('clause_ref'))


def _has_nc(text, item):
    c = norm_clause(item.get('clause'))
    for m in NC_RX.finditer(text or ''):
        if m.group(1).lower() == nc_type(item) and (not c or (m.group(2) or '') == c):
            return True
    return False


def closing_lines(project, row):
    """Bu bolumun DOCX metnine eklenecek satirlar (metinde zaten olanlar atlanir)."""
    text = str(row.get('value') or '')
    low = text.lower()
    ncs = [it for it in section_ncs(project, row['clause']) if nc_detail(it)]
    nas = [na for na in section_nas(project, row['clause']) if str(na.get('clause_ref') or '').strip()]
    out = []
    for na in nas:
        line = na_line(na)
        if line.lower().rstrip('.') not in low:
            out.append(line)
    for it in ncs:
        if not _has_nc(text, it):
            out.append(nc_line(it))
    if not ncs and text.strip() and not NC_RX.search(text) and 'no non-conformit' not in low:
        out.append(NO_NC_SENTENCE)
    return out


def with_closing(project, row):
    extra = closing_lines(project, row)
    text = str(row.get('value') or '').rstrip()
    if not extra:
        return text
    return (text + '\n\n' if text else '') + '\n'.join(extra)


def export_sections(project):
    """DOCX icin bolum kopyalari: kapanis cumleleri eklenmis metinle."""
    out = []
    for row in project.get('sections') or []:
        r = dict(row)
        r['value'] = with_closing(project, row)
        out.append(r)
    return out


def scan(project):
    """Bolum metinlerindeki 'Minor NC 2.2.2: ...' kalıplarini NC listesine ekler (zaten olanlari atlar).
    Donus: {'added': [...], 'existing': n, 'counts': counts(project)}"""
    items = project.setdefault('meta', {}).setdefault('action_plan', {}).setdefault('items', [])
    have = {(nc_type(i), norm_clause(i.get('clause')), re.sub(r'\s+', ' ', nc_detail(i)).lower()) for i in items}
    added, existing = [], 0
    for row in project.get('sections') or []:
        for m in NC_RX.finditer(str(row.get('value') or '')):
            detail = m.group(3).strip()
            if not detail:
                continue
            item = {'type': m.group(1).lower(), 'clause': m.group(2) or row['clause'], 'nc_text': detail, 'section': row['clause'],
                    'correction': '', 'root_cause': '', 'proposed_preventive_action': '', 'date_reviewed': '', 'reviewed_by': '',
                    'source': 'scan'}
            k = (item['type'], norm_clause(item['clause']), re.sub(r'\s+', ' ', detail).lower())
            if k in have:
                existing += 1
                continue
            have.add(k)
            items.append(item)
            added.append(item)
    return {'added': added, 'existing': existing, 'counts': counts(project)}
