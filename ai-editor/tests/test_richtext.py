# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4 - bicimli metin duzenleyici (Tk): yazma, bicim, liste, tablo, resim ve geri al."""
import io
import pathlib
import sys
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import agfo_richdoc as R  # noqa: E402
from test_richdoc import png, sample_blocks, strip  # noqa: E402

try:
    import tkinter as tk
    import agfo_richtext as RT
    HAVE_TK = True
except Exception:  # pragma: no cover
    HAVE_TK = False
_root = None

COLORS = {'EDIT_BG': '#0e1b2e', 'FG': '#ecf3ff', 'ACCENT': '#49b3ef', 'SEL_BG': '#285475', 'MUTED': '#a5b6ce', 'BG': '#0a1425',
          'PANEL': '#12243b', 'PANEL2': '#192e48'}


class Key:
    def __init__(self, char, keysym=None, state=0):
        self.char, self.keysym, self.state = char, keysym or char, state


@unittest.skipUnless(HAVE_TK, 'Tk yok')
class RichTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _root
        _root = tk.Tk()
        _root.withdraw()

    @classmethod
    def tearDownClass(cls):
        _root.destroy()

    def setUp(self):
        self.t = RT.RichText(_root, COLORS)
        self.t.pack()

    def tearDown(self):
        self.t.destroy()

    def type(self, s):
        for ch in s:
            self.t._on_key(Key(ch))

    def test_load_get_roundtrip_and_page_mode(self):
        t = self.t
        blocks = sample_blocks()
        t.load_blocks(blocks)
        self.assertEqual(strip(t.get_blocks()), strip(blocks))
        self.assertFalse(t.undo.dirty())
        t.set_page_mode(True)
        self.assertEqual(t.cget('bg'), '#ffffff')
        self.assertEqual(strip(t.get_blocks()), strip(blocks))
        self.assertIn('1. Adım bir', t.get('1.0', 'end'))

    def test_typing_inherits_format_and_undo(self):
        t = self.t
        t.load_blocks([R.para([R.run('Normal '), R.run('kalın', b=True)])])
        t.mark_set('insert', '1.end')
        self.type('ca')
        self.assertEqual(t.get_blocks()[0]['runs'][-1], R.run('kalınca', b=True))
        self.assertTrue(t.undo.dirty())
        t.edit_undo()
        self.assertEqual(t.get('1.0', 'end-1c'), 'Normal kalın')
        self.assertFalse(t.undo.dirty())
        t.edit_redo()
        self.assertEqual(t.get('1.0', 'end-1c'), 'Normal kalınca')
        # secim yokken arac cubugundan italik: yazilacak metne uygulanir
        t.mark_set('insert', '1.0')
        t.toggle_char('i')
        self.type('X')
        self.assertEqual(t.get_blocks()[0]['runs'][0], R.run('X', i=True))

    def test_toggle_bold_on_selection_and_undo_restores_format(self):
        t = self.t
        t.load_blocks([R.para(text='Gıda güvenliği kültürü')])
        t.tag_add('sel', '1.0', '1.4')
        t.toggle_char('b')
        self.assertEqual(t.get_blocks()[0]['runs'][0], R.run('Gıda', b=True))
        self.assertIn('F_normal_10', t.tag_names('1.1'))                 # yazi tipi de kalin
        t.toggle_char('b')                                                # ikinci kez: kaldir
        self.assertEqual(t.get_blocks()[0]['runs'], [R.run('Gıda güvenliği kültürü')])
        t.edit_undo()
        self.assertEqual(t.get_blocks()[0]['runs'][0], R.run('Gıda', b=True))
        t.tag_add('sel', '1.0', '1.end')
        t.toggle_char('color', 'c00000')
        self.assertEqual(t.get_blocks()[0]['runs'][-1]['color'], 'C00000')
        # silme + geri al: bicim geri gelir (Tk'nin kendi geri alinda gelmez)
        t.tag_remove('sel', '1.0', 'end')
        t.delete('1.0', '1.end')
        t.edit_undo()
        self.assertEqual(t.get_blocks()[0]['runs'][0], R.run('Gıda', b=True, color='C00000'))

    def test_styles_lists_and_enter(self):
        t = self.t
        t.load_blocks([R.para(text='Başlık'), R.para(text='bir')])
        t.mark_set('insert', '1.2')
        t.set_style('h1')
        self.assertEqual(t.get_blocks()[0]['style'], 'h1')
        t.mark_set('insert', '1.end')
        t._on_return()
        self.type('metin')
        self.assertEqual(t.get_blocks()[1], R.para(text='metin'))           # basliktan sonra normal paragraf
        t.mark_set('insert', '3.0')
        t.toggle_list('number')
        t.mark_set('insert', '3.end')
        t._on_return()
        self.type('iki')
        t._on_return()
        self.type('üç')
        self.assertEqual(t.get('3.0', '5.end'), '1. bir\n2. iki\n3. üç')
        t.mark_set('insert', '4.end')
        t._on_tab(None)                                                     # Tab: alt duzey
        self.assertEqual(t.get_blocks()[3]['level'], 1)
        self.assertEqual(t.get('5.0', '5.end'), '2. üç')
        t._on_tab(None, back=True)
        self.assertEqual(t.get('5.0', '5.end'), '3. üç')
        t.mark_set('insert', '5.end')
        t._on_return()
        t._on_return()                                                      # bos ogede Enter: listeden cik
        self.assertIsNone(t.get_blocks()[-1]['list'])
        t.mark_set('insert', '4.3')
        t._on_backspace()                                                   # isaretten hemen sonra: listeden cikar
        self.assertIsNone(t.get_blocks()[3]['list'])
        self.assertEqual(t.get('5.0', '5.end'), '1. üç')
        for _ in range(12):
            t.edit_undo()
        self.assertEqual(t.get('1.0', 'end-1c'), 'Başlık\nbir')

    def test_merge_paragraphs_keeps_first_style(self):
        t = self.t
        t.load_blocks([R.para(text='Başlık', style='h2'), R.para(text=' devam')])
        t.mark_set('insert', '2.0')
        t._on_backspace()
        self.assertEqual(t.get_blocks(), [R.para(text='Başlık devam', style='h2')])
        t.edit_undo()
        self.assertEqual(len(t.get_blocks()), 2)

    def test_images_insert_resize_remove_undo(self):
        t = self.t
        t.load_blocks([R.para(text='Önce'), R.para(text='Sonra')])
        t.mark_set('insert', '1.2')
        name = t.insert_image('insert', R.image_block(png(80, 40)))
        self.assertEqual([b['t'] for b in t.get_blocks()], ['p', 'img', 'p'])
        t.resize_image(name, 300)
        self.assertEqual(round(t.get_blocks()[1]['w']), 300)
        t.edit_undo()
        self.assertEqual(round(t.get_blocks()[1]['w']), 60)
        self.assertTrue(t.remove_image(name))
        self.assertEqual([b['t'] for b in t.get_blocks()], ['p', 'p'])
        t.edit_undo()
        self.assertEqual([b['t'] for b in t.get_blocks()], ['p', 'img', 'p'])
        t.edit_undo()
        t.edit_undo()
        self.assertEqual([b['t'] for b in t.get_blocks()], ['p', 'p'])
        t.edit_redo()
        self.assertEqual([b['t'] for b in t.get_blocks()], ['p', 'img', 'p'])

    def test_tables(self):
        t = self.t
        t.load_blocks([R.para(text='Tablo:')])
        t.mark_set('insert', '1.end')
        t.insert_table(2, 3)
        b = t.get_blocks()
        self.assertEqual((b[1]['t'], len(b[1]['rows']), len(b[1]['rows'][0])), ('table', 2, 3))
        t.mark_set('insert', '2.0')
        self.type('A')
        t._on_tab(None)
        self.type('B')
        t._on_tab(None)
        t._on_tab(None)                                                     # sonraki satira gecer
        self.type('C')
        rows = [[R.runs_text(c) for c in r] for r in t.get_blocks()[1]['rows']]
        self.assertEqual(rows, [['A', 'B', ''], ['C', '', '']])
        t.table_add_row(3)
        t.table_add_col(2, '2.1')
        rows = [[R.runs_text(c) for c in r] for r in t.get_blocks()[1]['rows']]
        self.assertEqual(rows, [['A', '', 'B', ''], ['C', '', '', ''], ['', '', '', '']])
        t.table_delete_col(2, '2.0')
        t.table_delete_row(4)
        rows = [[R.runs_text(c) for c in r] for r in t.get_blocks()[1]['rows']]
        self.assertEqual(rows, [['', 'B', ''], ['', '', '']])
        t.table_delete(2)
        self.assertEqual([b['t'] for b in t.get_blocks()], ['p'])
        t.edit_undo()
        self.assertEqual([b['t'] for b in t.get_blocks()], ['p', 'table'])

    def test_markdown_replace_and_insert(self):
        t = self.t
        t.load_blocks([R.para(text='bir'), R.para(text='iki', style='h2'), R.para(text='üç')])
        md, imgs = t.markdown('2.0', '2.end')
        self.assertEqual(md, '## iki')
        t.replace_with_markdown('2.0', '2.end', 'İKİ **kalın**')
        self.assertEqual(t.get_blocks()[1], R.para([R.run('İKİ '), R.run('kalın', b=True)], 'h2'))
        t.replace_with_markdown('1.0', '3.end', '# Yeni\n\n- a\n- b\n\n| x | y |\n|---|---|\n| 1 | 2 |')
        self.assertEqual([b['t'] for b in t.get_blocks()], ['p', 'p', 'p', 'table'])
        self.assertEqual(t.get_blocks()[0]['style'], 'h1')
        t.edit_undo()
        self.assertEqual(t.get('1.0', 'end-1c'), 'bir\nİKİ kalın\nüç')
        t.insert_markdown_after('1.end', 'eklenen *paragraf*')
        self.assertEqual(t.get_blocks()[1], R.para([R.run('eklenen '), R.run('paragraf', i=True)]))
        # resim yer tutucusu AI yanitinda korunursa resim yerinde kalir
        t.load_blocks([R.para(text='a'), R.image_block(png()), R.para(text='b')])
        md, imgs = t.markdown()
        self.assertIn('![resim:1]', md)
        t.replace_with_markdown('1.0', 'end-1c', md.replace('a', 'A'), imgs)
        self.assertEqual([b['t'] for b in t.get_blocks()], ['p', 'img', 'p'])

    def test_rich_copy_paste(self):
        t = self.t
        t.load_blocks([R.para([R.run('kalın', b=True), R.run(' düz')]), R.para(text='')])
        t.tag_add('sel', '1.0', '1.end')
        t._on_copy()
        t.clipboard_clear()
        t.clipboard_append(t.get('1.0', '1.end'))
        t.tag_remove('sel', '1.0', 'end')
        t.mark_set('insert', '2.0')
        t._on_paste()
        self.assertEqual(t.get_blocks()[1]['runs'][0], R.run('kalın', b=True))
        t.clipboard_clear()
        t.clipboard_append('dış\nmetin')
        t.mark_set('insert', '2.end')
        t._on_paste()
        self.assertEqual(R.runs_text(t.get_blocks()[2]['runs']), 'metin')

    def test_plain_mode(self):
        t = RT.RichText(_root, COLORS, rich=False)
        t.insert('1.0', '# düz metin')
        self.assertEqual(t.get('1.0', 'end-1c'), '# düz metin')
        t.edit_undo()
        self.assertEqual(t.get('1.0', 'end-1c'), '')
        t.enable_rich()
        self.assertTrue(t.rich)
        t.destroy()


if __name__ == '__main__':
    unittest.main()
