# AGFO AI Manager — Bağlayıcı Entegrasyon Spesifikasyonu

**Sürüm:** 16.17.6 · **Kaynak:** `wp-content/plugins/agfo-ai-manager` (canlı kod okunarak üretildi)
**Kapsam:** AGFO eklenti ailesindeki *tüm* AI çağrıları. Bu belge sözleşmedir; koda değil bu belgeye göre geliştirilir, kod bu belgeden saparsa kod hatalıdır.

> **Bu belgenin varlık nedeni:** `max_tokens` / `max_completion_tokens`, temperature reddi, provider gövde farkları ve token tavanları her yeni eklentide yeniden keşfedilip yeniden düzeltiliyordu. Bu dosya o düzeltmeleri **tek seferlik** hale getirir. Bir çağrı bu belgedeki desene uyuyorsa, sonucu provider değişse bile bozulmaz.

---

## 0. Altın Kural (tek cümle)

> **Bağımlı eklenti provider'ı bilmez.** Yapılandırmayı `agfo_get_priority_api_key()` / `agfo_get_provider_for_capability()` çözer, gövdeyi eklenti provider-şekline göre kurar, isteği **daima** `agfo_api_post()` gönderir. `wp_remote_post()`, `curl`, hardcode URL/anahtar **yasaktır**.

---

## 1. Katman Mimarisi

```
Bağımlı eklenti (agfo-poem-translator, agfo-brcgs-report-studio, ...)
        │
        ├─ metin/chat ──────────► agfo_get_priority_api_key() ──► agfo_api_post()   [SENKRON]
        │
        ├─ TTS / müzik ─────────► agfo_job_submit() / agfo_speech_synthesize()      [KUYRUK]
        │                          └─ bütçe rezervasyonu → adapter → private asset store
        │
        ├─ görsel ──────────────► agfo_capability_request('image_generate', ...)    [SENKRON]
        │
        └─ model kararı ────────► agfo_ai_get_* (Model Intelligence)                [SALT OKUR]
```

**Değişmez kural:** Model *kararı* Model Intelligence'tan, *taşıma yapılandırması* `agfo_get_priority_api_key()`'den gelir. İkisi karıştırılmaz.

---

## 2. Provider Registry (`agfo_api_registry()`)

| Kod | Label | type | chat_url / submit_url | auth başlığı | capabilities |
|---|---|---|---|---|---|
| `openai` | OpenAI | llm | `api.openai.com/v1/chat/completions` | `Authorization: Bearer {key}` | chat, speech_synthesize, image_generate |
| `openrouter` | OpenRouter | llm | `openrouter.ai/api/v1/chat/completions` | `Authorization: Bearer {key}` | chat, music_generate, image_generate |
| `claude` | Claude | llm | `api.anthropic.com/v1/messages` | `x-api-key: {key}` + `anthropic-version: 2023-06-01` | chat |
| `gemini` | Gemini | llm | `…/v1beta/models/{model}:generateContent?key={key}` | *(yok — anahtar URL'de)* | chat, music_generate, image_generate |
| `groq` | Groq | llm | `api.groq.com/openai/v1/chat/completions` | Bearer | chat |
| `deepseek` | DeepSeek | llm | `api.deepseek.com/chat/completions` | Bearer | chat |
| `deepinfra` | DeepInfra | llm | `api.deepinfra.com/v1/openai/chat/completions` | Bearer | chat |
| `llama_together` | Together.ai | llm | `api.together.xyz/v1/chat/completions` | Bearer | chat |
| `nvidia` | NVIDIA NIM | llm | `integrate.api.nvidia.com/v1/chat/completions` | Bearer (`nvapi-…`) | chat |
| `minimax` | MiniMax | llm | `api.minimax.io/v1/chat/completions` · T2A: `/v1/t2a_v2` · sesler: `/v1/get_voice` | Bearer | chat, speech_synthesize, music_generate, image_generate |
| `elevenlabs` | ElevenLabs | **media** | `…/v1/text-to-speech/{voice}` | `xi-api-key: {key}` | speech_synthesize, music_generate |
| `fal` | fal.ai | **media** | `queue.fal.run/{model}` | `Authorization: Key {key}` | music_generate, audio_transform, image_generate |

**Kritik:** `type !== 'llm'` olan provider'lar (`elevenlabs`, `fal`) `agfo_get_priority_api_key()` tarafından **reddedilir** (chat akışı korunur). Bunlara yalnız capability/job katmanından erişilir.

### Yetenek bazlı varsayılan modeller (`default_models[capability]`)
- openai → tts `gpt-4o-mini-tts`, image `gpt-image-2`
- openrouter → image `openai/gpt-5.4-image-2`
- gemini → chat `gemini-2.5-flash`, music `lyria-3-clip-preview`, image `imagen-4.0-generate-001`
- minimax → chat `MiniMax-M3`, tts `speech-2.8-hd`, music `music-2.6-free`, image `image-01`
- elevenlabs → tts `eleven_multilingual_v2`, music `music_v1`
- fal → `fal-ai/stable-audio-25/text-to-audio`

Çözüm önceliği: `args['model']` → routing ayarı → `default_models[capability]` → `default_model`.

---

## 3. ⚠️ TOKEN ALANI MATRİSİ — en çok hata yapılan yer

`agfo_api_post()` gövdeyi **provider_code'a göre merkezî olarak yeniden yazar**. Bağımlı eklentinin görevi doğru alan adını *tahmin etmek değil*, doğru `provider_code`'u geçmektir.

| provider_code | Sen ne gönder | Gate ne yapar | Tavan |
|---|---|---|---|
| `openai` | `max_tokens` | model legacy değilse → **`max_completion_tokens`** olarak yeniden adlandırır | — |
| `openrouter` | `max_tokens` | **koşulsuz** `max_completion_tokens`'a çevirir | — |
| `minimax` (chat) | `max_tokens` | `max_completion_tokens`'a çevirir + kırpar | M3: **524288**, M2.x: **204800** |
| `nvidia` | `max_tokens` | dokunmaz, sadece kırpar | **4096** (üstü otomatik kırpılır) |
| `claude` | **`max_tokens`** (zorunlu alan) | **dokunmaz** | — |
| `gemini` | `generationConfig.maxOutputTokens` | **dokunmaz** | — |
| `groq` / `deepseek` / `deepinfra` / `llama_together` | `max_tokens` | **dokunmaz** | — |

### `agfo_uses_max_completion_tokens($model)` gerçek mantığı
Mantık **terstir**: pattern eşleşen "modern" modeller değil, yalnızca **legacy** adlar `max_tokens`'ta kalır.

```
false döner  ⇔  model adı legacy desenlerden biriyle eşleşiyorsa:
   text-davinci · davinci · babbage · curie · ada · instruct · gpt-3.5
kısa desenlerde (<=4 karakter) eşleşme kelime sınırıyla yapılır;
aksi halde  →  true  (bilinmeyen/yeni çıkan tüm modeller dahil)
```
Bu sayede yeni model çıktığında liste güncellenmeden doğru çalışır.

> **16.16.2'de çözüldü:** Kısa legacy desenler artık kelime sınırıyla eşleşir. `ada`, `text-ada-001` ve `text-embedding-ada-002` legacy kalırken, yalnızca adının içinde tesadüfen `ada` geçen yeni model kimlikleri legacy sayılmaz.

> **16.16.2'de çözüldü:** `agfo_get_priority_api_key()` içindeki `uses_max_completion_tokens` alanı artık OpenAI modern modellerinin yanında OpenRouter ve MiniMax chat için de merkezî taşıma katmanıyla tutarlı biçimde `true` raporlanır. Yine de bağımlı eklentiler için tercih edilen desen değişmez: **`max_tokens` gönderip dönüşümü `agfo_api_post()` gate'ine bırakmak en güvenli yoldur.**

### MiniMax chat ek normalizasyonu
- `temperature` → `[0, 2]` aralığına kırpılır
- `top_p` → `[0, 1]` aralığına kırpılır
- `n` alanı **silinir** (MiniMax desteklemez, 400 üretir)

---

## 4. ⚠️ SAMPLING / TEMPERATURE KURALLARI

AGFO AI Manager `temperature` güvenliğini merkezî taşıma katmanında uygular. Bağımlı eklentinin kendi ayarında `temperature` bulunması, parametrenin sağlayıcıya mutlaka gönderileceği anlamına gelmez.

`openai` ve `openrouter` için fail-safe kural:

1. Model kimliği `gpt-5` ile başlıyorsa veya `^o[0-9]+(-|$)` desenine uyuyorsa **provider-default sampling** kabul edilir. Eski canlı probe `supported` yazsa bile bu güvenli kural önceliklidir.
2. `temperature_status = unsupported` ise model ailesinden bağımsız olarak sampling parametreleri silinir.
3. Yukarıdaki iki koşul yoksa mevcut gövde korunur.
4. Buna rağmen yeni veya henüz tanınmayan bir chat modeli sağlayıcıdan açık bir `temperature unsupported/not supported` HTTP hatası döndürürse `agfo_api_post()` isteği **bir kez** `temperature` kaldırılmış gövdeyle tekrarlar. Bu fallback yalnız açık sağlayıcı reddinde çalışır.

**Silinen OpenAI/OpenRouter sampling parametreleri:** `temperature`, `top_p`, `presence_penalty`, `frequency_penalty`, `logprobs`, `top_logprobs`, `logit_bias`, `n`

`agfo_openai_model_is_reasoning($model)` yalnız reasoning-effort davranışını sınıflandırır; temperature kararı bundan ayrıdır. Bu nedenle `gpt-5*-chat-*` varyantı reasoning sayılmasa bile merkezî sampling koruması temperature alanını yine yok sayabilir.

OpenRouter'da vendor öneki soyulur: `openai/gpt-5.5` → sampling kontrolü `gpt-5.5` üzerinden yapılır.

**Sonuç:** Bağımlı eklentiler mevcut `temperature` ayarlarını kaldırmak zorunda değildir. AI Manager modern/uyumsuz modellerde parametreyi iletmez ve açık provider reddinde tek seferlik güvenli retry uygular.

---

## 5. Zorunlu Chat Çağrı Deseni (kopyala-yapıştır)

```php
$ai = function_exists( 'agfo_get_priority_api_key' ) ? agfo_get_priority_api_key() : false;
if ( ! $ai || empty( $ai['key'] ) || empty( $ai['model'] ) || empty( $ai['chat_url'] ) ) {
    return new WP_Error( 'agfo_ai_missing', 'AGFO AI Manager yapılandırılmamış.' );
}

$provider = $ai['code'];
$model    = $ai['model'];
$headers  = array_merge( [ 'Content-Type' => 'application/json' ], $ai['auth'] ?? [] );

$messages = [
    [ 'role' => 'system', 'content' => $system_prompt ],
    [ 'role' => 'user',   'content' => $prompt ],
];

if ( 'gemini' === $provider ) {
    $contents = []; $sys = '';
    foreach ( $messages as $m ) {
        if ( 'system' === $m['role'] ) { $sys = $m['content']; continue; }
        $contents[] = [
            'role'  => 'assistant' === $m['role'] ? 'model' : 'user',
            'parts' => [ [ 'text' => $m['content'] ] ],
        ];
    }
    $body = [
        'contents'         => $contents,
        'generationConfig' => [ 'temperature' => 0.3, 'maxOutputTokens' => 1200 ],
    ];
    if ( $sys ) $body['systemInstruction'] = [ 'parts' => [ [ 'text' => $sys ] ] ];

} elseif ( 'claude' === $provider ) {
    $list = []; $sys = '';
    foreach ( $messages as $m ) {
        if ( 'system' === $m['role'] ) { $sys = $m['content']; continue; }
        $list[] = $m;
    }
    $body = [ 'model' => $model, 'max_tokens' => 1200, 'temperature' => 0.3, 'messages' => $list ];
    if ( $sys ) $body['system'] = $sys;

} else { // openai, openrouter, groq, deepseek, deepinfra, llama_together, nvidia, minimax
    $body = [ 'model' => $model, 'messages' => $messages, 'temperature' => 0.3, 'max_tokens' => 1200 ];
    // max_tokens → max_completion_tokens dönüşümünü agfo_api_post() yapar. ELLE YAPMA.
}

$result = agfo_api_post( $ai['chat_url'], $headers, wp_json_encode( $body ), [
    'provider_code' => $provider,   // ZORUNLU — tüm normalizasyon buna bağlı
    'model'         => $model,      // ZORUNLU — token/sampling kuralları buna bağlı
    'capability'    => 'chat',      // opsiyonel; boş = 'chat'
    'timeout'       => 60,
    'source'        => 'my-plugin-slug',
] );

if ( isset( $result['error'] ) ) {
    return new WP_Error( 'agfo_ai_error', $result['error'] );
}
if ( (int) $result['http_code'] < 200 || (int) $result['http_code'] >= 300 ) {
    return new WP_Error( 'agfo_ai_http', 'HTTP ' . $result['http_code'] . ': ' . substr( $result['body'], 0, 500 ) );
}

$d = json_decode( (string) $result['body'], true );
$text = 'gemini' === $provider ? ( $d['candidates'][0]['content']['parts'][0]['text'] ?? '' )
      : ( 'claude' === $provider ? ( $d['content'][0]['text'] ?? '' )
      : ( $d['choices'][0]['message']['content'] ?? '' ) );

if ( '' === trim( (string) $text ) ) {
    return new WP_Error( 'agfo_ai_empty', 'AI yanıtı ayrıştırılamadı.' );
}
return trim( (string) $text );
```

### Yanıt yolu tablosu
| Provider | Yanıt yolu |
|---|---|
| gemini | `candidates[0].content.parts[0].text` |
| claude | `content[0].text` |
| diğer hepsi (OpenAI-uyumlu) | `choices[0].message.content` |

### Sistem promptunun yeri
| Provider | Yer |
|---|---|
| gemini | üst düzey `systemInstruction` — `contents` içinde **değil** |
| claude | üst düzey `system` (string) — `messages` içinde **değil** |
| diğer | `messages[0]` içinde `role: system` |

---

## 6. `agfo_api_post()` Sözleşmesi

```php
agfo_api_post( string $url, array $headers, string|array $body, array $options = [] ): array
```

**`$options`:**
| Anahtar | Tip | Not |
|---|---|---|
| `provider_code` | string | **Geçilmezse hiçbir normalizasyon çalışmaz.** En sık hata budur. |
| `model` | string | Token/sampling kuralları bu değere bakar; boşsa gövdedeki `model` kullanılır |
| `capability` | string | Boş = `chat`. Chat dışı gövdeye Fusion/chat normalizasyonu uygulanmaz |
| `timeout` | int | `[5,180]` arası kırpılır. Varsayılan 60, **nvidia için 120** |
| `source` | string | Çağıran eklenti slug'ı — telemetri/log |
| `progress` | callable | `fn(string $stage, array $detail)` — aşama bildirimi |
| `poll_budget` | int | fal.ai kuyruk bekleme bütçesi, varsayılan 600s (tavan 900) |
| `agfo_call_id` | string | Verilmezse üretilir; `agfo_ai_call_*` hook'larında taşınır |

**Dönüş — başarı:**
```php
[ 'http_code' => int, 'body' => string, 'stage' => 'http', 'transport' => 'agfo_api_post'|'agfo_api_post_guard_shield' ]
```
**Dönüş — hata:**
```php
[ 'error' => string, 'stage' => 'http'|'nvidia_poll'|'fal_poll'|… ]
```
> `http_code` 4xx/5xx **hata sayılmaz** — `error` anahtarı yoktur. HTTP kodunu ayrıca kontrol edin.

**Özel taşımalar (otomatik, çağıran görmez):**
- **NVIDIA 202** → `nvcf-reqid` başlığı/`requestId` ile polling (bütçe = timeout, tavan 180s)
- **fal.ai 2xx + `status_url`** → `IN_QUEUE`/`IN_PROGRESS` bitene kadar polling, sonuç `response_url`'den çekilir
- **Connector guard shield** — yönetilen AI URL'lerinde 3. parti connector onay tuzakları devre dışı bırakılır

**OpenRouter Fusion:** yalnız `provider_code === 'openrouter'` **ve** capability chat iken enjekte edilir. Gövdede zaten `tools` varsa **atlanır**. Mod: `off` / `auto` / `force` (`force` → `tool_choice: required`). **Bağımlı eklenti asla elle `tools` eklememelidir.**

**Güvenlik:** Hata metinleri ve loglar `agfo_redact_secrets()`'ten geçer (Gemini anahtarı URL'de taşındığı için zorunlu).

---

## 7. `agfo_get_priority_api_key()` Dönüş Sözleşmesi

```php
agfo_get_priority_api_key( bool $force_check = false, string $preferred_model = '' ): array|false
```
`false` döner: anahtar yok · provider registry'de yok · **provider `type !== 'llm'`**.

| Alan | Tip | Açıklama |
|---|---|---|
| `code` | string | provider slug |
| `provider_name` | string | insan okur etiket |
| `model` | string | seçili model (boşsa `agfo_models_{code}` listesinin ilki) |
| `key` | string | **çözülmüş** API anahtarı |
| `chat_url` | string | kullanıma hazır uç (gemini'de `{model}`/`{key}` yerleşik) |
| `auth` | array | `{key}` yerleştirilmiş başlıklar |
| `base_url` | string | registry'deki ham şablon |
| `provider_info` | array | tam registry girdisi |
| `uses_max_completion_tokens` | bool | OpenAI modern modelleri, OpenRouter ve MiniMax chat için `true`; merkezî token alanı davranışıyla uyumlu (§3) |
| `model_capabilities` | array | probe + heuristic + default birleşimi |
| `endpoint_type` / `supports_chat` / `supports_temperature` / `docx_allowed` | — | kısayol alanları |
| `compatibility_level` / `compatibility_notes` | — | uyumluluk özeti |
| `openrouter_fusion` | array | yalnız openrouter'da dolu |

---

## 8. Capability Katmanı

`agfo_ai_capabilities()` — tanımlı yetenekler:

| Yetenek | in→out | transport | maliyet birimi | parametreler |
|---|---|---|---|---|
| `chat` | text→text | sync | token | messages, temperature, max_tokens |
| `speech_synthesize` | text→audio | **queued** | karakter | text, voice, model, format, speed, instructions, language, language_boost, volume, pitch, emotion, sample_rate, bitrate, channel, retention_days |
| `music_generate` | text→audio | **queued** | şarkı/saniye | prompt, lyrics, duration, instrumental, lyrics_optimizer, model, format, retention_days |
| `image_generate` | text→image | sync | görsel | prompt, model, size, aspect, quality, format |
| `audio_transform` | audio→audio | async | saniye | source_asset, prompt |

**Fonksiyonlar:**
```php
agfo_ai_capability_exists( string $cap ): bool
agfo_ai_capability_is_chat( $cap ): bool          // boş/tanımsız = chat (geriye uyumluluğun bel kemiği)
agfo_provider_capabilities( string $code ): array
agfo_provider_supports_capability( string $code, string $cap ): bool
agfo_providers_for_capability( string $cap, bool $require_key = true ): array  // code => label
agfo_get_capability_routing(): array               // [cap => ['provider'=>…, 'model'=>…]]
agfo_get_provider_for_capability( string $cap, array $args = [] ): array|WP_Error
agfo_capability_request( string $cap, array $body, array $options = [] ): array|WP_Error
```

`agfo_get_provider_for_capability('chat')` **bilerek** `agfo_get_priority_api_key()` ile birebir aynı davranır — her yerde güvenle kullanılabilir.
`$args['provider']` geçilebilir; yalnız o yeteneği gerçekten destekleyen kod kabul edilir, aksi halde davranış değişmez.

`agfo_capability_request()`: `speech_synthesize` ve `music_generate` **otomatik olarak job kuyruğuna** yönlendirilir; diğerleri senkron `agfo_api_post()`'a gider.

---

## 9. İş (Job) & Asset Katmanı

```php
agfo_job_submit( string $capability, array $payload, array $args = [] ): array|WP_Error
agfo_job_status( string $job_uuid, int $user_id = 0 ): array|WP_Error
agfo_job_cancel( string $job_uuid, int $user_id = 0 ): true|WP_Error
agfo_speech_synthesize( string $text, array $options = [] ): array|WP_Error
agfo_music_generate( string $prompt, array $options = [] ): array|WP_Error
agfo_asset_url( string $asset_uuid, bool $download = false ): string
```

**`$args`:** `provider`, `model`, `provider_models` (`[provider => model]` — fallback rotaları için), `source_plugin` (**zorunlu pratik**), `created_by`, `idempotency_key`, `max_attempts` (varsayılan 3).

**Yaşam döngüsü:**
```
kill switch kontrolü → payload sanitize → rota çözümü (en fazla 3 rota)
→ adapter payload doğrulaması → EN YÜKSEK rota maliyeti hesaplanır
→ draft → ATOMİK bütçe rezervasyonu → queue → worker → asset
```
En yüksek rota tahmini rezerve edilir; böylece 429/5xx failover bütçe tavanını **aşamaz**.

**Dönen public iş nesnesi:** `job_uuid, capability, provider, model, status, attempts, max_attempts, cost_estimate, cost_actual, currency, created_at, updated_at, error_code, error_message` — tamamlandığında ek: `asset_uuid, asset_url, download_url, mime, bytes, attachment_id, attachment_url, metadata`.

**Depolama:** varsayılan `{dirname(ABSPATH)}/agfo-ai-store` (web root **dışı**). `wp-config.php` içinde `AGFO_AI_STORE_PATH` ile değiştirilebilir. Medya Kütüphanesine yazım yalnız açık `publish_to_media_library` opt-in ile.

**Tablolar:** `{prefix}agfo_ai_jobs` · `{prefix}agfo_ai_assets` · `{prefix}agfo_ai_usage`

---

## 10. Model Intelligence (salt okunur karar katmanı)

```php
agfo_ai_get_model_intelligence( $provider, $model ): array
agfo_ai_get_compatible_models( array $args ): array   // provider, chat_only, docx_only, temperature_required, prefer_best_fp, prefer_cheapest, min_score
agfo_ai_get_docx_allowed_models( $provider = '' ): array
agfo_ai_get_best_model( $args ) / agfo_ai_get_best_fp_model( $p ) / agfo_ai_get_cheapest_compatible_model( $p )
agfo_ai_estimate_model_cost( $provider, $model, $in_tokens, $out_tokens ): array
agfo_ai_get_model_recommendation_label( $provider, $model ): string
```
**Kurallar:** (1) her çağrıyı `function_exists()` ile koru, (2) batch scan **manuel** ve yalnız AI Manager admin'ine aittir — özellik eklentisi asla tetiklemez.

**REST (yalnız `manage_options`):**
`GET /wp-json/agfo-ai/v1/models/compatible` · `GET /wp-json/agfo-ai/v1/models/intelligence?provider=…&model=…`

---

## 11. Hook Envanteri

**Action (izleme):** `agfo_ai_call_started` · `agfo_ai_call_stage` · `agfo_ai_call_finished`
Payload: `call_id, provider, model, source, timeout, host` / `stage, detail` / `ok, http_code, error`

**Filter (genişletme):** `agfo_ai_capabilities` · `agfo_provider_capabilities` · `agfo_capability_config`

---

## 12. Option Anahtarları (dokunulmaz sözleşme)

| Anahtar | İçerik |
|---|---|
| `agfo_selected_provider` | aktif chat provider (varsayılan `openai`) |
| `agfo_{code}_api_key` | **şifreli** API anahtarı — asla düz okuma, `agfo_get_api_key()` kullan |
| `agfo_global_preferred_model` | genel tercih edilen model |
| `agfo_reasoning_mode` | 0/1 |
| `agfo_models_{code}` | provider model listesi cache'i |
| `agfo_model_filter_settings` | model listesi filtreleri |
| `agfo_ai_capability_routing` | `[cap => ['provider','model']]` |
| `agfo_openrouter_fusion_{mode,profile,analysis_models,max_tool_calls,judge_model,max_completion_tokens,temperature}` | Fusion yapılandırması |
| `agfo_ai_pricing_rates` | admin girişli fiyat varsayımları |
| `agfo_ai_budget_warning` | bütçe uyarı eşikleri |
| `agfo_ai_minimax_audio_{monthly_quota,reset_day}` | MiniMax audio point kotası |
| `agfo_ai_manager_transport_log` | biriktirmeli taşıma logu (redakte) |
| `agfo_ai_storage_error` / `agfo_ai_schema_error` | kurulum tanılaması |

**Sabitler:** `AGFO_AIM_VERSION`, `AGFO_AIM_PLUGIN_DIR/URL`, `AGFO_AIM_DATA_DIR/FILE`, `AGFO_AI_STORE_PATH` (wp-config), `AGFO_AIM_FFMPEG_PATH` (wp-config).

---

## 13. AJAX Action Envanteri (donmuş isimler)

**Job API** (nonce `agfo_ajax_nonce`): `agfo_job_submit` · `agfo_job_status` · `agfo_job_cancel`
**Model/veri:** `agfo_refresh_provider_models` · `agfo_refresh_all_models` · `agfo_clear_model_cache` · `agfo_download_models` · `agfo_qs_get_data` · `agfo_qs_get_models_only` · `agfo_qs_get_compatible_models` · `agfo_probe_model_capabilities` · `agfo_qs_save` · `agfo_get_model_score` · `agfo_chat_test`
**Model Intelligence:** `agfo_aim_mi_list` · `agfo_aim_mi_probe`
**Eski iş katmanı:** `agfo_ai_job_start` · `agfo_ai_job_status` · `agfo_ai_job_run` · `agfo_ai_model_speed`
**Medya/içerik:** `agfo_ai_tts_catalog` · `agfo_ai_content_transform` · `agfo_ai_image_generate` · `agfo_ai_image_set_featured` · `agfo_ai_image_preview_prompt` · `agfo_ai_provider_quota`
**Legacy alias (AI Suite kapalıyken):** `agfo_suite_get_status` · `agfo_suite_process` · `agfo_suite_save_prompts`

---

## 14. YASAKLAR (ihlali bug'dır)

1. ❌ Chat/completion için `wp_remote_post()` / `curl` doğrudan kullanmak
2. ❌ API anahtarı veya provider URL'i hardcode etmek; anahtarı yeni eklentide saklamak
3. ❌ Registry mantığını kopyalamak
4. ❌ `agfo_api_post()`'a `provider_code` geçmeden çağrı yapmak *(tüm normalizasyon ölür)*
5. ❌ `max_tokens ↔ max_completion_tokens` dönüşümünü eklenti içinde elle yapmak
6. ❌ OpenRouter'da elle `tools` enjekte etmek
7. ❌ TTS/müzik/medya için provider ucuna doğrudan gitmek — `agfo_job_submit()` zorunlu
8. ❌ Bütçe rezervasyonu, kill switch, job sahipliği veya asset ACL'ini atlamak
9. ❌ Üretilen medyayı `source_plugin`/provenance olmadan yazmak; denetim kanıtıyla etiketsiz karıştırmak
10. ❌ Video üretimi varsaymak — **kapsam dışı** (`VIDEO-001` ertelendi)
11. ❌ Batch model scan'i özellik eklentisinden tetiklemek
12. ❌ Yeni sembollerde `agfo_` öneki kullanmak — kendi slug'ını kullan (`agfo_cert_` vb.). *İstisna: mevcut eklenti tarihsel olarak `agfo_` kullanıyorsa yeniden adlandırma yapma, yalnız yeni sembollere uygula.*

---

## 15. Hata & Dayanıklılık Sözleşmesi

- AGFO AI Manager pasifse eklenti **fatal vermez** — her public çağrı `function_exists()` ile korunur
- Provider/model/anahtar yoksa admin notice veya `WP_Error`, asla crash
- `agfo_api_post()` dönüşünde **hem** `error` **hem** `http_code` kontrol edilir
- Uzun çağrılarda timeout yönetimi + okunabilir hata metni
- WP-Cron bağlamında `wp-admin/includes/file.php` otomatik yüklenmez — gerektiğinde açıkça `require_once`

---

## 16. Yeni Provider / Model Eklerken Kontrol Listesi

1. `agfo_api_registry()`'ye girdi ekle: `label, url, chat_url|submit_url, auth, type, capabilities, default_models`
2. `type` doğru mu? `llm` değilse chat akışından **otomatik dışlanır** (istenen davranış mı?)
3. Token alanı: `agfo_api_post()` içinde normalizasyon gerekiyor mu? Tavan var mı?
4. Sampling: reddedilen parametre var mı? Varsa merkezî strip listesine bağla
5. Yanıt yolu: `choices[0].message.content` dışında mı? Parser'a ekle
6. Chat dışı yetenek: adapter + `AGFO_AIM_Adapter_Registry` kaydı + `validate_payload` + `estimate_cost`
7. Fiyat: `agfo_ai_pricing_rates` altına varsayılan snapshot
8. `readme.txt` + `README.md` + `revision.json` + `tracker.json` güncelle
9. Doğrulama: `php -l` tüm dosyalar · JSON parse · public `agfo_*` fonksiyon envanteri korunuyor mu · `wp_ajax_agfo_*` envanteri korunuyor mu

---

## 17. Donmuş (Frozen) Geriye Uyumluluk Sözleşmeleri

Bunlar **kırılamaz** — bağımlı eklentiler bunlara yaslanır:

`agfo_get_priority_api_key()` · `agfo_api_post()` · `agfo_get_provider_for_capability()` · `agfo_capability_request()` · `agfo_get_api_key()` · `agfo_get_selected_provider()` · `agfo_api_registry()` · `agfo_uses_max_completion_tokens()` · `agfo_ai_store_generated_media()` · tüm `wp_ajax_agfo_*` action adları · tüm option anahtarları · `data/data.json` şeması · eski transient tabanlı `AGFO_AIM_AI_Jobs`

*Not: `agfo_model_temperature_status()` ikinci parametresi 16.15.2'de opsiyonel yapıldı (tek argümanlı eski çağrılar fatal veriyordu). Benzer imza genişletmeleri **daima geriye uyumlu** olmalı.*

---

## 18. Bilinen Sınırlar

- Video üretimi/düzenleme yok (`VIDEO-001` ertelendi)
- Uzun metin otomatik parçalanıp birleştirilmiyor — OpenAI TTS **4096**, ElevenLabs **40000** karakter iş sınırı
- Webhook tabanlı provider callback katmanı yok (polling kullanılır)
- OpenAI TTS fiyatı admin girişlidir; `0` ise parasal rezervasyon uygulanmaz
- MiniMax entegrasyonu gerçek anahtarla staging'de doğrulanmadıkça "runtime doğrulanmış" sayılmaz

---

## 19. Bu Spesifikasyonun Bakımı

Eklenti içinde **AGFO AI → 📐 AI Specification** ekranı (`AGFO_AI_Spec_Class`) bu belgenin çalışma-zamanı sürümünü üretir: aktif provider/model, WP ortamı ve isteğe bağlı olarak seçili eklentinin kaynak kodu dahil. Yeni bir eklenti geliştirirken **bu belge + o ekranın çıktısı** birlikte AI'ye verilir.

Bu dosya değiştiğinde: sürüm başlığını güncelle, `revision.json`/`tracker.json` ile tutarlılığı koru.


## 16.17.5 — Hızlı ve yapılandırılmış içerik üretimi

- `agfo_content_transform()` geriye uyumlu kalır. GPT-5.6 OpenAI içerik çağrılarında `reasoning_effort=none` ve `verbosity=medium` kullanılır.
- İçerik çıktı bütçesi artık PAGE/POST CONTEXT uzunluğundan türetilmez; görevin türüne göre sınırlı bir bütçe seçilir.
- Yeni public facade: `agfo_content_generate_structured( string $source_html, array $options = [] )`. Trusted AGFO pluginleri JSON Schema ile yapılandırılmış veri isteyebilir. Bu facade hiçbir post/meta kaydı yapmaz.
- OpenAI/OpenRouter structured çağrılarında `response_format.type=json_schema` kullanılır; diğer sağlayıcılarda şema prompt içinde uygulanır.
- Structured ve normal içerik sonuçları gecikme/finish/reasoning tanı bilgisi döndürür.


## 16.17.6 — Yapılandırılmış içerikte çıktı dili

`agfo_content_generate_structured()` `language` seçeneğini kabul eder. Dil, source/title/LMS delivery dilinden bağımsız olarak sistem talimatında zorunlu tutulur. Varsayılan `Türkçe`dir.
