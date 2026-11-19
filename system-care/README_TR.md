# AGFO System Care 4.1 — Açık kaynak motorlar tek arayüzde

## Kurulum
**Önerilen (Python gerekmez):** `AGFO-System-Care-v4.x.x-Windows.zip` dosyasını indirip açın, klasördeki `Kur-ve-Baslat.cmd`'yi çalıştırın. Python, tkinter ve gerekli kütüphaneler pakette hazır gelir. Uygulama `%LOCALAPPDATA%\Programs\AGFO System Care` klasörüne kurulur ve Başlat menüsüne kısayol eklenir.

**Python ile:** `AGFO-System-Care-v4.x.x.zip` paketini açıp `agfo-care/Kur-ve-Baslat.cmd` ile de kurabilirsiniz. Bunun için Python 3.10+ ve tkinter gerekir. Bu paket aynı zamanda uygulama içi güncelleme paketidir.

İlk açılışta **Motorlar** sekmesindeki "Eksik motorları kur" düğmesine basın.

## 4.1'de ne değişti — Üretici desteği ve NVIDIA
- **Üretici desteği (Donanım > Üretici desteği):** Üretici, model ve seri numarası Windows'tan okunur. Dell ve ASUS'ta doğrudan ürününüzün sürücü sayfası açılır. HP, Lenovo, Acer, Sony/VAIO, MSI, Microsoft Surface, Samsung, Dynabook, Fujitsu, Huawei, Casper, Monster ve diğerlerinde resmî sürücü sayfası açılır; seri numarası ya da model panoya kopyalanır. "Üretici sitesinde ara" yalnızca üreticinin kendi sitesinde arar. Kendi topladığınız masaüstünde anakart üreticisi (ASUS, MSI, GIGABYTE, ASRock) kullanılır. Üreticinin kendi güncelleme aracı tek tıkla kurulur: Dell Command Update, HP Support Assistant / Image Assistant, Lenovo Vantage / System Update, MyASUS, MSI Center ve Intel Driver & Support Assistant.
- **NVIDIA (Donanım > NVIDIA):**
  - Kurulu sürüm ile NVIDIA'nın kendi sürücü servisindeki en yeni sürüm karşılaştırılır.
  - "İndir ve kur": sürücü NVIDIA sunucusundan indirilir, dijital imzası doğrulanır (yalnızca NVIDIA Corporation imzalı dosya çalıştırılır) ve sessiz kurulur. İsteğe bağlı: temiz kurulum, yalnızca sürücü (NVIDIA App olmadan, 7-Zip ile).
  - Kaldırma: NVIDIA'nın kendi sessiz kaldırıcısı, Windows sürücü deposundan paket silme (pnputil) ya da açık kaynak Display Driver Uninstaller (DDU) ile derin temizlik (geri yükleme noktası + yeniden başlatma).
- Sol menü uzadığı için artık fare tekerleğiyle kaydırılıyor; seçili sayfa her zaman görünür.

## 4.0'da ne değişti
- **Genel bakış (ilk sayfa):** diskler, aygıtlar, Microsoft Defender, güvenlik duvarı, Windows Update, bekleyen yeniden başlatma, bellek, çalışma süresi, BitLocker ve VPN tek ekranda; 0–100 arası sağlık puanı. Her kartta ilgili sayfayı ya da Windows ayarını açan bir düğme var.
- **Donanım bölümü:**
  - **Sistem özeti** (Everest/AIDA64 tarzı): işlemci, anakart/BIOS, bellek modülleri, ekran kartı, diskler, bölümler, ağ, ses, monitör ve pil. Bilgiler Windows'un kendi verisinden okunur; sürücü kurulmaz.
  - **Aygıt yöneticisi:** sorunlu aygıtlar en üstte. Etkinleştirme, devre dışı bırakma, yeniden başlatma ve kaldırma; kritik sistem aygıtları için ek uyarı.
  - **Disk sağlığı:** Windows'un depolama sayaçları (SMART benzeri): genel durum, sıcaklık, SSD aşınması, çalışma saati, düzeltilemeyen hatalar.
  - **Rapor:** tüm donanım dökümü HTML ya da metin olarak kaydedilir.
  - **Sensörler (isteğe bağlı):** açık kaynak LibreHardwareMonitor kurulup açıkken sıcaklık, fan ve voltaj okunur. Kurmadan önce PawnIO sürücüsü ve hile önleme sistemleriyle ilgili uyarı gösterilir.
  - Sürücüler, Aygıt temizliği ve Kol / Gamepad sayfaları da bu bölüme taşındı.
- **İşlem bazında yönetici onayı:** Uygulama normal kullanıcıyla çalışır. Yönetici isteyen işlem (sürücü kurulumu, DISM/SFC, geri yükleme noktası, aygıt işlemleri, sistem çapında ince ayarlar, DNS) uygulamayı yeniden açtırmaz; o işlem için Windows UAC onayı istenir. VPN tünelleri şimdilik yine "Yönetici olarak yeniden aç" ister.
- **Python'suz kurulum:** Windows paketi Python, tkinter, ttkbootstrap, Pillow ve Paramiko'yu içerir. Uygulama dosyaları exe'nin yanında durduğu için uygulama içi güncelleme aynen çalışır.
- **Altyapı:** kod sayfa modüllerine bölündü; her sürüm GitHub'da gerçek bir Windows makinesinde de test ediliyor (PowerShell eylemleri, yönetici yardımcısı ve uçtan uca arayüz).

## 3.14.0'da ne değişti — SuperTools artık System Care içinde

Sol menüdeki **Ağ** bölümüne SuperTools'un tüm araçları geldi:
- **Ağ tarayıcı:** yerel ağdaki cihazları bulur (ICMP/TCP, ARP, SSDP/mDNS). SMB klasörünü ya da web arayüzünü açar, paylaşımları sorgular, NAS hesabıyla bağlanır, CSV kaydeder. Bulunan cihazdan tek tıkla SSH profili oluşturulur.
- **Ağ testleri:** MX, SPF, DMARC, DKIM, MTA-STS, SMTP, TLS sertifikası, HTTP, TCP portu, ping, traceroute ve RDAP.
- **SSH sunucularım ve SSH oturumları:** kayıtlı sunucular, dahili SSH (parola isteğe bağlı olarak Windows DPAPI ile 1–24 saat), birden çok oturum ve alt alta iki oturum görünümü.
- **VPN ile bağlantı:** "UGREEN ayarını kopyala" ve "Hetzner komutunu kopyala" komutu kayıtlı bir SSH sunucusunda doğrudan çalıştırabiliyor. Bağlantı kurulunca komut oturuma gönderiliyor; ayrı bir uygulama açmak gerekmiyor.

**Kayıtlarınız bu bilgisayarda kalır.** SSH profilleri, şifreli parola kasası, bilinen sunucu anahtarları ve tarama ayarları SuperTools ile aynı yerde, `%LOCALAPPDATA%\AGFO-MultiSubnet-Scanner` klasöründe tutulur. SuperTools'ta kayıtlı sunucularınız System Care'de kendiliğinden görünür. Bu dosyalar uygulama paketine, güncellemelere ya da GitHub'a hiçbir zaman girmez. Depoda bunu denetleyen bir gizlilik testi var: kişisel kayıt dosyası, özel anahtar ya da bilinen kişisel adres bulunursa sürüm çıkmaz.

## 3.13.2'de ne değişti — UGREEN'de mevcut Tailscale

- NAS Tailscale'de zaten görünüyorsa "UGREEN ayarını kopyala" tek satırlık bir SSH komutu veriyor. Komut sadece çıkış noktalığını açıyor; Docker kurulumu gerekmiyor.

## 3.13.1'de ne değişti — Hetzner komutu düzeltmesi

- Tailscale sunucuda zaten kuruluysa "Hetzner komutunu kopyala" komutu artık hata vermiyor. Makinenin adı ve DNS ayarı değişmiyor; komut yalnızca çıkış noktalığını açıyor.
- Onaylı çıkış noktası yoksa VPN sayfası, tailnet'teki çıkış noktası olmayan sunucuları ve yapılacak adımı gösteriyor.

## 3.13.0'da ne değişti — Kendi çıkış noktalarınız: Türk IP (UGREEN) / yabancı IP (Hetzner)
- VPN sayfasında **Kendi çıkışlarım (Tailscale)** görünümü (varsayılan). Tailscale'in açık kaynak istemcisiyle (WireGuard tabanlı, modemde port açmak gerekmez) kendi cihazlarınızı internet çıkışı olarak kullanırsınız:
  - **Yurt dışındayken Türk IP'si:** Türkiye'deki UGREEN NAS çıkış noktası olur (**ugreen-turkiye**). "UGREEN ayarını kopyala" Docker Compose projesini panoya koyar ve adımları gösterir (Docker > Proje > Oluştur > yapıştır > günlükteki bağlantıyla giriş).
  - **Türkiye'deyken yabancı IP:** Hetzner sunucusu çıkış noktası olur (**hetzner-cikis**). "Hetzner komutunu kopyala" sunucuda root olarak çalıştırılacak tek satırlık kurulumu verir.
  - Her yeni çıkış noktası Tailscale yönetim panelinde bir kez "Use as exit node" ile onaylanır ("Yönetim panelini aç").
- Listeden çıkışı seçip **Bağlan**, normal internete dönmek için **Bağlantıyı kes**. **En hızlıya bağlan** gecikmesi en düşük çevrimiçi çıkışı seçer. Bağlantıdan sonra görünen IP kendiliğinden denetlenir. Bu bilgisayarı da "Bu bilgisayarı çıkış noktası yap" ile çıkış yapabilirsiniz. Tailscale kurulu değilse tek tıkla kurulur (kişisel kullanım ücretsiz).

## 3.12.0'da ne değişti — Hesapsız ücretsiz VPN sunucuları (VPN Gate)
- VPN sayfasında **Ücretsiz sunucular (VPN Gate)** seçeneği: Japonya'daki Tsukuba Üniversitesi'nin akademik VPN Gate projesinin gönüllü sunucuları, hesap ve yapılandırma dosyası gerekmeden listelenir (ülke, ölçülmüş hız, oturum sayısı, açık kalma süresi, işletmeci). Liste saatte bir yenilenir; "Sunucu listesini yenile" ile elle de alınır.
- **En hızlıya bağlan**: seçili ülkedeki en hızlı 12 sunucunun size olan gecikmesi ölçülür, hız/gecikme dengesi en iyi olana bağlanılır. Bağlantı resmî açık kaynak **OpenVPN** istemcisiyle kurulur (yoksa tek tıkla kurulur); durum ve görünen IP sayfada görünür.
- Güvenlik: internetten gelen yapılandırmalardan komut / betik / eklenti çalıştırabilen yönergeler (script-security, up, route-up, plugin …) atılır; VPN Gate'in herkese açık ortak kimliği dosyadan verilir.
- Hiç kendi yapılandırmanız yoksa VPN sayfası bu seçenekle açılır. Aynı anda tek VPN çalışır (WireGuard tüneli varsa kapatılır). Gönüllü sunucular olduğundan hız ve süreklilik değişkendir; tam hız için ücretli bir WireGuard sağlayıcısı (Proton Plus, Mullvad) önerilir.

## 3.11.0'da ne değişti — VPN (WireGuard, ülke seçmeli)
- Sol menüde yeni **Ağ > VPN** sayfası. Açık kaynak **WireGuard** (bilinen en hızlı VPN protokolü, resmî Windows istemcisi) ile farklı ülkelerin IP'leri üzerinden bağlanırsınız. WireGuard kurulu değilse sayfadan tek tıkla kurulur.
- **Yapılandırma ekle…**: VPN sağlayıcınızdan (Proton VPN: hesap > İndirmeler > WireGuard yapılandırması; Mullvad: hesap > WireGuard yapılandırması) ya da kendi sunucunuzdan aldığınız `.conf` dosyalarını toplu ekleyin. Ülke dosya adından tanınır (ör. `NL-FREE#12`, `mullvad-de-fra-wg-001`). Yapılandırmalar WireGuard'ın kendi şifreli klasörüne kopyalanır; özel anahtar System Care'in dosyalarında tutulmaz.
- **Ülke** süzgeci, **Gecikmeyi ölç**, **En hızlıya bağlan** (seçili ülkedeki en düşük gecikmeli sunucu), **Bağlan / Bağlantıyı kes** (aynı anda tek tünel; başka ülkeye geçerken eskisi kapatılır), **Görünen IP'yi denetle** (bağlandıktan sonra IP'nin hangi ülkede göründüğünü gösterir). Bağlı tünelin son el sıkışma zamanı ve aktarım miktarı görünür.
- Bağlantı, siz kesene kadar Windows yeniden başlasa da sürer. Yönetici yetkisi gerekir.

## 3.10.2 düzeltmesi
- **Kaldırıp yeniden kur** artık kaldırıcı sessiz kipte hata verirse (ör. Skywork, kod 1603) kaldırıcının kendi penceresiyle bir kez daha dener; yine kaldırılamazsa en yeni sürümü eskisinin üzerine kurar (`winget install --force`) ve bunu Ayrıntı sütununda belirtir. İkisi de olmazsa yönetici olarak açıp yeniden denemeniz önerilir.

## 3.10.1 düzeltmesi
- WinGet "daha yeni sürüm var ama sisteminize/gereksinimlerinize uymuyor" dediğinde (ör. Skywork) uygulama yanlışlıkla "Güncel" görünüyordu. Artık "Yeniden kurulmalı" olarak işaretlenir ve **Kaldırıp yeniden kur** ile güncellenir. Yalnızca "uygulanabilir güncelleme yok" dönenler "Zaten güncel olabilir" diye gösterilir (uygulama kendini tarama ile güncelleme arasında güncellemiş olabilir).

## 3.10.0'da ne değişti — GitHub'ın popüler uygulamaları ve daha sağlam güncelleme
- **Uygulama kur** kataloğu 159'dan **258** uygulamaya çıktı: GitHub'da çok sevilen 99 açık kaynak uygulama eklendi (Flow Launcher, EarTrumpet, QuickLook, Files, LocalSend, ScreenToGif, Espanso, Ditto, WinMerge, Twinkle Tray, Windhawk, System Informer, UniGetUI, VeraCrypt, Cryptomator, Ollama, Jan, GPT4All, Upscayl, Zed, VSCodium, WezTerm, Bruno, Godot, FreeCAD, KiCad, OrcaSlicer, Kodi, Moonlight/Sunshine, RetroArch ve diğerleri). Yeni **Yapay zekâ** kategorisi. Tüm WinGet kimlikleri Microsoft'un resmî winget-pkgs deposunda doğrulandı.
- **Uygulama güncellemeleri** daha dayanıklı: sessiz güncelleme başarısız olursa uygulamanın kendi kurulum penceresiyle bir kez daha denenir. Uygulama açıksa "Uygulama açık" yazar. Yeni sürümü farklı kurulum türüyle gelen uygulamalar "Yeniden kurulmalı" diye işaretlenir; **Kaldırıp yeniden kur** düğmesi onları kaldırıp en yeni sürümü kurar. Yeni **Ayrıntı** sütunu WinGet'in hata nedenini Türkçe gösterir.

## 3.9.0'da ne değişti — Uygulama kur: logolar ve büyük simge görünümü
- **Büyük simgeler** görünümü (varsayılan): her uygulama logosu, adı ve durumuyla bir kutucuk; tıklayınca seçilir (vurgulanır, köşede ✔). **Liste** görünümü de duruyor ve listede de küçük logolar var. Seçim iki görünüm arasında korunur; görünüm tercihi hatırlanır.
- **Logolar** pakette dağıtılmaz: sayfa büyük simge görünümünde ilk açıldığında her uygulamanın kendi sitesinden (tarayıcının sekme simgesini bulması gibi) bir kez indirilir ve `%LOCALAPPDATA%\AGFO\SystemCare\app-icons` altında saklanır; sonraki açılışlarda internet gerekmez. Yalnızca HTTPS kullanılır. Logo bulunamayan uygulamalar (ör. sitesi GitHub sayfası olanlar) renkli harf simgesiyle gösterilir; başarısız olanlar 30 gün yeniden denenmez.
- Modern görünüm kuruluysa (Pillow) ICO/JPG/WEBP logolar da okunur ve keskin biçimde küçültülür; değilse yalnızca PNG logolar kullanılır.

## 3.8.0'da ne değişti — Yeni arayüz, renk temaları, Dosya düzeni
- **Sol menü**: üstteki sekme şeridi yerine gruplu sol menü — Genel, Temizlik (Temizlik, Bloatware, Dosya düzeni), Sistem (İnce ayarlar, Sürücüler, Aygıt temizliği, Bakım ve sağlık), Uygulamalar (Programlar, Uygulama güncellemeleri, Uygulama kur), Donanım (Kol / Gamepad). Uygulama en son açtığınız sayfayla açılır.
- **Renk temaları** (sol alt, "Görünüm"): AGFO Gece, AGFO Açık, Tokyo Gecesi, Nord Koyu, Dracula, Orman, Gruvbox, One Koyu, Pastel Açık, Nord Açık, Solarized Açık, Yüksek karşıtlık. Tema anında uygulanır, yeniden başlatma gerekmez; seçim hatırlanır. Tüm temalarda yazı/zemin karşıtlığı en az 4,5:1.
- **Modern görünüm (ttkbootstrap)**: düğmeler, onay kutuları, listeler ve açılır kutular daha düzgün çizilir. `Kur-ve-Baslat.cmd` bileşeni yalnızca System Care'in kendi klasörüne (`%LOCALAPPDATA%\AGFO\SystemCare\ui-lib`) kurar; Python kurulumunuza dokunmaz. Uygulama içi güncellemeyle 3.8.0'a geçenlerde sol altta **Modern görünümü kur** düğmesi çıkar (internet ve Python 3.10+ gerekir). Bileşen yoksa ya da "Klasik görünüme dön" seçilirse aynı renk temaları klasik çizimle kullanılır.
- **Dosya düzeni** (AGFO Smart Organizer artık System Care'in içinde): Masaüstü ve Belgeler'in doğrudan altındaki dosya, klasör ve kısayolları sınıflandırır (Faturalar, Denetimler, Raporlar, Görseller …), "AGFO Düzenlenenler" altına taşımayı önerir. Siz onaylamadan hiçbir şey taşınmaz, üzerine yazma ve silme yapılmaz; **Son taşımayı geri al** her şeyi eski yerine döndürür. Yerel AI (Ollama + Gemma) isteğe bağlıdır, içerik bilgisayardan çıkmaz. Taşıma kaydı bağımsız Smart Organizer ile ortaktır.

## 3.7.0'da ne değişti — İnce ayarlar ve Uygulama kur
WinCleaner (emirttac, MIT) projesinin katalogundan uygun bölümler System Care'e alındı. Yalnızca kayıt defteri, zamanlanmış görev, hizmet ve güç planı türündeki ayarlar alındı; serbest komut çalıştıran ayarlar (bcdedit, netsh, PowerShell betikleri) bilerek dışarıda bırakıldı.

**Yeni "İnce ayarlar" sekmesi**
- 70 ayar ve 28 hizmet tek listede, gruplu: Gizlilik ve telemetri, Oyun ve performans, Görünüm ve Gezgin, Windows 11 arayüzü, Ağ, Sistem ve Windows Update, Hizmetler. Bu Windows sürümüne uymayanlar (ör. Windows 10'da Windows 11 ayarları) listelenmez.
- **Durumu oku**: her ayarın şu anki durumu (Uygulanmış / Kısmen / Uygulanmamış / Bu sistemde yok); hizmetlerde şu anki ve hedef başlangıç türü. Sekme ilk açıldığında kendiliğinden okunur.
- **Risk düzeyi**: Güvenli, Dikkat (turuncu), Tehlikeli, Engelli. Tehlikeli ayarlar (ör. Windows Update hizmetini kapatmak) yalnızca "Tehlikeli ayarlara izin ver" işaretliyken uygulanır. Engelli hizmetler (RPC, DCOM, Windows Defender) hiç değiştirilemez. Bazı rekabetçi oyunların hile korumasını etkileyebilecek ayarlar için ayrıca onay istenir.
- **Ön ayarlar**: Gamer Modu, Dengeli Mod, Minimal / Sunucu Modu, Laptop / Pil Modu, Maksimum Gizlilik. Ön ayar yalnızca işaretler; uygulamak için "Seçilenleri uygula" gerekir.
- **Birebir geri alma**: her değişiklikten önce mevcut değer `%LOCALAPPDATA%\AGFO\SystemCare\tweaks-journal.json` dosyasına kaydedilir. "Son değişikliği geri al" ve "Geçmiş…" penceresi ayarları Windows varsayılanına değil, değişiklikten önceki gerçek değerlerine döndürür (değer hiç yoksa siler, yeni oluşturulan anahtar boş kaldıysa temizler). "Seçilenleri varsayılana döndür" ise Windows'un varsayılan değerini yazar.
- **Profil dışa / içe aktarma** (JSON). WinCleaner'ın özel profil dosyaları da okunur; tanınmayan ayarlar atlanır.
- **DNS**: bağlı fiziksel bağdaştırıcılarda Otomatik (DHCP), Cloudflare, Google, Quad9, AdGuard veya özel IPv4 adresleri; önceki ayar kaydedilir ve Geçmiş'ten geri alınır. **DNS önbelleğini temizle** düğmesi.
- Görev çubuğu / Gezgin ayarlarından sonra Gezgin'i yeniden başlatma önerilir; yeniden başlatma gerektiren ayarlar günlükte belirtilir.
- Yönetici gerektirmeyen (yalnızca bu kullanıcıyı etkileyen) ayarlar standart kullanıcıyla da uygulanır; yönetici gerektirenler ayrıca bildirilir. "Önce geri yükleme noktası" seçeneği vardır.

**Yeni "Uygulama kur" sekmesi**
- 159 sık kullanılan uygulama (tarayıcılar, iletişim, geliştirici, oyun, medya, araçlar) WinGet resmî deposundan sessiz kurulur veya kaldırılır. "Kurulu olanları denetle" bu bilgisayardakileri işaretler; süzgeç ve arama vardır.

**Düzeltme**
- `packaging/install_windows.ps1` sürümü elle yazılmış eski değer (3.5.0) yerine `care_core.py`'den okuyor.

## 3.6.0'da ne değişti — Kol / Gamepad
Yeni **Kol / Gamepad** sekmesi Xbox kollarının teşhis ve onarımını tek yerde toplar. EA SPORTS FC 27'de Bluetooth ile bağlı kolun rastgele giriş üretmesi gibi sorunlar için hazırlandı.
- **Liste** (`controller-list`): şu an bağlı Xbox kol bileşenleri, bağlantı yolu (USB kablo / Bluetooth / Xbox Wireless Adapter), sürücü durumu; Bluetooth radyosu ve `bthserv` hizmeti. Yalnızca Xbox kol/adaptör aygıtları sayılır (Microsoft VID 045E + bilinen ürün kimlikleri, adında "Xbox" ya da XboxComposite/XnaComposite sınıfı); Microsoft fare ve klavye listeye girmez. Sorunlu bileşen en üstte ve işaretli gelir.
- **Canlı test** (XInput): 4 yuva; tuşlar, analoglar, tetikler, pil düzeyi; bırakılmış analog ölü bölge dışında kalırsa "olası kayma (drift)" uyarısı. Sekme açık değilken okuma yavaşlar.
- **Tanı**: bağlantı yoluna göre öneriler — yalnız Bluetooth ise FC 27 / Steam Input uyarısı, USB ise firmware önerisi, sürücü sorunu, hizmet durmuş, yuvası boş kol.
- **Kol sürücüsünü sıfırla** (yönetici, `controller-reset`): işaretli (işaret yoksa listedeki tüm) Xbox bileşenlerinin aygıt kaydı `pnputil /remove-device` ile kaldırılır ve donanım yeniden taranır. PowerShell tarafı Xbox olmayan kimliği ayrıca reddeder.
- **Bluetooth hizmetini yeniden başlat** (yönetici, `bt-restart`): eşleştirmeler silinmez.
- **FC ayarlarını yedekle ve sıfırla**: en yeni `%LOCALAPPDATA%\EA SPORTS FC nn\settings\Settings*` dosyaları aynı klasörde `settings_backup_<zaman>` altına kopyalanır, kopya doğrulandıktan sonra silinir; oyun açılışta yenilerini oluşturur. Geri almak için yedekteki dosyaları geri kopyalayın.
- Kısayollar: Xbox Accessories (firmware; kurulu değilse Store sayfası), Steam kumanda ayarları, Oyun kumandaları (joy.cpl), Bluetooth ayarları, FC ayar klasörü.

## 3.5.0'da ne değişti — Aygıt temizliği
Yeni **Aygıt temizliği** sekmesi, bu bilgisayara bir zamanlar bağlanmış ama şu an bağlı olmayan aygıtları (eski USB bellekler, telefonlar, yazıcılar, USB-seri/COM portları, kaldırılmış donanım) listeler ve seçilenleri kaldırır. Uwe Sieber'in DeviceCleanup aracıyla aynı ölçütleri kullanır, fakat üçüncü taraf araç indirmez: işlem System Care'in kendi koduyla yapılır.
- Liste: `Get-PnpDevice` ile bağlı olmayan aygıtlar (genellikle Aygıt Yöneticisi kodu 45). **Son görülme**: aygıtın son bağlanma/ayrılma tarihi veya `HKLM\SYSTEM\CurrentControlSet\Enum` altındaki kayıt anahtarının son yazma zamanı (hangisi en yeniyse). Sınıfa göre gruplu; süzgeç (30 günden eski / 1 yıldan eski / tarihi bilinmeyen) ve arama.
- Varsayılan seçim: 30 günden eski olanlar. Sistem/yazılım aygıtları (`ROOT\`, `SWD\`, System, SoftwareDevice vb.) turuncu **Dikkat** olarak işaretlenir ve varsayılan seçilmez.
- Kaldırma (yönetici): Windows 10 2004 ve sonrası `pnputil /remove-device`, daha eskilerde SetupAPI. Kaldırmadan hemen önce aygıtın hâlâ bağlı olmadığı yeniden denetlenir; bağlı aygıta asla dokunulmaz. Aygıt yeniden takılırsa Windows onu yeni aygıt olarak tanır ve sürücüsünü yeniden kurar. Son COM portu kullanan aygıt kaldırılınca Windows 10 1903+ port rezervasyonunu kendisi serbest bırakır.
- **Önce geri yükleme noktası**: Windows 8+ 24 saatte yalnızca bir nokta oluşturur; bu seçenek `SystemRestorePointCreationFrequency` değerini geçici olarak 0 yapar, noktayı oluşturur ve değeri eski haline getirir.

## 3.4.0'da ne değişti — GitHub'dan tek tıkla güncelleme
- Açılışta (en fazla 6 saatte bir) `downtownck/agfo-windows-apps` deposundaki `system-care-v*` sürümleri denetlenir. Yeni sürüm varsa üstte **Şimdi güncelle / Notlar / Bu sürümü atla** bandı çıkar.
- **Şimdi güncelle**: sürüm ZIP'i indirilir, GitHub SHA-256 özetiyle (ve `SHA256SUMS.txt`) doğrulanır, ardından 3.3.0'daki yerel güncelleme hattından geçer (paket/MANIFEST denetimi, Python ve PowerShell ön kontrolü, yedek, otomatik geri alma) ve uygulama yeniden başlar.
- Güncelleme penceresinde **GitHub'da denetle** ve **Açılışta güncellemeleri denetle** seçeneği vardır. Sorgu yalnızca GitHub'a gider, kişisel veri gönderilmez.

## 3.3.0'da ne değişti — Uygulama içi güncelleme
Üst çubuktaki **Güncelleme…** düğmesi güncelleme penceresini açar. Yeni sürümün ZIP paketini seçmeniz yeterlidir; uygulama kendini günceller.
1. **Denetim** (paket diske açılmadan): ZIP yapısı ve dosya yolları (dışarı yazma girişimleri reddedilir), 50 MB sınırı, zorunlu dosyalar (`app.pyw`, `care_core.py`, `care_tasks.ps1`), sürüm bilgisi, sürüm düşürme/aynı sürüm uyarısı, varsa `MANIFEST.json` ile her dosyanın SHA-256 doğrulaması.
2. **Ön kontrol**: yeni dosyalar geçici klasöre açılır; tüm Python dosyaları derlenir, PowerShell betiği sözdizimi denetiminden geçer. Bir adım başarısızsa "Uygula" düğmesi açılmaz.
3. **Uygulama**: mevcut sürüm yedeklenir (`%LOCALAPPDATA%\AGFO\SystemCare\update-backups`, en son 3 yedek), dosyalar tek tek atomik olarak değiştirilir. Herhangi bir adım başarısız olursa önceki sürüm **otomatik geri yüklenir**. Ardından uygulama yeniden başlar.
4. **Geri dönüş**: pencerenin altındaki yedek listesinden bir sürüm seçip "Seçili yedeğe dön" — dönmeden önce mevcut sürüm de yedeklenir. "Geçmiş" düğmesi yapılan güncellemeleri listeler (`updates.log`).
- Ayarlar, günlükler, motor klasörleri (BleachBit/BCU/SDIO) ve SDIO çalışma klasörü güncellemeden etkilenmez. Testler (`tests/`), kurulum betikleri ve `.cmd` dosyaları kurulum klasörüne kopyalanmaz.
- **Güncelleme paketi** normal sürüm ZIP'idir (bu ZIP dahil). Yeni paket hazırlarken `python packaging/build_update_manifest.py agfo-care` komutu paket köküne `MANIFEST.json` yazar. MANIFEST bozulma/değiştirilme denetimidir, paketi kimin hazırladığını kanıtlamaz; paketleri yalnızca güvendiğiniz kaynaktan kurun. MANIFEST'siz eski paketler uyarıyla ve onayınızla kurulabilir.
- 3.2.0 veya öncesinden geçişte bu sürümü bir kez `Kur-ve-Baslat.cmd` ile kurun; sonraki sürümler Güncelleme penceresinden yüklenir.

## 3.2.0'da ne değişti — Bloatware temizliği
Yeni **Bloatware** sekmesi Windows ile gelen gereksiz uygulamaları tek listede toplar ve seçilenleri toplu kaldırır.
- **Store / ön yüklü uygulamalar** (`Get-AppxPackage`): bilinen paketler üç gruba ayrılır.
  - *Önerilen — güvenle kaldırılabilir* (varsayılan işaretli): King/Candy Crush oyunları, Microsoft Haberler, Bing Arama, Yardım Alın, İpuçları, Solitaire, Microsoft 365 tanıtım uygulaması, Geri Bildirim Merkezi, Haritalar, 3D Görüntüleyici/Karma Gerçeklik, Skype/Mesajlaşma, Cortana, Clipchamp, Family Safety, Filmler ve TV, Kişiler/eski Posta.
  - *Dikkat — kullanıyor olabilirsiniz* (işaretsiz): Hava Durumu, Medya Oynatıcı, Xbox/Game Bar/Xbox kimlik bileşeni, Telefon Bağlantısı, Teams, Outlook, To Do/Notlar/OneNote, Saat/Kamera/Ekran Alıntısı/Paint/Fotoğraflar, Spotify/Netflix/Disney+/TikTok vb.
  - *Korunan* (seçilemez): Microsoft Store, WinGet (App Installer), VCLibs/UI.Xaml/.NET/Windows App Runtime, Windows Güvenliği ve sistem bileşenleri, medya codec uzantıları, Terminal/Not Defteri/Hesap Makinesi, Realtek/NVIDIA/AMD/Intel/Dolby gibi sürücü yardımcıları ve Windows'un "kaldırılamaz" işaretlediği paketler. PowerShell tarafı bu paketleri arayüzden gelse bile ayrıca reddeder.
  - Katalogda olmayan Store uygulamaları *Diğer* grubunda, işaretsiz listelenir.
- **Masaüstü bloatware** (kayıt defteri): McAfee/WebAdvisor, WildTangent, Booking.com (önerilen); Norton/Avast/AVG/ExpressVPN denemeleri, CyberLink, HP/Dell/Lenovo OEM araçları, ön yüklü Microsoft 365 dil paketleri (dikkat). Bunlar kendi kaldırıcılarıyla, mümkünse sessiz kaldırılır. Programlar sekmesine de "Bilinen bloatware" süzgeci eklendi.
- Seçenekler: *Yeni kullanıcı hesapları için de kaldır* (yönetici; `Remove-AppxProvisionedPackage`), *Önce geri yükleme noktası*. Kaldırılan Store uygulamaları Microsoft Store'dan yeniden kurulabilir.

## 3.1.1 düzeltmeleri
- **BleachBit taşınabilir indirme düzeltildi ("File is not a zip file").** `download.bleachbit.org/get/…` adresi dosyanın kendisi değil, "indirme başlıyor" diyen bir web sayfasıdır (indirmeyi JavaScript başlatır). 3.1.1 dosyayı doğrudan adresinden (`download.bleachbit.org/BleachBit-6.0.4-portable.zip`) indirir ve yayıncının yayımladığı SHA-256 özetiyle (`bleachbit-6.0.4-sha256sum.txt`) doğrular; özet alınamayan bilinmeyen bir sürüm kurulmaz. Sunucu yine web sayfası döndürürse hata mesajı bunu açıkça söyler.
- **WinGet "0x8A15002B — uygulanabilir güncelleme yok".** WinGet bu kodu, paket zaten kurulu ve daha yenisi yokken döndürür; yani BleachBit sisteminizde kayıtlı. Uygulama artık motorları kayıt defterindeki kurulum kayıtlarından (InstallLocation, kaldırıcı ve simge klasörü) da arar. Böyle kurulu bir BleachBit bulunursa doğrudan kullanılır. Bulunamazsa kayıtlı konum gösterilir ve kurulumun yarım kalmış olabileceği söylenir; o zaman Programlar sekmesinden kaldırıp yeniden kurabilirsiniz. Taşınabilir paket ise her durumda ayrı ve bağımsız çalışır.

## 3.1.0'da ne değişti
- **BleachBit kurulumu düzeltildi.** BleachBit'in kurulum programı sessiz kipte `/allusers` ve yönetici yetkisi ister; WinGet'in sessiz kurulumu bu yüzden "indirildi ama kurulamadı" diye düşebiliyordu. 3.1.0 BleachBit'i **resmî taşınabilir paketinden** (download.bleachbit.org, şu an 6.0.4, yayıncı SHA-256 özetiyle doğrulanır) AGFO motor klasörüne (`%LOCALAPPDATA%\AGFO\SystemCare\engines\BleachBit`) kurar: yönetici yetkisi, kurulum programı ve UAC gerekmez. Olmazsa WinGet `/S /allusers` (yöneticiyken) ile denenir. BCU ve SDIO için önce WinGet, olmazsa resmî taşınabilir paket (BCU: GitHub sürümü, yayıncı SHA-256 özetiyle doğrulanır; SDIO: glenn.delahoy.com).
- İndirmeler yalnızca HTTPS ve izinli alan adlarından yapılır (yönlendirmeler de denetlenir), 700 MB sınırı vardır, ZIP'ten klasör dışına yazma (zip-slip) reddedilir, yarım indirme silinir, güncelleme eski sürümün yerine atomik yapılır.
- WinGet hata kodları resmî listeye göre Türkçe açıklanır (ör. `0x8A150011 — kurulum dosyasının karması bildirimle uyuşmuyor`). 3.0'daki yanlış açıklama (0x8A150109) düzeltildi.
- **Sürücü Merkezi (SDIO tarzı görünüm).** Her aygıt bir satır; altında aday sürücüler. Sütunlar: durum, kurulu sürüm/tarih, yeni sürüm/tarih, sağlayıcı, boyut. Durumlar renkli: *Güncelleme var*, *Sürücü eksik*, *Sorunlu (Aygıt Yöneticisi kodu)*, *Güncel*; adaylar *Daha yeni sürüm*, *Eksik sürücü — kurulması önerilir*, *Aynı sürüm*, *Daha eski sürüm*, *Daha zayıf eşleşme (genel uyumlu sürücü)*. Önerilenler (eksik + daha yeni) otomatik işaretlenir; üstte sayaçlar; süzgeç (Güncellemeler ve sorunlar / Tüm aygıtlar / Yalnız güncellemeler / Eksik-sorunlu / Güncel) ve arama; sağda seçili aygıtın ya da adayın ayrıntısı (donanım kimlikleri, INF, imza, eşleşme türü). "Seçilenleri kur" önce geri yükleme noktası oluşturur, yalnızca işaretli adayları kurar, ardından yeniden tarar.
  - Veri kaynağı: aygıtlar ve kimlikleri `Win32_PnPEntity`, kurulu sürücüler `Win32_PnPSignedDriver`, adaylar Windows Update sürücü kataloğu; eşleştirme donanım kimliğiyle (HWID, yoksa uyumlu kimlik) yapılır. SDIO motoru aynı sekmenin altında (analiz / seçili kategorileri kurma) kullanılmaya devam eder.

## 3.0.0'da ne değişti
2.x'te SDIO ve BCU düğmeleri yalnızca projelerin web sayfasını açıyordu. 3.0.0'da hiçbir işlev web sayfası açmaz: motorlar WinGet ile sessizce kurulur, arka planda komut satırı / betik kipinde çalışır, listeler, seçimler ve sonuçlar AGFO penceresinde görünür.

| Sekme | Motor | Uygulama içinde yapılanlar |
|---|---|---|
| Motorlar | WinGet | BleachBit, BCU, SDIO'nun kurulu olup olmadığı, sürümü ve konumu; tek tıkla sessiz kurulum / güncelleme / kaldırma |
| Temizlik | BleachBit | Tüm temizleyiciler (Windows, tarayıcılar, uygulamalar) işaretlenebilir ağaçta; "Güvenli öneri" ön seçimi; seçilenlerle önizleme ve temizlik; kurtarılacak alan özeti. Seçim hatırlanır |
| Bloatware | Windows (AppX) + kayıt defteri | 3.2.0: Store/ön yüklü ve masaüstü bloatware; Önerilen/Dikkat/Korunan grupları (yukarıya bakın) |
| Programlar | BCU + yerleşik tarama | Kurulu programlar (makine 64/32 bit + kullanıcı) boyut, tarih, tür, sessiz kaldırma bilgisiyle; arama ve süzgeçler; çoklu seçimle sıralı (mümkünse sessiz) kaldırma; kaldırma sonrası artık klasörlerin bulunup Geri Dönüşüm Kutusu'na taşınması; yetim kayıt temizliği (.reg yedeğiyle); "BCU motoruyla genişlet" ile Store/Steam/yetim kurulumların da listeye eklenmesi |
| Sürücüler | Windows Update + SDIO | 3.1.0'da Sürücü Merkezi'ne dönüştü (yukarıya bakın) |
| Uygulama güncellemeleri | WinGet | Güncellenebilir uygulamalar listede; yalnızca işaretlenenler sırayla sessiz güncellenir; her satırda sonuç |
| Bakım ve sağlık | Windows yerleşik | Temp analizi/temizliği, DISM bileşen deposu, ScanHealth, RestoreHealth + SFC, sistem bilgisi, geri yükleme noktası |

Ortak: tek işlem günlüğü (canlı ilerleme, `\r` kareleri tek satırda), Durdur düğmesi (kesilmesi güvenli işlerde), zincirleme işler (ör. kaldır → yeniden tara → artık öner), 30 günlük günlük saklama, yüksek DPI, yönetici gerektiren işlerde yükseltme önerisi.

## Güvenlik kuralları
- BleachBit: parola, çerez, oturum, form geçmişi, geri dönüşüm kutusu ve "boş alanın üzerine yaz" seçenekleri turuncu işaretlidir, güvenli öneriye girmez; temizlikte ayrıca listelenip onay istenir.
- Programlar: artık klasörler yalnızca kesin eşleşmeyle önerilir (kurulum konumu veya Program Files/ProgramData/AppData altında programın tam adı); başka kurulu programın konumuyla çakışan ya da kök klasör olan hiçbir yol önerilmez. Taşıma kalıcı silme değildir, Geri Dönüşüm Kutusu'na yapılır; PowerShell tarafı da kök/sistem klasörlerini ayrıca reddeder. Yetim kayıtlar silinmeden önce `.reg` yedeği alınır (`%LOCALAPPDATA%\AGFO\DriverCare\logs\registry-backups`).
- SDIO: "Analiz" kipi `enableinstall off` ile çalışır, sürücü paketi indirmez, kurulum yapmaz. "Kur" kipi önce geri yükleme noktası oluşturur, yalnızca seçili kategorileri (varsayılan: eksik, daha yeni, daha iyi eşleşme) kurar. Çalışma klasörü `C:\ProgramData\AGFO\SDIO` (SDIO betik dili boşluklu yolları belgelemediği için boşluksuz kök). SDIO ilk güncellemede torrent kullanır; Windows Güvenlik Duvarı izin isteyebilir.
- Motor kurulumları yalnızca resmî kaynaklardan yapılır: WinGet (`BleachBit.BleachBit`, `Klocman.BulkCrapUninstaller`, `GlennDelahoy.SnappyDriverInstallerOrigin`) veya yayıncının taşınabilir paketi (bleachbit.org, github.com/Klocman, glenn.delahoy.com).

## Lisanslar
Bu paket BleachBit (GPL-3.0), BCU (Apache-2.0) ve SDIO (GPL-3.0) kodunu veya ikili dosyalarını içermez ve yeniden dağıtmaz; her motor kullanıcının makinesine kendi lisansıyla, resmî kaynağından kurulur. AGFO, motorları belgelenmiş komut satırı arayüzleri üzerinden çağırır (BleachBit `--list-cleaners/--preview/--clean`, BCU-console `export`, SDIO `-script:` betik komutları). Bu bir fork değildir.

İnce ayarlar ve Uygulama kur kataloğu (`care_catalog.py`) WinCleaner v2.6.0 kataloglarından uyarlanmıştır — https://github.com/emirttac/WinCleaner, MIT Lisansı, Copyright (c) 2026 emirttac. Lisansın tam metni pakette `THIRD_PARTY_LICENSES.txt` dosyasındadır. WinCleaner'ın kodu (C#/WPF) alınmamıştır; System Care kendi PowerShell ve Python koduyla uygular.

## Sözleşme ve uyumluluk
Kurulum yolu, Başlat menüsü kısayolu, günlük klasörü (`%LOCALAPPDATA%\AGFO\DriverCare\logs`) ve `care_tasks.ps1 -Action` adları 2.x ile uyumludur; 3.0.0 yeni eylemler ekler (`drivers-list`, `recycle-paths`) ve `-UpdateIds`, `-Paths` parametrelerini getirir. Ayarlar: `%LOCALAPPDATA%\AGFO\SystemCare\settings.json`.

## Test durumu
Bu ortamda yapılanlar: Python 3.11/3.12/3.13 derleme; çekirdek birim testleri (28: sürücü eşleştirme ve durum, sürüm karşılaştırma, WinGet kodları, indirme kaynakları ve alan adı denetimi, SHA-256/boyut/yarım dosya, zip-slip, taşınabilir kurulum); çalıştırıcı akış testi; sanal ekranda gerçek Tk penceresiyle 114 adımlık uçtan uca arayüz testi (sahte motorlar ve sahte HTTPS yanıtıyla gerçek indirme/açma kodu; Temp ve geri dönüşüm eylemleri gerçek PowerShell 7 ile); PowerShell sözdizimi denetimi. **Windows üzerinde gerçek motorlarla ve gerçek Windows Update kataloğuyla çalıştırma yapılmamıştır** (bkz. `regression.json` SC-W*). Testler: `tests/` klasörü.
