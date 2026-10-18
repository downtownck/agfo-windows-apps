# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4 - bicimli belge modeli: DOCX / Markdown / HTML donusumleri."""
import io
import os
import pathlib
import sys
import tempfile
import unittest
import zipfile

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))

import agfo_richdoc as R  # noqa: E402

TMP = tempfile.mkdtemp(prefix='agfo-richdoc-')


def png(w=40, h=20, color=(200, 30, 30)):
    from PIL import Image
    b = io.BytesIO()
    Image.new('RGB', (w, h), color).save(b, 'PNG')
    return b.getvalue()


def sample_blocks():
    return [R.para(text='Denetim Raporu', style='h1'),
            R.para([R.run('Firma '), R.run('Örnek Gıda', b=True), R.run(' — '), R.run('önemli', i=True, u=True),
                    R.run(' kırmızı', color='C00000')]),
            R.para(text='Kapsam', style='h2'),
            R.para(text='Birinci madde', lst='bullet'), R.para(text='Alt madde', lst='bullet', level=1),
            R.para(text='Adım bir', lst='number'), R.para(text='Adım iki', lst='number'),
            R.image_block(png(), 120, 60, align='center'),
            {'t': 'table', 'rows': [[[R.run('Madde', b=True)], [R.run('Durum', b=True)]],
                                    [[R.run('4.11.2')], [R.run('Uygun değil | kayıt yok')]]]},
            R.para(text='Sonuç', style='quote', align='right', pb=True)]


def strip(blocks):
    return [{k: (len(v) if k == 'data' else v) for k, v in b.items()} for b in blocks]


WORD_DOC = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"><w:body>
<w:p><w:pPr><w:pStyle w:val="Balk1"/></w:pPr><w:r><w:t>Giriş</w:t></w:r></w:p>
<w:p><w:r><w:t xml:space="preserve">Metin </w:t></w:r><w:r><w:rPr><w:rStyle w:val="Strong"/></w:rPr><w:t>güçlü</w:t></w:r>
<w:hyperlink r:id="rId9"><w:r><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr><w:t>bağlantı</w:t></w:r></w:hyperlink>
<w:ins w:id="1"><w:r><w:t xml:space="preserve"> eklendi</w:t></w:r></w:ins><w:del w:id="2"><w:r><w:delText>silindi</w:delText></w:r></w:del>
<w:r><w:rPr><w:b w:val="0"/><w:i/></w:rPr><w:t xml:space="preserve"> eğik</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="5"/></w:numPr></w:pPr><w:r><w:t>madde</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="6"/></w:numPr></w:pPr><w:r><w:t>sıra</w:t></w:r></w:p>
<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing><wp:inline><wp:extent cx="1270000" cy="635000"/><wp:docPr id="1" name="r"/>
<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:blipFill><a:blip r:embed="rId7"/></pic:blipFill></pic:pic></a:graphicData></a:graphic>
</wp:inline></w:drawing></w:r></w:p>
<w:p><w:r><w:t>önce</w:t></w:r><w:r><w:br w:type="page"/></w:r><w:r><w:t>sonra</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A1</w:t></w:r></w:p><w:p><w:r><w:t>devam</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>B1</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>birleşik</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
<w:sdt><w:sdtContent><w:p><w:r><w:t>içerik denetimi</w:t></w:r></w:p></w:sdtContent></w:sdt>
<w:sectPr/></w:body></w:document>'''

WORD_STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:styleId="Balk1"><w:name w:val="heading 1"/></w:style>
<w:style w:type="character" w:styleId="Strong"><w:name w:val="Strong"/><w:rPr><w:b/></w:rPr></w:style>
</w:styles>'''

WORD_NUMBERING = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>
<w:abstractNum w:abstractNumId="2"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum>
<w:num w:numId="5"><w:abstractNumId w:val="1"/></w:num><w:num w:numId="6"><w:abstractNumId w:val="2"/></w:num>
</w:numbering>'''

WORD_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://agfo.app" TargetMode="External"/>
</Relationships>'''


def word_like_docx(path):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('word/document.xml', WORD_DOC)
        z.writestr('word/styles.xml', WORD_STYLES)
        z.writestr('word/numbering.xml', WORD_NUMBERING)
        z.writestr('word/_rels/document.xml.rels', WORD_RELS)
        z.writestr('word/media/image1.png', png(100, 50))


class DocxTests(unittest.TestCase):
    def test_roundtrip_keeps_everything(self):
        blocks = sample_blocks()
        p = os.path.join(TMP, 'rt.docx')
        pathlib.Path(p).write_bytes(R.docx_bytes(blocks))
        back = R.read_docx_blocks(p)
        self.assertEqual(strip(back), strip(blocks))
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            self.assertIn('word/media/image1.png', names)
            self.assertIn('word/numbering.xml', names)
            doc = z.read('word/document.xml').decode('utf-8')
            self.assertIn('<w:pageBreakBefore/>', doc)
            self.assertIn('Default Extension="png"', z.read('[Content_Types].xml').decode('utf-8'))

    def test_word_features(self):
        p = os.path.join(TMP, 'word.docx')
        word_like_docx(p)
        b = R.read_docx_blocks(p)
        self.assertEqual((b[0]['style'], R.runs_text(b[0]['runs'])), ('h1', 'Giriş'))
        runs = b[1]['runs']
        self.assertEqual(R.runs_text(runs), 'Metin güçlübağlantı eklendi eğik')          # silinen izli metin yok
        self.assertTrue(next(r for r in runs if r['text'] == 'güçlü')['b'])                # karakter stili (Strong)
        link = next(r for r in runs if r['text'] == 'bağlantı')
        self.assertEqual((link['u'], link['color']), (True, '0563C1'))
        self.assertTrue(next(r for r in runs if 'eğik' in r['text'])['i'])
        self.assertEqual((b[2]['list'], b[3]['list']), ('bullet', 'number'))
        self.assertEqual((b[4]['t'], b[4]['align'], round(b[4]['w'])), ('img', 'center', 100))
        self.assertEqual(R.runs_text(b[5]['runs']), 'önce')
        self.assertEqual((R.runs_text(b[6]['runs']), b[6]['pb']), ('sonra', True))
        self.assertEqual(b[7]['t'], 'table')
        self.assertEqual(R.runs_text(b[7]['rows'][0][0]), 'A1 devam')
        self.assertEqual(R.runs_text(b[7]['rows'][1][0]), 'birleşik')
        self.assertEqual(len(b[7]['rows'][1]), 2)                                         # eksik hucre tamamlanir
        self.assertEqual(R.runs_text(b[8]['runs']), 'içerik denetimi')

    def test_bilingual_and_plain(self):
        data = R.bilingual_docx_bytes([([R.run('Merhaba')], [R.run('Hello')])], 'Türkçe', 'English')
        p = os.path.join(TMP, 'bi.docx')
        pathlib.Path(p).write_bytes(data)
        t = R.read_docx_blocks(p)[0]
        self.assertEqual([[R.runs_text(c) for c in row] for row in t['rows']], [['Türkçe', 'English'], ['Merhaba', 'Hello']])
        txt = R.plain_text(sample_blocks())
        self.assertIn('• Birinci madde\n  • Alt madde\n1. Adım bir\n2. Adım iki', txt)

    def test_image_sniff(self):
        self.assertEqual(R.sniff_image(png(30, 10))[:3], ('png', 30, 10))
        from PIL import Image
        b = io.BytesIO()
        Image.new('RGB', (64, 48)).save(b, 'JPEG')
        self.assertEqual(R.sniff_image(b.getvalue()), ('jpeg', 64, 48))
        with self.assertRaises(ValueError):
            R.image_block(b'not an image')
        big = R.image_block(png(2000, 1000))
        self.assertAlmostEqual(big['w'], R.CONTENT_W_PT, places=1)                         # sayfa genisligine sigar


class MarkdownTests(unittest.TestCase):
    def test_roundtrip(self):
        blocks = sample_blocks()
        img = blocks[7]
        md = R.blocks_to_markdown(blocks, {id(img): '1'})
        self.assertIn('![resim:1]', md)
        self.assertIn('| **Madde** | **Durum** |', md)
        self.assertIn('Uygun değil \\| kayıt yok', md)
        back = R.markdown_to_blocks(md, {'1': img})
        want = strip(blocks)
        for b in want:                     # Markdown hizalama, renk ve sayfa sonunu tasimaz
            b.pop('align', None)
            b.pop('pb', None)
            for r in b.get('runs', []):
                r['color'] = None
        got = strip(back)
        for b in got:
            b.pop('align', None)
            b.pop('pb', None)
        self.assertEqual(got, want)

    def test_inline_edge_cases(self):
        self.assertEqual(R.md_inline('a **b** c'), [R.run('a '), R.run('b', b=True), R.run(' c')])
        self.assertEqual(R.md_inline('2 * 3 = 6'), [R.run('2 * 3 = 6')])                    # carpma isareti italik degil
        self.assertEqual(R.md_inline('**açık kalan'), [R.run('**açık kalan')])              # dengesiz isaret duz kalir
        self.assertEqual(R.md_inline('***ikisi***'), [R.run('ikisi', b=True, i=True)])
        self.assertEqual(R.md_inline('<u>alt</u> çizgi'), [R.run('alt', u=True), R.run(' çizgi')])
        self.assertEqual(R.md_inline('kaçış \\*yıldız\\*'), [R.run('kaçış *yıldız*')])
        for text in ('# başlık değil', '- tire', '1. sayı', '> alıntı değil'):
            md = R.blocks_to_markdown([R.para(text=text)])
            self.assertEqual(R.runs_text(R.markdown_to_blocks(md)[0]['runs']), text)
            self.assertEqual(R.markdown_to_blocks(md)[0]['style'], 'normal')

    def test_md_file_with_images(self):
        blocks = [R.para(text='Rapor'), R.image_block(png())]
        path = os.path.join(TMP, 'not.md')
        md, files = R.markdown_file_text(blocks, path)
        self.assertIn('![resim1.png](not_resimler/resim1.png)', md)
        for fp, data in files.items():
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            pathlib.Path(fp).write_bytes(data)
        back = R.markdown_to_blocks(md, base_dir=TMP)
        self.assertEqual([b['t'] for b in back], ['p', 'img'])


class HtmlTests(unittest.TestCase):
    def test_html_to_markdown(self):
        html = ('<h2>Başlık</h2><p>Bir <strong>kalın</strong> ve <em>eğik</em> <u>çizgi</u> 5*3</p>'
                '<ul><li>bir</li><li>iki<ul><li>alt</li></ul></li></ul><ol><li>x</li><li>y</li></ol>'
                '<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2|3</td></tr></table>'
                '<p># düz</p><script>alert(1)</script>')
        md = R.html_to_markdown(html)
        self.assertIn('## Başlık', md)
        self.assertIn('Bir **kalın** ve *eğik* <u>çizgi</u> 5\\*3', md)
        self.assertIn('- bir\n- iki\n  - alt\n1. x\n2. y', md)
        self.assertIn('| **A** | **B** |\n|---|---|\n| 1 | 2\\|3 |', md)
        self.assertNotIn('alert', md)
        blocks = R.markdown_to_blocks(md)
        self.assertEqual(R.runs_text(blocks[-1]['runs']), '# düz')

    def test_blocks_html_roundtrip(self):
        blocks = sample_blocks()
        html = R.html_document(blocks, 'Rapor')
        self.assertIn('data:image/png;base64,', html)
        back = R.html_to_blocks(html)
        self.assertEqual([b['t'] for b in back], [b['t'] for b in blocks])
        self.assertEqual(back[1]['runs'][1], R.run('Örnek Gıda', b=True))

    def test_json_roundtrip(self):
        blocks = sample_blocks()
        self.assertEqual(strip(R.blocks_from_json(R.blocks_to_json(blocks))), strip(blocks))
        self.assertTrue(R.has_formatting(blocks))
        self.assertFalse(R.has_formatting([R.para(text='düz')]))


if __name__ == '__main__':
    unittest.main()
