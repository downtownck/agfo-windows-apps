# -*- coding: utf-8 -*-
"""AGFO AI Editor - bolum bazinda NC / NA, sayim ve rapor kapanis satirlari.

Tek veri kaynagi: NC'ler project.meta.action_plan.items, NA'lar project.meta.na_clauses (DOCX'in resmi tablolarina
giden listeler). Bir kayit, maddesinin (2.2.2) en uzun on-eki olan rapor bolumune (2.2) aittir; bolum ekraninda
eklenen kayitlarda 'section' alani bunu sabitler.

DOCX'e yazarken bolum metninin sonuna, metinde zaten yoksa (bicim gercek bir FS Issue 9 raporundan alindi):
  - her NC icin  "Minor NC Ref. 2.7.1: <detay>"
  - bolumun tamami uygulanamaz ve metin bossa  "N/A: <gerekce>"  (alt madde NA'lari yalniz resmi NA tablosuna gider)
Uygunsuzluk yoksa sabit bir cumle eklenmez: gercek raporlarda bolum maddeye ozgu bir uygunluk ifadesiyle biter
("Records sampled during the audit were found to be complete, legible ..."); AI metni yazarken bunu kurar.
Bu satirlar kayitli metne yazilmaz; her disa aktarimda verilerden yeniden turetilir.
"""
from __future__ import annotations

import re

TYPES = ('critical', 'major', 'minor', 'fundamental')
TYPE_LABELS = {'critical': 'Critical', 'major': 'Major', 'minor': 'Minor', 'fundamental': 'Fundamental'}
NA_PREFIX = 'N/A: '
COUNT_KEYS = {'critical': 'CRITICAL', 'major': 'MAJOR', 'minor': 'MINOR', 'fundamental': 'FUNDAMENTAL'}

# "Minor NC Ref. 2.7.1: metin" (FS Issue 9 raporu), "Minor NC 2.2.2 : metin", "Major non-conformity 4.4.1 - metin";
# paragraf ortasinda da olabilir. Madde numarasi ve ayirici zorunlu: "The 10 minor non-conformities raised at last
# year's audit ..." gibi siradan cumleler NC sayilmaz. Metin satir sonuna ya da sonraki NC'ye kadar surer.
NC_RX = re.compile(r'\b(Fundamental|Critical|Major|Minor)\s+(?:NC|non[- ]?conformit(?:y|ies))\b\s*(?:(?:Ref|No|Reference)\.?\s*)?'
                   r'(\d+(?:\.\d+)+)\s*[:\-–—]\s*'
                   r'(.*?)(?=\s*\b(?:Fundamental|Critical|Major|Minor)\s+(?:NC|non[- ]?conformit)|\n|$)', re.I)


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
    m = NC_RX.match(t)                          # "Minor NC Ref. 2.2.2: x" bicimindeki tarama satirlarindan yalniz detay
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
    """Sablondaki NC sayac alanlarina (CRITICAL/MAJOR/MINOR[/FUNDAMENTAL]) NC listesinden turetilen sayilari yazar."""
    c = counts(project)
    out = dict(values)
    for t, key in COUNT_KEYS.items():
        if key in field_keys:
            out[key] = str(c[t])
    return out


def nc_line(item):
    return '%s NC Ref. %s: %s' % (TYPE_LABELS[nc_type(item)], norm_clause(item.get('clause')), nc_detail(item))


def na_line(na):
    just = str(na.get('justification') or '').strip()
    return NA_PREFIX + just if just else 'Not applicable'


def _has_nc(text, item):
    c = norm_clause(item.get('clause'))
    for m in NC_RX.finditer(text or ''):
        if m.group(1).lower() == nc_type(item) and (not c or m.group(2) == c):
            return True
    return False


def closing_lines(project, row):
    """Bu bolumun DOCX metnine eklenecek satirlar. Raporun herhangi bir bolumunde zaten yazili olan NC tekrar eklenmez
    (gercek raporlarda bolum 2'nin tum NC'leri tek kutuda, 2.1 metninde durur; 2.7.1 NC'si bos 2.7 satirina eklenmemeli)."""
    text = str(row.get('value') or '')
    everywhere = '\n'.join(str(r.get('value') or '') for r in project.get('sections') or [])
    ncs = [it for it in section_ncs(project, row['clause']) if nc_detail(it)]
    nas = section_nas(project, row['clause'])
    out = []
    whole = [na for na in nas if norm_clause(na.get('clause_ref')) == row['clause']]
    if whole and not text.strip():
        out.append(na_line(whole[0]))
    for it in ncs:
        if not _has_nc(everywhere, it):
            out.append(nc_line(it))
    return out


def with_closing(project, row):
    extra = closing_lines(project, row)
    text = str(row.get('value') or '').rstrip()
    if not extra:
        return text
    return (text + '\n' if text else '') + '\n'.join(extra)


def export_sections(project):
    """DOCX icin bolum kopyalari: kapanis satirlari eklenmis metinle."""
    out = []
    for row in project.get('sections') or []:
        r = dict(row)
        r['value'] = with_closing(project, row)
        out.append(r)
    return out


def scan(project):
    """Bolum metinlerindeki 'Minor NC Ref. 2.2.2: ...' kaliplarini NC listesine ekler (zaten olanlari atlar).
    Donus: {'added': [...], 'existing': n, 'counts': counts(project)}"""
    items = project.setdefault('meta', {}).setdefault('action_plan', {}).setdefault('items', [])
    have = {(nc_type(i), norm_clause(i.get('clause')), re.sub(r'\s+', ' ', nc_detail(i)).lower()) for i in items}
    added, existing = [], 0
    for row in project.get('sections') or []:
        for m in NC_RX.finditer(str(row.get('value') or '')):
            detail = m.group(3).strip()
            if not detail:
                continue
            item = {'type': m.group(1).lower(), 'clause': m.group(2), 'nc_text': detail, 'section': row['clause'],
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
