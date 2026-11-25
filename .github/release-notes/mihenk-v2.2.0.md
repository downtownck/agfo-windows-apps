# AGFO Mihenk 2.2.0

Güncellemenin kendisini düzeltir. 2.1.0'a kadar otomatik güncelleme iki yerden kırıktı.

## "Erişim engellendi" hatası

Windows çalışan bir EXE'nin üzerine yazdırmaz. Yeni sürüm bu yüzden güncelleyici kipinde
başlatılır ve **uygulamanın kapanması** gerekir; yerine koyma işini güncelleyici yapıp
uygulamayı yeniden açar.

Mihenk kapanmıyordu. Güncelleyici 90 saniye boyunca kapanmayan ana süreci bekliyor, o
sırada indirilen dosyayı kilitli tutuyordu; ikinci deneme o kilitli dosyanın üzerine
yazamayınca `[WinError 5] Erişim engellendi` ile düşüyordu.

Artık güncelleyici başlatıldıktan sonra iki saniye beklenip ayakta olduğu doğrulanıyor
(güvenlik yazılımı hemen kapattıysa buradan anlaşılıyor) ve uygulama kapanıyor. Önceki
denemelerden kalan kilitli bir dosya varsa indirme ona takılmıyor, yanına yeni bir ad
açıyor.

Bir şey ters giderse kurulu sürüm değişmiyor ve sebebi açıkça yazılıyor.

## Kaynaktan çalışanlar

Kaynaktan çalıştırılan sürüm kendi kendini değiştiremez. Güncelle düğmesi artık bunu
söylüyor ve Kurulum ZIP'ini indirip `Derle-ve-Kur.cmd` çalıştırmanız gerektiğini belirtiyor.

## 2.1.0'daki düzeltme

Açık duran uygulama da yeni sürümü görüyor: denetim yalnızca açılışta değil, çalışırken de
saatte bir yineleniyor.
