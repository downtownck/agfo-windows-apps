## AGFO AI Editor 2.7.1 — Denetim Kaynaklar'daki belgelerle çalışıyor

- **Kanıt seçimi (Denetim › Kanıt):** Belge + Kaynaklar (varsayılan), Yalnız açık belge, Yalnız Kaynaklar. Seçim hatırlanır.
  - Kaynaklar seçildiğinde, Kaynaklar sekmesinde seçili belgeler ya da klasör (seçim yoksa tümü) standart, madde, denetim işi ve sorunuza göre aranır. Bulunan bölümler denetime kanıt olarak gönderilir.
  - Yanıttaki her iddianın yanında **[K#] atfı** var; tıklayınca kaynak belgedeki yer açılır. Sorularda aynı bölümler aynı etiketlerle kalır, yeni bulunanlar eklenir.
  - **Yeni sekmede aç** yanıtın sonuna kullanılan kaynakların listesini ekler. **Belgeye uygula** rapor metnine [K#] etiketlerini koymaz.
- **Boş sekme artık kanıt sayılmıyor:** açık belge boşsa (ör. "Adsız 1"), "Denetlenecek metin yok" demek yerine Kaynaklar kullanılır.
- Denetim panelindeki seçimler iki sütuna alındı; sohbete daha çok yer kaldı.
- Klasör eklenince kurulan arama dizini artık gerçekten kullanılıyor. 2.7.0'da yanlış anahtarla saklandığı için ilk soruda dizin yeniden kuruluyordu.
