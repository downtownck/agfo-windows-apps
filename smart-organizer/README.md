# AGFO Smart Desktop Organizer v1.0.2

Windows masaüstü ve Belgeler klasöründeki dosyaları/kısayolları **önce sınıflandıran, onay almadan hiçbirini taşımayan** masaüstü uygulaması.

## Kullanım

**En kolay yol:** Windows 10/11 ve Python 3.10+ kuruluysa `Baslat.bat` dosyasına çift tıklayın. Uygulama tkinter ile açılır; bu işlem için pip veya başka paket gerekmez.

1. `Masaüstü` ve/veya `Belgeler` kaynağını seçin; `Hızlı analiz et` düğmesine basın.
2. Önerileri inceleyin. Satırlara çift tıklayarak hedef ana konumu ve alt klasörü düzenleyebilirsiniz. Birden fazla satırı seçerek hepsini aynı hedefe atayabilirsiniz.
3. `Seçilenleri kabul et/reddet` veya `TÜMÜNÜ kabul et/reddet` kullanın. **Toplu işlemler, arama filtresinde gizlenen satırları da kapsar.**
4. `ONAYLANANLARI TAŞI` düğmesine tıklayın ve onay penceresini okuyup kabul edin.
5. Gerektiğinde `Son taşımayı geri al` ile kaydedilen taşımaları geri alın.

Windows'la gelen varsayılan Türkçe/İngilizce klasör adları yerine gerçek Windows Known Folder yolları çözülür. Böylece OneDrive'a yönlendirilmiş masaüstü ve Documents konumları desteklenir. OneDrive kullanılan klasörlerden yapılan taşıma bulut eşitlemesini tetikleyebilir.

## AI (isteğe bağlı)

Hızlı analiz, uzantı/dosya adı ve desteklenen belgelerde kısa içerik örneği kullanarak **tamamen yerel** çalışır. Gerçek bir dil modeliyle sınıflandırma için:

1. Ekran kartı gerektirmeyen otomatik kurulum için `KUR-GEMMA.cmd` çalıştırın. Ollama yoksa yükler; RAM'e göre `gemma3:1b` (6 GB+) veya `gemma3:270m` (6 GB altı) modelini indirir ve uygulama ayarını günceller.
2. Uygulamayı yeniden açıp **Modelleri bul** düğmesine basın. Yüklü modeller listelenir; eski ama bulunamayan `qwen2.5:3b` tercihi otomatik olarak yüklü Gemma modeliyle değiştirilir.
3. **Yerel AI ile iyileştir** düğmesine basın. Model bulunamadığında kurulu seçenekler gösterilir.
3. Elle kurulum alternatifi: https://ollama.com/download/windows adresinden Ollama'yı yükleyip `ollama pull gemma3:1b` çalıştırın.

CPU'da ilk yanıtın uzun sürme ihtimali için AI istek zaman aşımı 120 saniyedir. Model metin sınıflandırma içindir; görüntü analizi yapmaz.

AI yalnızca **bekleyen, belirsiz** öğeleri belirlenen sayıya kadar işler. Örnek metinler yalnızca `127.0.0.1:11434` adresindeki yerel Ollama'ya gider; bulut API bağlantısı yoktur. Ollama'nın ve modelin kurulumu isteğe bağlıdır; kurulu değilse yerel kurallara dayalı düzenleme sorunsuz çalışır. AI kategori için numaralı seçim ve Ollama JSON şeması kullanır. İngilizce/tekil kategori adlarının güvenli eşdeğerleri de tanınır. Geçersiz yanıtlarda dosyanın eski önerisi korunur; art arda 3 geçersiz cevapta AI analizi durdurulur. AI sınıflandırması hatalı olabileceğinden sonuçlar yine kullanıcı onayına tabidir.

PDF içerik çıkarımı isteğe bağlı `pypdf` paketi ile çalışır. Kurmak için: `py -3 -m pip install pypdf`. DOCX, XLSX, XLSM, PPTX, TXT, CSV gibi dosyalarda kısa içerik örneği Python standart araçlarıyla okunur. Şifreli, taranmış veya desteklenmeyen dosyalarda yalnızca ad/uzantı sınıflandırması yapılabilir. OCR yoktur.

## Windows EXE üretimi

`EXE-OLUSTUR.bat` üzerine çift tıklayın. Python, pip ve internet bağlantısı gerekir; PyInstaller kurulur ve `dist/AGFO-Smart-Organizer.exe` üretilir. Alternatif olarak projeyi GitHub reposuna yükleyip `Actions → Windows EXE` iş akışını çalıştırın; oluşan tek dosyalı EXE Artifacts bölümüne yüklenir.

> Bu teslimat `.exe` içermez; Windows'ta derlenebilir eksiksiz kaynak ve başlatıcı içerir. Bu ortam Linux olduğu için gerçek Windows GUI ve EXE çalıştırması burada doğrulanmamıştır.

## Güvenlik ve kapsam

- Sadece Masaüstü ve Belgeler klasörünün **doğrudan altındaki öğeleri** tarar. İç içe alt klasörleri tek tek taramaz; var olan üst düzey klasörleri isterse bütün olarak taşıyabilir.
- Taşıma hedefi yalnızca `Masaüstü/AGFO Düzenlenenler/...` veya `Belgeler/AGFO Düzenlenenler/...` altıdır. Hedef klasör seçimini kullanıcı düzenleyebilir.
- Dosyalar **yalnızca `Kabul`** durumundaysa taşınır. `Bekliyor` ve `Red` durumları dokunulmadan kalır.
- `desktop.ini`, `thumbs.db`, uygulamanın düzenleme klasörü ve dosya sistemi bağlantıları dışarıda tutulur. `.lnk` ve `.url` kısayolları normal dosya olarak taşınabilir; hedefleri değişmez.
- **Dosya silmez, mevcut dosyanın üzerine yazmaz.** Hedef dosya varsa çakışmayı raporlar.
- Taşınmadan sonra SQLite işlem kaydı `%LOCALAPPDATA%\AGFO\SmartOrganizer\moves.sqlite3` dosyasına yazılır. Her başarılı taşıma tek tek kaydedilir. Uygulama kapansa bile son batch geri alınabilir. Özgün yolda çakışma varsa geri alma güvenli biçimde atlar.
- Dosya tarama sırasında değişmişse taşıma yapılmaz. Klasör içeriğinde değişiklik kontrolü sınırlıdır; klasör bütün olarak taşınacağı için gözden geçirin.
- Yalnızca bulutta duran çevrimdışı OneDrive dosyaları içerik okumak için indirilmez; metadata ile sınıflandırılır. OneDrive ve üçüncü parti eşitleme davranışı uygulama tarafından yönetilmez. Taşımadan önce önemli dosyalar için yedek önerilir.
- Herhangi bir internet arka plan işlemi, telemetri veya otomatik taşınma yoktur.
- Windows masaüstü simgelerinin **ekran koordinatlarını/grid yerleşimini** değiştirmez; simgeyi oluşturan dosya ve kısayolları klasörlere gruplar.

## Geliştirici testleri

`py -3 -m unittest discover -s tests -v`

Dağıtım: MIT lisanslı kaynak; AGFO için hazırlanmış örnek uygulama.
