#!/usr/bin/env bash
# AGFO TTS ses denemesi: EMA (kadin) ile Chatterbox Multilingual'i ayni metinle karsilastirir.
# Calisan EMA servisine dokunmaz; her sey /opt/agfo-tts-bench altina kurulur, sonra silinebilir.
# Kullanim:  sudo bash run-bench.sh [REFERANS_SES.wav|mp3 ya da https://.../ses.mp3]
#   Referans: 10-20 sn, tek kisi, temiz Turkce konusma. Verilmezse modelin yerlesik sesi kullanilir.
set -euo pipefail
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
BENCH=/opt/agfo-tts-bench
OUT=/root/tts-bench
REF_IN="${1:-}"
[ "$(id -u)" = 0 ] || { echo "root olarak çalıştırın"; exit 1; }
echo "== Sunucu"
echo "Çekirdek: $(nproc) · Boş bellek: $(free -g | awk '/Mem:/{print $7}') GB · /opt boş alan: $(df -BG --output=avail /opt | tail -1 | tr -d ' ')"
AVAIL_G=$(df -BG --output=avail /opt | tail -1 | tr -dc '0-9')
[ "$AVAIL_G" -ge 8 ] || { echo "En az 8 GB boş disk gerekir."; exit 1; }
MEM_G=$(free -g | awk '/Mem:/{print $7}')
[ "$MEM_G" -ge 3 ] || echo "UYARI: 3 GB'tan az boş bellek var; deneme yavaş olabilir veya bellek yetmeyebilir."
mkdir -p "$BENCH" "$OUT"
REF=""
if [ -n "$REF_IN" ]; then
  if [[ "$REF_IN" =~ ^https?:// ]]; then
    curl -fL -o "$BENCH/referans.in" "$REF_IN"
  else
    cp -f "$REF_IN" "$BENCH/referans.in"
  fi
  ffmpeg -loglevel error -y -i "$BENCH/referans.in" -ac 1 -ar 24000 -t 25 "$BENCH/referans.wav"
  REF="$BENCH/referans.wav"
  echo "Referans ses hazır: $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$REF") sn"
fi
echo "== Chatterbox kurulumu (ilk seferde birkaç dakika; yaklaşık 4-5 GB)"
UV=/opt/agfo-tts/.local/bin/uv
[ -x "$UV" ] || { curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$BENCH/bin" sh >/dev/null; UV="$BENCH/bin/uv"; }
export UV_NO_CONFIG=1 UV_CACHE_DIR="$BENCH/uv-cache" UV_PYTHON_INSTALL_DIR="$BENCH/python"
[ -x "$BENCH/venv/bin/python" ] || "$UV" venv --python 3.11 "$BENCH/venv" >/dev/null
"$UV" pip install --python "$BENCH/venv/bin/python" -q --index-url https://pypi.org/simple \
  --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match chatterbox-tts==0.1.7
echo "== Deneme (model ilk seferde Hugging Face'ten iner, yaklaşık 2 GB)"
THREADS=$(( $(nproc) / 2 )); [ "$THREADS" -ge 1 ] || THREADS=1
HF_HOME="$BENCH/hf" BENCH_THREADS=$THREADS nice -n 15 "$BENCH/venv/bin/python" "$HERE/bench.py" "$OUT" "$REF"
echo
echo "== Dosyalar: $OUT"
ls -la "$OUT"
SITE_UP=""
for d in /home/agfo.app/public_html/wp-content/uploads /home/*/public_html/wp-content/uploads; do
  [ -d "$d" ] && { SITE_UP="$d"; break; }
done
if [ -n "$SITE_UP" ]; then
  KEY=$(openssl rand -hex 6)
  mkdir -p "$SITE_UP/agfo-tts-deneme-$KEY"
  cp "$OUT"/*.mp3 "$SITE_UP/agfo-tts-deneme-$KEY/"
  chown -R --reference="$SITE_UP" "$SITE_UP/agfo-tts-deneme-$KEY"
  DOMAIN=$(echo "$SITE_UP" | cut -d/ -f3)
  echo "Dinlemek için (deneme bitince silin: rm -rf $SITE_UP/agfo-tts-deneme-$KEY):"
  for f in "$OUT"/*.mp3; do echo "  https://$DOMAIN/wp-content/uploads/agfo-tts-deneme-$KEY/$(basename "$f")"; done
fi
echo "Denemeyi tamamen kaldırmak için: rm -rf $BENCH $OUT"
