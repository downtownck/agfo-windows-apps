## AGFO Mic Monitor 1.4.0: Prompter ile sesli metin kaydı

Mic Monitor artık yalnızca şarkı için değil, metin okuyarak yapılan ses kayıtları için de kullanılabiliyor: seslendirme, anlatım, eğitim videosu sesi gibi. AGFO Prompter eklentisinin çalışma biçimi korunuyor; buna düşük gecikmeli dinleme ve hizalı kayıt ekleniyor.

**Prompter kipi** ("Prompter / söz ekranı" > "Kip" düğmesi):
- Metin, pencereye sığan bölümlere ayrılır. Ekrana sığmayan uzun paragraflar cümle sınırlarından bölünür.
- **İleri:** Boşluk, PageDown, ↓ ya da →. **Geri:** PageUp, ↑ ya da ←. **Başa:** Home. Sunum kumandaları da bu tuşları gönderdiği için kumandayla geçebilirsiniz.
- Altta sıradaki bölümün ilk kelimeleri ve "3 / 12" gibi bölüm sayacı görünür.
- Tam ekran (F11) ya da ikinci monitörde kullanılabilir. Yazı boyutu A− / A+ ile değişir; değişince bölümler yeniden hesaplanır.

**Kayıt:**
- Pencerede "● Kayıt" düğmesi var. Ayarlanabilir geri sayımdan sonra (varsayılan 3 sn) kayıt ilk bölümden başlar; kayıt süresi sağ üstte kırmızıyla görünür.
- Kayıt sırasında her bölüm geçişi zamanıyla birlikte işaretlenir:
  - İşaretler WAV dosyasının içine yazılır (cue/label). Cool Edit ve Adobe Audition bunları işaret listesinde gösterir; ffmpeg bölüm olarak okur.
  - Ayrıca `Kayit_..._bolumler.txt` dosyası yazılır. Audacity'de Dosya > İçe Aktar > Etiketler… ile açılır.
- Böylece her bölümün kaydın neresinde başladığını tek tıkla bulursunuz; yanlış okunan bir bölümü bulup tekrar almak kolaylaşır.

**Fon müziği:**
- Altyapı sekmesindeki yeni "Döngüde çal" seçeneğiyle müzik sona gelince baştan devam eder.
- Kayıt bitince ses ayrı, karışım ayrı dosyaya yazılır. Karışımda müzik konuşma boyunca döngüde çalar ve sonda 2 saniyede yumuşakça kısılır.
- Bölüm işaretleri karışım dosyasına da eklenir.

**İçe aktarma:** TXT, Word (.docx), LRC ve Markdown (.md; başlık, madde, vurgu ve bağlantı işaretleri temizlenir). Yapıştırma da mümkün.

Şarkı sözü kipi (müziğe bağlı akış ve "Zamanla") aynen duruyor.
