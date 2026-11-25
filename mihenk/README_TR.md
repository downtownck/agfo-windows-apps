# AGFO Mihenk

Ekipman bakımı, kalibrasyon ve doğrulama takibi. Windows masaüstü uygulaması; veriler
bilgisayarda bir SQLite dosyasında durur, sunucu ya da internet bağlantısı gerekmez.

Kontrol listeleri, yedek parça stoğu, güvenilirlik göstergeleri ve denetime hazır Excel /
CSV / yazdırılabilir rapor çıktısı içerir.

Mihenk, altının ayarının denendiği taştır. Uygulamanın yaptığı iş de budur: ölçen
cihazın kendisini bir referansa vurup ayarını denetlemek.

## Neden ayrı bir kalibrasyon kaydı

Kaçan bir bakım gecikme yaratır. Kaçan bir kalibrasyon **geriye dönüktür**: o cihazın son
geçerli sonucundan beri ölçtüğü her şey şüpheye düşer. Mihenk bu farkı veri katmanında
tutar:

1. Kalibrasyon sonucu **uygunsuz** girildiğinde varlık aynı işlemde karantinaya alınır ve
   etkilenen aralığı uygunluğu gerçekten kanıtlayan son kayıttan doldurulmuş bir **etki
   değerlendirmesi** açılır.
2. Açık bir etki değerlendirmesi varken varlık hizmete **dönemez**.
3. Uygunsuz kalibrasyon kaydı, etki değerlendirmesi kapanmadan **kapatılamaz**.
4. Şartlı bir sonuç, yazılı bir kullanım sınırlaması olmadan kapatılamaz.

Bu kurallar ekranda değil `mihenk_states.py` içindeki tek geçit fonksiyonunda uygulanır.
Depolar `status` alanını doğrudan yazmaz; karantina kilidi bu yüzden gerçek bir kilittir.

## Sorumluluk reddi

Mihenk ücretsiz dağıtılır ve "olduğu gibi" sunulur; hiçbir garanti verilmez ve
kullanımından doğan zarardan sorumluluk kabul edilmez. Bir kalite yönetim sisteminin,
akredite bir kalibrasyonun ya da yasal bir uygunluk değerlendirmesinin yerine geçmez.
Tam metin [DISCLAIMER.txt](DISCLAIMER.txt) dosyasındadır; kurulumda ve ilk açılışta
gösterilir ve onaylanmadan uygulama kullanılmaz. Metin tek kaynaktan,
`mihenk_legal.py` içinden üretilir.

## Kurulum

1. Sürüm sayfasından `AGFO-Mihenk-vX.Y.Z-Kurulum.zip` dosyasını indirin ve açın.
2. **Derle-ve-Kur.cmd** dosyasını çalıştırın. Önce sorumluluk reddi yazılır ve onayınız
   istenir. EXE sizin bilgisayarınızda derlenir, bu yüzden
   "internetten indirildi" işareti taşımaz ve SmartScreen takılmaz. İlk çalıştırma derleme
   araçlarını indirdiği için birkaç dakika sürebilir.
3. Kısayollar: Başlat menüsü > AGFO ve Masaüstü.

İlk açılışta kütük boş olduğu için uygulama ne yaptığını gösteremez; bu yüzden bir karşılama
penceresi çıkar ve iki yol sunar: **demo veriyle başla** ya da **boş başla**. Demo seti kodu
`DEMO-` ile başlayan sekiz varlık, yedi plan, dört talep ve üç kalibrasyon kaydı kurar;
kayıtlardan biri bilerek uygunsuzdur, böylece karantina kilidi ilk dakikada görülür. Pencere
yalnızca bir kez çıkar ve demo veri Ayarlar ekranından tek tıkla temizlenir.

Yalnızca derlemek için `Sadece-Derle.cmd`, kaynaktan çalıştırmak için `Baslat.cmd`,
kaldırmak için `Kaldir.cmd`. Kaldırma kayıtlarınıza dokunmaz.

Gereken: Windows 10/11 ve tkinter'lı Python 3.10+ (derleme için).

## Dil

Arayüz Türkçe ve İngilizce. İlk açılışta dil sorulur — sorumluluk reddinden **önce**,
böylece kabul ettiğiniz metni kendi dilinizde okursunuz. Sonrasında dil **Ayarlar**
ekranından değiştirilir ve uygulama yeniden açıldığında geçerli olur; seçim kaydedilince
uygulama kendini yeniden başlatmayı teklif eder. Menü, tablo başlıkları ve durum etiketleri modül yüklenirken kurulduğu için dil
çalışırken değiştirilmiyor: yarısı bir dilde yarısı ötekinde bir ekran, yeniden
başlatmaktan kötüdür.

Çevrilen şey yalnızca ekranda görünen metinlerdir. Veritabanına yazılan durum anahtarları
(`quarantined`, `result_entered`), birim kodları (`hour`, `adet`) ve stok hareket
gerekçeleri (`consume`, `scrap`) her iki dilde aynıdır; bu yüzden dil değiştirmek
kayıtları bozmaz ve Türkçe girilmiş bir kayıt İngilizce arayüzde doğru okunur. Demo veri
ise kurulduğu dilde yazılır.

`MIHENK_LANG=en` ortam değişkeni ayarı geçersiz kılar; testler ve taşınabilir kullanım
içindir.

Uygulamanın zorunlu dış bağımlılığı yoktur; Excel yazıcısı dahil her şey standart kütüphaneyle
yazıldı. Tek isteğe bağlı bileşen **ttkbootstrap**: modern düğme, liste ve onay kutusu çizimi
sağlar, derleme sırasında pakete gömülür. Yoksa uygulama klasik çizimle sorunsuz çalışır ve
renkler iki yolda da aynıdır. Ayarlar ekranı hangi yolun kullanıldığını yazar ve gerekirse
bileşeni uygulamanın kendi klasörüne kurar — Python kurulumunuza dokunmaz.

Bu bileşen çizim yapamazsa uygulama açılmaya devam eder ve klasik çizime düşer; görünüm
yüzünden kayıtlara erişim kesilmez. Derleme sırasındaki öz-denetim bileşeni yalnızca içe
aktarmakla yetinmez, temayı gerçekten uygular — bozuk bir paket kullanıcının eline geçmeden
derlemede yakalanır.

## Veri nerede

    %APPDATA%\AGFO\Mihenk\mihenk.sqlite3     kayıtlar
    %APPDATA%\AGFO\Mihenk\settings.json      ayarlar
    %APPDATA%\AGFO\Mihenk\certificates\      kalibrasyon sertifikası dosyaları
    %APPDATA%\AGFO\Mihenk\exports\           dışa aktarılan raporlar
    %APPDATA%\AGFO\Mihenk\backups\           yedekler
    %APPDATA%\AGFO\Mihenk\ui-lib\            modern görünüm bileşeni (varsa)
    %APPDATA%\AGFO\Mihenk\last-scan.txt      son tarama özeti

Ayarlar ekranından yedek alabilir ve geri yükleyebilirsiniz. Geri yükleme, mevcut
veritabanının bir kopyasını `.pre-restore` uzantısıyla yanında bırakır.

Taşınabilir kullanım için `MIHENK_DATA_DIR` ortam değişkeni bu klasörü değiştirir.

## Ekranlar

| Ekran | Ne yapar |
|---|---|
| Pano | Açık iş, açık etki, geciken plan sayıları; sayaç baskısı; gecikenler ve yaklaşanlar; elle tarama |
| Varlıklar | Hiyerarşik kütük, tipe göre değişen öznitelikler, durum değişimi, sayaç okuması, geçmiş |
| Planlar | Önleyici bakım, kalibrasyon ve doğrulama planları; takvim ya da sayaç esaslı; kontrol listesi şablonu |
| Talepler | Sahadan gelen bildirimler; değerlendir, reddet, iş emrine dönüştür |
| İş emirleri | Yaşam döngüsü, kontrol listesi işaretleme, kullanılan parçalar, plana geri besleme |
| Kalibrasyon | Ölçüm noktası tablosu, canlı sapma hesabı, sertifika dosyası ve izlenebilirlik |
| Etki değerlendirmeleri | Etkilenen aralık, kapsam, değerlendirme, karar, düzeltici faaliyet |
| Yedek parçalar | Parça kütüğü, stok hareketleri, düşük stok uyarısı, iş emri maliyeti |
| Raporlar | Plan uyumu, MTBF/MTTR, duruş ve işçilik eğilimi, sapma geçmişi, dışa aktarım |
| Ayarlar | Operatör, ön uyarı günü, tarih biçimi, tema, modern görünüm, yedek, demo veri, sürüm |

## Kontrol listeleri

Plana bir adım listesi tanımlarsınız; o plandan üretilen her iş emri listenin **o anki
hâlini** kendi içine kopyalar. Şablon sonradan değişirse geçmiş iş emirleri değişmez — denetçi
"bu iş o gün nasıl yapıldı" diye sorduğunda gösterilen şey, o gün geçerli olan listedir.

Bir adım **ölçüm isteyebilir** (değer girilmeden uygun işaretlenemez) ve **kritik**
olabilir. Kritik adımlar işaretlenmeden iş emri tamamlanamaz; bu kural ekranda değil
`mihenk_repo.py` içindeki geçiş kodunda uygulanır. Tamamlanınca liste, yapılan iş alanına
özet olarak da yazılır.

## Yedek parça stoğu

Stok doğrudan yazılamaz: her değişim bir hareket satırı bırakır ve bakiye o satırın içinde
saklanır. "Stok neden bu seviyede" sorusunun cevabı her zaman kayıttadır. Stok eksiye
düşemez — elde olmayan bir parçanın kullanıldığını söyleyen kütük kimseye bir şey anlatmaz.

İş emri penceresinden parça kullanımı işlenir; stok düşer ve iş emrinin parça maliyeti
hesaplanır. Asgari seviyenin altına düşen parçalar panoda ve Yedek parçalar ekranında
kırmızı görünür.

## Raporlar

Bütün göstergeler seçilen dönemdeki kayıtlardan hesaplanır; tahmin ya da örnekleme yok.

- **Plan uyumu** — plandan üretilmiş iş emirlerinin, planın tolere ettiği gecikme içinde
  kapanma oranı
- **MTBF / MTTR** — varlık başına arızalar arası ortalama süre ve ortalama onarım süresi.
  İki arızası olmayan varlıkta MTBF boş kalır; sıfır yazmak yanıltıcı olurdu
- **Duruş ve işçilik eğilimi** — aya göre dakika toplamları
- **Sapma geçmişi** — bir ölçüm cihazının kalibrasyonlar boyunca en büyük sapması
- **Gecikme yaşlandırması** — hangi plan kaç gündür gecikmiş

## Denetime hazır çıktı

Raporlar ekranındaki **Dışa aktar** düğmesi üç biçim verir:

- **Excel kitabı** (.xlsx) — her tablo ayrı sayfada, başlık satırı donmuş, otomatik filtreli
- **CSV klasörü** — her tablo ayrı dosyada, noktalı virgül ayraçlı, Excel'in doğrudan açtığı
  kodlamada
- **Yazdırılabilir rapor** (.html) — özet kartları ve tablolar; tarayıcıda Ctrl+P ile PDF
  olarak kaydedilir

PDF'i uygulama kendi üretmiyor. Kendi PDF yazıcımızı yazmak Türkçe karakter ve sayfa kırılımı
tarafında sessiz hatalar üretirdi; tarayıcının yazdırma motoru bu işi doğru yapıyor.

Sertifika dosyaları yalnızca yol olarak tutulmuyor: seçtiğiniz dosya veri klasörüne
kopyalanıyor. Özgün dosya taşınsa ya da silinse bile kayıt boşa düşmüyor. Dışa aktarımda
sertifikaları da çıktı klasörüne kopyalatabilirsiniz.

## Planlar nasıl kayda dönüşür

Uygulama açılırken (ayarlardan kapatılabilir) ve Pano'daki **Taramayı çalıştır** düğmesiyle
vadesi gelen planlar taranır. Önleyici plan iş emri, kalibrasyon ve doğrulama planı
kalibrasyon kaydı üretir. Aynı plan için açık bir kayıt varken ikincisi üretilmez, bu
yüzden tarama istediğiniz kadar çalıştırılabilir.

Sayaç tabanlı planlar, varlığa yeni bir sayaç okuması girildiğinde değerlendirilir. Sayaç
okuması bir öncekinden düşük olamaz.

## Demo veri

Ayarlar ekranından birbirine bağlı bir örnek set kurulur: sekiz varlık, yedi plan, dört
talep, üç durumda iş emri ve biri uygunsuz üç kalibrasyon kaydı. Kurulum gerçek depolardan
geçer, yani veri kadar durum makinesini de çalıştırır.

Temizlik yalnızca kodu `DEMO-` ile başlayan varlıkları ve onlara bağlı kayıtları siler.
Sitede bu öneki gerçek ekipman için kullanmayın.

## Denetim günlüğü

Her değişiklik önce **niyet**, sonra **sonuç** satırı bırakır. Uygulama ortada kapansa bile
ne yapılmak istendiği kayıtta kalır. Reddedilen bir geçiş sonuç satırı bırakmaz. Geçmiş
her kaydın kendi penceresinde, son hareketler Ayarlar ekranında görünür.

## Sürüm ve güncelleme

Kurulu uygulama GitHub Releases üzerinden güncellenir. Açılıştan birkaç saniye sonra ve
sonrasında saatte bir arka planda sessizce denetlenir; ağa gerçekte altı saatte bir çıkılır,
bu sınırı uygulama kendi tutar. Yeni sürüm varsa durum çubuğunda bir **Güncelle** düğmesi
belirir; tek tıkla iner ve kurulur. Beklemeden denetlemek için Ayarlar >
**Güncellemeleri denetle**.

2.0.0 ve öncesinde denetim yalnızca açılışta yapılıyordu: gün boyu açık kalan bir uygulama
aradan çıkan sürümü fark etmiyordu. 2.1.0 bunu düzeltir.

İndirilen dosya SHA-256 ile doğrulanır; özet yoksa dosya kullanılmaz. Güven kökü GitHub
hesabıdır, kod imzası değildir. Kayıtlarınız (`%APPDATA%\AGFO\Mihenk`) güncellemeden
etkilenmez.

## Testler

    python -I tests/test_core.py .              59 çekirdek testi
    python -I tests/test_update.py .            güncelleme modülü
    python -I tests/test_xlsx.py .              5 test, üretilen .xlsx'i openpyxl ile okur
    python -I tests/test_i18n.py .              19 dil testi, çeviri açığını ölçer
    xvfb-run -a python -I tests/test_gui.py .   35 arayüz duman testi

Arayüz testleri hem klasik hem modern çizimle koşar; CI ikisini de çalıştırır.

Simgeyi yeniden üretmek için: `python packaging/make_icon.py`
Sorumluluk reddi metnini yeniden üretmek için: `python packaging/make_disclaimer.py`
