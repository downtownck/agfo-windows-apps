# -*- coding: utf-8 -*-
"""agfo_brcgs.coverage testleri: Report Studio 5.2.1 assets/coverage.js ile birebir esitlik.

Iki katman:
  * StaticExpectations: node gerektirmez (CI). Degerler orijinal coverage.js'in bir calismasindan kopyalandi.
  * NodeParity: orijinal coverage.js'i node vm baglaminda (tarayicidaki window.agfoBrs ile) yukler; 5 profil x
    tum madde/bolum anahtarlari x uretilmis metinler icin sectionCoverage + itemStatus + summary + badgeText +
    dil + turkishKeywords + guideRuleFor sonuclarini Python portuyla karsilastirir. node veya eklenti kaynagi
    yoksa atlanir. PHP varsa standart verisi PHP json_decode/json_encode'dan gecirilir (wp_localize_script gibi).
Eklenti kaynagi: AGFO_BRS_PLUGIN_DIR ortam degiskeni (varsayilan: oturum karalama alani).
"""
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))

from agfo_brcgs import coverage as cov  # noqa: E402

NODE = shutil.which('node') or ('/opt/node22/bin/node' if os.path.exists('/opt/node22/bin/node') else None)
PHP = shutil.which('php')
PLUGIN_DIR = pathlib.Path(os.environ.get(
    'AGFO_BRS_PLUGIN_DIR',
    '/tmp/claude-0/-home-claude/362ddb9d-524b-53b3-91b7-2fdfa939e92b/scratchpad/rs/agfo-brcgs-report-studio'))
COVERAGE_JS = PLUGIN_DIR / 'assets' / 'coverage.js'
EDITOR_JS = PLUGIN_DIR / 'assets' / 'editor.js'
HAVE_PARITY = bool(NODE) and COVERAGE_JS.is_file()
PROFILES = ('fs', 'pm', 'cp', 'ab', 'sd')

HARNESS_JS = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const req = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const ctx = { console: console, setTimeout: setTimeout, clearTimeout: clearTimeout };
ctx.window = ctx;
ctx.document = { getElementById: function () { return null; }, addEventListener: function () {},
                 createElement: function () { return {}; } };
vm.createContext(ctx);
// Veri tarayicidaki gibi sayfa baglaminda JSON'dan olusur (wp_localize_script ciktisi).
ctx.__raw = fs.readFileSync(req.data_path, 'utf8');
vm.runInContext('window.agfoBrs = JSON.parse(__raw); delete window.__raw;', ctx);
vm.runInContext(fs.readFileSync(req.coverage_js, 'utf8'), ctx, { filename: 'coverage.js' });
const Cov = ctx.AgfoBrsCoverage;

function proj(ci) { return [String(ci.clause || ''), String(ci.label || '')]; }
const out = { cases: [], tr_keywords: {}, word_match: [], guide: [], guide_key: [] };

req.cases.forEach(function (c) {
    const cv = Cov.sectionCoverage(c.profile, c.clause, c.parent, c.title);
    const res = { cov: null, texts: [] };
    if (cv) {
        res.cov = { section: cv.section, title: cv.title, chapter: cv.chapter, guide_reminder: cv.guide_reminder,
                    original_text: cv.original_text, items: cv.coverage_items.map(proj) };
    }
    c.texts.forEach(function (t) {
        const items = cv ? cv.coverage_items : [];
        const sum = Cov.summary(cv, t[0], t[1]);
        res.texts.push({
            statuses: items.map(function (ci) { return Cov.itemStatus(ci, t[0], t[1]); }),
            summary: sum, badge: Cov.badgeText(sum),
            lang_report: Cov.language(t[0]), lang_combined: Cov.combinedLanguage(t[0], t[1])
        });
    });
    out.cases.push(res);
});

['pm', 'fs', 'cp', 'ab', 'sd'].forEach(function (p) {
    const st = Cov.standardFor(p), secs = st.sections || {}, list = [];
    Object.keys(secs).forEach(function (k) {
        (secs[k].coverage_items || []).forEach(function (ci) { list.push(Cov.turkishKeywords(ci)); });
    });
    (st.coverage_items || []).forEach(function (ci) { list.push(Cov.turkishKeywords(ci)); });
    out.tr_keywords[p] = list;
});

req.word_pairs.forEach(function (wp) { out.word_match.push(Cov.turkishWordMatch(wp[0], wp[1])); });

req.guide.forEach(function (g) {
    const r = Cov.guideRuleFor(g[0], g[1]);
    out.guide.push(r ? (typeof r === 'function' ? '<proto>' : [String(r.clause), r.minimum_words || null]) : null);
});

(function () {
    const src = fs.readFileSync(req.coverage_js, 'utf8');
    const m = src.match(/function trKeywordDictionary\(\) \{\s*return (\{[\s\S]*?\});\s*\}/);
    out.dictionary = Object.entries(vm.runInNewContext('(' + m[1] + ')'));
})();

if (req.editor_js) {
    const src = fs.readFileSync(req.editor_js, 'utf8');
    const m = src.match(/function guideKey\(prefix, text\) \{[\s\S]*?\n    \}/);
    const guideKey = vm.runInNewContext('(' + m[0] + ')');
    req.guide_key.forEach(function (s) { out.guide_key.push(guideKey('g', s)); });
}
fs.writeFileSync(process.argv[3], JSON.stringify(out));
"""

PHP_DUMP = r"""<?php
$d = $argv[1];
$m = array('pm' => 'pm_i7', 'fs' => 'fs_i9', 'cp' => 'cp_i4', 'ab' => 'ab_i3', 'sd' => 'sd_i4');
$o = array('standards' => array(), 'knowledge' => array());
foreach ($m as $s => $f) {
    $j = json_decode(file_get_contents("$d/standards/{$f}_standard.json"), true);
    $o['standards'][$s] = is_array($j) ? $j : array();
    $j = json_decode(file_get_contents("$d/knowledge/{$f}_howto.json"), true);
    $o['knowledge'][$s] = is_array($j) ? $j : array();
}
echo json_encode($o, JSON_HEX_TAG | JSON_UNESCAPED_SLASHES);
"""


# ---------------------------------------------------------------------------
# Metin uretici (deterministik)
# ---------------------------------------------------------------------------

_SOFT = {'k': 'ğ', 'p': 'b', 't': 'd', 'ç': 'c'}
_SUFFIXES = ['', 'ların', 'lerin', 'ı', 'i', 'si', 'sı', 'nin', 'ın', 'de', 'den', 'leri', 'miştir', 'mıştır']
_RANDOM_POOL = ('lorem ipsum weather football guitar sky blue river mountain coffee table window '
                'constructor __proto__ toString kahve deniz bulut masa kalem müzik şarkı yağmur ırmak').split()


def _inflect(word, rng):
    if word[-1:] in _SOFT and rng.random() < 0.5:
        return word[:-1] + _SOFT[word[-1]] + rng.choice(['ı', 'i', 'ü', 'u'])
    return word + rng.choice(_SUFFIXES)


def english_text(items, rng, groups=True):
    words = []
    for ci in items[:6]:
        kws = ci.get('keywords_any') or []
        if kws:
            words.append(rng.choice(kws))
        if groups:
            for g in ci.get('keywords_groups') or []:
                if g:
                    words.append(rng.choice(g))
    return 'The site has ' + ', '.join(words) + ' and the records were verified for the audit.'


def turkish_text(items, rng):
    phrases = []
    for ci in items[:6]:
        kws = cov.derive_turkish_keywords(ci)
        if kws:
            ws = rng.choice(kws).split()
            if ws:
                ws[-1] = _inflect(ws[-1], rng)
                phrases.append(' '.join(ws))
    return ('Tesiste ' + ', '.join(phrases) +
            ' ile ilgili prosedürlerin kaydı incelenmiş ve doğrulanmıştır.')


def random_text(rng):
    return ' '.join(rng.choice(_RANDOM_POOL) for _ in range(rng.randint(1, 12)))


def texts_for(items, rng, full=True):
    en, tr = english_text(items, rng), turkish_text(items, rng)
    if not full or len(items) > 40:  # sure icin cekirdek metinler (ayni ogeler baska vakada tam test edilir)
        return [['', ''], [en, ''], [tr, ''], ['Genel gözlem yapıldı.', en]]
    return [
        ['', ''],
        [en, ''],
        [english_text(items, rng, groups=False), ''],
        [tr, ''],
        [tr.upper(), ''],
        [en + ' ' + tr, ''],
        ['Genel gözlem yapıldı.', en],
        ['Short note.', tr],
        [random_text(rng), random_text(rng)],
    ]


def clause_keys(profile):
    st = cov.standard_for(profile)
    secs = st.get('sections') or {}
    keys = list(cov.js_keys(secs))
    for k in cov.js_keys(secs):
        for ci in secs[k].get('coverage_items') or []:
            keys.append(ci.get('clause'))
    for ci in st.get('coverage_items') or []:
        keys.append(ci.get('clause'))
    boxes = json.loads((cov.data_dir() / 'report-boxes' / ('%s_boxes.json' % profile)).read_text('utf-8'))
    keys += [u['key'] for u in boxes.get('units') or []]
    keys += ['', '0', '01.1', ' 2.1 ', '99', '99.1', '1.1.99', '4.x', 'constructor', 'toString', '13.1.1', '002']
    seen, out = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out, boxes


def build_cases():
    rng = random.Random(20261024)
    cases = []
    for p in PROFILES:
        keys, boxes = clause_keys(p)
        box_clause = {b['tag']: b['clause'] for b in boxes.get('boxes') or []}
        unit_box = {u['key']: box_clause.get(u['box'], '') for u in boxes.get('units') or []}
        secs = cov.standard_for(p).get('sections') or {}
        for i, k in enumerate(keys):
            # Bolum anahtari olmayan alt maddeler ust bolumun ogelerini tekrarlar: onlarda metinler kendi
            # maddesinin ogelerinden uretilir, kume kucuk tutulur; her 5.'si tam kumeyle calisir.
            full = k in secs or i % 5 == 0
            variants = [('', 'Başlık %s' % k)]
            if unit_box.get(k) and unit_box[k] != k:
                variants.append((unit_box[k], ''))
            if i % 7 == 0:
                variants.append((cov.parent_key_of(k) or '99', None))
            for parent, title in variants:
                c = cov.section_coverage(p, k, parent, title)
                items = c['coverage_items'] if c else []
                nk = cov.normalize_section_key(k)
                items = [ci for ci in items if ci.get('clause') == nk] + \
                    [ci for ci in items if ci.get('clause') != nk]  # once maddenin kendi anahtar kelimeleri
                cases.append({'profile': p, 'clause': k, 'parent': parent, 'title': title,
                              'texts': texts_for(items, rng, full)})
    # profil adlari ve normalize kurali
    for alias in ('ab_i3', 'agents_brokers', 'SD_I4', 'storage_distribution', 'xx', ''):
        cases.append({'profile': alias, 'clause': '1.1', 'parent': '', 'title': '', 'texts': [['', '']]})
    return cases


def word_pairs():
    rng = random.Random(7)
    base = ['kayıt', 'prosedür', 'ürün', 'tedarikçi', 'kontrol', 'denetim', 'kanıt', 'hedef', 'kitap', 'renk',
            'ağaç', 'sistem', 'izlenebilirlik', 'onay', 'temizlik', 've', 'ile', 'için', 'politika', 'gözden']
    pairs = []
    for kw in base:
        for _ in range(6):
            pairs.append([_inflect(kw, rng), kw])
        pairs.append([kw[:3], kw])
        pairs.append([kw[:5], kw])
        pairs.append([kw.upper(), kw])
        pairs.append(['', kw])
    return pairs


def guide_queries():
    out = []
    for p in PROFILES:
        keys, _ = clause_keys(p)
        out += [[p, k] for k in keys]
    return out


GUIDE_KEY_STRINGS = ['', 'a', 'Politika imzalı mı?', 'Gıda güvenliği kültürü düzeyi: nasıl belirlendi',
                     'emoji 🎉 test', 'x' * 500, 'İçerik ŞĞÜÖÇı']


# ---------------------------------------------------------------------------
# Testler
# ---------------------------------------------------------------------------

def _py_case(c):
    cv = cov.section_coverage(c['profile'], c['clause'], c['parent'], c['title'])
    res = {'cov': None, 'texts': []}
    if cv:
        res['cov'] = {'section': cv['section'], 'title': cv['title'], 'chapter': cv['chapter'],
                      'guide_reminder': cv['guide_reminder'], 'original_text': cv['original_text'],
                      'items': [[cov.js_str(ci.get('clause') or ''), cov.js_str(ci.get('label') or '')]
                                for ci in cv['coverage_items']]}
    for rep, note in c['texts']:
        items = cv['coverage_items'] if cv else []
        sm = cov.summary(cv, rep, note)
        res['texts'].append({'statuses': [cov.item_status(ci, rep, note) for ci in items],
                             'summary': sm, 'badge': cov.badge_text(sm),
                             'lang_report': cov.coverage_language(rep),
                             'lang_combined': cov.combined_language(rep, note)})
    return res


@unittest.skipUnless(HAVE_PARITY, 'node veya orijinal coverage.js bulunamadi')
class NodeParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix='agfo-brs-cov-'))
        data_path = cls.tmp / 'agfoBrs.json'
        cls.via_php = False
        if PHP:
            (cls.tmp / 'dump.php').write_text(PHP_DUMP, 'utf-8')
            r = subprocess.run([PHP, str(cls.tmp / 'dump.php'), str(cov.data_dir())], capture_output=True)
            if r.returncode == 0 and r.stdout:
                data_path.write_bytes(r.stdout)
                cls.via_php = True
        if not cls.via_php:
            data_path.write_text(json.dumps({'standards': cov.all_standards(), 'knowledge': cov.all_knowledge()},
                                            ensure_ascii=False), 'utf-8')
        cls.cases = build_cases()
        cls.pairs = word_pairs()
        cls.guide = guide_queries()
        req = {'data_path': str(data_path), 'coverage_js': str(COVERAGE_JS), 'cases': cls.cases,
               'word_pairs': cls.pairs, 'guide': cls.guide,
               'editor_js': str(EDITOR_JS) if EDITOR_JS.is_file() else '', 'guide_key': GUIDE_KEY_STRINGS}
        (cls.tmp / 'req.json').write_text(json.dumps(req, ensure_ascii=False), 'utf-8')
        (cls.tmp / 'harness.js').write_text(HARNESS_JS, 'utf-8')
        subprocess.run([NODE, str(cls.tmp / 'harness.js'), str(cls.tmp / 'req.json'), str(cls.tmp / 'out.json')],
                       check=True, timeout=600)
        cls.js = json.loads((cls.tmp / 'out.json').read_text('utf-8'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_section_coverage_and_status(self):
        n_status = 0
        mismatches = []
        for c, js in zip(self.cases, self.js['cases']):
            py = _py_case(c)
            n_status += sum(len(t['statuses']) for t in py['texts'])
            if py != js:
                mismatches.append((c['profile'], c['clause'], c['parent']))
        print('\n[coverage parity] sectionCoverage cases=%d, text cases=%d, itemStatus checks=%d, via_php=%s'
              % (len(self.cases), sum(len(c['texts']) for c in self.cases), n_status, self.via_php))
        self.assertEqual(mismatches[:20], [])
        self.assertEqual(len(self.cases), len(self.js['cases']))

    def test_status_variety(self):
        """Uretilen metinler dort durumu da gercekten uretmeli (testin anlamli oldugunun kaniti)."""
        seen = set()
        for js in self.js['cases']:
            for t in js['texts']:
                seen.update(t['statuses'])
                seen.add(t['lang_report'])
                seen.add(t['lang_combined'])
        for want in ('green', 'yellow', 'red', 'tr', 'en', 'mixed', 'unknown'):
            self.assertIn(want, seen)

    def test_turkish_keywords_all_items(self):
        n = 0
        for p in PROFILES:
            st = cov.standard_for(p)
            secs = st.get('sections') or {}
            py = []
            for k in cov.js_keys(secs):
                py += [cov.derive_turkish_keywords(ci) for ci in secs[k].get('coverage_items') or []]
            py += [cov.derive_turkish_keywords(ci) for ci in st.get('coverage_items') or []]
            self.assertEqual(py, self.js['tr_keywords'][p], p)
            n += len(py)
        print('\n[coverage parity] turkishKeywords items=%d' % n)

    def test_dictionary_verbatim(self):
        self.assertEqual([list(x) for x in cov.TR_KEYWORD_DICTIONARY.items()], self.js['dictionary'])

    def test_word_match(self):
        py = [cov.turkish_word_match(a, b) for a, b in self.pairs]
        self.assertEqual(py, self.js['word_match'])
        self.assertIn(True, py)
        self.assertIn(False, py)

    def test_guide_rule(self):
        py = []
        for p, k in self.guide:
            r = cov.guide_rule_for(p, k)
            if r is cov._PROTO:
                py.append('<proto>')
            else:
                py.append([cov.js_str(r['clause']), r.get('minimum_words') or None] if r else None)
        self.assertEqual(py, self.js['guide'])
        print('\n[coverage parity] guideRuleFor queries=%d' % len(py))

    def test_guide_key(self):
        if not self.js['guide_key']:
            self.skipTest('editor.js yok')
        self.assertEqual([cov.guide_key('g', s) for s in GUIDE_KEY_STRINGS], self.js['guide_key'])


class StaticExpectations(unittest.TestCase):
    """Orijinal coverage.js calismasindan kopyalanan degerler (node gerektirmez)."""

    def test_language(self):
        self.assertEqual(cov.coverage_language(''), 'unknown')
        self.assertEqual(cov.coverage_language('kayıt'), 'unknown')
        self.assertEqual(cov.coverage_language('Prosedürlerin kaydı doğrulanmıştır ve incelendi.'), 'tr')
        self.assertEqual(cov.coverage_language('The site has records and the procedure was reviewed.'), 'en')
        self.assertEqual(cov.coverage_language('The records and procedure were kayıt ve prosedür için kontrol'),
                         'tr')
        self.assertEqual(cov.coverage_language('The site and the records were checked; kayıt ve prosedür'), 'mixed')
        self.assertEqual(cov.combined_language('', 'The site has records'), 'en')
        self.assertEqual(cov.combined_language('Kayıtlar ve prosedür', 'The site has records'), 'mixed')

    def test_word_match(self):
        self.assertTrue(cov.turkish_word_match('prosedürlerin', 'prosedür'))
        self.assertTrue(cov.turkish_word_match('kaydı', 'kayıt') is False)  # orijinal: 'kayd' != 'kayıd'
        self.assertTrue(cov.turkish_word_match('kitabı', 'kitap'))
        self.assertTrue(cov.turkish_word_match('ağacı', 'ağaç'))
        self.assertTrue(cov.turkish_word_match('hedefi', 'hedef'))
        self.assertTrue(cov.turkish_word_match('izlen', 'izlenebilirlik'))
        self.assertFalse(cov.turkish_word_match('izle', 'izlenebilirlik'))

    def test_words_in_order(self):
        self.assertTrue(cov.turkish_words_in_order('Tedarikçi onayının kayıtları incelendi', 'tedarikçi onayı'))
        self.assertFalse(cov.turkish_words_in_order('onayı tedarikçi', 'tedarikçi onayı'))
        self.assertFalse(cov.turkish_words_in_order('constructor', 'constructor'))  # JS prototip tuhafligi

    def test_uniq_and_dictionary(self):
        self.assertEqual(cov.uniq_text_list([' A ', 'a', '', None, 'constructor', 'B']), ['A', 'B'])
        self.assertEqual(len(cov.TR_KEYWORD_DICTIONARY), 62)
        ci = {'label': 'Corrective action and root cause', 'keywords_any': ['corrective action', 'root cause']}
        self.assertEqual(cov.derive_turkish_keywords(ci),
                         ['düzeltici faaliyet', 'kök neden analizi', 'Corrective action and root cause',
                          'Corrective', 'action', 'root', 'cause'])

    def test_section_coverage_rules(self):
        c = cov.section_coverage('pm', '1.1')
        self.assertEqual(c['section'], '1.1')
        self.assertEqual([ci['clause'] for ci in c['coverage_items']],
                         ['1.1.%d' % i for i in range(1, 12)])
        # tam madde yoksa yalniz dogrudan ust
        c2 = cov.section_coverage('pm', '1.1.1', None, 'T')
        self.assertEqual(c2['section'], '1.1.1')
        self.assertEqual(c2['title'], 'T')
        self.assertEqual(len(c2['coverage_items']), 11)
        self.assertIsNone(cov.section_coverage('pm', '99'))
        self.assertIsNone(cov.section_coverage('pm', '99.1'))
        self.assertEqual(cov.section_coverage('pm', '01.1')['section'], '1.1')
        # bilinmeyen profil -> pm
        self.assertEqual(cov.section_coverage('zz', '1.1'), c)
        # 'constructor' JS'te prototip uzerinden "tam madde" sayilir
        self.assertEqual(cov.section_coverage('fs', 'constructor'),
                         {'section': 'constructor', 'title': 'Section constructor', 'chapter': '',
                          'guide_reminder': '', 'original_text': '', 'coverage_items': []})

    def test_status_and_badge(self):
        c = cov.section_coverage('pm', '1.1')
        item = c['coverage_items'][0]
        en = 'The documented policy was signed and communicated, with continual improvement.'
        self.assertEqual(cov.item_status(item, en, ''), 'green')
        self.assertEqual(cov.item_status(item, 'Kısa not.', en), 'yellow')
        self.assertEqual(cov.item_status(item, 'The policy was signed.', ''), 'red')
        self.assertEqual(cov.item_status(None, en, ''), 'grey')
        sm = cov.summary(c, en, 'Kısa not')
        self.assertEqual(sm, {'green': 1, 'yellow': 0, 'red': 10, 'grey': 0, 'total': 11})
        self.assertEqual(cov.badge_text(sm), '1/11 · 10 eksik')
        tr_item = cov.section_coverage('fs', '1.1')['coverage_items'][0]
        self.assertEqual(cov.item_status(
            tr_item, 'Üst yönetim taahhüdü kapsamında dokümante politikanın imzalanması doğrulanmıştır.', ''), 'green')
        self.assertEqual(cov.badge_text({'green': 2, 'yellow': 1, 'red': 3, 'grey': 0, 'total': 6}),
                         '2/6 +1 kanıt · 3 eksik')
        self.assertEqual(cov.badge_text({'total': 0}), 'manuel')
        self.assertEqual(cov.badge_text(None), 'manuel')

    def test_guide(self):
        g = cov.guide_expectations('fs', '1.1.1')
        self.assertEqual(g['matched_clause'], '1')
        self.assertTrue(g['show_match'])
        self.assertEqual(cov.guide_rule_for('sd', '4.3.2')['clause'], '4')
        self.assertTrue(g['source'])
        self.assertIsNone(cov.guide_rule_for('fs', '99.9'))
        self.assertEqual(cov.guide_expectations('fs', '99.9')['rows'], [('empty', cov.GUIDE_EMPTY_TEXT)])

    def test_guide_key(self):
        self.assertEqual(cov.guide_key('g', ''), 'g' + cov._base36(5381))

    def test_js_keys_and_roundtrip(self):
        self.assertEqual(cov.js_keys({'1.1': 0, '2': 0, '1': 0, 'a': 0, '10': 0}), ['1', '2', '10', '1.1', 'a'])
        self.assertEqual(cov.php_json_roundtrip({'a': {}, 'b': {'0': 1, '1': 2}, 'c': {'1': 1}}),
                         {'a': [], 'b': [1, 2], 'c': {'1': 1}})


if __name__ == '__main__':
    unittest.main()
