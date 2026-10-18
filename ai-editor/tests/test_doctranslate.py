# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4 - bicim koruyan belge cevirisi."""
import pathlib
import re
import sys
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import agfo_doctranslate as T  # noqa: E402
import agfo_richdoc as R  # noqa: E402
from test_richdoc import sample_blocks  # noqa: E402

DICT = {'Denetim Raporu': 'Audit Report', 'Kapsam': 'Scope', 'Birinci madde': 'First item', 'Alt madde': 'Sub item',
        'Adım bir': 'Step one', 'Adım iki': 'Step two', 'Madde': 'Clause', 'Durum': 'Status', 'Sonuç': 'Conclusion',
        '4.11.2': '4.11.2', 'Uygun değil | kayıt yok': 'Nonconforming | no record'}


def fake_translate(text, instruction):
    """Isaretleri koruyan sahte ceviri: sozlukte olanlari cevirir, digerlerini EN: onekiyle doner."""
    out = []
    for m in re.finditer(r'⟦(\d+)⟧ (.*?)(?=\n\n⟦|\Z)', text, re.S):
        body = m.group(2).strip()
        plain = body.replace('**', '')
        if plain in DICT:
            body = body.replace(plain, DICT[plain])
        else:
            body = body.replace('Örnek Gıda', 'Sample Foods').replace('Firma', 'Company').replace('önemli', 'important')
        out.append('⟦%s⟧ %s' % (m.group(1), body))
    return '\n\n'.join(out)


class TranslateTests(unittest.TestCase):
    def test_structure_and_inline_format_preserved(self):
        blocks = sample_blocks()
        calls = []

        def call(text, instr):
            calls.append((text, instr))
            return fake_translate(text, instr)
        new, stats = T.translate_blocks(blocks, call, 'English')
        self.assertEqual(stats['missing'], 0)
        self.assertEqual([b['t'] for b in new], [b['t'] for b in blocks])
        self.assertEqual(new[0], R.para(text='Audit Report', style='h1'))
        self.assertEqual(new[1]['runs'][1], R.run('Sample Foods', b=True))
        self.assertTrue(new[1]['runs'][3]['i'] and new[1]['runs'][3]['u'])
        self.assertEqual((new[4]['list'], new[4]['level']), ('bullet', 1))
        self.assertIs(new[7]['data'], blocks[7]['data'])                                      # resim dokunulmadan kalir
        self.assertEqual(new[7]['align'], 'center')
        self.assertEqual(R.runs_text(new[8]['rows'][1][1]), 'Nonconforming | no record')
        self.assertEqual((new[9]['style'], new[9]['align'], new[9]['pb']), ('quote', 'right', True))
        self.assertEqual(R.runs_text(blocks[0]['runs']), 'Denetim Raporu')                     # ozgun degismez
        self.assertIn('English', calls[0][1])
        self.assertNotIn('resim', calls[0][0])                                                # resim AI'a gitmez

    def test_batches_and_missing_segments_retry(self):
        blocks = [R.para(text='Paragraf %d ' % n + 'x' * 300) for n in range(30)]
        state = {'n': 0}

        def call(text, instr):
            state['n'] += 1
            ids = re.findall(r'⟦(\d+)⟧', text)
            if len(ids) > 1:                         # toplu istekte ilk parcayi "unut"
                ids = ids[1:]
            return '\n\n'.join('[[%s]] EN %s' % (i, i) for i in ids)
        new, stats = T.translate_blocks(blocks, call, 'English', limit=2000)
        self.assertGreater(stats['batches'], 3)
        self.assertEqual(stats['missing'], 0)
        self.assertEqual(R.runs_text(new[0]['runs']), 'EN 0')
        self.assertEqual(R.runs_text(new[29]['runs']), 'EN 29')
        self.assertEqual(state['n'], stats['batches'] * 2)                                    # her grupta bir tekrar

    def test_cancel_and_progress(self):
        blocks = [R.para(text='p%d ' % n + 'y' * 500) for n in range(10)]
        seen = []
        with self.assertRaises(InterruptedError):
            T.translate_blocks(blocks, fake_translate, 'English', progress=lambda i, n: seen.append((i, n)),
                               cancelled=lambda: len(seen) >= 2, limit=1000)
        self.assertEqual(seen[0][0], 0)

    def test_parse_variants(self):
        got = T.parse('⟦1⟧ bir\n\n【2】 iki\n[[3]] üç\n⟦9⟧ fazla', {1, 2, 3})
        self.assertEqual(got, {1: 'bir', 2: 'iki', 3: 'üç'})

    def test_pdf_reflow(self):
        text = ('4.11.2 Cleaning procedures shall be\nvalidated and records\nkept.\nThe site shall review\nannually.\n'
                '• first bullet\n• second\n\nNew para-\ngraph here')
        paras = T.reflow(text)
        self.assertEqual(paras[0], '4.11.2 Cleaning procedures shall be validated and records kept.')
        self.assertEqual(paras[1], 'The site shall review annually.')
        self.assertEqual(paras[2:4], ['• first bullet', '• second'])
        self.assertEqual(paras[4], 'New paragraph here')
        blocks = T.pdf_units_to_blocks([{'loc': 's. 1', 'text': text}], 'BRCGS')
        self.assertEqual(blocks[0]['style'], 'h1')
        self.assertEqual(blocks[1]['style'], 'h3')
        self.assertEqual(blocks[4]['list'], 'bullet')


if __name__ == '__main__':
    unittest.main()
