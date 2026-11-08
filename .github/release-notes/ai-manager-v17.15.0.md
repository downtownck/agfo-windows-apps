## AGFO AI Manager 17.15.0 — OpenRouter ile seslendirme

- **Yeni ses sağlayıcısı: OpenRouter.** Sitedeki OpenRouter anahtarıyla şu modellerle seslendirme yapılabiliyor:
  - Gemini TTS (70+ dil, Türkçe ve Arapça dahil)
  - Grok Voice
  - Kokoro (çok ucuz; İngilizce ve İspanyolca)
  - OpenAI gpt-4o-mini-tts
  - Ses listesini OpenRouter'ın bildirdiği diğer modeller
- **Modele göre sesler:** Model listesi OpenRouter'dan alınıyor ve her modelin yalnız kendi sesleri gösteriliyor. Ağ ya da anahtar yoksa bilinen modellerin yedek listesi kullanılıyor.
- **Okuma talimatı:** Ton, aksan ve tempo talimatı (ör. "Mısır Arapçasıyla, sakin oku") Gemini ve OpenAI modellerine gönderiliyor.
- **Sorunlu modeller kendiliğinden ele alınıyor:**
  - Yalnız PCM veren modellerin sesi WAV'a sarılıyor; sunucuda FFmpeg varsa MP3'e çevriliyor.
  - Hız ayarını desteklemeyen modeller hızsız yeniden deneniyor.
- **Nerede:**
  - **AGFO AI › 🔊 Ses Stüdyosu**'na OpenRouter paneli eklendi.
  - **AI Editor 2.15.0**'ın Ses sekmesinde OpenRouter sağlayıcı olarak seçilebiliyor.
- **Mevcut yönlendirme değişmiyor:** Otomatik yönlendirme OpenRouter'ı yalnız açıkça seçildiğinde kullanıyor. Sohbet için OpenRouter anahtarı olan sitelerde mevcut seslendirme yönlendirmesi aynı kalıyor.
