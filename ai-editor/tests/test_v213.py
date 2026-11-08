"""2.13.0: seslendirmede OpenAI / ElevenLabs / MiniMax (AI Manager 17.14+)."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-213-')
os.environ['LOCALAPPDATA'] = TMP

import agfo_ai_client as ai  # noqa: E402
import agfo_speech as speech  # noqa: E402

PROVIDERS = [
    {'id': 'ema', 'label': 'EMA Lightning (Türkçe, AGFO sunucusu)', 'ready': True, 'max_chars': 4000, 'job_max_chars': 60000,
     'speed_min': 0.7, 'speed_max': 1.4, 'default_model': 'ema-lightning', 'default_voice': 'ema'},
    {'id': 'openai', 'label': 'OpenAI', 'ready': True, 'max_chars': 4000, 'job_max_chars': 4000, 'speed_min': 0.25,
     'speed_max': 4.0, 'default_model': 'gpt-4o-mini-tts', 'default_voice': 'marin'},
    {'id': 'elevenlabs', 'label': 'ElevenLabs', 'ready': False, 'max_chars': 4000, 'job_max_chars': 9000, 'speed_min': 0.7,
     'speed_max': 1.2, 'default_model': 'eleven_multilingual_v2', 'default_voice': ''},
    {'id': 'minimax', 'label': 'MiniMax', 'ready': True, 'max_chars': 4000, 'job_max_chars': 9000, 'speed_min': 0.5,
     'speed_max': 2.0, 'default_model': 'speech-2.8-hd', 'default_voice': ''},
]
CATALOG = {'voices': [{'id': 'marin', 'name': 'Marin', 'description': 'Önerilen kalite'}, {'id': 'cedar', 'name': 'Cedar'}],
           'models': [{'id': 'gpt-4o-mini-tts', 'name': 'GPT-4o mini TTS', 'recommended': True}, {'id': 'tts-1', 'name': 'TTS-1'}]}


class ClientTests(unittest.TestCase):
    def backend(self, opts=None):
        b = ai.ManagerBackend('https://ornek.test', token='agfo_x')
        b.speech_opts = opts
        sent = []
        b._call = lambda route, payload=None, timeout=0: (sent.append((route, payload)) or
                                                           {'audio_base64': 'SUQz', 'seconds': 1.5, 'job': 'j1', 'status': 'queued'})
        return b, sent

    def test_ema_sends_no_provider(self):
        b, sent = self.backend({'provider': 'ema'})
        b.speech_quick('Merhaba')
        self.assertNotIn('provider', sent[0][1])
        b, sent = self.backend(None)
        b.speech_submit('Merhaba')
        self.assertNotIn('provider', sent[0][1])

    def test_provider_fields(self):
        b, sent = self.backend({'provider': 'openai', 'voice': 'cedar', 'model': 'tts-1', 'instructions': 'Sakin oku',
                                'job_max_chars': 4000})
        audio, secs = b.speech_quick('Merhaba', speed=1.1)
        self.assertEqual((sent[0][0], sent[0][1]['provider'], sent[0][1]['voice'], sent[0][1]['model']),
                         ('/editor/speech-quick', 'openai', 'cedar', 'tts-1'))
        self.assertEqual(sent[0][1]['instructions'], 'Sakin oku')
        self.assertEqual((audio, secs), (b'ID3', 1.5))
        b.speech_submit('Uzun metin')
        self.assertEqual(sent[1][1]['provider'], 'openai')
        self.assertEqual(b.speech_part_limit, 3400)
        b.voices('openai', refresh=True)
        self.assertEqual(sent[2], ('/editor/voices', {'provider': 'openai', 'refresh': True}))

    def test_narrate_uses_provider_limit(self):
        b, _sent = self.backend({'provider': 'openai', 'job_max_chars': 4000})
        text = '\n\n'.join('Paragraf %d. ' % i + 'Bu cümle bölünme sınırını denemek için yazıldı. ' * 8 for i in range(40))
        parts = speech.split_parts(text, b.speech_part_limit)
        self.assertGreater(len(parts), 3)
        self.assertTrue(all(len(p) <= 3400 for p in parts))


def _display():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(_display(), 'ekran gerekli')
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('agfo_ai_editor', str(SRC / 'agfo_ai_editor.pyw'))
        spec = importlib.util.spec_from_loader('agfo_ai_editor', loader)
        cls.m = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.m)

    def setUp(self):
        self.app = self.m.App(smoke=True)
        self.app.update()
        self.app.settings['speech_service'] = 'site'
        self.app.sp_service_var.set('site')

    def tearDown(self):
        self.app.destroy()

    def pump(self, until=lambda: False, n=200):
        for _ in range(n):
            self.app.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def test_old_manager_hides_providers(self):
        self.app.manager_info = {'speech': {'speech_ready': True, 'quick': True}}
        self.app._sync_speech_tab()
        self.assertFalse(self.app.sp_voice_box.winfo_manager())
        self.assertEqual(self.app._speech_opts()['provider'], 'ema')
        self.assertIn('EMA Lightning hazır', self.app.sp_state_var.get())

    def test_select_openai_voice(self):
        app = self.app
        fake = mock.Mock(kind='manager')
        fake.voices = mock.Mock(return_value=CATALOG)
        with mock.patch.object(app, 'backends', return_value=[fake]):
            app.manager_info = {'speech': {'speech_ready': True, 'ema_ready': False, 'providers': PROVIDERS}}
            app._sync_speech_tab()
            self.assertTrue(app.sp_voice_box.winfo_manager())
            labels = list(app.sp_provider_cb.cget('values'))
            self.assertTrue(any('anahtar tanımlı değil' in x for x in labels))           # ElevenLabs anahtarsiz
            app.sp_provider_var.set(labels[1])                                          # OpenAI
            app._speech_provider_changed()
            self.assertTrue(self.pump(lambda: app.sp_voice_var.get().startswith('Marin')))
            self.assertEqual(app.settings['speech_provider'], 'openai')
            self.assertTrue(app.sp_instr_row.winfo_manager())
            app.sp_voice_var.set('Cedar')
            app.sp_model_var.set('TTS-1')
            app.sp_instr_var.set('Yavaş ve net oku')
            app._speech_voice_changed()
            o = app._speech_opts()
            self.assertEqual((o['provider'], o['voice'], o['model'], o['instructions'], o['job_max_chars']),
                             ('openai', 'cedar', 'tts-1', 'Yavaş ve net oku', 4000))
            self.assertTrue(app._voice_sig().startswith('openai-'))
            self.assertIn('OpenAI hazır', app.sp_state_var.get())
            b = app._manager_backend('x')
            self.assertEqual(b.speech_opts['voice'], 'cedar')
            # anahtarsiz saglayici secilemez
            with mock.patch.object(self.m.messagebox, 'showinfo') as info:
                app.sp_provider_var.set(labels[2])
                app._speech_provider_changed()
                info.assert_called_once()
            self.assertEqual(app.settings['speech_provider'], 'openai')
            # EMA'ya donus
            app.sp_provider_var.set(labels[0])
            app._speech_provider_changed()
            self.assertEqual(app._voice_sig(), 'ema')
            self.assertFalse(app.sp_instr_row.winfo_manager())

    def test_local_mode_hides_providers(self):
        app = self.app
        app.manager_info = {'speech': {'speech_ready': True, 'providers': PROVIDERS}}
        with mock.patch.object(app, 'backends', return_value=[]):
            app._sync_speech_tab()
        app.settings['speech_service'] = 'local'
        with mock.patch.object(app, '_local_backend', return_value=None):
            app._sync_speech_tab()
        self.assertFalse(app.sp_voice_box.winfo_manager())
        self.assertEqual(app._voice_sig(), 'yerel')


if __name__ == '__main__':
    unittest.main()
