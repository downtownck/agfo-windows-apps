# AGFO System Care 3.13.2

- **UGREEN — mevcut Tailscale kurulumu**: "UGREEN ayarını kopyala" artık önce NAS'ın Tailscale'de zaten görünüp görünmediğini soruyor. Görünüyorsa tek satırlık bir SSH komutu kopyalanıyor. Komut IP yönlendirmeyi açıyor ve tailscale'i bulup (PATH, uygulama klasörleri ya da Docker kapsayıcısı) yalnızca çıkış noktalığını açıyor; makinenin adı ve ayarları değişmiyor. Görünmüyorsa sıfırdan kurulum için önceki Docker Compose ayarı kopyalanıyor.
- Adında "nas" ya da UGREEN model adı (DXP/DH) geçen makineler "Türkiye — UGREEN NAS (Türk IP)" olarak etiketleniyor.
