## AGFO AI Editor 2.14.1 — Bu bilgisayarda İngilizce ve İspanyolca ses (Qwen3-TTS)

- **Yeni yerel ses:** `AGFO-Ses-Qwen-Kur.cmd` ile kurulan Qwen3-TTS servisi Ses sekmesindeki **Yerel ses** listesinde görünür. Örnek: "Qwen3-TTS (İngilizce, İspanyolca) · Aiden".
- **Dil seçimi kendiliğinden:** Metnin dili (İngilizce ya da İspanyolca) paragraf paragraf seçilir; ikisi aynı belgede bulunabilir.
- **Uzun paragraflar:** Kelime atlamasın diye cümle sınırından bölünerek okunur.
- **▶ Dene:** Bir İngilizce, bir İspanyolca örnek cümle okur.
- **Kendi sesiniz:** İzinli bir kayıt (`ad.wav` + `ad.txt`) `%LOCALAPPDATA%\AGFO\TTS-QWEN\data\voices` klasörüne konunca listeye eklenir. İspanyolcayı anadil gibi okuyan bir ses için İspanyolca bir kayıt önerilir.
- **Sınırlar:** Qwen3-TTS'te Türkçe ve Arapça yok; bu diller için EMA Lightning ve SILMA/Habibi kullanılır. AI okuma metni ve telaffuz sözlüğü yalnız Türkçe seste çalışır.
