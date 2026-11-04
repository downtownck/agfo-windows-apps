## AGFO AI Editor 2.7.0 — klasörle sohbet, denetim sohbeti, Word'deki gibi üst/alt bilgi

- **Sekmelerde × düğmesi:** her açık belgenin, PDF'in ve BRCGS raporunun sekmesinde kapatma düğmesi var. Kaydedilmemiş değişiklik varsa önce sorar, yoksa hemen kapatır. Orta tıklama ve Ctrl+W da çalışmaya devam ediyor.
- **Klasörle sohbet (Kaynaklar › 📁 Klasör ekle):** bir klasör seçin, içindeki belgeler alt klasörleriyle birlikte okunur: PDF, Word, Excel, PowerPoint, metin, CSV ve e-posta. OneDrive ve Google Drive klasörleri de bilgisayarda birer klasör olduğu için doğrudan seçilebilir.
  - Belgeler ağaçta klasörün altında, göreli yollarıyla listelenir. Klasörü seçince sohbet yalnız o klasörle, tek belge seçince yalnız o belgeyle yapılır; yanıtlar alıntı bağlantılı gelir.
  - **Belgeleri analiz et:** hangi belgeler var, her biri ne hakkında, konulara göre gruplama, kopya ya da eski sürüm gibi görünenler ve eksik görünen belge türleri. Yüzlerce belgede de çalışır: her belge listeye girer.
  - Gizli klasörler, Office geçici dosyaları (~$) ve 200 MB üstü dosyalar atlanır. Bir klasörden en fazla 500 belge okunur. Klasör uygulama yeniden açılınca tekrar taranır, böylece eklenen belgeler de gelir. Okuma ilerlemesi Kaynaklar panelinde görünür.
- **Denetim artık bir sohbet:** standart, madde ve denetim işini (uygunsuzluk bulgusu, uygunluk ifadesi, DÖF değerlendirmesi…) seçin, **Denetle**'ye basın. Yanıt panelde gelir; ardından aynı belge üzerinden soru sorabilirsiniz ("bu bulgu major mı?", "hangi kanıt eksik?").
  - **Belge değiştirilemiyorsa durmuyor:** PDF'de, açık belge yokken (kutuya yazdığınız metin denetlenir) ya da çok uzun metinde (ilk bölüm denetlenir) yanıt yine gelir. **Yeni sekmede aç** ile kullanılır.
  - Düzenlenebilir belgede **Belgeye uygula** önce fark penceresini açar; siz onaylamadan belge değişmez.
- **Üst/alt bilgisinde tablo olan Word belgeleri:**
  - **Kayıtta korunuyor:** tablo, logo, alanlar ve ilk sayfa farkı dahil özgün üst/alt bilgi aynen geri yazılır. Bu sürüme kadar kaydedince düz metne dönüyordu. Belgenin tablo stilleri de korunur. Üst/alt bilgi metnini editörde değiştirirseniz o düz metin yazılır.
  - **Word görünümü (Görünüm › 🖨 Word görünümü):** belge Word'ün çizdiği haliyle gösterilir: üst/alt bilgi tabloları, logolar, sayfa düzeni. Böyle bir belge açıldığında kendiliğinden bu görünümde gelir. **✎ Düzenle** ya da çift tıklama metin düzenlemeye döner; değişiklikten sonra Word görünümü editördeki hali çizer.
- **Düzeltme:** arka plandaki belge okuma, kapanan pencerelerin Tk nesnelerini yanlış iş parçacığında bırakabiliyordu. Bu, seyrek çökmelere yol açabiliyordu.
