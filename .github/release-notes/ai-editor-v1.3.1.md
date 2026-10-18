## AGFO AI Editor 1.3.1 — Şifreli (AES) PDF'ler açılıyor

- **"cryptography>=3.1 is required for AES algorithm" hatası giderildi.** BRCGS yayınları gibi AES ile şifrelenmiş, açma parolası olmayan PDF'ler artık PDF düzenleyicide açılır, çizilir ve okunur. Şifre çözme bileşeni EXE'ye eklendi.
- **Belge sahibinin izinlerine uyulur.** Şifreli PDF'lerde yayıncının koyduğu kısıtlar (vurgu/not, içerik değiştirme, sayfa düzenleme, form doldurma, metin çıkarma) okunur. İzin verilmeyen araçlar soluk görünür, üstte turuncu bir "🔒 Şifreli ve kısıtlı PDF" şeridi neyin yapılamayacağını yazar, durum çubuğunda "🔒 kısıtlı" görünür.
- **İzinli değişiklikler kaydedilirken belge yeniden şifrelenir:** çıktı aynı (birden çok kaynak varsa en kısıtlı) izinleri taşır, AES-256 ile şifrelenir ve yine parolasız açılır. Özgün sahip parolası kopyalanmaz.
- Sahibi metin çıkarmaya izin vermiyorsa "Sayfa metnini al", "Metin olarak aç" ve Kaynaklar'a ekleme açık bir Türkçe mesajla durur. Erişilebilirlik amaçlı metin izni olan belgelerde (çoğu BRCGS PDF'i) metin alınabilir.
- Açma parolası isteyen PDF'ler için anlaşılır bir mesaj gösterilir (parola girişi sonraki sürümde).
- Testler: şifreli PDF açma, çizim, izin denetimi, yeniden şifreleme ve karma kaynaklar; derlenmiş EXE'nin kendi testine AES-256 PDF senaryosu eklendi.
