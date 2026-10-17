## AGFO BackupSync 2.3.0 — GitHub'dan tek tıkla güncelleme

- Bildirim alanı uygulaması açılıştan 20 sn sonra ve 12 saatte bir yeni sürümü denetler; yeni sürüm varsa Windows bildirimi gösterir ve menüde **Güncelle: vX (tek tık)** belirir. Elle denetim: **Güncellemeleri denetle**.
- Tek tık: AGFO-BackupSync-Setup.exe indirilir, GitHub SHA-256 özetiyle doğrulanır, yönetici onayıyla sessiz güncelleme kipinde çalışır; masaüstü kısayolu / otomatik başlatma tercihleri korunur, tepsi uygulamasının kapanması beklenir ve uygulama normal kullanıcı yetkisiyle yeniden açılır.
- Kurulum dosyaları bu sürümden itibaren GitHub Actions'ın Windows makinesinde derlenir (yerelde Python/PyInstaller kurmak gerekmez).
- 2.2.2'den geçiş: bu sürümdeki **AGFO-BackupSync-Setup.exe** dosyasını bir kez indirip çalıştırın. Profiller, loglar ve zamanlı görevler korunur.
- Not: EXE dosyaları kod imzalı değildir; Windows SmartScreen ilk çalıştırmada uyarı gösterebilir ("Ek bilgi > Yine de çalıştır").
