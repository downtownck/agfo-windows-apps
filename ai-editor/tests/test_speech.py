# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.5 seslendirme testleri (ag gerektirmez).  python tests/test_speech.py
GUI testleri ekran yoksa atlanir (Linux'ta xvfb-run ile calisir)."""
import base64
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-editor-speech-')
os.environ['LOCALAPPDATA'] = TMP

import agfo_ai_client as ai  # noqa: E402
import agfo_speech as sp  # noqa: E402
import agfo_readaloud as ra  # noqa: E402


class MarkdownToSpeechTests(unittest.TestCase):
    def test_structure_becomes_sentences(self):
        md = ('# Gıda Güvenliği Kültürü\n\nFabrika **%92** puan aldı; [rapor](https://x.test) ![resim:1] hazır.\n\n'
              '- Alerjen yönetimi\n- İzlenebilirlik.\n1. Kalibrasyon\n\n| Madde | Durum |\n|---|---|\n| 4.2.1 | Uygun |\n\n> Alıntı')
        out = sp.markdown_to_speech(md)
        self.assertEqual(out.split('\n\n')[0], 'Gıda Güvenliği Kültürü.')
        self.assertIn('Fabrika %92 puan aldı; rapor hazır.', out)
        self.assertIn('Alerjen yönetimi.\nİzlenebilirlik.\nKalibrasyon.', out)
        self.assertIn('Madde, Durum.\n4.2.1, Uygun.', out)
        self.assertTrue(out.endswith('Alıntı.'))
        self.assertNotIn('**', out)
        self.assertNotIn('|', out)
        self.assertNotIn('resim', out)

    def test_plain_paragraphs_untouched(self):
        txt = 'Birinci paragraf\nikinci satır\n\n\n\nÜçüncü'
        self.assertEqual(sp.markdown_to_speech(txt), 'Birinci paragraf\nikinci satır\n\nÜçüncü')

    def test_markdown_escapes_removed(self):
        self.assertEqual(sp.markdown_to_speech('Madde 4\\.2\\.1 ve \\#etiket \\*not\\*'), 'Madde 4.2.1 ve #etiket *not*')

    def test_heading_with_quote_keeps_single_terminal(self):
        self.assertEqual(sp.markdown_to_speech('## “Neden?”'), '“Neden?”')


class SplitTests(unittest.TestCase):
    def test_short_text_one_part(self):
        self.assertEqual(sp.split_parts('Kısa metin.'), ['Kısa metin.'])
        self.assertEqual(sp.split_parts('   '), [])

    def test_long_text_split_on_paragraphs(self):
        para = 'Cümle burada bitiyor. ' * 300
        text = '\n\n'.join([para.strip()] * 12)
        parts = sp.split_parts(text, 20000)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= 20000 for p in parts))
        self.assertEqual(sum(p.count('\n\n') + 1 for p in parts), 12)

    def test_oversized_paragraph_split_on_sentences(self):
        parts = sp.split_parts('Uzun bir cümle. ' * 3000, 10000)
        self.assertTrue(all(len(p) <= 10000 for p in parts))
        self.assertTrue(all(p.endswith('.') for p in parts))


class FakeBackend:
    kind = 'manager'

    def __init__(self, statuses=('processing', 'complete'), fail=False):
        self.statuses = list(statuses)
        self.fail = fail
        self.submitted = []
        self.downloads = []

    def speech_submit(self, text, **kw):
        self.submitted.append((text, kw))
        return {'job': 'job-%d' % len(self.submitted), 'status': 'queued'}

    def speech_status(self, job):
        st = self.statuses.pop(0) if self.statuses else 'complete'
        if st == 'complete':
            self.statuses = ['processing', 'complete']
        if self.fail:
            return {'job': job, 'status': 'failed', 'error': 'EMA servisine ulaşılamadı'}
        return {'job': job, 'status': st, 'duration_ms': 1500,
                'script': {'status': 'done', 'chunks': 1, 'kept_original': 0, 'model': 'openai|m'}}

    def speech_download(self, job, dest):
        data = ('MP3-%s|' % job).encode()
        with open(dest, 'wb') as fh:
            fh.write(data)
        self.downloads.append(job)
        return len(data)


class NarrateTests(unittest.TestCase):
    def test_single_part(self):
        b = FakeBackend()
        dest = os.path.join(TMP, 'tek.mp3')
        msgs = []
        res = sp.narrate(b, 'Merhaba dünya.', dest, reading_script=True, speed=1.1, progress=msgs.append, sleep=lambda s: None)
        self.assertEqual(pathlib.Path(dest).read_bytes(), b'MP3-job-1|')
        self.assertEqual(res['parts'], 1)
        self.assertEqual(res['duration_ms'], 1500)
        self.assertTrue(b.submitted[0][1]['reading_script'])
        self.assertEqual(b.submitted[0][1]['speed'], 1.1)
        self.assertTrue(any('hazırlanıyor' in m for m in msgs))
        self.assertFalse([f for f in os.listdir(TMP) if f.startswith('tek.mp3.')])   # gecici parca kalmaz

    def test_long_text_parts_concatenated_in_order(self):
        b = FakeBackend()
        dest = os.path.join(TMP, 'uzun.mp3')
        text = '\n\n'.join(['Paragraf metni burada. ' * 1500] * 4)
        with mock.patch.object(sp, 'PART_LIMIT', 40000):
            res = sp.narrate(b, text, dest, sleep=lambda s: None)
        self.assertGreater(res['parts'], 1)
        self.assertEqual(pathlib.Path(dest).read_bytes(), b''.join(('MP3-job-%d|' % i).encode() for i in range(1, res['parts'] + 1)))
        self.assertEqual(len(set(kw['request_id'] for _t, kw in b.submitted)), res['parts'])

    def test_failure_reports_server_error_and_leaves_no_file(self):
        dest = os.path.join(TMP, 'hata.mp3')
        with self.assertRaises(RuntimeError) as cm:
            sp.narrate(FakeBackend(fail=True), 'Metin.', dest, sleep=lambda s: None)
        self.assertIn('EMA servisine ulaşılamadı', str(cm.exception))
        self.assertFalse(os.path.exists(dest))

    def test_cancel(self):
        with self.assertRaises(sp.Cancelled):
            sp.narrate(FakeBackend(), 'Metin.', os.path.join(TMP, 'iptal.mp3'), cancel=lambda: True, sleep=lambda s: None)

    def test_script_note(self):
        self.assertIn('okuma metni: 2 bölüm', sp.script_note([{'status': 'done', 'chunks': 2, 'model': 'x'}]))
        self.assertIn('özgün okundu', sp.script_note([{'status': 'done', 'chunks': 2, 'kept_original': 1, 'model': 'x'}]))
        self.assertIn('olduğu gibi okundu', sp.script_note([{'status': 'skipped', 'reason': 'model yok'}]))
        self.assertEqual(sp.script_note([]), '')


class PlanTests(unittest.TestCase):
    def test_headings_define_sections_and_long_ones_are_balanced(self):
        md = ('# Kitap\n\nÖnsöz.\n\n## Bir\n\n' + '\n\n'.join(['Uzun paragraf metni burada. ' * 40] * 12) +
              '\n\n## İki\n\n' + 'İkinci bölüm metni. ' * 40 + '\n\n## Son\n\nKısa.')
        secs = sp.plan_sections(md, max_chars=5000)
        titles = [s['title'] for s in secs]
        self.assertTrue(titles[0].startswith('Kitap – Bir ('), titles)
        self.assertIn('İki', titles[-1])                     # kisa "Son" bir onceki bolume katildi
        bir = [s for s in secs if 'Bir (' in s['title']]
        self.assertGreater(len(bir), 1)
        self.assertTrue(all(s['chars'] <= 5000 for s in secs))
        sizes = [s['chars'] for s in bir]
        self.assertLess(max(sizes) - min(sizes), 2500)        # dengeli parcalar
        self.assertTrue(all(s['seconds'] > 0 for s in secs))

    def test_no_headings(self):
        secs = sp.plan_sections('\n\n'.join(['Paragraf metni burada. ' * 30] * 30), max_chars=6000)
        self.assertEqual([s['title'] for s in secs][:2], ['Bölüm 1', 'Bölüm 2'])
        self.assertEqual(sp.plan_sections('Kısa metin.')[0]['text'], 'Kısa metin.')

    def test_subheadings_used_before_paragraphs(self):
        md = '## Ana\n\n### Alt A\n\n' + 'A metni. ' * 300 + '\n\n### Alt B\n\n' + 'B metni. ' * 300 + '\n\n## Diğer\n\n' + 'Diğer. ' * 80
        secs = sp.plan_sections(md, max_chars=3500)
        ana = [s for s in secs if s['title'].startswith('Ana (')]
        self.assertEqual(len(ana), 2)
        self.assertTrue(ana[1]['text'].startswith('Alt B.'))

    def test_safe_name(self):
        self.assertEqual(sp.safe_name('Giriş: A/B? "C"', 3), '03 - Giriş A B C.mp3')

    def test_narrate_sections_files_and_failure_isolated(self):
        b = FakeBackend()
        calls = {'n': 0}
        orig = b.speech_status

        def status(job):
            calls['n'] += 1
            if job == 'job-2':
                return {'job': job, 'status': 'failed', 'error': 'sunucu hatası'}
            return orig(job)
        b.speech_status = status
        folder = os.path.join(TMP, 'parca')
        states = []
        res = sp.narrate_sections(b, [{'title': 'Bir', 'text': 'Bir.'}, {'title': 'İki', 'text': 'İki.'}, {'title': 'Üç', 'text': 'Üç.'}],
                                  folder, mode='files', status=lambda i, st, info: states.append((i, st)), sleep=lambda s: None, poll=0)
        self.assertEqual(sorted(os.listdir(folder)), ['00 - çalma listesi.m3u', '01 - Bir.mp3', '03 - Üç.mp3'])
        self.assertEqual(res['failed'][0][0], 1)
        self.assertIn((1, 'hata'), states)
        self.assertIn((2, 'tamam'), states)
        m3u = pathlib.Path(folder, '00 - çalma listesi.m3u').read_text(encoding='utf-8')
        self.assertEqual(m3u, '#EXTM3U\n01 - Bir.mp3\n03 - Üç.mp3\n')

    def test_narrate_sections_single_file(self):
        dest = os.path.join(TMP, 'tek-bolumlu.mp3')
        res = sp.narrate_sections(FakeBackend(), [{'title': 'A', 'text': 'A.'}, {'title': 'B', 'text': 'B.'}], dest,
                                  sleep=lambda s: None, poll=0)
        self.assertEqual(res['paths'], [dest])
        self.assertEqual(pathlib.Path(dest).read_bytes(), b'MP3-job-1|MP3-job-2|')
        self.assertFalse([f for f in os.listdir(TMP) if f.startswith('.agfo-bolum')])


class ReadAloudTests(unittest.TestCase):
    def test_group_paragraphs(self):
        lines = ['Başlık', '', 'a1', 'a2', '', '', 'b', '']
        self.assertEqual(ra.group_paragraphs(lines, rich=False), [(0, 0), (2, 3), (6, 6)])
        self.assertEqual(ra.group_paragraphs(lines, rich=True), [(0, 0), (2, 2), (3, 3), (6, 6)])

    def test_split_piece(self):
        parts = ra.split_piece('Cümle bir. ' * 400, 500)
        self.assertTrue(all(len(p) <= 500 for p in parts))
        self.assertEqual(''.join(parts).replace(' ', ''), ('Cümle bir. ' * 400).replace(' ', ''))
        self.assertTrue(all(len(p) <= 100 for p in ra.split_piece('x' * 450, 100)))

    def _session(self, fetch, segs, clock):
        events = []
        player = ra.TimerPlayer(clock=lambda: clock[0])
        ses = ra.ReadAloud(segs, fetch, os.path.join(TMP, 'ra-%d' % len(os.listdir(TMP))), player=player,
                           on_segment=lambda i: events.append(('seg', i)), on_state=lambda st, m='': events.append((st, m)))
        return ses, player, events

    def _run(self, ses, clock, step=0.5, n=200):
        import time as _t
        for _ in range(n):
            ses.tick()
            if ses.done:
                return
            clock[0] += step
            _t.sleep(0.005)

    def test_plays_in_order_and_prefetches_ahead(self):
        clock = [0.0]
        asked = []

        def fetch(text):
            asked.append(text)
            return b'ID3' + text.encode(), 1.0
        segs = [{'id': 'p1', 'texts': ['a', 'b']}, {'id': 'p2', 'texts': ['c']}, {'id': 'p3', 'texts': ['d']}]
        ses, player, events = self._session(fetch, segs, clock)
        ses.start()
        self._run(ses, clock)
        self.assertEqual(asked, ['a', 'b', 'c', 'd'])
        self.assertEqual([e[1] for e in events if e[0] == 'seg'], ['p1', 'p2', 'p3'])   # paragraf basina bir vurgu
        self.assertEqual(len(player.played), 4)
        self.assertEqual(events[-1][0], 'bitti')

    def test_fetch_error_ends_with_message(self):
        clock = [0.0]

        def fetch(text):
            if text == 'b':
                raise RuntimeError('EMA ulaşılamadı')
            return b'ID3', 0.5
        ses, player, events = self._session(fetch, [{'id': 1, 'texts': ['a']}, {'id': 2, 'texts': ['b']}], clock)
        ses.start()
        self._run(ses, clock)
        self.assertEqual(events[-1], ('hata', 'EMA ulaşılamadı'))
        self.assertEqual(len(player.played), 1)

    def test_cache_reused(self):
        clock = [0.0]
        n = {'c': 0}

        def fetch(text):
            n['c'] += 1
            return b'ID3', 0.2
        cache = os.path.join(TMP, 'ra-cache')
        for _ in range(2):
            ses = ra.ReadAloud([{'id': 1, 'texts': ['aynı metin']}], fetch, cache, player=ra.TimerPlayer(clock=lambda: clock[0]))
            ses.start()
            self._run(ses, clock)
        self.assertEqual(n['c'], 1)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def req(url, method='GET', headers=None, payload=None, timeout=0, opener=None):
            self.calls.append((url, method, headers, payload))
            if url.endswith('/editor/lexicon/listen'):
                return 200, json.dumps({'mime': 'audio/mpeg', 'audio_base64': base64.b64encode(b'ID3sound').decode()}).encode(), {}
            if '/editor/speech/' in url:
                return 200, b'{"job":"j1","status":"processing"}', {}
            return 200, b'{"job":"j1","status":"queued","ok":true}', {}
        self.b = ai.ManagerBackend('https://site.test', token='agfoed.x.y', request=req)

    def test_submit_payload_and_auth(self):
        self.b.speech_submit('Metin', reading_script=False, script_ready=True, speed=1.234, paragraph_pause_ms=900, request_id='r1')
        url, method, headers, payload = self.calls[-1]
        self.assertTrue(url.endswith('/wp-json/agfo-ai/v1/editor/speech'))
        self.assertEqual(method, 'POST')
        self.assertEqual(headers, {'X-AGFO-Editor-Token': 'agfoed.x.y'})
        self.assertEqual(payload['text'], 'Metin')
        self.assertFalse(payload['reading_script'])
        self.assertTrue(payload['script_ready'])
        self.assertEqual(payload['speed'], 1.23)
        self.assertEqual(payload['paragraph_pause_ms'], 900)
        self.assertNotIn('pause_ms', payload)

    def test_speech_quick(self):
        orig = self.b._request

        def req(url, method='GET', headers=None, payload=None, timeout=0, opener=None):
            if url.endswith('/editor/speech-quick'):
                self.calls.append((url, method, headers, payload))
                return 200, json.dumps({'audio_base64': base64.b64encode(b'ID3q').decode(), 'seconds': 1.5}).encode(), {}
            return orig(url, method, headers, payload, timeout, opener)
        self.b._request = req
        audio, secs = self.b.speech_quick('Metin.', reading_script=True, speed=1.1, script_ready=False)
        self.assertEqual((audio, secs), (b'ID3q', 1.5))
        self.assertEqual(self.calls[-1][3]['reading_script'], True)
        self.assertEqual(self.calls[-1][3]['speed'], 1.1)

    def test_status_and_lexicon_routes(self):
        self.assertEqual(self.b.speech_status('j1')['status'], 'processing')
        self.assertTrue(self.calls[-1][0].endswith('/editor/speech/j1'))
        self.assertEqual(self.calls[-1][1], 'GET')
        self.b.lexicon_change('save', 'HACCP', 'hasip')
        self.assertEqual(self.calls[-1][3], {'op': 'save', 'word': 'HACCP', 'reading': 'hasip'})
        self.assertEqual(self.b.lexicon_listen('hasip'), b'ID3sound')


def _gui_available():
    try:
        import tkinter
        r = tkinter.Tk()
        r.destroy()
        return True
    except Exception:
        return False


@unittest.skipUnless(_gui_available(), 'ekran yok')
class SpeechGuiTests(unittest.TestCase):
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
        self.app.withdraw()
        self.app.settings['speech_service'] = 'site'      # 1.7: bu testler sitedeki AI Manager yolunu dener
        self.app._test_local_cfg = None
        self.backend = FakeBackend()
        self.backend.speech_script = lambda text: {'text': text.replace('Chicago', 'Şikago'), 'chunks': 1, 'rewritten': 1,
                                                   'kept_original': 0, 'model': 'openai|m'}
        self.backend.lexicon_list = lambda: {'entries': [{'word': 'HACCP', 'reading': 'hasip', 'source': 'base'},
                                                         {'word': 'Kaya Gıda', 'reading': 'Kaya Gıda', 'source': 'added'}],
                                             'active': 2, 'can_edit': True}
        self.changes = []
        self.backend.lexicon_change = lambda op, w, r='': self.changes.append((op, w, r)) or {'ok': True}
        self.backend.lexicon_listen = lambda r: b'ID3'
        self.p = mock.patch.object(self.m.App, 'backends', lambda _self: [self.backend])
        self.p.start()
        self.p_poll = mock.patch.object(self.m.speech, 'POLL_SECONDS', 0.01)   # yavas CI'da da hizli
        self.p_poll.start()

    def tearDown(self):
        self.p.stop()
        self.p_poll.stop()
        for w in list(self.app.winfo_children()):
            if isinstance(w, self.m.tk.Toplevel):
                w.destroy()
        self.app.destroy()

    def pump(self, until, n=3000):
        import time
        for _ in range(n):
            self.app.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def test_tab_and_info_sync(self):
        tabs = [self.app.ai_nb.tab(t, 'text') for t in self.app.ai_nb.tabs()]
        self.assertIn('Ses', tabs)
        self.app.manager_info = {'speech': {'speech_ready': True, 'reading_script_default': True}}
        self.app._sync_speech_tab()
        self.assertIn('hazır', self.app.sp_state_var.get())
        self.app.manager_info = {'text_ready': True}
        self.app._sync_speech_tab()
        self.assertIn('17.12.0', self.app.sp_state_var.get())

    def test_preview_opens_script_tab_and_narrates_it_as_ready(self):
        d = self.app.cur()
        d.text.insert('1.0', 'Chicago fabrikası denetlendi.')
        self.app.scope_var.set('all')
        n0 = len(self.app.docs)
        self.app.preview_reading_script()
        self.assertTrue(self.pump(lambda: len(self.app.docs) > n0))
        sd = self.app.cur()
        self.assertTrue(sd.speech_script)
        self.assertIn('Şikago', sd.text.get('1.0', 'end-1c'))
        dest = os.path.join(TMP, 'gui.mp3')
        self.app._test_speech_path = dest
        win = self.app.narrate_current()
        win.mode.set('single')
        win.start()
        self.assertTrue(self.pump(lambda: os.path.exists(dest) and self.app.sp_result_var.get()))
        _text, kw = self.backend.submitted[-1]
        self.assertTrue(kw['script_ready'])
        self.assertFalse(kw['reading_script'])
        self.assertIn('1 dosya', self.app.sp_result_var.get())
        self.assertEqual(str(self.app.sp_play_btn['state']), 'normal')

    def test_narrate_original_uses_reading_script_flag(self):
        self.app.new_doc(text='# Başlık\n\nMetin burada.')
        self.app.scope_var.set('all')
        self.app.sp_script_var.set(True)
        dest = os.path.join(TMP, 'gui2.mp3')
        self.app._test_speech_path = dest
        win = self.app.narrate_current()
        win.mode.set('single')
        win.start()
        self.assertTrue(self.pump(lambda: os.path.exists(dest)))
        text, kw = self.backend.submitted[-1]
        self.assertTrue(kw['reading_script'])
        self.assertFalse(kw['script_ready'])
        self.assertIn('Başlık.', text)
        self.assertNotIn('#', text)

    def test_export_window_plans_sections_and_writes_files(self):
        md = ('# Rehber\n\nKısa giriş.\n\n## Alerjen Yönetimi\n\n' + 'Alerjen metni burada anlatılıyor. ' * 30 +
              '\n\n## İzlenebilirlik\n\n' + 'İzlenebilirlik metni burada. ' * 30 + '\n\n## Sonuç\n\n' + 'Sonuç bölümü uzun bir paragraf. ' * 20)
        self.app.new_doc(text=md, title='Rapor.docx')
        self.app.scope_var.set('all')
        win = self.app.narrate_current()
        titles = [s['title'] for s in win.sections]
        self.assertEqual(titles, ['Rehber – Alerjen Yönetimi', 'İzlenebilirlik', 'Sonuç'])
        self.assertEqual(win.tree.set('0', 'on'), '☑')
        win._toggle('1')                                  # Izlenebilirlik cikarilir
        self.assertEqual(win.tree.set('1', 'on'), '☐')
        self.assertIn('2 / 3 bölüm', win.total.cget('text'))
        folder = os.path.join(TMP, 'bolumler')
        self.app._test_speech_path = folder
        win.mode.set('files')
        win.start()
        self.assertTrue(self.pump(lambda: not win.running and win.msg.get().startswith('✓')), win.msg.get())
        names = sorted(os.listdir(folder))
        self.assertEqual(names, ['00 - çalma listesi.m3u', '01 - Rehber – Alerjen Yönetimi.mp3', '02 - Sonuç.mp3'])
        self.assertTrue(win.tree.set('0', 'state').startswith('✓'))
        self.assertEqual(win.tree.set('1', 'state'), '—')
        self.assertEqual(len(self.backend.submitted), 2)
        self.assertIn('Alerjen Yönetimi.', self.backend.submitted[0][0])

    def test_read_aloud_highlights_paragraphs_in_order(self):
        player = ra.TimerPlayer()
        self.app._test_player = player
        fetched = []

        def quick(text, **kw):
            fetched.append((text, kw))
            return b'ID3' + text.encode()[:8], 0.05
        self.backend.speech_quick = quick
        self.app.manager_info = {'speech': {'speech_ready': True, 'quick': True}}
        d = self.app.new_doc(text='# Başlık\n\nBirinci paragraf.\n\nİkinci paragraf.\n\nÜçüncü paragraf.')
        d.text.mark_set('insert', d.text.search('Birinci', '1.0'))   # imlec birinci paragrafta: baslik atlanir
        seen = []
        orig = self.app._ra_segment

        def spy(i):
            orig(i)
            r = d.text.tag_ranges('readaloud')
            seen.append(d.text.get(r[0], r[1]) if r else '')
        self.app._ra_segment = spy
        self.app.read_aloud()
        self.assertTrue(self.pump(lambda: self.app.ra_session.done))
        self.assertEqual(seen, ['Birinci paragraf.', 'İkinci paragraf.', 'Üçüncü paragraf.'])
        self.assertEqual([t for t, _k in fetched], ['Birinci paragraf.', 'İkinci paragraf.', 'Üçüncü paragraf.'])
        self.assertEqual(len(player.played), 3)
        self.assertEqual(self.app.ra_state_var.get(), 'Okuma bitti.')
        self.assertEqual(d.text.tag_ranges('readaloud'), ())
        self.assertEqual(str(self.app.ra_stop_btn['state']), 'disabled')

    def test_read_aloud_pause_and_stop(self):
        player = ra.TimerPlayer()
        self.app._test_player = player
        self.backend.speech_quick = lambda text, **kw: (b'ID3', 5.0)
        self.app.manager_info = {'speech': {'speech_ready': True, 'quick': True}}
        d = self.app.new_doc(text='Bir.\n\nİki.')
        d.text.mark_set('insert', '1.0')
        self.app.read_aloud()
        self.assertTrue(self.pump(lambda: len(player.played) == 1))
        self.app.read_aloud_pause()
        self.assertEqual(self.app.ra_state_var.get(), 'Duraklatıldı')
        self.assertIsNotNone(player.paused_left)
        self.app.read_aloud()                             # F9 = surdur
        self.assertIsNone(player.paused_left)
        self.app.read_aloud_stop()
        self.assertTrue(self.app.ra_session.done)
        self.assertEqual(self.app.ra_state_var.get(), 'Okuma durduruldu.')
        self.assertEqual(len(player.played), 1)

    def test_read_aloud_needs_new_manager(self):
        self.app.manager_info = {'speech': {'speech_ready': True}}     # 17.12: quick yok
        with mock.patch.object(self.m.messagebox, 'showinfo') as info:
            self.app.read_aloud()
        self.assertIn('17.13.0', info.call_args[0][1])

    def test_lexicon_window_from_selection(self):
        d = self.app.cur()
        d.text.insert('1.0', 'HACCP planı')
        d.text.tag_add('sel', '1.0', '1.5')
        self.app.add_selection_to_lexicon()
        win = self.app.lexicon_win
        self.assertTrue(self.pump(lambda: win.tree.get_children()))
        self.assertEqual(win.word.get(), 'HACCP')
        self.assertEqual(win.reading.get(), 'hasip')            # mevcut okunus forma gelir
        self.assertEqual(len(win.tree.get_children()), 1)        # arama kelimeye gore suzer
        win.reading.set('hasip deneme')
        win.save()
        self.assertTrue(self.pump(lambda: self.changes))
        self.assertEqual(self.changes[-1], ('save', 'HACCP', 'hasip deneme'))
        win.delete()
        self.assertTrue(self.pump(lambda: len(self.changes) > 1))
        self.assertEqual(self.changes[-1][0], 'delete')
        win.listen()
        self.assertTrue(self.pump(lambda: getattr(win, 'last_listen', '')))
        self.assertEqual(pathlib.Path(win.last_listen).read_bytes(), b'ID3')


if __name__ == '__main__':
    unittest.main()
