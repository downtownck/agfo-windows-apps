## AGFO BackupSync 2.3.2 — Python DLL hatası düzeltmesi + AGFO koyu tema

- **Düzeltildi:** "Ağ Keşfi / SMB" ve "Sürücü Harfleri" sekmelerinde çıkan *Failed to load Python DLL … _MEI…\python312.dll* hatası. Tepsi uygulamasının (PyInstaller) gizli ortam değişkenleri GUI üzerinden yardımcı AGFO-BackupSync.exe'ye geçiyordu; artık tepsi, GUI ve kurucu her alt sürece temiz ortam verir.
- **Arayüz AGFO standardında:** System Care / SuperTools ile aynı koyu tema, "AGFO / SUPERTOOLS" başlık, koyu sekme şeridi, koyu liste / kutu / log alanları, düz düğmeler. Koyu zeminde koyu yazı yok; hiçbir işlev kaldırılmadı.
- Ekran görüntüsü: bu sürümdeki **AGFO-BackupSync-v2.3.2-ekran.png** (6 sekme).
- 2.3.0'dan geçiş: tepsi simgesine sağ tıklayıp **Güncelle: v2.3.2 (tek tık)**. Güncelleme başlamazsa bu sürümdeki **AGFO-BackupSync-Setup.exe** dosyasını bir kez elle çalıştırın; profiller, loglar ve zamanlı görevler korunur.
- Not: EXE dosyaları kod imzalı değildir; Windows SmartScreen uyarı gösterebilir ("Ek bilgi > Yine de çalıştır").
- 2.3.1'den farkı: açılır listeler (çalışma modu, kopyalama kuralı, sıklık, gün, sürücü harfi) de koyu temaya alındı.
