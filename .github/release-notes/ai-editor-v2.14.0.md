## AGFO AI Editor 2.14.0 — Bu bilgisayarda Arapça, İngilizce ve İspanyolca ses

- **Yerel ses seçimi:** Ses sekmesinde "Bu bilgisayar" seçiliyken yeni bir **Yerel ses** listesi var. Bu bilgisayarda kurulu bütün ses servisleri ve sesleri burada görünür:
  - EMA Lightning (Türkçe)
  - SILMA (Arapça): Fusha ve Mısırlı deneme sesi
  - Habibi (Arapça): Mısır ve Fusha modelleri
  - Qwen3-TTS (İngilizce, İspanyolca): hazır sesler; metnin dili paragraf paragraf kendiliğinden seçilir
  - `data\voices` klasörüne eklenen kendi kayıtlarınız
- **▶ Dene:** Seçili sesin diline göre (Türkçe, Arapça ya da İngilizce ve İspanyolca) kısa bir örnek okur.
- **Her yerde aynı ses:** Sesli oku, Ses dosyası ve Sesli çizgi roman / Video seçilen yerel sesle çalışır. Ses değişince önceden üretilmiş sesler yeniden kullanılmaz.
- **Türkçe dışındaki seslerde sınırlar:** AI okuma metni ve telaffuz sözlüğü yalnız Türkçe seste var; diğer dillerde metin olduğu gibi okunur. Arapçada rakamlar servis tarafında yazıya çevrilir.
- **Kurulum:** Arapça servisler `AGFO-Arapca-Servis-Kur.cmd` ile kurulur; betik deneme betikleriyle kurulmuş modelleri kullanır ve yeni model indirmez. İngilizce ve İspanyolca servis `AGFO-Ses-Qwen-Kur.cmd` ile kurulur. Kurulu servis yoksa liste görünmez; Türkçe EMA eskisi gibi çalışır.
