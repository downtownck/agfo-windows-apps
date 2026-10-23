# -*- coding: utf-8 -*-
"""AGFO AI Editor - BRCGS kapsam lambalari (coverage engine), birebir port.

Kaynak: AGFO BRCGS Report Studio v5.2.1
  assets/coverage.js            window.AgfoBrsCoverage (+ AgfoBrsCore.normalizeProfile)
  assets/editor.js              kilavuz form alanlari: resolveClause / formFor / guideKey /
                                structOf / assembleText (Excel ice aktarma da bunlari kullanir)
  includes/class-admin-page.php agfoBrs.standards / agfoBrs.knowledge / agfoBrs.boxes yerellestirmesi
  includes/class-standard.php, class-knowledge.php, class-report-boxes.php (JSON yukleyiciler)

Bu bir PORT'tur, yeniden tasarim degil: eslestirme kurallari, sira ve JS'in tuhafliklari korunur.
JS'e ozgu davranislar bilerek taklit edilir:
  * JS bosluk sinifi (\\s, trim) Python'unkinden farklidir -> _JS_WS.
  * Object.keys() sirasi: tam sayi gorunumlu anahtarlar once ve artan sirada -> js_keys().
  * Duz nesnelerde ({}) prototip anahtarlari ('constructor', '__proto__', 'toString' ...) "dolu"
    sayilir -> _jget() / _PROTO. (Ornek: uniqTextList 'constructor' kelimesini atar.)
  * PHP json_decode(assoc)+wp_localize_script gidis-donusu: bos {} -> [], 0..n-1 anahtarli
    nesne -> dizi -> php_json_roundtrip().
  * String uzunluklari UTF-16 kod birimiyle (JS .length) -> _js_len().
HTML ureten fonksiyonlar (panelHtml, indicatorHtml, languageBadgeHtml, guideExpectationsHtml)
yerine Tk arayuzunun cizecegi veriyi donduren panel_data / indicator_data / language_badge /
guide_expectations verilir.
"""
from __future__ import annotations

import functools
import json
import math
import pathlib
import re
import sys

# ---------------------------------------------------------------------------
# JS uyumluluk yardimcilari
# ---------------------------------------------------------------------------

# ECMAScript WhiteSpace + LineTerminator (\s ve String.prototype.trim kumesi)
_JS_WS_CHARS = '\t\n\x0b\x0c\r \xa0  -     　﻿'
_JS_WS_RUN = re.compile('[' + _JS_WS_CHARS + ']+')
_JS_TRIM = re.compile('^[' + _JS_WS_CHARS + ']+|[' + _JS_WS_CHARS + ']+$')

# Object.prototype uzerindeki ozellikler: duz bir JS nesnesinde obj[k] bunlar icin "truthy" doner.
_OBJ_PROTO_KEYS = frozenset((
    'constructor', '__proto__', 'toString', 'toLocaleString', 'valueOf', 'hasOwnProperty',
    'isPrototypeOf', 'propertyIsEnumerable', '__defineGetter__', '__defineSetter__',
    '__lookupGetter__', '__lookupSetter__',
))


class _ProtoValue(dict):
    """Prototipten gelen (fonksiyon) degerin yerine gecer: truthy ama hicbir alani yok."""

    def __bool__(self):
        return True


_PROTO = _ProtoValue()


def _jget(obj, key):
    """JS `obj[key]` (obj JSON'dan gelen nesne/dizi). Yoksa None."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        return _PROTO if key in _OBJ_PROTO_KEYS else None
    if isinstance(obj, list):
        if isinstance(key, str) and re.fullmatch(r'0|[1-9][0-9]*', key) and int(key) < len(obj):
            return obj[int(key)]
        return None
    return None


def _truthy(v) -> bool:
    """JS ToBoolean."""
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return not (v == 0 or (isinstance(v, float) and math.isnan(v)))
    if isinstance(v, str):
        return v != ''
    return True  # nesne / dizi (bos olsa bile) / True


def js_str(v) -> str:
    """JS String(v)."""
    if v is None:
        return 'null'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, float):
        if math.isnan(v):
            return 'NaN'
        if math.isinf(v):
            return 'Infinity' if v > 0 else '-Infinity'
        if v.is_integer() and abs(v) < 1e21:
            return str(int(v))
        return repr(v)
    if isinstance(v, list):
        return ','.join('' if x is None else js_str(x) for x in v)
    if isinstance(v, dict):
        return '[object Object]'
    return str(v)


def _or_str(v, default='') -> str:
    """JS `String(v || default)`."""
    return js_str(v) if _truthy(v) else default


def js_trim(s: str) -> str:
    return _JS_TRIM.sub('', s)


def _js_len(s: str) -> int:
    """JS .length (UTF-16 kod birimi)."""
    return len(s.encode('utf-16-le')) // 2


def _as_list(v) -> list:
    """JS `v || []` ardindan dizi gibi kullanim."""
    if isinstance(v, list):
        return v
    return []


def _concat(*args) -> list:
    """JS [].concat(a, b, ...): dizi ise acilir, degilse tek eleman eklenir."""
    out = []
    for a in args:
        if isinstance(a, list):
            out.extend(a)
        else:
            out.append(a)
    return out


_INDEX_KEY = re.compile(r'0|[1-9][0-9]*')


def js_keys(obj) -> list:
    """JS Object.keys(): dizi indeksi gorunumlu anahtarlar once (artan), sonra ekleme sirasi."""
    if isinstance(obj, list):
        return [str(i) for i in range(len(obj))]
    if not isinstance(obj, dict):
        return []
    idx, rest = [], []
    for k in obj:
        ks = str(k)
        if _INDEX_KEY.fullmatch(ks) and int(ks) < 4294967295:
            idx.append(ks)
        else:
            rest.append(ks)
    idx.sort(key=int)
    return idx + rest


def php_json_roundtrip(value):
    """PHP json_decode(..., true) + json_encode (wp_localize_script) sonrasi JS'in gordugu yapi.

    PHP dizisi bossa veya anahtarlari tam olarak 0..n-1 ise JSON dizisi olarak yazilir.
    """
    if isinstance(value, dict):
        if not value:
            return []
        keys = list(value.keys())
        if all(k == str(i) for i, k in enumerate(keys)):
            return [php_json_roundtrip(value[k]) for k in keys]
        return {k: php_json_roundtrip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [php_json_roundtrip(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Veri yukleyici (agfoBrs.standards / agfoBrs.knowledge / agfoBrs.boxes karsiligi)
# ---------------------------------------------------------------------------

PROFILES = ('pm', 'fs', 'cp', 'ab', 'sd')
_STANDARD_FILES = {'pm': 'pm_i7_standard.json', 'fs': 'fs_i9_standard.json', 'cp': 'cp_i4_standard.json',
                   'ab': 'ab_i3_standard.json', 'sd': 'sd_i4_standard.json'}
_KNOWLEDGE_FILES = {'pm': 'pm_i7_howto.json', 'fs': 'fs_i9_howto.json', 'cp': 'cp_i4_howto.json',
                    'ab': 'ab_i3_howto.json', 'sd': 'sd_i4_howto.json'}

_data_dir = None
_cache: dict = {}
_guide_index_cache: dict = {}


def data_dir() -> pathlib.Path:
    """brcgs_data klasoru (PyInstaller'da _MEIPASS/brcgs_data)."""
    if _data_dir is not None:
        return _data_dir
    base = getattr(sys, '_MEIPASS', None)
    if base and (pathlib.Path(base) / 'brcgs_data').is_dir():
        return pathlib.Path(base) / 'brcgs_data'
    return pathlib.Path(__file__).resolve().parent.parent / 'brcgs_data'


def set_data_dir(path) -> None:
    """Veri klasorunu degistir (testler icin); tum onbellekleri temizler."""
    global _data_dir
    _data_dir = pathlib.Path(path) if path is not None else None
    _cache.clear()
    _guide_index_cache.clear()
    _form_cache.clear()


def _load_json_file(rel: str):
    """PHP load_profile(): okunamaz/gecersiz ise array() (JS'te [])."""
    path = data_dir() / rel
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    return php_json_roundtrip(data) if isinstance(data, (dict, list)) else []


def all_standards() -> dict:
    """agfoBrs.standards: {profil: standard JSON} (AGFO_BRS_Standard::load_all)."""
    if 'standards' not in _cache:
        _cache['standards'] = {p: _load_json_file('standards/' + _STANDARD_FILES[p]) for p in PROFILES}
    return _cache['standards']


def all_knowledge() -> dict:
    """agfoBrs.knowledge: {profil: how-to JSON} (AGFO_BRS_Knowledge::load_all)."""
    if 'knowledge' not in _cache:
        _cache['knowledge'] = {p: _load_json_file('knowledge/' + _KNOWLEDGE_FILES[p]) for p in PROFILES}
    return _cache['knowledge']


def guide_fields_data():
    """window.AgfoBrsGuideFields (assets/guide-fields.js) - JS nesnesi, PHP'den gecmez."""
    if 'guide_fields' not in _cache:
        try:
            with open(data_dir() / 'guide_fields.json', encoding='utf-8') as fh:
                _cache['guide_fields'] = json.load(fh)
        except (OSError, ValueError):
            _cache['guide_fields'] = {}
    return _cache['guide_fields']


def all_box_maps() -> dict:
    """agfoBrs.boxes (class-admin-page.php box_maps()): {profil: {units, boxes, optional, modules}}."""
    if 'boxes' in _cache:
        return _cache['boxes']
    out = {}
    for profile in ('fs', 'pm', 'cp', 'ab', 'sd'):
        spec = _load_json_file('report-boxes/%s_boxes.json' % profile)
        spec = spec if isinstance(spec, dict) else {}
        units_l = spec.get('units') if isinstance(spec.get('units'), list) else []
        boxes_l = spec.get('boxes') if isinstance(spec.get('boxes'), list) else []
        if not boxes_l or not units_l:  # has_spec()
            continue
        units, optional, boxes = {}, {}, {}
        for unit in units_l:
            units[_php_str(unit.get('key'))] = _php_str(unit.get('box'))
            if _php_nonempty(unit.get('optional_module')):
                optional[_php_str(unit.get('key'))] = {
                    'module': _php_str(unit.get('optional_module')),
                    'title': _php_str(unit.get('title')) if unit.get('title') is not None else '',
                    'requirement': _php_str(unit.get('requirement')) if unit.get('requirement') is not None else '',
                    'brcgs_ref': _php_str(unit.get('brcgs_ref')) if unit.get('brcgs_ref') is not None else '',
                    'regulation': _php_str(unit.get('regulation')) if unit.get('regulation') is not None else '',
                }
        for box in boxes_l:
            boxes[_php_str(box.get('tag'))] = {'clause': _php_str(box.get('clause')), 'title': _php_str(box.get('title'))}
        mods = spec.get('optional_modules')
        out[profile] = php_json_roundtrip({
            'units': units, 'boxes': boxes, 'optional': optional,
            'modules': mods if isinstance(mods, (dict, list)) else [],
        })
    _cache['boxes'] = out
    return out


def _php_str(v) -> str:
    """PHP (string) cast (null -> '', true -> '1', false -> '')."""
    if v is None or v is False:
        return ''
    if v is True:
        return '1'
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _php_nonempty(v) -> bool:
    """PHP ! empty($v)."""
    return not (v is None or v is False or v == '' or v == '0' or v == 0 or v == [] or v == {})


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def normalize_profile(slug) -> str:
    """AgfoBrsCore.normalizeProfile: bilinmeyen profil 'pm' olur."""
    slug = _or_str(slug).lower()
    if slug in ('ab_i3', 'agents_brokers'):
        return 'ab'
    if slug in ('sd_i4', 'storage_distribution'):
        return 'sd'
    if slug in ('pm', 'fs', 'cp', 'ab', 'sd'):
        return slug
    return 'pm'


# ---------------------------------------------------------------------------
# Metin yardimcilari
# ---------------------------------------------------------------------------

def norm_text(s) -> str:
    """normText: kucuk harf, bosluk katlama, trim."""
    return _norm_str('' if s is None else js_str(s))


@functools.lru_cache(maxsize=8192)
def _norm_str(s: str) -> str:
    # Saf fonksiyon; onbellek yalniz hiz icin (lambalar her tus vurusunda yeniden hesaplanir).
    return js_trim(_JS_WS_RUN.sub(' ', s.lower()))


def _text_list(arr) -> list:
    return [js_trim(js_str(x)) for x in _as_list(arr) if js_trim(_or_str(x))]


def uniq_text_list(arr) -> list:
    """uniqTextList: kirpilmis, bos olmayan, kucuk harfe gore tekil (ilk gorulen korunur)."""
    seen, out = set(), []
    for x in _text_list(arr):
        k = x.lower()
        if k in seen or k in _OBJ_PROTO_KEYS:  # JS: seen = {} -> seen['constructor'] truthy
            continue
        seen.add(k)
        out.append(x)
    return out


def _has_any(text, arr) -> bool:
    text = norm_text(text)
    if not text:
        return False
    for kw in _as_list(arr):
        k = norm_text(kw)
        if k and k in text:
            return True
    return False


# ---------------------------------------------------------------------------
# Dil algilama
# ---------------------------------------------------------------------------

_TR_CHARS = re.compile('[ğüşöçı]')
_TR_WORDS = ['ve', 'ile', 'için', 'olarak', 'tarafından', 'bulunmaktadır', 'edilmiştir', 'yapılmıştır', 'kayıt',
             'sistem', 'prosedür', 'ürün', 'hammadde', 'ambalaj', 'malzeme', 'izlenebilirlik', 'tedarikçi',
             'uygunluk', 'kontrol', 'denetim', 'kanıt', 'numaralı', 'tarihli', 'gerçekleştirilmiştir']
_EN_WORDS = ['the', 'and', 'with', 'for', 'shall', 'site', 'system', 'procedure', 'records', 'record', 'product',
             'raw', 'materials', 'packaging', 'traceability', 'supplier', 'audit', 'was', 'were', 'has', 'have',
             'is', 'are', 'monitoring']


def coverage_language(text) -> str:
    """Cov.language: 'tr' | 'en' | 'mixed' | 'unknown'."""
    return _language_of_clean(norm_text(text))


@functools.lru_cache(maxsize=1024)
def _language_of_clean(clean: str) -> str:
    tokens = [t for t in clean.split(' ') if t]
    if not clean or len(tokens) < 2:
        return 'unknown'
    tr = len(_TR_CHARS.findall(clean)) * 2
    en = 0
    for word in tokens:
        if any(_word_match_norm(word, k) for k in _TR_WORDS):
            tr += 1
        if word in _EN_WORDS:
            en += 1
    if tr >= 2 and en >= 2 and max(tr, en) / max(1, min(tr, en)) < 1.8:
        return 'mixed'
    if tr >= 2 and tr > en:
        return 'tr'
    if en >= 2 and en > tr:
        return 'en'
    if tr >= 2:
        return 'tr'
    if en >= 2:
        return 'en'
    return 'unknown'


def language_label(lang) -> str:
    """Cov.languageLabel."""
    return {'tr': 'Türkçe', 'en': 'English', 'mixed': 'Karma TR/EN'}.get(lang, 'Belirsiz')


def combined_language(report, evidence) -> str:
    """Cov.combinedLanguage: rapor + kanit notu dili."""
    a, b = coverage_language(report), coverage_language(evidence)
    if a == 'unknown':
        return b
    if b == 'unknown' or a == b:
        return a
    return 'mixed'


# ---------------------------------------------------------------------------
# Turkce ek toleransli eslestirme
# ---------------------------------------------------------------------------

_SOFT = {'k': 'ğ', 'p': 'b', 't': 'd', 'ç': 'c'}


def turkish_word_match(word, keyword) -> bool:
    """turkishWordMatch: esitlik, onek (ek toleransi), kisa kelime onegi, unsuz yumusamasi."""
    return _word_match_norm(norm_text(word), norm_text(keyword))


def _word_match_norm(word: str, keyword: str) -> bool:
    """turkishWordMatch govdesi; girdiler zaten normText'ten gecmis (normText idempotenttir)."""
    if not word or not keyword:
        return False
    if word == keyword or word.startswith(keyword) or \
            ((len(word) >= 5 or _js_len(word) >= 5) and keyword.startswith(word)):
        return True
    last, base = keyword[-1:], keyword[:-1]
    return last in _SOFT and word.startswith(base + _SOFT[last])


_TR_STOP = {'ve', 'ile', 'icin', 'için', 'bir', 'bu', 'da', 'de', 'olan', 'olarak'}


def turkish_words_in_order(text, phrase) -> bool:
    """turkishWordsInOrder: ifadenin (durak kelimesiz) kelimeleri metinde ayni sirada var mi."""
    words = _phrase_words(norm_text(phrase))
    tokens = _text_tokens(norm_text(text))
    if not words:
        return False
    pos = 0
    for w in words:
        found = -1
        for j in range(pos, len(tokens)):
            if _word_match_norm(tokens[j], w):
                found = j
                break
        if found < 0:
            return False
        pos = found + 1
    return True


@functools.lru_cache(maxsize=8192)
def _phrase_words(clean: str) -> tuple:
    # JS: stop = {...} duz nesne -> 'constructor' / '__proto__' de durak kelimesi sayilir
    return tuple(w for w in clean.replace('-', ' ').split(' ')
                 if w and w not in _TR_STOP and w not in _OBJ_PROTO_KEYS)


@functools.lru_cache(maxsize=256)
def _text_tokens(clean: str) -> tuple:
    return tuple(t for t in _JS_WS_RUN.split(clean.replace('-', ' ')) if t)


def _has_any_turkish(text, arr) -> bool:
    return any(turkish_words_in_order(text, p) for p in _as_list(arr))


# ---------------------------------------------------------------------------
# Turkce anlam sozlugu (coverage.js trKeywordDictionary, birebir)
# ---------------------------------------------------------------------------

TR_KEYWORD_DICTIONARY = {
    'product defence': 'ürün savunması', 'threat assessment': 'tehdit değerlendirmesi',
    'product defence plan': 'ürün savunma planı', 'food contact': 'gıda temas uygunluğu',
    'food safety plan': 'gıda güvenliği planı', 'documented threat assessment': 'dokümante tehdit değerlendirmesi',
    'security arrangements': 'güvenlik düzenlemeleri', 'potential risks': 'potansiyel riskler',
    'deliberate attempt': 'kasıtlı kontaminasyon girişimi', 'contamination damage': 'kontaminasyon veya zarar verme riski',
    'authorised personnel': 'yetkili personel erişimi', 'contractors': 'yüklenici erişimi',
    'visitors': 'ziyaretçi kontrolü', 'visitor reporting': 'ziyaretçi bildirim sistemi',
    'security procedures': 'güvenlik prosedürleri', 'unidentified': 'tanımlanmamış kişi bildirimi',
    'unknown': 'bilinmeyen ziyaretçi raporlama', 'complaint': 'müşteri şikayetleri',
    'investigation': 'şikayet incelemesi', 'root cause': 'kök neden analizi', 'trend': 'trend analizi',
    'record': 'kayıtların izlenebilirliği', 'traceability': 'izlenebilirlik sistemi',
    'recall': 'ürün geri çağırma', 'withdrawal': 'ürün geri çekme',
    'non-conforming': 'uygun olmayan ürün/malzeme', 'corrective action': 'düzeltici faaliyet',
    'preventive action': 'önleyici faaliyet', 'internal audit': 'iç denetim programı',
    'supplier approval': 'tedarikçi onayı', 'supplier of services': 'hizmet tedarikçisi onayı',
    'specification': 'spesifikasyon yönetimi', 'document control': 'doküman kontrolü',
    'controlled document': 'kontrollü doküman listesi', 'record keeping': 'kayıt tutma',
    'maintenance': 'bakım programı', 'cleaning': 'temizlik prosedürleri', 'pest': 'haşere yönetimi',
    'calibration': 'kalibrasyon kayıtları', 'training': 'personel eğitimi',
    'competence': 'yetkinlik değerlendirmesi', 'hygiene': 'hijyen uygulamaları',
    'medical screening': 'sağlık durumu bildirimi', 'symptoms of infection': 'hastalık/enfeksiyon belirtisi',
    'disease or condition': 'hastalık durumu bildirimi', 'temporary personnel': 'geçici personel bildirimi',
    'excluded from work': 'çalışmadan uzaklaştırma', 'protective clothing': 'koruyucu kıyafet kontrolü',
    'incident': 'olay yönetimi', 'management review': 'yönetimin gözden geçirmesi',
    'objective': 'ölçülebilir hedefler', 'policy': 'dokümante politika', 'procedure': 'dokümante prosedür',
    'monitoring': 'izleme kayıtları', 'verification': 'doğrulama faaliyetleri', 'validation': 'geçerli kılma',
    'risk assessment': 'risk değerlendirmesi', 'hazard analysis': 'tehlike analizi',
    'prerequisite programme': 'ön koşul programı', 'process flow': 'proses akış diyagramı',
    'critical limits': 'kritik limitler', 'control measure': 'kontrol önlemi'
}


def _semantic_turkish_from_english(arr) -> list:
    found = []
    for phrase in uniq_text_list(arr):
        low = phrase.lower()
        for k, v in TR_KEYWORD_DICTIONARY.items():
            if k in low:
                found.append(v)
    return found


_SEED_SPLIT = re.compile(r'[.;:()\[\],/\-]+')
_LABEL_KEEP = re.compile('[^A-Za-zğüşöçıİĞÜŞÖÇ]')


def derive_turkish_keywords(ci) -> list:
    """Cov.turkishKeywords: keywords_tr (ve esdegerleri) varsa onlar; yoksa sozluk + etiket/hatirlatma tohumlari."""
    ci = ci if isinstance(ci, dict) else {}
    direct = _concat(*[ci.get(k) if _truthy(ci.get(k)) else []
                       for k in ('keywords_tr', 'turkish_keywords', 'keywords_tr_any', 'tr_keywords_any',
                                 'keywords_turkish')])
    if direct:
        return uniq_text_list(direct)

    group_words = []
    for g in _as_list(ci.get('keywords_groups')):
        group_words = _concat(group_words, g if _truthy(g) else [])
    found = _semantic_turkish_from_english(_concat(ci.get('keywords_any') if _truthy(ci.get('keywords_any')) else [],
                                                   group_words))

    seed = ' '.join([_or_str(ci.get('label')), _or_str(ci.get('reminder'))])
    for part in _SEED_SPLIT.split(seed):
        t = js_trim(part)
        if _js_len(t) >= 4:
            found.append(t)
    for word in _JS_WS_RUN.split(_or_str(ci.get('label'))):
        t = js_trim(_LABEL_KEEP.sub('', word))
        if _js_len(t) >= 4:
            found.append(t)
    return uniq_text_list(found)[:20]


# ---------------------------------------------------------------------------
# Kapsam karari
# ---------------------------------------------------------------------------

def covers_item_english(text, item) -> bool:
    """coversItemEnglish: keywords_any'den biri VE her keywords_groups grubundan biri."""
    if not _has_any(text, item.get('keywords_any')):
        return False
    for g in _as_list(item.get('keywords_groups')):
        if not _has_any(text, g):
            return False
    return True


def covers_item_turkish(text, item) -> bool:
    """coversItemTurkish: turetilmis Turkce ifadelerden biri sirali kelime eslesmesiyle + TR gruplari."""
    any_ = derive_turkish_keywords(item)
    if not any_ or not _has_any_turkish(text, any_):
        return False
    groups = item.get('keywords_groups_tr') if _truthy(item.get('keywords_groups_tr')) else item.get('turkish_keywords_groups')
    for g in _as_list(groups):
        if not _has_any_turkish(text, g):
            return False
    return True


def covers_item(text, item, lang=None) -> bool:
    """Cov.coversItem."""
    if not _truthy(item):
        return False
    text = norm_text(text)
    if not text:
        return False
    lang = lang if _truthy(lang) else coverage_language(text)
    if lang == 'tr':
        return covers_item_turkish(text, item)
    if lang == 'en':
        return covers_item_english(text, item)
    return covers_item_english(text, item) or covers_item_turkish(text, item)


def item_status(item, report, evidence) -> str:
    """Cov.itemStatus: green = rapor metninde, yellow = yalniz kanit notunda, red = yok, grey = tanim yok."""
    if not _truthy(item):
        return 'grey'
    report_lang = coverage_language(report)
    if covers_item(report, item, report_lang):
        return 'green'
    combined = _or_str(report) + ' ' + _or_str(evidence)
    if covers_item(combined, item, combined_language(report, evidence)):
        return 'yellow'
    return 'red'


def status_label(status, lang) -> str:
    """Cov.statusLabel."""
    suffix = ' · ' + language_label(lang) + ' otomatik'
    if status == 'green':
        return 'rapor metninde bulundu' + suffix
    if status == 'yellow':
        return 'yalnız kanıt notunda bulundu' + suffix
    if status == 'red':
        return 'eşleşme bulunamadı' + suffix
    return 'manuel / tanımsız'


# ---------------------------------------------------------------------------
# Standart / kilavuz arama
# ---------------------------------------------------------------------------

def standard_for(profile):
    """Cov.standardFor."""
    v = _jget(all_standards(), normalize_profile(profile))
    return v if _truthy(v) else {}


def knowledge_for(profile):
    """Cov.knowledgeFor."""
    v = _jget(all_knowledge(), normalize_profile(profile))
    return v if _truthy(v) else {}


_LEADING_ZEROS = re.compile(r'^0+(?=[0-9])')


def normalize_section_key(key) -> str:
    """normalizeSectionKey: trim + bastaki sifirlar ('01.2' -> '1.2')."""
    return _LEADING_ZEROS.sub('', js_trim(_or_str(key)), count=1)


def parent_key_of(key) -> str:
    """parentKeyOf: '4.3.2' -> '4.3', '4' -> ''."""
    parts = normalize_section_key(key).split('.')
    if len(parts) <= 1:
        return ''
    return '.'.join(parts[:-1])


def _add_item_once(lst, seen, item):
    if not _truthy(item):
        return
    item_id = normalize_section_key(item.get('clause') if isinstance(item, dict) else None) + '|' + \
        js_str(item.get('label') if isinstance(item, dict) and _truthy(item.get('label')) else '')
    if item_id in seen:
        return
    seen.add(item_id)
    lst.append(item)


def _items_of(defn) -> list:
    v = _jget(defn, 'coverage_items') if isinstance(defn, (dict, list)) else None
    return v if isinstance(v, list) else []


def coverage_items_for_key(standard, sections, key) -> list:
    """coverageItemsForKey: kutunun kendi ogeleri + tum alt maddelerinin ogeleri + duz listeden eslesenler."""
    key = normalize_section_key(key)
    items, seen = [], set()
    if not key:
        return items
    own = _jget(sections, key)
    if _truthy(own):
        for ci in _items_of(own):
            _add_item_once(items, seen, ci)
    for sec in js_keys(sections):
        norm = normalize_section_key(sec)
        if norm == key or not norm.startswith(key + '.'):
            continue
        for ci in _items_of(_jget(sections, sec)):
            _add_item_once(items, seen, ci)
    flat = _jget(standard, 'coverage_items') if _truthy(standard) else None
    for ci in (flat if isinstance(flat, list) else []):
        clause = normalize_section_key(ci.get('clause') if isinstance(ci, dict) else None)
        if not clause:
            continue
        if clause == key or clause.startswith(key + '.'):
            _add_item_once(items, seen, ci)
    return items


def section_coverage(profile, clause, coverage_parent=None, title=None):
    """Cov.sectionCoverage: tam madde, yoksa YALNIZ dogrudan ust madde. Dallar arasi odunc yok.

    Donus: None ya da {section, title, chapter, guide_reminder, original_text, coverage_items}.
    """
    standard = standard_for(profile)
    sections = _jget(standard, 'sections') if _truthy(standard) else None
    sections = sections if _truthy(sections) else {}
    key = normalize_section_key(clause)
    exact = _jget(sections, key)
    exact = exact if _truthy(exact) else None

    coverage_key = key
    if _truthy(coverage_parent):
        coverage_key = normalize_section_key(coverage_parent)
    elif not exact:
        parent = parent_key_of(key)
        if parent and _truthy(_jget(sections, parent)):
            coverage_key = parent

    items = coverage_items_for_key(standard, sections, coverage_key)
    if not items and coverage_key != key:
        items = coverage_items_for_key(standard, sections, key)
    if not exact and not items:
        return None

    def ex(field):
        v = exact.get(field) if exact else None
        return v if _truthy(v) else None

    m = re.match(r'[0-9]+', key)
    return {
        'section': key,
        'title': ex('title') or (title if _truthy(title) else None) or ('Section ' + key),
        'chapter': ex('chapter') or (m.group(0) if m else ''),
        'guide_reminder': ex('guide_reminder') or '',
        'original_text': ex('original_text') or '',
        'coverage_items': items,
    }


def summary(coverage, report, note) -> dict:
    """Cov.summary: {green, yellow, red, grey, total}."""
    items = (coverage or {}).get('coverage_items') or []
    counts = {'green': 0, 'yellow': 0, 'red': 0, 'grey': 0, 'total': len(items)}
    for ci in items:
        counts[item_status(ci, _or_str(report), _or_str(note))] += 1
    return counts


def badge_text(counts) -> str:
    """Cov.badgeText: '3/5 +1 kanıt · 1 eksik' ya da 'manuel'."""
    if not counts or not counts.get('total'):
        return 'manuel'
    out = '%d/%d' % (counts['green'], counts['total'])
    if counts.get('yellow'):
        out += ' +%d kanıt' % counts['yellow']
    if counts.get('red'):
        out += ' · %d eksik' % counts['red']
    return out


# ---------------------------------------------------------------------------
# Gosterim verisi (HTML render fonksiyonlarinin yerine)
# ---------------------------------------------------------------------------

_REQ_FIELDS = ('original_text', 'original_clause_text', 'official_text', 'requirement', 'requirement_text',
               'standard_text', 'clause_text', 'content', 'full_text')
REQUIREMENT_MISSING_TEXT = (
    'Bu madde için orijinal standart metni mevcut standard JSON içinde yok. Bu alan özet/reminder ile doldurulmaz. '
    'Orijinal metni göstermek için coverage item kaydına original_text, original_clause_text, official_text, '
    'requirement_text, standard_text veya clause_text alanı eklenmelidir.')
NO_DEFINITION_TITLE = 'Keyword tanımı yok'
NO_DEFINITION_TEXT = ('Bu bölüm şimdilik manuel kontrol edilir. Standard JSON içine coverage item eklenince '
                      'lamba çalışır.')


def clause_requirement_text(ci) -> str:
    """Cov.clauseRequirementText: orijinal madde metni alanlari, tekil, satir satir."""
    lines = [js_str(ci[k]) for k in _REQ_FIELDS if isinstance(ci, dict) and _truthy(ci.get(k))]
    return '\n'.join(uniq_text_list(lines))


def indicator_data(ci, report, note) -> dict:
    """indicatorHtml'in cizdigi veri: tek bir lamba satiri."""
    status = item_status(ci, report, note)
    lang = coverage_language(report) if status == 'green' else combined_language(report, note)
    groups = [g for g in _as_list(ci.get('keywords_groups')) if _truthy(g) and len(g)]
    return {
        'clause': _or_str(ci.get('clause')),
        'label': _or_str(ci.get('label')),
        'status': status,
        'language': lang,
        'status_label': status_label(status, lang),
        'reminder': _or_str(ci.get('reminder')),
        'requirement_text': clause_requirement_text(ci),
        'requirement_display': clause_requirement_text(ci) or REQUIREMENT_MISSING_TEXT,
        'keywords_any': uniq_text_list(ci.get('keywords_any')),
        'keywords_groups': [uniq_text_list(g) for g in groups],
        'keywords_tr': uniq_text_list(derive_turkish_keywords(ci)),
    }


def language_badge(report, note) -> dict:
    """languageBadgeHtml verisi."""
    lang = combined_language(report, note)
    return {'language': lang, 'label': language_label(lang), 'detail': 'otomatik algılandı'}


def panel_data(coverage, report, note) -> dict:
    """panelHtml verisi: {'empty': bool, 'language': {...}|None, 'items': [indicator_data...]}."""
    items = (coverage or {}).get('coverage_items') or []
    if not items:
        return {'empty': True, 'title': NO_DEFINITION_TITLE, 'text': NO_DEFINITION_TEXT, 'status': 'grey',
                'language': None, 'items': []}
    return {'empty': False, 'language': language_badge(report, note),
            'items': [indicator_data(ci, report, note) for ci in items]}


# ---------------------------------------------------------------------------
# How-To kilavuz kurali (guideRuleFor) ve beklentiler
# ---------------------------------------------------------------------------

def _guide_index(profile) -> dict:
    profile = normalize_profile(profile)
    if profile in _guide_index_cache:
        return _guide_index_cache[profile]
    k = knowledge_for(profile)
    lst = _jget(k, 'detailed_rules') if _truthy(k) else None
    mp = {}
    for rule in (lst if isinstance(lst, list) else []):
        if not _truthy(rule):
            continue
        clause = normalize_section_key(rule.get('clause'))
        if clause and not _truthy(_jget(mp, clause)):
            mp[clause] = rule
    _guide_index_cache[profile] = mp
    return mp


def guide_rule_for(profile, clause):
    """Cov.guideRuleFor: tam madde, sonra yalniz dogrudan ust zincir. Bulunamazsa None."""
    mp = _guide_index(profile)
    key = normalize_section_key(clause)
    hit = _jget(mp, key)
    if _truthy(hit):
        return hit
    parent = parent_key_of(key)
    while parent:
        hit = _jget(mp, parent)
        if _truthy(hit):
            return hit
        parent = parent_key_of(parent)
    return None


GUIDE_EMPTY_TEXT = ('Bu rapor kutusu için kılavuzda ayrı bir açıklama tanımlı değil. '
                    'Bölümü, standardın ilgili maddelerini objektif kanıtla karşılayacak şekilde manuel doldurun.')


def guide_expectations(profile, clause) -> dict:
    """guideExpectationsHtml verisi.

    rows: [(kind, text)] kind = 'expected' | 'evidence' ('Kanıt:' onekli) | 'empty'
    """
    rule = guide_rule_for(profile, clause)
    k = knowledge_for(profile)
    source = js_str(k.get('document_code')) if isinstance(k, dict) and _truthy(k.get('document_code')) \
        else 'BRCGS How to Complete'
    r = rule if isinstance(rule, dict) else {}
    matched = normalize_section_key(r.get('clause')) if rule else ''
    expected = [js_str(x) for x in _as_list(r.get('expected_content')) if js_trim(_or_str(x))]
    must = [js_str(x) for x in _as_list(r.get('must_include')) if js_trim(_or_str(x))]
    rows = [('expected', x) for x in expected] + [('evidence', x) for x in must]
    if not rows:
        rows.append(('empty', GUIDE_EMPTY_TEXT))
    avoid = r.get('should_not_include')
    avoid = ['' if x is None else js_str(x) for x in avoid] if isinstance(avoid, list) and avoid else []
    min_words = r.get('minimum_words') if _truthy(r.get('minimum_words')) else None
    return {
        'clause': clause,
        'source': source,
        'matched_clause': matched,
        'show_match': bool(matched and matched != normalize_section_key(clause)),
        'expected_content': expected,
        'must_include': must,
        'should_not_include': avoid,
        'minimum_words': min_words,
        'rows': rows,
        'rule': rule,
    }


# ---------------------------------------------------------------------------
# Kilavuz form alanlari (editor.js v5.2.1: resolveClause / formFor / assembleText)
# ---------------------------------------------------------------------------

LEGACY_KEY = '_legacy'
_GENERIC_PREFIX = 'Bu bölüm için kılavuzda belirtilen'


def _js_ci_canon(ch: str) -> str:
    """JS (u bayraksiz) /i karsilastirma kanonu."""
    up = ch.upper()
    if len(up) != 1 or (ord(ch) >= 128 and ord(up) < 128):
        return ch
    return up


def _is_generic_guide_line(line: str) -> bool:
    """GENERIC_GUIDE_RX = /^Bu bölüm için kılavuzda belirtilen/i."""
    if len(line) < len(_GENERIC_PREFIX):
        return False
    return all(_js_ci_canon(a) == _js_ci_canon(b) for a, b in zip(line, _GENERIC_PREFIX))


def _to_int32(n: int) -> int:
    n &= 0xFFFFFFFF
    return n - 0x100000000 if n & 0x80000000 else n


def _base36(n: int) -> str:
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    if n == 0:
        return '0'
    out = ''
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    return out


def guide_key(prefix: str, text) -> str:
    """guideKey: madde metninden kararli anahtar (djb2, UTF-16 kod birimleri, int32)."""
    h = 5381
    data = js_str(text).encode('utf-16-le')
    for i in range(0, len(data), 2):
        code = data[i] | (data[i + 1] << 8)
        h = _to_int32(_to_int32(h << 5) + h + code)
    return prefix + _base36(h & 0xFFFFFFFF)


def howto_fields_exact(profile, clause):
    """howtoFieldsExact: yalniz bu maddeye ait how-to kuralindan alanlar, ya da None."""
    rule = guide_rule_for(profile, clause)
    if not _truthy(rule) or js_trim(js_str(rule.get('clause'))) != js_str(clause):
        return None
    out = []
    for line in _as_list(rule.get('expected_content')):
        line = js_trim(_or_str(line))
        if line and not _is_generic_guide_line(line):
            out.append({'key': guide_key('g', line), 'label': line, 'type': 'textarea', 'rows': 2})
    for line in _as_list(rule.get('must_include')):
        line = js_trim(_or_str(line))
        if line:
            out.append({'key': guide_key('k', line), 'label': 'Kanıt: ' + line, 'type': 'textarea', 'rows': 2})
    return out or None


def resolve_clause(profile, clause):
    """resolveClause: {'fields', 'source'} ('curated' | 'guide' | 'fields') ya da None."""
    gf = guide_fields_data() or {}
    p = profile
    cur = _jget(gf.get('_curated') or {}, p) or {}
    old = _jget(gf, p) or {}
    c = _or_str(clause)
    hit = _jget(cur, c) if isinstance(cur, dict) else None
    if isinstance(hit, list) and hit:
        return {'fields': hit, 'source': 'curated'}
    h = howto_fields_exact(p, c)
    if h:
        return {'fields': h, 'source': 'guide'}
    hit = _jget(old, c) if isinstance(old, dict) else None
    if isinstance(hit, list) and hit:
        return {'fields': hit, 'source': 'fields'}
    return None


_form_cache: dict = {}


def form_for(profile, clause):
    """formFor: {'fields', 'source', 'rule', 'rule_exact'} ya da None (kilavuz icerigi yok)."""
    p = normalize_profile(profile)
    cache_key = p + '|' + js_str(clause)
    if cache_key in _form_cache:
        return _form_cache[cache_key]
    r = resolve_clause(p, clause)
    rule = guide_rule_for(p, clause)
    d = None
    if r:
        d = {'fields': r['fields'], 'source': r['source'], 'rule': rule,
             'rule_exact': bool(_truthy(rule) and js_trim(js_str(rule.get('clause'))) == js_str(clause))}
    _form_cache[cache_key] = d
    return d


def struct_of(row) -> dict:
    """structOf: kayitli yapisal yanitlar, yoksa eski metin tek '_legacy' alani olarak."""
    flags = row.get('flags')
    if _truthy(flags) and isinstance(flags, dict) and _truthy(flags.get('struct')):
        return flags['struct']
    s = {}
    if js_trim(_or_str(row.get('value'))):
        s[LEGACY_KEY] = js_str(row.get('value'))
    return s


_SELECT_TAIL = re.compile('[' + _JS_WS_CHARS + r'?:.]+\Z')


def assemble_text(profile, row, struct) -> str:
    """assembleText: rapor metni = once eski serbest metin, sonra doldurulan alanlar kilavuz sirasiyla."""
    if not isinstance(struct, dict):
        return ''
    d = form_for(profile, row.get('clause'))
    parts = []
    legacy = js_trim(_or_str(struct.get(LEGACY_KEY)))
    if legacy:
        parts.append(legacy)
    if d:
        for fd in d['fields']:
            val = js_trim(_or_str(struct.get(fd.get('key'))))
            if not val:
                continue
            if fd.get('type') == 'select':
                lab = fd.get('report_label') if _truthy(fd.get('report_label')) else fd.get('label')
                val = _SELECT_TAIL.sub('', _or_str(lab)) + ': ' + val
            parts.append(val)
    else:
        for k in js_keys(struct):
            if k == LEGACY_KEY:
                continue
            val = js_trim(_or_str(struct.get(k)))
            if val:
                parts.append(val)
    return '\n\n'.join(parts)
