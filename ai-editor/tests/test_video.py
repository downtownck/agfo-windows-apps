"""2.9.0: sesli cizgi roman / video (MOV): sahne plani, tarzlar, gorsel promptlari, altyazi ve ffmpeg ile cikti."""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-video-')
os.environ['LOCALAPPDATA'] = TMP

import agfo_video as V  # noqa: E402

MD = """# Başlangıç

Leo sabah erkenden limana indi. Gemiler sisin içinde bekliyordu.

Celeste onu iskelede karşıladı, elinde eski bir harita vardı.

## Yolculuk

İkisi küçük bir tekneyle açıldılar. Rüzgâr güneyden esiyordu ve dalgalar yükseliyordu.

Akşam olduğunda ufukta bir ada belirdi."""

PLAN = {'summary': 'Leo ve Celeste bir adaya yolculuk eder.', 'style': 'whatever',
        'characters': [{'name': 'Leo', 'look': 'young man, short black hair, red scarf'},
                       {'name': 'Celeste', 'look': 'woman in her 30s, grey coat, silver braid'}],
        'scenes': [{'title': 'Liman', 'start': 1, 'end': 3, 'characters': ['Leo', 'Celeste'], 'shot': 'wide',
                    'visual': 'A foggy harbour at dawn'},
                   {'title': 'Açık deniz', 'start': 5, 'end': 7, 'characters': ['Leo'], 'shot': 'close-up',
                    'visual': 'Small boat on rising waves'}]}


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.paras = V.paragraphs_from_markdown(MD)

    def test_paragraphs(self):
        self.assertGreaterEqual(len(self.paras), 5)
        self.assertTrue(any('Leo' in p for p in self.paras))

    def test_parse_plan_contiguous(self):
        pl = V.parse_plan('```json\n' + json.dumps(PLAN) + '\n```', len(self.paras), 'comic')
        sc = pl['scenes']
        self.assertEqual(sc[0]['start'], 0)
        self.assertEqual(sc[-1]['end'], len(self.paras) - 1)
        for a, b in zip(sc, sc[1:]):
            self.assertEqual(a['end'] + 1, b['start'])
        self.assertEqual([s['id'] for s in sc], ['s01', 's02'])
        self.assertEqual(sc[1]['shot'], 'close-up')
        self.assertEqual(pl['style'], V.STYLES['comic']['look'])    # hazir tarz AI'nin cumlesini ezer

    def test_auto_style_keeps_ai_choice(self):
        pl = V.parse_plan(json.dumps(dict(PLAN, style='ligne claire, flat muted colours')), len(self.paras), 'auto')
        self.assertEqual(pl['style'], 'ligne claire, flat muted colours')

    def test_bad_plan(self):
        self.assertIsNone(V.parse_plan('not json', len(self.paras)))

    def test_plan_prompt_per_style(self):
        fixed = V.plan_prompt(self.paras, style_key='cinematic')
        self.assertIn(V.STYLES['cinematic']['look'], fixed)
        self.assertIn('10-35 seconds', fixed)
        auto = V.plan_prompt(self.paras, style_key='auto')
        self.assertIn('Choose ONE art style', auto)

    def test_auto_plan_merge_split(self):
        pl = V.auto_plan(self.paras, 4.0)
        n = len(pl['scenes'])
        self.assertGreater(n, 1)
        self.assertTrue(V.merge_scene(pl, 1))
        self.assertEqual(len(pl['scenes']), n - 1)
        big = max(range(len(pl['scenes'])), key=lambda i: pl['scenes'][i]['end'] - pl['scenes'][i]['start'])
        if pl['scenes'][big]['end'] > pl['scenes'][big]['start']:
            self.assertTrue(V.split_scene(pl, big))
            self.assertEqual(len(pl['scenes']), n)

    def test_compose_prompt(self):
        proj = V.new_project(tempfile.mkdtemp(dir=TMP), 'Deneme', self.paras, 'cinematic')
        proj['plan'] = V.parse_plan(json.dumps(PLAN), len(self.paras), 'cinematic')
        p = V.compose_prompt(proj, proj['plan']['scenes'][0])
        self.assertTrue(p.startswith('cinematic film still'))
        self.assertIn('wide shot', p)
        self.assertIn('red scarf', p)
        self.assertIn('silver braid', p)
        self.assertIn('no speech bubbles', p)
        p2 = V.compose_prompt(proj, proj['plan']['scenes'][1])
        self.assertNotIn('silver braid', p2)                       # sahnede olmayan karakter eklenmez
        proj['plan']['scenes'][1]['prompt'] = 'elle yazilmis'
        self.assertEqual(V.compose_prompt(proj, proj['plan']['scenes'][1]), 'elle yazilmis')
        V.set_style(proj, 'manga')
        self.assertIn('manga', V.compose_prompt(proj, proj['plan']['scenes'][0]))

    def test_cues_srt_ass(self):
        cl = V.cues(['Bir. İki cümle burada.', 'Üçüncü paragraf.'], [4.0, 2.0], 0.5)
        self.assertEqual(cl[0][0], 0.0)
        self.assertAlmostEqual(cl[-1][1], 6.5, places=2)
        self.assertIn('-->', V.srt(cl))
        a = V.ass(cl)
        self.assertIn('PlayResX: 1920', a)
        self.assertIn('Dialogue:', a)
        for c in cl:
            self.assertLessEqual(c[2].count('\n') + c[2].count('\\N'), 1)

    def test_placeholder(self):
        from PIL import Image, ImageChops
        clean, draft = os.path.join(TMP, 'ph.png'), os.path.join(TMP, 'ph_draft.png')
        V.placeholder(clean, 1, 'cinematic', False, 'Liman', 'wide · foggy')
        V.placeholder(draft, 1, 'cinematic', True, 'Liman', 'wide · foggy')
        clean2 = os.path.join(TMP, 'ph2.png')
        V.placeholder(clean2, 1, 'cinematic', False, 'Baska baslik', 'baska tarif')
        with Image.open(clean) as a, Image.open(draft) as b, Image.open(clean2) as c:
            self.assertEqual(a.size, (1920, 1080))
            self.assertIsNotNone(ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox())   # taslakta not var
            self.assertIsNone(ImageChops.difference(a.convert('RGB'), c.convert('RGB')).getbbox())      # son urunde yazi yok

    def test_overlay_frames(self):
        comic = V.overlay_image('comic')
        self.assertEqual(comic.mode, 'RGBA')
        self.assertEqual(comic.getpixel((960, 540))[3], 0)            # orta saydam: gorsel gorunur
        self.assertEqual(comic.getpixel((5, 5))[3], 255)              # sayfa boslugu
        self.assertLess(sum(comic.getpixel((32, 540))[:3]), 100)       # siyah kare kenarligi
        cine = V.overlay_image('cinematic')
        self.assertEqual(cine.getpixel((960, 20)), (0, 0, 0, 255))     # sinema bandi
        self.assertEqual(cine.getpixel((960, 540))[3], 0)
        for k in V.STYLES:
            self.assertEqual(V.overlay_image(k).getpixel((960, 540))[3], 0, k)

    def test_preview_uses_image_under_frame(self):
        from PIL import Image
        folder = tempfile.mkdtemp(dir=TMP)
        proj = V.new_project(folder, 'Deneme', self.paras, 'comic')
        src = os.path.join(folder, 'red.png')
        Image.new('RGB', (800, 600), (220, 20, 20)).save(src)
        V.set_image(proj, 0, src)
        with Image.open(V.preview_frame(proj, 0)) as im:
            self.assertEqual(im.getpixel((960, 540)), (220, 20, 20))   # gorsel ortada
            self.assertGreater(sum(im.getpixel((5, 5))), 700)          # cerceve gorselin ustunde

    def test_project_file_detection_and_recent(self):
        folder = tempfile.mkdtemp(dir=TMP)
        V.save_project(V.new_project(folder, 'Deneme', self.paras))
        path = os.path.join(folder, V.PROJECT_FILE)
        self.assertTrue(V.is_project_file(path))
        other = os.path.join(TMP, 'proje.json')
        pathlib.Path(other).write_text('{"a": 1}', encoding='utf-8')
        self.assertFalse(V.is_project_file(other))
        st = {}
        V.remember_project(st, folder)
        V.remember_project(st, os.path.join(TMP, 'yok'))
        V.remember_project(st, folder)
        self.assertEqual(st['video_recent'][0], folder)
        self.assertEqual(V.recent_projects(st), [folder])

    def test_project_roundtrip(self):
        folder = tempfile.mkdtemp(dir=TMP)
        proj = V.new_project(folder, 'Deneme', self.paras, 'manga')
        V.save_project(proj)
        back = V.load_project(folder)
        self.assertEqual(back['style_key'], 'manga')
        self.assertEqual(len(back['paragraphs']), len(self.paras))


class FilterSyntaxTests(unittest.TestCase):
    """2.9.1: yeni ffmpeg '-/filter_complex dosya' ister, eski surum -filter_complex_script'e duser."""
    def _render(self, fail_new):
        paras = V.paragraphs_from_markdown(MD)
        folder = tempfile.mkdtemp(dir=TMP)
        proj = V.new_project(folder, 'Deneme', paras, 'comic')
        calls = []

        def run(args, cwd=None, timeout=None):
            calls.append(args)
            if '-/filter_complex' in args and fail_new:
                raise V.VideoError("ffmpeg hatası:\nUnrecognized option '/filter_complex'.\n"
                                   'Error splitting the argument list: Option not found')
            return None
        with mock.patch.object(V, '_run', run), mock.patch.object(V, 'duration', return_value=1.0):
            V.render(proj, lambda t: b'ID3', 'ffmpeg', 'ffprobe')
        return [c for c in calls if 'filter.txt' in c]

    def test_new_syntax_first(self):
        calls = self._render(False)
        self.assertEqual(len(calls), 1)
        self.assertIn('-/filter_complex', calls[0])
        self.assertNotIn('-filter_complex_script', calls[0])

    def test_old_ffmpeg_fallback(self):
        calls = self._render(True)
        self.assertEqual(len(calls), 2)
        self.assertIn('-filter_complex_script', calls[1])


FF = V.find_ffmpeg()


@unittest.skipUnless(FF and FF[0] and FF[1], 'ffmpeg gerekli')
class RenderTests(unittest.TestCase):
    def test_render_mov(self):
        ff, fp = FF
        paras = V.paragraphs_from_markdown(MD)
        folder = tempfile.mkdtemp(dir=TMP)
        proj = V.new_project(folder, 'Deneme Video', paras, 'comic')
        proj['plan'] = V.parse_plan(json.dumps(PLAN), len(paras), 'comic')
        tmp = os.path.join(folder, 'tone.mp3')

        def speak(text):
            subprocess.run([ff, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=%.2f' % max(0.6, len(text) / 30),
                            '-c:a', 'libmp3lame', '-q:a', '7', tmp], capture_output=True, check=True)
            return pathlib.Path(tmp).read_bytes()
        mov = V.render(proj, speak, ff, fp)
        self.assertTrue(mov.endswith('.mov') and os.path.getsize(mov) > 10000)
        info = subprocess.run([fp, '-v', 'error', '-show_entries', 'stream=codec_type,width,height', '-of', 'json', mov],
                              capture_output=True, text=True).stdout
        streams = json.loads(info)['streams']
        self.assertIn('audio', [s['codec_type'] for s in streams])
        v = [s for s in streams if s['codec_type'] == 'video'][0]
        self.assertEqual((v['width'], v['height']), (1920, 1080))
        self.assertTrue(os.path.exists(os.path.join(folder, 'subs.srt')))
        self.assertGreater(V.duration(fp, mov), 3)
        frame = os.path.join(folder, 'f.png')
        subprocess.run([ff, '-y', '-ss', '1', '-i', mov, '-frames:v', '1', frame], capture_output=True, check=True)
        from PIL import Image
        with Image.open(frame) as im:
            self.assertGreater(sum(im.convert('RGB').getpixel((6, 540))), 650)   # cizgi roman cercevesi videoda


def _display():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(_display(), 'ekran gerekli')
class VideoGuiTests(unittest.TestCase):
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
        self.app.geometry('1300x850')
        self.app.update()

    def tearDown(self):
        self.app.destroy()

    def pump(self, until=lambda: False, n=300):
        for _ in range(n):
            self.app.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def test_window_plan_and_style(self):
        self.app.new_doc(text=MD.replace('# ', '').replace('#', ''), title='Hikaye.md')
        with mock.patch.object(self.app, '_speech_backend', return_value=object()):
            win = self.app.open_video_project()
        self.assertIsNotNone(win)
        self.app.update()
        n_paras = len(win.proj['paragraphs'])

        def run(backends, fn, *args):
            return {'text': json.dumps(PLAN), 'via': 'Test', 'model': 'test'}
        win.preset_var.set(V.STYLES['cinematic']['label'])
        win.change_style()
        self.assertEqual(win.proj['style_key'], 'cinematic')
        with mock.patch.object(self.m.ai, 'run_with_fallback', run), mock.patch.object(self.app, 'backends', return_value=[]):
            win.make_plan()
            self.assertTrue(self.pump(lambda: win.proj.get('planned_by') == 'ai'))
        self.assertEqual(len(win.proj['plan']['scenes']), 2)
        self.assertEqual(win.proj['plan']['scenes'][-1]['end'], n_paras - 1)
        win.tree.selection_set(win.tree.get_children()[0])
        self.pump(n=20)
        self.assertIn('cinematic film still', win.prompt_box.get('1.0', 'end'))
        win.destroy()

    def test_open_project_file_without_document(self):
        folder = tempfile.mkdtemp(dir=TMP)
        paras = V.paragraphs_from_markdown(MD)
        proj = V.new_project(folder, 'Kayitli', paras, 'manga')
        proj['plan'] = V.parse_plan(json.dumps(PLAN), len(paras), 'manga')
        proj['planned_by'] = 'ai'
        V.save_project(proj)
        n_docs = len(self.app.docs)
        win = self.app.open_path(os.path.join(folder, V.PROJECT_FILE))     # Ac... ile de ayni yol
        self.app.update()
        self.assertIsNotNone(win)
        self.assertEqual(len(self.app.docs), n_docs)                          # belge acilmadi
        self.assertEqual(win.proj['style_key'], 'manga')
        self.assertEqual(win.proj['plan']['characters'][0]['name'], 'Leo')
        self.assertIn(folder, V.recent_projects(self.app.settings))
        self.assertTrue(win.preview(0).endswith('.png'))
        win.draft_var.set(True)
        win._draft_changed()
        self.assertTrue(V.load_project(folder)['draft'])
        win.destroy()


if __name__ == '__main__':
    unittest.main()
