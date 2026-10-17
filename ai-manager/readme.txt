=== AGFO AI Manager ===
Contributors: agfocert
Tags: ai, image-generation, featured-image, music-generation, tts, gemini, wordpress
Requires at least: 6.0
Requires PHP: 7.4
Stable tag: 17.4.1
License: GPL-2.0-or-later

Central AI provider, capability, persistent job, private asset and budget management for the AGFO ecosystem.

Version 16.17.6 keeps the fast structured-content path and adds explicit output-language control for AGFO Academy Course Content generation.

== Description ==

Version 17.0.0 adds a central request guard. Every request to a managed AI chat endpoint — from agfo_api_post() or from any plugin calling wp_remote_post() directly — is cleaned before it is sent: sampling parameters are removed for models that only accept the provider default (deny-by-default for new OpenAI families), parameters a provider has refused are learned and never sent again, OpenAI responses-only models (pro, codex, deep-research) are bridged transparently through /v1/responses, and unavailable or non-chat models are routed to a working model of the same provider. The AI Kontrol Merkezi modal is redesigned with a column-aligned model table, compatibility badges and a guard panel.

Version 16.17.7 hardens GPT-5/o-series temperature omission across capability metadata and direct WordPress HTTP calls while preserving explicit capability probes.

Version 16.17.0 redesigns the Quick Switch modal as a tabbed control workspace. Speed, benchmark, saved-model and active-setting cards are moved out of the narrow right column into full tabs; benchmark data now loads on model selection, saved models are searchable/selectable, and active versus unsaved state is visible. Existing provider, model, option and public API contracts remain backward compatible.

Version 16.16.0 adds a Classic Editor AI image studio: a new image_generate capability with provider-aware request bodies for OpenAI, OpenRouter, Gemini, fal.ai and MiniMax, editable art-direction presets, automatic subject briefing from the post title and body when no prompt is supplied, media-library storage and one-click featured image assignment. Existing chat, TTS, music, job, asset and budget contracts are unchanged.

Version 16.15.0 integrates AGFO AI Suite into AI Manager as a modern Classic Editor Content Studio. It adds source-faithful rewriting, prompt management, editor replace/insert/undo controls and direct handoff to the existing TTS modal while preserving jobs, TTS, music, storage, cost and public API contracts.

Existing public agfo_* APIs, AJAX action names, option keys and data/data.json remain backward compatible.

== Installation ==

1. Upload and activate the plugin.
2. Configure OpenAI, ElevenLabs or MiniMax API keys under AGFO AI.
3. Configure budgets and pricing assumptions under AGFO AI > Maliyet.
4. Run a short test under AGFO AI > Ses Studyosu.
5. Verify the storage directory is outside the web root and writable.

== Changelog ==

= 16.17.6 =
* Added explicit structured output language control for AGFO Academy Course Content.
* Language defaults to Türkçe when a caller does not provide one.

= 16.17.5 =
* GPT-5.6 Content Studio authoring uses reasoning_effort=none and task-sized output limits for lower latency and fewer empty completions.
* Added agfo_content_generate_structured() with JSON Schema Structured Outputs for trusted AGFO plugin integrations.
* Academy Content Studio timeout is capped at 60 seconds; general content transformations at 45 seconds.
* Added elapsed time, finish reason and reasoning-token diagnostics.

= 17.4.1 =
* AI Editor: Authorization başlığı sunucuda düşürüldüğünde 401 hatası (X-AGFO-Editor-Auth yedeği); 401 yanıtları gerçek nedeni bildirir.

= 17.4.0 =
* New REST API for the AGFO AI Editor (Windows): GET agfo-ai/v1/editor/info, POST agfo-ai/v1/editor/transform, POST agfo-ai/v1/editor/chat. Authentication with WordPress Application Passwords; requires the Content Studio capability (default manage_options). Keys never leave the server. Filter agfo_ai_editor_api_enabled disables it.
* Plugin updates from GitHub Releases (downtownck/agfo-windows-apps, tag ai-manager-vX.Y.Z). The package is verified with SHA-256 (GitHub digest or SHA256SUMS.txt) before install; data/data.json (model catalog, rankings, blacklist) is preserved across updates. Option agfo_aim_github_updates = 0 disables it.

= 17.3.3 =
* Code review: risks that state they cannot be verified are dropped; claims on wp_ajax_/admin_post_ registration lines are judged on the callback body; the refutation window ends at the enclosing function.

= 17.3.2 =
* Code review: every scanner finding gets a required answer (keyed strict schema, list-form fallback), refutation accepts only real current_user_can()/nonce checks, source_root jail uses a directory boundary.

= 17.3.1 =
* Code review drops "missing nonce/capability" risks that the code around the cited line refutes (optionally reading the installed file via source_root).
* agfo_ai_content_translation_templates filter output is validated (non-scalar values ignored).
* Front end: AI Kontrol Merkezi markup and assets load only when the admin bar is showing (filter agfo_aim_frontend_control_center).

= 17.3.0 =
* Classic editor: one-click "Çevir" button with a target-language picker next to "AI Düzenle"; translates the selection (or the whole content) without changing the studio's saved preferences.
* Translations ("Çevir ve düzelt") use the Çeviri (text_translate) model route and fall back to the default text model; output budget scales with the source (1200–8000 tokens) and truncated results are flagged.

= 17.2.0 =
* New AI code review service agfo_ai_code_review() with quick (gpt-4.1-mini by default) and deep model routes, strict JSON schema, secret masking and evidence checks. Used by AGFO Plugin Installer 2.3.0.

= 17.1.2 =
* All Base64 handling goes through one audited, constant-time codec (libsodium first); stored API keys stay compatible.
* FFmpeg runs through one hardened launcher: only the verified FFmpeg binary, no shell, NUL-byte rejection, timeouts (long-speech merge previously had none).

= 17.1.1 =
* Test files: prefixed helper functions and guarded WordPress stubs so static Code Health scans report no pluggable-risk globals. No runtime change.

= 17.1.0 =
* Model lists show the newest models first (provider release time, date in the id, family version) with a "Yeni" badge; sort by newest, score, price or name.
* Model refresh now keeps release time, token prices (OpenRouter, Together) and per-image prices.
* AI Kontrol Merkezi: Translation board (benchmark quality vs. cost per 1,000 words, one-click translation model via the new text_translate route and agfo_get_translation_config()) and Image board (quality note, per-image price, set studio default).

= 17.0.1 =
* Image studio: the model field is a real select listing every image model of the provider plus a custom-id option; image models found in downloaded provider lists are added automatically.

= 17.0.0 =
* Central request guard: deny-by-default sampling policy for OpenAI, learned provider refusals with same-call repair, transparent Responses API bridge for pro/codex models, working-model fallback for unavailable or non-chat models.
* Capability probes give reasoning models enough output tokens; stale false "chat ✗" results are corrected on read.
* agfo_api_post() no longer turns empty JSON objects into arrays; data.json is cached per request.
* Redesigned AI Kontrol Merkezi modal.

= 16.19.0 =
* Görsel stüdyosuna "sanat yönetmeni" adımı: metin modeli yazıyı, preset'i ve ek notu birlikte okuyup tek, betimleyici görsel promptu yazar (özne, mekân, kompozisyon, lens, ışık, palet, doku).
* Brief türü preset'e göre değişir: sahne, kapak (tipografi planıyla) ve infografik (yalnızca kaynaktaki rakamlarla yerleşim şartnamesi).
* Prompt, seçilen görsel modelinin uzunluk sınırına göre boyutlandırılır (MiniMax, FLUX, Recraft, Imagen); özne artık her zaman başta.
* Preset metinleri kural listesinden olumlu, somut sanat yönetimine çevrildi; eski varsayılanın kaydedilmiş kopyaları yeni varsayılanı artık maskelemez.
* Gemini görsel modellerine en-boy oranı, FLUX Pro Ultra'ya aspect_ratio iletilir.
* Brief çağrısında reasoning/thinking modelleri için token payı artırıldı; boş yanıt ve ham başlık düşüşü giderildi.

= 16.18.0 =
* Uzun metin seslendirme: sağlayıcı karakter sınırına göre paragraf/cümle/kelime sınırlarından bölme.
* Parça boyu yedek rotalar dahil en küçük model sınırından hesaplanır, %90 emniyet payı uygulanır.
* Yeni fonksiyonlar: agfo_speech_synthesize_long, agfo_speech_split_preview, agfo_speech_group_status, agfo_speech_group_merge, agfo_speech_limit.
* Aynı metin için idempotency anahtarı sabittir; mükerrer faturalandırma olmaz.

= 16.17.7 =
* GPT-5 and o-series now report supports_temperature=false consistently across capability and priority-config APIs even if historical probe data says supported.
* Added a narrow OpenAI/OpenRouter chat-completions HTTP shield for legacy AGFO plugins that call wp_remote_post() directly and bypass agfo_api_post().
* Explicit temperature capability probes bypass the runtime shield so Model Intelligence still measures real provider behavior.
* No database migration or breaking public API, AJAX action or option-key change.

= 16.17.2 =
* Modern GPT-5 and o-series chat requests ignore temperature and related sampling controls centrally, even when an older probe says temperature was supported.
* Added a one-time transport retry without temperature when a chat provider explicitly rejects that parameter.
* agfo_get_priority_api_key() now exposes effective supports_temperature=false for protected OpenAI/OpenRouter model families.
* Content Studio request bodies honor supports_temperature across providers.
* Classic Editor replace/insert now synchronizes TinyMCE with the underlying textarea and WordPress input/change listeners.
* No database migration or breaking public API, option key or AJAX action change.

= 16.17.1 =
* Renamed generic AGFO_Admin, AGFO_Ajax_Data and AGFO_Encryptor classes to plugin-specific AGFO_AIM_* names with safe legacy aliases when those names are available.

= 16.17.0 =
* Redesigned the Quick Switch modal as a tabbed workspace; the former speed, benchmark, saved-model and active-setting right-column cards are now full tabs.
* Added live benchmark loading for the selected model with source breakdown and AGFO ranking fallback when no source benchmark exists.
* Added searchable saved-model list, copy-all action and one-click model selection.
* Replaced the always-zero blacklist display with a real incompatible-model count and use Model Intelligence speed_score when available.
* Active Settings now compares the saved configuration against the current modal draft and marks unsaved changes.
* Added nonce verification to the existing agfo_get_model_score AJAX endpoint.
* No database migration or breaking public API, option key, AJAX action or data/data.json change.

= 16.16.2 =
* agfo_get_priority_api_key() now reports uses_max_completion_tokens for OpenRouter and MiniMax chat, matching the central agfo_api_post() normalization.
* Dependent plugins that build request bodies from this flag no longer send the wrong token field on OpenRouter.
* Legacy model detection applies word-boundary matching to short patterns, so identifiers that merely contain 'ada' are no longer treated as legacy.
* No database migration, public API signature change, AJAX action change or option key change.

= 16.15.2 =
* agfo_model_temperature_status() now accepts legacy single-argument (model-only) calls; the second parameter is optional.
* Single-argument calls resolve the model across all providers' probe evidence and fall back to the safe 'unknown' status.
* Fixes the fatal ArgumentCountError raised by agfo-flow-rollout-tracker after the 16.7.0 signature change.

= 16.15.1 =
* Fixed the Classic Editor Content Studio action chain when the modal markup is rendered after the script.
* The Rewrite button is now type=button and cannot submit the WordPress post form.
* Modal controls use delegated event handlers so character count, rewrite, apply, insert, copy, undo and TTS handoff initialize reliably.

= 16.15.0 =
* Integrated AGFO AI Suite into AI Manager as a Classic Editor Content Studio.
* Added AI Duzenle beside the existing Seslendir workflow.
* Added selected-text/full-content capture, source-faithful rewrite templates, target language, audience, tone, length and additional-instruction controls.
* Added replace, append, copy, undo and send-result-to-TTS actions.
* Added an AGFO AI > Content Prompts administration page with resettable prompt overrides.
* Added one-time migration for genuinely customized legacy `agfo_suite_prompts` values.
* Added `agfo_content_transform()` and compatibility aliases for legacy AI Suite AJAX calls when the standalone plugin is inactive.
* All content calls use the existing AGFO AI Manager provider selection and `agfo_api_post()` transport.
* No database migration or breaking public API change.

= 16.14.0 =
* Added dry, warm-room reverb, soft echo and hall reverb presets to the Classic Editor TTS modal.
* Added percentage effect depth and persistent FFmpeg MP3 rendering.
* Reused the managed AGFO Music Studio FFmpeg installation when available.
* Added preflight capability checks so unavailable effects do not trigger paid TTS calls.
* Added effect provenance and post-processing failure cost settlement without duplicate provider retries.

= 16.13.0 =
* Added queued `music_generate` capability and `agfo_music_generate()` facade.
* Added ElevenLabs `/v1/music` binary streaming adapter with Music v1/v2 support.
* Added MiniMax `/v1/music_generation` URL/hex adapter; `music-2.6-free` is the safe first-test default and paid Music 2.6 remains selectable.
* Added Google Gemini API Lyria 3 Clip/Pro adapter through the Interactions API.
* Uses the verified MP3 path for Lyria in this first release.
* Added provider/capability budget limits, pricing overrides and a music kill switch.
* Stores generated music in the private asset store by default with provenance and retention.
* No database migration or breaking public API change.

= 16.11.0 =
* Added MiniMax as a direct OpenAI-compatible chat provider.
* Added current MiniMax-M3/M2.x model discovery and central max_tokens-to-max_completion_tokens compatibility normalization.
* Added MiniMax synchronous T2A support for Speech 2.8, 2.6, 02 and 01 HD/Turbo models.
* Added live MiniMax account voice discovery with system, cloned and generated voice groups.
* Added MiniMax model and voice dropdowns to TTS Studio and the Classic Editor modal.
* Added language boost, volume, pitch, emotion, sample rate, bitrate and channel controls.
* Added MiniMax budget limits and HD/Turbo character-rate snapshots.
* Preserved existing public APIs, AJAX actions, options and database schema.
* Runtime verification with a real MiniMax key remains a staging acceptance step.

= 16.10.2 =
* Added a deterministic server-rendered AGFO Seslendirme launcher through `edit_form_after_title`.
* Removed post-type and editor-mode gates from authorised post edit screen asset loading.
* Kept the launcher visible when the Add Media toolbar is missing or replaced.
* Hid the launcher only after a real toolbar button is present.
* No database migration, job API, asset API or provider contract change.

= 16.10.1 =
* Fixed the Seslendir button being suppressed on some Classic Editor page screens.
* Removed the render dependency on the admin_enqueue_scripts eligibility flag.
* Avoided false-negative exclusion caused by block-editor availability checks.
* Added a JavaScript fallback that inserts the button beside Add Media or above the classic editor.
* No database migration, job API, asset API or provider contract change.

= 16.10.0 =
* Added a Seslendir button beside Add Media in the Classic Page Editor.
* Added a modal that captures selected text or the full page body.
* Reused OpenAI and live ElevenLabs model/voice catalogs in the editor workflow.
* Added queued generation status, audio preview, download, Media Library publishing and editor insertion.
* Inserted durable Media Library URLs as WordPress audio shortcodes; private nonce URLs are never persisted in page content.
* Limited the default integration to classic `page` editing screens; the block editor is unchanged.
* Added attachment_url to completed job responses without changing existing response fields.
* No database migration or breaking public API change.

= 16.9.0 =
* Replaced free-text TTS model and voice fields with provider-aware dropdowns.
* Added all current OpenAI Speech API TTS models and 13 built-in voices.
* Added live ElevenLabs TTS model discovery and paginated account voice discovery.
* Added voice search, cache refresh, provider-specific model routing and optional ElevenLabs voice settings.
* Added OpenAI model/voice compatibility protection.

= 16.8.2 =
* Fixed nonce-protected TTS playback and download URLs returned through AJAX.
* Asset URLs are now generated as raw query strings instead of HTML-escaped `wp_nonce_url()` output.
* No database migration, ACL change or public API signature change.

= 16.8.1 =
* Fixed WP-Cron TTS jobs fataling when `wp_tempnam()` was not loaded.
* OpenAI and ElevenLabs adapters now load the WordPress file API lazily before creating streamed temporary files.
* No database migration or public API change.

= 16.8.0 =
* Added speech_synthesize capability.
* Added OpenAI and ElevenLabs TTS adapters.
* Added persistent jobs, assets and usage tables.
* Added atomic budget reservation and capability kill switch.
* Added private generated-audio storage and ACL delivery.
* Added TTS Studio, Jobs, Costs and native Rollout Tracker pages.
* Deferred video generation and editing.
* Preserved existing public APIs and data.json.

= 16.7.0 =
* Improved model dropdown intelligence and temperature probe precedence.

= 16.6.0 =
* Added capability routing, generic async polling, fal.ai and media integration.


## 16.13.0 Music Generation
ElevenLabs Music, MiniMax Music 2.6 and Google Gemini Lyria 3 are available through the queued `music_generate` capability and `agfo_music_generate()` facade. Outputs are stored in the private asset store by default.
