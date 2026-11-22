# AGFO Router Connect

Evdeki birden çok router'dan sinyali en güçlü olana (yani en yakın olana) bağlanan Windows uygulaması. Router'ları bir kez seçersin; sonra tek tıkla ya da otomatik olarak en yakına geçer.

## Kurulum

1. Sürümler sayfasından `AGFO-Router-Connect-vX.Y.Z-Kurulum.zip` dosyasını indirip bir klasöre aç. Bu paket yalnızca betik ve kaynak kod içerir, EXE içermez; bu yüzden web filtreleri ve SmartScreen takılmaz.
2. `Derle-ve-Kur.cmd` dosyasına çift tıkla. EXE senin bilgisayarında derlenir, `%LOCALAPPDATA%\Programs\AGFO-Router-Connect` klasörüne kurulur, Başlat menüsüne (AGFO) ve masaüstüne kısayol eklenir. Yönetici yetkisi gerekmez.
3. Gereken tek şey Python 3.10 veya üstü (tkinter ile birlikte). Derleme araçları (PyInstaller) kullanıcının Python kurulumunu kirletmeyen ayrı bir ortama kurulur; ilk seferde internet gerekir.

Kaldırmak için `Kaldir.cmd` kullan; router listen silinmez. `Baslat.cmd` kaynaktan çalıştırır, `Sadece-Derle.cmd` yalnızca EXE üretir.

## Kullanım

1. **Router listesi kendiliğinden dolar.** Uygulama ilk açılışta liste boşsa daha önce bağlandığın ağlara bakar ve o an menzilde görünenleri ekler (aşağıda nasıl). Sonradan **Geçmişten bul…** ile aynısını istediğin zaman yaparsın; satırlar işaretli gelir, istemediğini kaldırıp eklersin. Elle seçmek için **Router ekle…** var (Ctrl ile birden çok).
2. **En yakına bağlan:** seçtiğin router'ları tarar, sinyali en güçlü olana bağlanır. **Yenile** yalnızca tarar, bağlantıyı değiştirmez.
3. **Otomatik** kutusu işaretliyse uygulama her *tarama aralığında* (varsayılan 60 sn) tarar ve yalnızca daha güçlü router'ın sinyali şu anki bağlantıdan en az *geçiş eşiği* kadar (varsayılan 10 puan) yüksekse geçer. Eşik, iki router arasında gidip gelmeyi önler.
4. **Windows açılınca küçültülmüş başlat** otomatik kipi bilgisayar açılınca hazır tutar. Pencereyi kapatma, küçült; kapatırsan tarama durur.

Otomatik kip başka bir ağa (örneğin telefon noktası) bağlıyken dokunmaz; yalnızca bağlı değilken ya da seçili router'lardan birindeyken çalışır. **En yakına bağlan** düğmesi ise her durumda geçer.

### Geçmişten nasıl bulur

Üç kaynak birleştirilir; hiçbiri yönetici yetkisi istemez, okunamayan kaynak atlanır:

- Windows'ta **kayıtlı Wi-Fi profilleri**.
- Windows'un **ağ geçmişi** (son bağlanma zamanı ve ağ geçidinin, yani router'ın MAC adresi). Router'ın MAC adresi şu an görünen router'la eşleşirse listede "router eşleşti" yazar.
- **Bağlanma zaman çizelgesi** (WLAN-AutoConfig olay günlüğü): ağa kaç kez bağlandığın ve ne zaman.

"Aynı ev" ölçütü, geçmişte bağlandığın bir ağın **şu an menzilde** görünmesidir. Kafe ya da iş yeri gibi başka yerlerdeki ağlar burada görünmediği için eklenmez, **Geçmişten bul…** penceresinde gri satır olarak kalır. Sinyali %30'un altındaki ağlar (komşunun ağı gibi) otomatik eklenmez. Bir ağ yanlışlıkla eklenirse **Listeden çıkar** ile silersin.

### Router'lar farklı adlıysa / aynı adlıysa

- **Farklı ağ adları:** Ağı seçmen yeterli. Uygulama o ad için görünen en güçlü sinyali (2,4 ve 5 GHz dahil) esas alır.
- **Aynı ağ adı (mesh, aynı adı yayınlayan ayrı router'lar):** Aynı adlı birden çok satırı birlikte seçersen BSSID'leri (router'ın donanım adresi) sabitlenir ve her biri ayrı router sayılır. Bağlanırken Windows WLAN API'siyle o BSSID istenir. Bu yol kullanılamazsa uygulama ağ adıyla bağlanmayı dener ve günlüğe yazar; bu durumda Windows hangi router'a bağlanacağına kendi karar verir.

### Windows'ta bir kereye mahsus

- Her ağ için Windows'ta **kayıtlı profil** olmalı (o ağa bir kez normal yoldan bağlanıp parolayı kaydet). Uygulama parola tutmaz.
- Windows 11'de ağ listesi için **Ayarlar > Gizlilik ve güvenlik > Konum** altında konum hizmetleri açık olmalı. Liste boş gelirse uygulama bunu hatırlatır.

## Veriler

Router listen ve ayarların `%APPDATA%\AGFO\RouterConnect\config.json` dosyasındadır ve depoya girmez. Güncellemeler bu dosyaya dokunmaz.

## Güncelleme

Açılışta (6 saatte bir) GitHub'daki `router-connect-v*` sürümlerini denetler. Yeni sürümün Kurulum ZIP'ini indirir, SHA-256 ile doğrular, `Derle-ve-Kur.cmd /update` ile yeniden derleyip kurar ve açar. Ortak denetleyici: `agfo_github_update.py`. Sağ üstteki **Güncelleme** düğmesi elle denetler.

## Sınırlar

- Windows 10/11 ve Wi-Fi kartı gerekir. Ağ listesi `netsh wlan` ile okunur.
- Sinyal yüzdesi Windows'un verdiği değerdir; 5 GHz bir router kapalı kapıların arkasında 2,4 GHz'e göre düşük görünebilir. Seçim yalnızca sinyale göre yapılır.
