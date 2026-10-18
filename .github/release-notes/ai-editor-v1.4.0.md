## AGFO AI Editor 1.4.0 — Word gibi biçimli editör, belge çevirisi, PDF'de yerinde metin düzenleme

### Biçimli editör (sayfa görünümü)
- Yeni biçim çubuğu: **Normal / Başlık 1-3 / Alıntı**, **K** (kalın), *İ* (italik), A (altı çizili), yazı rengi, madde ve numaralı listeler (Tab ile alt düzey), sola / ortala / sağa hizalama.
- **Sayfa görünümü:** beyaz A4 sayfa ve kenar boşluklarıyla; A−/A+ sayfayı yakınlaştırır. Düğmeyle koyu temaya dönülebilir. Durum çubuğunda yaklaşık sayfa sayısı görünür.
- **Resim:** ekle (PNG, JPG, GIF, BMP), sağ tıkla boyut (%25 / %50 / %75 / sayfa genişliği / özgün), hizala, değiştir, farklı kaydet, kaldır.
- **Tablo:** satır × sütun seçerek ekleyin; Tab hücreler arasında gezer; sağ tıkla satır / sütun ekleyin, silin ya da tabloyu silin.
- **Word belgeleri biçimleriyle açılır ve kaydedilir:** başlıklar, kalın / italik / altı çizili, renkler, madde ve numaralı listeler, tablolar, resimler, hizalama ve sayfa sonları. Üst / alt bilgi, dipnot ve yorumlar gösterilmez; özgün dosyanın üzerine yazmadan önce sorulur.
- `.md` ve `.html` dosyaları da biçimli açılır. `.md` kaydında resimler yanındaki `_resimler` klasörüne yazılır. `.txt` düz metin olarak kalır; istenirse biçimlendirmeye açılır.
- **Geri al / yinele artık biçimleri, listeleri, tabloları ve resimleri de geri getirir.**
- Biçimli belgeler arasında kopyala / yapıştır biçimi korur. Bul / değiştir değiştirdiği metnin biçimini korur.
- AI eylemleri (İçerik, Denetim, Çeviri, Sohbet) biçimli metinle çalışır: kalın / italik, başlık, liste, tablo ve resim yer tutucuları yanıtta korunur. Yanıtta düşen bir resim kaybolmaz, bölümün sonuna eklenir.

### Belge çevirisi
- Çeviri sekmesinde ve biçim çubuğunda **🌐 Belgeyi çevir**: tüm belge parça parça çevrilir. Başlık, liste, hizalama, tablo yapısı ve resimler yapay zekâya gitmeden yerinde kalır; satır içi kalın / italik korunur.
- Çıktı: **biçimli yeni belge**, **yan yana görünüm** (özgün | çeviri, paragraf eşlemeli eşzamanlı kaydırma, tıklanan paragrafın karşılığı vurgulanır) ya da ikisi. Yan yana görünüm **iki sütunlu Word tablosu** olarak kaydedilebilir.
- Açık **PDF de çevrilebilir** (PDF düzenleyicide 🌐 Çevir). Sayfa satırları paragraflara birleştirilir. Şifreli PDF'lerde metin çıkarma izni aranır.
- Eksik dönen parçalar tek tek yeniden istenir; yine gelmezse özgün haliyle bırakılır ve bildirilir. "Durdur" çeviriyi keser.

### PDF'de yerinde düzenleme
- **✏ Metni düzenle:** bir satıra tıklayın, metni düzeltin. Eski metin sayfadan gerçekten çıkarılır; yenisi aynı yere, benzer yazı tipi, boyut, kalınlık ve renkle **gerçek, aranabilir metin** olarak yazılır. Türkçe karakterler desteklenir. Fare satırın üstündeyken düzenlenecek alan çerçevelenir.
- **🗑 Resmi sil:** PDF'deki resim içerikten kaldırılır (beyaz kutuyla örtülmez).
- Geri al ile her iki işlem de döner. Form / şablon nesnesi içindeki ve döndürülmüş metin için "Üstüne yaz" önerilir. Şifreli PDF'lerde içerik değiştirme izni aranır; kayıtta özgün izinlerle yeniden şifrelenir.

### Teknik
- Yeni modüller: `agfo_richdoc` (DOCX / Markdown / HTML), `agfo_richtext` (biçimli editör + geri al), `agfo_doctranslate`, `agfo_compare`, `agfo_pdf_edit` (pdfium).
- Test sayısı 69'dan 104'e çıktı (biçimli belge, editör, çeviri, PDF düzenleme). Derlenmiş EXE'nin kendi testine Word gidiş-dönüş, PDF metin düzenleme ve çeviri ayrıştırma eklendi.
