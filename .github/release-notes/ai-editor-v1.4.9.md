## AGFO AI Editor 1.4.9: PDF çevirisinde ince ayar

CP410 (Denetçi yetkinliği) belgesinin çevirisinde görülen küçük hatalar düzeltildi.

- **Madde işaretleri:** Word'den gelen PDF'lerde madde işareti ayrı bir Symbol yazı tipi nesnesi. Bu nesne artık yerinde kalıyor, çeviriye girmiyor; maddeler de ayrı ayrı çevriliyor. Önceden işaretler kutu (□) olarak çıkıyor, maddeler tek paragrafta birleşiyordu. Bazı paragraflar tamamen kutulardan oluşuyordu; bunun nedeni paragrafın Symbol yazı tipiyle yazılmasıydı. Artık metin hiçbir zaman Symbol, Wingdings gibi yazı tipleriyle yazılmıyor ve paragrafın yazı tipi en çok kullanılan yazı tipinden seçiliyor.
- **İçindekiler:** Numara sütunu ile başlık ayrı kalıyor, satırlar birleşmiyor. Nokta dizisi, çeviri satıra sığacak şekilde kısaltılıp uzatılıyor; sayfa numarası hizada kalıyor.
- **Tablolar ve akış şeması kutuları:** Hücre çizgileri ve kutu kenarları algılanıyor; çeviri komşu hücreye ya da kutunun dışına taşmıyor. Sütunları ayıran sekmeler artık satırları birleştirmiyor ("Baskı ve kaydedilmiş DVD'ler").
- **Görünmeyen metin:** Kırpma yolunun dışında kalan (ekranda görünmeyen) metin çevrilmiyor. Önceden akış şemasında kutunun altında "ve 1 onay denetimi" gibi fazladan satırlar beliriyordu.
- **Tek satırlık paragraflar:** Çeviri uzunsa önce alttaki boşluğa ikinci satır olarak sarılıyor; okunamayacak kadar küçültülmüyor.
- **Paragraf ayrımı:** Bilinçli satır sonları (A1…A9 listesi, adres satırları, iki nokta ile biten giriş cümleleri) ayrı kalıyor. Sayfa ortasına tesadüfen denk gelen sola hizalı satırlar artık ortalanmıyor.
- **Satır aralığı:** Uzayan paragraf bir sonraki paragrafla arasındaki boşluğu yemiyor.
- **Tutarlılık ve hız:** Aynı metin (üst bilgi, alt bilgi, tekrarlanan tablo hücreleri) bir kez çevriliyor ve her yerde aynı kullanılıyor. "Page 3 of 20" gibi yalnızca sayısı farklı satırlar tek örnekten üretiliyor. Önceden alt bilgi her sayfada farklı çevriliyordu ("Sayfa 1 / 20", "20 sayfanın 12. sayfası", "Page 6 of 20"). Türkçe ekin sayıya bağlı olduğu durumlar (1'de / 3'te) ayrıca çevriliyor.
- Modelin yanıtındaki sekme, görünmez karakter ve özel alan karakterleri artık kutu olarak çizilmiyor.
