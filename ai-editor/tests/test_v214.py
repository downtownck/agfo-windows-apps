# -*- coding: utf-8 -*-
"""2.14.0: bu bilgisayardaki Arapca ses servisleri (SILMA, Habibi) ve yerel ses secimi."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-214-')
os.environ['LOCALAPPDATA'] = TMP

import agfo_ai_client as ai  # noqa: E402
import agfo_localtts as lt  # noqa: E402


class FakeArabic:
    """ar_server.py'nin /health, /voices, /tts ve /lexicon uclari."""

    def __init__(self, token='tok', engine='silma'):
        self.token, self.engine, self.calls = token, engine, []
        svc = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype='application/json', headers=None):
                data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header('Content-Type', ctype)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.headers.get('X-AGFO-Token') != svc.token:
                    return self._send(401, {'detail': 'invalid token'})
                if self.path == '/health':
                    return self._send(200, {'ok': True, 'model': svc.engine, 'language': 'ar', 'device': 'cuda', 'voices': 2})
                if self.path == '/voices':
                    return self._send(200, {'engine': svc.engine, 'default': 'fusha',
                                            'voices': [{'id': 'fusha', 'name': 'Fusha'}, {'id': 'misirli', 'name': 'Mısırlı'}]})
                if self.path == '/lexicon':
                    return self._send(200, {'entries': []})
                self._send(404, {'detail': 'yok'})

            def do_POST(self):
                if self.headers.get('X-AGFO-Token') != svc.token:
                    return self._send(401, {'detail': 'invalid token'})
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])).decode())
                if self.path == '/tts':
                    svc.calls.append(body)
                    return self._send(200, b'ID3' + body['text'].encode(), 'audio/mpeg', {'X-AGFO-Seconds': '2.50'})
                self._send(404, {'detail': 'yok'})

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.endpoint = 'http://127.0.0.1:%d' % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def write_env(folder, lines):
    d = os.path.join(os.environ['LOCALAPPDATA'], 'AGFO', folder)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, '.env'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return d


class ServiceDiscoveryTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {'LOCALAPPDATA': tempfile.mkdtemp(prefix='agfo-214-svc-')})
        p.start()
        self.addCleanup(p.stop)

    def test_local_services(self):
        self.assertEqual(lt.local_services(), [])
        write_env('TTS', ['AGFO_TTS_TOKEN=a', 'AGFO_TTS_PORT=8765'])
        write_env('TTS-AR', ['AGFO_TTS_TOKEN=b', 'AGFO_TTS_PORT=8770', 'AGFO_TTS_ENGINE=silma', 'AGFO_TTS_LANG=ar'])
        write_env('TTS-HABIBI', ['AGFO_TTS_PORT=8780'])                 # anahtarsiz: kurulu sayilmaz
        svcs = lt.local_services()
        self.assertEqual([(s['id'], s['lang'], s['endpoint']) for s in svcs],
                         [('ema', 'tr', 'http://127.0.0.1:8765'), ('silma', 'ar', 'http://127.0.0.1:8770')])
        self.assertEqual(svcs[1]['label'], 'SILMA (Arapça)')
        write_env('TTS-HABIBI', ['AGFO_TTS_TOKEN=c', 'AGFO_TTS_PORT=8780', 'AGFO_TTS_LABEL=Habibi Mısır'])
        self.assertEqual(lt.local_services()[2]['label'], 'Habibi Mısır')
        self.assertEqual(lt.local_services()[2]['engine'], 'habibi')
        write_env('TTS-QWEN', ['AGFO_TTS_TOKEN=d', 'AGFO_TTS_PORT=8790', 'AGFO_TTS_ENGINE=qwen', 'AGFO_TTS_LANG=en'])
        q = lt.local_services()[3]
        self.assertEqual((q['id'], q['lang'], q['label']), ('qwen', 'en', 'Qwen3-TTS (İngilizce, İspanyolca)'))
        b = lt.LocalSpeechBackend(q['endpoint'], 'd', lang=q['lang'], label=q['label'])
        self.assertFalse(b.has_lexicon)
        self.assertIn('Hola', lt.SAMPLES['en'])


class ArabicBackendTests(unittest.TestCase):
    def setUp(self):
        self.svc = FakeArabic()
        self.b = lt.LocalSpeechBackend(self.svc.endpoint, 'tok', site=mock.Mock(), lang='ar', engine='silma', voice='misirli',
                                       label='SILMA (Arapça)')

    def tearDown(self):
        self.svc.close()

    def test_voice_sent_and_no_script(self):
        job = self.b.speech_submit('مرحبا', reading_script=True)
        self.assertEqual(self.svc.calls[0]['voice'], 'misirli')
        self.assertEqual(self.svc.calls[0]['text'], 'مرحبا')
        self.assertEqual(job['script']['status'], 'skipped')
        self.b.site.speech_script.assert_not_called()
        audio, secs = self.b.speech_quick('نص', speed=1.2)
        self.assertEqual((audio[:3], secs), (b'ID3', 2.5))
        with self.assertRaises(ai.AIError):
            self.b.speech_script('نص')

    def test_voices_and_lexicon(self):
        v = self.b.voices()
        self.assertEqual([x['id'] for x in v['voices']], ['fusha', 'misirli'])
        self.assertFalse(self.b.has_lexicon)
        self.assertEqual(self.b.lexicon_list()['entries'], [])
        for call in (lambda: self.b.lexicon_change('save', 'a', 'b'), self.b.sync_from_site, lambda: self.b.lexicon_listen('x')):
            with self.assertRaises(ai.AIError) as cm:
                call()
            self.assertIn('telaffuz sözlüğü yok', str(cm.exception))

    def test_ema_has_single_voice_and_no_voice_field(self):
        b = lt.LocalSpeechBackend(self.svc.endpoint, 'tok')
        self.assertEqual(b.voices()['voices'][0]['name'], 'EMA Lightning')
        self.assertTrue(b.has_lexicon)
        b.speech_quick('Merhaba')
        self.assertNotIn('voice', self.svc.calls[-1])


@unittest.skipUnless(sys.platform == 'win32' or bool(os.environ.get('DISPLAY')), 'ekran gerekli')
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('agfo_ai_editor_214', str(SRC / 'agfo_ai_editor.pyw'))
        spec = importlib.util.spec_from_loader('agfo_ai_editor_214', loader)
        cls.m = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.m)

    def setUp(self):
        self.ar = FakeArabic(engine='silma')
        self.hb = FakeArabic(engine='habibi', token='tok2')
        self.p = mock.patch.object(self.m.App, 'backends', lambda _self: [])
        self.p.start()
        self.app = self.m.App(smoke=True)
        self.app.withdraw()
        self.app._test_local_services = [
            {'id': 'ema', 'endpoint': 'http://127.0.0.1:9', 'token': 'x', 'dir': TMP, 'engine': 'ema', 'lang': 'tr',
             'label': 'EMA Lightning (Türkçe)'},
            {'id': 'silma', 'endpoint': self.ar.endpoint, 'token': 'tok', 'dir': os.path.join(TMP, 'AGFO', 'TTS-AR'),
             'engine': 'silma', 'lang': 'ar', 'label': 'SILMA (Arapça)'},
            {'id': 'habibi', 'endpoint': self.hb.endpoint, 'token': 'tok2', 'dir': TMP, 'engine': 'habibi', 'lang': 'ar',
             'label': 'Habibi (Arapça)'},
        ]

    def tearDown(self):
        self.p.stop()
        for k in ('speech_service', 'local_tts_service', 'local_voice'):
            self.app.settings.pop(k, None)
        self.m.core.save_settings(self.app.settings)
        self.app.destroy()
        self.ar.close()
        self.hb.close()

    def pump(self, cond, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            self.app.update()
            if cond():
                return True
            time.sleep(0.02)
        return False

    def test_pick_arabic_voice(self):
        app = self.app
        app.sp_service_var.set('local')
        app._speech_service_changed()
        self.assertTrue(app.sp_local_box.winfo_manager())
        self.assertTrue(self.pump(lambda: len(app.sp_local_cb.cget('values')) == 5), app.sp_local_cb.cget('values'))
        labels = list(app.sp_local_cb.cget('values'))
        self.assertEqual(labels[0], 'EMA Lightning (Türkçe)')
        self.assertIn('SILMA (Arapça) · Mısırlı', labels)
        self.assertEqual(app._voice_sig(), 'yerel')
        app.sp_local_var.set('SILMA (Arapça) · Mısırlı')
        app._local_voice_changed()
        self.assertEqual((app.settings['local_tts_service'], app.settings['local_voice']['silma']), ('silma', 'misirli'))
        self.assertTrue(self.pump(lambda: 'SILMA (Arapça) bu bilgisayarda hazır' in app.sp_state_var.get()), app.sp_state_var.get())
        self.assertEqual(str(app.sp_sync_btn['state']), 'disabled')
        self.assertTrue(app._voice_sig().startswith('yerel-silma-'))
        self.assertIn('TTS-AR', app.sp_local_note.cget('text'))
        app.sp_local_var.set('EMA Lightning (Türkçe)')
        app._local_voice_changed()
        self.assertEqual(app.sp_local_note.cget('text'), '')
        app.sp_local_var.set('SILMA (Arapça) · Mısırlı')
        app._local_voice_changed()
        b = app._speech_backend('x')
        self.assertEqual((b.lang, b.voice, b.endpoint), ('ar', 'misirli', self.ar.endpoint))
        # ornek ses Arapca metinle
        self.assertTrue(app.try_speech_voice())
        self.assertTrue(self.pump(lambda: bool(self.ar.calls)))
        self.assertIn('مرحبا', self.ar.calls[0]['text'])
        self.assertEqual(self.ar.calls[0]['voice'], 'misirli')
        # sozluk Arapcada acilmaz
        with mock.patch.object(self.m.messagebox, 'showinfo') as info:
            self.assertIsNone(app.open_lexicon())
            info.assert_called_once()
        # Habibi'ye gec: farkli ses imzasi
        sig = app._voice_sig()
        app.sp_local_var.set('Habibi (Arapça) · Fusha')
        app._local_voice_changed()
        self.assertNotEqual(app._voice_sig(), sig)
        self.assertEqual(app._speech_backend('x').endpoint, self.hb.endpoint)

    def test_closed_service_listed(self):
        app = self.app
        self.hb.close()
        app.settings['speech_service'] = 'local'
        app.sp_service_var.set('local')
        app._sync_speech_tab()
        self.assertTrue(self.pump(lambda: any('kapalı' in x for x in app.sp_local_cb.cget('values'))), app.sp_local_cb.cget('values'))
        self.hb = FakeArabic()                                              # tearDown kapatsin

    def test_site_mode_hides_local_box(self):
        app = self.app
        app.sp_service_var.set('site')
        app._speech_service_changed()
        self.assertFalse(app.sp_local_box.winfo_manager())


if __name__ == '__main__':
    unittest.main()
