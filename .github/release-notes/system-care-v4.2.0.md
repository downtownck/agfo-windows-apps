# AGFO System Care 4.2.0 — Çalışan uygulamalar, Servisler, Başlangıç

## İndirme
- **Python gerektirmeyen kurulum:** `AGFO-System-Care-v4.2.0-Windows.zip` → `Kur-ve-Baslat.cmd`
- **Uygulama içi güncelleme:** `AGFO-System-Care-v4.2.0.zip`

## Yenilikler (Sistem bölümü)
- **Çalışan uygulamalar:** işlemci ve bellek kullanımıyla süreç listesi; sonlandır, alt süreçleriyle sonlandır, dosya konumu, otomatik yenileme. Kritik Windows süreçleri korunur.
- **Servisler:** başlat / durdur / yeniden başlat ve başlangıç türü (Otomatik, El ile, Devre dışı); kritik servisler korunur.
- **Başlangıç:** açılışta başlayan uygulamaları Görev Yöneticisi yöntemiyle, geri alınabilir şekilde etkinleştir / devre dışı bırak.

Gerçek Windows'ta test edildi: süreç sonlandırma, kritik süreç/servis koruması, başlangıç öğesini kapatıp açma.
