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
        cmd = [self.ff, '-hide_banner', '-loglevel', 'error', '-y'] + self.input_args
        if record_path:
            cmd += ['-filter_complex', '[0:v]split=2[rec][pv];[pv]%s[pvo]' % pv,
                    '-map', '[rec]', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p',
                    '-g', '60', str(record_path),
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


def probe_duration(ff, path):
    """ffmpeg ile sure (sn); ffprobe gerektirmez."""
    p = subprocess.run([ff, '-hide_banner', '-i', str(path)], capture_output=True, timeout=60, creationflags=CREATE_NO_WINDOW)
    m = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', (p.stderr or b'').decode('utf-8', 'replace'))
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
