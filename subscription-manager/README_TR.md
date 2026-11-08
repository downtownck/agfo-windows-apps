# AGFO Subscription Manager

Tüm ücretli aboneliklerini tek pencerede gösteren Windows uygulaması. Listeyi TL'ye çevirip toplar, yaklaşan yenilemeleri ve başarısız ödemeleri öne çıkarır, yeni abonelikleri e-posta ve banka ekstresinden bulur. İptal işlemini her abonelik için adım adım yürütür.

## Kurulum

1. Sürümler sayfasından `AGFO-Subscription-Manager-vX.Y.Z-Kurulum.zip` dosyasını indirip bir klasöre aç.
2. `Derle-ve-Kur.cmd` dosyasına çift tıkla. EXE senin bilgisayarında derlenir, bu yüzden SmartScreen uyarısı çıkmaz. Ardından `%LOCALAPPDATA%\Programs\AGFO-Subscription-Manager` klasörüne kurulur, Başlat menüsüne (AGFO) ve masaüstüne kısayol eklenir.
3. Gereken tek şey Python 3.10 veya üstü (tkinter ile birlikte). Derleme araçları kullanıcının Python kurulumunu kirletmeyen ayrı bir ortama kurulur.

Kaldırmak için `Kaldir.cmd` kullan; abonelik listen silinmez. `Baslat.cmd` kaynaktan çalıştırır, `Sadece-Derle.cmd` yalnızca EXE üretir.

Liste kişisel veridir ve depoya konmaz; ilk açılışta liste boştur. Hazır listeni **Liste içe aktar** ile yükle, **Yedekle** ile JSON olarak dışa al. Verilerin `%APPDATA%\AGFO\SubscriptionManager\subscriptions.json` dosyasında durur. Güncellemeler bu dosyaya dokunmaz. Her kayıttan önce `.bak` yedeği alınır.

## Neler yapar

- **Liste ve toplamlar:** Aylık ve yıllık toplamı TL olarak gösterir. Kurlar her gün TCMB'den çekilir, elle de girebilirsin. Ayrıca aktif abonelik sayısını, 30 gün içinde yenilenecekleri, ödeme sorunlarını ve kontrol bekleyenleri gösterir. Kapsam (Kişisel / AGFO), kanal, durum ve metin filtreleri vardır.
- **İptal:**
  - *Yönetim / iptal sayfasını aç:* Satıcının ya da Google Play / Apple / Paddle'ın abonelik sayfasını açar.
  - *İptal e-postası hazırla:* Gmail hesapları için Gmail'de, diğerleri için varsayılan posta programında hazır taslak açar. Alıcı adresi ".tr" ile bitiyorsa taslak Türkçe, değilse İngilizce olur.
  - *İptal sihirbazı:* Seçilenleri (ya da *Tümünü iptal…* ile ekrandaki listenin tamamını) tek tek gezer. Sen iptali yaptıktan sonra sonucu kaydeder: iptal edildi, dönem sonunda bitecek ya da onay bekliyor. Her durum değişikliği kaydın geçmişine yazılır.
- **E-posta tara:** IMAP üzerinden salt okunur tarama yapar; hiçbir iletiyi okundu olarak işaretlemez, taşımaz ya da silmez. Stripe, Google Play, Apple, Paddle, PayPal makbuzlarını, yenileme hatırlatmalarını, başarısız ödeme ve deneme bitiş e-postalarını tanır. Bulguları sen onaylarsın; listede zaten olanlar eklenmez, güncellenir.
  - Gmail için *uygulama şifresi* gerekir: myaccount.google.com/apppasswords
  - Diğer adresler için posta sunucusunun IMAP adresini gir (çoğunlukla `mail.alanadi:993`).
  - İstersen şifreler Windows Kimlik Yöneticisi'nde saklanır.
- **Ekstre içe aktar:** Banka veya kart ekstresini (CSV ya da XLSX) okur. En az iki farklı ayda tekrarlanan, tutarı benzer çekimleri abonelik adayı olarak listeler. E-posta göndermeyen abonelikler bu yolla yakalanır.
- **CSV:** Görünen listeyi Excel'de açılabilen bir CSV dosyasına aktarır.
- **Güncelleme:** Açılışta (6 saatte bir) GitHub'daki `subscription-manager-v*` sürümlerini denetler. Yeni sürümün Kurulum ZIP'ini indirir, SHA-256 ile doğrular, `Derle-ve-Kur.cmd /update` ile yeniden derleyip kurar. Ortak denetleyici: `agfo_github_update.py`.

## Önemli

Uygulama aboneliği satıcı adına kendiliğinden iptal etmez; bunu yapabilen genel bir API yok. İptal her zaman satıcının ya da mağazanın sayfasında veya e-postayla senin onayınla olur. Uygulama seni doğru sayfaya götürür, e-postayı hazırlar ve sonucu kayıt altına alır.

Listede "Sil" yalnızca kaydı kaldırır, aboneliği iptal etmez.
