# AGFO Mihenk

Ekipman bakımı, kalibrasyon ve doğrulama takibi. Windows masaüstü uygulaması; veriler
bilgisayarda bir SQLite dosyasında durur, sunucu ya da internet bağlantısı gerekmez.

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

## Kurulum

1. Sürüm sayfasından `AGFO-Mihenk-vX.Y.Z-Kurulum.zip` dosyasını indirin ve açın.
2. **Derle-ve-Kur.cmd** dosyasını çalıştırın. EXE sizin bilgisayarınızda derlenir, bu yüzden
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

Gereken: Windows 10/11 ve tkinter'lı Python 3.10+ (derleme için). Uygulamanın kendisi
yalnızca standart kütüphaneyi kullanır; dış bağımlılığı yoktur.

## Veri nerede

    %APPDATA%\AGFO\Mihenk\mihenk.sqlite3     kayıtlar
    %APPDATA%\AGFO\Mihenk\settings.json      ayarlar
    %APPDATA%\AGFO\Mihenk\backups\           yedekler
    %APPDATA%\AGFO\Mihenk\last-scan.txt      son tarama özeti

Ayarlar ekranından yedek alabilir ve geri yükleyebilirsiniz. Geri yükleme, mevcut
veritabanının bir kopyasını `.pre-restore` uzantısıyla yanında bırakır.

Taşınabilir kullanım için `MIHENK_DATA_DIR` ortam değişkeni bu klasörü değiştirir.

## Ekranlar

| Ekran | Ne yapar |
|---|---|
| Pano | Açık iş, açık etki, geciken plan sayıları; sayaç baskısı; gecikenler ve yaklaşanlar; elle tarama |
| Varlıklar | Hiyerarşik kütük, tipe göre değişen öznitelikler, durum değişimi, sayaç okuması, geçmiş |
| Planlar | Önleyici bakım, kalibrasyon ve doğrulama planları; takvim ya da sayaç esaslı |
| Talepler | Sahadan gelen bildirimler; değerlendir, reddet, iş emrine dönüştür |
| İş emirleri | Yaşam döngüsü, her durumun gerektirdiği alanlar, plana geri besleme |
| Kalibrasyon | Ölçüm noktası tablosu, canlı sapma hesabı, sertifika ve izlenebilirlik |
| Etki değerlendirmeleri | Etkilenen aralık, kapsam, değerlendirme, karar, düzeltici faaliyet |
| Ayarlar | Operatör, ön uyarı günü, tarih biçimi, tema, yedek, demo veri, sürüm |

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

Kurulu uygulama GitHub Releases üzerinden güncellenir. Açılıştan birkaç saniye sonra arka
planda sessizce denetlenir (altı saatte bir defadan sık değil, uygulama bunu kendi tutar).
Yeni sürüm varsa durum çubuğunda bir **Güncelle** düğmesi belirir; tek tıkla iner ve kurulur.
Beklemeden denetlemek için Ayarlar > **Güncellemeleri denetle**.

İndirilen dosya SHA-256 ile doğrulanır; özet yoksa dosya kullanılmaz. Güven kökü GitHub
hesabıdır, kod imzası değildir. Kayıtlarınız (`%APPDATA%\AGFO\Mihenk`) güncellemeden
etkilenmez.

## Testler

    python -I tests/test_core.py .          38 çekirdek testi (veritabanı, durum makinesi, tarama)
    python -I tests/test_update.py .        güncelleme modülü
    xvfb-run -a python -I tests/test_gui.py .   21 arayüz duman testi

Simgeyi yeniden üretmek için: `python packaging/make_icon.py`
