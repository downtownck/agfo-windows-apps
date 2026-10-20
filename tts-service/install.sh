#!/usr/bin/env bash
# AGFO TTS Service - EMA Lightning installer for Hetzner (Ubuntu/Debian, CyberPanel/LiteSpeed)
# Run as root:  bash install.sh
set -euo pipefail
SRC_DIR="$(dirname "$(readlink -f "$0")")"   # folder that holds server.py (may be a runner's private dir)
for f in server.py lexicon.json agfo-tts.service; do
  [ -f "$SRC_DIR/$f" ] || { echo "Missing $f next to install.sh (looked in $SRC_DIR)"; exit 1; }
done
export DEBIAN_FRONTEND=noninteractive

APP_DIR=/opt/agfo-tts
APP_USER=agfo-tts
PORT=${PORT:-8765}

echo "[1/6] System packages"
apt-get update -qq
apt-get install -y -qq curl ca-certificates ffmpeg >/dev/null

echo "[2/6] Service user and directories"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$APP_DIR/cache/hf" "$APP_DIR/.cache" "$APP_DIR/data"
cp -f "$SRC_DIR/server.py" "$SRC_DIR/lexicon.json" "$APP_DIR/"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
cd "$APP_DIR"   # never run the service user inside the source/runner directory

echo "[3/6] Python 3.12 (standalone via uv) + packages (CPU wheels)"
# ema-lightning needs Python >= 3.11; the system python may be older, so we use a
# self-contained interpreter managed by uv under the service user's home. No system change.
if [ ! -x "$APP_DIR/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
  sudo -u "$APP_USER" env HOME="$APP_DIR" UV_INSTALL_DIR="$APP_DIR/.local/bin" sh /tmp/uv-install.sh >/dev/null
  rm -f /tmp/uv-install.sh
fi
UV="$APP_DIR/.local/bin/uv"
export UV_NO_CONFIG=1
sudo -u "$APP_USER" env HOME="$APP_DIR" "$UV" python install 3.12 >/dev/null
sudo -u "$APP_USER" env HOME="$APP_DIR" "$UV" venv --clear --python 3.12 "$APP_DIR/venv" >/dev/null
sudo -u "$APP_USER" env HOME="$APP_DIR" "$UV" pip install --python "$APP_DIR/venv/bin/python" -q \
  --index-url https://pypi.org/simple \
  --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match \
  ema-lightning fastapi "uvicorn[standard]" soundfile numpy
"$APP_DIR/venv/bin/python" -c "import ema_lightning, sys; print('python', sys.version.split()[0], 'ema-lightning OK')"

echo "[4/6] Token"
if [ ! -f "$APP_DIR/.env" ]; then
  TOKEN=$(openssl rand -hex 24)
  cat > "$APP_DIR/.env" <<EOF
AGFO_TTS_TOKEN=$TOKEN
AGFO_TTS_PORT=$PORT
AGFO_TTS_THREADS=$(nproc)
AGFO_TTS_CACHE_DIR=$APP_DIR/cache
EOF
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"; chmod 600 "$APP_DIR/.env"
fi

echo "[5/6] systemd unit"
sed "s#__APP_DIR__#$APP_DIR#g; s#__APP_USER__#$APP_USER#g" "$SRC_DIR/agfo-tts.service" > /etc/systemd/system/agfo-tts.service
systemctl daemon-reload
systemctl enable --now agfo-tts
echo "[6/6] Smoke test"
TOKEN=$(grep AGFO_TTS_TOKEN "$APP_DIR/.env" | cut -d= -f2)
for i in $(seq 1 30); do
  if curl -sf -H "X-AGFO-Token: $TOKEN" "http://127.0.0.1:$PORT/health"; then echo; break; fi
  [ "$i" -eq 30 ] && { echo "Service did not answer in 90s - check: journalctl -u agfo-tts -n 40"; exit 1; }
  sleep 3
done
echo
echo "Done. Token (put this into every site's AI Manager settings):"
echo "  $TOKEN"
echo "Endpoint for sites on this server:  http://127.0.0.1:$PORT/tts"
