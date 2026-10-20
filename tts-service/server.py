"""AGFO TTS Service - thin HTTP wrapper around EMA Lightning.

One EMA instance for the whole server, one request per call.
Adds on top of the model: shared-token auth, pronunciation lexicon,
sentence-level pauses, MP3 encoding, and a content-hash cache.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ema_lightning import EMA

TOKEN = os.environ.get("AGFO_TTS_TOKEN", "")
THREADS = int(os.environ.get("AGFO_TTS_THREADS", "4"))
CACHE_DIR = Path(os.environ.get("AGFO_TTS_CACHE_DIR", "./cache"))
LEXICON_PATH = Path(__file__).with_name("lexicon.json")          # shipped list, replaced on update
DATA_DIR = Path(os.environ.get("AGFO_TTS_DATA_DIR", str(Path(__file__).with_name("data"))))
CUSTOM_PATH = DATA_DIR / "lexicon.custom.json"                    # edits from WordPress; survives updates
MAX_CUSTOM = 20_000
MAX_CHARS = 60_000  # roughly a very long article
FFMPEG = os.environ.get("AGFO_TTS_FFMPEG", "ffmpeg")  # 1.1.1: full path on Windows installs

try:
    import torch
    torch.set_num_threads(THREADS)
except Exception:
    pass

CACHE_DIR.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="AGFO TTS Service", version="1.1.1")
tts = EMA()
tts_lock = threading.Lock()

_lexicon: dict[str, str] = {}
_base: dict[str, str] = {}
_custom: dict[str, str | None] = {}
_lexicon_mtime = ""          # signature of both files; part of the audio cache key
_write_lock = threading.Lock()


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def load_lexicon() -> dict[str, str]:
    """Shipped lexicon.json + data/lexicon.custom.json (a null value removes a shipped word)."""
    global _lexicon, _base, _custom, _lexicon_mtime
    sig = f"{_mtime(LEXICON_PATH)}:{_mtime(CUSTOM_PATH)}"
    if sig != _lexicon_mtime:
        _base = {str(k): str(v) for k, v in _read_json(LEXICON_PATH).items() if k and v}
        _custom = {str(k): (None if v is None else str(v)) for k, v in _read_json(CUSTOM_PATH).items() if k}
        merged = dict(_base)
        for k, v in _custom.items():
            if v is None:
                merged.pop(k, None)
            else:
                merged[k] = v
        _lexicon = merged
        _lexicon_mtime = sig
    return _lexicon


def _save_custom(custom: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CUSTOM_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(sorted(custom.items(), key=lambda kv: kv[0].lower())), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CUSTOM_PATH)


_pattern_cache: dict[tuple, tuple] = {}


def _lexicon_matcher(lex: dict[str, str]):
    """One compiled alternation for the whole lexicon, longest keys first.

    A single pass means a replacement is never rewritten by a shorter key, and
    1000+ entries cost one regex scan instead of one scan per entry.
    """
    sig = (_lexicon_mtime, tuple(sorted(lex.items())))
    hit = _pattern_cache.get(sig)
    if hit:
        return hit
    keys = sorted((k for k in lex if k), key=len, reverse=True)
    rx = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(k) for k in keys) + r")(?![\w])") if keys else None
    if len(_pattern_cache) > 32:
        _pattern_cache.clear()
    _pattern_cache[sig] = (rx, lex)
    return rx, lex


def apply_lexicon(text: str, extra: dict[str, str] | None) -> str:
    lex = dict(load_lexicon())
    if extra:
        lex.update(extra)  # site overrides win
    rx, table = _lexicon_matcher(lex)
    if rx is None:
        return text
    return rx.sub(lambda m: table[m.group(0)], text)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?…:])\s+", text)
    return [p for p in parts if p.strip()]


def check_token(x_agfo_token: str | None):
    if not TOKEN or x_agfo_token != TOKEN:
        raise HTTPException(status_code=401, detail="bad token")


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_CHARS)
    speed: float = Field(1.0, ge=0.7, le=1.4)
    pause_ms: int = Field(350, ge=0, le=2000)        # silence after each sentence
    paragraph_pause_ms: int = Field(700, ge=0, le=3000)
    format: str = Field("mp3", pattern="^(mp3|wav)$")
    lexicon: dict[str, str] | None = None          # per-request overrides
    apply_lexicon: bool = True                     # False: text is already a prepared reading script
    seed: int = 0


class LexiconEntry(BaseModel):
    word: str = Field(..., min_length=1, max_length=80)
    reading: str = Field("", max_length=160)


class LexiconRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_CHARS)
    lexicon: dict[str, str] | None = None


def synth_sentence(sentence: str, speed: float, seed: int) -> tuple[np.ndarray, int]:
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.wav")
        with tts_lock:
            tts.say(sentence, path=path, speed=speed, seed=seed)
        audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio, sr


def to_mp3(wav_bytes: bytes) -> bytes:
    p = subprocess.run(
        [FFMPEG, "-loglevel", "error", "-i", "pipe:0", "-codec:a", "libmp3lame",
         "-b:a", "96k", "-f", "mp3", "pipe:1"],
        input=wav_bytes, capture_output=True, check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),   # 1.1.1: no console flash under pythonw
    )
    return p.stdout


@app.get("/health")
def health(x_agfo_token: str | None = Header(default=None)):
    check_token(x_agfo_token)
    return {"ok": True, "model": "ema-lightning", "threads": THREADS, "device": str(getattr(tts, "device", "cpu")),
            "lexicon_entries": len(load_lexicon()), "version": app.version,
            "features": ["lexicon_apply", "apply_lexicon_flag", "lexicon_edit"]}


def _clean_word(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if not value or any(c in value for c in "\n\r\t") or not re.search(r"\w", value):
        raise HTTPException(status_code=400, detail="geçersiz kelime")
    return value


@app.get("/lexicon")
def lexicon_list(x_agfo_token: str | None = Header(default=None)):
    check_token(x_agfo_token)
    merged = load_lexicon()
    rows = []
    for word in sorted(set(_base) | set(_custom), key=str.lower):
        c = _custom.get(word, ...)
        if c is None:
            source = "removed"
        elif c is not ...:
            source = "edited" if word in _base else "added"
        else:
            source = "base"
        rows.append({"word": word, "reading": merged.get(word, _base.get(word, "")), "source": source,
                     "base_reading": _base.get(word)})
    return {"entries": rows, "active": len(merged), "base": len(_base), "custom": len(_custom)}


@app.post("/lexicon/entry")
def lexicon_upsert(entry: LexiconEntry, x_agfo_token: str | None = Header(default=None)):
    """Add or change one reading. Stored in data/lexicon.custom.json, live immediately."""
    check_token(x_agfo_token)
    word = _clean_word(entry.word)
    reading = re.sub(r"\s+", " ", entry.reading).strip()
    if not reading:
        raise HTTPException(status_code=400, detail="okunuş boş")
    with _write_lock:
        load_lexicon()
        custom = dict(_custom)
        if word in _base and _base[word] == reading:
            custom.pop(word, None)          # back to the shipped reading
        else:
            if word not in custom and len(custom) >= MAX_CUSTOM:
                raise HTTPException(status_code=400, detail="özel kayıt sınırı dolu")
            custom[word] = reading
        _save_custom(custom)
        load_lexicon()
    return {"ok": True, "word": word, "reading": reading, "active": len(_lexicon)}


@app.post("/lexicon/delete")
def lexicon_delete(entry: LexiconEntry, x_agfo_token: str | None = Header(default=None)):
    """Remove a word. A shipped word is masked (null) so an update cannot bring it back;
    a word added from WordPress is simply dropped. reading="__restore__" un-masks / reverts."""
    check_token(x_agfo_token)
    word = _clean_word(entry.word)
    with _write_lock:
        load_lexicon()
        custom = dict(_custom)
        if entry.reading == "__restore__":
            custom.pop(word, None)
        elif word in _base:
            custom[word] = None
        elif word in custom:
            custom.pop(word)
        else:
            raise HTTPException(status_code=404, detail="kelime sözlükte yok")
        _save_custom(custom)
        load_lexicon()
    return {"ok": True, "word": word, "active": len(_lexicon)}


@app.post("/lexicon/apply")
def lexicon_apply(req: LexiconRequest, x_agfo_token: str | None = Header(default=None)):
    """Returns the text with the server lexicon (plus request overrides) applied, so a
    client can prepare a reading script first and then synthesise it with apply_lexicon=false."""
    check_token(x_agfo_token)
    return {"text": apply_lexicon(req.text, req.lexicon), "lexicon_entries": len(load_lexicon())}


@app.post("/tts")
def synthesize(req: TTSRequest, x_agfo_token: str | None = Header(default=None)):
    check_token(x_agfo_token)

    load_lexicon()  # refresh mtime so an edited lexicon.json never serves stale audio
    key = hashlib.sha256((req.model_dump_json() + f"|lex:{_lexicon_mtime}").encode()).hexdigest()
    cached = CACHE_DIR / f"{key}.{req.format}"
    if cached.exists():
        secs_file = cached.with_suffix(cached.suffix + ".sec")
        try:
            secs = float(secs_file.read_text())
        except (OSError, ValueError):
            secs = None
        return _audio_response(cached.read_bytes(), req.format, cached=True, seconds=secs)

    paragraphs = [p for p in re.split(r"\n\s*\n", req.text) if p.strip()]
    pieces: list[np.ndarray] = []
    sr = 48000
    for pi, para in enumerate(paragraphs):
        spoken = apply_lexicon(para, req.lexicon) if req.apply_lexicon else para
        for si, sent in enumerate(split_sentences(spoken)):
            audio, sr = synth_sentence(sent, req.speed, req.seed)
            pieces.append(audio)
            pieces.append(np.zeros(int(sr * req.pause_ms / 1000), dtype=np.float32))
        if pi < len(paragraphs) - 1:
            pieces.append(np.zeros(int(sr * req.paragraph_pause_ms / 1000), dtype=np.float32))

    if not pieces:
        raise HTTPException(status_code=400, detail="no speakable text")

    full = np.concatenate(pieces)
    buf = io.BytesIO()
    sf.write(buf, full, sr, format="WAV", subtype="PCM_16")
    data = buf.getvalue()
    if req.format == "mp3":
        data = to_mp3(data)

    cached.write_bytes(data)
    seconds = len(full) / sr
    try:
        cached.with_suffix(cached.suffix + ".sec").write_text(f"{seconds:.2f}")
    except OSError:
        pass
    return _audio_response(data, req.format, cached=False, seconds=seconds)


def _audio_response(data: bytes, fmt: str, cached: bool, seconds: float | None = None):
    headers = {"X-AGFO-Cached": "1" if cached else "0"}
    if seconds is not None:
        headers["X-AGFO-Seconds"] = f"{seconds:.2f}"
    media = "audio/mpeg" if fmt == "mp3" else "audio/wav"
    return Response(content=data, media_type=media, headers=headers)
