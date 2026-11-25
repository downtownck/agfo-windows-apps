# AGFO Mihenk 1.0.0

Ekipman bakımı, kalibrasyon ve doğrulama takibi. Veriler bilgisayarda bir SQLite dosyasında
durur; sunucu, hesap ya da internet bağlantısı gerekmez.

## Bu sürümde

- Hiyerarşik varlık kütüğü; tipe göre değişen öznitelik setleri; sayaç okuması
- Önleyici bakım, kalibrasyon ve doğrulamayı tek tabloda toplayan plan yapısı (takvim ya da sayaç esaslı)
- Talep akışı: bildir, değerlendir, reddet, iş emrine dönüştür
- İş emri yaşam döngüsü; her durumun gerektirdiği alanlar; tamamlanınca planın ileri sarması
- Ölçüm noktası tablosu, canlı sapma hesabı ve tolerans değerlendirmesi
- **Uygunsuz kalibrasyonda otomatik karantina ve etki değerlendirmesi.** Etkilenen aralık,
  uygunluğu gerçekten kanıtlayan son kayıttan doldurulur. Değerlendirme kapanmadan varlık
  hizmete dönemez, kalibrasyon kaydı kapanamaz
- Şartlı sonuç, yazılı kullanım sınırlaması olmadan kapatılamaz
- Niyet ve sonuç çiftiyle denetim günlüğü
- SQLite yedekleme ve geri yükleme; birbirine bağlı demo veri seti
- Açık ve koyu tema; yüksek DPI desteği

## Kurulum

`AGFO-Mihenk-v1.0.0-Kurulum.zip` dosyasını açın ve **Derle-ve-Kur.cmd** çalıştırın. EXE
sizin bilgisayarınızda derlenir, bu yüzden SmartScreen uyarısı çıkmaz.

Veri klasörü: `%APPDATA%\AGFO\Mihenk`
