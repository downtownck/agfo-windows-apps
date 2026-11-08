## AGFO AI Manager 17.14.0 — AI Editor seslendirmesinde OpenAI, ElevenLabs ve MiniMax

- **Sağlayıcı seçimi:** AI Editor'ün "Sesli oku", "Ses dosyası" ve "Sesli çizgi roman / Video" işlevleri artık EMA'ya ek olarak OpenAI, ElevenLabs ve MiniMax ile de seslendirebiliyor. Sitede **AI Manager › Sağlayıcılar** sayfasında anahtarı girilmiş sağlayıcılar editörde seçilebilir oluyor.
- **Ses ve model listesi:** Yeni uç `/editor/voices` (GET ya da POST, `provider=…`), AI Manager'ın ses kataloğundan sesleri ve modelleri döndürüyor: OpenAI'nin yerleşik sesleri, ElevenLabs hesabındaki sesler, MiniMax sesleri.
- **Kısa seslendirme** (`/editor/speech-quick`) sağlayıcıya anında gidiyor ve kullanım **Kullanım** tablosuna yazılıyor. **Ses dosyası işleri** (`/editor/speech`) her zamanki iş kuyruğu, bütçe ve geçiş kurallarıyla çalışıyor.
- **AI okuma metni** (sayılar, kısaltmalar, yabancı adlar) bütün sağlayıcılarda kullanılabiliyor. Cümle ve paragraf arası duraklama ile ortak telaffuz sözlüğü yalnız EMA'da var.
- **Geriye uyumluluk:** Sağlayıcı belirtmeyen istekler eskisi gibi EMA'ya gidiyor; eski editör sürümleri aynen çalışıyor.
