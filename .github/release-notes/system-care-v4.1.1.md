# AGFO System Care 4.1.1

- **NVIDIA indirme düzeltmesi:** sürücü bulunuyor ama indirilmiyordu (1 GB'ı aşan paketler genel 700 MB sınırına takılıyordu). Düzeltildi; indirme hatası artık ekranda bildiriliyor.
- **Lenovo otomatik güncelleme:** Üretici desteği > "Lenovo güncellemelerini tara". Lenovo'nun kendi kataloğundan bu bilgisayara uygun sürücü, yazılım ve (isteğe bağlı) BIOS güncellemeleri listelenir, seçilenler sessiz kurulur. Açık kaynak LSUClient (MIT) kullanılır; ThinkPad, ThinkCentre, IdeaPad, Legion ve Yoga desteklenir.
- **Dell otomatik güncelleme:** Dell Command | Update komut satırıyla tara ve sessiz kur.
- Diğer üreticilerde düğme Windows Update sürücü taramasına yönlendirir.
- PowerShell 7 kurulu bilgisayarlarda bazı Windows PowerShell modüllerinin (imza denetimi, paket yönetimi) yüklenememesi giderildi.
