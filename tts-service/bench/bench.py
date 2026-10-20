"""AGFO TTS deneme duzenegi: ayni Turkce metni EMA (calisan servis) ve Chatterbox Multilingual ile seslendirir,
sureleri olcer. Calisan EMA servisine dokunmaz; Chatterbox ayri bir venv'de calisir.
Kullanim: python bench.py CIKTI_KLASORU [REFERANS_SES]"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

OUT = sys.argv[1]
REF = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else ''
os.makedirs(OUT, exist_ok=True)

# Sayilar ve yabanci adlar yazili: yalniz ses kalitesi karsilastirilsin
TEXT = ("Geçen yıl İstanbul'da düzenlenen gıda güvenliği konferansında, fabrika yöneticileri denetim sonuçlarını tartıştı. "
        "Konuşmacılar, alerjen yönetiminin ve izlenebilirliğin en çok gözden kaçan iki konu olduğunu söyledi. "
        "Yeni dönemde hedef, her üretim hattında aynı titizliği göstermek ve çalışanların bu kültürü benimsemesini sağlamak.")
SENTENCES = [s for s in re.split(r'(?<=[.!?])\s+', TEXT) if s.strip()]
report = {'text_chars': len(TEXT), 'reference': REF or '(yerleşik ses)'}


def mp3(wav_path, mp3_path):
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', wav_path, '-b:a', '128k', mp3_path], check=True)


def audio_seconds(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


# 1) EMA: calisan servis
try:
    env = dict(l.split('=', 1) for l in open('/opt/agfo-tts/.env').read().split() if '=' in l)
    port = env.get('AGFO_TTS_PORT', '8765')
    req = urllib.request.Request('http://127.0.0.1:%s/tts' % port, data=json.dumps({'text': TEXT, 'format': 'mp3'}).encode(),
                                 headers={'X-AGFO-Token': env['AGFO_TTS_TOKEN'], 'Content-Type': 'application/json'})
    t = time.time()
    data = urllib.request.urlopen(req, timeout=300).read()
    el = time.time() - t
    p = os.path.join(OUT, '1-ema-kadin.mp3')
    open(p, 'wb').write(data)
    sec = audio_seconds(p)
    report['ema'] = {'seconds_to_generate': round(el, 2), 'audio_seconds': round(sec, 2), 'rtf': round(el / sec, 3) if sec else None}
    print('EMA: %.1f sn ses, %.1f sn sürdü' % (sec, el))
except Exception as e:
    report['ema'] = {'error': str(e)}
    print('EMA denemesi atlandı:', e)

# 2) Chatterbox Multilingual (Turkce)
import torch  # noqa: E402
import soundfile as sf  # noqa: E402
from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # noqa: E402

torch.set_num_threads(max(1, int(os.environ.get('BENCH_THREADS', '2'))))
t = time.time()
model = ChatterboxMultilingualTTS.from_pretrained(device='cpu')
report['chatterbox_load_seconds'] = round(time.time() - t, 1)
print('Chatterbox yüklendi: %.0f sn' % report['chatterbox_load_seconds'])
t = time.time()
pieces = []
for i, s in enumerate(SENTENCES):
    kw = {'language_id': 'tr'}
    if REF and i == 0:
        kw['audio_prompt_path'] = REF
    wav = model.generate(s, **kw)
    pieces.append(wav)
    pieces.append(torch.zeros(1, int(model.sr * 0.35)))
el = time.time() - t
full = torch.cat(pieces, dim=1)
wav_path = os.path.join(OUT, 'chatterbox.wav')
sf.write(wav_path, full.squeeze(0).numpy(), model.sr)
p = os.path.join(OUT, '2-chatterbox-%s.mp3' % ('referans' if REF else 'yerlesik'))
mp3(wav_path, p)
os.unlink(wav_path)
sec = full.shape[1] / model.sr
report['chatterbox'] = {'seconds_to_generate': round(el, 2), 'audio_seconds': round(sec, 2), 'rtf': round(el / sec, 3),
                        'threads': torch.get_num_threads()}
print('Chatterbox: %.1f sn ses, %.1f sn sürdü (RTF %.2f)' % (sec, el, el / sec))
if REF:
    # cfg_weight=0: referansin aksani Turkceye tasinmasin diye onerilen ayar
    t = time.time()
    pieces = []
    for s in SENTENCES:
        pieces.append(model.generate(s, language_id='tr', cfg_weight=0.0))
        pieces.append(torch.zeros(1, int(model.sr * 0.35)))
    full = torch.cat(pieces, dim=1)
    sf.write(wav_path, full.squeeze(0).numpy(), model.sr)
    mp3(wav_path, os.path.join(OUT, '3-chatterbox-referans-cfg0.mp3'))
    os.unlink(wav_path)
    report['chatterbox_cfg0_seconds'] = round(time.time() - t, 2)

# Uzun makale tahmini: 30.000 karakter
for k in ('ema', 'chatterbox'):
    r = report.get(k) or {}
    if r.get('seconds_to_generate'):
        report.setdefault('estimate_30k_chars_minutes', {})[k] = round(r['seconds_to_generate'] * 30000 / len(TEXT) / 60, 1)
json.dump(report, open(os.path.join(OUT, 'sonuc.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False, indent=2))
