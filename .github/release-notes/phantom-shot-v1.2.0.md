## AGFO Phantom Shot 1.2.0: EXE bilgisayarınızda derlenir

Kurulum artık diğer AGFO uygulamalarıyla aynı yoldan yapılıyor. Önceden hazır EXE indiriliyordu; şimdi EXE **sizin bilgisayarınızda derleniyor**. Yerelde üretilen dosya "internetten indirildi" damgası taşımadığı için SmartScreen uyarısı çıkmıyor.

- **İlk kurulum:** `AGFO-Phantom-Shot-v1.2.0-Kurulum.zip` dosyasını indirip bir klasöre açın, sonra `Derle-ve-Kur.cmd` dosyasını çalıştırın. Betik Python'u bulur ve ayrı bir derleme ortamı kurar. PyInstaller ile EXE'yi derler, `%LOCALAPPDATA%\Programs\AGFO-Phantom-Shot` altına kurar, kısayolları ekler ve uygulamayı açar. Yönetici yetkisi gerekmez.
- **Güncelleme:** Uygulama içinde "Şimdi güncelle" dediğinizde yeni EXE uygulamanın kendi koduyla indirilir ve SHA-256 ile doğrulanır. Tarayıcı kullanılmadığı için dosyaya damga eklenmez. 1.1.0 kurulu olan bilgisayarlar bu sürümü uygulama içinden alabilir.
- Hazır EXE'yi indiren `AGFO-Phantom-Shot-Kur.cmd` kaldırıldı.
