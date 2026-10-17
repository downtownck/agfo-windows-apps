AGFO BACKUPSYNC 2.1 - WINDOWS 11 / 10
====================================

Bu program C:\agfo-backutil klasorune yuklenir.
Baslat menusu: AGFO > AGFO BackupSync
Bildirim alani: AGFO BackupSync simgesi. Simgeye sag tiklayin.

Ag Kesfi / SMB sekmesi
---------------------
- Baslangicta Windows'un bagli / kalici ag suruculeri ve profilinizdeki
  UNC paylasim kokleri otomatik listelenir.
- 'Yerel agda SMB ara' butonu sadece siz onaylarsaniz ozel IPv4 aginizda
  en fazla iki /24 blogundaki TCP 445 uzerinden SMB cihazlarini arar.
- Windows'un izin verdigi SMB paylasimlari listelenir.
- Bir paylasimi secip 'Alt klasor sec' ile alttaki klasoru belirleyin;
  kaynak veya hedef olarak secin; once baglanti testi/Onizleme yapin.
- Sunucu listelenip paylasim listelenmiyorsa Windows Dosya Gezgini'nde
  \\NAS\Paylasim UNC yoluyla oturum acin; sonra listeyi yenileyin.
- Kesif SMB1 acmaz, parola denemez, port acmaz ve yazma yapmaz.
- NFS/WebDAV vb. protokoller Windows ag surucusune baglandiysa gosterilir;
  tum ag protokollerinin sunucu paylasimlarini otomatik taramaz.
- Erisim testi salt okuma testidir. Hedefe yazma izni garanti edilmez.

Yedekleme ve esitleme
---------------------
- Artimli: Robocopy, mevcut hedef dosyalarini silmeden yeni/degisenleri aktarir.
- Surumlu: rclone, hedefteki eski dosya surumlerini arsivler.
- Surumlu esitleme: rclone, fazlalari arsivler ve silme limiti uygular.
- Klasor uzunluk sinirlari Windows / SMB sunucusunun destegine de baglidir.
- WindowsApps, @eaDir ve benzeri varsayilan haric klasorler korunur.
- Gece zamanlamasi Windows Gorev Zamanlayici ile calisir, oturum acik kalmalidir.
- Windows uykusu engellenmeli; dizustu kapagi kapanmasinin ayarini kontrol edin.
- Zamanlanan profiller icin disk harfi yerine UNC yolu onerilir.

Kurulum ve veri konumu
----------------------
- Derle-ve-Kur.cmd ilk seferde gerekli Python'u winget ile (yoksa) kurar,
  pystray/Pillow/PyInstaller paketlerini pip araciligiyla indirir.
- Derlenen program Windows icin kendi basina calisan iki EXE icerir.
- dist\AGFO-BackupSync-Setup.exe yeniden kurulabilir veya paylasilabilir.
- Setup.exe Windows yonetici izni ister, cunku C:\ dizinine kurulur.
- Kayitlar ve profiller: %LOCALAPPDATA%\AGFO-BackupSync
- Daha once olusturulan zamanli gorevler DEĞISTIRILMEZ. Yeni bir gorev
  kaydederseniz dogru C:\ yolu ile yeniden olusturulur.
- Program kaldirilsa bile profiller ve loglar saklanir.
- Baslat menusu bildirim alanindaki simgeyi calistirir.
- Simge Windows tarafindan gizli simgeler acilir menusu icine alinabilir.
  Gorusunu Ayarlar > Kisisellestirme > Gorev cubugu > Diger sistem tepsisi
  simgelerinden acabilir veya simgeyi saga tasiyabilirsiniz.
- Bu derleme AGFO geliştirici imzasi icermeyen yerel bir uygulamadir.

Durum / tanilama
----------------
- C:\agfo-backutil\Dogrula.cmd ile PowerShell parser ve cekirdek testlerini acin.
- %%LOCALAPPDATA%%\AGFO-BackupSync\logs\startup-last.txt ve
  tray-last-error.txt sorunlari kaydeder.
- Windows / NAS calisma testi kurulumu yapan Windows sisteminde yapilmalidir.
- "Oturum acildiginda baslat" secenegi varsayilan olarak aciktir;
  HKLM Run kaydi ile bilgisayardaki oturumlarda tray simgesini baslatir.
  Otomatik acilmasini istemiyorsaniz kurulumda kutunun isaretini kaldirin.
