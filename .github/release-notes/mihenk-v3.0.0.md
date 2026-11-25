# AGFO Mihenk 3.0.0

İngilizce arayüz ve ilk kurulumda onaylanan sorumluluk reddi.

## İngilizce

Menü, ekranlar, pencereler, hata iletileri, boş liste yönlendirmeleri, demo veri ve
yazdırılabilir rapor artık iki dilde. 691 metin çevrildi.

Dil **Ayarlar** ekranından seçilir. Seçim kaydedilince uygulama kendini yeniden
başlatmayı teklif eder; menü, tablo başlıkları ve durum etiketleri modül yüklenirken
kurulduğu için dil çalışırken değiştirilmiyor. Yarısı bir dilde yarısı ötekinde bir
ekran, kısa bir yeniden başlatmadan kötüdür.

**Kayıtlar etkilenmez.** Çevrilen şey yalnızca ekranda görünen metin. Veritabanına
yazılan durum anahtarları (`quarantined`, `result_entered`), birim kodları (`hour`,
`adet`) ve stok hareket gerekçeleri (`consume`, `scrap`) her iki dilde de aynı kalır.
Türkçe girilmiş bir kayıt İngilizce arayüzde doğru okunur, tersi de geçerli.

Yazdırılabilir rapor `lang="en"` bildirir ve içinde Türkçe metin kalmaz.

Çeviri açığı elle değil testle ölçülüyor: `tests/test_i18n.py` görünen metinleri
kaynaktan AST ile çıkarıp karşılığı olmayanı listeler, sözlükte kaynakta bulunmayan
ölü girdi kalmasına da izin vermez. Yeni bir metin eklendiğinde test kendiliğinden
haberdar olur.

## Sorumluluk reddi

Uygulama ücretsiz yayınlandığı için sorumluluk reddi iki yerde gösteriliyor ve
onaylanmadan kullanılmıyor:

- **Derle-ve-Kur.cmd** kurulumdan önce metni yazar ve onay ister; reddedilirse kurulum
  yapılmaz. Güncelleme yolunda (`/update`) yeniden sorulmaz.
- **İlk açılışta** modal bir pencere çıkar; kutu işaretlenmeden onay düğmesi açılmaz,
  reddedilirse uygulama kapanır. Onay sürüm numarasıyla saklanır, metin esaslı
  değişirse yeniden sorulur.

Metin ayrıca Ayarlar ekranının altında durur ve `DISCLAIMER.txt` olarak pakete girer.
Tek kaynaktan, `mihenk_legal.py` içinden üretilir; dosyanın kaymadığını test doğrular.

Metin dört şeyi söyler: garanti verilmediğini; yazılımın bir kalite yönetim sisteminin,
akredite kalibrasyonun ya da yasal uygunluk değerlendirmesinin yerine geçmediğini;
kullanımından doğan zarardan sorumluluk kabul edilmediğini; ve yazılımı kullanmanın
AGFO ile bir belgelendirme ilişkisi kurmadığını, hiçbir denetimde avantaj sağlamadığını.

## Kurulum

`AGFO-Mihenk-v3.0.0-Kurulum.zip` dosyasını indirip açın ve `Derle-ve-Kur.cmd`
çalıştırın. Kurulu bir 2.x sürümü varsa uygulama güncellemeyi kendisi indirir; kayıtlara
dokunulmaz.

## Doğrulananlar

Çekirdek 59, arayüz 32 (hem klasik hem modern çizimle), xlsx 5, dil 13 test; güncelleme
modülü testi; EXE öz-denetimi `ui=modern i18n=691/en,tr` bildiriyor.
