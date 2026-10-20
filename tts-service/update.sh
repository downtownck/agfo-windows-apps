#!/usr/bin/env bash
# AGFO TTS Service — hızlı güncelleme: yalnız server.py ve lexicon.json'u yeniler.
# Model, venv, token ve WordPress'ten eklenen sözlük kayıtlarına dokunmaz. Kullanım: sudo bash update.sh
set -euo pipefail
SRC_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
APP_DIR=/opt/agfo-tts
APP_USER=agfo-tts
PORT=${PORT:-8765}
[ -d "$APP_DIR" ] || { echo "Kurulum bulunamadı: $APP_DIR (önce install.sh)"; exit 1; }
python3 -c "import json,sys; d=json.load(open('$SRC_DIR/lexicon.json', encoding='utf-8')); print('sözlük:', len(d), 'kayıt')"
cp -f "$SRC_DIR/server.py" "$SRC_DIR/lexicon.json" "$APP_DIR/"
mkdir -p "$APP_DIR/data"   # WordPress'ten eklenen kayıtlar burada kalır; güncelleme dokunmaz
chown "$APP_USER:$APP_USER" "$APP_DIR/server.py" "$APP_DIR/lexicon.json" "$APP_DIR/data"
sed "s#__APP_DIR__#$APP_DIR#g; s#__APP_USER__#$APP_USER#g" "$SRC_DIR/agfo-tts.service" > /etc/systemd/system/agfo-tts.service
systemctl daemon-reload
systemctl restart agfo-tts
TOKEN=$(grep AGFO_TTS_TOKEN "$APP_DIR/.env" | cut -d= -f2)
for i in $(seq 1 45); do
  if curl -sf -H "X-AGFO-Token: $TOKEN" "http://127.0.0.1:$PORT/health"; then echo; echo "Güncelleme tamam."; exit 0; fi
  sleep 2
done
echo "Servis yanıt vermedi: journalctl -u agfo-tts -n 50"; exit 1
