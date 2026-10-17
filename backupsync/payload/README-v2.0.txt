AGFO BACKUPSYNC 2.0 - WINDOWS / SYNOLOGY / UGREEN
===================================================

KURULUM
1) ZIP arsivini C:\AGFO-BackupSync-Kurulum gibi bir klasore cikarin.
2) Once "Dogrula.cmd" dosyasini calistirin. Hata yoksa "Kur-ve-Baslat.cmd" calistirin.
3) Uygulama, %LOCALAPPDATA%\AGFO-BackupSync\app klasorune kurulur.
   Masaustunde "AGFO BackupSync" kisayolu olusturulmaya calisilir.
4) Profil adi, kaynak (or: D:\Documents), hedef (or: \\UGREEN\Backup\Documents)
   bilgilerini girin, once Onizleme, sonra Simdi calistir secin.
5) Gecelik yedek icin Gece Zamanlamasi sekmesini kullanin.

3 MOD
1. ARTIMLI YEDEK: Windows'un Robocopy motorunu kullanir. Hedefte fazladan
   kalan dosyalari SILMEZ. Degismis dosyalarin eski surumu saklanmaz.
2. SURUMLU YEDEK: rclone copy + --backup-dir kullanir. Hedefte eski hali
   degisecek dosyalar, .agfo-versions/<profil>/<calistirma> altinda saklanir.
   Hedefte tek basina bulunan dosyalar silinmez.
3. SURUMLU ESITLEME: rclone sync + --backup-dir kullanir. Kaynakta bulunmayan
   hedef dosyalarini silmek yerine ARSIV klasorune tasimaya calisir.
   Bos kaynak engellenir, silme adedi varsayilan olarak 100 ile sinirlanir.
   Bu sinir asilirsa esitleme kismen tamamlanip hata verebilir. Tek yonludur!

SURUM ARSIVI / GERI YUKLEME
Surumler sekmesi, her calistirmada DEGISTIRILMIS veya hedeften kaldirilmis
ESKI dosyalari gosterir. Tam gunluk snapshot/sistem imaji DEGILDIR.
Geri yukleme, varsayilan olarak Windows Documents\AGFO-Restore altindaki
YENI ve BOS bir klasore kopyalar. Canli hedefin uzerine yazmaz.
Surum arsivleri varsayilan olarak OTOMATIK SILINMEZ. Kapasiteyi kontrol edin.
Profilin hedef yolunu degistirirseniz eski arsiv eski hedefte kalir.

HATALAR VE UZUN DOSYA YOLLARI
Robocopy /256 kullanilmaz; uzun yollar desteklenir. Ayrica sifrelenmis EFS
nesneleri /XA:E ve varsayilan WindowsApps haric tutularak atlanir.
Sorunlu dosya 2 kere yeniden denenir; ardindan digerleri islenir.
Hata varsa sonuc 'partial' olabilir; asla sessiz basari sayilmaz.
Windows PC acik ve uyanik olmali. Zamanlanmis islerde oturum acik kalmali.
Windows ekran kilidi sorun degildir. Yine de Windows uyku/guclendirme ayarlarini
ve NAS cihazlarinin calisir halde oldugunu kontrol edin.

AG PAYLASIMLARI / SIFRELER
SMB UNC yollarini kullanin: \\SYNOLOGY\Paylasim veya \\UGREEN\Paylasim.
Windows kullanici hesabinin iki NAS'a erisim yetkisi bulunmali.
Uygulama hicbir NAS parolasini profillere yazmaz. Windows oturum / Credential
Manager ayarlari size aittir. Administrator olarak calistirmak gerekmez.

YENI / ESKI PROFILLER
Eski v1 AGFO-NAS-Copy profilleri otomatik ice aktarilir.
Eski profiller, yanlis silmeyi engellemek icin 'artimli yedek' moduna getirilir.
Eski program ve profilleri SILINMEZ. Eski v1 GECE GOREVLERI de otomatik
kaldirilmaz: Windows Gorev Zamanlayici'dan kontrol edin. Iki surumu ayni anda
ayni hedefe calistirmayin.
Yeni profillerin JSON dosyalari: %LOCALAPPDATA%\AGFO-BackupSync\profiles
Calisma loglari: %LOCALAPPDATA%\AGFO-BackupSync\logs

RCLONE / WINGET
Robocopy Windows 10/11 ile gelir, kurulum istemez.
Surumlu modlar icin Motorlar sekmesindeki 'rclone kur (winget)' dugmesini
kullanin. Kullanici onayi ile resmi Rclone.Rclone paketi kurulur.
winget yoksa App Installer gereklidir; otomatik rastgele dosya indirilmez.

GUVENLIK
- Kaynak dosyalar hicbir modda silinmez.
- Robocopy /MIR /PURGE kullanilmaz.
- Surumlu esitleme ayri onay ve maksimum silme limiti gerektirir.
- Islem dosya hatasinda log yazar; yalnizca bir kisim kopyalandiysa 'partial'.
- Restore hedefi canli kaynaktan veya hedef klasorunden AYRI olmalidir.
- EFS sifrelenmis kaynak dosyalari Robocopy tarafinda atlanir.
- Uygulama Windows gerektirir; Linux uzerinde calistirma testi yapilamaz.
- Dogrula.cmd yerel PowerShell parser ve guvenlik fonksiyon testlerini calistirir.

RESMI BELGELER
https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/robocopy/
https://rclone.org/docs/#backup-dir
https://rclone.org/flags/
