# AGFO System Care 3.4.0 — Açık kaynak motorlar tek arayüzde

## Kurulum
ZIP'i açın, `agfo-care/Kur-ve-Baslat.cmd` çalıştırın. Python 3.8+ ve tkinter gerekir (python.org kurulumunda varsayılan olarak gelir). 2.x sürümünün üzerine kurulur; çalışan eski sürüm kurulumda kapatılır. İlk açılışta **Motorlar** sekmesinden "Eksik motorları kur" düğmesine basın.

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

## Sözleşme ve uyumluluk
Kurulum yolu, Başlat menüsü kısayolu, günlük klasörü (`%LOCALAPPDATA%\AGFO\DriverCare\logs`) ve `care_tasks.ps1 -Action` adları 2.x ile uyumludur; 3.0.0 yeni eylemler ekler (`drivers-list`, `recycle-paths`) ve `-UpdateIds`, `-Paths` parametrelerini getirir. Ayarlar: `%LOCALAPPDATA%\AGFO\SystemCare\settings.json`.

## Test durumu
Bu ortamda yapılanlar: Python 3.11/3.12/3.13 derleme; çekirdek birim testleri (22: sürücü eşleştirme ve durum, sürüm karşılaştırma, WinGet kodları, indirme kaynakları ve alan adı denetimi, SHA-256/boyut/yarım dosya, zip-slip, taşınabilir kurulum); çalıştırıcı akış testi; sanal ekranda gerçek Tk penceresiyle 83 adımlık uçtan uca arayüz testi (sahte motorlar ve sahte HTTPS yanıtıyla gerçek indirme/açma kodu; Temp ve geri dönüşüm eylemleri gerçek PowerShell 7 ile); PowerShell sözdizimi denetimi. **Windows üzerinde gerçek motorlarla ve gerçek Windows Update kataloğuyla çalıştırma yapılmamıştır** (bkz. `regression.json` SC-W*). Testler: `tests/` klasörü.
