# -*- coding: utf-8 -*-
"""AGFO AI Editor - BRCGS raporlarinin bu bilgisayardaki deposu.

Kaynak: AGFO BRCGS Report Studio 5.2.1 includes/class-repository.php (WordPress veritabani yerine yerel dosyalar).
Korunan kurallar:
  * rapor tek otoritededir (rapor basina bir JSON dosyasi), tarayici/gecici taslak yoktur; yazma atomiktir
  * her kayittan once sikistirilmis surum anlik goruntusu alinir, son 25 surum saklanir, geri donulebilir
  * veri kaybi korumasi: kayitli metin 4000 karakteri asiyorsa ve gelen veri bunun %25'inin (en az 400) altindaysa
    kayit reddedilir; kullanici isterse "yine de kaydet" (force)
  * cop kutusu geri alinabilir; kalici silme yalniz cop kutusundaki rapor icin
  * bolum sirasi okuma aninda sayisal (4.1.2)
"""
from __future__ import annotations

import copy
import datetime
import gzip
import json
import os
import pathlib
import re
import secrets
import tempfile

from . import boxes as B
from . import data

REVISION_LIMIT = 25
META_BRANCHES = ('na_clauses', 'report_tables', 'section_findings', 'action_plan', 'final_context', 'final_acceptance', 'flags')
STATUSES = ('active', 'trash')


class GuardError(Exception):
    """Gelen veri kayitli rapora gore tehlikeli derecede bos."""

    def __init__(self, stored, incoming):
        super().__init__('Kayıt durduruldu: gelen veri kayıtlı rapora göre tehlikeli derecede boş (kayıtlı %d karakter, gelen %d '
                         'karakter). Veri kaybı riski nedeniyle yazılmadı.' % (stored, incoming))
        self.stored, self.incoming = stored, incoming


def now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def new_uid():
    return 'brs_%s_%s' % (datetime.datetime.now().strftime('%Y%m%d_%H%M%S'), secrets.token_urlsafe(5).replace('-', 'x').replace('_', 'y'))


def empty_report_tables():
    return {'present_at_audit': [], 'gfsi_history': [], 'audit_team': [], 'audit_duration_days': []}


def default_meta():
    return {'na_clauses': [], 'report_tables': empty_report_tables(), 'section_findings': {}, 'action_plan': {'items': [], 'updated_at': ''},
            'final_context': {}, 'final_acceptance': {}, 'flags': {}}


def _first(values, keys):
    for k in keys:
        v = values.get(k)
        if isinstance(v, list):
            v = next((x for x in v if str(x).strip()), '')
        if v and str(v).strip():
            return str(v).strip()
    return ''


def company_of(values):
    return _first(values, ('OWNERCOMPANY', 'COMPANY_NAME', 'SITE_NAME', 'CERTIFIED_SITE_NAME', 'SITE_NAMEAB'))


def site_code_of(values):
    return _first(values, ('BRC_SITE_CODE', 'SITE_CODE'))


def audit_date_of(values):
    return _first(values, ('AUDIT_START_DATE', 'EVALUATION_START_DATE', 'AUDIT_FINISH_DATE', 'EVALUATION_END_DATE',
                           'EVALUATION_FINISH_DATE'))


def text_score(values, sections, meta=None) -> int:
    total = 0
    for v in (values or {}).values():
        if isinstance(v, list):
            total += sum(len(str(x).strip()) for x in v)
        elif isinstance(v, (str, int, float)):
            total += len(str(v).strip())
    for row in sections or []:
        total += len(str(row.get('value') or '').strip()) + len(str(row.get('note') or '').strip())
    total += len(json.dumps(meta or {}, ensure_ascii=False)) // 4
    return total


def _atomic_write_bytes(path, blob):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.agfo-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Store:
    def __init__(self, root=None):
        if root is None:
            import agfo_editor_core as core
            root = pathlib.Path(core.data_dir()) / 'brcgs-reports'
        self.root = pathlib.Path(root)
        (self.root / 'revisions').mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ dosya
    def _path(self, uid):
        if not re.match(r'^[A-Za-z0-9_\-]{6,80}$', str(uid or '')):
            raise KeyError('Geçersiz rapor kimliği: %r' % uid)
        return self.root / ('%s.json' % uid)

    def _read(self, uid):
        p = self._path(uid)
        if not p.exists():
            raise KeyError('Rapor bulunamadı.')
        with open(p, encoding='utf-8') as fh:
            return json.load(fh)

    def _write(self, project):
        blob = json.dumps(project, ensure_ascii=False, indent=1).encode('utf-8')
        _atomic_write_bytes(self._path(project['id']), blob)

    @staticmethod
    def _normalize(project):
        p = project
        p['profile'] = data.norm_profile(p.get('profile'))
        p.setdefault('values', {})
        meta = default_meta()
        meta.update({k: v for k, v in (p.get('meta') or {}).items() if k in META_BRANCHES})
        rt = empty_report_tables()
        rt.update(meta.get('report_tables') or {})
        meta['report_tables'] = rt
        if not isinstance(meta.get('action_plan'), dict):
            meta['action_plan'] = {'items': [], 'updated_at': ''}
        p['meta'] = meta
        p['sections'] = B.sort_sections(list(p.get('sections') or []))
        p['company'] = company_of(p['values'])
        p['site_code'] = site_code_of(p['values'])
        p['audit_date'] = audit_date_of(p['values'])
        p.setdefault('status', 'active')
        return p

    # ------------------------------------------------------------------ liste / ac
    def list(self, status='active', query=''):
        rows = []
        q = str(query or '').strip().lower()
        for f in self.root.glob('brs_*.json'):
            try:
                with open(f, encoding='utf-8') as fh:
                    pr = json.load(fh)
            except (OSError, ValueError):
                continue
            if status != 'all' and pr.get('status', 'active') != status:
                continue
            filled = sum(1 for s in pr.get('sections') or [] if str(s.get('value') or '').strip())
            row = {'id': pr.get('id'), 'title': pr.get('title') or '', 'profile': pr.get('profile'), 'company': pr.get('company') or '',
                   'site_code': pr.get('site_code') or '', 'audit_date': pr.get('audit_date') or '', 'status': pr.get('status', 'active'),
                   'sections': len(pr.get('sections') or []), 'filled': filled, 'updated_at': pr.get('updated_at') or '',
                   'created_at': pr.get('created_at') or '', 'size': f.stat().st_size, 'source_file': pr.get('source_file') or ''}
            if q and q not in ' '.join(str(row[k]) for k in ('title', 'company', 'site_code', 'profile')).lower():
                continue
            rows.append(row)
        rows.sort(key=lambda r: r['updated_at'], reverse=True)
        return rows

    def get(self, uid):
        return self._normalize(self._read(uid))

    def mark_opened(self, uid):
        pr = self._read(uid)
        pr['opened_at'] = now()
        self._write(pr)

    # ------------------------------------------------------------------ olustur / kaydet
    def create(self, profile, title='', values=None, sections=None, meta=None, origin='new-file', source_file=''):
        profile = data.norm_profile(profile)
        values = dict(values or {})
        sections = sections if sections is not None else B.sections_for_profile(profile)
        uid = new_uid()
        company = company_of(values)
        if not title:
            title = (company + ' ' if company else '') + data.PROFILE_SHORT[profile] + ' Audit Report'
        pr = {'id': uid, 'title': title, 'profile': profile, 'values': values, 'sections': sections, 'meta': meta or {},
              'origin': origin, 'source_file': source_file, 'status': 'active', 'created_at': now(), 'updated_at': now()}
        pr = self._normalize(pr)
        pr['text_score'] = text_score(pr['values'], pr['sections'], pr['meta'])
        self._write(pr)
        return pr

    def save(self, project, force=False):
        uid = project['id']
        old = self._read(uid)
        pr = self._normalize(copy.deepcopy(project))
        new_score = text_score(pr['values'], pr['sections'], pr['meta'])
        old_score = int(old.get('text_score') or text_score(old.get('values'), old.get('sections'), old.get('meta')))
        if not force and old_score > 4000 and new_score < max(400, old_score // 4):
            raise GuardError(old_score, new_score)
        self.snapshot(uid, 'pre-save', old)
        pr['text_score'] = new_score
        pr['updated_at'] = now()
        pr['created_at'] = old.get('created_at') or pr.get('created_at') or now()
        self._write(pr)
        self.drop_draft(uid)
        return self.get(uid)                    # geri okunan dogrulanmis hali

    # ------------------------------------------------------------------ kurtarma taslagi (otomatik kayit)
    def _draft_path(self, uid):
        self._path(uid)
        d = self.root / 'drafts'
        d.mkdir(parents=True, exist_ok=True)
        return d / ('%s.json' % uid)

    def save_draft(self, project):
        """Kaydedilmemis hal; surum gecmisine girmez, asil kaydi degistirmez. Cokme sonrasi geri getirmek icin."""
        pr = copy.deepcopy(project)
        pr['draft_at'] = now()
        _atomic_write_bytes(self._draft_path(project['id']), json.dumps(pr, ensure_ascii=False).encode('utf-8'))

    def get_draft(self, uid):
        p = self._draft_path(uid)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text('utf-8'))
        except (OSError, ValueError):
            return None

    def drop_draft(self, uid):
        try:
            self._draft_path(uid).unlink()
        except (OSError, KeyError):
            pass

    # ------------------------------------------------------------------ surumler
    def _rev_dir(self, uid):
        self._path(uid)
        d = self.root / 'revisions' / uid
        d.mkdir(parents=True, exist_ok=True)
        return d

    def snapshot(self, uid, label='', project=None):
        pr = project if project is not None else self._read(uid)
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        meta = {'label': label, 'created_at': now(), 'title': pr.get('title'), 'text_score': pr.get('text_score'),
                'filled': sum(1 for s in pr.get('sections') or [] if str(s.get('value') or '').strip())}
        blob = gzip.compress(json.dumps({'meta': meta, 'project': pr}, ensure_ascii=False).encode('utf-8'))
        _atomic_write_bytes(self._rev_dir(uid) / ('%s.json.gz' % stamp), blob)
        revs = sorted(self._rev_dir(uid).glob('*.json.gz'))
        for old in revs[:-REVISION_LIMIT]:
            try:
                old.unlink()
            except OSError:
                pass
        return stamp

    def revisions(self, uid):
        out = []
        for f in sorted(self._rev_dir(uid).glob('*.json.gz'), reverse=True):
            try:
                meta = json.loads(gzip.decompress(f.read_bytes()).decode('utf-8'))['meta']
            except (OSError, ValueError, KeyError):
                continue
            out.append(dict(meta, id=f.name[:-len('.json.gz')], size=f.stat().st_size))
        return out

    def restore_revision(self, uid, rev_id):
        f = self._rev_dir(uid) / ('%s.json.gz' % re.sub(r'[^0-9\-]', '', rev_id))
        pr = json.loads(gzip.decompress(f.read_bytes()).decode('utf-8'))['project']
        self.snapshot(uid, 'pre-restore')
        pr['updated_at'] = now()
        self._write(pr)
        return self.get(uid)

    # ------------------------------------------------------------------ dosya islemleri
    def duplicate(self, uid, title=None):
        pr = self.get(uid)
        return self.create(pr['profile'], title or pr['title'] + ' (kopya)', copy.deepcopy(pr['values']), copy.deepcopy(pr['sections']),
                           copy.deepcopy(pr['meta']), origin='duplicate', source_file=pr.get('source_file') or '')

    def rename(self, uid, title):
        title = str(title or '').strip()
        if not title:
            raise ValueError('Rapor adı boş olamaz.')
        pr = self._read(uid)
        pr['title'] = title[:200]
        pr['updated_at'] = now()
        self._write(pr)

    def set_status(self, uid, status):
        if status not in STATUSES:
            raise ValueError(status)
        pr = self._read(uid)
        pr['status'] = status
        pr['updated_at'] = now()
        self._write(pr)

    def delete_forever(self, uid):
        pr = self._read(uid)
        if pr.get('status') != 'trash':
            raise ValueError('Yalnız çöp kutusundaki raporlar kalıcı silinebilir.')
        self._path(uid).unlink()
        self.drop_draft(uid)
        d = self.root / 'revisions' / uid
        if d.is_dir():
            for f in d.glob('*'):
                f.unlink()
            d.rmdir()

    # ------------------------------------------------------------------ DOCX
    def import_docx(self, path, title=''):
        from . import docx_engine as E
        res = E.read_report(path, os.path.basename(str(path)))
        meta = {'na_clauses': res['na_clauses'], 'report_tables': res['report_tables'],
                'action_plan': {'items': res['action_plan']['items'], 'updated_at': now()}}
        return self.create(res['profile'], title, res['values'], res['sections'], meta, origin='docx-import',
                           source_file=os.path.basename(str(path)))

    @staticmethod
    def export_payload(project):
        meta = project.get('meta') or {}
        return {'profile': project['profile'], 'values': project.get('values') or {}, 'sections': project.get('sections') or [],
                'na_clauses': meta.get('na_clauses') or [], 'report_tables': meta.get('report_tables') or {},
                'action_plan': meta.get('action_plan') or {}}

    def export_docx(self, uid_or_project, out_path):
        from . import docx_engine as E
        pr = uid_or_project if isinstance(uid_or_project, dict) else self.get(uid_or_project)
        return E.write_report(self.export_payload(pr), out_path)


# ----------------------------------------------------------------------------- yardimcilar (repository.php)
def export_check(project):
    p = project['profile']
    merged = B.merge_for_export(p, project.get('sections') or [])
    filled = sum(1 for s in project.get('sections') or [] if str(s.get('value') or '').strip())
    return {'profile': p, 'units_total': len(project.get('sections') or []), 'units_filled': filled,
            'boxes_written': len(merged['rows']), 'merged_boxes': merged['merged'], 'skipped': merged['skipped'],
            'unmapped_spec': B.unmapped_clauses(p)}


def preview_text(project, field_labels=None):
    lines = [str(project.get('title') or '').upper(), 'Profil: ' + project['profile'].upper()]
    if project.get('company'):
        lines.append('Firma: ' + project['company'])
    if project.get('site_code'):
        lines.append('Site kodu: ' + project['site_code'])
    lines += ['', '== GENEL RAPOR ALANLARI ==']
    labels = field_labels or {}
    for key, value in (project.get('values') or {}).items():
        vals = value if isinstance(value, list) else [value]
        vals = [str(v).strip() for v in vals if str(v).strip()]
        if vals:
            lines.append('%s: %s' % (labels.get(key, key), ', '.join(vals)))
    lines += ['', '== DETAILED REPORT ==']
    for row in project.get('sections') or []:
        v = str(row.get('value') or '').strip()
        lines += ['', '%s %s' % (row['clause'], row.get('title') or ''), v or '[boş]']
        if str(row.get('note') or '').strip():
            lines.append('Kanıt notu: ' + str(row['note']).strip())
    meta = project.get('meta') or {}
    if meta.get('na_clauses'):
        lines += ['', '== NOT APPLICABLE CLAUSES ==']
        for na in meta['na_clauses']:
            lines.append('%s - %s' % (str(na.get('clause_ref') or '').strip(), str(na.get('justification') or '').strip()))
    items = (meta.get('action_plan') or {}).get('items') or []
    if items:
        lines += ['', '== NC ACTION PLAN ==']
        for it in items:
            lines.append('%s [%s] %s' % (str(it.get('clause') or '').strip(), str(it.get('type') or '').strip(),
                                         str(it.get('nc_text') or it.get('detail') or '').strip()))
    return '\n'.join(lines)


_NC_LINE = re.compile(r'\b(non[- ]?conformity|non[- ]?conformance|uygunsuzluk|\bNC\b)\b', re.I)


def scan_action_plan(project):
    """Bolum metinlerindeki NC satirlarini eylem planina toplar (repository.php scan_action_plan)."""
    items = []
    for row in project.get('sections') or []:
        text = str(row.get('value') or '')
        for line in re.split(r'\r\n|\r|\n', text):
            line = line.strip()
            if not line or not _NC_LINE.search(line):
                continue
            m = re.search(r'\b(fundamental|critical|major|minor)\b', line, re.I)
            cm = re.search(r'\b(\d+(?:\.\d+)+)\b', line)
            items.append({'clause': cm.group(1) if cm else row['clause'], 'type': m.group(1).lower() if m else 'minor',
                          'nc_text': line, 'root_cause': '', 'correction': '', 'proposed_preventive_action': '',
                          'date_reviewed': '', 'reviewed_by': '', 'source': 'scan'})
    return items
