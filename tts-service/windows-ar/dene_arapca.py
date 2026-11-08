# -*- coding: utf-8 -*-
"""AGFO Arapca ses denemesi - SILMA TTS (Apache-2.0) bu bilgisayarin ekran kartinda.

Ornek metinleri seslendirir, her biri icin sureyi ve hizi (RTF) olcer, sesleri masaustundeki
'AGFO-Arapca-Deneme' klasorune MP3 olarak yazar. Kendi referans sesinizle denemek icin:
    python dene_arapca.py --ses C:\\yol\\kayit.wav --ses-metni "kayittaki cumlenin yazisi"
Referans ses 5-15 saniyelik, gurultusuz bir kayit olmali; sesi kullanilan kisinin izni gerekir.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SAMPLES = [
    ('1-fusha-harekesiz', 'مرحبا، أنا صوت تجريبي يعمل على هذا الحاسوب. نقوم اليوم بتدقيق نظام سلامة الغذاء في المصنع، '
                          'ونراجع خطة تحليل المخاطر ونقاط التحكم الحرجة.'),
    ('2-sayilar', 'بدأ التدقيق في الساعة 9 صباحا واستمر 15 دقيقة في المستودع. تم فحص 240 عينة، '
                  'وكانت درجة حرارة غرفة التبريد 4 درجات مئوية.'),
    ('3-arapca-ingilizce', 'تستند هذه المراجعة إلى معيار BRCGS ومعيار IFS. '
                           'The audit report will be shared with the site within ten working days.'),
    ('4-uzun-paragraf', 'تهدف هذه الإجراءات إلى ضمان تحديد المواد المسببة للحساسية في جميع مراحل الإنتاج، '
                        'من استلام المواد الخام وحتى التعبئة والتغليف. ويتعين على فريق سلامة الغذاء مراجعة مصفوفة '
                        'المواد المسببة للحساسية مرة واحدة على الأقل في السنة، أو عند إدخال منتج جديد أو تغيير مورد. '
                        'كما يجب التحقق من فعالية التنظيف بين دفعات الإنتاج المختلفة وتسجيل النتائج.'),
]
REF_TEXT = 'ويدقق النظر في القرآن الكريم وسائر الكتب السماوية ويتبع مسالك الرسل العظام عليهم الصلاة والسلام.'


def numbers_to_words(text: str) -> str:
    """Rakamlari Arapca okunusa cevirir (nemo normalizer Windows'ta calismadigi icin)."""
    try:
        from num2words import num2words
    except ImportError:
        return text

    def repl(m):
        try:
            return num2words(int(m.group(0)), lang='ar')
        except (NotImplementedError, ValueError, OverflowError):
            return m.group(0)
    if not re.search(r'[\u0600-\u06FF]', text):
        return text
    return re.sub(r'(?<![A-Za-z])\d+(?![A-Za-z])', repl, text)


def to_mp3(ffmpeg: str, wav: Path, mp3: Path) -> bool:
    try:
        subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-i', str(wav), '-codec:a', 'libmp3lame', '-b:a', '128k', str(mp3)],
                       check=True, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        wav.unlink(missing_ok=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--ses', help='referans ses dosyasi (wav/mp3, 5-15 sn)')
    ap.add_argument('--ses-metni', default=None, help='referans sesteki cumlenin yazisi')
    ap.add_argument('--cikti', default=str(Path.home() / 'Desktop' / 'AGFO-Arapca-Deneme'))
    ap.add_argument('--ffmpeg', default=os.environ.get('AGFO_TTS_FFMPEG', 'ffmpeg'))
    ap.add_argument('--adim', type=int, default=16, help='cizim adimi (16 varsayilan; 32 daha temiz, daha yavas)')
    args = ap.parse_args()

    out = Path(args.cikti)
    out.mkdir(parents=True, exist_ok=True)
    import torch
    from importlib.resources import files
    from silma_tts.api import SilmaTTS

    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    print('torch %s, aygit: %s%s' % (torch.__version__, dev,
                                     (' (' + torch.cuda.get_device_name(0) + ')') if dev == 'cuda' else ''), flush=True)
    t0 = time.time()
    tts = SilmaTTS(enable_normalizer=False, force_tashkeel=True, device=dev)
    print('Model yuklendi: %.1f sn' % (time.time() - t0), flush=True)

    if args.ses:
        ref_file, ref_text = args.ses, args.ses_metni
        if not ref_text:
            print('Uyari: --ses-metni verilmedi; kayit konusma tanima ile yaziya dokulecek (ilk seferde buyuk bir model iner).',
                  flush=True)
    else:
        ref_file, ref_text = str(files('silma_tts').joinpath('infer/ref_audio_samples/ar.ref.24k.wav')), REF_TEXT

    report = {'device': dev, 'gpu': torch.cuda.get_device_name(0) if dev == 'cuda' else '', 'torch': torch.__version__,
              'nfe_step': args.adim, 'samples': []}
    first = True
    for name, text in SAMPLES:
        spoken = numbers_to_words(text)
        if dev == 'cuda':
            torch.cuda.reset_peak_memory_stats()
        t = time.time()
        wav, sr, _spec = tts.infer(ref_file=ref_file, ref_text=ref_text, gen_text=spoken, file_wave=str(out / (name + '.wav')),
                                   seed=1234, speed=1.0, nfe_step=args.adim, normalize_numbers=False)
        took = time.time() - t
        secs = len(wav) / float(sr)
        rtf = took / secs if secs else 0
        mem = torch.cuda.max_memory_allocated() / 2 ** 30 if dev == 'cuda' else 0
        mp3 = to_mp3(args.ffmpeg, out / (name + '.wav'), out / (name + '.mp3'))
        note = ' (ilk parca: isinma dahil)' if first else ''
        first = False
        print('%-22s %5.1f sn ses, %5.1f sn surdu, RTF %.2f, GPU bellek %.1f GB%s' % (name, secs, took, rtf, mem, note), flush=True)
        report['samples'].append({'name': name, 'audio_s': round(secs, 2), 'took_s': round(took, 2), 'rtf': round(rtf, 3),
                                  'vram_gb': round(mem, 2), 'mp3': mp3})
    (out / 'sonuc.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\nSesler: %s' % out, flush=True)
    print('RTF 1\'in altindaysa ses, suresinden hizli uretiliyor demektir (0.2 = 10 sn sesi 2 sn\'de).', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
