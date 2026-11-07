# -*- coding: utf-8 -*-
"""AGFO AI Editor 2.9 - seslendirmeden video (MOV, 16:9, altyazi goruntuye yakili).

Akis:
  1. Metin paragraflara ayrilir (seslendirmedeki temizlikle: basliklar cumle olur, bicim isaretleri duser).
  2. AI once kisa bir ozet, karakter kartlari ve sahne plani cikarir; kac gorsel (sahne) gerektigine AI karar verir.
     Her sahne ardisik paragraflari kapsar. AI yoksa ya da yanit bozuksa plan sozcuk sayisina gore kendiliginden kurulur.
  3. Her sahnenin bir gorseli olur: kullanicinin sectigi gorsel ya da sahne metnini gosteren yer tutucu kart.
  4. Ses paragraf paragraf uretilir ve suresi olculur; altyazi cumle cumle, ses ile birebir zamanlanir.
  5. ffmpeg: gorseller sahne suresince hafif yaklasir (Ken Burns), altyazi goruntuye yakilir, H.264 + AAC .mov.

Proje bir klasordur: proje.json, audio/, images/, placeholders/, subs.srt, subs.ass, <ad>.mov.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile

W, H, FPS = 1920, 1080, 25
WORDS_PER_SEC = 2.4                 # Turkce anlatim icin kaba tahmin (plan suresi gosterimi)
MAX_SCENES = 80
DEFAULT_STYLE = 'Graphic novel comic art, confident ink outlines, flat colours with soft shading, cinematic lighting'  # yedek
PROJECT_FILE = 'proje.json'
FFMPEG_ZIP = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
IS_WIN = sys.platform == 'win32'
CREATE_NO_WINDOW = 0x08000000


class VideoError(Exception):
    pass


class Cancelled(VideoError):
    pass


# ----------------------------------------------------------------------------- paragraflar
def paragraphs_from_markdown(md: str) -> list:
    """Seslendirilecek ve altyazida gorunecek paragraflar (bos olmayan, temiz metin)."""
    import agfo_speech as sp
    text = sp.markdown_to_speech(md or '')
    return [re.sub(r'\s+', ' ', p).strip() for p in re.split(r'\n\s*\n', text) if p.strip()]


def words(text: str) -> int:
    return len(re.findall(r'\w+', text or ''))


def est_seconds(paras: list, start: int, end: int) -> float:
    return sum(words(p) for p in paras[start:end + 1]) / WORDS_PER_SEC


# ----------------------------------------------------------------------------- gorsel tarzlari
# look: goruntu promptunun tarz kismi (Ingilizce). plan: AI'nin kurguyu bu tarza gore yapmasi. pace: sahne suresi hedefi (sn).
# zoom: Ken Burns yaklasma orani. 'auto': tarzi metne gore AI secer.
STYLES = {
    'comic': {'label': 'Çizgi roman', 'pace': (6, 20), 'zoom': 0.05,
              'look': ('comic book panel, bold clean ink line art, flat cel colouring with halftone dot shading, dynamic '
                       'composition, strong silhouettes, expressive faces, thick black panel border'),
              'plan': ('Think in comic panels: one strong panel per story beat; vary panel framing (establishing wide panel, '
                       'medium, close-up on faces and hands, low and high angles); show the key action or emotion of each beat.')},
    'cinematic': {'label': 'Sinematik', 'pace': (10, 35), 'zoom': 0.08,
                  'look': ('cinematic film still, anamorphic widescreen composition, dramatic motivated lighting, shallow depth '
                           'of field, subtle film grain, rich colour grade, highly detailed'),
                  'plan': ('Plan it like a film: each scene is a shot with a clear shot size and camera angle (wide establishing, '
                           'medium, close-up, over-the-shoulder, tracking); mind lighting and time of day.')},
    'manga': {'label': 'Manga', 'pace': (6, 18), 'zoom': 0.05,
              'look': ('black and white manga panel, crisp ink lines, screentone shading, speed lines for motion, expressive '
                       'eyes, dramatic framing'),
              'plan': 'One manga panel per beat: dramatic angles, close-ups on emotion, speed lines for action.'},
    'graphic_novel': {'label': 'Grafik roman (noir)', 'pace': (8, 25), 'zoom': 0.06,
                      'look': ('graphic novel illustration, heavy chiaroscuro ink, limited muted palette with one accent colour, '
                               'gritty texture, moody noir atmosphere, painted comic art'),
                      'plan': 'Moody graphic novel: atmospheric establishing panels, tight close-ups for tension.'},
    'watercolor': {'label': 'Suluboya illüstrasyon', 'pace': (12, 35), 'zoom': 0.06,
                   'look': ('storybook watercolour illustration, soft washes and visible paper texture, gentle ink outlines, '
                            'warm natural light, delicate colour palette'),
                   'plan': 'Illustrated storybook: calm, readable scenes; one clear moment per page.'},
    'realistic': {'label': 'Gerçekçi fotoğraf', 'pace': (10, 35), 'zoom': 0.06,
                  'look': 'photorealistic photograph, natural light, 35mm lens, realistic textures, documentary framing',
                  'plan': 'Photo story: clear documentary scenes.'},
    'auto': {'label': 'AI seçsin (metne göre)', 'pace': (8, 40), 'zoom': 0.06, 'look': '', 'plan': ''},
}
DEFAULT_STYLE_KEY = 'comic'
NO_TEXT = 'no text, no letters, no captions, no speech bubbles in the image'


def style_of(key_or_proj):
    key = key_or_proj.get('style_key') if isinstance(key_or_proj, dict) else key_or_proj
    return STYLES.get(key or DEFAULT_STYLE_KEY) or STYLES[DEFAULT_STYLE_KEY]


def compose_prompt(proj: dict, sc: dict) -> str:
    """Sahnenin goruntu promptu: tarz + cekim + sahne + sahnedeki karakterlerin sabit gorunumu (her karede ayni tarif:
    tutarlilik). Kullanici sahnenin promptunu elle yazdiysa o kullanilir."""
    if (sc.get('prompt') or '').strip():
        return sc['prompt'].strip()
    plan = proj['plan']
    style = (plan.get('style') or style_of(proj)['look'] or DEFAULT_STYLE).strip().rstrip('.')
    looks = {c['name'].strip().lower(): c for c in plan.get('characters') or []}
    chars = [looks[n.strip().lower()] for n in sc.get('characters') or [] if n.strip().lower() in looks]
    parts = [style + '.']
    if sc.get('shot'):
        parts.append('%s shot.' % sc['shot'].strip().rstrip('.').replace(' shot', ''))
    parts.append((sc.get('visual') or sc.get('title') or '').strip().rstrip('.') + '.')
    if chars:
        parts.append('Characters, keep exactly this appearance in every image: ' +
                     '; '.join('%s: %s' % (c['name'], c['look'].rstrip('.')) for c in chars) + '.')
    parts.append('16:9 widescreen, %s.' % NO_TEXT)
    return ' '.join(p for p in parts if p.strip('. '))


# ----------------------------------------------------------------------------- sahne plani
PLAN_SYSTEM = (
    'You are a comic book editor, storyboard artist and film director. You turn a narrated text into an audio comic '
    '(motion comic / narrated picture story): one image per scene, the same art style and the same character designs in every '
    'image, narration and subtitles over the images. Answer with JSON only, no prose and no code fences.')

PLAN_USER = """The narration text is split into numbered paragraphs [P1]..[P{n}] (about {secs} seconds of narration in total).

1. Write a short summary of the whole text (3-5 sentences) in {lang}.
2. {style_step}
3. List the recurring characters (people, animals or named figures that should look the same in every panel). For each:
   "name" and "look" - a fixed visual description in English (age range, face, hair, build, clothing, distinctive marks) that
   an illustrator can reuse in every scene. No characters? Use an empty list.
4. Decide how many panels the comic needs and split the text into scenes. One scene = one panel, covering consecutive
   paragraphs. Start a new scene when the place, time, action or main subject visibly changes. Pacing for this style: scenes
   of about {pace_min}-{pace_max} seconds of narration. {style_plan} You decide the count.
   For each scene: "title" ({lang}, a few words), "start" and "end" (paragraph numbers, inclusive), "characters" (names from
   the list), "shot" (one of: wide, medium, close-up, extreme close-up, over-the-shoulder, bird's-eye; vary them like a
   comic artist), "visual" (English, 1-3 sentences: what the panel shows - setting, action, expressions, composition, mood;
   refer to characters by name, do not re-describe them; no text, letters or speech bubbles in the image).
Scenes must cover every paragraph from P1 to P{n} in order without gaps or overlaps.

JSON shape: {{"summary": "...", "style": "...", "characters": [{{"name": "...", "look": "..."}}], "scenes": [{{"title": "...", "start": 1, "end": 3, "characters": ["..."], "shot": "medium", "visual": "..."}}]}}

TEXT:
{text}"""


def plan_prompt(paras: list, lang: str = 'Türkçe', budget: int = 60000, style_key: str = DEFAULT_STYLE_KEY) -> str:
    per = max(200, budget // max(1, len(paras)))
    lines = []
    for i, p in enumerate(paras, start=1):
        lines.append('[P%d] %s' % (i, p if len(p) <= per else p[:per] + ' …'))
    st = style_of(style_key)
    if st['look']:
        step = ('The art style is fixed: "%s". Return it unchanged as "style" (you may append a short palette/lighting note '
                'that fits the text).' % st['look'])
    else:
        step = ('Choose ONE art style for the whole work that fits the text\'s tone and audience ("style", English, one '
                'sentence: comic or film tradition, line work, colouring, palette, lighting; e.g. "European ligne claire graphic '
                'novel, clean ink outlines, flat muted colours, soft daylight"). Every image uses it.')
    return PLAN_USER.format(n=len(paras), secs=int(est_seconds(paras, 0, len(paras) - 1)), lang=lang, text='\n'.join(lines),
                            style_step=step, pace_min=st['pace'][0], pace_max=st['pace'][1], style_plan=st['plan'])


def _json_from_text(text: str):
    t = (text or '').strip()
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', t)
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r'\{.*\}', t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                return None
    return None


def parse_plan(text: str, n_paras: int, style_key: str = DEFAULT_STYLE_KEY) -> dict | None:
    """AI yanitini plana cevirir ve duzeltir: sahneler sirali, bosluksuz, cakismasiz P1..Pn. Kurtarilamazsa None."""
    d = _json_from_text(text)
    if not isinstance(d, dict) or not isinstance(d.get('scenes'), list) or n_paras <= 0:
        return None
    raw = []
    for s in d['scenes']:
        if not isinstance(s, dict):
            continue
        try:
            a, b = int(s.get('start')), int(s.get('end', s.get('start')))
        except (TypeError, ValueError):
            continue
        a, b = max(1, min(n_paras, a)), max(1, min(n_paras, b))
        if b < a:
            a, b = b, a
        raw.append({'title': str(s.get('title') or '').strip()[:80], 'start': a - 1, 'end': b - 1,
                    'characters': [str(c) for c in (s.get('characters') or []) if str(c).strip()][:8],
                    'shot': str(s.get('shot') or '').strip()[:30],
                    'visual': str(s.get('visual') or '').strip()[:1200]})
    if not raw:
        return None
    raw.sort(key=lambda s: (s['start'], s['end']))
    scenes, nxt = [], 0
    for s in raw:
        if s['end'] < nxt:                              # tamamen onceki sahnenin icinde: at
            continue
        s['start'] = nxt                                # bosluk varsa bu sahne onu da kapsar; cakisma kirpilir
        scenes.append(s)
        nxt = s['end'] + 1
        if nxt >= n_paras:
            break
    if nxt < n_paras:
        scenes[-1]['end'] = n_paras - 1
    scenes = scenes[:MAX_SCENES]
    scenes[-1]['end'] = n_paras - 1
    chars = []
    for c in d.get('characters') or []:
        if isinstance(c, dict) and str(c.get('name') or '').strip():
            chars.append({'name': str(c['name']).strip()[:60], 'look': str(c.get('look') or '').strip()[:800]})
    look = style_of(style_key)['look']
    style = str(d.get('style') or '').strip()[:400]
    if look and not style.lower().startswith(look[:30].lower()):   # hazir tarz secildiyse tarz cumlesi o kalir
        style = look
    return {'summary': str(d.get('summary') or '').strip()[:3000], 'style': style or look or DEFAULT_STYLE,
            'characters': chars[:20], 'scenes': finish_scenes(scenes)}


def finish_scenes(scenes: list) -> list:
    for i, s in enumerate(scenes, start=1):
        s.setdefault('id', 's%02d' % i)
        s.setdefault('image', '')
        s.setdefault('shot', '')
        s['title'] = s.get('title') or 'Sahne %d' % i
    return scenes


def auto_plan(paras: list, target_seconds: float = 25.0, style_key: str = DEFAULT_STYLE_KEY) -> dict:
    """AI olmadan: paragraf sinirinda, sahne basina ~25 saniye."""
    scenes, start, acc = [], 0, 0.0
    for i, p in enumerate(paras):
        acc += words(p) / WORDS_PER_SEC
        if acc >= target_seconds or i == len(paras) - 1:
            scenes.append({'title': '', 'start': start, 'end': i, 'characters': [], 'visual': ''})
            start, acc = i + 1, 0.0
    if not scenes:
        scenes = [{'title': '', 'start': 0, 'end': max(0, len(paras) - 1), 'characters': [], 'visual': ''}]
    return {'summary': '', 'style': style_of(style_key)['look'] or DEFAULT_STYLE, 'characters': [],
            'scenes': finish_scenes(scenes[:MAX_SCENES])}


def merge_scene(plan: dict, idx: int) -> bool:
    """Sahneyi bir oncekiyle birlestirir (ilk sahne: sonrakiyle)."""
    sc = plan['scenes']
    if len(sc) < 2:
        return False
    a, b = (idx - 1, idx) if idx > 0 else (0, 1)
    sc[a]['end'] = sc[b]['end']
    sc[a]['characters'] = list(dict.fromkeys(sc[a]['characters'] + sc[b]['characters']))
    if not sc[a].get('image') and sc[b].get('image'):
        sc[a]['image'] = sc[b]['image']
    del sc[b]
    return True


def split_scene(plan: dict, idx: int) -> bool:
    """Sahneyi ortadaki paragraf sinirindan ikiye boler (tek paragrafli sahne bolunmez)."""
    s = plan['scenes'][idx]
    if s['end'] <= s['start']:
        return False
    mid = (s['start'] + s['end']) // 2
    new = {'id': 's%d' % int(time.time() * 1000), 'title': s['title'] + ' (2)', 'start': mid + 1, 'end': s['end'],
           'characters': list(s['characters']), 'shot': s.get('shot', ''), 'visual': s['visual'], 'image': ''}
    s['end'] = mid
    plan['scenes'].insert(idx + 1, new)
    return True


# ----------------------------------------------------------------------------- altyazi
def sentences(text: str) -> list:
    parts = [p.strip() for p in re.split(r'(?<=[.!?…])\s+', text or '') if p.strip()]
    out = []
    for p in parts:                                     # cok uzun cumleyi virgulden bol
        while len(p) > 110:
            cut = max(p.rfind(', ', 0, 100), p.rfind('; ', 0, 100))
            if cut < 40:
                cut = p.rfind(' ', 0, 100)
            if cut < 20:
                break
            out.append(p[:cut + 1].strip())
            p = p[cut + 1:].strip()
        out.append(p)
    return out


def wrap2(text: str, width: int = 42) -> str:
    """En fazla iki satir; daha uzunsa satir genisligi buyur (altyazi tek kare olarak kalir)."""
    t = text.strip()
    if len(t) <= width:
        return t
    while True:
        mid = len(t) // 2
        left, right = t.rfind(' ', 0, mid + 1), t.find(' ', mid)
        cut = min((c for c in (left, right) if c > 0), key=lambda c: abs(c - mid), default=-1)
        if cut < 0:
            return t
        a, b = t[:cut].strip(), t[cut:].strip()
        if max(len(a), len(b)) <= max(width, len(t) // 2 + 8):
            return a + '\n' + b
        width += 6


def cues(paras: list, durations: list, gap: float) -> list:
    """Altyazi kareleri [(bas, son, metin)]: her paragrafin suresi cumlelere karakter oraninda dagitilir."""
    out, t = [], 0.0
    for p, dur in zip(paras, durations):
        sents = sentences(p) or [p]
        total = sum(len(s) for s in sents) or 1
        start = t
        for s in sents:
            d = dur * len(s) / total
            out.append((start, start + d, wrap2(s)))
            start += d
        t += dur + gap
    return out


def _ts(sec: float, sep=','):
    ms = int(round(max(0.0, sec) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return '%02d:%02d:%02d%s%03d' % (h, m, s, sep, ms)


def srt(cue_list: list) -> str:
    return '\n'.join('%d\n%s --> %s\n%s\n' % (i, _ts(a), _ts(b), txt) for i, (a, b, txt) in enumerate(cue_list, start=1))


def ass(cue_list: list, font='Arial', size=54) -> str:
    """Goruntuye yakmak icin: 1080p olcekli, alt ortada, yari saydam koyu kutu."""
    def t(sec):
        cs = int(round(max(0.0, sec) * 100))
        h, cs = divmod(cs, 360000)
        m, cs = divmod(cs, 6000)
        s, cs = divmod(cs, 100)
        return '%d:%02d:%02d.%02d' % (h, m, s, cs)
    head = ('[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n'
            '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, '
            'Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, '
            'MarginR, MarginV, Encoding\n'
            'Style: Default,%s,%d,&H00FFFFFF,&H00FFFFFF,&H7A000000,&H7A000000,0,0,0,0,100,100,0,0,3,14,0,2,160,160,70,1\n\n'
            '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n') % (W, H, font, size)
    lines = ['Dialogue: 0,%s,%s,Default,,0,0,0,,%s' % (t(a), t(b), txt.replace('\n', '\\N').replace('{', '(').replace('}', ')'))
             for a, b, txt in cue_list]
    return head + '\n'.join(lines) + '\n'


# ----------------------------------------------------------------------------- yer tutucu
def _font(size, bold=False):
    from PIL import ImageFont
    names = (['segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'] if bold else ['segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf'])
    for n in names:
        for base in ('', os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts'), '/usr/share/fonts/truetype/dejavu'):
            try:
                return ImageFont.truetype(os.path.join(base, n) if base else n, size)
            except OSError:
                continue
    return ImageFont.load_default()


def placeholder(path: str, n: int, total: int, title: str, visual: str, excerpt: str, style_label: str = ''):
    """Gorsel gelene kadar sahneyi anlatan kart (1920x1080)."""
    from PIL import Image, ImageDraw
    hue = (n * 47) % 360
    import colorsys
    r, g, b = [int(255 * c) for c in colorsys.hsv_to_rgb(hue / 360.0, 0.45, 0.32)]
    img = Image.new('RGB', (W, H), (r, g, b))
    dr = ImageDraw.Draw(img)
    for y in range(H):                                  # yukaridan asagi koyulasan gecis
        k = y / H
        dr.line([(0, y), (W, y)], fill=(int(r * (1 - 0.55 * k)), int(g * (1 - 0.55 * k)), int(b * (1 - 0.55 * k))))
    f_small, f_title, f_body = _font(34), _font(76, bold=True), _font(40)
    dr.text((120, 110), 'KARE %d / %d  ·  %sGÖRSEL BEKLENİYOR' % (n, total, (style_label.upper() + '  ·  ') if style_label else ''),
            font=f_small, fill=(230, 230, 230))
    y = 190
    for line in _wrap_px(dr, title or 'Sahne %d' % n, f_title, W - 240)[:2]:
        dr.text((120, y), line, font=f_title, fill=(255, 255, 255))
        y += 96
    y += 20
    body = visual or excerpt
    for line in _wrap_px(dr, body, f_body, W - 240)[:9]:
        dr.text((120, y), line, font=f_body, fill=(225, 225, 225))
        y += 56
    img.save(path, 'PNG')
    return path


def _wrap_px(dr, text, font, width):
    out, line = [], ''
    for w in (text or '').split():
        test = (line + ' ' + w).strip()
        if dr.textlength(test, font=font) <= width:
            line = test
        else:
            if line:
                out.append(line)
            line = w
    if line:
        out.append(line)
    return out


# ----------------------------------------------------------------------------- ffmpeg
def find_ffmpeg(tools_dir=None):
    """ffmpeg ve ffprobe: once indirilmis kopya, sonra PATH."""
    exe = '.exe' if IS_WIN else ''
    if tools_dir:
        for root, _dirs, files in os.walk(tools_dir):
            if 'ffmpeg' + exe in files and 'ffprobe' + exe in files:
                return os.path.join(root, 'ffmpeg' + exe), os.path.join(root, 'ffprobe' + exe)
    a, b = shutil.which('ffmpeg'), shutil.which('ffprobe')
    return (a, b) if a and b else (None, None)


def download_ffmpeg(tools_dir, progress=None, cancel=None):
    """Windows: acik kaynak ffmpeg (BtbN derlemesi, GPL; libx264 + libass) indirilir ve acilir."""
    import urllib.request
    os.makedirs(tools_dir, exist_ok=True)
    zpath = os.path.join(tools_dir, 'ffmpeg.zip')
    req = urllib.request.Request(FFMPEG_ZIP, headers={'User-Agent': 'AGFO-AI-Editor'})
    with urllib.request.urlopen(req, timeout=60) as r, open(zpath, 'wb') as fh:
        total = int(r.headers.get('Content-Length') or 0)
        got = 0
        while True:
            if cancel is not None and cancel():
                raise Cancelled('Durduruldu.')
            chunk = r.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
            got += len(chunk)
            if progress:
                progress('ffmpeg indiriliyor… %d / %d MB' % (got >> 20, total >> 20) if total else 'ffmpeg indiriliyor… %d MB' % (got >> 20))
    with zipfile.ZipFile(zpath) as z:
        for m in z.namelist():
            if m.endswith(('bin/ffmpeg.exe', 'bin/ffprobe.exe')):
                with z.open(m) as src, open(os.path.join(tools_dir, os.path.basename(m)), 'wb') as dst:
                    shutil.copyfileobj(src, dst)
    os.remove(zpath)
    ff, fp = find_ffmpeg(tools_dir)
    if not ff:
        raise VideoError('ffmpeg indirildi ama içinde ffmpeg.exe bulunamadı.')
    return ff, fp


def _run(args, cwd=None, timeout=None):
    p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout,
                       creationflags=CREATE_NO_WINDOW if IS_WIN else 0)
    if p.returncode != 0:
        tail = (p.stderr or b'').decode('utf-8', 'replace').strip().splitlines()[-6:]
        raise VideoError('ffmpeg hatası:\n' + '\n'.join(tail))
    return p


def duration(ffprobe, path) -> float:
    p = _run([ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', path])
    try:
        return float(p.stdout.decode().strip())
    except ValueError:
        raise VideoError('Ses süresi okunamadı: %s' % path)


# ----------------------------------------------------------------------------- proje
def project_dir_for(doc_path: str | None, title: str, base: str) -> str:
    if doc_path:
        d, f = os.path.split(os.path.abspath(doc_path))
        return os.path.join(d, os.path.splitext(f)[0] + '_video')
    safe = re.sub(r'[^\w\- ]+', '', os.path.splitext(title or 'video')[0]).strip() or 'video'
    return os.path.join(base, safe + '_video')


def new_project(folder: str, title: str, paras: list, style_key: str = DEFAULT_STYLE_KEY) -> dict:
    os.makedirs(folder, exist_ok=True)
    key = style_key if style_key in STYLES else DEFAULT_STYLE_KEY
    pace = sum(STYLES[key]['pace']) / 2.0
    return {'version': 1, 'title': title, 'size': [W, H], 'fps': FPS, 'style_key': key, 'paragraphs': paras,
            'plan': auto_plan(paras, pace, key), 'planned_by': 'auto', 'folder': folder}


def set_style(proj: dict, key: str):
    """Hazir tarzi degistirir: tarz cumlesi yenilenir (AI secsin'de mevcut cumle kalir). Kurgu (sahne sayisi) icin plan
    yeniden cikarilmalidir."""
    if key not in STYLES:
        return
    proj['style_key'] = key
    if STYLES[key]['look']:
        proj['plan']['style'] = STYLES[key]['look']


def save_project(proj: dict):
    p = dict(proj)
    p.pop('folder', None)
    tmp = os.path.join(proj['folder'], PROJECT_FILE + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(p, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(proj['folder'], PROJECT_FILE))


def load_project(folder: str) -> dict | None:
    try:
        with open(os.path.join(folder, PROJECT_FILE), encoding='utf-8') as fh:
            p = json.load(fh)
    except (OSError, ValueError):
        return None
    p['folder'] = folder
    return p


def set_image(proj: dict, idx: int, src: str) -> str:
    """Kullanicinin gorselini projeye kopyalar (proje klasoru tasinabilir kalir)."""
    os.makedirs(os.path.join(proj['folder'], 'images'), exist_ok=True)
    ext = os.path.splitext(src)[1].lower() or '.png'
    sc = proj['plan']['scenes'][idx]
    dst = os.path.join('images', '%s%s' % (sc['id'], ext))
    shutil.copyfile(src, os.path.join(proj['folder'], dst))
    sc['image'] = dst
    return dst


def scene_text(proj: dict, sc: dict) -> str:
    return ' '.join(proj['paragraphs'][sc['start']:sc['end'] + 1])


# ----------------------------------------------------------------------------- uretim
def render(proj: dict, speak, ffmpeg, ffprobe, *, gap_ms=600, voice_key='', status=None, cancel=None, out_name=None) -> str:
    """speak(metin) -> mp3 bayt. Ses paragraf paragraf (onbellekli), altyazi, yer tutucular ve MOV. Donus: MOV yolu."""
    folder = proj['folder']
    paras = proj['paragraphs']
    scenes = proj['plan']['scenes']
    say = status or (lambda m: None)

    def stop():
        if cancel is not None and cancel():
            raise Cancelled('Durduruldu.')
    adir = os.path.join(folder, 'audio')
    os.makedirs(adir, exist_ok=True)
    import agfo_readaloud as ra
    durs, files = [], []                                # files: paragraf basina parca dosyalari
    for i, p in enumerate(paras):
        stop()
        pieces, total_p = [], 0.0
        for j, piece in enumerate(ra.split_piece(p) or [p]):   # uzun paragraf: sesin tek is sinirina gore parcalar
            key = hashlib.sha1(('%s|%s' % (voice_key, piece)).encode('utf-8')).hexdigest()[:16]
            f = os.path.join(adir, 'p%03d_%02d_%s.mp3' % (i + 1, j, key))
            if not os.path.isfile(f) or os.path.getsize(f) == 0:
                say('Seslendiriliyor… paragraf %d / %d' % (i + 1, len(paras)))
                data = speak(piece)
                if not data:
                    raise VideoError('Paragraf %d için ses gelmedi.' % (i + 1))
                with open(f + '.tmp', 'wb') as fh:
                    fh.write(data)
                os.replace(f + '.tmp', f)
            pieces.append(f)
            total_p += duration(ffprobe, f)
        files.append(pieces)
        durs.append(total_p)
    gap = max(0, int(gap_ms)) / 1000.0
    # tek ses dosyasi (paragraflar arasinda sessizlik)
    say('Ses birleştiriliyor…')
    sil = os.path.join(adir, 'gap_%d.wav' % int(gap * 1000))
    if gap and not os.path.isfile(sil):
        _run([ffmpeg, '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-t', '%.3f' % gap, sil])
    lst = os.path.join(adir, 'list.txt')
    with open(lst, 'w', encoding='utf-8') as fh:
        for i, pieces in enumerate(files):
            for f in pieces:
                fh.write("file '%s'\n" % os.path.basename(f))
            if gap and i < len(files) - 1:
                fh.write("file '%s'\n" % os.path.basename(sil))
    _run([ffmpeg, '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-ar', '44100', '-ac', '1', '-c:a', 'pcm_s16le', 'voice.wav'],
         cwd=adir)
    # altyazi
    cl = cues(paras, durs, gap)
    with open(os.path.join(folder, 'subs.srt'), 'w', encoding='utf-8') as fh:
        fh.write(srt(cl))
    with open(os.path.join(folder, 'subs.ass'), 'w', encoding='utf-8') as fh:
        fh.write(ass(cl))
    # sahne sureleri ve gorseller
    starts, t = [], 0.0
    for i, d in enumerate(durs):
        starts.append(t)
        t += d + (gap if i < len(durs) - 1 else 0)
    total = t
    pdir = os.path.join(folder, 'placeholders')
    os.makedirs(pdir, exist_ok=True)
    inputs, filt, labels = [], [], []
    for n, sc in enumerate(scenes):
        stop()
        a = starts[sc['start']]
        b = starts[sc['end'] + 1] if sc['end'] + 1 < len(starts) else total
        dur = max(0.5, b - a)
        sc['seconds'] = round(dur, 2)
        img = os.path.join(folder, sc['image']) if sc.get('image') else ''
        if not img or not os.path.isfile(img):
            img = placeholder(os.path.join(pdir, '%s.png' % sc['id']), n + 1, len(scenes), sc.get('title'),
                              ' · '.join(x for x in (sc.get('shot'), sc.get('visual')) if x), scene_text(proj, sc)[:400],
                              style_of(proj)['label'])
        inputs += ['-i', img]
        frames = max(1, int(round(dur * FPS)))
        zmax = style_of(proj)['zoom']
        zoom = "min(zoom+%.6f,%.3f)" % (zmax / frames, 1 + zmax)
        filt.append('[%d:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,'
                    "zoompan=z='%s':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=%d:s=%dx%d:fps=%d,trim=end_frame=%d[v%d]"
                    % (n, W * 5 // 4, H * 5 // 4, W * 5 // 4, H * 5 // 4, zoom, frames, W, H, FPS, frames, n))
        labels.append('[v%d]' % n)
    filt.append('%sconcat=n=%d:v=1:a=0[vc]' % (''.join(labels), len(labels)))
    filt.append('[vc]subtitles=subs.ass,format=yuv420p[vout]')
    out = out_name or (re.sub(r'[^\w\- ]+', '', proj.get('title') or 'video').strip() or 'video') + '.mov'
    say('Video oluşturuluyor (%d sahne, %d sn)…' % (len(scenes), int(total)))
    with open(os.path.join(folder, 'filter.txt'), 'w', encoding='utf-8') as fh:
        fh.write(';\n'.join(filt))
    tail = ['-map', '[vout]', '-map', '%d:a' % len(scenes), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
            '-r', str(FPS), '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', out]
    head = [ffmpeg, '-y'] + inputs + ['-i', os.path.join('audio', 'voice.wav')]
    # 2.9.1: filtre dosyadan okunur. ffmpeg 7+ '-/filter_complex dosya' ister (yeni surumlerde -filter_complex_script
    # kaldirildi); 7'den eski surumler yalniz -filter_complex_script bilir.
    try:
        _run(head + ['-/filter_complex', 'filter.txt'] + tail, cwd=folder)
    except VideoError as e:
        if 'filter_complex' not in str(e) or not re.search(r'Unrecognized option|Option not found', str(e)):
            raise
        _run(head + ['-filter_complex_script', 'filter.txt'] + tail, cwd=folder)
    proj['rendered'] = {'file': out, 'seconds': round(total, 2), 'at': time.strftime('%Y-%m-%d %H:%M')}
    save_project(proj)
    return os.path.join(folder, out)
