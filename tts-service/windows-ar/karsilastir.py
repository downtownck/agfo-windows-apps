# -*- coding: utf-8 -*-
"""AGFO Arapca ses karsilastirmasi - Habibi-TTS (Misir ve Fusha modelleri) ile ornek sesler.

Habibi-TTS'in yalniz Apache-2.0 lisansli 'Specialized' modelleri kullanilir: EGY (Misir) ve MSA (Fusha).
Her ornek ayri bir surecte habibi_tts.infer.infer_cli ile uretilir; sure olculur, MP3'e cevrilir.
Referans sesler paketle gelen ornek kayitlardir (yalniz deneme icin; urunde kendi izinli sesimiz kullanilacak).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

AUDIT_MSA = ('نقوم اليوم بتدقيق نظام سلامة الغذاء في المصنع، ونراجع خطة تحليل المخاطر ونقاط التحكم الحرجة. '
             'وسيتم إرسال تقرير التدقيق إلى الموقع خلال عشرة أيام عمل.')
AUDIT_EGY = ('أهلا بيك، النهارده هنراجع نظام سلامة الغذاء في المصنع، وهنبص على خطة تحليل المخاطر ونقط التحكم الحرجة. '
             'التقرير هيوصلكم خلال عشر أيام شغل.')
REF = {
    'EGY': ('EGY.mp3', 'ايه الكلام. بقولك ايه. استخدم صوتي في المحادثات. استخدمه هيعجبك اوي.'),
    'MSA': ('MSA.mp3', 'كان اللعيب حاضرًا في العديد من الأنشطة والفعاليات المرتبطة بكأس العالم، مما سمح للجماهير بالتفاعل معه والتقاط الصور التذكارية.'),
}
RUNS = [
    # (dosya adi, model lehcesi, referans, metin, aciklama)
    ('A-misir-modeli-fusha-metin', 'EGY', 'EGY', AUDIT_MSA, 'Misir modeli, Misirli ses, Fusha denetim metni'),
    ('B-misir-modeli-misir-agzi', 'EGY', 'EGY', AUDIT_EGY, 'Misir modeli, Misirli ses, Misir agziyla ayni icerik'),
    ('C-fusha-modeli', 'MSA', 'MSA', AUDIT_MSA, 'Fusha modeli, Fusha ses, Fusha denetim metni'),
]


def to_mp3(ffmpeg, wav: Path, mp3: Path) -> bool:
    try:
        subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-i', str(wav), '-codec:a', 'libmp3lame', '-b:a', '128k', str(mp3)],
                       check=True, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        wav.unlink(missing_ok=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--cikti', required=True)
    ap.add_argument('--ffmpeg', default='ffmpeg')
    ap.add_argument('--adim', type=int, default=32)
    args = ap.parse_args()
    out = Path(args.cikti)
    out.mkdir(parents=True, exist_ok=True)
    from importlib.resources import files
    assets = files('habibi_tts').joinpath('assets')
    for key, (name, _t) in REF.items():                      # referans kayitlar da dinlenebilsin
        src = Path(str(assets.joinpath(name)))
        try:
            (out / ('referans-%s%s' % (key.lower(), src.suffix))).write_bytes(src.read_bytes())
        except OSError:
            pass
    report = []
    for fname, dialect, ref_key, text, note in RUNS:
        ref_name, ref_text = REF[ref_key]
        cmd = [sys.executable, '-m', 'habibi_tts.infer.infer_cli', '--model', 'Specialized', '--dialect', dialect,
               '--ref_audio', str(assets.joinpath(ref_name)), '--ref_text', ref_text, '--gen_text', text,
               '--output_dir', str(out), '--output_file', fname + '.wav', '--nfe_step', str(args.adim)]
        t = time.time()
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        took = time.time() - t
        wav = out / (fname + '.wav')
        if p.returncode != 0 or not wav.exists():
            tail = '\n'.join((p.stderr or p.stdout or '').strip().splitlines()[-15:])
            print('%-30s HATA\n%s' % (fname, tail), flush=True)
            report.append({'name': fname, 'ok': False, 'error': tail})
            continue
        try:
            import soundfile as sf
            secs = sf.info(str(wav)).duration
        except Exception:
            secs = 0.0
        mp3 = to_mp3(args.ffmpeg, wav, out / (fname + '.mp3'))
        print('%-30s %5.1f sn ses, %5.1f sn surdu (model yukleme dahil)  - %s' % (fname, secs, took, note), flush=True)
        report.append({'name': fname, 'ok': True, 'audio_s': round(secs, 2), 'took_s': round(took, 2), 'mp3': mp3, 'note': note})
    (out / 'sonuc.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if any(r['ok'] for r in report) else 1


if __name__ == '__main__':
    sys.exit(main())
