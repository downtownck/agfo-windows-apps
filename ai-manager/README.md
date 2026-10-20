# AGFO AI Manager

AGFO ekosisteminin merkezi AI sağlayıcı, model, yetenek, iş kuyruğu, medya ve maliyet yönetim katmanıdır.

**Version:** 17.13.0  
**Requires WordPress:** 6.0+  
**Requires PHP:** 7.4+


## 17.13.0 — Sesli oku ucu

AI Editor 1.6.0'ın "Sesli oku" özelliği için `POST /editor/speech-quick`: en çok 4.000 karakterlik bir paragrafı iş kuyruğuna girmeden, istek içinde EMA ile MP3'e çevirir ve `audio_base64`, `seconds`, `script` döndürür. Sunucu sözlüğü uygulanır; `reading_script` açıksa okuma metni hazırlanır (30 günlük önbellek sayesinde tekrar okumada model çağrılmaz); `script_ready` hazır okuma metnini sözlüksüz okur. `/editor/info` speech özetinde `quick` ve `quick_max_chars` vardır.

## 17.12.0 — AI Editor seslendirme uçları

AGFO AI Editor 1.5.0'ın "Ses" sekmesi için REST uçları (aynı bağlantı anahtarı / uygulama parolası): `POST /editor/speech` EMA işi başlatır (okuma metni seçeneği, önizlenmiş metin, hız, duraklamalar), `GET /editor/speech/{iş}` durumu ve okuma metni özetini, `GET /editor/speech/{iş}/audio` MP3'ü akıtır; `POST /editor/speech-script` okuma metnini önizler; `GET/POST /editor/lexicon` ortak sözlüğü listeler ve değiştirir (değiştirmek için manage_options), `POST /editor/lexicon/listen` okunuşu örnek MP3 olarak döndürür. `/editor/info` yanıtında `speech` özeti vardır. Düzeltme: iş verisinde PHP `false` olarak gelen reading_script artık "kapalı" sayılır (önceden site varsayılanına düşüyordu).

## 17.11.0 — Telaffuz Sözlüğü (WordPress → sunucu)

AGFO AI › Telaffuz Sözlüğü sayfası, Hetzner'deki AGFO TTS Service'in ortak sözlüğünü yönetir: arama ve süzme (tümü / eklenen-değiştirilen / kaldırılan / hazır), kelime ekleme, satırda okunuş değiştirme, kaldırma, hazır okunuşa dönme ve "Dinle" ile okunuşu EMA'nın sesiyle hemen duyma. Kayıtlar sunucuda data/lexicon.custom.json dosyasına yazılır; bütün sitelerde ve okuma metni adımında hemen geçerlidir, servis güncellemesi (update.sh) bu dosyaya dokunmaz. Hazır gelen bir kelime kaldırıldığında maskelenir; güncelleme onu geri getirmez. Siteye özel okunuşlar Ses Stüdyosu'ndaki alanda kalır. AGFO TTS Service 1.1.0 gerekir.

## 17.10.0 — EMA okuma metni (AI ile)

EMA Lightning yalnız Türkçe okur; rakam, sembol ve yabancı adları harf harf okur. 17.10.0'da EMA işi seslendirilmeden önce metin üç adımdan geçer: (1) sunucu telaffuz sözlüğü tek geçişte uygulanır, (2) sitenin metin modeli metni "okuma metni"ne çevirir — yabancı adlar Türkçe okunuşla, sayılar, tarihler, saatler, yüzdeler, birimler, para, semboller, internet adresleri ve kısaltmalar sözcükle yazılır; geri kalan her kelime aynen kalır, (3) sonuç sözlük yeniden uygulanmadan seslendirilir.

Metin paragraf sınırlarında en çok 2.800 karakterlik bölümlere ayrılır. Her bölümün yanıtı denetlenir: satır sayısı aynı olmalı, uzunluk oranı makul olmalı, kaynaktaki Türkçe kelimelerin en az %85'i korunmalı, yanıt kesilmemiş olmalı. Denetimden geçmeyen bölüm özgün haliyle okunur; model hiçbir cümleyi atamaz, ekleyemez ya da çeviremez. Yanıtlar bölüm başına 30 gün önbellekte tutulur.

Ses Stüdyosu ve klasik editörde "Okuma metnini AI ile hazırla" seçeneği (varsayılan açık), "Okuma metnini önizle" ve "Özgün metne dön" düğmeleri vardır; önizlenen metin elle düzeltilip aynen seslendirilebilir. Okuma metni modeli EMA servis ayarlarından seçilir (boşsa sitenin varsayılan metin modeli). AGFO TTS Service 1.0.8 gerekir (/lexicon/apply ve apply_lexicon); eski serviste sözlük yine seslendirme sırasında uygulanır.

## 17.9.1 — EMA seçeneği editörde her zaman görünür

Klasik editördeki "Sayfayı Seslendir" penceresi yalnız anahtarı kayıtlı sağlayıcıları listelediği için token girilmemiş sitelerde EMA hiç görünmüyordu. Artık "EMA Lightning (yerel, Türkçe) — token gerekli" olarak listelenir; seçildiğinde token'ın Sağlayıcılar ekranında nereye girileceği gösterilir ve "Sesi Üret" kapalı kalır.

## 17.9.0 — EMA Lightning (yerel Türkçe TTS) sağlayıcısı

Sunucuda çalışan AGFO TTS Service (EMA Lightning, Apache-2.0) yeni bir konuşma sağlayıcısı olarak eklendi. Sağlayıcılar ekranındaki "EMA Lightning (yerel TTS)" alanına servis token'ı girilir (ya da wp-config.php içinde AGFO_TTS_TOKEN); servis adresi, telaffuz sözlüğü ve duraklamalar Ses Stüdyosu › EMA servis ayarlarından yönetilir. Karakter ücreti yoktur, tek işte 60.000 karaktere kadar metin kabul edilir, hız 0.7–1.4 aralığındadır. Otomatik yönlendirmede Türkçe olmayan metin EMA tarafından reddedilir ve iş sonraki sağlayıcıya geçer.

## 17.8.0 — AI Editor'de iş başına çeviri modeli

AI Editor için iş başına çeviri modeli: yeni GET /editor/models uç noktası, sitede anahtarı olan sağlayıcıların çeviriye uygun modellerini kalite, tahmini maliyet ve hız sınıfıyla (hızlı/dengeli/yavaş-düşünen) listeler; /editor/transform isteğe bağlı model="sağlayıcı|model" alır ve yalnız çeviri şablonlarında, yalnız anahtarı olan sağlayıcıların listedeki modellerini kabul eder. Seçilen model çalışmazsa varsayılan modele düşülür; bu durum sitenin Çeviri rotası hatası olarak kaydedilmez.

## 17.7.0 — Çeviri düzeltmeleri

Çeviri düzeltmeleri: AI Kontrol Merkezi › Çeviri rotası sağlayıcının sunmadığı bir modele (ör. Together AI 'non-serverless' DeepSeek-R1-Distill-Qwen-7B) ayarlıysa çeviriler artık 400 hatasıyla durmaz; bir kez varsayılan metin modeliyle yeniden denenir, yanıt route_fallback/route_error ile bildirilir ve Çeviri panelinde uyarı gösterilir. Reasoning modellerinin <think> blokları temizlenir. AI Editor için Markdown kipi (/editor/transform format=markdown): kaynak Markdown olarak gider, sonuç Markdown döner; tablolar, altı çizili, H1, satır yapısı ve ⟦n⟧ parça işaretleri artık HTML temizleyicide kaybolmaz.

## 17.6.0 — Kaynaklardan uzun içerik üretimi

AI Editor 1.2 'Kaynaklar' için: /editor/chat isteğe bağlı max_output_tokens (256–8000) kabul eder; uzun içerik üretiminde (makale, eğitim notu, kontrol listesi) çıktı 2400 belirteçte kesilmez, zaman aşımı 180 sn olur.

## 17.5.0 — AI Editor bağlantı anahtarı

AI Editor bağlantı anahtarı: AI Manager › AI Editor bağlantısı sayfasından tek tıkla anahtar oluşturulur, editöre yapıştırılır (X-AGFO-Editor-Token). Uygulama Parolası gerekmez; Authorization başlığını düşüren sunucularda ve Uygulama Parolalarını kapatan güvenlik eklentilerinde de çalışır. Anahtarlar kullanıcıya bağlı, yalnız HMAC olarak saklanır, tek tek silinebilir ve yalnız /agfo-ai/v1/editor/* uçlarında geçerlidir. Yeni /editor/ping ucu bağlantı tanısı için yalnız sürüm ve evet/hayır bilgileri döndürür.

## 17.4.1 — AI Editor kimlik doğrulama düzeltmesi

AI Editor bağlantısında 401 düzeltmesi: bazı LiteSpeed/CGI sunucuları Authorization başlığını PHP'ye iletmediği için Uygulama Parolası hiç denetlenmiyordu. Editör aynı kimlik bilgisini X-AGFO-Editor-Auth başlığıyla da gönderir; yalnızca /agfo-ai/v1/editor/* için ve WordPress'in kendi Uygulama Parolası doğrulamasıyla kabul edilir. 401 yanıtları artık WordPress'in gerçek nedenini (incorrect_password, invalid_username, application_passwords_disabled) ve kimlik bilgisinin sunucuya ulaşıp ulaşmadığını bildirir.

## 17.4.0 — AGFO AI Editor API ve GitHub güncellemesi

- Windows masaüstü **AGFO AI Editor** için REST uçları: `GET agfo-ai/v1/editor/info`, `POST agfo-ai/v1/editor/transform`, `POST agfo-ai/v1/editor/chat`. Kimlik doğrulama WordPress Uygulama Parolası (HTTPS); Content Studio yetkisi gerekir (varsayılan `manage_options`). API anahtarları sunucudan çıkmaz.
- Eklenti güncellemeleri GitHub Releases'ten (`ai-manager-vX.Y.Z`); paket kurulmadan önce SHA-256 ile doğrulanır, `data/data.json` güncellemede korunur. Kapatmak için `agfo_aim_github_updates` = 0.

## 17.3.3 — Spekülatif riskler

- Kendi doğrulanamadığını söyleyen risk atılır.
- AJAX/admin-post kayıt satırındaki "kontrol yok" iddiası callback fonksiyonunun gövdesine göre değerlendirilir.
- Çürütme bağlamı çevreleyen fonksiyonun sonunda biter.

## 17.3.2 — İnceleme kalitesi

- Her Code Health bulgusu için zorunlu yanıt (F1…Fn anahtarlı strict şema); sağlayıcı reddederse liste şemasına bir kez geri dönülür.
- "Kontrol yok" iddiasını yalnız gerçek `current_user_can()` / `user_can()` ya da core nonce çağrısı (veya bunu çağıran sarmalayıcı) çürütür.
- `source_root` sınırı dizin ayırıcısıyla denetlenir.

## 17.3.1 — AI inceleme bulgularının düzeltilmesi

- Kod incelemesi, kodun kendisinin çürüttüğü "nonce / yetki kontrolü yok" iddialarını atar; payload'daki `source_root` ile bağlam kurulu dosyadan okunur.
- `agfo_ai_content_translation_templates` filtresi tip güvenli.
- Ön yüzde AI Kontrol Merkezi yalnız yönetici çubuğu görünürken yüklenir (`agfo_aim_frontend_control_center` filtresi).
- Test: `php tests/admin-guard-tests.php`.

## 17.3.0 — Editörde tek tıkla çeviri

- Klasik editörde "AI Düzenle"nin yanında **Çevir** butonu ve hedef dil listesi. Seçili metni (seçim yoksa tüm içeriği) çevirir; sonuç İçerik Stüdyosu'nda "Editörde Değiştir" / "Altına Ekle" ile uygulanır.
- "Çevir ve düzelt" şablonu AI Kontrol Merkezi → Çeviri sekmesinde / Yetenek Yönlendirme'de seçilen modeli kullanır; seçim yoksa varsayılan metin modeli.
- Çeviri çıktı payı kaynakla ölçeklenir (1200–8000 token), zaman aşımı 120 sn; kesilen sonuç uyarılır.
- Filtreler: `agfo_ai_content_languages`, `agfo_ai_content_translation_templates`.
- Test: `php tests/content-translate-tests.php` (16 assertion).

## 17.2.0 — AI kod inceleme servisi

- `agfo_ai_code_review( $payload, [ 'mode' => 'quick'|'deep' ] )`: bulguları gerçek sorun / gerekçeli / yanlış alarm olarak sınıflandırır, satır farklarındaki riskleri raporlar. Kanıtı (dosya:satır) gösterilemeyen risk atılır; hüküm doğrulanmış içerikten hesaplanır.
- Yönlendirme: "Kod inceleme (hızlı)" boşsa gpt-4.1-mini, "Kod inceleme (derin)" boşsa varsayılan chat modeli.
- Test: `php tests/code-review-tests.php` (16 assertion).

## 17.1.0 — En yeni model üstte, Çeviri ve Görsel panoları

- Model listeleri varsayılan olarak en yeni model üstte: sağlayıcının yayın tarihi, id içindeki tarih, yoksa sürüm ailesi (gpt-5.7 > gpt-5.6, gpt-5.10 > gpt-5.9). "Yeni" rozeti.
- "Güncelle" artık yayın tarihlerini ve OpenRouter/Together fiyatlarını da kaydeder (`agfo_models_{sağlayıcı}_meta`).
- Çeviri sekmesi: benchmark kalitesi ile 1.000 kelime maliyeti karşılaştırması, üç öneri, tek tıkla çeviri modeli. Eklentiler `agfo_get_translation_config()` ile alır.
- Görsel üretimi sekmesi: kalite notu, güçlü yanlar, görsel başı fiyat (satırda düzenlenebilir), Görsel Stüdyosu varsayılanını atama.
- Test: `php tests/model-catalog-tests.php` (21 assertion).

## 17.0.0 — Merkezi istek koruması ve yeni AI Kontrol Merkezi

- `AGFO_AIM_Request_Guard` sitedeki her AI chat isteğini (agfo_api_post veya doğrudan wp_remote_post) gönderimden önce temizler, ret yanıtından öğrenir ve aynı isteği bir kez onarır.
- OpenAI'de temperature varsayılan olarak kapalı: yalnız GPT-4/GPT-3.5 aileleri ve canlı testte destek kanıtlanan modeller alır. Yeni aileler ilk günden korunur.
- Responses-only OpenAI modelleri (pro, codex, deep-research) chat gövdesiyle çağrılsa da `/v1/responses` üzerinden çalışır; yanıt chat.completion biçiminde döner.
- Erişilemeyen veya chat dışı model, aynı sağlayıcının çalışan bir modeline yönlendirilir (kapatılabilir).
- Uyumluluk testi reasoning modellerinde yanlış "chat ✗" üretmez; eski yanlış kayıtlar okuma anında düzeltilir.
- AI Kontrol Merkezi: sütunlu model tablosu, uyum rozetleri, 16 px checkbox'lar, sabit kaydet çubuğu, klavye gezinmesi, koruma paneli.
- Test: `php tests/request-guard-tests.php` (42 assertion).

## 16.17.7 — GPT-5 temperature koruması sertleştirmesi

- GPT-5 ve o-serisi için `supports_temperature=false` artık yalnız priority config'te değil, `agfo_get_model_capabilities()` ve `agfo_model_supports_temperature()` yüzeylerinde de efektif sözleşmedir. Tarihsel başarılı probe kaydı bu kuralı ezemez.
- Merkezi `agfo_api_post()` korumasına ek olarak, OpenAI/OpenRouter `chat/completions` uçlarına doğrudan `wp_remote_post()` yapan legacy AGFO kodları da dar kapsamlı WordPress HTTP filtresinde korunur. GPT-5/o-serisi gövdelerindeki unsupported sampling alanları sağlayıcıya çıkmadan temizlenir.
- Model Intelligence'ın gerçek temperature probe çağrıları `X-AGFO-Temperature-Probe` başlığıyla bu filtreden muaf tutulur; böylece capability ölçümü sahte biçimde başarılı görünmez.
- `gpt-4o` ve temperature destekleyen diğer modellerin davranışı değişmez. Veri tabanı migration'ı yoktur.

## 16.17.4 — AGFO Academy eğitim bağlamı

- İçerik Stüdyosuna **AGFO Academy / Eğitim** işlemi eklendi.
- Bu işlem yalnız kaynak editör metnine bakmaz; mevcut post/page için kayıtlı **başlık, post type, taksonomiler ve güvenli custom field/meta değerlerini** ikinci kaynak olarak modele verir.
- Süre, fiyat, eğitmen, eğitim sağlayıcısı, yöntem, tarih, sınav, sertifika, dil veya ön koşul gibi değerler bağlamda mevcutsa model bunları gerçek kurs bilgisi olarak kullanır ve bunların yerine “sağlayıcıya göre değişebilir” türü jenerik ifadeler üretmez.
- Parola, token, nonce, API/auth/session verileri, özel toplantı/portal bağlantıları, telefon/e-posta ve büyük builder metadata alanları model bağlamından çıkarılır.
- Kısa eğitim brieflerinde sonuç gerçek bir eğitim sayfası açıklamasına genişleyebilir; ancak akreditasyon, tanınırlık, sınav/sertifika hakkı ve standardın yeni sürümüne özgü hükümler kaynak veya sayfa bağlamında yoksa uydurulmaz.
- Sonuç metasında bağlam kullanımı **`sayfa bağlamı: X meta`** olarak görünür. Kaydedilmemiş özel alan değişiklikleri için önce WordPress yazısını güncellemek gerekir; editördeki güncel başlık ayrıca gönderilir.

## 16.17.2 — İçerik Stüdyosu ve temperature uyumluluk düzeltmesi

- Classic Editor **AI Düzenle** akışında yeni model `temperature` parametresini reddettiğinde dönüşümün HTTP 400 ile kesilmesine karşı merkezî koruma güçlendirildi.
- GPT-5 ailesi ve o-serisi için bağımlı eklentiler `temperature` göndermeye devam edebilir; `agfo_api_post()` bu sampling alanlarını sağlayıcıya iletmeden temizler. Eski `supported` probe kaydı artık bu güvenli kuralı geçersiz kılamaz.
- Henüz tanınmayan bir chat modeli açık bir `temperature unsupported/not supported` yanıtı verirse taşıma katmanı isteği temperature olmadan yalnız bir kez tekrarlar.
- `agfo_get_priority_api_key()` modern OpenAI/OpenRouter modellerinde `supports_temperature=false` raporlar; böylece bağımlı eklentiler gövdeyi kurarken parametreyi baştan atlayabilir.
- İçerik Stüdyosu provider capability bilgisini gövde üretiminde uygular. TinyMCE üzerinde **Editörde Değiştir** veya **Altına Ekle** sonrasında `editor.save()` ve WordPress `input/change` olayları tetiklenir; görünür editör ile temel `textarea` aynı anda güncel kalır.
- Veri tabanı migration'ı yoktur; mevcut public fonksiyonlar, AJAX action adları, option keyleri ve provider sözleşmeleri korunmuştur.

## 16.17.1 — Global class çakışma düzeltmesi

- Genel `AGFO_Admin`, `AGFO_Ajax_Data` ve `AGFO_Encryptor` class adları plugin-özel `AGFO_AIM_*` adlarına taşındı; eski adlar yalnız boşta olduklarında alias olarak korunur.

## 16.17.0 — Sekmeli AI Kontrol Merkezi

Quick Switch modalı daha sade ve işlevsel bir çalışma alanına dönüştürüldü.

- Eski sağ kolondaki **Hız Dağılımı**, **Benchmark**, **Kayıtlı Modeller** ve **Aktif Ayarlar** kartları ayrı modal sekmelerine taşındı; ana model listesi artık sağ panel tarafından daraltılmıyor.
- Yeni sekme yapısı klavye ok tuşlarıyla gezilebilir, son açık sekmeyi oturum boyunca hatırlar ve küçük ekranlarda tek kolonlu düzene düşer.
- Benchmark sekmesi mevcut `agfo_get_model_score` AJAX ucunu gerçekten kullanır; model seçildiğinde birleşik skor ve kaynak kırılımı yüklenir. Kaynak benchmark yoksa dropdown içindeki AGFO sıralama puanı güvenli fallback olarak gösterilir.
- `agfo_get_model_score` isteğine mevcut admin nonce kontrolü eklendi; capability kontrolü korunur.
- Hız görünümü artık mümkün olduğunda Model Intelligence `speed_score` verisini kullanır. Önceki sürekli `0` gösteren Blacklist kutusu, gerçek `supports_chat` / `compatibility_level` verisinden hesaplanan **Uyumsuz** sayısına dönüştürüldü.
- Kayıtlı Modeller sekmesi tam liste, arama, toplu kopyalama ve tek tıkla modele geçiş sunar.
- Aktif Ayarlar sekmesi kaydedilmiş durum ile modalda hazırlanan seçimi yan yana gösterir ve kaydedilmemiş değişiklikleri işaretler.
- Veri tabanı migration'ı yoktur; mevcut public API, option key, AJAX action adları ve `data/data.json` sözleşmeleri korunur.

## 16.16.2 düzeltmesi

Merkezî token alanı normalizasyonu artık tutarlı biçimde raporlanıyor.

- `agfo_get_priority_api_key()`, `uses_max_completion_tokens` alanını OpenRouter ve MiniMax chat için de `true` döndürür. `agfo_api_post()` dönüşümü zaten bu iki sağlayıcı için yapıyordu; alan yalnız `openai` için hesaplandığından, alanı okuyup gövdeyi elle kuran bağımlı eklentiler OpenRouter'da yanlış alan adı gönderebiliyordu.
- Çift dönüşüm oluşmaz: OpenRouter bloğu yalnız `max_tokens` varken çalışır, MiniMax bloğu mevcut `max_completion_tokens` değerini yalnız model tavanına kırpar.
- `agfo_uses_max_completion_tokens()` içindeki legacy tespiti, kısa desenlerde kelime sınırı kontrolü uygular. Önceden `ada` alt-dize olarak arandığı için, içinde tesadüfen bu harf dizisi geçen bir model adı legacy sayılıp `max_tokens` alanında bırakılabiliyordu.
- Eklenti kökünde bağlayıcı entegrasyon spesifikasyonu korunur ve 16.16.2 davranışıyla güncellenmiştir: `AGFO-AI-MANAGER-SPEC.md`.
- Veri tabanı migration'ı yoktur; public API imzaları, AJAX action adları, option anahtarları ve `data/data.json` sözleşmeleri korunur.

## 16.16.1 düzeltmesi

Görsel Stüdyosu modalı çağrılmadan ekranda kalıyor ve kapatılamıyordu. Modal ile overlay'in `display` kuralları tarayıcının `[hidden]` kuralıyla eşit özgüllükte olduğu için onu eziyordu. Görünürlük artık `.is-open` sınıfıyla sürülür, `[hidden]` koruması `!important` ile garanti altındadır ve sayfa yüklenirken kapalı durum ayrıca zorlanır.

## 16.16.0 — Görsel Stüdyosu

- Klasik editör araç çubuğuna ve **Öne Çıkan Görsel** kutusuna **AI Görsel** düğmesi eklendi.
- Yeni `image_generate` yeteneği: OpenAI (gpt-image-2 / gpt-image-1 / DALL·E 3), OpenRouter (`openai/gpt-5.4-image-2`, `google/flash-image-2.5`), Gemini (Imagen 4/3, Gemini Flash Image), fal.ai (FLUX, Recraft) ve MiniMax desteklenir. Model alanı serbest metindir; listedeki kimlikler yalnızca öneridir.
- Ek prompt alanı boş bırakılırsa görsel, yazının başlığı ve içeriğinden metin modeliyle çıkarılan kısa bir sahne özetinden üretilir. `Konu kaynağı` seçicisiyle yalnızca başlık ya da yalnızca operatör promptu da kullanılabilir.
- Hazır preset promptları: felsefi öne çıkan görsel, şarkı albüm kapağı, tıklanma odaklı kapak, dikey infografik, editoryal makale görseli ve kurumsal/teknik. Tümü **AGFO AI → Görsel Promptları** ekranından düzenlenebilir ve varsayılanlara döndürülebilir.
- Her çağrıda zorunlu kurallar uygulanır: dini sembol ve ibadet mekânı yok, kimliklendirilebilir özel kişi yok, marka/filigran yok, ölçülü kıyafet, yayına hazır kompozisyon.
- Üretilen görsel medya kütüphanesine yazılır (`_agfo_ai_generated`, `_agfo_ai_image_prompt` meta ile) ve tek tıkla öne çıkan görsel yapılabilir. Görsel MIME'i dosya imzasından doğrulanır; beyaz liste dışı içerik yazılmaz.
- fal.ai kuyruk polling'i mevcut merkezi `agfo_async_poll_result()` üzerinden çalışır; yeni bir taşıma katmanı eklenmemiştir.
- `agfo_get_provider_for_capability()` artık opsiyonel `provider` argümanını kabul eder. Geçirilmediğinde davranış birebir eskisi gibidir.

## 16.15.1 düzeltmesi

Classic Editor footer hook sıralamasında modal HTML'si JavaScript'ten sonra oluşabildiği için doğrudan bağlanan olaylar çalışmıyordu. `Yeniden Yaz` düğmesi artık parent post formunu submit edemeyen `type=button` kullanır; tüm modal eylemleri gecikmeli DOM üretimine dayanıklı delegated event binding ile çalışır.

## 16.15.0 özeti

- Bağımsız **AGFO AI Suite** işlevleri AGFO AI Manager içine **İçerik Stüdyosu** olarak alındı.
- Klasik editörde **AI Düzenle** ve mevcut **Seslendir** araçları birlikte çalışır; yeniden yazılan sonuç tek tıkla TTS modalına aktarılabilir.
- Seçili metin veya tüm içerik; akıcı yeniden yazma, düzeltme, kısaltma, özet, geliştirme, sadeleştirme, profesyonel, akademik, teknik/denetim, SEO, LinkedIn, çeviri ve yaratıcı anlatım şablonlarıyla işlenebilir.
- Promptlar isim, tarih, sayı, standart, teknik terim ve iddiaları korumayı; kaynakta bulunmayan gerçek, kayıt, kanıt, atıf veya ölçüm uydurmamayı zorunlu kılar.
- Hedef dil, okuyucu, ton, uzunluk ve ek talimat ayrı alanlara taşındı. Sonuç editörde değiştirilebilir, seçili bölgenin yerine uygulanabilir, alta eklenebilir, kopyalanabilir ve geri alınabilir.
- Yeni **AGFO AI → İçerik Promptları** ekranında şablonlar özelleştirilebilir ve varsayılanlara döndürülebilir.
- Eski `agfo_suite_prompts` seçeneğindeki gerçekten özelleştirilmiş promptlar bir kez içe aktarılır; eski varsayılanlar modern promptları ezmez.
- Eski `agfo_suite_*` AJAX sözleşmeleri ve `agfo_ai_suite_ajax_info()` bağımsız AI Suite kapalıyken geriye uyumlu alias olarak korunur.
- Metin çağrıları doğrudan provider endpointlerine gitmez; mevcut `agfo_get_priority_api_key()` ve `agfo_api_post()` taşıma katmanını kullanır.
- Veri tabanı migration'ı yoktur; mevcut TTS, reverb/echo, müzik, job, asset, bütçe ve model yönetimi korunur.

## 16.14.0 özeti

- Klasik editördeki **Seslendir** modalına kalıcı `Reverb / Echo` post-processing eklendi.
- Presetler: efektsiz/kuru, hafif sıcak oda reverbü, yumuşak echo ve belirgin salon reverbü.
- Etki miktarı yüzde 0–100 aralığında seçilir; işlem gerçek zamanlı değildir, tamamlanan ses dosyasına FFmpeg ile uygulanır.
- Music Studio tarafından web kökü dışına kurulan yönetimli FFmpeg otomatik algılanır; ayrıca `AGFO_AIM_FFMPEG_PATH` ve sistem yolları desteklenir.
- Efektli çıktı güvenli biçimde MP3/192 kbps olarak özel asset deposuna ve isteğe bağlı Medya Kütüphanesine yazılır.
- FFmpeg kullanılamıyorsa istek sağlayıcıya gönderilmeden önce durdurulur; gereksiz TTS maliyeti oluşmaz.
- Efekt işleme sağlayıcı çağrısından sonra başarısız olursa aynı ücretli TTS isteği otomatik tekrar edilmez ve gerçek kullanım maliyeti kaydedilir.

## 16.13.0 özeti

- Sağlayıcı bağımsız `music_generate` yeteneği ve `agfo_music_generate()` public facade eklendi.
- ElevenLabs Music `/v1/music`, MiniMax Music 2.6 `/v1/music_generation` ve Google Gemini API Lyria 3 `/v1beta/interactions` adaptörleri eklendi.
- Müzik işleri mevcut kalıcı job kuyruğu, atomik bütçe rezervasyonu, kill switch, kullanım muhasebesi ve web root dışı private asset store üzerinden çalışır.
- MiniMax için ilk güvenli test modeli `music-2.6-free` seçilir; ücretli `music-2.6` Token Plan veya Credits gerektirebilir.
- Gemini Lyria 3 Clip ve Pro desteklenir. İlk sürümde yanlış MIME/uzantı riskini kaldırmak için yalnız doğrulanmış MP3 çıktı yolu açılmıştır.
- ElevenLabs model başına 3–600 saniye, MiniMax prompt/lyrics sınırları ve Gemini model/format sınırları adaptör içinde doğrulanır.
- Google Flow adıyla bir endpoint kullanılmaz; resmi müzik API ürünü Gemini API içindeki Lyria 3'tür.
- Veri tabanı migration'ı yoktur; mevcut public API, AJAX, TTS, chat, option key ve `data/data.json` sözleşmeleri korunur.

## 16.11.0 özeti

- MiniMax doğrudan sağlayıcı olarak eklendi; aynı şifreli API anahtarı chat ve `speech_synthesize` yeteneklerinde sunucu tarafında kullanılır.
- Chat istekleri MiniMax'in OpenAI uyumlu `/v1/chat/completions` sözleşmesine yönlendirilir; canlı model yenileme `/v1/models` üzerinden çalışır ve güncel fallback `MiniMax-M3` ile M2.x ailesini içerir. Eski `max_tokens` kullanan bağımlı plugin gövdeleri merkezde `max_completion_tokens` alanına dönüştürülür; model bazlı token ve sampling sınırları uygulanır.
- Senkron MiniMax T2A HTTP desteği eklendi: Speech 2.8, 2.6, 02 ve 01 HD/Turbo modelleri, hesap sesleri, Türkçe dil güçlendirme, hız, ses düzeyi, perde, duygu, örnekleme hızı, bitrate ve kanal ayarları.
- MiniMax hesabındaki sistem, klonlanmış ve tasarlanmış sesler `/v1/get_voice` ile sunucu tarafında okunur; arayüze API anahtarı aktarılmaz.
- Ses Stüdyosu ve Klasik Editör modalında MiniMax model/ses dropdownları, arama ve zorunlu yenileme düğmesi eklendi.
- MiniMax TTS maliyet tahmini ve sağlayıcı bütçe tavanı eklendi. Varsayılan snapshot HD için 0.10 USD/1000 karakter, Turbo için 0.06 USD/1000 karakterdir; yönetici değerleri geçersiz kılabilir.
- Video yetenekleri bu sürümün kapsamına alınmadı. Veri tabanı migration'ı gerekmez; mevcut public API, AJAX action, option key ve `data/data.json` sözleşmeleri korunur.
- Kaynak kod, JSON, JavaScript ve mock HTTP testleri yapılmıştır; gerçek MiniMax anahtarıyla WordPress staging testi yapılmadan bu entegrasyon runtime doğrulanmış sayılmaz.

## 16.10.2 düzeltmesi

- Önceki iki sürümün yalnız ekran tespiti ve JavaScript DOM varsayımlarına dayanması nedeniyle düğmenin gerçek kurulumda görünmemesi kabul edildi ve bu bağımlılık kaldırıldı.
- Tüm `post.php` ve `post-new.php` yönetim ekranlarında, yetkili kullanıcı için TTS assetleri doğrudan yüklenir; `get_current_screen()`, post type veya editör modu sonucu artık yüklemeyi engellemez.
- Klasik formun `edit_form_after_title` hook'unda sunucu tarafından **her zaman görünür bir AGFO Seslendirme başlatıcısı** oluşturulur.
- Medya düğme satırı mevcutsa araç çubuğu düğmesi kullanılır ve üst başlatıcı gizlenir; satır yoksa üst başlatıcı görünür kalır.
- Modal, ElevenLabs/OpenAI katalogları, iş kuyruğu, maliyet, medya ve public API sözleşmeleri değişmedi; migration gerekmez.

## 16.10.1 düzeltmesi

- Klasik Sayfa editöründeki **Seslendir** düğmesinin görünürlüğü artık `admin_enqueue_scripts` sırasında oluşturulan geçici bir bayrağa bağlı değildir.
- `use_block_editor_for_post()` sonucunun klasik editör arayüzünü yanlışlıkla elemesini önlemek için asset ve modal yükleme kontrolü desteklenen Sayfa düzenleme ekranına bağlandı.
- WordPress `media_buttons` hook'u temada veya editör eklentisinde çalıştırılmazsa JavaScript, klasik editör DOM'unu algılayıp düğmeyi **Medya Ekle** satırına ekler.
- Medya düğme satırı bulunamazsa düğme editörün hemen üstünde güvenli bir yedek konumda gösterilir.
- Modal, iş kuyruğu, ElevenLabs/OpenAI katalogları, maliyet ve medya sözleşmeleri değişmedi; migration gerekmez.

## 16.10.0 özeti

- Klasik WordPress Sayfa editörüne **Seslendir** düğmesi ve modal TTS akışı eklendi.
- Seçili metin veya tüm sayfa içeriği OpenAI/ElevenLabs ile üretilebilir, dinlenebilir ve Medya Kütüphanesi URL'siyle editöre eklenebilir.
- Özel nonce URL'leri sayfa içeriğine yazılmaz; kalıcı ekleme yalnız attachment URL oluştuğunda yapılır.

## 16.9.0 özeti

- Ses Stüdyosu'ndaki serbest metin model ve Voice ID alanları sağlayıcıya duyarlı dropdownlara dönüştürüldü.
- OpenAI Speech API için desteklenen TTS modelleri ve 13 yerleşik ses hazır olarak listelenir.
- ElevenLabs anahtarı tanımlandığında `/v1/models` içinden yalnız TTS modelleri, `/v2/voices` üzerinden hesaba açık sesler sayfalanarak yüklenir.
- ElevenLabs listesi 15 dakika güvenli transient cache kullanır; **Listeyi yenile** düğmesi zorunlu tazeleme yapar.
- Sesler ad, kategori, dil, aksan ve diğer etiketlerle aranabilir; ekranda ad görünür, sağlayıcıya Voice ID gönderilir.
- Otomatik yönlendirmede OpenAI ve ElevenLabs için ayrı model seçimleri `provider_models` rota sözleşmesiyle korunur.
- TTS-1/TTS-1 HD ile uyumsuz OpenAI sesleri arayüzde gizlenir ve adaptör tarafında da reddedilir.
- ElevenLabs dil, stability, similarity boost, style ve speaker boost ayarları isteğe bağlı olarak eklendi; boş alanlar sesin kayıtlı varsayılanını kullanır.
- Veri tabanı migration'ı yoktur; mevcut public fonksiyon ve AJAX sözleşmeleri korunur.

## 16.8.2 düzeltmesi

- AJAX ile dönen TTS oynatma ve indirme bağlantılarında nonce parametresinin kaybolmasına neden olan HTML entity sorunu giderildi.
- `agfo_asset_url()` artık ham sorgu dizesi üretir; HTML içinde kullanan mevcut ekranlar URL'yi `esc_url()` ile güvenli biçimde yazdırmaya devam eder.
- İş kuyruğu, veritabanı şeması, ACL modeli ve public fonksiyon imzaları değişmedi.

## 16.8.1 düzeltmesi

- WP-Cron sırasında WordPress admin dosya yardımcıları otomatik yüklenmediğinde oluşan `Call to undefined function wp_tempnam()` fatal hatası giderildi.
- OpenAI ve ElevenLabs TTS adaptörleri `wp-admin/includes/file.php` dosyasını yalnız gerektiğinde yükler.
- İş kuyruğu, veritabanı şeması, public API ve sağlayıcı sözleşmeleri değişmedi.

## 16.8.0 özeti

Bu sürüm video üretimini erteler ve daha hafif, doğrulanabilir bir çekirdeğe odaklanır:

- `speech_synthesize` metinden sese yeteneği
- OpenAI, ElevenLabs ve MiniMax TTS adapterleri
- DB tabanlı kalıcı iş kuyruğu
- Atomik iş sahiplenme, retry/backoff ve kontrollü sağlayıcı fallback'i
- Sağlayıcı, yetenek ve kaynak plugin bazlı bütçe tavanları
- Tahmini maliyetin çağrıdan önce atomik rezervasyonu
- Web root dışındaki özel ses deposu
- Nonce, capability ve sahiplik kontrollü ses akışı
- Retention temizliği ve zorunlu provenance
- Ses Stüdyosu, İşler, Maliyet ve Geliştirme Takibi ekranları
- Native `tracker.json`, `revision.json` ve sürüm zinciri

Mevcut chat transport'u, public `agfo_*` fonksiyonları, AJAX action adları, option key'leri ve `data/data.json` korunur.

## Kurulum

1. ZIP dosyasını WordPress **Eklentiler > Yeni Ekle > Eklenti Yükle** ekranından kurun.
2. Eklentiyi etkinleştirin. Üç yeni tablo ve cron görevleri idempotent biçimde oluşturulur.
3. **AGFO AI > AGFO AI Manager** ekranında OpenAI, ElevenLabs veya MiniMax API anahtarını kaydedin.
4. **AGFO AI > Maliyet** ekranında bütçe tavanlarını ve geçerli fiyat varsayımlarını girin.
5. **AGFO AI > Ses Stüdyosu** ekranından kısa bir smoke TTS işi çalıştırın.

## Özel depolama

Varsayılan depolama kökü:

```text
{dirname(ABSPATH)}/agfo-ai-store
```

CyberPanel kurulumu `/home/agfo.app/public_html/` ise bu varsayılan genellikle:

```text
/home/agfo.app/agfo-ai-store
```

olur. Farklı bir yol için `wp-config.php` içinde:

```php
define( 'AGFO_AI_STORE_PATH', '/secure/path/agfo-ai-store' );
```

kullanılabilir. Yol web root dışında ve PHP kullanıcısı tarafından yazılabilir olmalıdır.

## TTS kullanımı

### Kolay facade

```php
$result = agfo_speech_synthesize(
    'Bu metin seslendirilecektir.',
    [
        'provider'        => 'openai',
        'model'           => 'gpt-4o-mini-tts',
        'voice'           => 'coral',
        'format'          => 'mp3',
        'speed'           => 1.0,
        'instructions'    => 'Sakin ve olgun bir tonla oku.',
        'retention_days'  => 30,
        'source_plugin'   => 'agfo-poem-translator',
        'created_by'      => get_current_user_id(),
        'idempotency_key' => 'poem-123-tts-v1',
    ]
);

if ( is_wp_error( $result ) ) {
    return $result;
}
```

### Genel job API

```php
$job = agfo_job_submit(
    'speech_synthesize',
    [
        'text'           => 'Merhaba dünya.',
        'voice'          => 'coral',
        'format'         => 'mp3',
        'visibility'     => 'private',
        'retention_days' => 30,
    ],
    [
        'provider'        => 'openai',
        'provider_models' => [
            'openai'     => 'gpt-4o-mini-tts',
            'elevenlabs' => 'eleven_multilingual_v2',
            'minimax'     => 'speech-2.8-hd',
        ],
        'source_plugin'   => 'my-agfo-plugin',
        'created_by'      => get_current_user_id(),
    ]
);
```

İş durumu:

```php
$status = agfo_job_status( $job['job_uuid'], get_current_user_id() );
```

İptal:

```php
agfo_job_cancel( $job['job_uuid'], get_current_user_id() );
```

Tamamlanan işte kontrollü akış URL'leri `asset_url` ve `download_url` alanlarında döner.

## Geriye uyumluluk

Aşağıdaki mevcut sözleşmeler korunur:

- `agfo_get_priority_api_key()`
- `agfo_api_post()`
- `agfo_get_provider_for_capability()`
- `agfo_capability_request()`
- Mevcut `wp_ajax_agfo_*` action adları
- Mevcut option anahtarları
- `data/data.json`
- Eski transient tabanlı `AGFO_AIM_AI_Jobs` sınıfı
- Eski `agfo_ai_store_generated_media()` medya aktarım fonksiyonu

Yeni TTS/job akışı özel depoyu varsayılan kullanır; eski medya fonksiyonunun davranışı bağımlı pluginleri kırmamak için değiştirilmemiştir.

## Mimari

```text
agfo-ai-manager/
├── agfo-ai-manager.php
├── includes/
│   ├── core/          # schema, installer, migration
│   ├── adapters/      # provider-specific TTS contracts
│   ├── jobs/          # persistent queue and public API
│   ├── assets/        # private storage and ACL delivery
│   ├── governance/    # budget, usage and kill switch
│   ├── tracker/       # native rollout tracker
│   ├── tts/           # provider model and voice catalogs
│   ├── functions.php  # preserved legacy/public transport API
│   └── class-ai-capability.php
├── admin/
│   ├── class-admin.php
│   └── class-operations.php
├── assets/
│   ├── js/tts-studio.js
│   └── css/operations.css
├── data/data.json
├── tracker.json
├── revision.json
└── revision.txt
```

## Veri tabloları

- `{prefix}agfo_ai_jobs`: iş, rota, lease, deneme, maliyet rezervasyonu ve sonuç
- `{prefix}agfo_ai_assets`: özel dosya, hash, MIME, ACL, provenance ve retention
- `{prefix}agfo_ai_usage`: günlük sağlayıcı × model × yetenek × kaynak plugin rollup

## Güvenlik

- Admin işlemlerinde `manage_options`
- Yazma işlemlerinde nonce
- Girdi sanitization ve çıktı escaping
- Job/asset sahibi veya yönetici ACL
- Opak asset UUID ve dosya adı
- Web root dışı varsayılan depolama
- SHA-256 bütünlük kaydı
- API key redaksiyonu
- Zorunlu provenance
- Medya Kütüphanesine yalnız açık opt-in
- Capability kill switch
- Atomik bütçe rezervasyonu

## Rollout doğrulaması

**AGFO AI > Geliştirme Takibi** ekranı `tracker.json` planını ve runtime kanıtlarını gösterir. Kaynak paketinde uygulanan görevler `implemented` durumundadır; WordPress staging smoke kontrolleri kanıtla tamamlanmadan `verified` sayılmaz.

## Bilinen sınırlar

- Video üretimi ve video düzenleme `VIDEO-001` göreviyle ertelenmiştir.
- OpenAI TTS fiyatı sözleşmeye göre admin tarafından girilir; fiyat `0` ise parasal rezervasyon uygulanmaz.
- Uzun metinler ilk sürümde otomatik parçalara ayrılıp birleştirilmez. OpenAI adapteri 4096, ElevenLabs adapteri 40000 karakterlik iş sınırı uygular.
- Webhook tabanlı provider callback katmanı bu TTS sürümünün parçası değildir.


## 16.13.0 Music Generation
ElevenLabs Music, MiniMax Music 2.6 and Google Gemini Lyria 3 are available through the queued `music_generate` capability and `agfo_music_generate()` facade. Outputs are stored in the private asset store by default.


## 16.17.5 - Course Content performance and structured output
- GPT-5.6 content jobs use `reasoning_effort=none` and a task-sized output budget instead of inheriting a huge budget from page context.
- Content Studio waits at most 60 seconds for Academy tasks (45 seconds for general transformations).
- Adds `agfo_content_generate_structured()` for trusted AGFO plugins. OpenAI/OpenRouter use JSON Schema Structured Outputs; no database write is performed by this service.
- Returns elapsed time, finish reason and reasoning-token diagnostics for content calls.


## 16.17.6 - Structured Course Content language control

`agfo_content_generate_structured()` now accepts a `language` option. The selected language is enforced for all public-facing generated fields, independent of the source/title/LMS delivery language. Supported Academy UI values: Türkçe, English, Español, Italiano, Deutsch and Français. If omitted, Türkçe is used.
