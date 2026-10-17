AGFO BackupSync v2.3.0 - TEK TIK WINDOWS KURULUM
=================================================

1) ZIP'i tamamen cikar.
2) Derle-ve-Kur.cmd dosyasina CIFT TIKLA.
3) Ilk seferde Python bulunamazsa winget ile otomatik yuklenir.
4) Python / PyInstaller / pystray / Pillow kurulumu tamamlandiginda
   iki Windows EXE derlenir (ilk calistirmada birkac dakika surebilir).
5) Windows yonetici onayi ver. Kurulum dosyasi C:\agfo-backutil\ konumuna
   uygular ve AGFO BackupSync kisayolunu Baslat menusune ekler.
6) Baslat > AGFO > AGFO BackupSync kisayolunu ac.
7) 'Ag Kesfi / SMB' sekmesinde bagli suruculer listelenir. 'Yerel agda
   SMB ara' ile yerel cihazlari tarayabilir ve kaynak/hedef secebilirsin.

ONEMLI: Windows .exe'lerini bu Linux ortaminda natively derlemek mumkun degil.
Bu ZIP, Windows uzerindeki derlemeyi ve ardindan kurulumu TEK TIKLA yapar.
Ilk derlemenin urettigi dist\AGFO-BackupSync-Setup.exe artik tek basina
calisan, Python gerektirmeyen Windows kurulum dosyasidir.

Alternatif: Sadece-Derle.cmd derler ama kurulumu baslatmaz.

Mevcut v2.0 profiller/surum arsivleri ve planli gorevler korunur.
Eski zamanli gorevler eski script yolunu kullanmaya devam eder;
istedigin profilin zamanlamasini v2.2'de yeniden kaydederek tasiyabilirsin.

Windows bildirim alaninda simgenin gorunurlugu Microsoft'un gorev cubugu
ayarlarindan kontrol edilir. Uygulama kendini zorla sabitlemez.

Sorun olursa .build-logs\last-build.txt dosyasini paylas.

YENI: Surucu Harfleri / NET USE + SUBST
- SMB (\\NAS\Paylasim) icin ag surucusu harfi (net use).
- Yerel klasorler icin SUBST, yalnizca oturum boyunca.
- Bos harfler otomatik listelenir; sistem diskleri degistirilmez.
- Kaynak/hedef olarak GERCEK yol saklanir; gece gorevleri harfe bagli kalmaz.
- Network Discovery sekmesinden dogrudan 'Harfe bagla...' secilebilir.
- Surucu kaldirmak sadece Windows eslemesini siler; dosyalara dokunmaz.

V2.2.1 - FARKLI PC'DE PYTHON KURULUM HATASI DUZELTMESI
--------------------------------------------------------
Python 3.12'nin eski bir bilgisayardaki yoluna isaret eden tasinmis
.build-venv klasoru artik kullanilmaz. Derleme sanal ortami PC'ye ozeldir:
  %LOCALAPPDATA%\AGFO-BackupSync\build-cache\venv
Kurucu secilen Python ile ortam uyumunu her seferinde kontrol eder;
yoksa veya bozuksa derleme ortamini otomatik yeniden olusturur.
Mevcut Python kurulumunuzu kaldirmayin veya PATH'i degistirmeyin.
Eski .build-venv klasoru varliginda otomatik olarak yok sayilir.
Bagimsiz Windows EXE'lerin uretilmesi icin ilk seferde internet gerekir.

V2.2.2 - PYTHON VENV / PIP OTOMATIK ONARIM
------------------------------------------
- Python yorumlayicisi gercekten calisiyor mu ayrica test edilir.
- Pip varligi venv calisabilirligi ile karistirilmaz.
- Pip yoksa yalnizca yerel sanal ortama ensurepip ile kurulur.
- Arizali sanal ortam yeniden kurulur; global Python ayarlari degistirilmez.
- Hata halinde venv olusturma ve pip denetiminin GERCEK ciktisi logda gorunur.
- Her bilgisayarin build-cache ortami ayri kalir.
- PyInstaller derlemeleri de bilgisayarin yerel build-cache dizininde yapilir.
- Sadece bitmis EXE dosyalari kaynak klasordeki dist/ dizinine kopyalanir.

V2.3.0 - GITHUB'DAN TEK TIKLA GUNCELLEME
----------------------------------------
- Bildirim alani uygulamasi acilistan 20 sn sonra ve 12 saatte bir yeni surumu denetler
  (github.com/downtownck/agfo-windows-apps, etiket backupsync-v*).
- Yeni surum varsa Windows bildirimi cikar; simgeye sag tiklayip "Guncelle: vX (tek tik)".
- Setup.exe indirilir, GitHub SHA-256 ozetiyle dogrulanir, yonetici onayiyla sessiz
  guncelleme kipinde calisir (--update). Masaustu kisayolu / otomatik baslatma tercihleri
  korunur; tepsi uygulamasi kapanip kilidi biraktiktan sonra dosyalar degistirilir ve
  uygulama normal kullanici yetkisiyle yeniden acilir. Hata olursa eski dosyalar geri konur.
- Kurulum dosyalari GitHub Actions'in Windows makinesinde derlenir; Releases sayfasindan
  hazir AGFO-BackupSync-Setup.exe indirilebilir (yerelde derleme gerekmez).
- EXE dosyalari kod imzali degildir; SmartScreen uyari gosterebilir.
