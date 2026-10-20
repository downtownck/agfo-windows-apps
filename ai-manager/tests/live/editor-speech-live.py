#!/usr/bin/env python3
"""AI Editor seslendirme uclari canli testi (AI Manager 17.12.0).

Yerel/izinli bir WordPress'te calisir; EMA servisi olarak AGFO TTS Service 1.1.0+ (gercek ya da sahte model)
gerekir. Ortam: AGFO_TEST_BASE_URL, AGFO_TEST_WP_PATH, AGFO_TEST_EMA_TOKEN, AGFO_TEST_EMA_LEXICON_ENDPOINT.
Bir editor baglanti anahtari olusturur, uclari dener ve anahtari iptal eder.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ['AGFO_TEST_BASE_URL'].rstrip('/') + '/wp-json/agfo-ai/v1'
WP = os.environ['AGFO_TEST_WP_PATH']
ok = fail = 0


def php(code):
    return subprocess.run(['php', '-r', "require getenv('AGFO_TEST_WP_PATH') . '/wp-load.php'; " + code],
                          capture_output=True, text=True, timeout=60).stdout.strip()


def chk(name, cond, extra=''):
    global ok, fail
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '  ' + str(extra)[:300]))
    ok += bool(cond)
    fail += (not cond)


def call(route, payload=None, token=None, raw=False):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['X-AGFO-Editor-Token'] = token
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(BASE + route, data=data, headers=headers, method='POST' if data else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            body = r.read()
            return r.status, (body if raw else json.loads(body or b'{}')), dict(r.headers)
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body or b'{}'), dict(e.headers)
        except ValueError:
            return e.code, body, dict(e.headers)


token = php("$e = $GLOBALS['AGFO_ENC']; update_option('agfo_ema_api_key', $e ? $e->encrypt(getenv('AGFO_TEST_EMA_TOKEN')) : getenv('AGFO_TEST_EMA_TOKEN'));"
            " update_option('agfo_ai_ema_endpoint', getenv('AGFO_TEST_EMA_LEXICON_ENDPOINT'));"
            " $r = AGFO_AIM_Editor_Tokens::create(1, 'AGFO_REGRESSION speech'); echo is_string($r) ? $r : '';")
try:
    chk('editor token created', token.startswith('agfoed.'), token)
    st, d, _ = call('/editor/info', token=token)
    chk('info advertises speech', st == 200 and 'speech' in d.get('features', []) and d.get('speech', {}).get('speech_ready') is True, d)
    st, d, _ = call('/editor/speech', {'text': 'x'})
    chk('speech without key -> 401', st == 401, st)
    st, d, _ = call('/editor/speech-script', {'text': 'AGFO_REGRESSION: Gıda güvenliği kültürü %92 oranında güçlü.\n\nİkinci paragraf.'}, token)
    chk('reading script preview', st == 200 and d.get('chunks') == 1 and '\n\n' in d.get('text', ''), d)
    st, d, _ = call('/editor/speech', {'text': 'AGFO_REGRESSION: Gıda güvenliği %92.\n\nİkinci paragraf.', 'reading_script': False,
                                       'speed': 1.1, 'paragraph_pause_ms': 800, 'request_id': 'reg-%d' % time.time()}, token)
    chk('submit -> 202 queued', st == 202 and d.get('job') and d.get('status') in ('queued', 'processing', 'complete'), d)
    job = d.get('job', '')
    for _ in range(90):
        st, d, _ = call('/editor/speech/' + job, token=token)
        if d.get('status') in ('complete', 'failed'):
            break
        time.sleep(1)
    chk('job completes', d.get('status') == 'complete' and d.get('bytes', 0) > 0, d)
    chk('reading_script=false honoured', (d.get('script') or {}).get('status') == 'off', d.get('script'))
    st, audio, h = call('/editor/speech/' + job + '/audio', token=token, raw=True)
    chk('audio streamed', st == 200 and isinstance(audio, bytes) and audio[:3] in (b'ID3', b'\xff\xfb', b'\xff\xf3') and 'audio' in h.get('Content-Type', ''), (st, h.get('Content-Type')))
    st, d, _ = call('/editor/speech/' + job + '/audio')
    chk('audio without key -> 401', st == 401, st)
    st, d, _ = call('/editor/lexicon', token=token)
    chk('lexicon list', st == 200 and d.get('active', 0) > 0 and d.get('can_edit') is True, d if st != 200 else d.get('active'))
    st, d, _ = call('/editor/lexicon', {'op': 'save', 'word': 'AGFO_REGRESSION_Ed', 'reading': 'editör regresyon'}, token)
    chk('lexicon save', st == 200 and d.get('ok'), d)
    st, d, _ = call('/editor/lexicon', token=token)
    chk('saved word listed as added', any(e.get('word') == 'AGFO_REGRESSION_Ed' and e.get('source') == 'added' for e in d.get('entries', [])))
    st, d, _ = call('/editor/lexicon', {'op': 'delete', 'word': 'AGFO_REGRESSION_Ed'}, token)
    chk('lexicon delete', st == 200 and d.get('ok'), d)
    st, d, _ = call('/editor/lexicon', {'op': 'nope', 'word': 'x'}, token)
    chk('invalid op -> 400', st == 400, st)
    st, d, _ = call('/editor/lexicon/listen', {'reading': 'hasip'}, token)
    chk('listen returns mp3', st == 200 and d.get('mime') == 'audio/mpeg' and len(d.get('audio_base64', '')) > 100, st)
finally:
    php("foreach ( AGFO_AIM_Editor_Tokens::list_for(1) as $id => $t ) { if ( false !== strpos( (string) ( $t['label'] ?? '' ), 'AGFO_REGRESSION' ) ) { AGFO_AIM_Editor_Tokens::revoke(1, (string) $id); } } delete_option('agfo_ai_ema_endpoint');")
print('TOTAL %d pass / %d fail' % (ok, fail))
sys.exit(1 if fail else 0)
