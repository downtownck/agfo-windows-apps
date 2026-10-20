## AGFO Phantom Shot 1.1.0 — tek dosyalık EXE

Phantom Shot artık Python gerektirmeyen **tek dosyalık bir EXE** olarak dağıtılıyor (BackupSync / AI Editor gibi).

- **Kurulum (yönetici gerekmez):** `AGFO-Phantom-Shot-Kur.cmd` dosyasını çalıştırın — en güncel `AGFO-Phantom-Shot.exe`'yi GitHub'dan indirir, SHA-256 ile doğrular, `%LOCALAPPDATA%\Programs\AGFO-Phantom-Shot` altına kurar, Başlat menüsü + masaüstü kısayolu oluşturur ve başlatır. `.cmd` ile indirmek genelde SmartScreen uyarısını atlatır.
- **Tek tıkla güncelleme:** açılışta `phantom-shot-v*` sürümleri denetlenir; "Şimdi güncelle" yeni EXE'yi indirip doğrular, uygulama kapanınca yerine koyar ve yeniden açar. Ayarlar (`config.json`) korunur.
- `mss`, `pynput`, `pillow`, `pystray` EXE'ye gömülü; ayrı paket kurulumu gerekmez.
- Güncelleme penceresinde "Bu bilgisayardan kaldır".

Yakalama davranışı aynı: seçtiğiniz klavye/fare tuşuna basınca ekran görüntüsü sessizce kaydedilir; ekranda hiçbir şey görünmez.
