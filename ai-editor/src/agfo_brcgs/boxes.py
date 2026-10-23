# -*- coding: utf-8 -*-
"""AGFO AI Editor - resmi rapor kutulari ve calisma bolumleri.

Kaynak: AGFO BRCGS Report Studio 5.2.1
  includes/class-report-boxes.php   (merge_for_export, split_import, na_rows_for_export, export_note)
  includes/class-section-builder.php (sections_for_profile, merge_imported, compare_clauses, short_title)
  includes/class-repository.php      (sort_sections_numeric)
Kural (docs/report-box-specification.md): rapor yazilirken madde bazli (bolunmus), DOCX'e yazilirken resmi
kutulara birlestirilir, DOCX'ten okunurken yeniden ayrilir. Harita report-boxes/*.json'dan gelir, elle liste yok.
"""
from __future__ import annotations

import functools
import re

from . import data

HEADING_GLUE = ' '
_PLACEHOLDER_RX = re.compile(r'^(click or tap here to enter text\.?|choose an item\.?|please select|select a date\.?|'
                             r'clause/section ref|justification|enter text)$', re.I)


def normalize_clause(clause) -> str:
    c = re.sub(r'[^0-9.]', '', str(clause or '').strip())
    return c.strip('.')


def compare_key(clause):
    """compare_clauses(): sayisal parca sirasi, esitlikte metin."""
    parts = []
    for p in str(clause).split('.'):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return parts, str(clause)


def sort_clauses(clauses):
    return sorted(clauses, key=compare_key)


def is_placeholder(value) -> bool:
    v = str(value or '').strip()
    return v == '' or bool(_PLACEHOLDER_RX.match(v))


def short_title(title) -> str:
    t = re.sub(r'\s+', ' ', str(title or '')).strip()
    if len(t) > 140:
        cut = t[:140]
        sp = cut.rfind(' ')
        if sp > 60:
            cut = cut[:sp]
        return cut + '…'
    return t


# ----------------------------------------------------------------------------- harita
def units(profile):
    return list(data.boxes_spec(profile).get('units') or [])


def boxes(profile):
    return list(data.boxes_spec(profile).get('boxes') or [])


@functools.lru_cache(maxsize=None)
def _box_index(profile):
    return {str(b['tag']): b for b in boxes(profile)}


@functools.lru_cache(maxsize=None)
def _unit_index(profile):
    return {str(u['key']): u for u in units(profile)}


def box_by_tag(profile, tag):
    return _box_index(data.norm_profile(profile)).get(str(tag))


def unit(profile, clause):
    return _unit_index(data.norm_profile(profile)).get(normalize_clause(clause))


def box_tag_for_clause(profile, clause) -> str:
    u = unit(profile, clause)
    return str(u['box']) if u else ''


def siblings_for_clause(profile, clause):
    tag = box_tag_for_clause(profile, clause)
    if not tag:
        return []
    return [u for u in units(profile) if str(u['box']) == tag]


def unmapped_clauses(profile):
    v = data.boxes_spec(profile).get('unmapped_clauses')
    return list(v) if isinstance(v, list) else []


def detail_tags(profile):
    return set(_box_index(data.norm_profile(profile)))


def na_tags(profile):
    return {str(b['na_tag']) for b in boxes(profile) if b.get('na_tag')}


def optional_modules(profile):
    spec = data.boxes_spec(profile)
    mods = spec.get('optional_modules') if isinstance(spec.get('optional_modules'), dict) else {}
    return mods


def module_units(profile, module):
    return sort_clauses([str(u['key']) for u in units(profile) if str(u.get('optional_module') or '') == str(module)])


def chapter_of(clause) -> str:
    return str(clause).split('.')[0]


def chapter_title(profile, chapter) -> str:
    """editor.js chapterTitle(): standardin bolum listesi, yoksa istege bagli modul basligi."""
    std = data.standard(profile)
    for ch in std.get('chapters') or []:
        if isinstance(ch, dict) and str(ch.get('chapter')) == str(chapter):
            return ch.get('title') or ''
    for key, mod in optional_modules(profile).items():
        if any(chapter_of(u['key']) == str(chapter) for u in units(profile) if str(u.get('optional_module') or '') == str(key)):
            return mod.get('title') or ''
    return ''


# ----------------------------------------------------------------------------- bolumler
def _row(clause, title, sort_order, **extra):
    r = {'clause': str(clause), 'title': str(title), 'value': '', 'note': '', 'sort_order': int(sort_order), 'tag': '',
         'part': '', 'sdt_index': '', 'coverage_parent': '', 'source_key': '', 'flags': {}}
    r.update(extra)
    return r


def sections_for_profile(profile):
    """Yeni raporun bolum iskeleti: kutu haritasindaki yazim birimleri (istege bagli moduller haric)."""
    p = data.norm_profile(profile)
    secs = data.standard(p).get('sections') or {}
    out = []
    i = 0
    for u in units(p):
        if u.get('optional_module'):
            continue
        key = str(u['key'])
        d = secs.get(key) if isinstance(secs.get(key), dict) else {}
        title = short_title(u['title']) if str(u.get('title') or '').strip() else (
            short_title(d['title']) if d.get('title') else 'Section ' + key)
        out.append(_row(key, title, i, coverage_parent=str(d.get('coverage_parent') or ''), part='report-box',
                        tag=str(u['box']), sdt_index='box_%s_%s' % (p, key.replace('.', '_')),
                        flags={'box': str(u['box']), 'unit_source': str(u.get('source') or '')}))
        i += 1
    return sort_sections(out)                            # 4.1.2: okuma aninda gercek sayisal sira


def module_row(profile, key):
    """editor.js makeModuleRow()."""
    p = data.norm_profile(profile)
    u = unit(p, key) or {}
    tag = str(u.get('box') or '')
    return _row(key, u.get('title') or key, 0, tag=tag, part='report-box',
                sdt_index='box_%s_%s' % (p, key.replace('.', '_')),
                flags={'box': tag, 'unit_source': 'module' + str(u.get('optional_module') or '')})


def sort_sections(rows):
    out = sorted(rows, key=lambda r: compare_key(r.get('clause', '')))
    for i, r in enumerate(out):
        r['sort_order'] = i
    return out


def merge_imported(profile, imported):
    """DOCX'ten okunan satirlari iskelete yerlestirir; okunan metin kazanir, iskelet hicbir kutuyu kaybettirmez."""
    skeleton = sections_for_profile(profile)
    imported = split_import(profile, imported or [])
    by_clause = {r['clause']: r for r in skeleton}
    order = list(by_clause)
    for i, row in enumerate(imported):
        clause = str(row.get('clause') or '').strip() or 'index_%d' % i
        value = str(row.get('value') or '')
        if is_placeholder(value):
            value = ''
        if clause not in by_clause:
            u = unit(profile, clause)
            if u and u.get('optional_module'):
                by_clause[clause] = module_row(profile, clause)
            else:
                by_clause[clause] = _row(clause, str(row.get('title') or ''), len(order))
            order.append(clause)
        t = by_clause[clause]
        if value:
            t['value'] = value
        if row.get('title') and not str(t['title']).strip():
            t['title'] = str(row['title'])
        for k in ('tag', 'part', 'sdt_index', 'coverage_parent'):
            if row.get(k):
                t[k] = str(row[k])
        if row.get('key'):
            t['source_key'] = str(row['key'])
    return sort_sections([by_clause[c] for c in order])


# ----------------------------------------------------------------------------- DOCX'e yazma (birlestirme)
def merge_for_export(profile, sections):
    """{'rows': [...], 'skipped': [...], 'merged': {tag: [maddeler]}} - class-report-boxes.php ile ayni."""
    p = data.norm_profile(profile)
    stored = {}
    for row in sections or []:
        key = normalize_clause(row.get('clause'))
        if key:
            stored[key] = {'value': str(row.get('value') or ''), 'title': str(row.get('title') or '')}
    buckets, skipped = {}, []
    for u in units(p):
        key, tag = str(u['key']), str(u['box'])
        value = stored.get(key, {}).get('value', '').strip()
        if not value:
            continue
        if not tag:
            skipped.append(key)
            continue
        title = str(u['title']) if str(u.get('title') or '').strip() else stored[key]['title']
        buckets.setdefault(tag, []).append({'clause': key, 'title': title, 'value': value})
    rows, merged = [], {}
    for tag, box in _box_index(p).items():
        parts = buckets.get(tag)
        if not parts:
            continue
        if len(parts) == 1 and not box.get('module'):
            text = parts[0]['value']
        else:
            text = '\n\n'.join((part['clause'] + HEADING_GLUE + part['title']).strip() + '\n' + part['value'] for part in parts)
            merged[tag] = [part['clause'] for part in parts]
        rows.append({'clause': str(box['clause']), 'title': str(box['title']), 'value': text, 'tag': tag,
                     'detail_index': int(box.get('order') or 0), 'merged_from': [part['clause'] for part in parts]})
    return {'rows': rows, 'skipped': skipped, 'merged': merged}


def _title_fingerprint(title) -> str:
    t = str(title or '').strip().lower()
    t = re.sub(r'[^a-z0-9çğıöşü ]+', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def split_merged_text(text, box_units):
    """Birlesik kutuyu basliklarindan boler. Baslik = madde no + o birimin TAM basligi (ya da yalniz madde no)."""
    text = str(text or '')
    if not text.strip() or not box_units:
        return {}
    titles = {str(u['key']): _title_fingerprint(u.get('title') or '') for u in box_units}
    out, current, buf, found = {}, '__preamble', [], False
    for line in re.split(r'\r\n|\r|\n', text):
        probe = line.strip()
        key = ''
        m = re.match(r'^(\d+(?:\.\d+)*)(?:[.)]|\s|$)', probe) if probe and len(probe.encode('utf-8')) <= 220 else None
        if m:
            cand = m.group(1).strip('.')
            if cand in titles:
                rest = _title_fingerprint(probe[len(m.group(1)):])
                if rest == '' or rest == titles[cand]:
                    key = cand
        if key:
            if buf:
                out[current] = '\n'.join(buf).strip()
            current, buf, found = key, [], True
            continue
        buf.append(line)
    if buf:
        out[current] = '\n'.join(buf).strip()
    if not found:
        return {}
    return {k: v for k, v in out.items() if str(v).strip()}


def split_import(profile, imported):
    p = data.norm_profile(profile)
    bx = _box_index(p)
    by_box = {}
    for u in units(p):
        if str(u['box']):
            by_box.setdefault(str(u['box']), []).append(u)
    out = []
    for row in imported or []:
        value = str(row.get('value') or '')
        tag = str(row.get('tag') or '').strip()
        clause = normalize_clause(row.get('clause'))
        if not tag and clause:
            tag = box_tag_for_clause(p, clause)
        if not tag or tag not in bx:
            out.append(row)
            continue
        if bx[tag].get('module') and not value.strip():
            continue
        bu = by_box.get(tag, [])
        if len(bu) <= 1:
            target = str(bu[0]['key']) if bu else str(bx[tag]['clause'])
            out.append(dict(row, clause=target, tag=tag, value=value))
            continue
        pieces = split_merged_text(value, bu)
        if not pieces:
            out.append(dict(row, clause=str(bu[0]['key']), tag=tag, value=value))
            continue
        for u in bu:
            k = str(u['key'])
            if k in pieces:
                out.append({'clause': k, 'title': str(u['title']), 'value': pieces[k], 'tag': tag, 'part': row.get('part', '')})
        if '__preamble' in pieces:
            out.append({'clause': str(bu[0]['key']), 'title': str(bu[0]['title']), 'value': pieces['__preamble'], 'tag': tag})
    return out


def na_rows_for_export(profile, na_clauses):
    """NA maddelerini bolum basina resmi NA kutusuna (CP1NAC, 1SANDDNAC ...) toplar."""
    chapter_tag = {}
    for b in boxes(profile):
        if not b.get('na_tag'):
            continue
        ch = chapter_of(b['clause'])
        chapter_tag.setdefault(ch, str(b['na_tag']))
    if not chapter_tag:
        return []
    buckets = {}
    for row in na_clauses or []:
        ref = normalize_clause(row.get('clause_ref'))
        if not ref:
            continue
        ch = chapter_of(ref)
        if ch not in chapter_tag:
            continue
        just = str(row.get('justification') or '').strip()
        buckets.setdefault(chapter_tag[ch], []).append(ref + (' - ' + just if just else ''))
    return [{'clause': '', 'title': 'Non-applicable clauses', 'value': '\n'.join(lines), 'tag': tag, 'brs_box': True}
            for tag, lines in buckets.items()]


def export_note(profile, clause):
    tag = box_tag_for_clause(profile, clause)
    if not tag:
        return {'tag': '', 'merged': False, 'siblings': [], 'warning': True}
    keys = [str(u['key']) for u in siblings_for_clause(profile, clause)]
    return {'tag': tag, 'merged': len(keys) > 1, 'siblings': keys, 'warning': False}
