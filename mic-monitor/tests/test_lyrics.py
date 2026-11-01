"""AGFO Mic Monitor - sarki sozu ve zamanlama testleri (standart kutuphane).

    python -I tests/test_lyrics.py <mic-monitor klasoru>
"""
import pathlib
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
import mic_lyrics as ly  # noqa: E402

PASSED = []
TMP = pathlib.Path(tempfile.mkdtemp(prefix='micmon-ly-'))


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


SONG = '﻿\n\nUzun ince bir yoldayım\nGidiyorum gündüz gece\n\n\n\nBilmiyorum ne haldeyim\nGidiyorum gündüz gece\n\n'


@test
def text_cleanup_keeps_turkish_and_stanzas():
    lines = ly.parse_text(SONG)
    assert lines == ['Uzun ince bir yoldayım', 'Gidiyorum gündüz gece', '',
                     'Bilmiyorum ne haldeyim', 'Gidiyorum gündüz gece']


@test
def lrc_parse_offset_and_multi_stamps():
    lrc = '[ti:Deneme]\n[offset:+500]\n[00:12.50]Bir\n[00:05.00][00:30.25]Nakarat\n[01:02]İki\nbozuk satır\n'
    lines, times = ly.parse_lrc(lrc)
    assert lines == ['Nakarat', 'Bir', 'Nakarat', 'İki']
    assert times == [4.5, 12.0, 29.75, 61.5]


@test
def lrc_roundtrip():
    lines = ['Bir', '', 'İki']
    txt = ly.to_lrc(lines, [1.0, 2.345, 65.5], title='Şarkı')
    assert '[01:05.50]İki' in txt and '[ti:Şarkı]' in txt
    l2, t2 = ly.parse_lrc(txt)
    assert l2 == lines and [round(x, 2) for x in t2] == [1.0, 2.35, 65.5]   # [00:02.35] (yuvarlama)


@test
def load_formats_and_encodings():
    (TMP / 'a.txt').write_text(SONG, encoding='utf-8')
    (TMP / 'b.txt').write_bytes('Gönül dağı\nyağmur yağmur\n'.encode('cp1254'))
    (TMP / 'c.lrc').write_text('[00:01.00]Gönül\n[00:03.00]Dağı\n', encoding='utf-8')
    a, b, c = ly.load(TMP / 'a.txt'), ly.load(TMP / 'b.txt'), ly.load(TMP / 'c.lrc')
    assert len(a) == 5 and not a.timed
    assert b.lines == ['Gönül dağı', 'yağmur yağmur']                 # eski Windows Turkce kodlama
    assert c.timed and c.times == [1.0, 3.0]
    doc = TMP / 'd.docx'
    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="%s"><w:body>'
           '<w:p><w:r><w:t>Gönül </w:t></w:r><w:r><w:t>dağı</w:t></w:r></w:p>'
           '<w:p/><w:p><w:r><w:t>Yağmur</w:t><w:br/><w:t>yağmur</w:t></w:r></w:p></w:body></w:document>') % W
    with zipfile.ZipFile(str(doc), 'w') as z:
        z.writestr('word/document.xml', xml)
    d = ly.load(doc)
    assert d.lines == ['Gönül dağı', '', 'Yağmur', 'yağmur'], d.lines
    assert ly.from_text('[00:02]A\n[00:04]B').timed and not ly.from_text('A\nB').timed


@test
def distribute_and_index():
    lines = ['a', 'b', '', 'c', 'd']
    t = ly.distribute(lines, 90, start=0)
    assert t[0] == 0 and len(t) == 5 and t[2] - t[1] == 20 and t[3] - t[2] == 10   # bos satir yarim agirlik
    assert ly.current_index(t, -1) == -1 and ly.current_index(t, 0) == 0
    assert ly.current_index(t, 25) == 1 and ly.current_index(t, 999) == 4
    L = ly.Lyrics(lines).ensure_times(90)
    assert L.index_at(41) == 2 and abs(L.progress_at(10) - 0.5) < 1e-9
    assert abs(L.progress_at(85, end=90) - (4 + 15 / 20.0)) < 1e-9


@test
def tapper_builds_times_and_skips_blank_lines():
    tp = ly.Tapper(['a', 'b', '', 'c'])
    assert tp.next_index == 0
    tp.tap(1.0); tp.tap(3.0)
    assert tp.next_index == 3                                      # bos satir atlanir
    tp.tap(2.0)                                                    # geri gidemez
    assert tp.done and tp.times() == [1.0, 3.0, 3.0, 3.0]
    tp.undo(); tp.tap(9.0)
    assert tp.times() == [1.0, 3.0, 6.0, 9.0]
    p = ly.save_lrc(tp.lines, tp.times(), TMP / 'x.lrc', title='t')
    L = ly.load(p)
    assert L.timed and L.lines == ['a', 'b', '', 'c'] and L.times == [1.0, 3.0, 6.0, 9.0]


@test
def companion_files():
    bg = TMP / 'Longa.mp3'; bg.write_bytes(b'x')
    assert ly.find_for_backing(bg) is None
    (TMP / 'Longa.txt').write_text('a', encoding='utf-8')
    assert ly.find_for_backing(bg).name == 'Longa.txt'
    (TMP / 'Longa.lrc').write_text('[00:01]a', encoding='utf-8')
    assert ly.find_for_backing(bg).name == 'Longa.lrc'               # LRC once
    assert ly.lrc_path_for(ly.load(TMP / 'Longa.txt')).name == 'Longa.lrc'
    assert ly.lrc_path_for(ly.from_text('a'), bg).name == 'Longa.lrc'


print('OK - %d test gecti: %s' % (len(PASSED), ', '.join(PASSED)))
