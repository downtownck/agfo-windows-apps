"""Small Gemma response regression scenarios; Ollama is mocked, no network needed."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from organizer_core import (
    AICategoryError, CATEGORIES, classify, ollama_refine, parse_ai_response,
)


class Response(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.close()


class CategoryParsingTests(unittest.TestCase):
    def test_numeric_output_maps_to_allowed_category(self):
        self.assertEqual(parse_ai_response('{"category_id": 3, "confidence": 0.8}'), ('Sözleşmeler', 0.8))
        self.assertEqual(parse_ai_response('{"category_id": "2", "confidence": 0.9}')[0], 'Faturalar')
        for i, category in enumerate(CATEGORIES):
            self.assertEqual(parse_ai_response(json.dumps({'category_id': i}))[0], category)

    def test_legacy_turkish_and_english_labels(self):
        cases = {'Invoices': 'Faturalar', 'fatura': 'Faturalar',
                 'Contracts': 'Sözleşmeler', 'Sözleşmeler': 'Sözleşmeler',
                 'AUDIT REPORTS': 'Denetimler', 'Documents': 'Belgeler',
                 'Kurulum Dosyaları': 'Kurulum Dosyaları', 'Yazilim': 'Yazılım',
                 'Needs review': 'İncelenecek'}
        for name, category in cases.items():
            with self.subTest(name=name):
                self.assertEqual(parse_ai_response(json.dumps({'category': name}))[0], category)

    def test_rejects_ambiguous_and_invalid_values(self):
        samples = ['{"category":"Legal Documents"}', '{"category":"General"}',
                   '{"category_id":99}', '{"category_id":-1}',
                   '{"category_id": true}', 'no json', '{"category": null}']
        for raw in samples:
            with self.subTest(raw=raw), self.assertRaises(AICategoryError):
                parse_ai_response(raw)

    def test_bad_confidence_is_safe(self):
        for confidence in ('garbage', 'NaN', None, 'Infinity'):
            self.assertEqual(parse_ai_response(json.dumps({'category_id': 2, 'confidence': confidence})),
                             ('Faturalar', 0.65))
        self.assertEqual(parse_ai_response('{"category_id": 17,"confidence":0.99}'), ('İncelenecek', 0.65))

    def test_http_request_uses_schema_and_does_not_move_file(self):
        with tempfile.TemporaryDirectory() as d:
            doc = Path(d) / 'confidential.txt'
            doc.write_text('sample document data', encoding='utf-8')
            item = classify(doc)
            old_category, old_folder, old_decision = item.category, item.folder, item.decision
            payload = json.dumps({'response': '{"category_id": 3, "confidence": 0.76}'})
            with patch('organizer_core.request.urlopen', return_value=Response(payload.encode())) as called:
                category, confidence, reason = ollama_refine(item, model='gemma3:1b')
            request_data = json.loads(called.call_args.args[0].data.decode('utf-8'))
            self.assertIn('enum', request_data['format']['properties']['category_id'])
            self.assertEqual(len(request_data['format']['properties']['category_id']['enum']), len(CATEGORIES))
            self.assertEqual(category, 'Sözleşmeler')
            self.assertEqual(confidence, 0.76)
            self.assertIn('Ollama', reason)
            self.assertTrue(doc.exists())
            self.assertEqual((item.category, item.folder, item.decision),
                             (old_category, old_folder, old_decision))

    def test_model_failure_leaves_existing_plan_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            doc = Path(d) / 'unknown.txt'
            doc.write_text('sample document data', encoding='utf-8')
            item = classify(doc)
            before = (item.category, item.folder, item.confidence, item.decision)
            payload = json.dumps({'response': '{"category":"anything goes"}'})
            with patch('organizer_core.request.urlopen', return_value=Response(payload.encode())):
                with self.assertRaisesRegex(AICategoryError, 'Mevcut öneri korundu'):
                    ollama_refine(item)
            self.assertEqual((item.category, item.folder, item.confidence, item.decision), before)
            self.assertTrue(doc.exists())


if __name__ == '__main__':
    unittest.main()
