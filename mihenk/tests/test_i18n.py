# -*- coding: utf-8 -*-
"""AGFO Mihenk - dil katmani.

    python -I tests/test_i18n.py <mihenk klasoru>

Iki soruyu ayri ayri soruyor:

  1. Kaynak kodda ekranda gorunen her Turkce metnin Ingilizce karsiligi var mi?
     Metinler kaynaktan AST ile cikariliyor, elle tutulan bir listeden degil;
     boylece yeni bir metin eklendiginde test kendiliginden haberdar oluyor.

  2. Ingilizce secildiginde uygulama gercekten Ingilizce mi calisiyor? Tablolar,
     demo veri, Excel sayfa adlari ve HTML rapor bu dilde uretiliyor mu, ve
     veritabanina yazilan makine anahtarlari degismeden duruyor mu?

Ikinci soru onemli: ceviri sozlugu dolu olabilir ama metinler t() ile
sarilmamissa uygulama yine Turkce calisir. Sozluge bakan bir test bunu
goremez, ekrana bakan bir test gorur.
"""
import ast
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
os.environ['MIHENK_DATA_DIR'] = tempfile.mkdtemp()
os.environ.setdefault('APPDATA', tempfile.mkdtemp())
os.environ.setdefault('LOCALAPPDATA', tempfile.mkdtemp())
os.environ['MIHENK_LANG'] = 'en'

import mihenk_i18n as i18n  # noqa: E402

PASSED = []

# Veritabanina yazilan ya da makine anahtari olan degerler: asla cevrilmez.
MACHINE = {'adet', 'metre', 'kg', 'litre', 'paket', 'takım'}
TR_LETTERS = set('şğüöçıİŞĞÜÖÇ')
SOURCES = sorted(p.name for p in ROOT.glob('mihenk_*.py')
                 if p.name not in ('mihenk_i18n.py', 'mihenk_selftest.py'))


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


def looks_turkish(value: str) -> bool:
    """Ekranda gorunecek bir Turkce metin mi, yoksa teknik bir sabit mi."""
    if value in MACHINE or len(value) < 3 or '<style>' in value:
        return False
    if re.fullmatch(r'[\s%sdfgx0-9.\-+<>/|]*', value):
        return False
    return bool(set(value) & TR_LETTERS) or bool(
        re.search(r'\b(ve|bir|için|yok|var|bu|ile)\b', value))


def source_strings():
    """Kaynaktaki cevrilecek metinler; belge metinleri haric."""
    found = {}
    for name in SOURCES:
        tree = ast.parse((ROOT / name).read_text(encoding='utf-8'))
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if ast.get_docstring(node, clean=False) is not None and node.body:
                    docs.add(id(node.body[0].value))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docs and looks_turkish(node.value)):
                found.setdefault(node.value, name)
    return found


@test
def every_visible_turkish_string_has_an_english_counterpart():
    found = source_strings()
    gaps = [(s, found[s]) for s in i18n.missing(found)]
    assert not gaps, 'cevirisi olmayan %d metin: %s' % (
        len(gaps), ['%s: %r' % (f, s[:60]) for s, f in gaps[:8]])


@test
def the_dictionary_carries_no_dead_entries():
    """Sozlukte kaynakta artik bulunmayan metin kalmasin: cop birikmesin.

    Kaynaktaki butun metin sabitlerine bakiyor, yalnizca cevrilecek olanlara
    degil: 'Ad' ya da 'Kod' gibi kisa etiketler cikarma olcutunun altinda
    kaliyor ama kodda gercekten kullaniliyor. Duz metin aramasi da ise
    yaramaz, cunku uzun metinler kaynakta satirlara bolunmus durumda.
    """
    live = set()
    for name in SOURCES:
        for node in ast.walk(ast.parse((ROOT / name).read_text(encoding='utf-8'))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                live.add(node.value)
    dead = [k for k in i18n.EN if k not in live]
    assert not dead, 'kaynakta olmayan %d ceviri: %s' % (len(dead), [d[:50] for d in dead[:8]])


@test
def no_english_value_is_left_as_the_turkish_source():
    # Ozel adlar cevrilmez; listeye girmeleri bilincli bir karar olsun diye
    # burada tek tek yaziliyor.
    proper_nouns = {'Klüber', 'SKF Türkiye'}
    same = [k for k, val in i18n.EN.items()
            if k == val and set(k) & TR_LETTERS and k not in proper_nouns]
    assert not same, 'cevrilmemis kalmis: %s' % same[:8]


@test
def the_tables_built_at_import_time_come_out_in_english():
    import mihenk_app as app
    import mihenk_export as export
    import mihenk_parts as parts
    import mihenk_repo as repo
    import mihenk_states as states
    import mihenk_widgets as widgets

    assert [n[1] for n in app.NAV][:3] == ['Dashboard', 'Assets', 'Plans'], app.NAV
    assert states.LABELS['asset']['quarantined'] == 'Quarantined'
    assert repo.AssetTypes.TYPES['measuring_device'] == 'Measuring device'
    assert repo.ScheduleRepo.PLAN_TYPES['calibration'] == 'Calibration'
    assert parts.REASONS['consume'] == 'Used on a work order'
    assert widgets.MONTHS[0] == 'January' and widgets.WEEKDAYS[0] == 'Mo'
    assert [title for _, title, _ in export.ALL_TABLES][:2] == ['Assets', 'Plans']


@test
def the_machine_keys_behind_those_labels_do_not_move():
    """Etiketler cevrilir, veritabanina yazilan anahtar cevrilmez."""
    import mihenk_parts as parts
    import mihenk_repo as repo
    import mihenk_states as states

    assert set(states.MAP['asset']) == {'active', 'out_of_service', 'quarantined', 'retired'}
    assert set(repo.AssetTypes.COUNTER_UNITS) == {'', 'hour', 'cycle', 'km'}
    assert set(repo.ScheduleRepo.UNITS) == {'day', 'week', 'month', 'year'}
    assert set(parts.REASONS) == {'consume', 'receive', 'return', 'count', 'scrap'}


@test
def demo_data_installs_in_english_and_keeps_the_quarantine_rule():
    import mihenk_db as db
    import mihenk_repo as repo
    import mihenk_seed as seed

    conn = db.connect(pathlib.Path(tempfile.mkdtemp()) / 'en.sqlite3')
    report = seed.seed(conn)
    assert report['ok'], report
    assert any('assets' in line for line in report['lines']), report['lines']

    rows = repo.AssetRepo.query(conn)
    names = [r['name'] for r in rows]
    assert 'Filling Line 1' in names, names[:6]
    assert not any(set(n) & TR_LETTERS for n in names), [n for n in names if set(n) & TR_LETTERS]

    # Dil degisti diye asil kural kaybolmasin.
    quarantined = [r for r in rows if r['status'] == 'quarantined']
    assert len(quarantined) == 1, [r['status'] for r in rows]
    assert repo.ImpactRepo.open_count_for_asset(conn, quarantined[0]['id']) == 1


@test
def the_printable_report_declares_english_and_reads_in_english():
    import mihenk_db as db
    import mihenk_export as export
    import mihenk_seed as seed

    conn = db.connect(pathlib.Path(tempfile.mkdtemp()) / 'rep.sqlite3')
    seed.seed(conn)
    target = pathlib.Path(tempfile.mkdtemp()) / 'report.html'
    export.to_html(conn, target)
    text = target.read_text(encoding='utf-8')
    assert '<html lang="en">' in text, text[:200]
    assert 'Ctrl+P to print' in text
    assert 'Mihenk audit report' in text
    body = text.split('</style>', 1)[1]
    proper_nouns = {'Klüber', 'Türkiye'}          # tedarikci adlari cevrilmez
    leftover = sorted({w for w in re.findall(r'\w+', body)
                       if set(w) & TR_LETTERS and w not in proper_nouns})
    assert not leftover, 'Ingilizce raporda Turkce kelime kaldi: %s' % leftover[:10]


@test
def turkish_still_works_in_a_separate_process():
    """Ayni kod Turkce calistirildiginda Turkce kalmali."""
    script = ('import sys; sys.path.insert(0, %r)\n'
              'import mihenk_app as app, mihenk_states as st\n'
              'print(app.NAV[1][1], st.LABELS["asset"]["quarantined"], sep="|")\n' % str(ROOT))
    env = dict(os.environ, MIHENK_LANG='tr', MIHENK_DATA_DIR=tempfile.mkdtemp())
    # -X utf8: Windows'ta alt surecin stdout'u yoksa cp1252'ye duser ve
    # 'Varlıklar' yazilamaz. -I izole kip PYTHON* degiskenlerini yok saydigi
    # icin bunu ortamdan degil bayrakla vermek gerekiyor.
    out = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c', script],
                         capture_output=True, text=True, env=env, encoding='utf-8')
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == 'Varlıklar|Karantinada', out.stdout


@test
def an_unknown_language_code_falls_back_instead_of_breaking():
    assert i18n.set_language('de') == 'tr'
    assert i18n.t('Varlıklar') == 'Varlıklar'
    assert i18n.months()[0] == 'Ocak'
    assert i18n.set_language('en') == 'en'
    assert i18n.t('Varlıklar') == 'Assets'


@test
def the_disclaimer_file_matches_the_text_the_application_shows():
    """DISCLAIMER.txt uretilmis bir dosya: kaynaktan kaymis olmasin."""
    sys.path.insert(0, str(ROOT / 'packaging'))
    import make_disclaimer

    target = ROOT / 'DISCLAIMER.txt'
    assert target.exists(), 'DISCLAIMER.txt yok; python packaging/make_disclaimer.py'
    assert target.read_text(encoding='utf-8') == make_disclaimer.build(), (
        'DISCLAIMER.txt eskimis; python packaging/make_disclaimer.py ile yeniden uretin')


@test
def the_disclaimer_is_offered_once_and_remembered_by_version():
    import mihenk_legal as legal
    import mihenk_store as store

    os.environ['MIHENK_DATA_DIR'] = tempfile.mkdtemp()
    store.save_settings({'disclaimer_accepted': 0})
    assert not legal.accepted(), 'temiz kurulumda onay istenmeliydi'
    legal.accept()
    assert legal.accepted(), 'onay hatirlanmadi'

    # Metin esasli degisirse onay yeniden sorulmali.
    store.save_settings({'disclaimer_accepted': legal.VERSION - 1})
    assert not legal.accepted(), 'eski surumun onayi yeni metni kapsamamali'

    # Bozuk bir deger uygulamayi dusurmemeli, onay istemeli.
    store.save_settings({'disclaimer_accepted': 'evet'})
    assert not legal.accepted()


@test
def the_disclaimer_says_the_things_it_has_to_say():
    """Metnin icerigi kazara daralmasin."""
    import mihenk_legal as legal

    body = legal.text()
    for needle in ('as is', 'no liability', 'impartiality', 'quality management system'):
        assert needle in body, 'Ingilizce metinde eksik: %r' % needle
    assert legal.VERSION >= 1


@test
def an_untranslated_string_passes_through_rather_than_failing():
    i18n.set_language('en')
    assert i18n.t('bu metnin karşılığı yok') == 'bu metnin karşılığı yok'
    assert i18n.tf('%d kayıt bulunamadı', 3) == '3 kayıt bulunamadı'


print('AGFO MIHENK I18N OK: %d tests (%d ceviri, %d kaynak dosya)'
      % (len(PASSED), len(i18n.EN), len(SOURCES)))
