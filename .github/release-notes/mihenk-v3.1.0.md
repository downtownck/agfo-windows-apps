# AGFO Mihenk 3.1.0

3.0.0'daki bir açılış çökmesi giderildi ve dil seçimi sorumluluk reddinin önüne alındı.

## Açılışta çökme (3.0.0'ı etkiliyordu)

Modern görünüm bileşeninin (ttkbootstrap) onay kutusu ve radyo düğmesi çizimleri paket
içindeki PNG dosyalarından geliyor. Bu dosyalar EXE'ye girmediğinde uygulama açılırken
`FileNotFoundError: checkbox-checked.png` ile kapanıyordu — kütük, kayıtlar ve yedekler
yerinde olmasına rağmen uygulamaya girilemiyordu.

Üç yerden düzeltildi:

1. **Uygulama artık çökmüyor.** Stil kurulumu tek bir korumalı adımda; çizim motoru ne
   sebeple olursa olsun hata verirse uygulama klasik çizime düşüp açılmaya devam ediyor.
   Ayarlar ekranı sebebi yazıyor. Görünüm bir ayrıntıdır; kayıtlara erişimi kesmemeli.
2. **Öz-denetim artık gerçekten çiziyor.** Önceki sürümde öz-denetim bileşeni yalnızca
   içe aktarıyordu — içe aktarma başarılıydı, çökme ise stiller kurulurken oluyordu, yani
   kullanıcı uygulamayı ilk açtığında. Artık öz-denetim temayı uyguluyor; bileşen kurulu
   olup çizim yapamıyorsa derleme orada duruyor ve bozuk EXE hiç üretilmiyor.
3. **Çizim dosyaları pakete açıkça ekleniyor.** `--collect-all` yanında dosya klasörü
   `--add-data` ile de veriliyor, böylece PyInstaller tarafındaki bir eksiklik sessizce
   geçmiyor.

Kurulu 3.0.0 açılmıyorsa: Kurulum ZIP'ini indirip `Derle-ve-Kur.cmd` çalıştırın.
Kayıtlarınıza dokunulmaz.

## Dil seçimi artık önce

İlk açılışta önce **Dil / Language** penceresi çıkıyor, sonra sorumluluk reddi. Kabul
ettiğiniz metni kendi dilinizde okuyorsunuz. Türkçe dışında bir dil seçilirse uygulama
kendini yeniden açıyor ve sorumluluk reddi o dilde geliyor.

Pencere yalnızca bir kez çıkar; sonrası Ayarlar ekranının işi. İki dil adı da kendi
dilinde yazıyor ("Türkçe", "English"), çünkü seçimi yapacak kişi henüz hangi dili
gördüğünü seçmedi.

## Doğrulananlar

Çekirdek 59, arayüz 35 (hem klasik hem modern çizimle), xlsx 5, dil 13 test; güncelleme
modülü testi. Çökme için ayrı bir regresyon testi var: çizim motoru bilerek bozuluyor ve
uygulamanın ayakta kalıp klasiğe düştüğü doğrulanıyor. Öz-denetimin bozuk paketi
yakaladığı da denendi.
