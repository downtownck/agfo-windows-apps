## AGFO AI Editor 2.6.1 — sunucu yoğunken çeviri durmuyor

- **"429 – Proxy at capacity" artık işi durdurmuyor.** Yapay zekâ servisi "şu an doluyum, biraz sonra deneyin" dediğinde (429, 502, 503, 504, 529) istek kendiliğinden yeniden gönderilir. Bekleme süresi sunucunun istediği kadardır (Retry-After); sunucu bir süre belirtmezse 2, 4, 8, 16, 30 saniye diye artar. En fazla 6 kez denenir.
- **Aynı anda giden istekler birlikte yavaşlar:** belge çevirisinde 4 istek aynı anda gidiyorsa ve biri "yoğun" yanıtı alırsa, diğerleri de bekler. Böylece sunucuya yük binmeye devam etmez.
- **Bekleme durum çubuğunda görünür:** "⏳ Sunucu yoğun; 8 sn sonra yeniden deneniyor". **Durdur** düğmesi beklemeyi de keser.
- Denemeler biter ve servis hâlâ yoğunsa açık bir mesaj çıkar: birkaç dakika sonra yeniden deneyin ya da "Aynı anda" istek sayısını azaltın. Çevrilen bölümler canlı çeviri sekmesinde kalır.
- AI Manager'ın kalıcı ayar hataları ("Model yok" gibi 503 yanıtları) beklemeyle düzelmez; bunlar eskisi gibi hemen bildirilir.
