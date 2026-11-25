# AGFO Mihenk 1.1.0

Bu sürüm iki şeye bakıyor: uygulamayı ilk kez açan biri ne görüyor, ve yeni sürümden nasıl
haberdar oluyor.

## İlk açılış

Boş bir kütükle karşılaşan kişi uygulamanın ne yaptığını göremiyordu — özellikle de asıl
ayırt edici davranışını, kalibrasyon uygunsuz çıktığında varlığın karantinaya alınmasını.
Artık ilk açılışta bir karşılama penceresi çıkıyor ve iki yol sunuyor:

- **Demo veriyle başla** — bir dolum hattının sekiz varlığı, yedi planı, dört talebi ve üç
  kalibrasyon kaydı kurulur. Kayıtlardan biri bilerek uygunsuzdur: varlığı karantinaya almış
  ve bir etki değerlendirmesi açmıştır.
- **Boş başla** — doğrudan kendi ekipmanınızı girersiniz.

Pencere yalnızca bir kez çıkar. Demo veri kurulmuşsa Ayarlar ekranından tek tıkla temizlenir;
kodu `DEMO-` ile başlayan varlıklar ve onlara bağlı kayıtlar dışında hiçbir şeye dokunmaz.

Boş listeler de artık sessiz değil: her ekran, o ekranda hiç kayıt yokken ne yapılması
gerektiğini bir satırla söylüyor.

## Otomatik güncelleme denetimi

Açılıştan birkaç saniye sonra GitHub Releases arka planda sessizce denetleniyor (altı saatte
bir defadan sık değil). Yeni sürüm varsa durum çubuğunda bir **Güncelle** düğmesi beliriyor;
tek tıkla iniyor ve kuruluyor. 1.0.0 kuranlar bu sürümü düğmeye basmadan görecek.

İndirilen dosya SHA-256 ile doğrulanıyor; özet yoksa dosya kullanılmıyor. Kayıtlarınız
(`%APPDATA%\AGFO\Mihenk`) güncellemeden etkilenmiyor.

## Testler

38 çekirdek, 21 arayüz testi, güncelleme modülü ve EXE öz-denetimi — hepsi koşuldu ve geçti.
