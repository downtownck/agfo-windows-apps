## AGFO Mic Monitor 1.3.0: Şarkı sözü ekranı

Altyapı üzerine şarkı söylerken sözleri büyük bir ekranda, şarkıyla birlikte akarken görebilirsiniz.

- **Söz kaynakları:**
  - Düz metin (.txt). Eski Windows Türkçe kodlaması da okunuyor.
  - Zaman damgalı söz (.lrc).
  - Word belgesi (.docx).
  - Kopyala-yapıştır.
- **Otomatik eşleşme:** Altyapıyla aynı adlı bir söz dosyası (`Şarkı.mp3` için `Şarkı.lrc` / `.txt` / `.docx`) varsa kendiliğinden yüklenir.
- **Söz ekranı:**
  - Ayrı bir pencerede açılır; tam ekran (F11) olabilir ya da ikinci monitöre taşınabilir.
  - O an söylenen satır beyaz ve büyük, sıradaki satır açık renkli, diğerleri soluk.
  - Metin, altyapının çalma konumuna göre yumuşakça kayar. Kayıt sırasında, provada ve altyapıyı ileri-geri sardığınızda hep doğru satırda durur.
  - Yazı boyutu A− / A+ düğmeleriyle ya da + / − tuşlarıyla değiştirilir ve kalıcı olarak saklanır.
- **Zamanlama:**
  - LRC dosyalarında satırlar damgalarına göre tam zamanında gelir.
  - Düz metinde satırlar başlangıçta şarkı süresine dağıtılır; boş satırlar kıta arası sayılır.
  - "Zamanla" düğmesiyle altyapı baştan çalar; her satırın başında BOŞLUK tuşuna basarsınız (geri almak için Backspace, bitirmek için Esc). Zamanlama, söz dosyasının yanına aynı adla `.lrc` olarak kaydedilir. Sonraki kayıtlarda sözler sizin temponuzla akar.
- **Altyapısız kayıt:** Sözler kaydın süresine göre akar.
- Söz ekranı her karede tek bir hafif işlem yaptığı için dinlemeyi ve kaydı etkilemez.

Güncelleme: 1.2.0 kuruluysa uygulama içinden (yeşil şerit ya da "Güncelleme…"). Daha eski bir sürüm kuruluysa bir kez elle kurun: Kurulum ZIP'ini açıp `Derle-ve-Kur.cmd`'yi çalıştırın.
