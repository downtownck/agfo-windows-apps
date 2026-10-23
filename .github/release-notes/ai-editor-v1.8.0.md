## AGFO AI Editor 1.8.0 — WordCraft ile Word düzeyinde belge düzenleme

AI Editor artık belgeleri **WordCraft** içinde düzenleyebilir. WordCraft, ArtCraft ekibinin açık kaynaklı (MIT / Apache-2.0) Word benzeri kelime işlemcisidir: şerit menü, stil galerisi, cetveller, gezinme paneli, tablolar, üst/alt bilgi, sütunlar, değişiklik izleme, yorumlar, içindekiler, dipnot ve kaynakça, adres mektup birleştirme, karanlık mod; DOCX, ODT, RTF, HTML, Markdown okur/yazar, PDF verir. Arayüzü Türkçedir.

- Biçim çubuğunda yeni **📝 WordCraft ▾** menüsü: *Bu belgeyi WordCraft'ta aç*, *Yeni WordCraft belgesi*, *WordCraft'ta dosya aç…*. Kaydedilmiş bir DOCX/ODT/RTF doğrudan açılır; kaydedilmemiş belge biçimiyle (başlık, kalın/italik, liste, tablo) aktarılır.
- AI panelinde yeni **Hedef** seçimi: *Bu editör* / *WordCraft*. WordCraft seçiliyken AI ile düzenle, hızlı düğmeler, çeviri ve sohbet WordCraft'taki belgede çalışır:
  - Seçili metin (yoksa imlecin paragrafı, ya da *Tüm belge*) başlık, kalın/italik, liste ve tablo bilgisiyle okunur.
  - Sonuç WordCraft'a **izlenen değişiklik** olarak, "AGFO AI Editor" yazar adıyla yazılır; İncele sekmesinden tek tek ya da topluca kabul/ret edilir. (Ayarlar › WordCraft'tan kapatılabilir.)
  - Siz beklerken o bölüm değiştiyse öneri uygulanmaz, uyarı verilir.
  - Çeviri "yeni sekmede" modunda çeviri WordCraft'ta yeni belge olarak açılır.
- **Kurulum ilk kullanımda, yönetici izni olmadan:** resmi, kod imzalı WordCraft 0.10.0 ZIP'i (x64 / ARM64 / x86) GitHub'dan indirilir, SHA-256 ile doğrulanır ve `%LOCALAPPDATA%\Programs\AGFO-AI-Editor\WordCraft` altına açılır (~100 MB indirme). Türkçe yazım denetimi için LibreOffice Türkçe sözlüğü (MPL 2.0) de doğrulanarak kurulur.
- WordCraft kapatılırsa AI hedefi kendiliğinden bu editöre döner.

**Bilinen sınırlar:** WordCraft alfa aşamasındadır; önemli belgelerde yedek alın. Ayrı bir pencerede açılır (Win+← / Win+→ ile yan yana dizebilirsiniz). Ekran kartı gerektirir (DirectX 12; eski PC'lerde OpenGL). Belgeyi çevir (sayfa düzenli PDF çevirisi) ve Ses sekmesi bu editördeki belgeyle çalışmaya devam eder.
