"""Regression checks for model-404 handling and installed-model selection."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from organizer_core import classify, list_ollama_models, pick_ollama_model, ollama_refine


class HttpResponse(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


class OllamaTests(unittest.TestCase):
    def test_installed_models_from_api(self):
        payload = json.dumps({'models': [{'name': 'gemma3:1b'}, {'name': 'gemma3:270m'}, {'name': 'gemma3:1b'}]})
        with patch('organizer_core.request.urlopen', return_value=HttpResponse(payload.encode())):
            self.assertEqual(list_ollama_models(), ['gemma3:1b', 'gemma3:270m'])

    def test_preserves_installed_choice_and_migrates_missing_qwen(self):
        self.assertEqual(pick_ollama_model('qwen2.5:3b', ['gemma3:1b']), 'gemma3:1b')
        self.assertEqual(pick_ollama_model('qwen2.5:3b', ['gemma3:270m']), 'gemma3:270m')
        self.assertEqual(pick_ollama_model('qwen2.5:3b', ['qwen2.5:3b', 'gemma3:1b']), 'qwen2.5:3b')
        self.assertEqual(pick_ollama_model('foo:latest', []), None)

    def test_no_ollama_is_clear_error(self):
        with patch('organizer_core.request.urlopen', side_effect=URLError('refused')):
            with self.assertRaisesRegex(RuntimeError, 'Ollama yerel sunucusuna'):
                list_ollama_models()

    def test_404_includes_installed_model(self):
        with tempfile.TemporaryDirectory() as path:
            p = Path(path) / 'sample.txt'
            p.write_text('invoice')
            item = classify(p)
            missing = HTTPError('http://127.0.0.1:11434/api/generate', 404, 'Not Found', None, None)
            payload = HttpResponse(json.dumps({'models': [{'name': 'gemma3:1b'}]}).encode())
            with patch('organizer_core.request.urlopen', side_effect=[missing, payload]):
                with self.assertRaisesRegex(RuntimeError, 'gemma3:1b') as err:
                    ollama_refine(item, model='qwen2.5:3b')
                self.assertIn('qwen2.5:3b', str(err.exception))


if __name__ == '__main__':
    unittest.main()
