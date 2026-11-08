## AGFO AI Editor 2.14.0 — Bu bilgisayarda Arapça ses (SILMA, Habibi)

- **Yerel ses seçimi:** Ses sekmesinde "Bu bilgisayar" seçiliyken yeni bir **Yerel ses** listesi var. Bu bilgisayarda kurulu bütün ses servisleri ve sesleri burada görünür:
  - EMA Lightning (Türkçe)
  - SILMA (Arapça): Fusha ve Mısırlı deneme sesi
  - Habibi (Arapça): Mısır ve Fusha modelleri
  - `data\voices` klasörüne eklenen kendi kayıtlarınız
- **▶ Dene:** Seçili sesin diline göre (Türkçe ya da Arapça) kısa bir örnek okur.
- **Her yerde aynı ses:** Sesli oku, Ses dosyası ve Sesli çizgi roman / Video seçilen yerel sesle çalışır. Ses değişince önceden üretilmiş sesler yeniden kullanılmaz.
- **Arapçada sınırlar:** AI okuma metni ve telaffuz sözlüğü yalnız Türkçe seste var; Arapça metin olduğu gibi okunur. Rakamlar servis tarafında yazıya çevrilir.
- **Kurulum:** Arapça servisler `AGFO-Arapca-Servis-Kur.cmd` ile kurulur. Betik, deneme betikleriyle kurulmuş modelleri kullanır ve yeni model indirmez. Kurulu servis yoksa liste görünmez; Türkçe EMA eskisi gibi çalışır.
