# AGFO AI Editor

Yazdığınız metinlerin **içeriğini** yapay zekâyla düzenleyen Windows metin editörü. Biçimlendirme aracı değildir;
odak noktası anlatım, mantık akışı, netlik, doğruluk ve tondur.

## Kurulum
GitHub Releases'ten `AGFO-AI-Editor.exe` dosyasını indirip çalıştırın. İlk açılışta "bu bilgisayara kurulsun mu?"
diye sorar: kullanıcı klasörünüze (`%LOCALAPPDATA%\Programs\AGFO-AI-Editor`) kopyalanır, Başlat menüsüne ve
masaüstüne kısayol eklenir. Yönetici yetkisi gerekmez. Güncellemeler uygulama içinden tek tıkla gelir
(etiket `ai-editor-v*`, SHA-256 doğrulamalı). EXE kod imzalı değildir; SmartScreen uyarabilir.

## Bağlantı (Ayarlar › Bağlantı)
- **AGFO AI Manager (önerilen):** WordPress sitenizdeki AI Manager 17.5.0+ kullanılır; API anahtarları sitede kalır.
  WordPress › AI Manager › *AI Editor bağlantısı* sayfasında "Anahtar oluştur"a basın; site adresini ve çıkan
  anahtarın tamamını editöre yapıştırın. (İsteğe bağlı: WordPress Uygulama Parolası ile kullanıcı adı + parola.) AI Manager'daki sağlayıcı/model,
  çeviri yönlendirmesi ve sitenize özel içerik şablonları editörde otomatik görünür.
- **Doğrudan sağlayıcı:** OpenAI, Anthropic, Gemini, OpenRouter veya DeepSeek anahtarı. Anahtar Windows DPAPI ile
  yalnız sizin Windows hesabınızda çözülebilecek şekilde saklanır.
- **Otomatik:** önce AI Manager, ulaşılamazsa doğrudan anahtar.

## Özellikler
- **Word gibi editör (2.0):** sekmeli şerit menü — *Giriş* (pano, biçim boyacısı, yazı tipi ve boyutu, kalın / italik /
  altı çizili / üstü çizili, üst ve alt simge, vurgu ve yazı rengi, biçimi temizle, madde / numaralı / çok düzeyli
  listeler, girinti, hizalama ve iki yana yaslama, satır aralığı, paragraf öncesi/sonrası boşluk, stil galerisi: Normal,
  Başlık 1-3, Alıntı), *Ekle* (tablo, resim, bağlantı, sayfa sonu, üst bilgi, alt bilgi, sayfa numarası, simge), *Düzen*
  (kenar boşlukları, dikey/yatay, A4 / A5 / Letter / Legal, girintiler ve aralıklar), *Görünüm* (sayfa görünümü,
  yakınlaştırma, yazım denetimi, AI paneli, koyu / açık tema), *Yapay zekâ* (içerik eylemleri, çeviri, sesli okuma,
  panel sekmeleri). Bunların hepsi `.docx` dosyasına yazılır ve geri okunur; Word'de aynı görünür. Sayfa bölünmesi
  editörde yaklaşıktır, Word / PDF çıktısı gerçek sayfa düzenini kullanır. Geri al / yinele bütün biçimleri, resimleri
  ve tabloları geri getirir. `.md` ve `.html` de biçimli açılır; `.txt` dosyaları düz metin kalır.
- **Türkçe yazım denetimi (2.0):** Windows'un kendi yazım denetleyicisi kullanılır (ek indirme yok). Hatalı kelimeler
  kırmızıyla işaretlenir; sağ tıkla öneriler, *Sözlüğe ekle*, *Tümünü yoksay*. Windows'ta Türkçe dil paketinin yazım
  denetimi bileşeni yüklü olmalıdır.
- Kodlama ve satır sonu korunur; Türkçe ANSI dosyalar tanınır. Bul/değiştir (biçimi korur), otomatik kurtarma, son dosyalar.
- **İçerik:** İçeriği güçlendir, Akışı ve yapıyı düzelt, Argümanı netleştir, Düzelt ve cilala, Kısalt, Geliştir,
  Sadeleştir, Özetle, ton dönüşümleri, SEO/LinkedIn, Devamını yaz, Eleştirel okuma, Başlık önerileri, Özel talimat
  ve AI Manager'daki sitenize özel şablonlar. Seçim yoksa imlecin bulunduğu paragraf işlenir.
- Sonuç **fark görünümünde** (silinen/eklenen kelimeler) gösterilir; düzenleyip onaylarsınız. Ctrl+Z ile geri alınır.
- **Belge çevirisi (1.4):** tüm belge (ya da açık PDF) biçim korunarak çevrilir; başlık, liste, tablo ve resimler yerinde
  kalır. Sonuç biçimli yeni sekmede ve/veya **yan yana** (özgün | çeviri, eşzamanlı kaydırma) açılır; yan yana görünüm
  iki sütunlu Word tablosu olarak kaydedilebilir.
- **Çeviri** (seçim: yerine koy / altına ekle / yeni sekme), **Sohbet** (belge bağlamlı), **Denetim** (BRCGS/IFS/FSSC/ISO:
  uygunsuzluk bulgusu, uygunluk ifadesi, DÖF ve kök neden değerlendirmesi, yönetici özeti). Kayıt no, tarih, ölçüm
  veya madde metni uydurulmaz.

- **Ses (1.5):** seçili metni ya da tüm belgeyi sitenizdeki AI Manager (17.12.0+) üzerinden sunucudaki EMA Lightning ile
  Türkçe seslendirip MP3 olarak kaydeder; karakter ücreti yoktur. "Okuma metnini AI ile hazırla" seçiliyse yabancı adlar,
  sayılar, tarihler, birimler ve kısaltmalar önce okunduğu gibi yazılır. "Okuma metnini önizle" hazırlanan metni yeni
  sekmede açar; düzeltip o sekmeden seslendirirseniz metin olduğu gibi okunur. Uzun belgeler parçalara bölünüp tek MP3'te
  birleştirilir. **Telaffuz sözlüğü:** yanlış okunan bir adı seçip sağ tıklayın ("Telaffuz sözlüğüne ekle") ya da Ses ›
  Sözlüğü aç; okunuşu dinleyip kaydedin. Kayıt sunucudaki ortak listeye yazılır, bütün sitelerde hemen geçerli olur
  (değiştirmek için site yöneticisi gerekir).
- **Ses servisi: bu bilgisayar (1.7):** AGFO-Ses-Kur.cmd ile EMA Lightning bu bilgisayara kurulur (NVIDIA ekran kartı
  varsa onu kullanır; yönetici izni gerekmez, oturum açılınca kendiliğinden başlar, yalnız bu bilgisayardan erişilir).
  Ses sekmesinde "Ses servisi: Bu bilgisayar" seçilince Sesli oku, Ses dosyası ve Telaffuz sözlüğü siteye gitmeden
  burada çalışır. AI okuma metni istenirse yine sitedeki AI Manager hazırlar. "Sözlüğü siteden eşitle" sunucudaki ortak
  sözlükte eklenen, değiştirilen ve kaldırılan kelimeleri bu bilgisayara uygular; buradan eklenen kelime site
  yöneticisiyseniz ortak sözlüğe de yazılır.
- **Sesli oku (1.6):** Ses sekmesinde "▶ Sesli oku" (F9) imlecin bulunduğu paragraftan (ya da seçimden) başlayarak
  belgeyi okur; okunan paragraf editörde yeşil vurgulanır. Sıradaki paragrafların sesi arka planda hazırlanır, böylece
  okuma beklemeden sürer. F9 duraklatır/sürdürür, "■ Durdur" bitirir. Aynı paragraf ikinci kez okunurken ses
  önbellekten gelir. AI Manager 17.13.0+ gerekir.
- **Ses dosyası oluştur (1.6):** belge önce başlık yapısına göre bölümlere ayrılır (en az iki kez kullanılan en üst
  başlık düzeyi), çok kısa bölümler komşusuyla birleşir, çok uzun bölümler önce alt başlıklardan, sonra dengeli
  paragraf gruplarından "Başlık (1/3)" gibi parçalara bölünür. Açılan pencerede bölümleri, karakter sayılarını ve
  tahmini süreleri görür, istediklerinizi seçersiniz. "Her bölüm ayrı MP3" klasöre "01 - Başlık.mp3" dosyaları ve bir
  çalma listesi yazar; "Tek MP3" seçilenleri birleştirir. Bir bölüm hata verirse diğerleri devam eder.
- **Kaynaklar (1.2):** PDF, Word, Excel, PowerPoint, metin ve e-posta dosyalarını ekleyip onlara soru sorun (tıklanabilir
  sayfa atıflarıyla) ya da onlardan makale, eğitim notu, SSS, quiz, denetim kontrol listesi, karşılaştırma, sunum taslağı
  üretin. Büyük belgelerde yerel arama yalnız ilgili bölümleri gönderir; kişisel bilgiler gönderimden önce maskelenebilir.

- **PDF düzenleyici (1.3):** PDF'ler sayfa görünümüyle açılır; vurgu, not, metin kutusu, "üstüne yaz" (beyaz kutu + metin),
  resim / imza, çerçeve; sayfa döndür / sil / taşı / birleştir / ayır; form doldurma. Kaydet her zaman yeni dosya önerir.
  **1.4:** "Metni düzenle" ile bir satıra tıklayıp mevcut metni yerinde değiştirin (eski metin sayfadan çıkarılır, yenisi
  benzer yazı tipiyle gerçek, aranabilir metin olarak yazılır); "Resmi sil" ile PDF'deki resimleri içerikten kaldırın.
  Şifreli PDF'lerde belge sahibinin izinlerine uyulur.

Kısayollar: Ctrl+N/O/S, Ctrl+Shift+S, Ctrl+W, Ctrl+F, Ctrl+H, F3, Ctrl+E (AI ile düzenle), Ctrl+Enter (sohbette gönder,
belgede sayfa sonu), Ctrl+B / Ctrl+I / Ctrl+U (kalın / italik / altı çizili), Ctrl+= (alt simge), Ctrl+L / Ctrl+R / Ctrl+J
(sola / sağa / iki yana), Ctrl+K (bağlantı; Ctrl+tık açar), Ctrl+Boşluk (karakter biçimini temizle), F9 (sesli oku),
Ctrl+Z / Ctrl+Y.

Veriler: `%LOCALAPPDATA%\AGFO-AI-Editor` (ayarlar, kurtarma kayıtları, hata günlüğü). Metinleriniz yalnızca seçtiğiniz
AI bağlantısına gönderilir.
