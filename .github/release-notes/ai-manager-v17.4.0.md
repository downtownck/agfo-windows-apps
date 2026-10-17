## AGFO AI Manager 17.4.0 — AI Editor bağlantısı + GitHub'dan güncelleme

- **AGFO AI Editor için REST ucu** (`/wp-json/agfo-ai/v1/editor/*`): `info`, `transform` (Content Studio şablonları ve çeviri yönlendirmesi), `chat` (belge bağlamlı sohbet). Kimlik doğrulama WordPress *Uygulama Parolası* ile (HTTPS); Content Studio yetkisi (varsayılan `manage_options`) gerekir. API anahtarları sitede kalır, yanıtlarda anahtar/uç adresi yoktur.
- **GitHub'dan tek tıkla güncelleme:** Eklentiler ekranında yeni sürüm görünür; paket GitHub Releases'ten indirilir, SHA-256 ile doğrulanır (özet yoksa güncelleme reddedilir). Sitenin `data/data.json` dosyası (model kataloğu, sıralamalar) güncelleme sırasında yedeklenip geri yüklenir.
- Geriye uyumluluk tam; mevcut işlevler değişmedi.
- **17.3.3'ten geçiş:** bu sürümdeki `agfo-ai-manager-17.4.0.zip` dosyasını bir kez Eklentiler › Yeni Ekle › Yükle ile kurun. Sonraki sürümler otomatik görünür.
- Kapatmak için: `agfo_aim_github_updates` seçeneği `0` ya da `agfo_ai_manager_github_updates` filtresi.
