# -*- coding: utf-8 -*-
"""AGFO Mihenk - uretilen .xlsx dosyasini bagimsiz bir okuyucuyla dogrular.

    python -I tests/test_xlsx.py <mihenk klasoru>

Kendi yazdigimiz kitabi yine kendi kodumuzla okumak bir sey kanitlamaz; bu
yuzden openpyxl ile aciliyor. openpyxl kurulu degilse test kendini atlar ve
bunu acikca yazar.
"""
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
os.environ['MIHENK_DATA_DIR'] = tempfile.mkdtemp()
# Bu dosyadaki beklentiler Turkce metinlere bakiyor; dil testin konusu
# degil. Ingilizce kapsami tests/test_i18n.py'de olculuyor.
os.environ['MIHENK_LANG'] = 'tr'
os.environ.setdefault('APPDATA', tempfile.mkdtemp())
os.environ.setdefault('LOCALAPPDATA', tempfile.mkdtemp())

try:
    import openpyxl
except ImportError:
    print('MIHENK XLSX ATLANDI: openpyxl kurulu degil (pip install openpyxl)')
    raise SystemExit(0)

import mihenk_db as db  # noqa: E402
import mihenk_export as export  # noqa: E402
import mihenk_seed as seed  # noqa: E402
import mihenk_xlsx as xlsx  # noqa: E402

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


def fresh():
    return db.connect(pathlib.Path(tempfile.mkdtemp()) / 'mihenk.sqlite3')


@test
def writer_round_trips_text_numbers_and_blanks():
    target = pathlib.Path(tempfile.mkdtemp()) / 'temel.xlsx'
    xlsx.write(target, [{
        'title': 'Deneme', 'headers': ['Metin', 'Sayı', 'Boş'],
        'rows': [['Makine & <kaçış>', 1.5, None],
                 ['Tırnak "x" ve \'y\'', -2, ''],
                 ['Türkçe: şğüöçıİ', 0, None]],
        'widths': [30, 10, 10]}])
    sheet = openpyxl.load_workbook(target)['Deneme']
    assert sheet['A1'].value == 'Metin'
    assert sheet['A2'].value == 'Makine & <kaçış>'
    assert sheet['B2'].value == 1.5
    assert sheet['C2'].value is None
    assert sheet['A3'].value == 'Tırnak "x" ve \'y\''
    assert sheet['B3'].value == -2
    assert sheet['A4'].value == 'Türkçe: şğüöçıİ'
    assert sheet.freeze_panes == 'A2'
    assert sheet.auto_filter.ref == 'A1:C4'


@test
def illegal_sheet_names_are_made_safe_and_unique():
    target = pathlib.Path(tempfile.mkdtemp()) / 'adlar.xlsx'
    xlsx.write(target, [
        {'title': 'a/b*c[d]:e', 'headers': ['X'], 'rows': [[1]]},
        {'title': 'a/b*c[d]:e', 'headers': ['X'], 'rows': [[2]]},
        {'title': 'Ç' * 60, 'headers': ['X'], 'rows': [[3]]},
    ])
    names = openpyxl.load_workbook(target).sheetnames
    assert len(names) == 3 and len(set(names)) == 3, names
    assert all(len(n) <= 31 for n in names), names
    assert not any(set(n) & set('\\/*?:[]') for n in names), names


@test
def control_characters_do_not_break_the_file():
    target = pathlib.Path(tempfile.mkdtemp()) / 'kontrol.xlsx'
    xlsx.write(target, [{'title': 'K', 'headers': ['A'],
                         'rows': [['once\x00sonra\x07bitti']]}])
    value = openpyxl.load_workbook(target)['K']['A2'].value
    assert '\x00' not in value and 'once' in value and 'bitti' in value


@test
def full_export_opens_and_carries_the_demo_data():
    conn = fresh()
    seed.seed(conn)
    target = pathlib.Path(tempfile.mkdtemp()) / 'kayitlar.xlsx'
    export.to_xlsx(conn, target)

    book = openpyxl.load_workbook(target)
    assert len(book.sheetnames) == len(export.ALL_TABLES), book.sheetnames

    assets = book['Varlıklar']
    codes = [row[0] for row in assets.iter_rows(min_row=2, max_col=1, values_only=True)]
    assert seed.PREFIX + 'THM-01' in codes, codes

    points = book['Ölçüm noktaları']
    rows = list(points.iter_rows(min_row=2, values_only=True))
    assert rows, 'olcum noktasi satiri bekleniyordu'
    assert any(r[3] == 'Pastörizasyon' and r[5] == 70.4 for r in rows), rows[:3]

    parts = book['Yedek parçalar']
    part_codes = [row[0] for row in parts.iter_rows(min_row=2, max_col=1, values_only=True)]
    assert seed.PREFIX + 'PRT-002' in part_codes, part_codes

    checklists = book['Kontrol listeleri']
    assert checklists.max_row > 1, 'kontrol listesi satiri bekleniyordu'


@test
def an_empty_database_still_produces_a_valid_workbook():
    conn = fresh()
    target = pathlib.Path(tempfile.mkdtemp()) / 'bos.xlsx'
    export.to_xlsx(conn, target)
    book = openpyxl.load_workbook(target)
    assert len(book.sheetnames) == len(export.ALL_TABLES)
    for name in book.sheetnames:
        assert book[name].max_row >= 1


print('AGFO MIHENK XLSX OK: %d tests' % len(PASSED))
