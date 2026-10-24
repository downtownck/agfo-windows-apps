# -*- coding: utf-8 -*-
"""AGFO AI Editor - BRCGS teknik gozden gecirme: raporu resmi rehber (F910 / P702 / CP417 / AB309 / SD408) ve teknik
gozden gecirme skill kurallarina gore denetler. Yapay zeka gerektirmez; her bulgu nereye ait oldugunu (alan / bolum /
NA / NC) ve kural kaynagini tasir.

Bulgu: {'id', 'level': 'error'|'warning'|'info', 'where': ('field', key, occ) | ('section', clause) | ('na', i) |
        ('nc', i) | ('report',), 'title', 'detail', 'source', 'excerpt', 'rule'}
"""
from __future__ import annotations

import datetime
import re

from . import boxes as B
from . import data
from . import docx_engine as E
from . import findings as F
from . import guide as G
from . import review_pack as RP

LEVELS = ('error', 'warning', 'info')

# skill: "Do not use conversational expressions, first- or second-person pronouns, or subjective words such as appears,
# seems, probably, likely or may"
SUBJECTIVE = re.compile(r'\b(appears?|appeared|seems?|seemed|probably|likely|perhaps|maybe)\b', re.I)
SOFT = re.compile(r'\b(may|might)\b', re.I)
# 'I' yalniz fiille: "Y.I (General Manager)" gibi bas harfler sahis zamiri degil
PERSONAL = re.compile(r'\b(?:we|our|ours|us|you|your|yours|my)\b|(?<![.\w])I\s+(?:have|had|am|was|checked|saw|observed|reviewed|'
                      r'found|noted|think|believe|verified|asked|interviewed)\b', re.I)
# skill: 'Do not write statements such as "this meets Clause X", "compliant with Clause X" or "in accordance with Clause X"'
CLAUSE_CLAIM = re.compile(r'\b(meets?|met|compliant\s+with|compl(?:y|ies|ied)\s+with|in\s+(?:accordance|compliance|line)\s+with|'
                          r'conforms?\s+(?:to|with)|satisf(?:y|ies|ied))\s+(?:the\s+)?(?:requirements?\s+of\s+)?(?:BRCGS\s+)?'
                          r'(?:clause|section|requirement)s?\s*\d', re.I)
PLACEHOLDER = re.compile(r'\[[^\]\n]{0,80}\]|\bTBC\b|\bTBD\b|to be confirmed|to be completed|\bxx+\b|\?\?|Click or tap here|'
                         r'Choose an item|Insert [a-z ]{3,30} here|lorem ipsum', re.I)
ISO_DATE = re.compile(r'\b(20\d\d)-(\d\d)-(\d\d)\b')
SLASH_DATE = re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b')
HONORIFIC = re.compile(r'\b(Mr|Mrs|Ms|Miss|Dr|Bay|Bayan|Sn)\.?\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+')
TR_CHARS = re.compile(r'[çğıöşüÇĞİÖŞÜ]')
TR_WORDS = re.compile(r'\b(ve|ile|için|olarak|edilmiştir|yapılmaktadır|bulunmaktadır|görülmüştür|tarafından|kontrol edil\w*|'
                      r'kayıt\w*|prosedür\w*|incelen\w*|uygun\w*)\b', re.I)
TRADE_WORDS = re.compile(r'\b(trade|trader|trading|sales|marketing)\b', re.I)


def _f(level, where, title, detail='', source='', excerpt='', rule=''):
    return {'level': level, 'where': where, 'title': title, 'detail': detail, 'source': source, 'excerpt': excerpt, 'rule': rule}


def guide_name(profile):
    return {'fs': 'F910', 'pm': 'P702', 'cp': 'CP417', 'ab': 'AB309', 'sd': 'SD408'}.get(data.norm_profile(profile), 'guide')


def _words(text):
    return len(re.findall(r"[A-Za-zÀ-ÿĞğİıŞşÇçÖöÜü0-9][\w'’.-]*", text or ''))


def language_of(text):
    t = str(text or '')
    if not t.strip():
        return 'empty'
    # buyuk harfle baslayan sozcukler (firma, kisi, yer adlari: "Anı Bisküvi", "Doğrul") dil olcusune katilmaz
    common = ' '.join(w for w in re.findall(r"[\wÇĞİÖŞÜçğıöşü'’-]+", t) if not w[:1].isupper())
    tr = len(TR_CHARS.findall(common)) * 2 + len(TR_WORDS.findall(common)) * 3
    words = max(1, _words(t))
    if tr / words > 0.25:
        return 'tr'
    if tr / words > 0.04:
        return 'mixed'
    return 'en'


def _text_checks(profile, where, text, names=()):
    """Skill yazim kurallari: yer tutucu, oznel ifade, birinci/ikinci sahis, 'clause X'e uygundur', tarih bicimi, dil, kisi adi."""
    out = []
    t = str(text or '')
    skill = 'Technical review skill'
    for m in PLACEHOLDER.finditer(t):
        out.append(_f('error', where, 'Placeholder or unfinished text: "%s"' % m.group(0)[:40],
                      'Remove placeholders, brackets, questions and confirmation requests before submission.', skill,
                      rule='placeholder'))
        break
    subj = sorted({m.group(0).lower() for m in SUBJECTIVE.finditer(t)})
    if subj:
        out.append(_f('warning', where, 'Subjective wording: %s' % ', '.join(subj[:5]),
                      'Use objective audit language; avoid "appears", "seems", "probably", "likely", "may".', skill, rule='subjective'))
    soft = sorted({m.group(0).lower() for m in SOFT.finditer(t)})
    if soft and not subj:
        out.append(_f('info', where, 'Possibility wording: %s' % ', '.join(soft),
                      'The skill asks for objective wording; check that "may / might" is not expressing uncertainty.', skill,
                      rule='subjective'))
    pers = sorted({m.group(0).split()[0] for m in PERSONAL.finditer(t)})
    if pers:
        out.append(_f('warning', where, 'First- or second-person wording: %s' % ', '.join(pers[:5]),
                      'Use passive voice and refer to the audited organisation as "the company".', skill, rule='person'))
    m = CLAUSE_CLAIM.search(t)
    if m:
        out.append(_f('warning', where, 'Clause conformity statement: "%s"' % m.group(0)[:60],
                      'Do not write "meets / compliant with / in accordance with Clause X"; present the evidence, controls and '
                      'implementation instead.', skill, rule='clause_claim'))
    if ISO_DATE.search(t) or SLASH_DATE.search(t):
        ex = (ISO_DATE.search(t) or SLASH_DATE.search(t)).group(0)
        out.append(_f('info', where, 'Date format "%s" in narrative text' % ex, 'Use DD.MM.YYYY in report narrative.', skill,
                      rule='date_format'))
    lang = language_of(t)
    if lang in ('tr', 'mixed'):
        out.append(_f('error' if lang == 'tr' else 'warning', where,
                      'Turkish text in the English report' if lang == 'tr' else 'Mixed Turkish/English text',
                      'The report text must be in English. Use the AI button to write English report text from the evidence.',
                      skill, rule='language'))
    hon = HONORIFIC.search(t)
    found_names = [n for n in names if n and len(n) > 3 and re.search(r'\b' + re.escape(n) + r'\b', t)]
    if hon or found_names:
        out.append(_f('warning', where, 'Personal name in report text: %s' % (hon.group(0) if hon else found_names[0]),
                      'Use job titles or functions instead of names in the Detailed Report.', skill, rule='names'))
    return out


def _names(project):
    """Kisi adlari: katilimci / denetim ekibi tablolari ve bilinen ad alanlari (Detayli Raporda kullanilmamali)."""
    out = set()
    rt = (project.get('meta') or {}).get('report_tables') or {}
    for key, rows in rt.items():
        for r in rows or []:
            for col, v in r.items():
                if col in ('name', 'auditor_name', 'Name') or 'name' in str(col).lower():
                    v = str(v or '').split('/')[0].strip()
                    if 3 < len(v) < 60:
                        out.add(v)
                        for part in v.split():
                            if len(part) > 3 and part[0].isupper():
                                out.add(part)
    for k, v in (project.get('values') or {}).items():
        if re.search(r'REPRESENTATIVE_NAME|AUDITOR.*NAME|LEAD_AUDITOR', k) and isinstance(v, str) and 3 < len(v) < 60:
            out.add(v.strip())
    return {n for n in out if not re.search(r'manager|director|officer|team|leader|supervisor|head|quality|technical', n, re.I)}


def _date(v):
    d = E.parse_date(str(v or '').strip())
    return d


def check_fields(project, fields):
    """Rapor alanlari: rehberde MANDATORY olan bos alanlar, kapsam/dislama kurallari, tarih sirasi."""
    p = project['profile']
    vals = project.get('values') or {}
    out = []
    gn = guide_name(p)
    counted = set(F.COUNT_KEYS.values())
    seen = set()
    for f in fields:
        k = (f['key'], f['occurrence'])
        if k in seen or f['key'] in counted:
            continue
        seen.add(k)
        v = vals.get(f['key'])
        if isinstance(v, list):
            v = v[f['occurrence']] if f['occurrence'] < len(v) else ''
        v = str(v or '').strip()
        rule = RP.field_rule(p, f['label'])
        where = ('field', f['key'], f['occurrence'])
        if f['occurrence'] == 0 and rule and rule['mandatory'] and (not v or B.is_placeholder(v) or E._PH_ANY.search(v)):
            out.append(_f('error', where, '%s is mandatory and empty' % f['label'], rule['text'][:400], gn, rule['text'], 'mandatory'))
        descriptive = re.search(r'SCOPE|EXCLUSION|JUSTIFICATION|DESCRIPTION|PROFILE|CHANGES|COMMENT|REASON|CLAIM|DEVIATION|'
                                r'PROCESS|PRODUCT|OUTSOURC|RATIONALE', f['key'], re.I) and not re.search(r'NAME|ADDRESS|COUNTRY',
                                                                                                     f['key'], re.I)
        if f['kind'] in ('text', 'rich', 'plain') and v and f['occurrence'] == 0:
            for x in _text_checks(p, where, v):
                if x['rule'] == 'placeholder' or (x['rule'] == 'language' and descriptive and _words(v) >= 6):
                    out.append(x)
    # kapsam ve dislamalar (tum rehberler)
    def first(*keys):
        for k in keys:
            if str(vals.get(k) or '').strip():
                return k, str(vals[k]).strip()
        return keys[0], ''
    sk, scope = first('SCOPE_OF_AUDIT', 'AUDIT_SCOPE', 'SCOPE')
    ek, excl = first('EXCLUSION_FROM_SCOPE', 'SCOPE_EXCLUSION', 'EXCLUSIONS_FROM_SCOPE', 'SCOPE_EXCLUSIONS')
    jk, just = first('JUSTIFICATION_FOR_EXCLUSION', 'JUSTIFICATION_FOR_EXCLUSIONS')
    keys = {f['key'] for f in fields}
    if sk in keys and scope:
        if len(re.findall(r'[,;]', scope)) > 10:
            out.append(_f('warning', ('field', sk, 0), 'Scope lists many items',
                          'The scope shall be clear, succinct and unambiguous and not provide a long list of products.', gn,
                          rule='scope_long'))
        if p in ('ab', 'cp') and TRADE_WORDS.search(scope):
            w = TRADE_WORDS.search(scope).group(0)
            out.append(_f('error', ('field', sk, 0), 'Scope uses "%s"' % w,
                          ('Do not use the terms trade, trader or trading in scope wording.' if p == 'ab' else
                           'Words such as sales, marketing, trade, distribution and delivery are not permitted in the scope.'),
                          gn, rule='scope_words'))
    if ek in keys and not excl:
        out.append(_f('error', ('field', ek, 0), 'Exclusions from scope is empty',
                      'This must not be left blank. If there are no exclusions, record "None".', gn, rule='exclusions'))
    if excl and excl.strip().lower() not in ('none', 'n/a', 'not applicable', 'no', '-') and jk in keys and not just:
        out.append(_f('error', ('field', jk, 0), 'Justification for exclusion is missing',
                      'Justification must be given for any exclusions from scope.', gn, rule='justification'))
    # tarih sirasi
    dk = {}
    for f in fields:
        if f['kind'] == 'date':
            dk.setdefault(f['key'], f)
    def d(*names):
        for n in names:
            if n in dk and _date(vals.get(n)):
                return n, _date(vals.get(n))
        return None, None
    s_k, start = d('EVALUATION_START_DATE', 'AUDIT_START_DATE')
    f_k, finish = d('AUDIT_FINISH_DATE', 'EVALUATION_FINISH_DATE')
    i_k, issue = d('CERTIFICATE_ISSUE_DATE')
    x_k, expiry = d('CERTIFICATE_EXPIRY_DATE')
    r_k, reaudit = d('AUDIT_REAUDIT_DATE', 'REAUDIT_DUE_DATE')
    if start and finish and finish < start:
        out.append(_f('error', ('field', f_k, 0), 'Audit finish date is before the start date', '', gn, rule='dates'))
    if issue and finish and issue < finish:
        out.append(_f('error', ('field', i_k, 0), 'Certificate issue date is before the end of the audit', '', gn, rule='dates'))
    if expiry and issue and expiry <= issue:
        out.append(_f('error', ('field', x_k, 0), 'Certificate expiry date is not after the issue date', '', gn, rule='dates'))
    if reaudit and expiry and reaudit > expiry:
        out.append(_f('warning', ('field', r_k, 0), 'Re-audit due date is after the certificate expiry date', '', gn, rule='dates'))
    return out


def check_sections(project):
    p = project['profile']
    out = []
    names = _names(project)
    na_by_sec = {}
    for i, na in enumerate((project.get('meta') or {}).get('na_clauses') or []):
        sec = F.item_section(project.get('sections') or [], na, 'clause_ref')
        na_by_sec.setdefault(sec, []).append(na)
    try:
        from . import coverage as COV
    except Exception:  # pragma: no cover
        COV = None
    by_clause = {r['clause']: r for r in project.get('sections') or []}
    empty_chapters = set()
    for row in project.get('sections') or []:
        clause = row['clause']
        where = ('section', clause)
        text = F.with_closing(project, row)
        whole_na = any(F.norm_clause(n.get('clause_ref')) == clause for n in na_by_sec.get(clause, []))
        note = B.export_note(p, clause)
        merged = bool(note.get('merged'))
        na_text = re.match(r'^\s*(N/?A|Not applicable|Non[- ]applicable)\b', text, re.I)
        if not text.strip():
            # birlesik kutu: ayni kutudaki baska bir madde dolu ise metin orada (gercek raporlarda bolum 2 tek kutuda)
            if merged and any(str((by_clause.get(c) or {}).get('value') or '').strip() for c in note.get('siblings') or []):
                continue
            unit = B.unit(p, clause) or {}
            if unit.get('optional_module'):
                continue
            ch = B.chapter_of(clause)
            if not any(str(r.get('value') or '').strip() for r in project.get('sections') or [] if B.chapter_of(r['clause']) == ch):
                if ch not in empty_chapters:
                    empty_chapters.add(ch)
                    out.append(_f('warning', where, 'Chapter %s %s is empty' % (ch, B.chapter_title(p, ch) or ''),
                                  'Complete the chapter, or confirm it is a module that is not included in this audit.',
                                  guide_name(p), rule='empty'))
                continue
            if not whole_na:
                out.append(_f('error', where, 'No report text', 'Every section of the Detailed Report needs report text, '
                              'or the whole section must be recorded as not applicable with a justification.', guide_name(p),
                              rule='empty'))
            continue
        out.extend(_text_checks(p, where, text, names))
        st = G.struct_of(row)
        if (row.get('flags') or {}).get('report_stale'):
            out.append(_f('info', where, 'Evidence changed after the report text was written',
                          'Run the AI button again or update the report text.', 'AGFO', rule='stale'))
        rule = (G.form_for(p, clause) or {}).get('rule') or {}
        mw = int(rule.get('minimum_words') or 0)
        if mw and not merged and not na_text and _words(row.get('value') or '') < mw:
            out.append(_f('warning', where, 'Short report text (%d words, about %d expected)' % (_words(row.get('value')), mw),
                          'The guide expects this section to give the reader enough detail to understand the controls.',
                          guide_name(p), rule='short'))
        if COV is not None:
            cv = COV.section_coverage(p, clause, row.get('coverage_parent'), row.get('title'))
            if cv and cv.get('coverage_items'):
                s = COV.summary(cv, str(row.get('value') or ''), row.get('note') or '')
                if int(s.get('red') or 0):
                    out.append(_f('info', where, '%d guideline point(s) not found in the report text' % int(s['red']),
                                  'See the coverage list in the section editor.', guide_name(p), rule='coverage'))
        del st
    return out


def check_findings(project):
    """NA ve NC kayitlari: gerekce, madde numarasi, ait oldugu bolum, NC metni."""
    out = []
    secs = project.get('sections') or []
    meta = project.get('meta') or {}
    for i, na in enumerate(meta.get('na_clauses') or []):
        ref = str(na.get('clause_ref') or '').strip()
        where = ('na', i)
        if not ref:
            out.append(_f('error', where, 'NA row without a clause number', '', 'Technical review skill', rule='na'))
            continue
        if not str(na.get('justification') or '').strip():
            out.append(_f('error', where, 'NA clause %s has no justification' % ref,
                          'Mark a clause as not applicable only when the absence of the product, process, claim, equipment or '
                          'activity is supported by evidence, and give the justification.', 'Technical review skill', rule='na'))
        sec = F.item_section(secs, na, 'clause_ref')
        row = next((r for r in secs if r['clause'] == sec), None)
        if row is not None and F.norm_clause(ref) == sec and str(row.get('value') or '').strip() and \
                _words(row.get('value')) > 40:
            out.append(_f('warning', ('section', sec), 'Section %s is recorded as not applicable but has report text' % sec,
                          'Check the applicability decision.', 'Technical review skill', rule='na'))
    for i, it in enumerate((meta.get('action_plan') or {}).get('items') or []):
        where = ('nc', i)
        det = F.nc_detail(it)
        if not det:
            out.append(_f('error', where, 'Non-conformity without details', '', 'Technical review skill', rule='nc'))
            continue
        if not str(it.get('clause') or '').strip():
            out.append(_f('error', where, 'Non-conformity without a clause number', det[:80], 'Technical review skill', rule='nc'))
        elif F.item_section(secs, it, 'clause') is None:
            out.append(_f('warning', where, 'NC clause %s does not belong to any report section' % it.get('clause'), det[:80],
                          'Technical review skill', rule='nc'))
        if language_of(det) == 'tr':
            out.append(_f('error', where, 'Non-conformity text is in Turkish', det[:80],
                          'Technical review skill', rule='language'))
        if re.search(r'\b(because|due to|caused by|resulting in|could lead|may lead|risk of)\b', det, re.I):
            out.append(_f('info', where, 'NC text contains a cause or consequence',
                          'Write objective, reproducible evidence only; do not add causes, consequences or risk commentary.',
                          'Technical review skill', rule='nc'))
    return out


def run(project, fields):
    """Tum kontroller; seviye ve rapor sirasina gore."""
    out = check_fields(project, fields) + check_sections(project) + check_findings(project)
    order = {l: k for k, l in enumerate(LEVELS)}
    sec_order = {r['clause']: k for k, r in enumerate(project.get('sections') or [])}

    def key(f):
        w = f['where']
        pos = (0, 0) if w[0] == 'field' else (1, sec_order.get(w[1], 999)) if w[0] == 'section' else (2, w[1] if len(w) > 1 else 0)
        return (order[f['level']], pos)
    out.sort(key=key)
    for k, f in enumerate(out):
        f['id'] = k
    return out


def counts(found):
    return {l: sum(1 for f in found if f['level'] == l) for l in LEVELS}


# ----------------------------------------------------------------------------- yapay zeka icin kaynak metinler
def section_guidance(profile, clause, title=''):
    """Rehberin Detayli Rapor kismindan bu bolumun beklentileri (baslik araniyor); bulunamazsa ''."""
    flat = RP._flat(profile)
    starts = list(re.finditer(r'How to complete the Detailed Section|Detailed Audit Report\s+1\.', flat, re.I))
    base = starts[-1].start() if starts else 0
    words = [w for w in re.findall(r'[A-Za-z]+', title or '') if len(w) > 2][:4]
    if not words:
        return ''
    m = re.search(r'\s+'.join(re.escape(w) for w in words), flat[base:], re.I)
    if not m:
        return ''
    seg = flat[base + m.start(): base + m.start() + 2200]
    return re.sub(r'[ \t]+', ' ', seg).strip()


def requirement_text(profile, clause):
    """Standardin gereklilik metni (bu bolumun maddeleri)."""
    std = data.standard(profile).get('sections') or {}
    out = []
    for k, v in std.items():
        if k == clause or k.startswith(clause + '.'):
            t = v.get('requirement') or v.get('text') or v.get('title') or ''
            if t:
                out.append('%s %s' % (k, t))
    return '\n'.join(out)[:6000]


def skill_text(profile):
    return RP.pack(profile)['skill']
