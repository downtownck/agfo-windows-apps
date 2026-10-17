# AGFO SuperTools 1.7.0 — GitHub'dan tek tıkla güncelleme

Uygulama açılışta (en fazla 6 saatte bir) `downtownck/agfo-windows-apps` deposundaki `supertools-v*` sürümlerini denetler.
Yeni sürüm varsa notlarıyla birlikte **Şimdi güncelle / Sonra / Bu sürümü atla** penceresi açılır. Güncelleme Merkezi'nde
**GitHub'da denetle**, **Şimdi indir ve güncelle** ve **Açılışta denetle** bulunur. İndirilen `.update.zip`, GitHub SHA-256
özetiyle ve paketin kendi manifestiyle doğrulanır; kurulum mevcut güncelleyiciyle (yedek + otomatik geri alma, gerekirse UAC)
yapılır. Yerel ZIP ile güncelleme aynen çalışmaya devam eder. 1.6.0'dan geçişte `AGFO-SuperTools-v1.7.0.update.zip`
dosyasını Güncelleme Merkezi'nden bir kez yükleyin.

# AGFO SuperTools 1.6.0 — Çoklu SSH oturumları

Yeni **SSH Oturumları** sayfasında birden fazla dahili SSH bağlantısı kendi sekmesinde açık kalır.
Sekmeler arasında geçerken bağlantı kesilmez. **Alt alta iki oturum** ile iki ayrı
bağlantıyı aynı sayfada eşzamanlı görün, gerektiğinde yukarı/aşağı oturumu ayrı ayrı seçin.
Her SSH oturumunun komut kutusu, Ctrl+C, bağlantıyı kes ve sekmeyi kapat kontrolleri ayrıdır.

**Kullanım:** SSH Sunucularım > profil seç > Dahili SSH / Parola. Yeni oturum için aynı
adımı başka bir profil için (veya aynı profil için) tekrarlayın. Sol menüden SSH Oturumları
sayfasına gidin. Burada Alt alta iki oturum / Sekme görünümüne dön düğmesini kullanın.

Parola yalnızca bağlantı anında sorulur, isteğe bağlı Windows DPAPI kasasında 1/3/4/8/24
saat tutulur. Yeni oturum eski oturumun bağlantısını kesmez. Sekme kapatma yalnızca
ilgili SSH oturumunu kapatır. Güncelleme yapıldığında **halen açık TCP/SSH oturumları**
kapanır; sunucudaki işlemlerinizin durumunu kontrol edip güncelleme yapın.

Tkinter konsolu bir **tam VT100/ANSI terminal emülatörü değildir**; `vim`, `nano`, `top`
gibi tam ekran komutlar için OpenSSH Terminal kullanın. Şifrelenmiş kasa,
profiller, uygulama ayarları ve geri alma mantığı korunur.

# AGFO SuperTools 1.6.0 — Güvenli SSH Parola Girişi

Koyu lacivert tasarım, ikonlu yan menü, merkezde tek tık tarama, canlı durum kartları, modern tablolar ve açık/koyu görünüm. Tüm 1.3 araçları ve ZIP Güncelleme Merkezi korunur.

# AGFO SuperTools / Multi-Subnet Scanner v1.6.0

Windows 10/11 icin ag kesfi, DNS / e-posta / TLS / TCP testleri ve kalici SSH sunucu profilleri sunan, birlestirilmis AGFO araci. Eski coklu subnet tarama, SMB ve guncelleme ozellikleri korunur.

## Hemen kurulum

1. ZIP dosyasini tamamen cikarin.
2. **Kur-ve-Baslat.cmd** dosyasina cift tiklayin.
3. Yonetici onayini verin; `C:\agfo-backutil\MultiSubnetScanner` klasorune kurulur.
4. Baslat menusunde **AGFO Multi-Subnet Scanner** gorunur.

Python 3.10+ ve `tkinter` zaten varsa paket kurulmaz. Python yoksa `winget` ile Python 3.13 kurulumu denenir. Uygulamanin kendisi yalnizca Python standart kutuphanesini kullanir; pip veya venv gerektirmez.

**Baslat.cmd** portable olarak, kurulum yapmadan calistirir (Python gereklidir). **EXE-Derle.cmd** ise istege bagli olarak PyInstaller kullanip Windows bilgisayarinda `dist\AGFO-MultiSubnet-Scanner.exe` olusturur. Derlenen EXE icin Python kurulu olmasi gerekmez. Linux uzerinde Windows EXE derlenemez; paket EXE degil, Windows uzerinde EXE uretebilen kaynak kod ve kurucu icerir.

## v1.1 yenilikleri

- **Konsol pencereleri gizlendi:** Windows `ping`, `arp`, `route`, `net view` ve PowerShell komutlari GUI icinde pencere acmadan calisir. Uygulamanin "Dahili terminal / Gunluk" sekmesi komut ciktilarini gosterir. Bu alan komut girilen bir shell degil, guvenli islem gunlugudur.
- **Daha kapsamli kesif:** ARP komsu onbellegi ve yerel SSDP/mDNS yayinlari taranir. Bilinen cihazlara oncelik verilir. Aktif taramadan sonra ARP bir daha okunur ve adaylara sinirli bir ikinci deneme yapilir.
- **TCP yoklamasi hizlandi:** Portlar her cihaz icin es zamanli test edilir; yanitlayan ama hizmet portu kapali olan cihazlar TCP-RST ile bulunabilir. Yeni varsayilan zaman asimi 650 ms.
- **Aktif / aday ayrimi:** ICMP veya TCP ile dogrulanan cihazlar "Aktif", yalniz ARP kaydinda bulunanlar "Aday (dogrulanmadi)" olarak gosterilir; ikisi karistirilmaz.
- **MAC bilgisi ve CSV:** ARP'den MAC biliniyorsa ekranda ve CSV'de gorunur. Farkli subnet uzerindeki MAC bilgisi her zaman erisilebilir degildir.
- **Eski ayarlar:** Mevcut kullanici profili/tercihleri korunur; v1.0'in 300 ms varsayilani ilk calismada 650 ms'ye yukseltilir. Ozel ayarlar korunur.

**Sinir:** Fiziksel olarak bagli olan tum cihazlari bir Windows istemcisi tek basina goremez. Misafir agi, NAT, baska VLAN, Wi-Fi client isolation, guvenlik duvari ve ICMP/TCP'yi yanitlamayan cihazlar gizli kalabilir. Router DHCP kira listeleri, her alt agda ayri ajan veya AP/bridge modu gerekebilir.

## Kullanma

Onerilen tarama araliklari:

```
192.168.0.0/24
192.168.1.0/24
```

**Taramayi Baslat** ile cihazlari arayin. Acik `SMB (445)`, HTTP/HTTPS portlari, TCP red cevabi, ping ve ARP/mDNS/SSDP sonucuna gore IP adreslerini gorursunuz. "Aday" satirlari cihaz aktifliginin kaniti degildir. `Genis servis taramasi` FTP, SSH/SFTP, NFS, rsync ve diger web portlarini da kontrol eder.

- **SMB klasorunu ac:** Windows Explorer'da `\\IP` adresini acar.
- **Paylasimlari sorgula:** `net view \\IP` sonucunu gosterir. SMB kimlik bilgileri gerekebilir.
- **Web arayuzu:** Tespit edilen HTTP/HTTPS adresini acar.
- **UNC kopyala:** `\\IP` konumunu kopyalar. Gercek paylasim icin `\\IP\Paylasim` kullanin.
- **CSV kaydet:** Sonuclari UTF-8 (Excel icin BOM) dosyaya yazar.
- **Windows ag/rota bilgileri:** Yerel arayuz, route print -4, net use ve arp -a bilgilerini uygulamanin Dahili terminal / Gunluk sekmesine yazar.

Tarama ayarlari `%LOCALAPPDATA%\AGFO-MultiSubnet-Scanner\settings.json` konumuna kaydedilir. Parola veya kimlik bilgisi kaydedilmez.

## Guvenlik ve sinirlar

- Yalnizca size ait veya tarama yetkiniz olan aglari kullanin.
- Yalnizca ozel IPv4 araliklari (10/8, 172.16/12, 192.168/16) ve 100.64/10 CGNAT/Tailscale araligi desteklenir.
- En fazla 2048 IP taranabilir. /16 veya /8 yerine belirli /24 bloklari secin.
- Izin verilmeyen/rota bulunmayan baska bir IP blogunu otomatik kesfedemez; NAT veya firewall'i asamaz.
- Farkli DHCP sunucularinin verdigi bloklari (orn. 192.168.0.0/24 ve 192.168.1.0/24) bilerek ekleyin. Bu, internet portu acmaz, ayar veya dosya degistirmez.
- ICMP filtrelense bile TCP acik port veya TCP reddi cihaz hakkinda ipucu verebilir. ARP/mDNS/SSDP ek ipuclari saglar. Yanit vermeyen bazi cihazlar yine gorunmeyebilir.
- Ag IP blogu uzaktaysa MAC adresi veya yerel DHCP kiralari normal olarak okunamaz.
- Bazi IP'lerde port 445 acik olsa bile SMB paylasim listesi oturum/izin gerektirebilir. SMB1 etkinlestirilmez.
- Bu bir **tarayicidir**, rclone/BackupSync yedekleme motorunun yerini almaz.

## Paket yapisi

- `app.pyw`: Tkinter grafik arayuzu
- `scanner_core.py`: adres ve TCP/ICMP tarama motoru
- `packaging/*.ps1`: Windows kurulum ve istege bagli EXE derleme
- `tests/test_scanner_core.py`: tarama kapsami, guvenlik ve hata senaryolari testleri

Gercek Windows/NAS aginda ilk tarama ile davranisin kontrol edilmesi gerekir.

### Sorun giderme

Pencere acilmiyor veya hemen kapaniyorsa **Tanila.cmd** dosyasini calistirin.
PowerShell konsolunda Python GUI'nin gercek hata mesaji gorunur ve pencere acik kalir.

Not: taranacak diger yaygin yerel ag onerileri otomatik **onerilir**, izniniz/onayiniz olmadan tum yaygin aglar otomatik taranmaz.

Kurulumu kaldirmak icin **Kaldir.cmd** dosyasini kullanin. Yalnizca bu aracin klasoru ve Baslat menusu kisayolu silinir; BackupSync dosyalari ve kaydedilmis kullanici ayarlari silinmez.

## v1.1.1 - SMB hata 5 / Turkce karakter duzeltmesi

SMB 445/TCP acik olsa da `net view` islemi yetki gerektirebilir.
`Paylasimlari sorgula` hata 5 dondugunde uygulama artik bu farki aciklar ve
`SMB ile baglan` secenegini onerir. Paylasim adini biliyorsaniz o ada dogrudan
baglanabilirsiniz; paylasim listesinin acik olmasi gerekli degildir.

NAS kullanicisi/parolasi istenirse Windows WNetAddConnection2W API kullanilir:
parola komut satirina, loga veya ayarlara yazilmaz. Windows olusturulan SMB
oturumunu oturum bitene dek tutabilir. Bir NAS'a farkli hesapla kurulmus
mevcut SMB oturumu varsa 1219 hatasini verir; uygulama bu oturumlari silmez.

net.exe / arp.exe / route.exe ciktilari Windows OEM karakter kodlamasiyla
okunur (Turkce Windows icin genellikle cp857). SMB1 acilmaz; yonlendirici
ve NAS ayarlari otomatik degistirilmez.

## v1.2.0 - Güncelleme Merkezi (firmware-benzeri ZIP kurulumu)

Bu sürümde sağdaki sekmelerde **Güncelleme Merkezi** bulunur. İleride AGFO Scanner
sürümü geldiğinde **AGFO-...update.zip** dosyasını seçip **Doğrulanan paketi
yükle ve yeniden başlat** butonuna basın. Her yeni sürüm için CMD veya PowerShell
çalıştırmak gerekmez. **v1.1.1 -> v1.2.0 ilk geçişinde** henüz eski sürümde
Güncelleme Merkezi olmadığı için bu ZIP'teki `Kur-ve-Baslat.cmd` bir kez çalıştırılır.

- Güncelleme yalnızca kullanıcı tarafından seçilen yerel ZIP'ten yapılır. İnternet bağlantısı veya NAS firmware'ine erişim gerekmez.
- ZIP uygulama kimliği, yeni sürüm, dosya yolları, boyutlar ve SHA-256 ile doğrulanır. Bozuk veya beklenmeyen dosyalar ve eski sürümler reddedilir.
- İmzalama yoktur: **SHA-256, paket yayıncısının AGFO olduğunu kanıtlamaz.** Yalnızca güvenilir kaynaktan aldığınız güncellemeleri seçin. Paketler kod içerdiğinden bilinmeyen paketler zararlıdır.
- Güncelleme başlamadan önce yedek `%LOCALAPPDATA%\AGFO-MultiSubnet-Scanner\backups` altında saklanır. Başarısız uygulamada geri alınmaya çalışılır; başarılı güncelleme sonrası **Geri dönüş** bölümünden eski sürüm seçilebilir.
- Yükleme sırasında GUI kapanır, kurulu program dosyaları yenilenir, otomatik açılır. Kurulum klasörüne yazma izni yoksa UAC yönetici onayı istenir.
- Profiller / tarama aralıkları `%LOCALAPPDATA%` altında korunur; diğer AGFO araçlarına dokunulmaz.
- `%LOCALAPPDATA%\AGFO-MultiSubnet-Scanner\updates\last-result.json` ve `update-history.log` güncelleme sonuçlarını saklar.
- Eğer tek başına PyInstaller EXE ile **portable** çalışıyorsanız, GUI içi güncelleme desteklenmez. `Kur-ve-Baslat.cmd` ile kurulu Python tabanlı sürümü güncelleyin.

Gelecek sürüm paketleri geliştirici tarafından `python packaging/create_update.py --output AGFO-Scanner-vX.Y.Z.update.zip --notes "Yenilikler..."` komutuyla hazırlanabilir. Hazırlanan ZIP içinde `update-manifest.json` ve `payload/*` bulunur. Tam kurulum ZIP'i Güncelleme Merkezi'nde kabul edilmez. Güncelleme işlemi **router/NAS firmware'i yüklemez**; yalnızca bu Windows uygulamasının kodunu değiştirir.

Güncelleyici kurulum dosyalarına yazmak için yönetici izni istemek zorunda kalırsa, güvenlik nedeniyle **yönetici olarak çalışan tarayıcıyı kendiliğinden açmaz**. Bu durumda güncelleme bittikten sonra Başlat menüsünden normal kullanıcı olarak açın. Güncelleme durumu ilk açılışta Güncelleme Merkezi'nde gösterilir.

## v1.4.0 - AGFO SuperTools ve kayıtlı SSH sunucuları

Bu sürüm, önceki bütün ağ keşfi / SMB bağlantısı / dahili günlük / ZIP Güncelleme Merkezi özelliklerini korur. Sağ tarafta iki yeni sekme bulunur:

**SuperTools:** `DNS A`, `AAAA`, `MX`, `NS`, `CNAME`, `TXT`, `SOA`, `PTR`, `SRV`, `CAA`, `SPF`, `DKIM`, `DMARC`, `MTA-STS`, `TLS-RPT`, `Mail Sağlığı`, `TCP Port`, `Ping`, `Traceroute`, `HTTP`, `HTTPS`, `TLS Sertifikası`, `SMTP / STARTTLS`, `RDAP / ASN`. MXToolbox'a benzer tek komut kutusuna örneğin şunlar girilebilir:

```
mx: agfocert.com
dmarc: agfocert.com
dkim: selector:agfocert.com
mtasts: agfocert.com
tlsrpt: agfocert.com
tcp: 192.168.1.102:445
smtp: mail.example.com:587
```

Araç listesinden test seçip yalnızca alan adını/IP'yi yazmak da mümkündür. Testler arka planda ve konsol penceresi açmadan çalışır; çıktı SuperTools sekmesinde görünür. Son oturumun en fazla 30 sonucu **TXT raporunu kaydet** ile dışa aktarılabilir; otomatik geçmiş veya parola kaydı yapılmaz. `nslookup.exe`, Windows OpenSSH ve `tracert.exe` yerleşik Windows araçlarıdır. **Haricî pip paketi gerekmiyor.** Bazı DNS kayıtları (`CAA`, `SRV`) sistem nslookup aracının yeteneklerine bağlıdır. TLS testinde sertifika doğrulaması varsayılan olarak açıktır; sertifika hatası gizlenmez. SMTP el sıkışması e-posta göndermez, kimlik bilgisi istemez. MTA-STS hem DNS kaydını hem web politikasını sorgular. IP RDAP sorgusu genel RDAP/RIPEstat sunucularına gider ve kamuya açık IP ile sınırlıdır.

**SSH Sunucularım:** Sunucuya anlamlı profil adı, DNS/IP, port, SSH kullanıcı adı, isteğe bağlı özel anahtar **dosya yolu** ve not kaydedebilirsiniz. `SSH Terminal aç` seçeneği bir **istek üzerine** Windows Terminal penceresi açar; Windows Terminal yoksa native OpenSSH konsolu kullanılabilir. Bu terminalde parola veya anahtar parolası OpenSSH tarafından istenir. SSH ile özel anahtar/ssh-agent kullanıyorsanız tek satırlık **SSH komutu** için uygulama içi çıktı da kullanılabilir. Uzak komut çalıştırılmadan önce açık onay istenir. Arka planda çalışan komutlar `BatchMode=yes` kullanır ve beklenmedik parola pencereleri açmaz. İlk kez bağlanılan sunucunun host key'i, etkileşimli terminalde kullanıcı tarafından doğrulanmalıdır; sunucu anahtarı kontrolleri kapatılmaz.

SSH profil verileri `%LOCALAPPDATA%\AGFO-MultiSubnet-Scanner\ssh-profiles.json` konumuna kaydedilir. **Parolalar, SSH özel anahtar içeriği, API token'ları ve uzak komutlar saklanmaz.** Dosyada yalnızca sunucu/hesap metadata'sı ve varsa anahtar dosyasının yolu bulunur. Sunucu yöneticisi değişse bile kayıtlı profiller uygulama güncellemesinden etkilenmez. `ssh.exe` yoksa Windows'ta **İsteğe Bağlı Özellikler > OpenSSH İstemcisi** etkinleştirilmelidir.

**Güncelleme:** `v1.2.0 -> v1.4.0` geçişi için *Güncelleme Merkezi > Güncelleme ZIP'i seç* ile birlikte dağıtılan `AGFO-MultiSubnet-Scanner-v1.4.0.update.zip` dosyasını seçebilirsiniz. Tam kurulum paketi de aynı `C:\agfo-backutil\MultiSubnetScanner` konumuna kurulur. v1.3 güncellemesi `supertools_core.py`, `supertools_ui.py` ve `ssh_profiles.py` modüllerini kurar. Güncelleme öncesi çalışan program kapanır, önceki sürümün yedeği oluşturulur; sorun çıkarsa arayüzde geri dönüş kaydı vardır. Geçerli kurulumu yönetici olarak çalıştırmanız gerekiyorsa Windows UAC onayı istenebilir. Güvenilir olmayan ZIP'ler kullanmayın: SHA-256 tek başına yayıncı imzası değildir.

**Ağ güvenliği:** Kullanıcının başlattığı testlerin bazıları internet sunucularına erişir ve hedef adı/IP bilgisi üçüncü taraf servislerde görülebilir. Port, SMTP ve SSH işlemlerini yalnızca izinli sunucularda kullanın. SSH oturum açma, yetkilerin veya firewall/SSH sunucu ayarlarının otomatik değiştirilmesine yol açmaz. Web TLS testleri sistem güven köklerine dayanır; asla doğrulamayı `verify=False` ile kapatmayın.

## Test durumu

Python 3.10+ kaynak sözdizimi ve otomatik testler ile Tkinter arayüzü görüntüleme/saklama testi gerçekleştirilir. Windows'a özgü `nslookup`, `tracert`, Windows Terminal ve gerçek SSH sunucusu bağlantısı, geliştirmenin Linux ortamında doğrulanamaz; ilk Windows kurulumunda kontrol edilmelidir.


## v1.6.0 — Dahili SSH parola penceresi / zamanli DPAPI kasasi

SSH Sunucularim ekraninda profili kaydedin; **Dahili SSH / Parola** dugmesine basin.
Windows Terminal acilmaz: parola yildizli Tkinter penceresine yazilir ve temel SSH
terminal ciktilari uygulamanin kendi SSH panelinde gorulur. Istege bagli
**Parolayi gecici olarak hatirla** kutusunda 1, 3, 4, 8 veya 24 saat secin.
Ilk kimlik dogrulama basarili olmadan parola saklanmaz.

Sifreli kasa Windows CurrentUser DPAPI'yi kullanir,
`%LOCALAPPDATA%\AGFO-MultiSubnet-Scanner\ssh-password-cache.dpapi.json`
altindadir. Parolanin duz metni ne profilde ne komut satirinda bulunur.
Suresi dolan kayit tekrar kullanilamaz; uygulama acikken yaklasik her dakika ve
acilista temizlenir. Uygulama kapaliyken otomatik dosya silme gorevi calismaz;
sonraki acilista temizlik yapilir. **Bu parolayi unut** / **Tum parolalari unut**
secilerek derhal temizlenebilir. Mevcut SSH profilleri ve anahtar dosyalarina
dokunulmaz.

Dahili terminal icin guvenilir Paramiko Python kitapligi gerekir.
Ilk baglanti dugmesinde sorulur ve sadece onayinizla `pip --user` ile kurulur.
Anahtar/ssh-agent icin mevcut **OpenSSH (Anahtar)** dugmesi kalir. PyInstaller
ile EXE derlerseniz `EXE-Derle.cmd` Paramiko'yu EXE'ye dahil eder.
Sunucunun bilinmeyen SSH anahtari SHA256 parmak izi onayi olmadan kabul edilmez;
daha once onaylanmis sunucu anahtari degisirse baglanti engellenir.

Dahili terminal basit komut ve cikti icindir. vim/nano/tam ekran uygulamalar
ve tum ANSI terminal emulasyonu desteklenmez; bunlar icin OpenSSH Terminal
kullanilmalidir. `sudo` gibi ikinci parola girislerinde **Girisi gizle**
secenegini kullanin.

**Guvenlik siniri:** DPAPI, Windows kullanici hesabini korur ancak o oturumda
kullanici haklariyla calisan zararlilara karsi mutlak koruma saglamaz. Python
bellek yonetimi sebebiyle islem belleginden kesin silme garantisi verilmez.
Kurulu dosyalarla birlikte paylasilan `.update.zip` dosyasi imzali degildir;
yalnizca guvenilir kaynaktan gelen guncellemeleri yukleyin.
