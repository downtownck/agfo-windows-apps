# CPU'da Gemma 3 kurulum

Windows 10/11 bilgisayarda **KUR-GEMMA.cmd** dosyasina cift tiklayin. GPU gerekmez. Kurulum mevcut Ollama'yi yeniden kurmaz, Ollama yoksa resmi ve dijital imzali Windows yukleyicisini indirir. Model indirildikten sonra Smart Organizer ayarlarinda Gemma modelini secerek kaydeder. Kisisel tercihli farkli model varsa korur.

- RAM 6 GB ve uzeri: `gemma3:1b` (yaklasik 806 MB).
- RAM 6 GB alti: `gemma3:270m` (yaklasik 292 MB; daha dusuk siniflandirma kalitesi).
- Elle model secimi: `KUR-GEMMA.cmd -Model gemma3:270m`
- Servis: `http://127.0.0.1:11434` (yerel).
- Log: `%LOCALAPPDATA%\AGFO\SmartOrganizer\gemma-install-*.log`

Model indirmek icin internet gerekir. AI analizinde dosya ornekleri yalnizca yerel Ollama'ya gonderilir. Betik gizli Windows sistem ayarlarini degistirmez; dosya tasi(ya)maz.

Windows'ta canli kurulum testi ayrica gereklidir.
