# -*- coding: utf-8 -*-
"""AI Editor 1.8 - WordCraft koprusu testleri (ag gerektirmez).

Sahte bir kontrol sunucusu WordCraft'in satir basina JSON protokolunu (auth, engine.execute, document.inspect,
document.selection) taklit eder. Gercek WordCraft ile uctan uca test AGFO_WORDCRAFT_EXE verilirse calisir:
  AGFO_WORDCRAFT_EXE=/yol/wordcraft xvfb-run -a python -m unittest ai-editor/tests/test_wordcraft.py
"""
import hashlib
import io
import json
import os
import pathlib
import socket
import sys
import tempfile
import threading
import unittest
import zipfile

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-wc-test-')
os.environ.setdefault('LOCALAPPDATA', TMP)

import agfo_wordcraft as wc  # noqa: E402


def _info(blocks, a, f):
    return {'blocks': blocks, 'selection': {'anchor': a, 'focus': f, 'text': ''}}


def _pos(i, off):
    return {'story': 'body', 'path': [i], 'off': off}


class MarkdownTests(unittest.TestCase):
    def test_runs_bold_italic_turkish_byte_offsets(self):
        text = 'Tesiste kalın kısım ve normal metin.'
        runs = [{'start': 8, 'end': 22, 'props': {'bold': True}}]     # 'kalın kısım' = 14 bayt
        self.assertEqual(wc._runs_markdown(text, runs), 'Tesiste **kalın kısım** ve normal metin.')
        runs = [{'start': 0, 'end': 7, 'props': {'italic': True, 'bold': True}}]
        self.assertEqual(wc._runs_markdown('Tesiste x', runs), '***Tesiste*** x')

    def test_deleted_revision_zero_is_skipped(self):
        # WordCraft revizyon numarasini verir: {'del': 0} de silinmistir
        text = 'yeni eski'
        runs = [{'start': 0, 'end': 5, 'props': {'ins': 0}}, {'start': 5, 'end': 9, 'props': {'del': 0}}]
        self.assertEqual(wc._runs_markdown(text, runs), 'yeni ')

    def test_selection_spanning_heading_list_table(self):
        blocks = [
            {'index': 0, 'type': 'paragraph', 'style': 'Heading1', 'text': 'Denetim Raporu'},
            {'index': 1, 'type': 'paragraph', 'style': 'Normal', 'text': 'Giriş metni.', 'runs': []},
            {'index': 2, 'type': 'paragraph', 'style': 'ListParagraph', 'text': 'madde bir', 'list': {'level': 0, 'num': 1}},
            {'index': 3, 'type': 'paragraph', 'style': 'ListParagraph', 'text': 'alt madde', 'list': {'level': 1, 'num': 1}},
            {'index': 4, 'type': 'table', 'cells': [['A', 'B|C'], ['1', '2']], 'rows': 2, 'cols': 2},
            {'index': 5, 'type': 'paragraph', 'style': 'Normal', 'text': 'Son.'},
        ]
        md = wc.selection_markdown(_info(blocks, _pos(0, 0), _pos(5, 0)))
        self.assertEqual(md, '# Denetim Raporu\n\nGiriş metni.\n\n- madde bir\n  - alt madde\n\n| A | B\\|C |\n|---|---|\n| 1 | 2 |')
        # ters yonde secim ve kismi paragraflar
        md = wc.selection_markdown(_info(blocks, _pos(2, 5), _pos(1, 7)))
        self.assertEqual(md, 'metni.\n\n- madde')

    def test_selection_outside_body_or_in_cell_returns_empty(self):
        b = [{'index': 0, 'type': 'paragraph', 'text': 'x'}]
        self.assertEqual(wc.selection_markdown(_info(b, {'story': {'part': 1}, 'path': [0], 'off': 0}, _pos(0, 1))), '')
        self.assertEqual(wc.selection_markdown(_info(b, {'story': 'body', 'path': [0, 0, 0, 0], 'off': 0}, _pos(0, 1))), '')

    def test_paths_and_arch(self):
        with mock_env(PROCESSOR_ARCHITECTURE='ARM64'):
            self.assertEqual(wc.windows_arch(), 'arm64')
        with mock_env(PROCESSOR_ARCHITECTURE='x86', PROCESSOR_ARCHITEW6432=''):
            self.assertEqual(wc.windows_arch(), 'x86')
        with mock_env(WORDCRAFT_PROFILE_DIR=TMP):
            self.assertEqual(wc.key_path(7981), pathlib.Path(TMP) / 'control-key.local-7981')
        self.assertTrue(wc.host_allowed('https://github.com/storytold/wordcraft/releases/download/v0.10.0/x.zip'))
        self.assertTrue(wc.host_allowed('https://raw.githubusercontent.com/LibreOffice/dictionaries/x/tr_TR/tr_TR.dic'))
        self.assertFalse(wc.host_allowed('http://github.com/x'))
        self.assertFalse(wc.host_allowed('https://evil.example/x.zip'))
        self.assertEqual(set(wc.PORTABLE), {'x64', 'arm64', 'x86'})
        for name, sha in wc.PORTABLE.values():
            self.assertIn(wc.WORDCRAFT_VERSION, name)
            self.assertRegex(sha, r'^[0-9a-f]{64}$')


class mock_env:
    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = os.environ.get(k)
            os.environ[k] = v

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _Resp(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix='agfo-wc-inst-'))
        self.env = mock_env(LOCALAPPDATA=str(self.root))
        self.env.__enter__()
        os.environ.pop('AGFO_WORDCRAFT_EXE', None)

    def tearDown(self):
        self.env.__exit__()

    def _zip(self, members):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            for n, data in members.items():
                z.writestr(n, data)
        return b.getvalue()

    def test_install_verifies_extracts_and_is_idempotent(self):
        data = self._zip({'wordcraft-0.10.0-windows-x64-portable/wordcraft.exe': b'MZ', 'wordcraft-0.10.0-windows-x64-portable/LICENSE-MIT': b'm'})
        name = wc.PORTABLE['x64'][0]
        urls = []

        def opener(url):
            urls.append(url)
            return _Resp(data)
        with unittest.mock.patch.dict(wc.PORTABLE, {'x64': (name, hashlib.sha256(data).hexdigest())}):
            exe = wc.install(opener=opener, with_dictionary=False, arch='x64')
        self.assertEqual(exe.name, 'wordcraft.exe')
        self.assertEqual(exe.read_bytes(), b'MZ')
        self.assertTrue(str(exe).startswith(str(wc.install_root() / wc.WORDCRAFT_VERSION)))
        self.assertEqual(urls, [wc.RELEASE_URL % (wc.WORDCRAFT_VERSION, name)])
        self.assertFalse(list(wc.install_root().glob('*.zip')))          # ZIP silindi
        self.assertEqual(wc.install(opener=lambda u: self.fail('indirmemeliydi'), with_dictionary=False), exe)

    def test_sha_mismatch_installs_nothing(self):
        data = self._zip({'a/wordcraft.exe': b'MZ'})
        with self.assertRaises(wc.WordCraftError) as cm:
            wc.install(opener=lambda u: _Resp(data), with_dictionary=False, arch='x64')
        self.assertIn('SHA-256', str(cm.exception))
        self.assertIsNone(wc.installed_exe())
        self.assertFalse(list(wc.install_root().rglob('*.part')))

    def test_unsafe_zip_rejected(self):
        data = self._zip({'../evil.exe': b'x'})
        zp = self.root / 'z.zip'
        zp.write_bytes(data)
        with self.assertRaises(wc.WordCraftError):
            wc.safe_extract(zp, self.root / 'out')
        self.assertFalse((self.root / 'evil.exe').exists())

    def test_dictionary_download(self):
        blobs = {n: ('içerik ' + n).encode('utf-8') for n in wc.DICT_FILES}
        sums = {n: hashlib.sha256(b).hexdigest() for n, b in blobs.items()}
        with unittest.mock.patch.dict(wc.DICT_FILES, sums):
            self.assertFalse(wc.dictionary_installed())
            d = wc.install_dictionary(opener=lambda url: _Resp(blobs[url.rsplit('/', 1)[1]]))
            self.assertTrue(wc.dictionary_installed())
            self.assertEqual(d, self.root / 'WordCraft' / 'dictionaries')
            for n in wc.DICT_FILES:
                self.assertIn(wc.DICT_COMMIT, wc.DICT_URL % (wc.DICT_COMMIT, n))


import unittest.mock  # noqa: E402


class FakeWordCraft:
    """WordCraft kontrol protokolunun kucuk bir kopyasi: tek belge, duz paragraflar."""

    def __init__(self, key='k' * 64):
        self.key = key
        self.paras = ['Giriş paragrafı.', 'Gıda güvenliği kültürü önemlidir.']
        self.sel = (_pos(1, 0), _pos(1, len(self.paras[1].encode('utf-8'))))
        self.calls = []
        self.track = False
        self.author = ''
        self.srv = socket.socket()
        self.srv.bind(('127.0.0.1', 0))
        self.srv.listen(4)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def close(self):
        try:
            self.srv.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.srv.close()

    def _text(self, a, f):
        s, e = sorted((a, f), key=wc._pos_key)
        out = []
        for i in range(s['path'][0], e['path'][0] + 1):
            raw = self.paras[i].encode('utf-8')
            bs = s['off'] if i == s['path'][0] else 0
            be = e['off'] if i == e['path'][0] else len(raw)
            out.append(raw[bs:be].decode('utf-8'))
        return '\n'.join(out)

    def _serve(self):
        while True:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._conn, args=(conn,), daemon=True).start()

    def _conn(self, conn):
        f = conn.makefile('rwb')
        authed = False
        for line in f:
            req = json.loads(line)
            m, p = req.get('method'), req.get('params') or {}
            if m == 'auth':
                authed = req.get('key') == self.key
                res = {'ok': authed, 'result': {}} if authed else {'ok': False, 'error': 'unauthorized'}
            elif not authed and req.get('key') != self.key:
                res = {'ok': False, 'error': 'unauthorized'}
            else:
                res = self._handle(m, p)
            res['id'] = req.get('id')
            f.write((json.dumps(res, ensure_ascii=False) + '\n').encode('utf-8'))
            f.flush()
            if res.get('error') == 'unauthorized':
                conn.close()
                return

    def _handle(self, m, p):
        if m == 'engine.execute':
            m, p = p['command'], p.get('params') or {}
        self.calls.append((m, p))
        if m == 'document.inspect':
            blocks = [{'index': i, 'type': 'paragraph', 'style': 'Normal', 'text': t} for i, t in enumerate(self.paras)]
            return {'ok': True, 'result': {'blocks': blocks, 'trackChanges': self.track,
                                           'selection': {'anchor': self.sel[0], 'focus': self.sel[1], 'text': self._text(*self.sel)}}}
        if m == 'document.selection':
            return {'ok': True, 'result': {'anchor': self.sel[0], 'focus': self.sel[1], 'text': self._text(*self.sel)}}
        if m == 'select.range':
            self.sel = (p['anchor'], p['focus'])
        elif m == 'select.all':
            self.sel = (_pos(0, 0), _pos(len(self.paras) - 1, len(self.paras[-1].encode('utf-8'))))
        elif m == 'select.paragraph':
            i = self.sel[0]['path'][0]
            self.sel = (_pos(i, 0), _pos(i, len(self.paras[i].encode('utf-8'))))
        elif m == 'review.trackChanges':
            self.track = bool(p.get('value'))
        elif m == 'file.setAuthor':
            self.author = p['name']
        elif m == 'edit.paste':
            pass
        elif m == 'text.insert':
            i = self.sel[0]['path'][0]
            self.paras[i] = p['text']
        elif m in ('ui.inspect', 'ui.language', 'file.new', 'review.language', 'select.collapse', 'file.open'):
            pass
        else:
            return {'ok': False, 'error': 'unknown command %s' % m}
        return {'ok': True, 'result': {}}


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeWordCraft()
        self.c = wc.Client(self.fake.port, key=self.fake.key, timeout=5)

    def tearDown(self):
        self.c.close()
        self.fake.close()

    def test_capture_and_apply_with_tracking(self):
        cap = self.c.capture('selection')
        self.assertEqual((cap['where'], cap['markdown']), ('seçim', 'Gıda güvenliği kültürü önemlidir.'))
        self.c.apply(cap, '<p>Yeni <strong>metin</strong>.</p>')
        names = [m for m, _ in self.fake.calls]
        self.assertLess(names.index('select.range'), names.index('edit.paste'))
        self.assertIn('document.selection', names)                    # uygulamadan once dogrulama
        self.assertEqual(self.fake.author, wc.AUTHOR)
        self.assertTrue(self.fake.track)
        paste = [p for m, p in self.fake.calls if m == 'edit.paste'][-1]
        self.assertEqual(paste, {'html': '<p>Yeni <strong>metin</strong>.</p>'})

    def test_collapsed_selection_uses_paragraph_and_all_scope(self):
        self.fake.sel = (_pos(0, 3), _pos(0, 3))
        cap = self.c.capture('selection')
        self.assertEqual((cap['where'], cap['markdown']), ('paragraf', 'Giriş paragrafı.'))
        cap = self.c.capture('all')
        self.assertEqual(cap['where'], 'belge')
        self.assertEqual(cap['markdown'], 'Giriş paragrafı.\n\nGıda güvenliği kültürü önemlidir.')

    def test_apply_refuses_when_text_changed(self):
        cap = self.c.capture('selection')
        self.fake.paras[1] = 'Başka biri değiştirdi.'
        with self.assertRaises(wc.WordCraftError) as cm:
            self.c.apply(cap, '<p>x</p>')
        self.assertIn('değişti', str(cm.exception))
        self.assertNotIn('edit.paste', [m for m, _ in self.fake.calls])

    def test_below_mode_collapses_to_end_and_track_off(self):
        cap = self.c.capture('selection')
        self.c.apply(cap, '<p>Çeviri</p>', mode='below', track=False)
        ranges = [p for m, p in self.fake.calls if m == 'select.range']
        self.assertEqual(ranges[-1]['anchor'], ranges[-1]['focus'])
        self.assertEqual(ranges[-1]['anchor'], cap['focus'])
        self.assertFalse(self.fake.track)

    def test_wrong_key_and_closed_app(self):
        bad = wc.Client(self.fake.port, key='x' * 64, timeout=5)
        with self.assertRaises(wc.WordCraftError) as cm:
            bad.inspect()
        self.assertIn('anahtar', str(cm.exception))
        self.assertTrue(self.c.alive())
        self.fake.close()
        self.c.close()
        dead = wc.Client(self.fake.port, key=self.fake.key, timeout=2)
        self.assertFalse(dead.alive())

    def test_reconnects_after_dropped_connection(self):
        self.c.inspect()
        self.c._sock.close()                     # sunucu baglantiyi kesmis gibi
        self.assertIn('blocks', self.c.inspect())

    def test_launch_waits_for_key_file(self):
        prof = tempfile.mkdtemp(prefix='agfo-wc-prof-')

        class P:
            returncode = None

            def poll(self):
                return None
        calls = []

        def popen(args, **kw):
            calls.append(args)
            pathlib.Path(prof, 'control-key.local-%s' % args[2]).write_text(self_key)
            return P()
        self_key = self.fake.key
        with mock_env(WORDCRAFT_PROFILE_DIR=prof):
            c = wc.launch('/x/wordcraft.exe', files=['a.docx'], port=self.fake.port, popen=popen, wait=3)
            self.assertEqual(calls[0], ['/x/wordcraft.exe', '--control', str(self.fake.port), 'a.docx'])
            self.assertTrue(c.alive())
            c.close()

    def test_launch_reports_early_exit(self):
        class Dead:
            returncode = 3

            def poll(self):
                return 3
        with mock_env(WORDCRAFT_PROFILE_DIR=tempfile.mkdtemp()):
            with self.assertRaises(wc.WordCraftError) as cm:
                wc.launch('/x/wordcraft.exe', port=1, popen=lambda a, **k: Dead(), wait=2, sleep=lambda s: None)
        self.assertIn('çıkış kodu 3', str(cm.exception))


@unittest.skipUnless(os.environ.get('AGFO_WORDCRAFT_EXE') and (sys.platform == 'win32' or os.environ.get('DISPLAY')),
                     'gercek WordCraft icin AGFO_WORDCRAFT_EXE ve ekran gerekir')
class RealWordCraftTests(unittest.TestCase):
    """Gercek WordCraft: ac, sec, AI benzeri sonucu izlenen degisiklik olarak uygula, kaydet."""

    @classmethod
    def setUpClass(cls):
        cls.prof = tempfile.mkdtemp(prefix='agfo-wc-real-')
        cls.env = mock_env(WORDCRAFT_PROFILE_DIR=cls.prof)
        cls.env.__enter__()
        cls.c = wc.launch(os.environ['AGFO_WORDCRAFT_EXE'], wait=60)
        cls.c.setup()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.c.call('app.quit')
        except wc.WordCraftError:
            pass
        cls.c.close()
        if cls.c.process is not None:
            try:
                cls.c.process.wait(timeout=20)
            except Exception:
                cls.c.process.kill()
        cls.env.__exit__()

    def test_roundtrip_tracked_ai_edit(self):
        import agfo_richdoc as rdoc
        html = rdoc.blocks_to_html(rdoc.markdown_to_blocks('# Denetim Raporu\n\nTesiste **kalın kısım** ve normal metin.\n\nİkinci paragraf.', {}))
        self.c.new_document(html)
        self.c.execute('select.text', {'text': 'kalın kısım'})
        self.c.execute('select.paragraph')
        cap = self.c.capture('selection')
        self.assertEqual(cap['markdown'].strip(), 'Tesiste **kalın kısım** ve normal metin.')
        new = rdoc.blocks_to_html(rdoc.markdown_to_blocks('Tesiste **kritik** bir bulgu var.', {}))
        self.c.apply(cap, new)
        info = self.c.inspect()
        self.assertTrue(info['trackChanges'])
        changes = self.c.execute('review.changes')
        self.assertTrue(any(ch['kind'] == 'insert' and ch['author'] == wc.AUTHOR for ch in changes))
        self.assertTrue(any(ch['kind'] == 'delete' for ch in changes))
        md = self.c.document_markdown()
        self.assertIn('Tesiste **kritik** bir bulgu var.', md)
        self.assertNotIn('normal metin', md)                           # silinmis revizyon kaynaga girmez
        self.c.execute('review.acceptAll')
        out = pathlib.Path(self.prof) / 'kayit.docx'
        self.c.execute('file.saveAs', {'path': str(out)})
        self.assertTrue(out.is_file() and out.stat().st_size > 1000)
        # belge degisince uygulama reddedilir
        self.c.execute('select.text', {'text': 'İkinci'})
        cap2 = self.c.capture('selection')
        self.c.execute('text.insert', {'text': 'Üçüncü'})
        with self.assertRaises(wc.WordCraftError):
            self.c.apply(cap2, '<p>x</p>')


if __name__ == '__main__':
    unittest.main()
