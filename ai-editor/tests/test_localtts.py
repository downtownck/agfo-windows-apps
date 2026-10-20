# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.7 - bu bilgisayardaki ses servisi testleri.  python tests/test_localtts.py
Gercek servis yerine ayni HTTP arayuzunu sunan kucuk bir sahte servis kullanilir. GUI testleri xvfb ile calisir."""
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
TMP = tempfile.mkdtemp(prefix='agfo-editor-localtts-')
os.environ['LOCALAPPDATA'] = TMP

import agfo_ai_client as ai  # noqa: E402
import agfo_localtts as lt  # noqa: E402
import agfo_readaloud as ra  # noqa: E402
import agfo_speech as sp  # noqa: E402


class FakeService:
    """AGFO TTS Service 1.1.x'in /health, /tts ve /lexicon uclari."""

    def __init__(self, token='tok'):
        self.token = token
        self.tts_calls = []
        self.base = {'HACCP': 'hasip', 'Chicago': 'Şikago'}
        self.custom = {}
        self.cached = set()
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

            def _auth(self):
                if self.headers.get('X-AGFO-Token') != svc.token:
                    self._send(401, {'detail': 'bad token'})
                    return False
                return True

            def merged(self):
                m = dict(svc.base)
                for k, v in svc.custom.items():
                    if v is None:
                        m.pop(k, None)
                    else:
                        m[k] = v
                return m

            def do_GET(self):
                if not self._auth():
                    return
                if self.path == '/health':
                    return self._send(200, {'ok': True, 'version': '1.1.1', 'device': 'cuda:0', 'lexicon_entries': len(self.merged())})
                if self.path == '/lexicon':
                    m = self.merged()
                    rows = []
                    for w in sorted(set(svc.base) | set(svc.custom)):
                        c = svc.custom.get(w, ...)
                        src = 'removed' if c is None else ('base' if c is ... else ('edited' if w in svc.base else 'added'))
                        rows.append({'word': w, 'reading': m.get(w, svc.base.get(w, '')), 'source': src})
                    return self._send(200, {'entries': rows, 'active': len(m)})
                self._send(404, {'detail': 'yok'})

            def do_POST(self):
                if not self._auth():
                    return
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])).decode())
                if self.path == '/tts':
                    svc.tts_calls.append(body)
                    text = body['text']
                    if body.get('apply_lexicon', True):
                        for k, v in self.merged().items():
                            text = text.replace(k, v)
                    audio = b'ID3' + text.encode('utf-8')
                    key = json.dumps(body, sort_keys=True)
                    if key in svc.cached:
                        return self._send(200, audio, 'audio/mpeg', {'X-AGFO-Cached': '1'})
                    svc.cached.add(key)
                    return self._send(200, audio, 'audio/mpeg', {'X-AGFO-Cached': '0', 'X-AGFO-Seconds': '%.2f' % (len(text) / 20)})
                if self.path == '/lexicon/entry':
                    svc.custom[body['word']] = body['reading']
                    return self._send(200, {'ok': True})
                if self.path == '/lexicon/delete':
                    w = body['word']
                    if body.get('reading') == '__restore__':
                        svc.custom.pop(w, None)
                    elif w in svc.base:
                        svc.custom[w] = None
                    elif w in svc.custom:
                        svc.custom.pop(w)
                    else:
                        return self._send(404, {'detail': 'kelime sözlükte yok'})
                    return self._send(200, {'ok': True})
                self._send(404, {'detail': 'yok'})

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.endpoint = 'http://127.0.0.1:%d' % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class FakeSite:
    kind = 'manager'

    def __init__(self, fail_script=False, fail_change=False):
        self.fail_script, self.fail_change = fail_script, fail_change
        self.scripts, self.changes = [], []

    def speech_script(self, text):
        self.scripts.append(text)
        if self.fail_script:
            raise ai.AIError('AI Manager: model yanıt vermedi')
        return {'text': text.replace('Chicago', 'Şikago').replace('15', 'on beş'), 'chunks': 1, 'rewritten': 1,
                'kept_original': 0, 'model': 'openai|m'}

    def lexicon_change(self, op, word, reading=''):
        self.changes.append((op, word, reading))
        if self.fail_change:
            raise ai.AIError('Ortak telaffuz sözlüğünü yalnız site yöneticisi değiştirebilir.')
        return {'ok': True}

    def lexicon_list(self):
        return {'entries': [{'word': 'HACCP', 'reading': 'hasip', 'source': 'base'},
                            {'word': 'Kaya Gıda', 'reading': 'Kaya Gıda', 'source': 'added'},
                            {'word': 'Chicago', 'reading': 'Şikago', 'source': 'removed'},
                            {'word': 'Henry', 'reading': 'Anri', 'source': 'edited'}], 'can_edit': True}


class ConfigTests(unittest.TestCase):
    def test_read_config(self):
        d = os.path.join(TMP, 'cfg1')
        os.makedirs(d)
        p = os.path.join(d, '.env')
        with open(p, 'w', encoding='utf-8-sig') as fh:
            fh.write('# yorum\nAGFO_TTS_PORT=8771\nAGFO_TTS_TOKEN=abc123\n')
        self.assertEqual(lt.read_config(p), {'endpoint': 'http://127.0.0.1:8771', 'token': 'abc123', 'dir': d})
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write('AGFO_TTS_PORT=8771\n')
        self.assertIsNone(lt.read_config(p))
        self.assertIsNone(lt.read_config(os.path.join(TMP, 'yok', '.env')))

    def test_default_location(self):
        self.assertEqual(lt.install_dir(), os.path.join(os.environ['LOCALAPPDATA'], 'AGFO', 'TTS'))


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.svc = FakeService()
        self.site = FakeSite()
        self.b = lt.LocalSpeechBackend(self.svc.endpoint, 'tok', site=self.site)

    def tearDown(self):
        self.svc.close()

    def test_health_and_bad_token(self):
        self.assertEqual(self.b.health()['device'], 'cuda:0')
        bad = lt.LocalSpeechBackend(self.svc.endpoint, 'yanlis')
        with self.assertRaises(ai.AIError) as cm:
            bad.health()
        self.assertIn('anahtarı kabul etmedi', str(cm.exception))

    def test_unreachable(self):
        self.svc.close()
        with self.assertRaises(ai.AIError) as cm:
            self.b.health()
        self.assertIn('ulaşılamadı', str(cm.exception))
        self.svc = FakeService()        # tearDown icin

    def test_system_proxy_is_ignored(self):
        with mock.patch.dict(os.environ, {'http_proxy': 'http://127.0.0.1:9', 'HTTP_PROXY': 'http://127.0.0.1:9', 'no_proxy': '', 'NO_PROXY': ''}):
            b = lt.LocalSpeechBackend(self.svc.endpoint, 'tok')
            self.assertTrue(b.health()['ok'])

    def test_quick_lexicon_only(self):
        audio, secs = self.b.speech_quick('Chicago ve HACCP.', speed=1.1)
        self.assertEqual(audio, b'ID3' + 'Şikago ve hasip.'.encode())
        self.assertGreater(secs, 0)
        self.assertEqual(self.site.scripts, [])
        self.assertTrue(self.svc.tts_calls[-1]['apply_lexicon'])
        self.assertEqual(self.svc.tts_calls[-1]['speed'], 1.1)
        audio2, secs2 = self.b.speech_quick('Chicago ve HACCP.', speed=1.1)      # onbellekten: sure MP3 boyundan
        self.assertEqual(audio2, audio)
        self.assertAlmostEqual(secs2, len(audio) * 8 / 96000, places=2)

    def test_reading_script_via_site_without_lexicon(self):
        audio, _s = self.b.speech_quick('Chicago 15 dakika.', reading_script=True)
        self.assertEqual(self.site.scripts, ['Chicago 15 dakika.'])
        self.assertFalse(self.svc.tts_calls[-1]['apply_lexicon'])
        self.assertEqual(self.svc.tts_calls[-1]['text'], 'Şikago on beş dakika.')

    def test_reading_script_failure_falls_back_to_lexicon(self):
        self.b.site = FakeSite(fail_script=True)
        job = self.b.speech_submit('Chicago.', reading_script=True)
        self.assertEqual(job['status'], 'complete')
        self.assertEqual(job['script']['status'], 'skipped')
        self.assertIn('model yanıt vermedi', job['script']['reason'])
        self.assertTrue(self.svc.tts_calls[-1]['apply_lexicon'])
        self.b.site = None
        self.assertEqual(self.b.speech_submit('Chicago.', reading_script=True)['script']['reason'], 'AI Manager bağlantısı yok')
        with self.assertRaises(ai.AIError):
            self.b.speech_script('x')

    def test_script_ready_never_reapplies_lexicon(self):
        self.b.speech_quick('HACCP hazır.', reading_script=True, script_ready=True)
        self.assertEqual(self.site.scripts, [])
        self.assertFalse(self.svc.tts_calls[-1]['apply_lexicon'])

    def test_narrate_sections_through_local_service(self):
        folder = os.path.join(TMP, 'yerel-bolumler')
        secs = [{'title': 'Giriş', 'text': 'Chicago.'}, {'title': 'Sonuç', 'text': 'HACCP.'}]
        states = []
        res = sp.narrate_sections(self.b, secs, folder, mode='files', status=lambda i, st, info: states.append((i, st)),
                                  reading_script=False, speed=1.0, paragraph_pause_ms=500, sleep=lambda s: None, poll=0)
        self.assertEqual(res['failed'], [])
        self.assertEqual(sorted(os.listdir(folder)), ['00 - çalma listesi.m3u', '01 - Giriş.mp3', '02 - Sonuç.mp3'])
        self.assertEqual(pathlib.Path(folder, '01 - Giriş.mp3').read_bytes(), b'ID3' + 'Şikago.'.encode())
        self.assertEqual(self.svc.tts_calls[-1]['paragraph_pause_ms'], 500)
        self.assertIn((1, 'tamam'), states)
        self.assertEqual(self.b._jobs, {})                          # indirilen sesler bellekte kalmaz
        single = os.path.join(TMP, 'yerel-tek.mp3')
        out = sp.narrate(self.b, 'Kısa bir metin.', single, reading_script=False, sleep=lambda s: None, poll=0)
        self.assertTrue(os.path.exists(out['path']))
        self.assertGreater(out['duration_ms'], 0)

    def test_lexicon_change_writes_local_and_site(self):
        d = self.b.lexicon_change('save', 'Kaya Gıda', 'Kaya Gıda A Ş')
        self.assertEqual(d['site'], 'ok')
        self.assertEqual(self.svc.custom['Kaya Gıda'], 'Kaya Gıda A Ş')
        self.assertEqual(self.site.changes, [('save', 'Kaya Gıda', 'Kaya Gıda A Ş')])
        self.b.lexicon_change('delete', 'HACCP')
        self.assertIsNone(self.svc.custom['HACCP'])
        self.b.lexicon_change('restore', 'HACCP')
        self.assertNotIn('HACCP', self.svc.custom)
        self.b.site = FakeSite(fail_change=True)
        d = self.b.lexicon_change('save', 'Henry', 'Anri')
        self.assertIn('yalnız site yöneticisi', d['site'])
        self.assertEqual(self.svc.custom['Henry'], 'Anri')          # yerelde yine kaydedildi
        self.b.site = None
        self.assertEqual(self.b.lexicon_change('save', 'X', 'iks')['site'], 'none')
        with self.assertRaises(ai.AIError):
            self.b.lexicon_change('nope', 'X')
        rows = {r['word']: r for r in self.b.lexicon_list()['entries']}
        self.assertEqual(rows['Henry']['source'], 'added')
        self.assertTrue(self.b.lexicon_list()['local'])

    def test_listen_reads_as_written(self):
        self.assertEqual(self.b.lexicon_listen('Chicago'), b'ID3Chicago')
        self.assertFalse(self.svc.tts_calls[-1]['apply_lexicon'])

    def test_sync_from_site(self):
        res = self.b.sync_from_site()
        self.assertEqual((res['added'], res['removed'], res['same'], res['errors']), (2, 1, 0, []))
        self.assertEqual(self.svc.custom, {'Kaya Gıda': 'Kaya Gıda', 'Chicago': None, 'Henry': 'Anri'})
        again = self.b.sync_from_site()
        self.assertEqual((again['added'], again['removed'], again['same']), (0, 0, 3))
        self.b.site = None
        with self.assertRaises(ai.AIError):
            self.b.sync_from_site()


@unittest.skipUnless(os.environ.get('DISPLAY') or sys.platform == 'win32', 'ekran yok')
class LocalGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('agfo_ai_editor_lt', str(SRC / 'agfo_ai_editor.pyw'))
        spec = importlib.util.spec_from_loader('agfo_ai_editor_lt', loader)
        cls.m = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.m)

    def setUp(self):
        self.svc = FakeService()
        self.site = FakeSite()
        self.p = mock.patch.object(self.m.App, 'backends', lambda _self: [self.site])
        self.p.start()
        self.app = self.m.App(smoke=True)
        self.app.withdraw()

    def tearDown(self):
        self.p.stop()
        self.app.settings['speech_service'] = 'site'      # diger test dosyalarina sizmasin
        self.m.core.save_settings(self.app.settings)
        try:
            self.app.destroy()
        except Exception:
            pass
        self.svc.close()

    def pump(self, cond, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            self.app.update()
            if cond():
                return True
            time.sleep(0.02)
        return False

    def use_local(self):
        self.app._test_local_cfg = {'endpoint': self.svc.endpoint, 'token': 'tok', 'dir': TMP}
        self.app.sp_service_var.set('local')
        self.app._speech_service_changed()

    def test_mode_defaults_and_state_label(self):
        self.app.settings.pop('speech_service', None)
        self.app._test_local_cfg = None
        self.assertEqual(self.app._speech_mode(), 'site')
        self.app._test_local_cfg = {'endpoint': self.svc.endpoint, 'token': 'tok', 'dir': TMP}
        self.assertEqual(self.app._speech_mode(), 'local')       # kuruluysa varsayilan bu bilgisayar
        self.use_local()
        self.assertEqual(self.app.settings['speech_service'], 'local')
        self.assertTrue(self.pump(lambda: 'hazır' in self.app.sp_state_var.get()), self.app.sp_state_var.get())
        self.assertIn('ekran kartında', self.app.sp_state_var.get())
        self.assertEqual(str(self.app.sp_sync_btn['state']), 'normal')
        self.app._test_local_cfg = None
        self.app._sync_speech_tab()
        self.assertIn('kurulu değil', self.app.sp_state_var.get())
        with mock.patch.object(self.m.messagebox, 'showinfo') as info:
            self.app.read_aloud()
        self.assertIn('AGFO-Ses-Kur', info.call_args[0][1])
        self.app.sp_service_var.set('site')
        self.app._speech_service_changed()
        self.assertEqual(str(self.app.sp_sync_btn['state']), 'disabled')

    def test_read_aloud_uses_local_service(self):
        self.use_local()
        player = ra.TimerPlayer()
        self.app._test_player = player
        self.app.manager_info = {'speech': {'speech_ready': True}}     # sitede 17.12: quick yok, yerelde gerekmez
        d = self.app.new_doc(text='Chicago şehri.\n\nHACCP planı.')
        d.text.mark_set('insert', '1.0')
        self.app.read_aloud()
        self.assertTrue(self.pump(lambda: self.app.ra_session.done), self.app.ra_state_var.get())
        self.assertEqual(self.app.ra_state_var.get(), 'Okuma bitti.')
        self.assertEqual([c['text'] for c in self.svc.tts_calls], ['Chicago şehri.', 'HACCP planı.'])
        self.assertEqual(len(player.played), 2)

    def test_export_window_writes_files_locally(self):
        self.use_local()
        self.app.new_doc(text='## Bir\n\n' + 'Birinci bölüm metni. ' * 30 + '\n\n## İki\n\n' + 'İkinci bölüm metni. ' * 30)
        self.app.scope_var.set('all')
        win = self.app.narrate_current()
        self.assertIsInstance(win.b, self.m.localtts.LocalSpeechBackend)
        folder = os.path.join(TMP, 'gui-yerel')
        self.app._test_speech_path = folder
        self.app.sp_script_var.set(False)
        win.mode.set('files')
        win.start()
        self.assertTrue(self.pump(lambda: not win.running and win.msg.get().startswith('✓'), 20), win.msg.get())
        self.assertEqual(sorted(os.listdir(folder)), ['00 - çalma listesi.m3u', '01 - Bir.mp3', '02 - İki.mp3'])

    def test_sync_button_and_lexicon_window(self):
        self.use_local()
        self.app.sync_local_lexicon()
        self.assertTrue(self.pump(lambda: 'Sözlük eşitlendi' in self.app.sp_result_var.get()), self.app.sp_result_var.get())
        self.assertIn('2 kelime eklendi/güncellendi, 1 kaldırıldı', self.app.sp_result_var.get())
        win = self.app.open_lexicon(word='Şirket')
        self.assertIn('bu bilgisayar', win.title())
        self.assertTrue(self.pump(lambda: win.rows))
        win.reading.set('Şirket A Ş')
        win.save()
        self.assertTrue(self.pump(lambda: 'Bu bilgisayarda ve bütün sitelerde geçerli' in win.status.get()), win.status.get())
        self.assertEqual(self.svc.custom['Şirket'], 'Şirket A Ş')
        self.assertIn(('save', 'Şirket', 'Şirket A Ş'), self.site.changes)


if __name__ == '__main__':
    unittest.main(verbosity=1)
