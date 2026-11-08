# -*- coding: utf-8 -*-
"""AGFO Yerel Ses Servisi - bu bilgisayarin ekran kartinda Arapca (SILMA TTS, Habibi-TTS) ya da
Ingilizce / Ispanyolca (Qwen3-TTS).

Turkce AGFO TTS Service (EMA Lightning) ile ayni API'yi sunar; AGFO AI Editor onu ayni sekilde kullanir:
  GET  /health             durum (motor, aygit, ses sayisi)
  GET  /voices             kullanilabilir sesler
  POST /tts                {"text", "voice", "speed", "paragraph_pause_ms", "format", "seed"} -> ses dosyasi
  GET  /lexicon            bos liste (Arapca icin telaffuz sozlugu yok; editorun sozluk penceresi bozulmasin)
Her istekte X-AGFO-Token basligi zorunludur. Ayarlar .env dosyasindan okunur (run_ar.py):
  AGFO_TTS_ENGINE   silma | habibi | qwen
  AGFO_TTS_QWEN_SIZE  1.7B (varsayilan) | 0.6B
  AGFO_TTS_QWEN_DIR   indirilmis Qwen modellerinin klasoru (yoksa Hugging Face onbellegi)
  AGFO_TTS_NFE      cizim adimi (varsayilan 32; 16 daha hizli)
Sesler (referans kayitlar) iki yerden gelir: motorun hazir sesleri ve DATA_DIR/voices klasoru. Kendi sesinizi
eklemek icin oraya 5-15 saniyelik bir kayit (ad.wav ya da ad.mp3) ve kayittaki cumlenin yazisini (ad.txt) koyun.
Habibi'de dosya adi __EGY ya da __MSA ile biterse o lehce modeli kullanilir (varsayilan EGY). Sesi kullanilan kisinin
izni gerekir.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

VERSION = '1.1.0'
ENGINE = os.environ.get('AGFO_TTS_ENGINE', 'silma').strip().lower()
TOKEN = os.environ.get('AGFO_TTS_TOKEN', '')
CACHE_DIR = Path(os.environ.get('AGFO_TTS_CACHE_DIR', './cache'))
DATA_DIR = Path(os.environ.get('AGFO_TTS_DATA_DIR', './data'))
VOICES_DIR = DATA_DIR / 'voices'
FFMPEG = os.environ.get('AGFO_TTS_FFMPEG', 'ffmpeg')
NFE = int(os.environ.get('AGFO_TTS_NFE', '32'))
MAX_CHARS = 20_000
AUDIO_EXT = ('.wav', '.mp3', '.flac')

CACHE_DIR.mkdir(parents=True, exist_ok=True)
VOICES_DIR.mkdir(parents=True, exist_ok=True)
app = FastAPI(title='AGFO Yerel Ses Servisi', version=VERSION)
_lock = threading.Lock()

SILMA_REF_TEXT = 'ويدقق النظر في القرآن الكريم وسائر الكتب السماوية ويتبع مسالك الرسل العظام عليهم الصلاة والسلام.'
EGY_REF_TEXT = 'ايه الكلام. بقولك ايه. استخدم صوتي في المحادثات. استخدمه هيعجبك اوي.'
MSA_REF_TEXT = ('كان اللعيب حاضرًا في العديد من الأنشطة والفعاليات المرتبطة بكأس العالم، مما سمح للجماهير بالتفاعل معه '
                'والتقاط الصور التذكارية.')


# ------------------------------------------------------------------------------------------- yardimcilar
def numbers_to_words(text: str) -> str:
    """Arapca cumledeki rakamlari okunusa cevirir (SILMA'nin sayi normalizer'i Windows'ta yok)."""
    if not re.search(r'[؀-ۿ]', text):
        return text
    try:
        from num2words import num2words
    except ImportError:
        return text

    def repl(m):
        try:
            return num2words(int(m.group(0)), lang='ar')
        except (NotImplementedError, ValueError, OverflowError):
            return m.group(0)
    return re.sub(r'(?<![A-Za-z])\d+(?![A-Za-z])', repl, text)


_ES_WORDS = set('el la los las de que y en un una por para con del al es se no lo como pero sus su más este esta '
                'son están está fue han debe deberá durante entre sobre también'.split())
_EN_WORDS = set('the and of to in is that for with on as was by be are this it from at which shall must will has have'.split())


def detect_lang(text: str) -> str:
    """Qwen3 icin paragraf dili: 'spanish' ya da 'english' (kaba ama yeterli)."""
    if re.search(r'[ñÑ¿¡]', text):
        return 'spanish'
    words = re.findall(r"[a-záéíóúü]+", text.lower())
    es = sum(w in _ES_WORDS for w in words) + 2 * len(re.findall(r'[áéíóú]', text.lower()))
    en = sum(w in _EN_WORDS for w in words)
    return 'spanish' if es > en else 'english'


def split_sentences(text: str, limit: int = 320) -> list[str]:
    """Uzun paragrafi cumle sinirindan parcalara boler (otoregresif model uzun metinde kelime atlayabilir)."""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ''
    for sent in re.split(r'(?<=[.!?;:])\s+', text):
        if cur and len(cur) + len(sent) + 1 > limit:
            parts.append(cur)
            cur = sent
        else:
            cur = (cur + ' ' + sent).strip()
    if cur:
        parts.append(cur)
    out = []
    for p in parts:                                   # tek cumle sinirdan uzunsa virgulden bol
        while len(p) > limit * 1.5:
            cut = p.rfind(', ', 0, limit)
            if cut < limit // 3:
                break
            out.append(p[:cut + 1])
            p = p[cut + 2:]
        out.append(p)
    return out


def retime(wav_bytes: bytes, speed: float) -> bytes:
    """Hiz ayari olmayan motorlarda (Qwen3) ffmpeg atempo ile perde bozulmadan hizlandirir/yavaslatir."""
    if abs(speed - 1.0) < 0.01:
        return wav_bytes
    p = subprocess.run([FFMPEG, '-loglevel', 'error', '-i', 'pipe:0', '-filter:a', 'atempo=%.3f' % speed, '-f', 'wav', 'pipe:1'],
                       input=wav_bytes, capture_output=True, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return p.stdout


def _ref_text_for(path: Path) -> str:
    txt = path.with_suffix('.txt')
    try:
        return txt.read_text(encoding='utf-8-sig').strip()
    except OSError:
        return ''


def user_voices() -> list[dict]:
    out = []
    for p in sorted(VOICES_DIR.iterdir()) if VOICES_DIR.is_dir() else []:
        if p.suffix.lower() not in AUDIO_EXT:
            continue
        stem = p.stem
        dialect = 'MSA' if stem.upper().endswith('__MSA') else 'EGY'
        name = re.sub(r'__(EGY|MSA)$', '', stem, flags=re.I)
        out.append({'id': 'u-' + stem, 'name': name, 'file': str(p), 'text': _ref_text_for(p), 'dialect': dialect, 'user': True})
    return out


def to_mp3(wav_bytes: bytes) -> bytes:
    p = subprocess.run([FFMPEG, '-loglevel', 'error', '-i', 'pipe:0', '-codec:a', 'libmp3lame', '-b:a', '96k', '-f', 'mp3', 'pipe:1'],
                       input=wav_bytes, capture_output=True, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return p.stdout


# ------------------------------------------------------------------------------------------- motorlar
class SilmaEngine:
    label = 'SILMA TTS'

    def __init__(self):
        self.tts = None
        self.device = 'cpu'

    def builtin(self) -> list[dict]:
        from importlib.resources import files
        out = [{'id': 'fusha', 'name': 'Fusha (SILMA örnek sesi)', 'file': str(files('silma_tts').joinpath('infer/ref_audio_samples/ar.ref.24k.wav')),
                'text': SILMA_REF_TEXT, 'dialect': 'MSA'}]
        egy = DATA_DIR / 'misirli.mp3'
        if egy.exists():
            out.append({'id': 'misirli', 'name': 'Mısırlı ses (deneme kaydı)', 'file': str(egy), 'text': EGY_REF_TEXT, 'dialect': 'EGY'})
        return out

    def load(self):
        if self.tts is None:
            import torch
            from silma_tts.api import SilmaTTS
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            self.tts = SilmaTTS(enable_normalizer=False, force_tashkeel=True, device=self.device)

    def say(self, text: str, voice: dict, speed: float, seed: int):
        self.load()
        wav, sr, _spec = self.tts.infer(ref_file=voice['file'], ref_text=voice['text'] or None, gen_text=text, seed=seed or 1234,
                                        speed=speed, nfe_step=NFE, normalize_numbers=False, progress=None, show_info=_noop)
        return np.asarray(wav, dtype=np.float32), int(sr)


class HabibiEngine:
    label = 'Habibi-TTS'
    STEPS = {'MSA': 200000, 'EGY': 100000}

    def __init__(self):
        self.models = {}
        self.vocoder = None
        self.refs = {}
        self.device = 'cpu'

    def builtin(self) -> list[dict]:
        from importlib.resources import files
        a = files('habibi_tts').joinpath('assets')
        return [{'id': 'misir', 'name': 'Mısır (Habibi Mısır modeli)', 'file': str(a.joinpath('EGY.mp3')), 'text': EGY_REF_TEXT, 'dialect': 'EGY'},
                {'id': 'fusha', 'name': 'Fusha (Habibi Fusha modeli)', 'file': str(a.joinpath('MSA.mp3')), 'text': MSA_REF_TEXT, 'dialect': 'MSA'}]

    def _model(self, dialect: str):
        if dialect not in self.models:
            from importlib.resources import files
            from cached_path import cached_path
            from hydra.utils import get_class
            from omegaconf import OmegaConf
            from f5_tts.infer.utils_infer import load_model, load_vocoder
            from habibi_tts.infer.utils_infer import device
            self.device = device
            cfg = OmegaConf.load(str(files('f5_tts').joinpath('configs/F5TTS_v1_Base.yaml')))
            cls = get_class('f5_tts.model.%s' % cfg.model.backbone)
            step = self.STEPS[dialect]
            ckpt = str(cached_path('hf://SWivid/Habibi-TTS/Specialized/%s/model_%d.safetensors' % (dialect, step)))
            vocab = str(cached_path('hf://SWivid/Habibi-TTS/Specialized/%s/vocab.txt' % dialect))
            self.models[dialect] = load_model(cls, cfg.model.arch, ckpt, mel_spec_type=cfg.model.mel_spec.mel_spec_type,
                                              vocab_file=vocab, device=device)
            if self.vocoder is None:
                self.vocoder = load_vocoder(vocoder_name=cfg.model.mel_spec.mel_spec_type, is_local=False, device=device)
        return self.models[dialect]

    def load(self):
        self._model('EGY')

    def say(self, text: str, voice: dict, speed: float, seed: int):
        from f5_tts.infer.utils_infer import preprocess_ref_audio_text
        from habibi_tts.infer.utils_infer import infer_process
        model = self._model(voice.get('dialect') or 'EGY')
        key = voice['file']
        if key not in self.refs:
            self.refs[key] = preprocess_ref_audio_text(voice['file'], voice['text'] or '', show_info=_noop)
        ref_audio, ref_text = self.refs[key]
        if seed:
            import torch
            torch.manual_seed(seed)
        wave, sr, _spec = infer_process(ref_audio, ref_text, text, model, self.vocoder, mel_spec_type='vocos', nfe_step=NFE,
                                        speed=speed, device=self.device, show_info=_noop, progress=None)
        return np.asarray(wave, dtype=np.float32), int(sr)


class QwenEngine:
    """Qwen3-TTS (Apache-2.0): hazir sesler CustomVoice modeliyle, data/voices kayitlari Base (klon) modeliyle.
    8 GB ekran kartinda iki 1.7B model birlikte tutulmaz; gerekince digeri bosaltilir."""
    label = 'Qwen3-TTS'
    native_speed = False
    SIZE = os.environ.get('AGFO_TTS_QWEN_SIZE', '1.7B')
    SPEAKERS = [('aiden', 'Aiden', 'Aiden (erkek, Amerikan İngilizcesi)'), ('ryan', 'Ryan', 'Ryan (erkek, İngilizce)'),
                ('serena', 'Serena', 'Serena (kadın, sıcak)'), ('vivian', 'Vivian', 'Vivian (kadın, canlı)'),
                ('ono_anna', 'Ono_Anna', 'Ono Anna (kadın, hafif)'), ('sohee', 'Sohee', 'Sohee (kadın, duygulu)'),
                ('uncle_fu', 'Uncle_Fu', 'Uncle Fu (erkek, tok)')]

    def __init__(self):
        self.kind = None
        self.model = None
        self.prompts = {}
        self.device = 'cpu'

    def builtin(self) -> list[dict]:
        return [{'id': vid, 'name': name, 'file': '', 'text': '', 'speaker': spk} for vid, spk, name in self.SPEAKERS]

    def _load(self, kind: str):
        if self.kind == kind and self.model is not None:
            return self.model
        import torch
        from qwen_tts import Qwen3TTSModel
        if self.model is not None:
            self.model = None
            self.prompts = {}
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        self.device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        dtype = torch.bfloat16 if self.device.startswith('cuda') else torch.float32
        name = 'Qwen3-TTS-12Hz-%s-%s' % (self.SIZE, 'CustomVoice' if kind == 'custom' else 'Base')
        local = os.path.join(os.environ.get('AGFO_TTS_QWEN_DIR', ''), name)
        repo = local if os.environ.get('AGFO_TTS_QWEN_DIR') and os.path.isdir(local) else 'Qwen/' + name
        self.model = Qwen3TTSModel.from_pretrained(repo, device_map=self.device, dtype=dtype, attn_implementation='sdpa')
        self.kind = kind
        return self.model

    def load(self):
        self._load('custom')

    def say(self, text: str, voice: dict, speed: float, seed: int):
        import torch
        lang = detect_lang(text)
        if seed:
            torch.manual_seed(seed)
        pieces, sr = [], 24000
        for chunk in split_sentences(text):
            if voice.get('speaker'):
                m = self._load('custom')
                wavs, sr = m.generate_custom_voice(text=chunk, language=lang, speaker=voice['speaker'])
            else:
                m = self._load('base')
                key = voice['file']
                if key not in self.prompts:
                    rt = voice.get('text') or ''
                    self.prompts[key] = m.create_voice_clone_prompt(ref_audio=voice['file'], ref_text=rt or None,
                                                                    x_vector_only_mode=not rt)
                wavs, sr = m.generate_voice_clone(text=chunk, language=lang, voice_clone_prompt=self.prompts[key])
            pieces.append(np.asarray(wavs[0], dtype=np.float32))
            pieces.append(np.zeros(int(sr * 0.12), dtype=np.float32))
        return np.concatenate(pieces[:-1] or pieces), int(sr)


def _noop(*_a, **_k):
    return None


engine = {'habibi': HabibiEngine, 'qwen': QwenEngine}.get(ENGINE, SilmaEngine)()


def voices() -> list[dict]:
    try:
        base = engine.builtin()
    except Exception:
        base = []
    return [v for v in base if not v['file'] or Path(v['file']).exists()] + user_voices()


def find_voice(vid: str) -> dict:
    vs = voices()
    if not vs:
        raise HTTPException(status_code=500, detail='Kullanılabilir referans ses yok.')
    return next((v for v in vs if v['id'] == vid), vs[0])


# ------------------------------------------------------------------------------------------- API
def check_token(tok: str | None):
    if not TOKEN or tok != TOKEN:
        raise HTTPException(status_code=401, detail='invalid token')


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_CHARS)
    voice: str = ''
    speed: float = Field(1.0, ge=0.5, le=1.5)
    pause_ms: int = Field(350, ge=0, le=2000)                # uyumluluk; cumle arasi motorun kendisinde
    paragraph_pause_ms: int = Field(700, ge=0, le=3000)
    format: str = Field('mp3', pattern='^(mp3|wav)$')
    apply_lexicon: bool = True                               # uyumluluk; Arapca sozluk yok
    seed: int = 0


@app.get('/health')
def health(x_agfo_token: str | None = Header(default=None)):
    check_token(x_agfo_token)
    try:
        import torch
        dev = 'cuda' if torch.cuda.is_available() else 'cpu'
        gpu = torch.cuda.get_device_name(0) if dev == 'cuda' else ''
    except Exception:
        dev, gpu = 'cpu', ''
    return {'ok': True, 'version': VERSION, 'model': ENGINE, 'engine': engine.label,
            'language': os.environ.get('AGFO_TTS_LANG') or ('en' if ENGINE == 'qwen' else 'ar'), 'device': dev,
            'gpu': gpu, 'voices': len(voices()), 'lexicon_entries': 0,
            'loaded': bool(getattr(engine, 'tts', None) or getattr(engine, 'models', None) or getattr(engine, 'model', None))}


@app.get('/voices')
def list_voices(x_agfo_token: str | None = Header(default=None)):
    check_token(x_agfo_token)
    vs = voices()
    return {'engine': ENGINE, 'voices': [{'id': v['id'], 'name': v['name'], 'dialect': v.get('dialect', ''), 'user': bool(v.get('user'))}
                                         for v in vs], 'default': vs[0]['id'] if vs else '', 'folder': str(VOICES_DIR)}


@app.get('/lexicon')
def lexicon_list(x_agfo_token: str | None = Header(default=None)):
    check_token(x_agfo_token)
    return {'entries': [], 'count': 0, 'base': 0, 'custom': 0, 'note': 'Bu ses için telaffuz sözlüğü yok.'}


@app.post('/tts')
def synthesize(req: TTSRequest, x_agfo_token: str | None = Header(default=None)):
    check_token(x_agfo_token)
    voice = find_voice(req.voice)
    vstamp = '%s|%s|%s' % (voice.get('speaker', ''), voice['file'],
                           os.path.getmtime(voice['file']) if voice['file'] and os.path.exists(voice['file']) else 0)
    key = hashlib.sha256(('%s|%s|%d|%s' % (ENGINE, req.model_dump_json(), NFE, vstamp)).encode('utf-8')).hexdigest()
    cached = CACHE_DIR / ('%s.%s' % (key, req.format))
    if cached.exists():
        try:
            secs = float(cached.with_suffix(cached.suffix + '.sec').read_text())
        except (OSError, ValueError):
            secs = None
        return _audio(cached.read_bytes(), req.format, True, secs)
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', req.text) if p.strip()]
    if not paragraphs:
        raise HTTPException(status_code=400, detail='no speakable text')
    pieces, sr = [], 24000
    with _lock:
        for i, para in enumerate(paragraphs):
            text = numbers_to_words(' '.join(para.split()))
            native = getattr(engine, 'native_speed', True)
            audio, sr = engine.say(text, voice, req.speed if native else 1.0, req.seed)
            pieces.append(audio)
            if i < len(paragraphs) - 1 and req.paragraph_pause_ms:
                pieces.append(np.zeros(int(sr * req.paragraph_pause_ms / 1000), dtype=np.float32))
    full = np.concatenate(pieces)
    buf = io.BytesIO()
    sf.write(buf, full, sr, format='WAV', subtype='PCM_16')
    data = buf.getvalue()
    if not getattr(engine, 'native_speed', True) and abs(req.speed - 1.0) >= 0.01:
        data = retime(data, req.speed)
        full = full[:int(len(full) / req.speed)]                 # sure hesabi icin
    if req.format == 'mp3':
        data = to_mp3(data)
    cached.write_bytes(data)
    secs = len(full) / float(sr)
    try:
        cached.with_suffix(cached.suffix + '.sec').write_text('%.2f' % secs)
    except OSError:
        pass
    return _audio(data, req.format, False, secs)


def _audio(data: bytes, fmt: str, cached: bool, seconds: float | None):
    headers = {'X-AGFO-Cached': '1' if cached else '0'}
    if seconds is not None:
        headers['X-AGFO-Seconds'] = '%.2f' % seconds
    return Response(content=data, media_type='audio/mpeg' if fmt == 'mp3' else 'audio/wav', headers=headers)
