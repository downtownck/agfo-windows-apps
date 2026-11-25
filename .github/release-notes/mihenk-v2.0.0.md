# AGFO Mihenk 2.0.0

Modern görünüm ve dört yeni yetenek. Mevcut kayıtlarınız olduğu gibi kalır: 1.x veritabanı
açıldığında yeni tablolar eklenir, hiçbir satır taşınmaz ya da yeniden yazılmaz.

## Modern görünüm

Arayüz artık **ttkbootstrap** ile çiziliyor — System Care'de kullanılan bileşenin aynısı.
Düğme, liste, onay kutusu ve açılır listeler Windows'un kendi görünümüne yakın duruyor.
Bileşen EXE'ye gömülü geliyor; bir sebeple yoksa uygulama klasik çizimle sorunsuz çalışıyor
ve renkler iki yolda da aynı. Ayarlar ekranı hangi yolun kullanıldığını yazıyor.

## Kontrol listesi şablonları

Plana bir adım listesi tanımlıyorsunuz; o plandan üretilen her iş emri listenin **o anki
hâlini** kendi içine kopyalıyor. Şablon sonradan değişirse geçmiş iş emirleri değişmiyor —
denetçiye gösterilen şey, işin yapıldığı gün geçerli olan liste.

Bir adım ölçüm isteyebiliyor (değer girilmeden uygun işaretlenemiyor) ve kritik olabiliyor.
**Kritik adımlar işaretlenmeden iş emri tamamlanamıyor.** Tamamlanınca liste, yapılan iş
alanına özet olarak da yazılıyor.

## Yedek parça stoğu

Parça kütüğü, stok hareketleri ve düşük stok uyarısı. Stok doğrudan yazılamıyor: her değişim
bir hareket satırı bırakıyor ve bakiye o satırın içinde saklanıyor. Stok eksiye düşemiyor.
İş emri penceresinden parça kullanımı işleniyor; stok düşüyor ve iş emrinin parça maliyeti
hesaplanıyor.

## Raporlar ve göstergeler

Yeni bir Raporlar ekranı: plan uyum oranı, varlık başına MTBF ve MTTR, aya göre duruş ve
işçilik eğilimi, ölçüm cihazlarının sapma geçmişi, gecikme yaşlandırması. Hepsi seçilen
dönemdeki kayıtlardan hesaplanıyor. İki arızası olmayan varlıkta MTBF boş kalıyor; sıfır
yazmak yanıltıcı olurdu.

## Denetime hazır çıktı

- **Excel kitabı** — on iki tablo, her biri ayrı sayfada, başlık satırı donmuş, filtreli.
  Excel yazıcısı standart kütüphaneyle yazıldı, dış bağımlılık eklemiyor; üretilen dosya
  CI'da openpyxl ile açılıp doğrulanıyor.
- **CSV klasörü** — her tablo ayrı dosyada.
- **Yazdırılabilir rapor** — özet kartları ve tablolar, tarayıcıdan PDF olarak kaydedilir.
  PDF'i uygulama kendi üretmiyor; kendi PDF yazıcımız Türkçe karakter ve sayfa kırılımında
  sessiz hatalar üretirdi.

**Sertifika dosyaları** artık yalnızca yol olarak tutulmuyor: seçtiğiniz dosya veri klasörüne
kopyalanıyor. Özgün dosya taşınsa ya da silinse bile kayıt boşa düşmüyor.

## Testler

59 çekirdek, 28 arayüz (hem klasik hem modern çizimle), 5 Excel doğrulama testi, güncelleme
modülü ve EXE öz-denetimi — hepsi koşuldu ve geçti.
