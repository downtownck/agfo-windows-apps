# AGFO TTS Service (EMA Lightning)

Hetzner sunucusunda, aynı makinedeki tüm WordPress sitelerinin ortak kullandığı Türkçe TTS servisi.
Model: EMA Lightning (Canberk Aslan, Apache-2.0, 34 MB, CPU'da çalışır).

## Kurulum (root olarak, bir kez)

```bash
cd /root && unzip agfo-tts-service-1.0.0.zip && cd agfo-tts-service
bash install.sh
```

Betik sonunda bir **token** yazdırır. Bunu her sitenin AI Manager ayarlarına gireceksin.
Token'ı sonradan görmek için: `grep TOKEN /opt/agfo-tts/.env`

Servis yalnızca `127.0.0.1:8765` dinler; dışarıdan erişilemez. Aynı sunucudaki siteler
`http://127.0.0.1:8765/tts` adresine istek atar.

## Doğrulama

```bash
systemctl status agfo-tts
TOKEN=$(grep AGFO_TTS_TOKEN /opt/agfo-tts/.env | cut -d= -f2)
curl -s -H "X-AGFO-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"text":"Merhaba. Bu ses Hetzner sunucusunda üretildi."}' \
  http://127.0.0.1:8765/tts -o /tmp/test.mp3 -D - | grep -i x-agfo
```

## API

`POST /tts` — JSON gövde:

| alan | varsayılan | açıklama |
|---|---|---|
| text | — | düz metin, paragraflar boş satırla ayrılır (en çok 60.000 karakter) |
| speed | 1.0 | 0.7–1.4 |
| pause_ms | 350 | cümle sonu sessizlik |
| paragraph_pause_ms | 700 | paragraf sonu sessizlik |
| format | mp3 | mp3 veya wav |
| lexicon | — | bu isteğe özel telaffuz ekleri `{"Hegel":"Hegel"}` |

Yanıt: ses dosyasının kendisi. Başlıklar: `X-AGFO-Seconds` (süre), `X-AGFO-Cached` (önbellekten mi).
Aynı metin ikinci kez istenirse önbellekten döner, model çalışmaz.

`GET /health` — ayar ekranındaki "Bağlantıyı test et" düğmesi için.

Her istekte `X-AGFO-Token` başlığı zorunlu.

## Telaffuz sözlüğü

`/opt/agfo-tts/lexicon.json` — düzenle, kaydet; servis yeniden başlatılmadan bir sonraki istekte devreye girer.
Yabancı kelimeleri Türkçe okunuşuyla yaz. Kısaltmaları harf harf aç.

## Diğer sunucudaki siteler (agfocert)

Bu sürüm bilerek yalnızca loopback dinliyor. Başka sunucudaki bir sitenin kullanması gerekirse
CyberPanel'de `tts.cemalkara.com` gibi bir alt alan açıp LiteSpeed reverse proxy ile
`127.0.0.1:8765`'e yönlendir; token zaten istekleri korur. Bu adım ayrıca yapılır.

## WordPress tarafı

`wp-client/class-agfo-tts-client.php` — AI Manager'a provider adaptörü olarak veya
herhangi bir AGFO eklentisine doğrudan eklenir. `synthesize_to_media()` bir yazının
metnini seslendirip medya kütüphanesine yazar, post meta'ya bağlar ve içerik değişmediyse
servisi hiç çağırmaz.

## Günlükler

```bash
journalctl -u agfo-tts -f
```

## Kaldırma

```bash
systemctl disable --now agfo-tts
rm -f /etc/systemd/system/agfo-tts.service && systemctl daemon-reload
rm -rf /opt/agfo-tts && userdel agfo-tts
```

## 1.0.7 — Geniş telaffuz sözlüğü

- `lexicon.json` 26 kayıttan 2.494 kayda çıktı: ABD/İngiltere/Avrupa/Asya yer adları, düşünür ve bilim insanları, yazar/sanatçı/besteciler, kamusal isimler ve sık geçen yabancı adlar, markalar, teknoloji ve denetim/gıda güvenliği terimleri, kurum kısaltmaları.
- Sözlük tek geçişte uygulanır (tek derlenmiş düzenli ifade, uzun anahtar önce). Bir değiştirme sonraki kayıtla yeniden değiştirilmez (ör. Henry → Henri, Henri → Anri zincirlenmez); 33 bin karakter ~40 ms.
- `update.sh`: yalnız `server.py` ve `lexicon.json`'u yeniler, servisi yeniden başlatır ve sağlık kontrolü yapar; model, venv ve token'a dokunmaz.
- Sözlüğe kayıt eklemek için `/opt/agfo-tts/lexicon.json` düzenlenir; servis dosya değişince yeniden yükler, yeniden başlatma gerekmez.

## 1.0.8 — Okuma metni desteği

- `POST /lexicon/apply` {text, lexicon?} → {text}: sözlüğü (sunucu + istekle gelen site kayıtları) tek geçişte uygular. AI Manager 17.10.0 okuma metnini bu metinden hazırlar.
- `/tts` isteğinde `apply_lexicon: false`: metin zaten hazırlanmış bir okuma metniyse sözlük ikinci kez uygulanmaz.
- `/health` sürüm ve özellik listesini döndürür.
- Önbellek anahtarı sözlük dosyasının değişme zamanını içerir; `lexicon.json` düzenlendiğinde eski ses dönmez.

## 1.0.9 — HACCP okunuşu

- Sözlükte HACCP → "hasip" (önceki "hasap").

## 1.1.0 — Sözlüğü WordPress'ten yönetme

- `GET /lexicon`: etkin sözlük, her kaydın kaynağı (base / added / edited / removed) ve sayılar.
- `POST /lexicon/entry` {word, reading}: kelime ekler veya okunuşu değiştirir. `POST /lexicon/delete` {word}: hazır kelimeyi maskeler, eklenen kelimeyi siler; reading="__restore__" ile hazır okunuşa döner.
- Düzenlemeler `/opt/agfo-tts/data/lexicon.custom.json` dosyasına yazılır ve hemen geçerli olur. `update.sh` bu dosyaya dokunmaz; hazır `lexicon.json` güncellense de eklenen ve değiştirilen kayıtlar kalır.
- systemd birimi `data/` dizinine yazma izni verir; `update.sh` birimi yeniler.
- WordPress tarafı: AI Manager 17.11.0 › AGFO AI › Telaffuz Sözlüğü.
- `tests/test_server.py`: EMA modeli yerine sahte modelle 20 sözlük/önbellek testi.

## 1.1.1 — Windows (bu bilgisayar) kurulumu

`windows/` klasörü aynı servisi bir Windows bilgisayara kurar: `AGFO-Ses-Kur.cmd` winget ile ffmpeg ve uv'yi,
uv ile Python 3.12'yi, NVIDIA kart varsa CUDA'lı PyTorch'u kurar; servisi `%LOCALAPPDATA%\AGFO\TTS` altına koyar,
yalnız 127.0.0.1'de çalıştırır, oturum açılınca Başlangıç klasöründeki kısayolla başlatır. AGFO AI Editor 1.7.0
adresi ve anahtarı `.env` dosyasından okur. `AGFO-Ses-Dene.cmd` erkek ses adaylarını (Chatterbox Multilingual,
Piper "Cem") aynı metinle ekran kartında dener. Sunucu kodundaki değişiklikler: `AGFO_TTS_FFMPEG` (ffmpeg'in tam
yolu) ve `/health` yanıtında `device`. Sunucuyu güncellemek gerekmez.
