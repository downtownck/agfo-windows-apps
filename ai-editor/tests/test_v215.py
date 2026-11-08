"""2.15.0: OpenRouter seslendirmesi (AI Manager 17.15+): modele gore ses listesi, okuma talimati."""
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
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='agfo-215-')

import agfo_ai_client as ai  # noqa: E402

PROVIDERS = [
    {'id': 'ema', 'label': 'EMA Lightning', 'ready': True, 'job_max_chars': 60000, 'default_model': 'ema-lightning', 'default_voice': 'ema',
     'instructions': False},
    {'id': 'openai', 'label': 'OpenAI', 'ready': True, 'job_max_chars': 4000, 'default_model': 'gpt-4o-mini-tts', 'default_voice': 'marin',
     'instructions': True},
    {'id': 'openrouter', 'label': 'OpenRouter (Gemini, Grok, Kokoro…)', 'ready': True, 'job_max_chars': 4000, 'speed_min': 0.5,
     'speed_max': 2.0, 'default_model': 'google/gemini-3.8-flash-tts', 'default_voice': 'Kore', 'instructions': True,
     'voices_by_model': True},
]
CATALOG = {
    'voices': [{'id': 'Kore', 'name': 'Kore', 'description': 'Kararlı'}, {'id': 'Puck', 'name': 'Puck'},
               {'id': 'af_heart', 'name': 'Af_heart'}, {'id': 'ef_dora', 'name': 'Ef_dora', 'description': 'İspanyolca, kadın'}],
    'models': [{'id': 'google/gemini-3.8-flash-tts', 'name': 'Gemini 3.8 Flash TTS', 'recommended': True, 'voice_ids': ['Kore', 'Puck'],
                'default_voice': 'Kore', 'description': '$0.5/M girdi'},
               {'id': 'hexgrad/kokoro-82m', 'name': 'Kokoro 82M', 'voice_ids': ['af_heart', 'ef_dora'], 'default_voice': 'af_heart'}],
}


class ClientTests(unittest.TestCase):
    def test_openrouter_fields(self):
        b = ai.ManagerBackend('https://ornek.test', token='agfo_x')
        b.speech_opts = {'provider': 'openrouter', 'voice': 'Puck', 'model': 'google/gemini-3.8-flash-tts',
                         'instructions': 'Mısır Arapçasıyla oku', 'job_max_chars': 4000}
        sent = []
        b._call = lambda route, payload=None, timeout=0: sent.append((route, payload)) or {'audio_base64': 'SUQz', 'seconds': 1}
        b.speech_quick('مرحبا')
        self.assertEqual((sent[0][1]['provider'], sent[0][1]['voice'], sent[0][1]['instructions']),
                         ('openrouter', 'Puck', 'Mısır Arapçasıyla oku'))


@unittest.skipUnless(sys.platform == 'win32' or bool(os.environ.get('DISPLAY')), 'ekran gerekli')
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('agfo_ai_editor_215', str(SRC / 'agfo_ai_editor.pyw'))
        spec = importlib.util.spec_from_loader('agfo_ai_editor_215', loader)
        cls.m = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.m)

    def setUp(self):
        self.app = self.m.App(smoke=True)
        self.app.withdraw()
        self.app.settings['speech_service'] = 'site'
        self.app.sp_service_var.set('site')
        for k in ('speech_provider', 'speech_voice', 'speech_model', 'speech_instructions'):
            self.app.settings.pop(k, None)

    def tearDown(self):
        for k in ('speech_provider', 'speech_voice', 'speech_model', 'speech_instructions', 'speech_service'):
            self.app.settings.pop(k, None)
        self.m.core.save_settings(self.app.settings)
        self.app.destroy()

    def pump(self, cond, n=300):
        for _ in range(n):
            self.app.update()
            if cond():
                return True
            time.sleep(0.01)
        return False

    def test_voices_follow_model(self):
        app = self.app
        fake = mock.Mock(kind='manager')
        fake.voices = mock.Mock(return_value=CATALOG)
        with mock.patch.object(app, 'backends', return_value=[fake]):
            app.manager_info = {'speech': {'speech_ready': True, 'providers': PROVIDERS}}
            app._sync_speech_tab()
            labels = list(app.sp_provider_cb.cget('values'))
            app.sp_provider_var.set(labels[2])
            app._speech_provider_changed()
            self.assertTrue(self.pump(lambda: app.sp_voice_var.get().startswith('Kore')), app.sp_voice_var.get())
            self.assertEqual(list(app.sp_voice_cb.cget('values')), ['Kore — Kararlı', 'Puck'])
            self.assertTrue(app.sp_instr_row.winfo_manager())                    # Gemini talimat alir
            app.sp_instr_var.set('Sakin oku')
            app.sp_voice_var.set('Puck')
            app._speech_voice_changed()
            self.assertEqual(app._speech_opts()['instructions'], 'Sakin oku')
            # Kokoro'ya gec: yalniz Kokoro sesleri, Puck gecersiz -> modelin varsayilan sesi
            app.sp_model_var.set('Kokoro 82M')
            app._speech_model_changed()
            self.assertEqual(list(app.sp_voice_cb.cget('values')), ['Af_heart', 'Ef_dora — İspanyolca, kadın'])
            o = app._speech_opts()
            self.assertEqual((o['provider'], o['model'], o['voice']), ('openrouter', 'hexgrad/kokoro-82m', 'af_heart'))
            sig = app._voice_sig()
            app.sp_voice_var.set('Ef_dora — İspanyolca, kadın')
            app._speech_voice_changed()
            self.assertNotEqual(app._voice_sig(), sig)
            # OpenAI: tum sesler (modele gore suzme yok), talimat satiri acik; EMA'da kapali
            app.sp_provider_var.set(labels[1])
            app._speech_provider_changed()
            self.assertTrue(app.sp_instr_row.winfo_manager())
            app.sp_provider_var.set(labels[0])
            app._speech_provider_changed()
            self.assertFalse(app.sp_instr_row.winfo_manager())


if __name__ == '__main__':
    unittest.main()
