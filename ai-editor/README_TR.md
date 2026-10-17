# AGFO AI Editor

Yazdığınız metinlerin **içeriğini** yapay zekâyla düzenleyen Windows metin editörü. Biçimlendirme aracı değildir;
odak noktası anlatım, mantık akışı, netlik, doğruluk ve tondur.

## Kurulum
GitHub Releases'ten `AGFO-AI-Editor.exe` dosyasını indirip çalıştırın. İlk açılışta "bu bilgisayara kurulsun mu?"
diye sorar: kullanıcı klasörünüze (`%LOCALAPPDATA%\Programs\AGFO-AI-Editor`) kopyalanır, Başlat menüsüne ve
masaüstüne kısayol eklenir. Yönetici yetkisi gerekmez. Güncellemeler uygulama içinden tek tıkla gelir
(etiket `ai-editor-v*`, SHA-256 doğrulamalı). EXE kod imzalı değildir; SmartScreen uyarabilir.

## Bağlantı (Ayarlar › Bağlantı)
- **AGFO AI Manager (önerilen):** WordPress sitenizdeki AI Manager 17.4.0+ kullanılır; API anahtarları sitede kalır.
  WordPress › Kullanıcılar › Profil › *Uygulama Parolaları* bölümünden bir parola oluşturup site adresi, kullanıcı adı
  ve bu parolayı girin (yönetici kullanıcı gerekir, bağlantı HTTPS olmalıdır). AI Manager'daki sağlayıcı/model,
  çeviri yönlendirmesi ve sitenize özel içerik şablonları editörde otomatik görünür.
- **Doğrudan sağlayıcı:** OpenAI, Anthropic, Gemini, OpenRouter veya DeepSeek anahtarı. Anahtar Windows DPAPI ile
  yalnız sizin Windows hesabınızda çözülebilecek şekilde saklanır.
- **Otomatik:** önce AI Manager, ulaşılamazsa doğrudan anahtar.

## Özellikler
- Sekmeli belgeler; `.txt`, `.md`, `.docx`, `.html` açma/kaydetme (kodlama ve satır sonu korunur; Türkçe ANSI
  dosyalar tanınır). DOCX metin olarak açılır; tablo/resim içeren belgede üzerine yazmadan önce uyarır.
- Bul/değiştir, sınırsız geri al, otomatik kurtarma (kapanırsa kaydedilmemiş metin geri gelir), son dosyalar.
- **İçerik:** İçeriği güçlendir, Akışı ve yapıyı düzelt, Argümanı netleştir, Düzelt ve cilala, Kısalt, Geliştir,
  Sadeleştir, Özetle, ton dönüşümleri, SEO/LinkedIn, Devamını yaz, Eleştirel okuma, Başlık önerileri, Özel talimat
  ve AI Manager'daki sitenize özel şablonlar. Seçim yoksa imlecin bulunduğu paragraf işlenir.
- Sonuç **fark görünümünde** (silinen/eklenen kelimeler) gösterilir; düzenleyip onaylarsınız. Ctrl+Z ile geri alınır.
- **Çeviri** (yerine koy / altına ekle / yeni sekme), **Sohbet** (belge bağlamlı), **Denetim** (BRCGS/IFS/FSSC/ISO:
  uygunsuzluk bulgusu, uygunluk ifadesi, DÖF ve kök neden değerlendirmesi, yönetici özeti). Kayıt no, tarih, ölçüm
  veya madde metni uydurulmaz.

Kısayollar: Ctrl+N/O/S, Ctrl+Shift+S, Ctrl+W, Ctrl+F, Ctrl+H, F3, Ctrl+E (AI ile düzenle), Ctrl+Enter (sohbet).

Veriler: `%LOCALAPPDATA%\AGFO-AI-Editor` (ayarlar, kurtarma kayıtları, hata günlüğü). Metinleriniz yalnızca seçtiğiniz
AI bağlantısına gönderilir.
