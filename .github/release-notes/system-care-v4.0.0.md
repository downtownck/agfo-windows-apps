# AGFO System Care 4.0.0

## İndirme
- **Python gerektirmeyen kurulum (önerilen):** `AGFO-System-Care-v4.0.0-Windows.zip` dosyasını açın, `Kur-ve-Baslat.cmd`'yi çalıştırın.
- **Uygulama içi güncelleme / Python ile kurulum:** `AGFO-System-Care-v4.0.0.zip`. 3.x kullanıyorsanız uygulama kendini bu paketle günceller.

## Yenilikler
- **Genel bakış:** bilgisayarın durumu tek ekranda (diskler, aygıtlar, Defender, güvenlik duvarı, Windows Update, yeniden başlatma, bellek, BitLocker, VPN) ve sağlık puanı.
- **Donanım:** Sistem özeti (Everest tarzı donanım dökümü), Aygıt yöneticisi, Disk sağlığı, HTML/metin rapor. Sensörler isteğe bağlı (LibreHardwareMonitor).
- **İşlem bazında yönetici onayı:** uygulama normal kullanıcıyla açılır; yönetici isteyen işlem tek başına UAC onayı ister.
- **Python'suz kurulum:** Python, tkinter, ttkbootstrap, Pillow ve Paramiko pakette hazır.
- Sürücüler, Aygıt temizliği ve Kol / Gamepad sayfaları Donanım bölümüne taşındı.

## Test
Her sürüm Linux'ta ve GitHub'daki gerçek bir Windows makinesinde test edilir: PowerShell eylemleri, yönetici yardımcısı, uçtan uca arayüz ve hazır çalışma ortamının öz-denetimi.
