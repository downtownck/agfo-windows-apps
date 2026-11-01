"""AGFO Mic Monitor - ffmpeg: indirme dogrulamasi, MP3, kamera (test goruntusu), MP4 esleme ve bolumler.

ffmpeg yoksa ffmpeg gerektiren testler atlanir (indirme dogrulamasi her zaman calisir).

    python -I tests/test_media.py <mic-monitor klasoru>
"""
import hashlib
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='micmon-media-')
import numpy as np  # noqa: E402
import mic_core as core  # noqa: E402
import mic_media as mm  # noqa: E402
import mic_backing as mb  # noqa: E402

PASSED, SKIPPED = [], []
TMP = pathlib.Path(tempfile.mkdtemp(prefix='micmon-mf-'))
FF = mm.find_ffmpeg()
LAVFI = ['-re', '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=30']


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


def needs_ff(fn):
    if not FF:
        SKIPPED.append(fn.__name__)
        return fn
    return test(fn)


class _Resp(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@test
def download_verifies_both_hashes_and_host():
    exe = b'MZ fake ffmpeg ' * 1000
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr(mm.FFMPEG_MEMBER, exe)
    wheel = buf.getvalue()
    ws, es = hashlib.sha256(wheel).hexdigest(), hashlib.sha256(exe).hexdigest()
    seen = []
    p = mm.download_ffmpeg(progress=lambda g, t: seen.append(g), wheel_sha=ws, exe_sha=es,
                           opener=lambda u: _Resp(wheel))
    assert p.read_bytes() == exe and seen and seen[-1] == len(wheel)
    assert (mm.ffmpeg_dir() / 'LISANS-ffmpeg.txt').read_text(encoding='utf-8').startswith('ffmpeg 7.1')
    assert mm.find_ffmpeg() == str(p)                               # indirilen, PATH'tekinden once
    p.unlink()
    for bad_ws, bad_es in ((ws[::-1], es), (ws, es[::-1])):         # kurcalanmis paket / exe reddedilir
        try:
            mm.download_ffmpeg(wheel_sha=bad_ws, exe_sha=bad_es, opener=lambda u: _Resp(wheel))
        except mm.MediaError as e:
            assert 'dogrulanamadi' in str(e)
        else:
            raise AssertionError('dogrulanmamis dosya kabul edildi')
        assert not mm.installed_ffmpeg().exists()
    try:
        mm.download_ffmpeg(url='https://evil.example.com/x.whl', opener=lambda u: _Resp(wheel))
    except mm.MediaError as e:
        assert 'Izin verilmeyen' in str(e)
    else:
        raise AssertionError('izinsiz adres kabul edildi')
    assert mm.FFMPEG_WHEEL_URL.startswith('https://files.pythonhosted.org/') and len(mm.FFMPEG_WHEEL_SHA256) == 64


@test
def dshow_listing_parse():
    new = ('[dshow @ 0] "Integrated Camera" (video)\n[dshow @ 0]   Alternative name "@device_pnp_x"\n'
           '[dshow @ 0] "OBS Virtual Camera" (none)\n[dshow @ 0] "Mikrofon (Realtek(R) Audio)" (audio)\n'
           '[dshow @ 0] "USB2.0 HD UVC WebCam" (video)\n')
    assert mm.parse_dshow_devices(new) == ['Integrated Camera', 'USB2.0 HD UVC WebCam']
    old = ('[dshow @ 0] DirectShow video devices (some may be both video and audio devices)\n'
           '[dshow @ 0]  "Logitech HD Webcam C270"\n[dshow @ 0]     Alternative name "@device_pnp_x"\n'
           '[dshow @ 0] DirectShow audio devices\n[dshow @ 0]  "Mikrofon (C270)"\n')
    assert mm.parse_dshow_devices(old) == ['Logitech HD Webcam C270']
    a = mm.camera_input_args('Integrated Camera', '1280x720')
    assert a[-2:] == ['-i', 'video=Integrated Camera'] and '-video_size' in a
    assert '-video_size' not in mm.camera_input_args('X', 'otomatik')


@test
def chapters_file_utf8_and_escaped():
    p = mm.write_chapters([(1.5, 'Bölüm 2; = #x'), (0.0, 'Bölüm 1')], 3.0, TMP / 'c.txt', offset=0.25)
    t = p.read_text(encoding='utf-8')
    assert t.startswith(';FFMETADATA1') and 'START=250' in t and 'START=1750' in t and 'END=3250' in t
    assert r'title=Bölüm 2\; \= \#x' in t


def probe(path, entries):
    return subprocess.run(['ffprobe', '-v', 'error', '-show_entries', entries, '-of', 'compact', str(path)],
                          capture_output=True, text=True).stdout


@needs_ff
def mp3_with_turkish_chapters():
    wav = mb.write_wav(TMP / 'v.wav', (np.random.RandomState(1).randn(48000 * 2, 1) * 0.1).astype(np.float32), 48000, 24)
    out = mm.to_mp3(FF, wav, marks=[(0.0, 'Bölüm 1: Giriş'), (1.0, 'Bölüm 2: Çıkış')])
    assert out.suffix == '.mp3' and out.stat().st_size > 1000
    assert not list(TMP.glob('*.part.mp3')) and not list(TMP.glob('*.chapters.txt'))
    if subprocess.run(['which', 'ffprobe'], capture_output=True).returncode == 0:
        pr = probe(out, 'stream=codec_name:chapter=start_time:chapter_tags=title')
        assert 'codec_name=mp3' in pr and 'title=Bölüm 2: Çıkış' in pr and 'start_time=1.000000' in pr


@needs_ff
def camera_preview_and_record_then_mux_in_sync():
    cam = mm.Camera(FF, LAVFI, preview=(240, 135))
    cam.start()
    assert cam.wait_first_frame(15)
    time.sleep(0.4)
    seq, ppm = cam.ppm()
    assert seq >= 2 and ppm.startswith(b'P6 240 135 255\n') and len(ppm) == len(b'P6 240 135 255\n') + 240 * 135 * 3
    assert cam.stop() is None and not cam.alive()
    mkv = TMP / 'k_kamera.mkv'
    cam.start(record_path=mkv)
    assert cam.wait_first_frame(15)
    t_v0 = cam.first_frame_t
    time.sleep(2.0)
    assert cam.stop() == mkv and mkv.stat().st_size > 1000
    vd = mm.probe_duration(FF, mkv)
    assert vd and vd > 1.0
    wav = mb.write_wav(TMP / 'k.wav', (np.random.RandomState(2).randn(48000 * 2, 2) * 0.1).astype(np.float32), 48000, 24)
    for shift, name in ((0.3, 'pos.mp4'), (-0.3, 'neg.mp4')):
        out = mm.mux_mp4(FF, mkv, wav, TMP / name, shift=shift, marks=[(0.0, 'Bölüm 1'), (1.0, 'Bölüm 2')])
        assert out.stat().st_size > 1000 and not list(TMP.glob('*.part.mp4'))
        if subprocess.run(['which', 'ffprobe'], capture_output=True).returncode == 0:
            pr = probe(out, 'stream=codec_type,codec_name,start_time:chapter=start_time:chapter_tags=title')
            assert 'codec_name=h264' in pr and 'codec_name=aac' in pr and 'title=Bölüm 2' in pr, pr
            starts = {ln.split('codec_type=')[1].split('|')[0]: float(ln.split('start_time=')[1].split('|')[0])
                      for ln in pr.splitlines() if ln.startswith('stream')}
            if shift > 0:
                assert abs(starts['video'] - 0.3) < 0.05 and starts['audio'] < 0.05, starts
            else:
                assert abs(starts['audio'] - 0.3) < 0.05 and starts['video'] < 0.05, starts
                assert '1.300000' in pr                                       # bolum de sesle kaydi
    assert t_v0 is not None


print('OK - %d test gecti: %s%s' % (len(PASSED), ', '.join(PASSED),
                                     ('  (ffmpeg yok, atlandi: %s)' % ', '.join(SKIPPED)) if SKIPPED else ''))
