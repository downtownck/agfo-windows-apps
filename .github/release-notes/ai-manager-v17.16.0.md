## AGFO AI Manager 17.16.0

- **AGFO System Care bağlantısı:** Windows bakım uygulaması AGFO System Care, AI Editor ile aynı bağlantı anahtarıyla bağlanır. `/editor/chat` ucu `profile=system_care` ile Windows bakım asistanı istemini kullanır (yalnız verilen sistem verisine dayanır, her öneride risk düzeyi ve geri alınabilirlik belirtir, kritik servis/güvenlik yazılımı kapatmayı önermez). Günlükte kaynak `agfo-system-care` olarak görünür.
- `/editor/ping` yanıtı desteklenen profilleri (`profiles`) bildirir.
- Menü: "AI Editor / System Care bağlantısı"; anahtar sayfası iki uygulamayı da anlatır. Her bilgisayar/uygulama için ayrı etiketli anahtar önerilir.
- Varsayılan profil `editor`: AI Editor'ün davranışı değişmedi.
