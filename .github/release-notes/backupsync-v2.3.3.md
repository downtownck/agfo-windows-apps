## AGFO BackupSync 2.3.3 — profil kaydetme / Önizleme hatası düzeltmesi

- **Düzeltildi:** Var olan bir profil kaydedilirken, **Önizleme** veya **Şimdi çalıştır**'a basınca çıkan *Exception calling "Replace" with "3" argument(s): "Yol geçerli bir biçimde değil."* hatası. PowerShell, .NET'e verilen boş (null) değeri boş metne çeviriyordu; dosya değiştirme işlemi bu yüzden reddediliyordu.
- Aynı hata, çalışma sırasında canlı durum dosyasının güncellenmesini de sessizce engelliyordu; o da düzeldi.
- Bu durum için Windows'ta otomatik test eklendi (var olan JSON ve profil dosyasının üzerine yazma).
- 2.3.0–2.3.2'den geçiş: tepsi simgesine sağ tıklayıp **Güncelle: v2.3.3 (tek tık)**, ya da bu sürümdeki **AGFO-BackupSync-Setup.exe**'yi bir kez çalıştırın.
