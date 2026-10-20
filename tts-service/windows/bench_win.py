"""AGFO ses denemesi (Windows, ekran karti): ayni Turkce metni EMA (bu bilgisayardaki servis), Chatterbox Multilingual
ve varsa Piper "Cem" ile seslendirir, sureleri olcer. EMA servisine dokunmaz; bu betik ayri bir sanal ortamda calisir.

Kullanim: python bench_win.py CIKTI_KLASORU [REFERANS_SES] [PIPER_MODEL.onnx]
REFERANS_SES: Chatterbox'in taklit edecegi 10-25 sn'lik temiz bir konusma kaydi (erkek ses icin bir erkek kaydi).
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ARGS = [a if a != '-' else '' for a in sys.argv[1:]] + ['', '', '']   # '-' = bos (PowerShell 5.1 bos argumani atar)
OUT, REF, PIPER = ARGS[0], ARGS[1], ARGS[2]
TTS_DIR = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AGFO', 'TTS')
os.makedirs(OUT, exist_ok=True)


def read_env():
    env = {}
    try:
        with open(os.path.join(TTS_DIR, '.env'), encoding='utf-8-sig') as fh:
            for line in fh:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    env[k] = v
    except OSError:
        pass
    return env


ENV = read_env()
FFMPEG = ENV.get('AGFO_TTS_FFMPEG') or 'ffmpeg'

TEXT = ("Geçen yıl İstanbul'da düzenlenen gıda güvenliği konferansında, fabrika yöneticileri denetim sonuçlarını tartıştı. "
        "Konuşmacılar, alerjen yönetiminin ve izlenebilirliğin en çok gözden kaçan iki konu olduğunu söyledi. "
        "Yeni dönemde hedef, her üretim hattında aynı titizliği göstermek ve çalışanların bu kültürü benimsemesini sağlamak.")
SENTENCES = [s for s in re.split(r'(?<=[.!?])\s+', TEXT) if s.strip()]
report = {'text_chars': len(TEXT), 'reference': REF or '(yerleşik ses)'}


def mp3(wav_path, mp3_path):
    subprocess.run([FFMPEG, '-loglevel', 'error', '-y', '-i', wav_path, '-b:a', '128k', mp3_path], check=True)
    os.unlink(wav_path)


def note(key, el, sec):
    report[key] = {'seconds_to_generate': round(el, 2), 'audio_seconds': round(sec, 2), 'rtf': round(el / sec, 3) if sec else None}
    print('%s: %.1f sn ses, %.1f sn sürdü' % (key, sec, el), flush=True)


# 1) EMA: bu bilgisayardaki servis
try:
    port = ENV.get('AGFO_TTS_PORT', '8765')
    req = urllib.request.Request('http://127.0.0.1:%s/tts' % port, data=json.dumps({'text': TEXT, 'format': 'mp3'}).encode(),
                                 headers={'X-AGFO-Token': ENV['AGFO_TTS_TOKEN'], 'Content-Type': 'application/json'})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    t = time.time()
    with op.open(req, timeout=600) as r:
        data = r.read()
        sec = float(r.headers.get('X-AGFO-Seconds') or 0)
    with open(os.path.join(OUT, '1-ema-kadin.mp3'), 'wb') as fh:
        fh.write(data)
    note('ema', time.time() - t, sec)
except Exception as e:  # servis kapali olabilir; diger denemeler surer
    report['ema'] = {'error': str(e)}
    print('EMA denemesi atlandı:', e, flush=True)

import soundfile as sf  # noqa: E402
import torch  # noqa: E402

DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
report['device'] = DEVICE + (' (%s)' % torch.cuda.get_device_name(0) if DEVICE == 'cuda' else '')
print('Aygıt:', report['device'], flush=True)

# 2) Chatterbox Multilingual (Turkce)
try:
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    t = time.time()
    model = ChatterboxMultilingualTTS.from_pretrained(device=DEVICE)
    report['chatterbox_load_seconds'] = round(time.time() - t, 1)
    print('Chatterbox yüklendi: %.0f sn' % report['chatterbox_load_seconds'], flush=True)
    variants = [('2-chatterbox-%s' % ('referans' if REF else 'yerlesik'), {})]
    if REF:
        variants.append(('3-chatterbox-referans-sakin', {'cfg_weight': 0.0}))   # referansin aksani tasinmasin
    for name, extra in variants:
        t = time.time()
        pieces = []
        for s in SENTENCES:
            kw = dict(language_id='tr', **extra)
            if REF:
                kw['audio_prompt_path'] = REF
            pieces.append(model.generate(s, **kw).cpu())
            pieces.append(torch.zeros(1, int(model.sr * 0.35)))
        el = time.time() - t
        full = torch.cat(pieces, dim=1)
        wav = os.path.join(OUT, name + '.wav')
        sf.write(wav, full.squeeze(0).numpy(), model.sr)
        mp3(wav, os.path.join(OUT, name + '.mp3'))
        note(name, el, full.shape[1] / model.sr)
    del model
    if DEVICE == 'cuda':
        torch.cuda.empty_cache()
except Exception as e:
    report['chatterbox'] = {'error': str(e)}
    print('Chatterbox denemesi başarısız:', e, flush=True)

# 3) Piper "Cem" (Hugging Face onayi ve modeli gerekir)
if PIPER:
    try:
        exe = os.path.join(os.path.dirname(sys.executable), 'piper.exe')
        wav = os.path.join(OUT, '4-piper-cem.wav')
        t = time.time()
        subprocess.run([exe, '--model', PIPER, '--output_file', wav], input=TEXT.encode('utf-8'), check=True)
        el = time.time() - t
        info = sf.info(wav)
        mp3(wav, os.path.join(OUT, '4-piper-cem.mp3'))
        note('piper_cem', el, info.duration)
    except Exception as e:
        report['piper_cem'] = {'error': str(e)}
        print('Piper denemesi başarısız:', e, flush=True)

with open(os.path.join(OUT, 'sonuc.json'), 'w', encoding='utf-8') as fh:
    json.dump(report, fh, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False, indent=2))
