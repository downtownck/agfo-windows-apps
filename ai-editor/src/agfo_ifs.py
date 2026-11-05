# -*- coding: utf-8 -*-
"""AGFO AI Editor - IFS auditXpress (.ifs) dosyalari.

.ifs duz bir JSON'dur (auditXpress Neo). Bu modul dosyayi okur, alanlari duzenler ve bire bir ayni bicimde geri yazar:
anahtar sirasi, bosluksuz ayiricilar ve UTF-8 (ASCII kacisi yok). Tanimadigi her sey dokunulmadan kalir.

Yapi (IFS Food 8, modul food_8):
  data.modules.<modul>.questions            rapor alanlari {anahtar: {answer, revision}}
  .checklists.<id>.resultScorings           maddeler {uuid: {score{value,scoreId,label}, isCorrectionRequired,
                                            answers{explanationText, englishExplanationText, note, fieldAnswers}}}
  .checklists.<id>.correctiveActions        B / C / D maddeleri icin {uuid: {requirementUuid, fields}}
  tekrarli gruplar                          [{id, rootQuestions{alan: {answer, revision}}, subQuestions{...}}]
Hash alanlari (hash, hashVersion2, hashVersion3) auditXpress'in kendi imzasidir; hesaplanamaz. Kayitta korunur ya da
(ayara gore) bosaltilir.
"""
from __future__ import annotations

import copy
import json
import os
import pathlib
import re
import shutil
import sys
import time
import uuid as _uuid

HASH_KEYS = ('hash', 'hashVersion2', 'hashVersion3')
# Dolu bir auditXpress dosyasindan: puan nesnesi {"value", "scoreId", "label"}
SCORES = [('A', 20), ('B', 15), ('C', 5), ('D', -20), ('NA', 0)]
SCORE_VALUE = dict(SCORES)
CORRECTION_SCORES = {'B', 'C', 'D'}          # auditXpress bu puanlarda duzeltme ister (isCorrectionRequired + correctiveActions)
YES_NO = ('', 'yes', 'no')


class IfsError(Exception):
    pass


def data_dir() -> pathlib.Path:
    base = getattr(sys, '_MEIPASS', None)
    return (pathlib.Path(base) if base else pathlib.Path(__file__).resolve().parent) / 'ifs_data'


def _load_catalog():
    try:
        rows = json.loads((data_dir() / 'field-catalog.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return {r['fieldKey']: r for r in rows if isinstance(r, dict) and r.get('fieldKey')}


CATALOG = _load_catalog()


def _load_shapes():
    """Bos listelerin yapisi (dolu bir auditXpress dosyasindan; yalniz alan adlari): {anahtar: {kind, root, sub}}."""
    out = {}
    for p in data_dir().glob('*-fields.json'):
        try:
            out.update(json.loads(p.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            pass
    return out


SHAPES = _load_shapes()

# Rapor alanlarinin bolumleri (AGFO IFS Builder eklentisindeki gruplama; kalanlar "Ozetler ve diger alanlar")
GROUPS = [
    ('company', 'Firma profili', (
        'companyCoid', 'companyName', 'companyStreetNo', 'companyZip', 'companyCity', 'companyCountry', 'companyTelephone',
        'companyFax', 'companyEmail', 'companyWebpage', 'companyGpsLatitude', 'companyGpsLongitude', 'companyGln',
        'companyGlnNumber', 'companyLegalRegistrationNumbers', 'companyLegalRegistrationNumbersText',
        'companySanitaryLegalAuthorisationNumbers', 'companySanitaryLegalAuthorisationNumbersText',
        'companyEmergencyContactName', 'companyEmergencyContactTelephone', 'companyEmergencyContactFax',
        'companyEmergencyContactEmail')),
    ('assessment', 'Denetim bilgileri', (
        'auditAnnouncedOption', 'executionMode', 'initialAuditType', 'auditCanceled', 'auditFailedBecauseMissingCorrections',
        'certificateIsIssued', 'auditWitnessType', 'auditLanguage', 'auditLastDay', 'certificationBodyName',
        'certificationBodyAccreditationNumber', 'certificationBodyAddress', 'certificateRegisterNumber', 'clientNumber',
        'qmsLanguage', 'workingLanguage', 'previousAuditWasUnannounced', 'previousAuditUnannouncedDate',
        'previousCertificationDate', 'previousCertificationCertificationBody', 'previousCertificationAuditor',
        'previousCertificationResult')),
    ('site', 'Tesis profili', (
        'companyYearConstruction', 'companyYearReConstruction', 'companyStructureDecentralised',
        'companyStructureMultiLocationProduction', 'companyStructureMultiLocationProductionCoidsNumber',
        'companyStructureMultiLegalEntity', 'companyStructureMultiLegalEntityCoidsNumber', 'headquartersName',
        'headquartersStreetNo', 'headquartersZip', 'headquartersCity', 'headquartersCountry', 'headquartersTelephone',
        'headquartersFax', 'headquartersEmail', 'headquartersWebpage', 'headquartersContactPersonName', 'numberOfEmployees',
        'numberOfEmployeesForTimeCalculation', 'numberOfEmployeesDescription', 'numberOfEmployeesDescription_en',
        'productionAreaSize', 'numberOfProductionLines', 'numberOfBuildings', 'numberOfFloors', 'seasonalProduction',
        'seasonalProductionBreak', 'seasonalProductionPeriod', 'seasonalProductionPeriod_en', 'seasonalProductionDescription',
        'seasonalProductionDescription_en', 'fullyOutsourcedProducts', 'profileFullyOutsourcedProductsCoidNumber',
        'tradedProductsBrokerActivity', 'tradedProductsBrokerActivityCoidNumber', 'partlyOutsourcedProcesses',
        'partlyOutsourcedProcessesCoidNumber', 'logoRequirementsFulfilled', 'otherStandardsCertification',
        'otherStandardsCertificationStandardsIfs', 'otherStandardsCertificationStandardsIfsDescription',
        'otherStandardsCertificationCombinedAssessment', 'otherStandardsCertificationCombinedAssessmentText',
        'companyClaimUse', 'companyClaims', 'companyClaimsOtherListText', 'hkzLogo', 'customerBrandedProducts', 'fsma',
        'geographicalIndicationScheme')),
    ('scope', 'Kapsam', (
        'scopeAuditScopeDescription', 'scopeAuditScopeDescription_en', 'scopeCertificateScopeDescription',
        'scopeCertificateScopeDescription_en', 'scopeProductGroupsDescription', 'scopeProductGroupsDescription_en',
        'exclusions', 'productsProducedProcessesRunning', 'productsProducedProcessesRunning_en')),
    ('summary', 'Özetler ve diğer alanlar', ()),
]

_HUMAN_RX = re.compile(r'([a-z0-9])([A-Z])')


def humanize(key: str) -> str:
    k = re.sub(r'_en$', ' (EN)', key or '')
    k = _HUMAN_RX.sub(r'\1 \2', k).replace('_', ' ').strip()
    return (k[:1].upper() + k[1:]) if k else 'Alan'


def label_of(key: str) -> str:
    row = CATALOG.get(key) or CATALOG.get(re.sub(r'_en$', '', key))
    if row and row.get('label'):
        lab = row['label']
        if key.endswith('_en') and not lab.lower().endswith(' en'):
            lab += ' (EN)'
        return re.sub(r' En$', ' (EN)', lab)
    return humanize(key)


def is_en(key: str) -> bool:
    return key.endswith('_en')


def pair_of(key: str):
    """'xxx_en' -> 'xxx' ve tersi (Turkce/yerel dil - Ingilizce cifti)."""
    return key[:-3] if key.endswith('_en') else key + '_en'


def is_group_list(value) -> bool:
    """Tekrarli grup: [{id, rootQuestions{...}, subQuestions{...}}]."""
    return isinstance(value, list) and all(isinstance(x, dict) and 'rootQuestions' in x for x in value)


def is_code_list(value) -> bool:
    """Secenek / kod listesi: ["ar", "en"], ["customerAgreementTypeRecipe", ...]."""
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def is_reference_list(value) -> bool:
    """auditXpress'in kendi kayitlarina bagli secimler (CCP secici, kapsamlar): [{type, uuid, ...}] - degistirilmez."""
    return isinstance(value, list) and bool(value) and all(isinstance(x, dict) and 'uuid' in x and 'rootQuestions' not in x
                                                           for x in value)


def field_kind(key, value) -> str:
    """str | yesno | codes | group | refs | other."""
    if isinstance(value, str):
        return 'yesno' if value in ('yes', 'no') or key in YESNO_KEYS else 'str'
    if value == []:                                     # bos liste: yapisi bilinen bir sablondan
        shape = SHAPES.get(key)
        if shape:
            return shape['kind']
        return 'refs' if key.startswith('widget') else 'other'
    if is_group_list(value) and value:
        return 'group'
    if is_reference_list(value):
        return 'refs'
    if is_code_list(value):
        return 'codes'
    return 'other'


YESNO_KEYS = {'companyStructureDecentralised', 'companyStructureMultiLocationProduction', 'companyStructureMultiLegalEntity',
              'seasonalProduction', 'fullyOutsourcedProducts', 'tradedProductsBrokerActivity', 'partlyOutsourcedProcesses',
              'logoRequirementsFulfilled', 'otherStandardsCertification', 'companyClaimUse', 'hkzLogo', 'auditCanceled',
              'auditFailedBecauseMissingCorrections', 'previousAuditWasUnannounced', 'certificateIsIssued',
              'customerBrandedProducts', 'exclusions', 'geographicalIndicationScheme', 'fsma'}


def group_template(key, items):
    """Yeni satir icin ornek: listedeki ilk satir, liste bossa bilinen yapi."""
    if items:
        return items[0]
    shape = SHAPES.get(key) or {}
    if shape.get('kind') != 'group':
        return None
    t = {'rootQuestions': {k: {'answer': '', 'revision': 'v1'} for k in shape.get('root') or ()}}
    if shape.get('sub') is not None:
        t['subQuestions'] = {k: {'answer': '', 'revision': 'v1'} for k in shape['sub']}
    return t


def new_group_item(template_item):
    """Gruba yeni satir: ayni alanlar bos, yeni kimlik (auditXpress kimlikleri UUID4)."""
    def blank(qs):
        out = {}
        for k, v in (qs or {}).items():
            a = v.get('answer') if isinstance(v, dict) else None
            out[k] = {'answer': [] if isinstance(a, list) else '', 'revision': (v or {}).get('revision', 'v1')}
        return out
    item = {'id': str(_uuid.uuid4()), 'rootQuestions': blank(template_item.get('rootQuestions'))}
    if 'subQuestions' in template_item:
        item['subQuestions'] = blank(template_item.get('subQuestions'))
    return item


class Requirement:
    """Kontrol listesinin bir maddesi (resultScorings icindeki kayit uzerinde calisir)."""

    def __init__(self, report, index, data):
        self.report, self.index, self.data = report, index, data

    @property
    def uuid(self):
        return self.data.get('requirementUuid', '')

    @property
    def answers(self):
        return self.data.setdefault('answers', {})

    @property
    def score_id(self):
        sc = self.data.get('score')
        return (sc.get('scoreId') or '') if isinstance(sc, dict) else ''

    @property
    def fields(self):
        fa = self.answers.get('fieldAnswers')
        return fa if isinstance(fa, dict) else {}

    def number(self):
        return self.report.number_of(self.uuid)

    def entry(self):
        return self.report.dictionary.get(self.uuid) or {}

    @property
    def is_ko(self):
        return bool(self.entry().get('ko'))

    def title(self):
        """Madde basligi: numara (+ KO) + metnin basi; metin yoksa bolum, ic alan ya da aciklamanin basi."""
        num = self.number()
        if num:
            e = self.entry()
            text = re.sub(r'\s+', ' ', e.get('text') or '').strip()
            text = re.sub(r'^KO N°\s*\d+\s*:\s*', '', text)
            if not text:
                sec = (e.get('section') or '').split(' › ')[-1]
                text = re.sub(r'^[\d.]+\s*', '', sec)
            return ('%s%s %s' % (num, ' KO' if e.get('ko') else '', (text[:80] + '…') if len(text) > 80 else text)).strip()
        if self.fields:
            first = next(iter(self.fields))
            return 'Madde %d · %s' % (self.index + 1, label_of(re.sub(r'(_en)?$', '', first)))
        hint = re.sub(r'\s+', ' ', self.answers.get('englishExplanationText') or self.answers.get('explanationText') or '').strip()
        if hint:                                        # sozluk yokken: aciklamanin basi konuyu gosterir
            hint = re.sub(r'^(Deviation|Explanation)\s*:\s*', '', hint, flags=re.I)
            return 'Madde %d · %s' % (self.index + 1, (hint[:60] + '…') if len(hint) > 60 else hint)
        return 'Madde %d' % (self.index + 1)

    def needs_explanation(self):
        """B / C / D / NA puanli ama iki aciklama kutusu da bos."""
        a = self.answers
        return self.score_id in ('B', 'C', 'D', 'NA') and not ((a.get('englishExplanationText') or '').strip()
                                                               or (a.get('explanationText') or '').strip())


class IfsReport:
    def __init__(self, path=None, raw=None):
        self.path = os.path.abspath(path) if path else None
        if raw is None:
            if not path:
                raise IfsError('Dosya yok.')
            try:
                raw = pathlib.Path(path).read_bytes().decode('utf-8-sig')
            except (OSError, UnicodeDecodeError) as e:
                raise IfsError('Dosya okunamadı: %s' % e)
        try:
            self.doc = json.loads(raw)
        except ValueError as e:
            raise IfsError('Bu bir auditXpress (.ifs) dosyası değil: %s' % e)
        if not isinstance(self.doc, dict) or not isinstance(self.doc.get('data'), dict) \
                or not isinstance(self.doc['data'].get('modules'), dict) or not self.doc['data']['modules']:
            raise IfsError('Bu bir auditXpress (.ifs) dosyası değil (modül bulunamadı).')
        self.original_text = raw
        self.dictionary = load_dictionary(self.module_id)

    # ---- yapi
    @property
    def module_id(self):
        return next(iter(self.doc['data']['modules']))

    @property
    def module(self):
        return self.doc['data']['modules'][self.module_id]

    @property
    def questions(self):
        q = self.module.get('questions')
        return q if isinstance(q, dict) else {}

    @property
    def checklist(self):
        cls = self.module.get('checklists') or {}
        return next(iter(cls.values())) if cls else {}

    def requirements(self):
        rs = self.checklist.get('resultScorings') or {}
        return [Requirement(self, i, r) for i, r in enumerate(rs.values())]

    def requirement(self, uid):
        rs = self.checklist.get('resultScorings') or {}
        if uid in rs:
            return Requirement(self, list(rs).index(uid), rs[uid])
        return None

    def report_language(self):
        return (self.module.get('axpxSettings') or {}).get('reportLanguage') or self.doc['data'].get('language') or ''

    def standard_name(self):
        mid = self.module_id
        m = re.match(r'([a-z]+)_(\d+)', mid)
        return ('IFS %s %s' % (m.group(1).capitalize(), m.group(2))) if m else 'IFS ' + mid

    def company(self):
        return str((self.questions.get('companyName') or {}).get('answer') or '').strip()

    def title(self):
        name = self.company() or os.path.splitext(os.path.basename(self.path or 'IFS raporu'))[0]
        return '%s · %s' % (self.standard_name(), name)

    # ---- sozluk (madde no + metin); auditXpress dosyasinda yok
    def number_of(self, uid):
        return (self.dictionary.get(uid) or {}).get('no', '')

    def requirement_text(self, uid):
        return (self.dictionary.get(uid) or {}).get('text', '')

    # ---- rapor alanlari
    def group_of(self, key):
        base = re.sub(r'_en$', '', key)
        for gid, _t, keys in GROUPS:
            if key in keys or base in keys:
                return gid
        return 'summary'

    def question_keys(self, gid):
        keys = [k for k in self.questions if self.group_of(k) == gid]
        order = next((list(ks) for g, _t, ks in GROUPS if g == gid), [])
        rank = {k: i for i, k in enumerate(order)}
        return sorted(keys, key=lambda k: (rank.get(re.sub(r'_en$', '', k), 10 ** 6), re.sub(r'_en$', '', k), is_en(k)))

    def answer(self, key):
        return (self.questions.get(key) or {}).get('answer')

    def set_answer(self, key, value):
        q = self.questions.get(key)
        if q is None:
            raise IfsError('Alan yok: %s' % key)
        q['answer'] = value

    # ---- maddeler
    def set_score(self, uid, score_id):
        """Puani yazar; B/C/D'de duzeltme kaydi acilir, A/NA/bos'ta kapatilir; D sayisi guncellenir."""
        r = (self.checklist.get('resultScorings') or {}).get(uid)
        if r is None:
            raise IfsError('Madde yok: %s' % uid)
        if score_id and score_id not in SCORE_VALUE:
            raise IfsError('Bilinmeyen puan: %s' % score_id)
        r['score'] = {'value': SCORE_VALUE[score_id], 'scoreId': score_id, 'label': score_id} if score_id else \
            {'value': '', 'scoreId': '', 'label': ''}
        need = score_id in CORRECTION_SCORES
        r['isCorrectionRequired'] = need
        ca = self.checklist.setdefault('correctiveActions', {})
        if need and uid not in ca:
            ca[uid] = {'requirementUuid': uid, 'fields': {}}
        elif not need and uid in ca and not (ca[uid].get('fields') or {}):
            del ca[uid]                                 # yalniz bos kaydi kaldir: yazilmis duzeltici faaliyet kaybolmasin
        if 'dCount' in self.checklist:
            self.checklist['dCount'] = sum(1 for x in self.requirements() if x.score_id == 'D')

    def set_text(self, uid, field, text):
        if field not in ('explanationText', 'englishExplanationText', 'note'):
            raise IfsError('Alan yok: %s' % field)
        self.requirement(uid).answers[field] = text

    def counts(self):
        c = {sid: 0 for sid, _v in SCORES}
        c[''] = 0
        for r in self.requirements():
            sid = r.score_id if r.score_id in c else ''
            c[sid] += 1
        return c

    # ---- kaydetme
    def dumps(self, hash_mode='keep'):
        doc = self.doc
        if hash_mode == 'clear':
            doc = dict(doc)
            for k in HASH_KEYS:
                if k in doc:
                    doc[k] = ''
        return json.dumps(doc, ensure_ascii=False, separators=(',', ':'))

    def changed(self):
        return self.dumps() != self.original_text

    def save(self, path=None, hash_mode='keep', backup_dir=None):
        path = os.path.abspath(path or self.path)
        text = self.dumps(hash_mode)
        if backup_dir and os.path.isfile(path):
            os.makedirs(backup_dir, exist_ok=True)
            stamp = time.strftime('%Y%m%d-%H%M%S')
            shutil.copy2(path, os.path.join(backup_dir, '%s.%s.ifs' % (os.path.splitext(os.path.basename(path))[0], stamp)))
            old = sorted(p for p in os.listdir(backup_dir) if p.endswith('.ifs'))
            for p in old[:-20]:
                try:
                    os.remove(os.path.join(backup_dir, p))
                except OSError:
                    pass
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='') as fh:
            fh.write(text)
        os.replace(tmp, path)
        self.path = path
        self.original_text = self.dumps()
        return path

    def snapshot(self):
        return copy.deepcopy(self.doc)

    def restore(self, snap):
        self.doc = snap


def load_dictionary(module_id):
    """Madde sozlugu {uuid: {'no', 'ko', 'star', 'section', 'text'}}.
    Paketteki <modul>-requirements.json: kimlik -> madde no, KO, bolum (IFS metni yok - telifli). Kullanicinin ice aktardigi
    <modul>-texts.json (yerel, yalniz bu bilgisayarda): kimlik -> madde metni. Ikisi birlestirilir."""
    out = {}
    for base in (data_dir(), user_dictionary_dir()):
        for name in ('%s-requirements.json' % module_id, '%s-texts.json' % module_id):
            p = pathlib.Path(base) / name
            try:
                rows = json.loads(p.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(rows, dict):
                rows = [dict(v, uuid=k) for k, v in rows.items() if isinstance(v, dict)]
            for r in rows if isinstance(rows, list) else []:
                if not (isinstance(r, dict) and r.get('uuid')):
                    continue
                e = out.setdefault(r['uuid'], {'no': '', 'ko': False, 'star': False, 'section': '', 'text': ''})
                for k in ('no', 'section', 'text'):
                    if r.get(k):
                        e[k] = str(r[k])
                for k in ('ko', 'star'):
                    if k in r:
                        e[k] = bool(r[k])
    return out


def parse_checklist_text(raw):
    """IFS kontrol listesi (Excel'den kopyalanmis, sekmeyle ayrilmis: no <TAB> metin; cok satirli hucreler tirnakli).
    Donus: sirali maddeler [{'no', 'ko', 'star', 'text'}] ve basliklar {no: baslik}. Basliklar madde sayilmaz."""
    import csv
    import io
    raw = raw.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    rows = list(csv.reader(io.StringIO(raw), delimiter='\t', quotechar='"'))
    reqs, heads = [], {}
    for r in rows:
        if not r or not any(c.strip() for c in r):
            continue
        num = r[0].strip()
        text = (r[1] if len(r) > 1 else '').strip()
        m = re.match(r'^(\d+(?:\.\d+)*)\.?', num.replace(' ', ''))
        if not m:
            continue
        n = m.group(1)
        is_req = ('shall' in text.lower() or text.startswith('KO N') or len(text) > 120) and n.count('.') >= 2
        if is_req:
            reqs.append({'no': n, 'ko': 'KO' in num, 'star': '*' in num, 'text': _unwrap(text)})
        else:
            heads[n] = re.sub(r'\s+', ' ', text).strip()
    return reqs, heads


def _unwrap(text):
    """PDF'ten gelen satir kirilmalarini birlestirir; madde imli (•) satirlar ayri kalir."""
    lines = [ln.strip() for ln in text.strip().split('\n')]
    out = []
    for ln in lines:
        if not ln:
            continue
        if out and not ln.startswith('•') and not out[-1].endswith(':') and not out[-1].startswith('•'):
            out[-1] += ' ' + ln
        elif out and not ln.startswith('•') and out[-1].startswith('•') and not out[-1].endswith(('.', ':')):
            out[-1] += ' ' + ln                         # madde iminin devam satiri
        else:
            out.append(ln)
    return '\n'.join(out)


def import_requirement_texts(report, path):
    """Kullanicinin IFS kontrol listesi dosyasindan madde metinlerini bu raporun kimliklerine (sirayla) esler ve yerel
    sozluge yazar. Madde sayisi tutmazsa ya da numaralar paketteki sozlukle celisirse hata verir (yanlis esleme olmasin)."""
    try:
        raw = pathlib.Path(path).read_bytes().decode('utf-8-sig', 'replace')
    except OSError as e:
        raise IfsError('Dosya okunamadı: %s' % e)
    reqs, _heads = parse_checklist_text(raw)
    items = report.requirements()
    if len(reqs) != len(items):
        raise IfsError('Listede %d madde var, raporda %d. Liste bu standardın kontrol listesi değil ya da eksik.'
                       % (len(reqs), len(items)))
    bad = [(it.number(), r['no']) for it, r in zip(items, reqs) if it.number() and it.number() != r['no']]
    if bad:
        raise IfsError('Madde numaraları sözlükle uyuşmuyor (ör. %s ≠ %s); metinler eşlenmedi.' % bad[0])
    out = [{'uuid': it.uuid, 'no': r['no'], 'ko': r['ko'], 'star': r['star'], 'text': r['text']} for it, r in zip(items, reqs)]
    d = pathlib.Path(user_dictionary_dir())
    d.mkdir(parents=True, exist_ok=True)
    (d / ('%s-texts.json' % report.module_id)).write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    report.dictionary = load_dictionary(report.module_id)
    return len(out)


def user_dictionary_dir():
    try:
        import agfo_editor_core as core
        return core.data_dir() / 'ifs'
    except Exception:
        return pathlib.Path(os.path.expanduser('~')) / '.agfo-ifs'


def looks_like_ifs(path) -> bool:
    if not str(path).lower().endswith('.ifs'):
        return False
    try:
        with open(path, 'rb') as fh:
            head = fh.read(400).decode('utf-8-sig', 'replace')
    except OSError:
        return False
    return '"schemaVersion"' in head or '"axpxVersion"' in head or '"data"' in head
