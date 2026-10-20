#!/usr/bin/env bash
# Piper "Cem" (dcx514ai/piper_tts_turkish_high, MIT, 21M parametre) denemesi: EMA ile ayni metni seslendirir.
# Hafif bir modeldir; yine de 1,5 GB bellek siniri ve dusuk oncelikle calisir. EMA servisine dokunmaz.
# Kullanim:  HF_TOKEN=hf_xxx bash run-piper-cem.sh      (Hugging Face'te model sartlarini kabul ettikten sonra)
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "root olarak çalıştırın"; exit 1; }
[ -n "${HF_TOKEN:-}" ] || { echo "HF_TOKEN gerekli (Hugging Face › Settings › Access Tokens › Read)."; exit 1; }
BENCH=/opt/agfo-tts-piper
OUT=/root/tts-bench
mkdir -p "$BENCH/model" "$OUT"
MEM_G=$(free -g | awk '/Mem:/{print $7}')
[ "$MEM_G" -ge 1 ] || { echo "DURDURULDU: 1 GB'tan az boş bellek var."; exit 1; }
echo "== Model dosyaları"
LIST=$(curl -fsS -H "Authorization: Bearer $HF_TOKEN" https://huggingface.co/api/models/dcx514ai/piper_tts_turkish_high) \
  || { echo "Erişim yok: model sayfasında onay henüz verilmemiş olabilir."; exit 1; }
FILES=$(echo "$LIST" | python3 -c "import json,sys; print('\n'.join(s['rfilename'] for s in json.load(sys.stdin).get('siblings',[])))")
echo "$FILES"
ONNX=$(echo "$FILES" | grep -E '\.q8\.onnx$' | head -1); [ -n "$ONNX" ] || ONNX=$(echo "$FILES" | grep -E '\.onnx$' | head -1)
CONF=$(echo "$FILES" | grep -E '\.onnx\.json$|config\.json$' | head -1 || true)
for f in "$ONNX" $CONF; do
  [ -n "$f" ] && curl -fsSL -H "Authorization: Bearer $HF_TOKEN" -o "$BENCH/model/$(basename "$f")" "https://huggingface.co/dcx514ai/piper_tts_turkish_high/resolve/main/$f"
done
ls -la "$BENCH/model"
if [ -z "$CONF" ]; then
  echo "Bu depoda Piper yapılandırma dosyası (.onnx.json) yok; özel çıkarım kodu gerekebilir. Yukarıdaki dosya listesini Claude'a gönderin."
  exit 2
fi
MODEL="$BENCH/model/$(basename "$ONNX")"
cp "$BENCH/model/$(basename "$CONF")" "$MODEL.json"
echo "== Piper kurulumu (küçük, ~100 MB)"
UV=/opt/agfo-tts/.local/bin/uv
export UV_NO_CONFIG=1 UV_CACHE_DIR="$BENCH/uv-cache" UV_PYTHON_INSTALL_DIR="$BENCH/python"
[ -x "$BENCH/venv/bin/python" ] || "$UV" venv --python 3.11 "$BENCH/venv" >/dev/null
"$UV" pip install --python "$BENCH/venv/bin/python" -q --index-url https://pypi.org/simple piper-tts
TEXT="Geçen yıl İstanbul'da düzenlenen gıda güvenliği konferansında, fabrika yöneticileri denetim sonuçlarını tartıştı. Konuşmacılar, alerjen yönetiminin ve izlenebilirliğin en çok gözden kaçan iki konu olduğunu söyledi. Yeni dönemde hedef, her üretim hattında aynı titizliği göstermek ve çalışanların bu kültürü benimsemesini sağlamak."
echo "== Seslendirme"
START=$(date +%s.%N)
echo "$TEXT" | nice -n 15 systemd-run --scope -q -p MemoryMax=1500M -p MemorySwapMax=0 \
  "$BENCH/venv/bin/piper" --model "$MODEL" --output_file "$OUT/4-piper-cem.wav"
END=$(date +%s.%N)
ffmpeg -loglevel error -y -i "$OUT/4-piper-cem.wav" -b:a 128k "$OUT/4-piper-cem.mp3" && rm -f "$OUT/4-piper-cem.wav"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/4-piper-cem.mp3")
echo "Piper Cem: ${DUR} sn ses, $(python3 -c "print(round($END-$START,1))") sn sürdü"
# EMA ile ayni metin (karsilastirma icin)
TOKEN=$(grep AGFO_TTS_TOKEN /opt/agfo-tts/.env | cut -d= -f2)
curl -fsS -o "$OUT/1-ema-kadin.mp3" -H "X-AGFO-Token: $TOKEN" -H "Content-Type: application/json" \
  -d "{\"text\":\"$TEXT\",\"format\":\"mp3\"}" http://127.0.0.1:8765/tts || true
SITE_UP=""
for d in /home/agfo.app/public_html/wp-content/uploads /home/*/public_html/wp-content/uploads; do [ -d "$d" ] && { SITE_UP="$d"; break; }; done
if [ -n "$SITE_UP" ]; then
  KEY=$(openssl rand -hex 6); mkdir -p "$SITE_UP/agfo-tts-deneme-$KEY"; cp "$OUT"/*.mp3 "$SITE_UP/agfo-tts-deneme-$KEY/"
  chown -R --reference="$SITE_UP" "$SITE_UP/agfo-tts-deneme-$KEY"; DOMAIN=$(echo "$SITE_UP" | cut -d/ -f3)
  echo "Dinlemek için (bitince silin: rm -rf $SITE_UP/agfo-tts-deneme-$KEY):"
  for f in "$OUT"/*.mp3; do echo "  https://$DOMAIN/wp-content/uploads/agfo-tts-deneme-$KEY/$(basename "$f")"; done
fi
echo "Denemeyi kaldırmak için: rm -rf $BENCH $OUT"
