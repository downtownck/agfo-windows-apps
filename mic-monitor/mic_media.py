"""AGFO Mic Monitor - ffmpeg ile MP3 / MP4 disa aktarma ve kamera (onizleme + kayit).

ffmpeg AYRI bir program olarak calistirilir (uygulamaya gomulu degil; GPL acisindan "toplama").
Yoksa ilk kullanimda bir kez indirilir: imageio-ffmpeg 0.7.0 Windows paketi (PyPI) icindeki gyan.dev
"essentials" ffmpeg 7.1 derlemesi (GPLv3). Paket ve icindeki ffmpeg.exe SHA-256 ile dogrulanir;
ozetler asagida sabittir, uyusmazsa dosya kullanilmaz.

Kamera (Windows: DirectShow): tek ffmpeg sureci hem kucuk, aynalanmis bir onizleme (ham RGB, boruyla)
hem de kayitta tam cozunurlukte H.264 video (.mkv; ani durmaya dayanikli) uretir. Kayit bitince video
ile ses (vokal ya da karisim) MP4'te birlestirilir; ses ile goruntunun baslangic farki olculup
-itsoffset ile duzeltilir, bolum isaretleri MP4 bolumlerine aktarilir.
"""
import collections
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile

import mic_core as core

IS_WIN = sys.platform == 'win32'
CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0

FFMPEG_WHEEL_URL = ('https://files.pythonhosted.org/packages/e5/55/1d50cdd78d862a30c2ce44f01cea387f77b364b21fa2fecf1590258b215b/'
                    'imageio_ffmpeg-0.7.0-py3-none-win_amd64.whl')
FFMPEG_WHEEL_SHA256 = '7a22b45f60321d4172bdf2bc61f716bce4c81b85727bd59c7c7e371055a6a440'
FFMPEG_WHEEL_SIZE = 31247004
FFMPEG_MEMBER = 'imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
FFMPEG_EXE_SHA256 = '2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3'
FFMPEG_ALLOWED_HOSTS = ('files.pythonhosted.org',)
FFMPEG_NOTICE = """ffmpeg 7.1 (gyan.dev "essentials" derlemesi), imageio-ffmpeg 0.7.0 paketinden.
Lisans: GNU GPL v3. AGFO Mic Monitor ffmpeg'i ayri bir program olarak calistirir.
Kaynak kodu: https://ffmpeg.org/download.html  -  Derleme: https://www.gyan.dev/ffmpeg/builds/
Paket: https://pypi.org/project/imageio-ffmpeg/0.7.0/
"""

PREVIEW_SIZES = {'kucuk': (240, 135), 'orta': (320, 180), 'buyuk': (480, 270)}
CORNERS = {'sag-ust': 'ne', 'sol-ust': 'nw', 'sag-alt': 'se', 'sol-alt': 'sw'}
RESOLUTIONS = ('1280x720', '1920x1080', '640x480', 'otomatik')
CAM_RATIOS = {'kucuk': 0.22, 'orta': 0.30, 'buyuk': 0.40}     # birlesik videoda kamera genisligi / video genisligi
CAMERA_LATENCY_S = 0.05     # kamera karesinin ffmpeg'e ulasma gecikmesi (USB + surucu); goruntu bu kadar erkene alinir
STAGE_BG = (5, 8, 15)
STAGE_FG = (255, 255, 255)


class MediaError(Exception):
    pass


# --------------------------------------------------------------------------- ffmpeg bulma / indirme
def ffmpeg_dir():
    return core.data_dir() / 'ffmpeg'


def installed_ffmpeg():
    return ffmpeg_dir() / ('ffmpeg.exe' if IS_WIN else 'ffmpeg')


def find_ffmpeg(configured=''):
    """Oncelik: ayarlarda verilen yol > uygulamanin indirdigi > PATH'teki ffmpeg."""
    for c in (configured, str(installed_ffmpeg())):
        if c and os.path.isfile(c):
            return c
    return shutil.which('ffmpeg')


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def download_ffmpeg(progress=None, should_stop=None, url=FFMPEG_WHEEL_URL, wheel_sha=FFMPEG_WHEEL_SHA256,
                    member=FFMPEG_MEMBER, exe_sha=FFMPEG_EXE_SHA256, opener=None):
    """ffmpeg'i indirir, iki asamada dogrular ve kurar. progress(okunan, toplam)."""
    from urllib.parse import urlsplit
    host = (urlsplit(url).hostname or '').lower()
    if urlsplit(url).scheme != 'https' or host not in FFMPEG_ALLOWED_HOSTS:
        raise MediaError('Izin verilmeyen indirme adresi: %s' % url)
    d = ffmpeg_dir()
    d.mkdir(parents=True, exist_ok=True)
    part = d / 'ffmpeg-paket.part'
    if opener is None:
        import urllib.request
        opener = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'AGFO-Mic-Monitor'}), timeout=60)
    h = hashlib.sha256()
    got = 0
    with opener(url) as r, open(part, 'wb') as f:
        total = int(getattr(r, 'headers', {}).get('Content-Length') or FFMPEG_WHEEL_SIZE)
        while True:
            if should_stop and should_stop():
                raise MediaError('Indirme iptal edildi.')
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            got += len(chunk)
            if progress:
                progress(got, total)
    if h.hexdigest() != wheel_sha:
        part.unlink(missing_ok=True)
        raise MediaError('Indirilen paket dogrulanamadi (SHA-256 uyusmuyor); kullanilmadi.')
    target = installed_ffmpeg()
    tmp = target.with_name(target.name + '.new')
    with zipfile.ZipFile(part) as z, z.open(member) as src, open(tmp, 'wb') as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
    part.unlink(missing_ok=True)
    if _sha256(tmp) != exe_sha:
        tmp.unlink(missing_ok=True)
        raise MediaError('ffmpeg dosyasi dogrulanamadi (SHA-256 uyusmuyor); kullanilmadi.')
    if not IS_WIN:
        os.chmod(tmp, 0o755)
    os.replace(tmp, target)
    (d / 'LISANS-ffmpeg.txt').write_text(FFMPEG_NOTICE, encoding='utf-8')
    return target


def run(ff, args, timeout=600):
    p = subprocess.run([ff, '-hide_banner', '-nostdin', '-loglevel', 'error'] + list(args), capture_output=True,
                       timeout=timeout, creationflags=CREATE_NO_WINDOW)
    if p.returncode:
        raise MediaError((p.stderr or b'').decode('utf-8', 'replace').strip()[-600:] or 'ffmpeg hata verdi')
    return p


# --------------------------------------------------------------------------- bolumler (UTF-8)
def wav_duration(path):
    import wave
    with wave.open(str(path), 'rb') as w:
        return w.getnframes() / float(w.getframerate() or 1)


def write_chapters(marks, duration, path, offset=0.0):
    """ffmpeg meta veri dosyasi (UTF-8): MP3/MP4 bolumleri Turkce basliklariyla dogru gorunur.
    (WAV icindeki etiketler Cool Edit / Audition icin Windows Turkce kodlamasindadir.)"""
    marks = sorted((max(0.0, float(t) + offset), str(lab)) for t, lab in marks)
    end_all = max(float(duration) + offset, marks[-1][0] + 0.001 if marks else 0.0)

    def esc(x):
        return re.sub(r'([=;#\\\n])', r'\\\1', x)
    lines = [';FFMETADATA1']
    for i, (t, lab) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else end_all
        lines += ['[CHAPTER]', 'TIMEBASE=1/1000', 'START=%d' % int(round(t * 1000)),
                  'END=%d' % max(int(round(t * 1000)) + 1, int(round(end * 1000))), 'title=%s' % esc(lab)]
    pathlib.Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


# --------------------------------------------------------------------------- MP3
def to_mp3(ff, wav, out=None, quality=2, marks=None):
    """WAV -> MP3 (LAME VBR; q2 ~ 170-210 kbps). marks verilirse ID3 bolumleri (CHAP) yazilir."""
    wav = pathlib.Path(wav)
    out = pathlib.Path(out) if out else wav.with_suffix('.mp3')
    tmp = out.with_name(out.stem + '.part.mp3')
    args = ['-y', '-i', str(wav)]
    meta = None
    if marks:
        meta = write_chapters(marks, wav_duration(wav), out.with_name(out.stem + '.chapters.txt'))
        args += ['-f', 'ffmetadata', '-i', str(meta), '-map', '0:a', '-map_chapters', '1']
    else:
        args += ['-map_chapters', '-1']
    try:
        run(ff, args + ['-c:a', 'libmp3lame', '-q:a', str(int(quality)), '-id3v2_version', '3', str(tmp)])
    finally:
        if meta:
            pathlib.Path(meta).unlink(missing_ok=True)
    os.replace(tmp, out)
    return out


# --------------------------------------------------------------------------- kamera
def list_cameras(ff):
    """Windows DirectShow video aygitlari (ad listesi)."""
    if not IS_WIN or not ff:
        return []
    p = subprocess.run([ff, '-hide_banner', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
                       capture_output=True, timeout=20, creationflags=CREATE_NO_WINDOW)
    return parse_dshow_devices((p.stderr or b'').decode('utf-8', 'replace'))


def parse_dshow_devices(text):
    names = []
    legacy_video = False
    for ln in text.splitlines():
        if 'DirectShow video devices' in ln:
            legacy_video = True
            continue
        if 'DirectShow audio devices' in ln:
            legacy_video = False
            continue
        if 'Alternative name' in ln:
            continue
        m = re.search(r'"([^"]+)"\s*\((video|audio|none)\)', ln)
        if m:
            if m.group(2) == 'video' and m.group(1) not in names:
                names.append(m.group(1))
            continue
        m = re.search(r'\]\s+"([^"]+)"\s*$', ln)
        if m and legacy_video and m.group(1) not in names:
            names.append(m.group(1))
    return names


def camera_input_args(name, size='1280x720', fps=30):
    """DirectShow kamera girdisi. Testlerde (Windows disi) yerine lavfi test goruntusu verilebilir."""
    args = ['-f', 'dshow', '-rtbufsize', '256M']
    if size and size != 'otomatik':
        args += ['-video_size', size, '-framerate', str(fps)]
    return args + ['-i', 'video=%s' % name]


class Camera:
    """Tek ffmpeg sureci: onizleme (ham RGB boru) + istege bagli kayit dosyasi."""

    def __init__(self, ff, input_args, preview=(320, 180), mirror=True):
        self.ff = ff
        self.input_args = list(input_args)
        self.pw, self.ph = preview
        self.mirror = mirror
        self.proc = None
        self.record_path = None
        self.frame = None
        self.seq = 0
        self.first_frame_t = None
        self.err = collections.deque(maxlen=40)
        self._lock = threading.Lock()

    def _cmd(self, record_path):
        pv = 'fps=15,scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2%s,format=rgb24' % (
            self.pw, self.ph, self.pw, self.ph, ',hflip' if self.mirror else '')
        ia = list(self.input_args)
        if record_path:
            # 1.5.1: her kare yakalandigi anin duvar saatiyle damgalanir (-copyts ile dosyaya aynen yazilir):
            # ses de ayni saatle olculdugu icin goruntu-ses farki dogrudan hesaplanir; uzun kayitta kayma olmaz.
            k = len(ia) - 1 - ia[::-1].index('-i')
            ia = ia[:k] + ['-use_wallclock_as_timestamps', '1'] + ia[k:]
        cmd = [self.ff, '-hide_banner', '-loglevel', 'error', '-y'] + ia
        if record_path:
            cmd += ['-filter_complex', '[0:v]split=2[rec][pv];[pv]%s[pvo]' % pv,
                    '-map', '[rec]', '-copyts', '-fps_mode', 'passthrough', '-c:v', 'libx264', '-preset', 'veryfast',
                    '-crf', '21', '-pix_fmt', 'yuv420p', '-g', '60', str(record_path),
                    '-map', '[pvo]', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
        else:
            cmd += ['-vf', pv, '-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
        return cmd

    def start(self, record_path=None):
        self.stop()
        self.record_path = pathlib.Path(record_path) if record_path else None
        self.first_frame_t = None
        self.err.clear()
        self.proc = subprocess.Popen(self._cmd(self.record_path), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW, bufsize=0)
        threading.Thread(target=self._read_frames, args=(self.proc,), daemon=True, name='micmon-cam').start()
        threading.Thread(target=self._read_err, args=(self.proc,), daemon=True, name='micmon-camerr').start()
        return self

    def _read_frames(self, proc):
        n = self.pw * self.ph * 3
        out = proc.stdout
        while True:
            buf = b''
            while len(buf) < n:
                chunk = out.read(n - len(buf))
                if not chunk:
                    return
                buf += chunk
            with self._lock:
                if self.first_frame_t is None and proc is self.proc:
                    self.first_frame_t = time.monotonic()
                self.frame = buf
                self.seq += 1

    def _read_err(self, proc):
        for ln in iter(proc.stderr.readline, b''):
            self.err.append(ln.decode('utf-8', 'replace').rstrip())

    def ppm(self):
        """(sira, PPM baytlari) - Tk PhotoImage dogrudan gosterir."""
        with self._lock:
            if self.frame is None:
                return self.seq, None
            return self.seq, b'P6 %d %d 255\n' % (self.pw, self.ph) + self.frame

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def wait_first_frame(self, timeout=8.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.first_frame_t is not None:
                return True
            if not self.alive():
                return False
            time.sleep(0.02)
        return False

    def stop(self, timeout=15.0):
        """Kayitta 'q' ile duzgun kapanir (dosya tamamlanir); onizlemede dogrudan sonlandirilir."""
        p, self.proc = self.proc, None
        if p is None:
            return None
        try:
            if self.record_path is not None and p.poll() is None:
                try:
                    p.stdin.write(b'q')
                    p.stdin.flush()
                except OSError:
                    pass
                try:
                    p.wait(timeout)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(5)
            elif p.poll() is None:
                p.terminate()
                try:
                    p.wait(5)
                except subprocess.TimeoutExpired:
                    p.kill()
        finally:
            for s in (p.stdin, p.stdout, p.stderr):
                try:
                    s.close()
                except Exception:
                    pass
        rec, self.record_path = self.record_path, None
        return rec

    def error_text(self):
        return ' | '.join(list(self.err)[-4:])


# --------------------------------------------------------------------------- MP4 birlestirme
def mux_mp4(ff, video, audio, out, shift=0.0, audio_bitrate='192k', marks=None):
    """video (.mkv H.264) + ses (WAV) -> MP4. shift > 0: goruntu sesten 'shift' sn GEC basladi (goruntu
    o kadar ileri kaydirilir); shift < 0: ses gec basladi. marks: MP4 bolumleri (ses zaman ekseninde)."""
    out = pathlib.Path(out)
    tmp = out.with_name(out.stem + '.part.mp4')
    v_in = ['-i', str(video)]
    a_in = ['-i', str(audio)]
    a_delay = 0.0
    if shift > 0.0005:
        v_in = ['-itsoffset', '%.4f' % shift] + v_in
    elif shift < -0.0005:
        a_in = ['-itsoffset', '%.4f' % (-shift)] + a_in
        a_delay = -shift
    extra, meta = [], None
    if marks:
        meta = write_chapters(marks, wav_duration(audio), out.with_name(out.stem + '.chapters.txt'), offset=a_delay)
        extra = ['-f', 'ffmetadata', '-i', str(meta)]
    chap = ['-map_chapters', '2'] if meta else ['-map_chapters', '-1']
    try:
        run(ff, ['-y'] + v_in + a_in + extra + ['-map', '0:v:0', '-map', '1:a:0'] + chap +
            ['-c:v', 'copy', '-c:a', 'aac', '-b:a', audio_bitrate, '-movflags', '+faststart', '-shortest', str(tmp)])
    finally:
        if meta:
            pathlib.Path(meta).unlink(missing_ok=True)
    os.replace(tmp, out)
    return out


def _probe(ff, path):
    p = subprocess.run([ff, '-hide_banner', '-i', str(path)], capture_output=True, timeout=60, creationflags=CREATE_NO_WINDOW)
    return (p.stderr or b'').decode('utf-8', 'replace')


def stream_start(ff, path):
    """Dosyanin baslangic zamani (sn). Kamera kaydinda bu, ilk karenin duvar saatidir (epoch)."""
    m = re.search(r'start:\s*(-?[0-9.]+)', _probe(ff, path))
    return float(m.group(1)) if m else None


def probe_duration(ff, path):
    """ffmpeg ile sure (sn); ffprobe gerektirmez. Duvar saatli dosyada baslangic dusulur."""
    t = _probe(ff, path)
    m = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', t)
    if not m:
        return None
    d = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    st = re.search(r'start:\s*(-?[0-9.]+)', t)
    if st and float(st.group(1)) > 1e6 and d > float(st.group(1)):
        d -= float(st.group(1))
    return d


# --------------------------------------------------------------------------- prompter videosu (metin + kamera)
def stage_size(cam_res):
    return (1920, 1080) if cam_res == '1920x1080' else (1280, 720)


def find_font():
    """Kalin, Turkce karakterli bir TrueType yazi tipi."""
    windir = os.environ.get('WINDIR', r'C:\Windows')
    for c in (os.path.join(windir, 'Fonts', 'segoeuib.ttf'), os.path.join(windir, 'Fonts', 'arialbd.ttf'),
              '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/Library/Fonts/Arial Bold.ttf'):
        if os.path.isfile(c):
            return c
    return None


def cam_box(W, H, corner, size):
    """Birlesik videoda kameranin kapladigi kutu (x, y, w, h) - 4:3 kamerayi da sigdiracak yukseklikle."""
    w = int(W * CAM_RATIOS.get(size, 0.30)) // 2 * 2
    h = int(w * 0.75) // 2 * 2
    m = int(W * 0.025)
    c = CORNERS.get(corner, 'se')
    x = W - w - m if 'e' in c else m
    y = H - h - m if 's' in c else m
    return x, y, w, h, m


def _wrap(draw, text, font, width):
    lines = []
    for para in text.split('\n'):
        words = para.split()
        if not words:
            lines.append('')
            continue
        cur = words[0]
        for wd in words[1:]:
            if draw.textlength(cur + ' ' + wd, font=font) <= width:
                cur += ' ' + wd
            else:
                lines.append(cur)
                cur = wd
        lines.append(cur)
    return lines


def render_slide(text, path, W=1280, H=720, reserve=None, font_path=None):
    """Bir prompter bolumunu PNG olarak cizer (koyu zemin, beyaz kalin yazi; ekrandaki gibi).
    reserve: (ust_pay, alt_pay) piksel - kameranin kapladigi bolge metne verilmez. Sigana kadar kucultur."""
    from PIL import Image, ImageDraw, ImageFont
    top_pad, bottom_pad = reserve or (0, 0)
    img = Image.new('RGB', (W, H), STAGE_BG)
    d = ImageDraw.Draw(img)
    fp = font_path or find_font()
    left, width = int(W * 0.05), int(W * 0.90)
    top = int(H * 0.06) + top_pad
    room = H - top - int(H * 0.05) - bottom_pad
    size = int(H * 0.075)
    while True:
        font = ImageFont.truetype(fp, size) if fp else ImageFont.load_default(size=size)
        lines = _wrap(d, text, font, width)
        lh = int(size * 1.28)
        if len(lines) * lh <= room or size <= 14:
            break
        size = int(size * 0.92)
    y = top
    for ln in lines:
        d.text((left, y), ln, font=font, fill=STAGE_FG)
        y += lh
    img.save(str(path))
    return path


def compose_mp4(ff, sections, timeline, audio, out, camera=None, shift=0.0, cam_res='1280x720',
                corner='sag-alt', size='orta', marks=None, workdir=None):
    """Prompter videosu: o an okunan bolumun metni sahnede, kamera kosede, ses ve bolum isaretleri.
    sections: bolum metinleri; timeline: [(sn, bolum_indeksi)] ses zaman ekseninde; camera: kamera .mkv
    (yoksa yalniz metin + ses); shift > 0: kamera sesten 'shift' sn gec basladi."""
    import tempfile
    out = pathlib.Path(out)
    W, H = stage_size(cam_res)
    dur = wav_duration(audio)
    tl = sorted((max(0.0, float(t)), int(i)) for t, i in timeline if 0 <= int(i) < len(sections)) or [(0.0, 0)]
    if tl[0][0] > 0:
        tl.insert(0, (0.0, tl[0][1]))
    x, y, cw, ch, m = cam_box(W, H, corner, size)
    reserve = (0, 0)
    if camera is not None:
        reserve = (ch + m, 0) if y < H / 2 else (0, ch + m)
    wd = pathlib.Path(workdir or tempfile.mkdtemp(prefix='micmon-stage-'))
    wd.mkdir(parents=True, exist_ok=True)
    fp = find_font()
    pngs = {}
    for _, i in tl:
        if i not in pngs:
            pngs[i] = render_slide('\n\n'.join(sections[i]) if isinstance(sections[i], (list, tuple)) else sections[i],
                                   wd / ('bolum_%03d.png' % i), W, H, reserve, fp)
    lines = ['ffconcat version 1.0']
    for k, (t, i) in enumerate(tl):
        end = tl[k + 1][0] if k + 1 < len(tl) else max(t + 0.1, dur)
        lines += ["file '%s'" % pngs[i].name, 'duration %.3f' % max(0.04, end - t)]
    lines.append("file '%s'" % pngs[tl[-1][1]].name)           # concat kurali: son kare tekrar
    lst = wd / 'sahne.ffconcat'
    lst.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    args = ['-y', '-f', 'concat', '-safe', '0', '-i', str(lst)]
    fc = '[0:v]fps=30,scale=%d:%d,setsar=1,format=yuv420p[bg]' % (W, H)
    if camera is not None:
        args += ['-i', str(camera)]
        if shift >= 0:
            cam = '[1:v]setpts=PTS-STARTPTS+%.4f/TB' % shift
        else:
            cam = '[1:v]trim=start=%.4f,setpts=PTS-STARTPTS' % (-shift)
        fc += ';%s,scale=%d:-2,setsar=1[cam];[bg][cam]overlay=x=%s:y=%s:eof_action=pass[v]' % (
            cam, cw, ('W-w-%d' % m) if x > W / 2 else str(m), ('H-h-%d' % m) if y > H / 2 else str(m))
        vout, a_idx = '[v]', 2
    else:
        vout, a_idx = '[bg]', 1
    args += ['-i', str(audio)]
    meta = None
    if marks:
        meta = write_chapters(marks, dur, wd / 'bolumler.txt')
        args += ['-f', 'ffmetadata', '-i', str(meta)]
    tmp = out.with_name(out.stem + '.part.mp4')
    args += ['-filter_complex', fc, '-map', vout, '-map', '%d:a:0' % a_idx]
    args += (['-map_chapters', str(a_idx + 1)] if meta else ['-map_chapters', '-1'])
    args += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p', '-r', '30',
             '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-t', '%.3f' % dur, str(tmp)]
    try:
        run(ff, args, timeout=max(600, int(dur * 4)))
        os.replace(tmp, out)
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    return out
