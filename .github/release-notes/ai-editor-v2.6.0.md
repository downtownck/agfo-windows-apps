## AGFO AI Editor 2.6.0 — rahat düzenleme: iki sütun, geri al, sayfa gezinme, yazım denetimi

- **Bölüm düzenleyicisi iki sütun:** kanıt kutuları solda kayar; İngilizce rapor metni, AI düğmesi, sözcük sayısı ve Önceki / Kaydet / Sonraki sağda sabit durur. Uzun bölümlerde rapor metnini görmek için artık aşağı kaydırmak gerekmiyor. Sütunlar arasındaki çizgi sürüklenebilir; seçilen oran sonraki bölümlerde de korunur.
- **Word görünümünde geri al:** sayfada yapılan her değişiklik (alan ya da rapor kutusu) **Ctrl+Z** ya da çubuktaki **↶ Undo** ile geri alınır; düğme neyi geri alacağını gösterir (son 50 değişiklik).
- **Esc artık sormadan silmiyor:** yerinde düzenleyicide metin değiştiyse Esc önce "Discard changes?" diye sorar.
- **Word görünümünde gezinme:**
  - Çubukta **Page x / N**: kaydırdıkça güncellenir; sayı yazıp Enter ile o sayfaya gidilir. Page Up / Page Down sayfa sayfa ilerler.
  - **Go to** listesi: rapor bilgisi, alan grupları, her bölüm (madde numarası ve başlığıyla), NA, NC ve resmi tablolar. Seçilen yer sayfada açılır.
  - **Sol menü** Word görünümündeyken formu açmaz, belgede o yere gider. Belgede karşılığı olmayan sayfalar (Technical review, Preview, Version history) yine kendi sayfasında açılır.
- **İngilizce yazım denetimi:** rapor metni, Word görünümündeki yerinde düzenleyici, NA gerekçesi, NC metni ve düzeltici faaliyet kutularında hatalı sözcükler kırmızı alt çizgiyle işaretlenir. Sağ tık: öneriler, sözlüğe ekle, tümünü yoksay, kes/kopyala/yapıştır. Windows yazım servisi kullanılır (en-GB, yoksa en-US); ayarlarda yazım denetimi kapalıysa çalışmaz.
