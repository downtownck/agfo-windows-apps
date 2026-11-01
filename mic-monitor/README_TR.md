# AGFO Mic Monitor — Mikrofonu gecikmesiz dinleme ve kayıt

Mikrofonu kulaklıktan **düşük gecikmeyle** dinletir; isterseniz aynı sesi aynı anda WAV olarak kaydeder.

## Neden gerekli?
Windows XP döneminde ses kartının içindeki analog karıştırıcı mikrofonu doğrudan kulaklığa veriyordu; gecikme sıfırdı. Vista'dan beri ses Windows'un yazılım ses motorundan geçiyor. Windows'un "Bu cihazı dinle" özelliği sesi şu katmanlardan geçirir:
- karıştırıcı ve tamponları,
- ses iyileştirmeleri (APO): Voice Clarity, gürültü bastırma, Nahimic vb.

Sonuç 50–100+ ms gecikme ve enstrüman sesinin "gürültü" diye kırpılmasıdır.

Mic Monitor akışı **WASAPI özel modda** ve **RAW** seçeneğiyle açar. Ses motoru ve efekt katmanları atlanır; ses doğrudan mikrofondan kulaklığa gider. Kablolu kulaklıkla tipik gecikme **6–20 ms**'dir. Kaydedilen ses de Windows efektlerinden geçmez.

Yazılımın düzeltemeyeceği iki şey var:
- **Bluetooth kulaklığın gecikmesi.** Kablolu kulaklık kullanın.
- **Ses kartının analog dönüştürücülerinin kendi gecikmesi** (1–3 ms). Sıfır gecikme için doğrudan izlemeli (direct monitoring) bir USB ses kartı gerekir.

## Kurulum (yönetici gerekmez)
1. GitHub Releases'ten **`AGFO-Mic-Monitor-vX.Y.Z-Kurulum.zip`** dosyasını indirip bir klasöre açın.
2. **`Derle-ve-Kur.cmd`** dosyasına çift tıklayın. Betik şunları yapar:
   - Python 3.10+ sürümünü bulur,
   - `%LOCALAPPDATA%\AGFO\MicMonitor\build` altında ayrı bir ortam kurar,
   - PyInstaller, sounddevice ve numpy kitaplıklarını yükler,
   - `AGFO-Mic-Monitor.exe` dosyasını derleyip `%LOCALAPPDATA%\Programs\AGFO-Mic-Monitor` altına kurar,
   - Başlat menüsüne ve masaüstüne kısayol ekler.

Hata olursa ayrıntılar `%LOCALAPPDATA%\AGFO\MicMonitor\build\last-build.txt` dosyasına yazılır. Python yoksa https://www.python.org/downloads/windows/ adresinden kurun. Derlenen EXE çalışmak için Python'a ihtiyaç duymaz.

## Kullanım
1. **Mikrofon** ve **Kulaklık** seçin. Bluetooth ya da hoparlör seçerseniz uygulama uyarır; hoparlör geri besleme yapar.
2. **Dinlemeyi başlat.** Durum satırında kullanılan kip, örnekleme hızı ve tahmini gecikme görünür.
3. **Mikrofon kazancı** ve **Dinleme sesi** anında uygulanır. Seviye göstergesi kırmızıya giriyorsa kazancı düşürün; sağ uçta kırmızı kutu kırpılmayı gösterir.
4. **● Kaydı başlat** ile o anda duyduğunuz sesi WAV olarak kaydeder. Varsayılan klasör `Müzik\AGFO Kayitlar`, varsayılan derinlik 24 bit. "Dinlemeyi sustur" ile kulaklığa ses vermeden yalnızca kaydedebilirsiniz.

### Kulaklık takma / çıkarma
Uygulama aygıt değişikliklerini kendisi izler; kulaklık takınca dinleme yeni aygıtla kendiliğinden yeniden başlar. Çıkış olarak hoparlör seçiliyken kablolu ya da USB bir kulaklık takarsanız uygulama kulaklığa geçer. HDMI ve Bluetooth aygıtlarına otomatik geçmez. Kulaklığı çıkarınca, hoparlörden geri besleme olmasın diye dinleme duraklar; kulaklığı yeniden takınca kendiliğinden devam eder. Ses akışı sessizce durursa (uyku, sürücü sıfırlanması) uygulama bunu birkaç saniye içinde fark edip yeniden açar.

### Gecikme ayarları
- **Kip**: "Otomatik" önce WASAPI özel modu dener. Olmazsa sırasıyla özel giriş + paylaşımlı çıkış, paylaşımlı mod (yine RAW) ve en son MME denenir. "Ayrıntılar" düğmesi hangi denemenin neden başarısız olduğunu gösterir.
- **Tampon**: Küçük tampon düşük gecikme demektir. Durum satırındaki "kesinti" sayacı artıyor ya da çıtırtı duyuyorsanız tamponu büyütün (5 → 10 ms).
- **Kanal**: Dizüstü mikrofon dizilerinde iki kanal karışık mono iyidir. Stereo bir ses kartında iki girişi ayrı kaydetmek için "Stereo"yu seçin.
- **Diğer uygulamaların sesi de duyulsun**: Özel modda çıkışı Mic Monitor tutar ve başka programların sesi duyulmaz. Kayıt sırasında altyapı ya da metronom çalacaksanız bunu açın; gecikme birkaç ms artar.
- **ASIO**: ASIO4ALL, FlexASIO ya da ses kartınızın ASIO sürücüsü kuruluysa açın; uygulama yeniden başlar. Kip olarak "ASIO"yu seçin.

### Özel mod reddedilirse
Ses ayarları > Kayıt > Mikrofon > Özellikler > Gelişmiş sekmesinde **"Uygulamaların bu aygıtı özel olarak denetlemesine izin ver"** işaretli olmalı. "Windows ses ayarları" düğmesi bu pencereyi açar. Mikrofonu kullanan başka bir program da (Zoom, Teams, tarayıcı) özel modu engeller. Mic Monitor çalışırken bu programlar mikrofonu kullanamaz.

## Güncelleme ve kaldırma
"Güncelleme…" penceresinden GitHub'daki yeni sürüm denetlenir. "Şimdi güncelle" yeni EXE'yi indirir, SHA-256 ile doğrular ve uygulamayı yeniden açar. Ayarlar `%LOCALAPPDATA%\AGFO\MicMonitor\config.json` dosyasında, günlük `logs\micmon.log` dosyasındadır; güncelleme bunlara dokunmaz. "Bu bilgisayardan kaldır" ya da `Kaldir.cmd` program dosyasını ve kısayolları siler; ayarlar ve kayıtlarınız kalır.
