## AGFO AI Editor 1.4.2 — PDF'de yerinde düzenleme artık sayfayı bozmuyor

**Sorun:** 1.4.0/1.4.1'de "Metni düzenle" ve "Resmi sil", sayfanın tüm içeriğini pdfium ile yeniden üretiyordu. Tasarımlı belgelerde bu işlem özel renkleri (Separation/ICC), saydamlığı, kırpma yollarını ve yazı tipi kodlamalarını bozabiliyordu. Sonuç olarak metin bozuk yazı tipiyle, siyah bir kutunun içinde ya da beyaz zemin üzerinde beyaz görünüyordu.

**Düzeltme:**
- Sayfa artık yeniden üretilmiyor. Yalnız değiştirilen satırın metin komutları (ya da silinen resim) PDF içeriğinden çıkarılıyor; sayfanın geri kalanı bayt bayt aynı kalıyor. Yeni metin, sayfanın üstüne ayrı bir katman olarak ekleniyor.
- **Yazı tipi:** Özgün yazı tipi bilgisayarda kuruluysa aynısı kullanılıyor (ör. DejaVu Sans, Calibri, Arial, Times New Roman). Kurulu değilse ölçüleri en yakın yazı tipi seçiliyor; gerekirse satır genişliği özgüne yakın kalacak şekilde hafifçe ölçekleniyor.
- **Renk:** Metin rengi korunuyor; renkli zemindeki beyaz yazı beyaz kalıyor. Bildirilen renk zeminde görünmüyorsa sayfadaki gerçek görünen renk kullanılıyor.
- Aynı satırdaki bitişik parçalar birlikte değişiyor. Konumu silinen parçaya bağlı başka metin varsa o metin kaymıyor.
- Taranmış sayfaların görünmez metin katmanında (OCR) ve içerik yapısı yerinde değişikliğe uygun olmayan sayfalarda, eski satır zemin rengindeki bir kutuyla örtülüp yeni metin üstüne yazılıyor. Bu yeni metin Seç aracıyla taşınabiliyor ve düzenlenebiliyor.
- Testler: özel renk, saydamlık, kırpma, beyaz yazı ve kerning'li metin içeren bir sayfada düzenlenen satır dışında hiçbir pikselin değişmediği doğrulanıyor. Eski yöntem bu testte renkli şeridi siyaha çeviriyordu.
