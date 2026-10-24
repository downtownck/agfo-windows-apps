## AGFO AI Editor 2.5.0 — BRCGS teknik gözden geçirme

Beş standardın teknik gözden geçirme kaynakları uygulamaya eklendi: gözden geçirme skill talimatı (rapor yazım kuralları), resmi "How to complete the audit report" rehberleri (F910, P702, CP417, AB309, SD408) ve standart gereklilikleri.

- **✔ Technical review** (rapor menüsünde yeni sayfa): rapor, AI kullanmadan anında denetlenir. Hata / uyarı / bilgi olarak listelenir; her bulgunun kuralı ve kaynağı (rehber ya da skill) gösterilir; "→ Go to" ile ilgili alan ya da bölüm açılır.
  - Rehbere göre: zorunlu (MANDATORY) boş alanlar, boş bırakılamayan "Exclusions from scope" ("None" yazılmalı), dışlama varsa gerekçe, kapsamda yasak sözcükler (AB: trade/trading; CP: sales, marketing, trade…), çok uzun ürün listesi, tarih sırası (bitiş ≥ başlangıç, sertifika tarihi, yeniden denetim tarihi), boş bölümler (birleşik kutular ve boş modüller doğru değerlendirilir), kısa metin.
  - Skill kurallarına göre: yer tutucu ve bitmemiş metin ([..], TBC, "Click or tap here"), öznel ifadeler (appears, seems, probably, likely), birinci/ikinci şahıs (we, our, you), "meets / compliant with Clause X" cümleleri, anlatımda DD.MM.YYYY dışı tarih, İngilizce raporda Türkçe metin, Detaylı Raporda kişi adı (katılımcı ve denetim ekibi tablolarındaki adlarla).
  - NA ve NC: gerekçesiz NA, NA sayılan ama metni olan bölüm, maddesiz ya da Türkçe NC, NC metninde neden/sonuç yorumu.
- **✨ AI: revise this section by the rules:** bölüm metnini skill talimatı, ilgili rehber kısmı, standart gereklilikleri ve bulunan sorunlarla birlikte yeniden yazar. Yalnız rapordaki ve kanıttaki bilgiler kullanılır; NC eklenmez. Önceki metin sürüm geçmişinde kalır.
- **Reviewer comments → responses:** belgelendirme kuruluşunun teknik gözden geçirici yorumlarını yapıştırın. AI her maddeyi "[n]. Clause X.X.X - konu" biçiminde, yalnız raporun metni ve kanıtıyla yanıtlar; kanıt yoksa "No records were provided for …" yazar. Bir yanıt tek tıkla ilgili bölümün metnine eklenebilir ya da metnin yerine konabilir. Yorumlar ve yanıtlar raporla birlikte saklanır.
- **AI rapor metni** artık skill kurallarına uyuyor: edilgen çatı, "the company", DD.MM.YYYY, belge referans biçimi, kişi adı yerine görev unvanı, "Clause X'e uygundur" cümlesi yok.
- **Düzeltmeler:**
  - Word görünümünde bazı tablo hücreleri (denetim ekibi, GFSI geçmişi) "Official tables" yerine rapor bilgisini açıyordu.
  - Seçimli alan düzenleyicisi dardı ve listesi bir tık daha istiyordu; artık geniş ve liste açık geliyor.
  - NA, NC ve tablo satırları onay sorulmadan siliniyordu.
  - Birleşik kutunun metni başka bir maddede yazılıysa bölüm sayfası bunu söylüyor ve o maddeye götürüyor.
