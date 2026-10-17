AGFO BackupSync v2.2 - surucu harfi yonetimi
============================================

Surucu Harfleri sekmesi Windows'ta iki yontemi birlestirir:
- SMB: \\UGREEN\Yedekler gibi UNC paylasimina NET USE ile surucu harfi.
- SUBST: C:\Belgeler\Arsiv gibi yerel klasore gecici surucu harfi.

Net use eslemesi /persistent:yes ile yeniden oturum acilinca Windows
araciligiyla baglanmayi dener. NAS'in acik olmasi ve Windows kimliginin
erisim hakki bulunmasi gerekir.

SUBST yalnizca mevcut oturumda gecerlidir; yeniden baslatmada kaybolur.
SUBST ile UNC yolu dogrudan eslenmez. Uygulama UNC yolu icin NET USE
kullanir. Onerilen gece yedekleri UNC/gercek disk yolu ile calisir.

GUI kullanimi:
1) Ag Kesfi / SMB sekmesinde paylasim sec.
2) Harfe Bagla secenegi Surucu Harfleri sekmesine aktarir.
3) Bos bir harf sec (ornegin Z:), gerekliyse kalici baglanti sec.
4) Surucuye bagla sec, sonra listeyi kontrol et.
5) Kaynak veya hedef secince asil UNC/klasor yolu kaydedilir.

Parola alinmaz ve saklanmaz. Ayrica baglanman gerekiyorsa Windows Dosya
Gezgini uzerinden NAS kimlik dogrulamasini tamamla.

Mevcut SMB veya SUBST eslemeleri sadece secilip ayrica ONAY verilirse
kaldirilir. Hicbir NAS dosyasi esleme kaldirma ile silinmez.

Not: Yonetici penceresinde olusturulan suruculer, normal kullanici
pencerelerinde gorunmeyebilir. Kurulum UAC gerektirir ama AGFO uygulamasini
normal kullanici hesabindan baslatmak daha uygun olur.
