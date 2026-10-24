## AGFO AI Editor 2.3.0 — BRCGS raporlarında Word görünümü

- **Word görünümü:** BRCGS raporu, bilgisayarınızdaki Microsoft Word'ün çizdiği sayfalarla açılır: logo, üst/alt bilgi, renkli başlık bantları, tablolar, sayfa düzeni Word'deki gibi. Word yoksa LibreOffice kullanılır. Yakınlaştırma, sayfaya sığdırma ve fare tekerleğiyle kaydırma var.
- **Görünümler arası geçiş:** üstteki "📄 Word view / ✎ Form" düğmeleriyle geçilir. Word görünümünde bir yere tıklayınca formda o alan ya da rapor bölümü açılır (alan imleçle seçili gelir). Forma girilen her şey Word görünümüne döndüğünüzde sayfalara yansır.
- **İçe/dışa aktarma yok:** bir BRCGS DOCX'ini açınca (Dosya › Aç ya da rapor gezgini) soru sormadan rapor olarak açılır ve o dosyaya bağlanır. **Kaydet doğrudan bu dosyaya yazar.** Dosyadaki logo, üst/alt bilgi, şablon dışı her şey korunur; her kayıttan önce dosyanın önceki hali yedeklenir (son 10). Aynı dosyayı yeniden açmak aynı raporu açar.
- **Word'de düzenleme:** "Open in Word" dosyayı Word'de açar. Word'de kaydedip uygulamaya döndüğünüzde değişiklikler rapora otomatik yüklenir (burada kaydedilmemiş değişiklik varsa önce sorulur).
- **Fare tekerleği ve odak:** BRCGS ekranlarında tekerlek artık her yerde sayfayı kaydırıyor; giriş kutusu, etiket ya da açılır listenin üzerindeyken de. Açılır listelerin değeri tekerlekle yanlışlıkla değişmiyor. Tab ile gelinen alan görünür alana kaydırılıyor.
- **Düzeltme:** aynı dosyaya tekrar tekrar yazıldığında belge her kayıtta büyüyordu (boş metin düğümleri birikiyordu); artık ikinci ve sonraki kayıtlar bayt bayt aynı.
