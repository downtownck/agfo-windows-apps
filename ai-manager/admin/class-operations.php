<?php
/**
 * TTS studio, job queue and governance admin pages.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Operations_Admin' ) ) {
    final class AGFO_AIM_Operations_Admin {
        public static function register_hooks(): void {
            add_action( 'admin_menu', [ __CLASS__, 'add_menus' ], 20 );
            add_action( 'admin_enqueue_scripts', [ __CLASS__, 'enqueue_assets' ] );
            add_action( 'admin_post_agfo_ai_save_governance', [ __CLASS__, 'save_governance' ] );
            add_action( 'admin_post_agfo_ai_retry_job', [ __CLASS__, 'retry_job' ] );
        }

        public static function add_menus(): void {
            add_submenu_page(
                'agfo-ai-manager',
                'Ses Stüdyosu',
                '🔊 Ses Stüdyosu',
                'manage_options',
                'agfo-ai-tts-studio',
                [ __CLASS__, 'render_studio' ]
            );
            add_submenu_page(
                'agfo-ai-manager',
                'AI İşleri',
                '🧾 İşler',
                'manage_options',
                'agfo-ai-jobs',
                [ __CLASS__, 'render_jobs' ]
            );
            add_submenu_page(
                'agfo-ai-manager',
                'AI Maliyet ve Kotalar',
                '💰 Maliyet',
                'manage_options',
                'agfo-ai-costs',
                [ __CLASS__, 'render_costs' ]
            );
        }

        public static function enqueue_assets( string $hook ): void {
            $page = isset( $_GET['page'] ) ? sanitize_key( wp_unslash( (string) $_GET['page'] ) ) : '';
            if ( ! in_array( $page, [ 'agfo-ai-tts-studio', 'agfo-ai-jobs', 'agfo-ai-costs' ], true ) ) {
                return;
            }

            $css = AGFO_AIM_PLUGIN_DIR . 'assets/css/operations.css';
            wp_enqueue_style(
                'agfo-ai-operations',
                AGFO_AIM_PLUGIN_URL . 'assets/css/operations.css',
                [],
                file_exists( $css ) ? AGFO_AIM_VERSION . '.' . filemtime( $css ) : AGFO_AIM_VERSION
            );

            if ( 'agfo-ai-tts-studio' === $page ) {
                $js = AGFO_AIM_PLUGIN_DIR . 'assets/js/tts-studio.js';
                wp_enqueue_script(
                    'agfo-ai-tts-studio',
                    AGFO_AIM_PLUGIN_URL . 'assets/js/tts-studio.js',
                    [ 'jquery' ],
                    file_exists( $js ) ? AGFO_AIM_VERSION . '.' . filemtime( $js ) : AGFO_AIM_VERSION,
                    true
                );
                wp_localize_script(
                    'agfo-ai-tts-studio',
                    'agfoTtsStudio',
                    [
                        'ajaxUrl'  => admin_url( 'admin-ajax.php' ),
                        'nonce'    => wp_create_nonce( 'agfo_ajax_nonce' ),
                        'pollMs'   => 2500,
                        'catalogs' => [
                            'openai'     => class_exists( 'AGFO_AIM_TTS_Catalog' ) ? AGFO_AIM_TTS_Catalog::openai_catalog() : [],
                            'elevenlabs' => class_exists( 'AGFO_AIM_TTS_Catalog' ) ? AGFO_AIM_TTS_Catalog::elevenlabs_fallback_catalog() : [],
                            'minimax'     => class_exists( 'AGFO_AIM_TTS_Catalog' ) ? AGFO_AIM_TTS_Catalog::minimax_fallback_catalog() : [],
                            'ema'         => class_exists( 'AGFO_AIM_Adapter_EMA' ) ? AGFO_AIM_Adapter_EMA::catalog( false ) : [],
                        ],
                        'hasKeys'  => [
                            'openai'     => function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'openai' ) ),
                            'elevenlabs' => function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'elevenlabs' ) ),
                            'minimax'     => function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'minimax' ) ),
                            'ema'         => function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'ema' ) ),
                        ],
                        'emaSettings' => class_exists( 'AGFO_AIM_Adapter_EMA' ) ? AGFO_AIM_Adapter_EMA::settings() : [],
                        'messages' => [
                            'queued'         => 'İş kuyruğa alındı.',
                            'processing'     => 'Ses üretiliyor…',
                            'storing'        => 'Ses güvenli depoya aktarılıyor…',
                            'complete'       => 'Ses üretimi tamamlandı.',
                            'failed'         => 'Ses üretimi başarısız oldu.',
                            'catalogLoading' => 'Model ve ses seçenekleri yükleniyor…',
                            'catalogReady'   => 'Model ve ses seçenekleri hazır.',
                            'catalogEmpty'   => 'Bu hesap için ses bulunamadı.',
                        ],
                    ]
                );
            }
        }

        public static function render_studio(): void {
            self::guard();
            $providers = function_exists( 'agfo_providers_for_capability' )
                ? agfo_providers_for_capability( 'speech_synthesize', false )
                : [];
            $openai_key    = function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'openai' ) );
            $eleven_key    = function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'elevenlabs' ) );
            $minimax_key   = function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'minimax' ) );
            $ema_key       = class_exists( 'AGFO_AIM_Adapter_EMA' ) && function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'ema' ) );
            $ema_settings  = class_exists( 'AGFO_AIM_Adapter_EMA' ) ? AGFO_AIM_Adapter_EMA::settings() : [];
            $storage_error = (string) get_option( 'agfo_ai_storage_error', '' );
            $schema_error  = (string) get_option( 'agfo_ai_schema_error', '' );
            $openai_catalog = class_exists( 'AGFO_AIM_TTS_Catalog' ) ? AGFO_AIM_TTS_Catalog::openai_catalog() : [ 'models' => [], 'voices' => [] ];
            $eleven_catalog = class_exists( 'AGFO_AIM_TTS_Catalog' ) ? AGFO_AIM_TTS_Catalog::elevenlabs_fallback_catalog() : [ 'models' => [], 'voices' => [] ];
            $minimax_catalog = class_exists( 'AGFO_AIM_TTS_Catalog' ) ? AGFO_AIM_TTS_Catalog::minimax_fallback_catalog() : [ 'models' => [], 'voices' => [] ];
            ?>
            <div class="wrap agfo-ops-wrap">
                <h1>Ses Stüdyosu</h1>
                <p class="description">Metni OpenAI, ElevenLabs, MiniMax veya sunucudaki EMA Lightning (Türkçe, ücretsiz) üzerinden sese dönüştürür. Model ve konuşmacı listeleri sağlayıcıya göre hazırlanır; hesap sesleri yalnız sunucu tarafında güvenli biçimde okunur.</p>

                <?php if ( $schema_error ) : ?>
                    <div class="notice notice-error inline"><p><strong>Veri tabanı şeması hazır değil:</strong> <?php echo esc_html( $schema_error ); ?></p></div>
                <?php endif; ?>
                <?php if ( $storage_error ) : ?>
                    <div class="notice notice-error inline"><p><strong>Özel depolama hazır değil:</strong> <?php echo esc_html( $storage_error ); ?></p></div>
                <?php endif; ?>
                <?php if ( ! $openai_key && ! $eleven_key && ! $minimax_key && ! $ema_key ) : ?>
                    <div class="notice notice-warning inline"><p>Önce <a href="<?php echo esc_url( admin_url( 'admin.php?page=agfo-ai-manager' ) ); ?>">Sağlayıcılar</a> ekranında OpenAI, ElevenLabs veya MiniMax API anahtarı ya da EMA Lightning servis token’ı tanımlayın.</p></div>
                <?php elseif ( ! $eleven_key || ! $minimax_key ) : ?>
                    <div class="notice notice-info inline"><p>ElevenLabs ve MiniMax anahtarları kaydedildiğinde bu sağlayıcılardaki hesap sesleri otomatik olarak dropdown listelerine alınır.</p></div>
                <?php endif; ?>

                <section class="agfo-quota-dashboard" aria-labelledby="agfo-quota-title">
                    <div class="agfo-quota-heading">
                        <div>
                            <h2 id="agfo-quota-title">Sağlayıcı kredileri</h2>
                            <p class="description">ElevenLabs değeri sağlayıcıdan canlı alınır. MiniMax değeri, belgelenmiş bakiye endpointi bulunmadığı için yalnız AGFO AI Manager kullanımından hesaplanan yerel tahmindir.</p>
                        </div>
                        <button type="button" id="agfo-quota-refresh-all" class="button button-secondary">Kredileri yenile</button>
                    </div>
                    <div class="agfo-quota-grid">
                        <article class="agfo-quota-card" data-quota-provider="elevenlabs">
                            <div class="agfo-quota-card-head">
                                <h3>ElevenLabs</h3>
                                <span class="agfo-quota-source is-loading">Yükleniyor</span>
                            </div>
                            <div class="agfo-quota-remaining">—</div>
                            <div class="agfo-quota-caption">kalan kredi</div>
                            <div class="agfo-quota-progress"><span style="width:0%"></span></div>
                            <dl class="agfo-quota-meta">
                                <div><dt>Kullanılan</dt><dd data-field="used">—</dd></div>
                                <div><dt>Toplam</dt><dd data-field="limit">—</dd></div>
                                <div><dt>Plan</dt><dd data-field="tier">—</dd></div>
                                <div><dt>Yenilenme</dt><dd data-field="reset_at">—</dd></div>
                            </dl>
                            <p class="agfo-quota-note">ElevenLabs abonelik bilgisi bekleniyor.</p>
                            <button type="button" class="button-link agfo-quota-refresh" data-provider="elevenlabs" <?php disabled( ! $eleven_key ); ?>>Yenile</button>
                        </article>
                        <article class="agfo-quota-card" data-quota-provider="minimax">
                            <div class="agfo-quota-card-head">
                                <h3>MiniMax</h3>
                                <span class="agfo-quota-source is-local">Yerel tahmin</span>
                            </div>
                            <div class="agfo-quota-remaining">—</div>
                            <div class="agfo-quota-caption">tahmini kalan audio point</div>
                            <div class="agfo-quota-progress"><span style="width:0%"></span></div>
                            <dl class="agfo-quota-meta">
                                <div><dt>AGFO kullanımı</dt><dd data-field="used">—</dd></div>
                                <div><dt>Plan kotası</dt><dd data-field="limit">—</dd></div>
                                <div><dt>Plan</dt><dd data-field="tier">—</dd></div>
                                <div><dt>Yerel sıfırlama</dt><dd data-field="reset_at">—</dd></div>
                            </dl>
                            <p class="agfo-quota-note">Yerel kullanım hesabı bekleniyor.</p>
                            <button type="button" class="button-link agfo-quota-refresh" data-provider="minimax" <?php disabled( ! $minimax_key ); ?>>Yenile</button>
                        </article>
                    </div>
                </section>

                <div class="agfo-ops-grid">
                    <section class="agfo-ops-card">
                        <form id="agfo-tts-form">
                            <div class="agfo-field-row">
                                <label for="agfo-tts-provider">Sağlayıcı</label>
                                <select id="agfo-tts-provider" name="provider">
                                    <option value="">Otomatik yönlendirme (anahtarı olan sağlayıcılar)</option>
                                    <?php foreach ( $providers as $code => $label ) : ?>
                                        <option value="<?php echo esc_attr( $code ); ?>" data-has-key="<?php echo esc_attr( ! empty( agfo_get_api_key( $code ) ) ? '1' : '0' ); ?>">
                                            <?php echo esc_html( $label . ( empty( agfo_get_api_key( $code ) ) ? ' — anahtar yok' : '' ) ); ?>
                                        </option>
                                    <?php endforeach; ?>
                                </select>
                                <p class="description">Otomatik yönlendirmede her sağlayıcı kendi modelini ve sesini kullanır; aynı model kimliği iki sağlayıcıya gönderilmez.</p>
                            </div>

                            <section class="agfo-provider-settings" data-provider-panel="openai">
                                <div class="agfo-provider-heading">
                                    <div>
                                        <h2>OpenAI konuşma ayarları</h2>
                                        <p class="description">Speech API'nin desteklediği model ve yerleşik sesler.</p>
                                    </div>
                                    <span class="agfo-provider-badge <?php echo $openai_key ? 'is-ready' : 'is-missing'; ?>"><?php echo esc_html( $openai_key ? 'Anahtar hazır' : 'Anahtar yok' ); ?></span>
                                </div>
                                <div class="agfo-inline-fields agfo-inline-fields-two">
                                    <div class="agfo-field-row">
                                        <label for="agfo-tts-model-openai">OpenAI TTS modeli</label>
                                        <select id="agfo-tts-model-openai" name="model_openai">
                                            <?php foreach ( (array) $openai_catalog['models'] as $model ) : ?>
                                                <option value="<?php echo esc_attr( (string) $model['id'] ); ?>"
                                                    data-description="<?php echo esc_attr( (string) ( $model['description'] ?? '' ) ); ?>"
                                                    data-supports-instructions="<?php echo esc_attr( ! empty( $model['supports_instructions'] ) ? '1' : '0' ); ?>"
                                                    data-max-characters="<?php echo esc_attr( (string) ( $model['max_characters'] ?? 4096 ) ); ?>"
                                                    <?php selected( 'gpt-4o-mini-tts', (string) $model['id'] ); ?>>
                                                    <?php echo esc_html( (string) $model['name'] . ( ! empty( $model['recommended'] ) ? ' — önerilen' : '' ) ); ?>
                                                </option>
                                            <?php endforeach; ?>
                                            <option value="__manual__">Özel / yeni model kimliği…</option>
                                        </select>
                                        <input id="agfo-tts-model-openai-manual" class="agfo-manual-field" type="text" placeholder="OpenAI model kimliği" hidden>
                                        <p id="agfo-openai-model-help" class="description"></p>
                                    </div>
                                    <div class="agfo-field-row">
                                        <label for="agfo-tts-voice-openai">OpenAI sesi</label>
                                        <select id="agfo-tts-voice-openai" name="voice_openai">
                                            <?php foreach ( (array) $openai_catalog['voices'] as $voice ) : ?>
                                                <option value="<?php echo esc_attr( (string) $voice['id'] ); ?>" <?php selected( 'coral', (string) $voice['id'] ); ?>>
                                                    <?php echo esc_html( (string) $voice['name'] . ( ! empty( $voice['description'] ) ? ' — ' . (string) $voice['description'] : '' ) ); ?>
                                                </option>
                                            <?php endforeach; ?>
                                        </select>
                                        <p class="description">Marin ve Cedar kalite için önerilir. TTS-1 ailesinde desteklenmeyen sesler otomatik gizlenir.</p>
                                    </div>
                                </div>
                            </section>

                            <section class="agfo-provider-settings" data-provider-panel="elevenlabs">
                                <div class="agfo-provider-heading">
                                    <div>
                                        <h2>ElevenLabs konuşma ayarları</h2>
                                        <p class="description">Model listesi ve Voice ID'ler API anahtarınıza bağlı olarak hesabınızdan alınır.</p>
                                    </div>
                                    <div class="agfo-provider-actions">
                                        <span class="agfo-provider-badge <?php echo $eleven_key ? 'is-ready' : 'is-missing'; ?>"><?php echo esc_html( $eleven_key ? 'Anahtar hazır' : 'Anahtar yok' ); ?></span>
                                        <button type="button" id="agfo-elevenlabs-refresh" class="button button-secondary" <?php disabled( ! $eleven_key ); ?>>Listeyi yenile</button>
                                    </div>
                                </div>
                                <div id="agfo-elevenlabs-catalog-status" class="agfo-catalog-status" aria-live="polite">
                                    <?php echo esc_html( $eleven_key ? 'Hesap seçenekleri yükleniyor…' : 'ElevenLabs API anahtarı beklendiği için yalnız model yedekleri gösteriliyor.' ); ?>
                                </div>
                                <div class="agfo-inline-fields agfo-inline-fields-two">
                                    <div class="agfo-field-row">
                                        <label for="agfo-tts-model-elevenlabs">ElevenLabs TTS modeli</label>
                                        <select id="agfo-tts-model-elevenlabs" name="model_elevenlabs">
                                            <?php foreach ( (array) $eleven_catalog['models'] as $model ) : ?>
                                                <option value="<?php echo esc_attr( (string) $model['id'] ); ?>"
                                                    data-description="<?php echo esc_attr( (string) ( $model['description'] ?? '' ) ); ?>"
                                                    data-max-characters="<?php echo esc_attr( (string) ( $model['max_characters'] ?? 40000 ) ); ?>"
                                                    <?php selected( 'eleven_multilingual_v2', (string) $model['id'] ); ?>>
                                                    <?php echo esc_html( (string) $model['name'] . ( ! empty( $model['recommended'] ) ? ' — önerilen' : '' ) ); ?>
                                                </option>
                                            <?php endforeach; ?>
                                            <option value="__manual__">Özel / yeni model kimliği…</option>
                                        </select>
                                        <input id="agfo-tts-model-elevenlabs-manual" class="agfo-manual-field" type="text" placeholder="ElevenLabs model kimliği" hidden>
                                        <p id="agfo-elevenlabs-model-help" class="description"></p>
                                    </div>
                                    <div class="agfo-field-row">
                                        <label for="agfo-tts-voice-elevenlabs-search">ElevenLabs sesi</label>
                                        <input id="agfo-tts-voice-elevenlabs-search" type="search" placeholder="Ses adında, dilde, aksanda veya kategoride ara" autocomplete="off">
                                        <select id="agfo-tts-voice-elevenlabs" name="voice_elevenlabs">
                                            <option value="">ElevenLabs anahtarıyla sesler yüklenecek</option>
                                            <option value="__manual__">Voice ID'yi manuel gir…</option>
                                        </select>
                                        <input id="agfo-tts-voice-elevenlabs-manual" class="agfo-manual-field" type="text" placeholder="ElevenLabs Voice ID" hidden>
                                        <p id="agfo-elevenlabs-voice-help" class="description">Ses adı gösterilir; API'ye güvenli biçimde ilgili Voice ID gönderilir.</p>
                                    </div>
                                </div>

                                <details class="agfo-advanced-settings">
                                    <summary>ElevenLabs gelişmiş ses ayarları</summary>
                                    <div class="agfo-inline-fields">
                                        <div class="agfo-field-row">
                                            <label for="agfo-tts-language">Dil</label>
                                            <select id="agfo-tts-language" name="language">
                                                <option value="">Otomatik algıla</option>
                                            </select>
                                        </div>
                                        <div class="agfo-field-row">
                                            <label for="agfo-tts-stability">Stability</label>
                                            <input id="agfo-tts-stability" type="number" name="stability" min="0" max="1" step="0.01" placeholder="Ses varsayılanı">
                                        </div>
                                        <div class="agfo-field-row">
                                            <label for="agfo-tts-similarity">Similarity boost</label>
                                            <input id="agfo-tts-similarity" type="number" name="similarity_boost" min="0" max="1" step="0.01" placeholder="Ses varsayılanı">
                                        </div>
                                        <div class="agfo-field-row">
                                            <label for="agfo-tts-style">Style</label>
                                            <input id="agfo-tts-style" type="number" name="style" min="0" max="1" step="0.01" placeholder="Model varsayılanı">
                                        </div>
                                        <div class="agfo-field-row">
                                            <label for="agfo-tts-speaker-boost">Speaker boost</label>
                                            <select id="agfo-tts-speaker-boost" name="use_speaker_boost">
                                                <option value="">Ses varsayılanı</option>
                                                <option value="1">Açık</option>
                                                <option value="0">Kapalı</option>
                                            </select>
                                        </div>
                                    </div>
                                    <p class="description">Boş bırakılan alanlar seçilen ElevenLabs sesinin kayıtlı varsayılanlarını kullanır.</p>
                                </details>
                            </section>

                            <section class="agfo-provider-settings" data-provider-panel="minimax">
                                <div class="agfo-provider-heading">
                                    <div>
                                        <h2>MiniMax konuşma ayarları</h2>
                                        <p class="description">Speech 2.8/2.6 T2A modelleri ve hesabınızdaki sistem, klonlanmış veya tasarlanmış sesler.</p>
                                    </div>
                                    <div class="agfo-provider-actions">
                                        <span class="agfo-provider-badge <?php echo $minimax_key ? 'is-ready' : 'is-missing'; ?>"><?php echo esc_html( $minimax_key ? 'Anahtar hazır' : 'Anahtar yok' ); ?></span>
                                        <button type="button" id="agfo-minimax-refresh" class="button button-secondary" <?php disabled( ! $minimax_key ); ?>>Listeyi yenile</button>
                                    </div>
                                </div>
                                <div id="agfo-minimax-catalog-status" class="agfo-catalog-status" aria-live="polite">
                                    <?php echo esc_html( $minimax_key ? 'MiniMax ses seçenekleri yükleniyor…' : 'MiniMax API anahtarı beklendiği için model yedekleri ve manuel Voice ID kullanılabilir.' ); ?>
                                </div>
                                <div class="agfo-inline-fields agfo-inline-fields-two">
                                    <div class="agfo-field-row">
                                        <label for="agfo-tts-model-minimax">MiniMax TTS modeli</label>
                                        <select id="agfo-tts-model-minimax" name="model_minimax">
                                            <?php foreach ( (array) $minimax_catalog['models'] as $model ) : ?>
                                                <option value="<?php echo esc_attr( (string) $model['id'] ); ?>"
                                                    data-description="<?php echo esc_attr( (string) ( $model['description'] ?? '' ) ); ?>"
                                                    data-max-characters="<?php echo esc_attr( (string) ( $model['max_characters'] ?? 9999 ) ); ?>"
                                                    <?php selected( 'speech-2.8-hd', (string) $model['id'] ); ?>>
                                                    <?php echo esc_html( (string) $model['name'] . ( ! empty( $model['recommended'] ) ? ' — önerilen' : '' ) ); ?>
                                                </option>
                                            <?php endforeach; ?>
                                            <option value="__manual__">Özel / yeni model kimliği…</option>
                                        </select>
                                        <input id="agfo-tts-model-minimax-manual" class="agfo-manual-field" type="text" placeholder="MiniMax model kimliği" hidden>
                                        <p id="agfo-minimax-model-help" class="description"></p>
                                    </div>
                                    <div class="agfo-field-row">
                                        <label for="agfo-tts-voice-minimax-search">MiniMax sesi</label>
                                        <input id="agfo-tts-voice-minimax-search" type="search" placeholder="Ses adında, kimliğinde veya kategoride ara" autocomplete="off">
                                        <select id="agfo-tts-voice-minimax" name="voice_minimax">
                                            <option value="">MiniMax anahtarıyla sesler yüklenecek</option>
                                            <option value="__manual__">Voice ID'yi manuel gir…</option>
                                        </select>
                                        <input id="agfo-tts-voice-minimax-manual" class="agfo-manual-field" type="text" placeholder="MiniMax Voice ID" hidden>
                                        <p id="agfo-minimax-voice-help" class="description">Ses adı gösterilir; API çağrısında gerçek Voice ID kullanılır.</p>
                                    </div>
                                </div>

                                <details class="agfo-advanced-settings">
                                    <summary>MiniMax gelişmiş ses ayarları</summary>
                                    <div class="agfo-inline-fields">
                                        <div class="agfo-field-row"><label for="agfo-minimax-language-boost">Dil güçlendirme</label><select id="agfo-minimax-language-boost" name="language_boost"><option value="auto">Otomatik algıla</option><option value="Turkish">Türkçe</option><option value="English">İngilizce</option><option value="German">Almanca</option><option value="French">Fransızca</option><option value="Spanish">İspanyolca</option><option value="Italian">İtalyanca</option><option value="Arabic">Arapça</option><option value="Russian">Rusça</option></select></div>
                                        <div class="agfo-field-row"><label for="agfo-minimax-volume">Ses düzeyi</label><input id="agfo-minimax-volume" type="number" name="volume" min="0.1" max="10" step="0.1" value="1"></div>
                                        <div class="agfo-field-row"><label for="agfo-minimax-pitch">Perde</label><input id="agfo-minimax-pitch" type="number" name="pitch" min="-12" max="12" step="1" value="0"></div>
                                        <div class="agfo-field-row"><label for="agfo-minimax-emotion">Duygu</label><select id="agfo-minimax-emotion" name="emotion"><option value="">Model varsayılanı</option><option value="happy">Mutlu</option><option value="sad">Hüzünlü</option><option value="angry">Öfkeli</option><option value="fearful">Korkulu</option><option value="surprised">Şaşkın</option><option value="calm">Sakin</option><option value="fluent">Akıcı</option><option value="whisper">Fısıltı</option></select></div>
                                        <div class="agfo-field-row"><label for="agfo-minimax-sample-rate">Örnekleme</label><select id="agfo-minimax-sample-rate" name="sample_rate"><option value="32000">32000 Hz</option><option value="44100">44100 Hz</option><option value="24000">24000 Hz</option><option value="22050">22050 Hz</option><option value="16000">16000 Hz</option><option value="8000">8000 Hz</option></select></div>
                                        <div class="agfo-field-row"><label for="agfo-minimax-bitrate">Bitrate</label><select id="agfo-minimax-bitrate" name="bitrate"><option value="128000">128 kbps</option><option value="256000">256 kbps</option><option value="64000">64 kbps</option><option value="32000">32 kbps</option></select></div>
                                        <div class="agfo-field-row"><label for="agfo-minimax-channel">Kanal</label><select id="agfo-minimax-channel" name="channel"><option value="1">Mono</option><option value="2">Stereo</option></select></div>
                                    </div>
                                    <p class="description">MiniMax hız aralığı sağlayıcı seçildiğinde otomatik olarak 0.5–2.0 ile sınırlandırılır.</p>
                                </details>
                            </section>

                            <?php if ( class_exists( 'AGFO_AIM_Adapter_EMA' ) ) : ?>
                            <section class="agfo-provider-settings" data-provider-panel="ema">
                                <div class="agfo-provider-heading">
                                    <div>
                                        <h2>EMA Lightning konuşma ayarları</h2>
                                        <p class="description">Sunucuda çalışan Türkçe model. Karakter ücreti yok; tek ses; yalnız Türkçe metin.</p>
                                    </div>
                                    <div class="agfo-provider-actions">
                                        <span class="agfo-provider-badge <?php echo $ema_key ? 'is-ready' : 'is-missing'; ?>"><?php echo esc_html( $ema_key ? 'Token hazır' : 'Token yok' ); ?></span>
                                        <button type="button" id="agfo-ema-refresh" class="button button-secondary" <?php disabled( ! $ema_key ); ?>>Bağlantıyı test et</button>
                                    </div>
                                </div>
                                <div id="agfo-ema-catalog-status" class="agfo-catalog-status" aria-live="polite">
                                    <?php echo esc_html( $ema_key ? 'EMA servisi: ' . (string) ( $ema_settings['endpoint'] ?? '' ) : 'EMA servis token’ı Sağlayıcılar ekranında “EMA Lightning (yerel TTS)” alanına girildiğinde kullanılabilir.' ); ?>
                                </div>
                                <div class="agfo-inline-fields agfo-inline-fields-two">
                                    <div class="agfo-field-row">
                                        <label for="agfo-tts-model-ema">EMA modeli</label>
                                        <select id="agfo-tts-model-ema" name="model_ema">
                                            <option value="ema-lightning" data-max-characters="<?php echo esc_attr( (string) AGFO_AIM_Adapter_EMA::MAX_CHARS ); ?>" selected>EMA Lightning (yerel, Türkçe) — önerilen</option>
                                        </select>
                                        <p id="agfo-ema-model-help" class="description">Tek istekte en fazla <?php echo esc_html( number_format_i18n( AGFO_AIM_Adapter_EMA::MAX_CHARS ) ); ?> karakter. Hız 0.7–1.4.</p>
                                    </div>
                                    <div class="agfo-field-row">
                                        <label for="agfo-tts-voice-ema">EMA sesi</label>
                                        <select id="agfo-tts-voice-ema" name="voice_ema">
                                            <option value="ema" selected>EMA (Türkçe, kadın)</option>
                                        </select>
                                        <p id="agfo-ema-voice-help" class="description">Model tek sesle gelir.</p>
                                    </div>
                                </div>
                                <div class="agfo-inline-fields agfo-inline-fields-two">
                                    <div class="agfo-field-row">
                                        <label for="agfo-ema-pause">Cümle arası duraklama (ms)</label>
                                        <input id="agfo-ema-pause" type="number" name="pause_ms" min="0" max="2000" step="50" value="<?php echo esc_attr( (string) ( $ema_settings['pause_ms'] ?? 350 ) ); ?>">
                                    </div>
                                    <div class="agfo-field-row">
                                        <label for="agfo-ema-paragraph-pause">Paragraf arası duraklama (ms)</label>
                                        <input id="agfo-ema-paragraph-pause" type="number" name="paragraph_pause_ms" min="0" max="3000" step="50" value="<?php echo esc_attr( (string) ( $ema_settings['paragraph_pause_ms'] ?? 700 ) ); ?>">
                                    </div>
                                </div>

                                <?php if ( class_exists( 'AGFO_AIM_Speech_Script' ) ) : ?>
                                <div class="agfo-ema-script-box">
                                    <label class="agfo-check-row">
                                        <input type="checkbox" id="agfo-ema-script" value="1" <?php checked( ! empty( $ema_settings['script_enabled'] ) ); ?>>
                                        Okuma metnini AI ile hazırla (yabancı adlar, sayılar, tarihler, birimler ve kısaltmalar okunduğu gibi yazılır)
                                    </label>
                                    <p class="description">Metin, seslendirmeden önce sitenin metin modeline gönderilir; yalnız yanlış okunacak parçalar değişir. Bir bölümün yanıtı denetimden geçmezse o bölüm özgün haliyle okunur.</p>
                                    <p>
                                        <button type="button" id="agfo-ema-script-preview" class="button button-secondary">Okuma metnini önizle</button>
                                        <button type="button" id="agfo-ema-script-undo" class="button-link" hidden>Özgün metne dön</button>
                                        <span id="agfo-ema-script-status" class="description" aria-live="polite"></span>
                                    </p>
                                </div>
                                <?php endif; ?>

                                <details class="agfo-advanced-settings">
                                    <summary>EMA servis ayarları ve telaffuz sözlüğü</summary>
                                    <div class="agfo-field-row">
                                        <label for="agfo-ema-endpoint">Servis adresi</label>
                                        <input id="agfo-ema-endpoint" type="url" class="regular-text" placeholder="<?php echo esc_attr( AGFO_AIM_Adapter_EMA::DEFAULT_URL ); ?>" value="<?php echo esc_attr( (string) ( $ema_settings['endpoint_saved'] ?? '' ) ); ?>">
                                        <p class="description">Boş bırakılırsa <?php echo esc_html( ! empty( $ema_settings['endpoint_constant'] ) ? 'wp-config.php içindeki AGFO_TTS_ENDPOINT' : AGFO_AIM_Adapter_EMA::DEFAULT_URL ); ?> kullanılır. Servis aynı sunucudaysa yerel adres yeterlidir.</p>
                                    </div>
                                    <div class="agfo-field-row">
                                        <label for="agfo-ema-lexicon">Telaffuz sözlüğü</label>
                                        <textarea id="agfo-ema-lexicon" rows="6" placeholder="BRCGS = Bi Ar Si Ci Es&#10;Nietzsche = Niçe"><?php echo esc_textarea( (string) ( $ema_settings['lexicon'] ?? '' ) ); ?></textarea>
                                        <p class="description">Her satıra bir kayıt: <code>Kelime = okunuş</code>. Yalnız bu site için geçerlidir; sunucudaki ortak sözlüğe eklenir ve aynı kelimede bu site kazanır. Bütün siteler için: <a href="<?php echo esc_url( admin_url( 'admin.php?page=agfo-ai-ema-lexicon' ) ); ?>">Telaffuz Sözlüğü</a>.</p>
                                    </div>
                                    <?php if ( class_exists( 'AGFO_AIM_Speech_Script' ) ) : ?>
                                    <div class="agfo-field-row">
                                        <label for="agfo-ema-script-model">Okuma metni modeli</label>
                                        <select id="agfo-ema-script-model">
                                            <option value="">Sitenin varsayılan metin modeli</option>
                                            <?php
                                            $board = class_exists( 'AGFO_AIM_Model_Catalog' ) ? AGFO_AIM_Model_Catalog::translation_board( 0 ) : [ 'rows' => [] ];
                                            $saved_choice = (string) ( $ema_settings['script_model'] ?? '' );
                                            $seen_choice  = false;
                                            foreach ( (array) ( $board['rows'] ?? [] ) as $row ) :
                                                if ( in_array( (string) ( $row['route'] ?? 'chat' ), [ 'unavailable', 'not_chat' ], true ) ) {
                                                    continue;
                                                }
                                                $choice = (string) $row['provider'] . '|' . (string) $row['id'];
                                                $seen_choice = $seen_choice || $choice === $saved_choice;
                                                $speed  = class_exists( 'AGFO_AIM_Editor_API' ) ? AGFO_AIM_Editor_API::speed_class( (string) $row['id'], ! empty( $row['reasoning'] ), $row['speed_score'] ?? null ) : '';
                                                ?>
                                                <option value="<?php echo esc_attr( $choice ); ?>" <?php selected( $saved_choice, $choice ); ?>><?php echo esc_html( (string) ( $row['provider_label'] ?? $row['provider'] ) . ' — ' . (string) $row['id'] . ( ! empty( $row['quality'] ) ? ' · kalite ' . (int) $row['quality'] : '' ) . ( 'fast' === $speed ? ' · hızlı' : ( 'slow' === $speed ? ' · yavaş' : '' ) ) ); ?></option>
                                            <?php endforeach; ?>
                                            <?php if ( '' !== $saved_choice && ! $seen_choice ) : ?>
                                                <option value="<?php echo esc_attr( $saved_choice ); ?>" selected><?php echo esc_html( $saved_choice ); ?></option>
                                            <?php endif; ?>
                                        </select>
                                        <p class="description">Hızlı ve ucuz bir model yeterlidir; düşünen (reasoning) modeller yavaştır. Yanıtlar bölüm bölüm 30 gün saklanır, aynı metin yeniden ücretlendirilmez.</p>
                                    </div>
                                    <?php endif; ?>
                                    <p class="description"><?php echo esc_html( ! empty( $ema_settings['token_constant'] ) ? 'Token wp-config.php içindeki AGFO_TTS_TOKEN sabitinden okunuyor.' : 'Token, Sağlayıcılar ekranındaki EMA Lightning anahtar alanında şifreli saklanır.' ); ?></p>
                                    <p><button type="button" id="agfo-ema-save" class="button button-secondary">EMA ayarlarını kaydet</button> <span id="agfo-ema-save-status" class="description" aria-live="polite"></span></p>
                                </details>
                            </section>
                            <?php endif; ?>

                            <div class="agfo-inline-fields">
                                <div class="agfo-field-row">
                                    <label for="agfo-tts-format">Biçim</label>
                                    <select id="agfo-tts-format" name="format">
                                        <option value="mp3">MP3</option>
                                        <option value="wav">WAV</option>
                                        <option value="opus">Opus</option>
                                        <option value="aac">AAC</option>
                                        <option value="flac">FLAC</option>
                                        <option value="pcm">PCM</option>
                                        <option value="ulaw">μ-law</option>
                                        <option value="alaw">A-law</option>
                                    </select>
                                    <p id="agfo-format-help" class="description"></p>
                                </div>
                                <div class="agfo-field-row">
                                    <label for="agfo-tts-speed">Hız</label>
                                    <input id="agfo-tts-speed" type="number" name="speed" min="0.25" max="4" step="0.05" value="1">
                                </div>
                                <div class="agfo-field-row">
                                    <label for="agfo-tts-retention">Saklama (gün)</label>
                                    <input id="agfo-tts-retention" type="number" name="retention_days" min="1" max="3650" value="30">
                                </div>
                            </div>

                            <div class="agfo-field-row">
                                <label for="agfo-tts-instructions">Okuma talimatı</label>
                                <textarea id="agfo-tts-instructions" name="instructions" rows="3" placeholder="Örn. Sakin, olgun ve İstanbul Türkçesiyle oku."></textarea>
                                <p id="agfo-instructions-help" class="description">GPT-4o mini TTS modelleri aksan, ton, duygu, hız ve fısıltı gibi talimatları yorumlayabilir.</p>
                            </div>

                            <div class="agfo-field-row">
                                <label for="agfo-tts-text">Metin</label>
                                <textarea id="agfo-tts-text" name="text" rows="12" required maxlength="40000"></textarea>
                                <div class="agfo-char-counter"><span id="agfo-tts-char-count">0</span> / <span id="agfo-tts-char-limit">40000</span> karakter</div>
                            </div>

                            <label class="agfo-check-row">
                                <input type="checkbox" name="publish_to_media_library" value="1">
                                Çıktıyı ayrıca WordPress Medya Kütüphanesine yayımla (herkese açık URL üretebilir)
                            </label>

                            <p class="agfo-disclosure">Yapay ses kullanıldığında, içeriğin yayımlandığı yerde bunun yapay olarak üretildiğini açıkça belirtin.</p>
                            <button type="submit" class="button button-primary button-hero" <?php disabled( ( ! $openai_key && ! $eleven_key && ! $minimax_key && ! $ema_key ) || $storage_error || $schema_error ); ?>>Sesi Üret</button>
                        </form>
                    </section>

                    <aside class="agfo-ops-card agfo-result-card" aria-live="polite">
                        <h2>İş Durumu</h2>
                        <div id="agfo-tts-status" class="agfo-status is-idle">Henüz iş başlatılmadı.</div>
                        <dl id="agfo-tts-meta" class="agfo-job-meta" hidden>
                            <div><dt>İş</dt><dd id="agfo-tts-job-id">—</dd></div>
                            <div><dt>Sağlayıcı</dt><dd id="agfo-tts-job-provider">—</dd></div>
                            <div><dt>Model</dt><dd id="agfo-tts-job-model">—</dd></div>
                            <div><dt>Tahmini maliyet</dt><dd id="agfo-tts-job-cost">—</dd></div>
                        </dl>
                        <div id="agfo-tts-output" hidden>
                            <audio id="agfo-tts-player" controls preload="metadata"></audio>
                            <p><a id="agfo-tts-download" class="button button-secondary" href="#">Dosyayı indir</a></p>
                        </div>
                        <button type="button" id="agfo-tts-cancel" class="button button-link-delete" hidden>İşi iptal et</button>
                    </aside>
                </div>
            </div>
            <?php
        }

        public static function render_jobs(): void {
            self::guard();
            $status = isset( $_GET['status'] ) ? sanitize_key( wp_unslash( (string) $_GET['status'] ) ) : '';
            $jobs   = class_exists( 'AGFO_AIM_Job_Store' ) ? AGFO_AIM_Job_Store::list_jobs( [ 'limit' => 100, 'status' => $status ] ) : [];
            ?>
            <div class="wrap agfo-ops-wrap">
                <h1>AI İşleri</h1>
                <p class="description">Kalıcı iş kuyruğu, sağlayıcı rotası, deneme sayısı, maliyet ve çıktı durumları.</p>
                <form method="get" class="agfo-filter-bar">
                    <input type="hidden" name="page" value="agfo-ai-jobs">
                    <select name="status">
                        <option value="">Tüm durumlar</option>
                        <?php foreach ( [ 'queued', 'processing', 'storing', 'retry', 'complete', 'failed', 'cancelled' ] as $item ) : ?>
                            <option value="<?php echo esc_attr( $item ); ?>" <?php selected( $status, $item ); ?>><?php echo esc_html( $item ); ?></option>
                        <?php endforeach; ?>
                    </select>
                    <button class="button">Filtrele</button>
                </form>
                <table class="wp-list-table widefat fixed striped agfo-jobs-table">
                    <thead><tr><th>İş</th><th>Yetenek</th><th>Sağlayıcı / Model</th><th>Durum</th><th>Deneme</th><th>Maliyet</th><th>Kaynak</th><th>Tarih</th><th>Çıktı</th></tr></thead>
                    <tbody>
                    <?php if ( ! $jobs ) : ?>
                        <tr><td colspan="9">Kayıtlı iş bulunamadı.</td></tr>
                    <?php else : foreach ( $jobs as $job ) : ?>
                        <tr>
                            <td><code title="<?php echo esc_attr( (string) $job['job_uuid'] ); ?>"><?php echo esc_html( substr( (string) $job['job_uuid'], 0, 8 ) ); ?></code></td>
                            <td><?php echo esc_html( (string) $job['capability'] ); ?></td>
                            <td><strong><?php echo esc_html( (string) $job['provider'] ); ?></strong><br><small><?php echo esc_html( (string) $job['model'] ); ?></small></td>
                            <td><span class="agfo-job-state state-<?php echo esc_attr( (string) $job['status'] ); ?>"><?php echo esc_html( (string) $job['status'] ); ?></span><?php if ( ! empty( $job['error_message'] ) ) : ?><br><small title="<?php echo esc_attr( (string) $job['error_message'] ); ?>"><?php echo esc_html( wp_html_excerpt( (string) $job['error_message'], 80, '…' ) ); ?></small><?php endif; ?></td>
                            <td><?php echo esc_html( (int) $job['attempts'] . '/' . (int) $job['max_attempts'] ); ?></td>
                            <td>$<?php echo esc_html( number_format_i18n( (float) $job['cost_actual'] ?: (float) $job['cost_estimate'], 6 ) ); ?></td>
                            <td><?php echo esc_html( (string) $job['source_plugin'] ); ?></td>
                            <td><?php echo esc_html( (string) $job['created_at'] ); ?></td>
                            <td>
                                <?php if ( 'complete' === $job['status'] && ! empty( $job['result']['asset_uuid'] ) ) : ?>
                                    <a class="button button-small" href="<?php echo esc_url( agfo_asset_url( (string) $job['result']['asset_uuid'], true ) ); ?>">İndir</a>
                                <?php elseif ( 'failed' === $job['status'] ) : ?>
                                    <?php $retry_url = wp_nonce_url( admin_url( 'admin-post.php?action=agfo_ai_retry_job&job_uuid=' . rawurlencode( (string) $job['job_uuid'] ) ), 'agfo_ai_retry_job_' . (string) $job['job_uuid'] ); ?>
                                    <a class="button button-small" href="<?php echo esc_url( $retry_url ); ?>">Yeniden dene</a>
                                <?php else : ?>—<?php endif; ?>
                            </td>
                        </tr>
                    <?php endforeach; endif; ?>
                    </tbody>
                </table>
            </div>
            <?php
        }

        public static function render_costs(): void {
            self::guard();
            $limits  = class_exists( 'AGFO_AIM_Budget' ) ? AGFO_AIM_Budget::limits() : [];
            $summary = class_exists( 'AGFO_AIM_Usage' ) ? AGFO_AIM_Usage::recent_summary( 30 ) : [];
            $switch  = class_exists( 'AGFO_AIM_Kill_Switch' ) ? AGFO_AIM_Kill_Switch::all() : [];
            $rates   = get_option( 'agfo_ai_pricing_rates', [] );
            $warning = get_option( 'agfo_ai_budget_warning', [] );
            $plugin_limits_text = '';
            foreach ( (array) ( $limits['plugins'] ?? [] ) as $plugin_slug => $plugin_limit ) {
                $plugin_limits_text .= sanitize_key( (string) $plugin_slug ) . '=' . (float) $plugin_limit . "\n";
            }
            $saved   = isset( $_GET['saved'] );
            ?>
            <div class="wrap agfo-ops-wrap">
                <h1>Maliyet ve Kotalar</h1>
                <?php if ( $saved ) : ?><div class="notice notice-success is-dismissible"><p>Ayarlar kaydedildi.</p></div><?php endif; ?>
                <?php if ( is_array( $warning ) && ! empty( $warning['label'] ) ) : ?>
                    <div class="notice notice-warning"><p><strong>Bütçe uyarısı:</strong> <?php echo esc_html( (string) $warning['label'] ); ?> için öngörülen kullanım $<?php echo esc_html( number_format_i18n( (float) $warning['projected'], 4 ) ); ?> / $<?php echo esc_html( number_format_i18n( (float) $warning['limit'], 4 ) ); ?>.</p></div>
                <?php endif; ?>
                <form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
                    <input type="hidden" name="action" value="agfo_ai_save_governance">
                    <?php wp_nonce_field( 'agfo_ai_save_governance' ); ?>
                    <div class="agfo-ops-grid">
                        <section class="agfo-ops-card">
                            <h2>Aylık bütçe tavanları (USD)</h2>
                            <div class="agfo-field-row"><label>Genel</label><input type="number" min="0" step="0.01" name="global_monthly" value="<?php echo esc_attr( (string) ( $limits['global_monthly'] ?? 0 ) ); ?>"><p class="description">0 = sınırsız. Tahmini maliyet, sağlayıcı çağrısından önce atomik olarak rezerve edilir.</p></div>
                            <div class="agfo-field-row"><label>OpenAI</label><input type="number" min="0" step="0.01" name="provider_openai" value="<?php echo esc_attr( (string) ( $limits['providers']['openai'] ?? 0 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>ElevenLabs</label><input type="number" min="0" step="0.01" name="provider_elevenlabs" value="<?php echo esc_attr( (string) ( $limits['providers']['elevenlabs'] ?? 0 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>MiniMax</label><input type="number" min="0" step="0.01" name="provider_minimax" value="<?php echo esc_attr( (string) ( $limits['providers']['minimax'] ?? 0 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>Gemini</label><input type="number" min="0" step="0.01" name="provider_gemini" value="<?php echo esc_attr( (string) ( $limits['providers']['gemini'] ?? 0 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>TTS</label><input type="number" min="0" step="0.01" name="capability_speech_synthesize" value="<?php echo esc_attr( (string) ( $limits['capabilities']['speech_synthesize'] ?? 0 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>Müzik üretimi</label><input type="number" min="0" step="0.01" name="capability_music_generate" value="<?php echo esc_attr( (string) ( $limits['capabilities']['music_generate'] ?? 0 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>Kaynak plugin tavanları</label><textarea name="plugin_limits" rows="5" placeholder="agfo-poem-translator=10.00"><?php echo esc_textarea( trim( $plugin_limits_text ) ); ?></textarea><p class="description">Her satır <code>plugin-slug=tutar</code>. 0 veya boş değer sınırsızdır.</p></div>
                        </section>
                        <section class="agfo-ops-card">
                            <h2>Fiyat varsayımları</h2>
                            <div class="agfo-field-row"><label>OpenAI / 1000 karakter</label><input type="number" min="0" step="0.000001" name="rate_openai_tts" value="<?php echo esc_attr( (string) ( $rates['openai']['gpt-4o-mini-tts']['per_1000_characters'] ?? 0 ) ); ?>"><p class="description">Güncel sözleşme fiyatınızı girin. 0 ise ön uçuş tahmini yapılır ancak parasal rezervasyon uygulanmaz.</p></div>
                            <div class="agfo-field-row"><label>ElevenLabs Multilingual / 1000 karakter</label><input type="number" min="0" step="0.000001" name="rate_elevenlabs_multilingual" value="<?php echo esc_attr( (string) ( $rates['elevenlabs']['eleven_multilingual_v2']['per_1000_characters'] ?? 0.10 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>ElevenLabs Flash / 1000 karakter</label><input type="number" min="0" step="0.000001" name="rate_elevenlabs_flash" value="<?php echo esc_attr( (string) ( $rates['elevenlabs']['eleven_flash_v2_5']['per_1000_characters'] ?? 0.05 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>MiniMax HD / 1000 karakter</label><input type="number" min="0" step="0.000001" name="rate_minimax_hd" value="<?php echo esc_attr( (string) ( $rates['minimax']['speech-2.8-hd']['per_1000_characters'] ?? 0.10 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>MiniMax Turbo / 1000 karakter</label><input type="number" min="0" step="0.000001" name="rate_minimax_turbo" value="<?php echo esc_attr( (string) ( $rates['minimax']['speech-2.8-turbo']['per_1000_characters'] ?? 0.06 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>ElevenLabs Music / dakika</label><input type="number" min="0" step="0.000001" name="rate_elevenlabs_music" value="<?php echo esc_attr( (string) ( $rates['elevenlabs']['music_v1']['per_minute'] ?? 0 ) ); ?>"><p class="description">ElevenLabs kredi sözleşmenize göre girin; 0 ise parasal rezervasyon yapılmaz.</p></div>
                            <div class="agfo-field-row"><label>MiniMax Music / şarkı</label><input type="number" min="0" step="0.000001" name="rate_minimax_music" value="<?php echo esc_attr( (string) ( $rates['minimax']['music-2.6']['per_song'] ?? 0.15 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>Gemini Lyria Clip / şarkı</label><input type="number" min="0" step="0.000001" name="rate_gemini_lyria_clip" value="<?php echo esc_attr( (string) ( $rates['gemini']['lyria-3-clip-preview']['per_request'] ?? 0.04 ) ); ?>"></div>
                            <div class="agfo-field-row"><label>Gemini Lyria Pro / şarkı</label><input type="number" min="0" step="0.000001" name="rate_gemini_lyria_pro" value="<?php echo esc_attr( (string) ( $rates['gemini']['lyria-3-pro-preview']['per_request'] ?? 0.08 ) ); ?>"></div>
                        </section>
                        <section class="agfo-ops-card">
                            <h2>MiniMax Audio Subscription yerel takibi</h2>
                            <div class="agfo-field-row"><label>Aylık audio point kotası</label><input type="number" min="0" step="1" name="minimax_audio_monthly_quota" value="<?php echo esc_attr( (string) get_option( 'agfo_ai_minimax_audio_monthly_quota', 100000 ) ); ?>"><p class="description">Starter plan için 100000. Bu değer MiniMax portalından canlı okunmaz; AGFO’nun yerel kalan tahmininin üst sınırıdır.</p></div>
                            <div class="agfo-field-row"><label>Aylık sıfırlama günü</label><input type="number" min="1" max="28" step="1" name="minimax_audio_reset_day" value="<?php echo esc_attr( (string) get_option( 'agfo_ai_minimax_audio_reset_day', 1 ) ); ?>"><p class="description">Aboneliğiniz ayın 1’inde başladığı için varsayılan 1’dir. Yalnız yerel dönem hesabını etkiler.</p></div>
                        </section>
                        <section class="agfo-ops-card">
                            <h2>Acil durdurma</h2>
                            <label class="agfo-check-row"><input type="checkbox" name="disable_tts" value="1" <?php checked( ! empty( $switch['speech_synthesize'] ) ); ?>> Metinden Sese (TTS) isteklerini durdur</label>
                            <label class="agfo-check-row"><input type="checkbox" name="disable_music" value="1" <?php checked( ! empty( $switch['music_generate'] ) ); ?>> Müzik üretimi isteklerini durdur</label>
                            <p class="description">Açıkken yeni TTS veya müzik işleri reddedilir; kuyruktaki işler de worker aşamasında güvenli biçimde durur.</p>
                        </section>
                    </div>
                    <p><button class="button button-primary">Ayarları Kaydet</button></p>
                </form>

                <section class="agfo-ops-card">
                    <h2>Son 30 gün kullanımı</h2>
                    <p><strong>Bu ay:</strong> $<?php echo esc_html( number_format_i18n( class_exists( 'AGFO_AIM_Usage' ) ? AGFO_AIM_Usage::month_spend() : 0, 6 ) ); ?></p>
                    <table class="widefat striped"><thead><tr><th>Sağlayıcı</th><th>Yetenek</th><th>Kaynak plugin</th><th>Çağrı</th><th>Birim</th><th>Maliyet</th></tr></thead><tbody>
                    <?php if ( ! $summary ) : ?><tr><td colspan="6">Henüz kullanım kaydı yok.</td></tr><?php else : foreach ( $summary as $row ) : ?>
                        <tr><td><?php echo esc_html( (string) $row['provider'] ); ?></td><td><?php echo esc_html( (string) $row['capability'] ); ?></td><td><?php echo esc_html( (string) $row['source_plugin'] ); ?></td><td><?php echo esc_html( (int) $row['calls'] ); ?></td><td><?php echo esc_html( number_format_i18n( (float) $row['input_units'], 0 ) ); ?></td><td>$<?php echo esc_html( number_format_i18n( (float) $row['cost'], 6 ) ); ?></td></tr>
                    <?php endforeach; endif; ?></tbody></table>
                </section>
            </div>
            <?php
        }

        public static function save_governance(): void {
            self::guard();
            check_admin_referer( 'agfo_ai_save_governance' );

            $plugin_limits = [];
            $plugin_lines  = preg_split( '/\r\n|\r|\n/', sanitize_textarea_field( wp_unslash( (string) ( $_POST['plugin_limits'] ?? '' ) ) ) );
            foreach ( is_array( $plugin_lines ) ? $plugin_lines : [] as $line ) {
                if ( false === strpos( $line, '=' ) ) {
                    continue;
                }
                [ $plugin_slug, $plugin_limit ] = array_map( 'trim', explode( '=', $line, 2 ) );
                $plugin_slug  = sanitize_key( $plugin_slug );
                $plugin_limit = max( 0, (float) $plugin_limit );
                if ( '' !== $plugin_slug && $plugin_limit > 0 ) {
                    $plugin_limits[ $plugin_slug ] = $plugin_limit;
                }
            }

            $limits = [
                'global_monthly' => max( 0, (float) ( $_POST['global_monthly'] ?? 0 ) ),
                'providers'      => [
                    'openai'     => max( 0, (float) ( $_POST['provider_openai'] ?? 0 ) ),
                    'elevenlabs' => max( 0, (float) ( $_POST['provider_elevenlabs'] ?? 0 ) ),
                    'minimax'     => max( 0, (float) ( $_POST['provider_minimax'] ?? 0 ) ),
                    'gemini'      => max( 0, (float) ( $_POST['provider_gemini'] ?? 0 ) ),
                ],
                'capabilities'   => [
                    'speech_synthesize' => max( 0, (float) ( $_POST['capability_speech_synthesize'] ?? 0 ) ),
                    'music_generate'    => max( 0, (float) ( $_POST['capability_music_generate'] ?? 0 ) ),
                ],
                'plugins'        => $plugin_limits,
                'warning_ratio'  => 0.8,
            ];
            update_option( AGFO_AIM_Budget::OPTION, $limits, false );

            $rates = get_option( 'agfo_ai_pricing_rates', [] );
            if ( ! is_array( $rates ) ) {
                $rates = [];
            }
            $rates['openai']['gpt-4o-mini-tts']['per_1000_characters']             = max( 0, (float) ( $_POST['rate_openai_tts'] ?? 0 ) );
            $rates['elevenlabs']['eleven_multilingual_v2']['per_1000_characters']  = max( 0, (float) ( $_POST['rate_elevenlabs_multilingual'] ?? 0.10 ) );
            $rates['elevenlabs']['eleven_flash_v2_5']['per_1000_characters']       = max( 0, (float) ( $_POST['rate_elevenlabs_flash'] ?? 0.05 ) );
            $rates['minimax']['speech-2.8-hd']['per_1000_characters']                  = max( 0, (float) ( $_POST['rate_minimax_hd'] ?? 0.10 ) );
            $rates['minimax']['speech-2.8-turbo']['per_1000_characters']               = max( 0, (float) ( $_POST['rate_minimax_turbo'] ?? 0.06 ) );
            $rates['elevenlabs']['music_v1']['per_minute']                            = max( 0, (float) ( $_POST['rate_elevenlabs_music'] ?? 0 ) );
            $rates['elevenlabs']['music_v2']['per_minute']                            = max( 0, (float) ( $_POST['rate_elevenlabs_music'] ?? 0 ) );
            $rates['minimax']['music-2.6']['per_song']                                = max( 0, (float) ( $_POST['rate_minimax_music'] ?? 0.15 ) );
            $rates['gemini']['lyria-3-clip-preview']['per_request']                   = max( 0, (float) ( $_POST['rate_gemini_lyria_clip'] ?? 0.04 ) );
            $rates['gemini']['lyria-3-pro-preview']['per_request']                    = max( 0, (float) ( $_POST['rate_gemini_lyria_pro'] ?? 0.08 ) );
            update_option( 'agfo_ai_pricing_rates', $rates, false );

            update_option( 'agfo_ai_minimax_audio_monthly_quota', max( 0, absint( $_POST['minimax_audio_monthly_quota'] ?? 100000 ) ), false );
            update_option( 'agfo_ai_minimax_audio_reset_day', max( 1, min( 28, absint( $_POST['minimax_audio_reset_day'] ?? 1 ) ) ), false );

            AGFO_AIM_Kill_Switch::set_disabled( 'speech_synthesize', ! empty( $_POST['disable_tts'] ), get_current_user_id() );
            AGFO_AIM_Kill_Switch::set_disabled( 'music_generate', ! empty( $_POST['disable_music'] ), get_current_user_id() );
            wp_safe_redirect( admin_url( 'admin.php?page=agfo-ai-costs&saved=1' ) );
            exit;
        }

        public static function retry_job(): void {
            self::guard();
            $uuid = isset( $_GET['job_uuid'] ) ? sanitize_text_field( wp_unslash( (string) $_GET['job_uuid'] ) ) : '';
            check_admin_referer( 'agfo_ai_retry_job_' . $uuid );
            $job = AGFO_AIM_Job_Store::get( $uuid );
            if ( ! is_array( $job ) || 'failed' !== $job['status'] ) {
                wp_die( 'Yeniden denenebilir iş bulunamadı.' );
            }
            global $wpdb;
            $table = AGFO_AIM_Schema::jobs_table();
            $wpdb->query(
                $wpdb->prepare(
                    "UPDATE {$table} SET status='draft', attempts=0, next_run_at=NULL, completed_at=NULL,
                     error_code='', error_message='', updated_at=%s WHERE id=%d AND status='failed'",
                    current_time( 'mysql' ),
                    (int) $job['id']
                )
            );
            $reserved = AGFO_AIM_Budget::reserve(
                (int) $job['id'],
                [
                    'cost_estimate' => (float) $job['cost_estimate'],
                    'provider'      => (string) $job['provider'],
                    'capability'    => (string) $job['capability'],
                    'source_plugin' => (string) $job['source_plugin'],
                ]
            );
            if ( is_wp_error( $reserved ) ) {
                $wpdb->update(
                    $table,
                    [ 'status' => 'failed', 'error_code' => $reserved->get_error_code(), 'error_message' => $reserved->get_error_message(), 'updated_at' => current_time( 'mysql' ) ],
                    [ 'id' => (int) $job['id'] ],
                    [ '%s', '%s', '%s', '%s' ],
                    [ '%d' ]
                );
                wp_die( esc_html( $reserved->get_error_message() ) );
            }
            if ( ! AGFO_AIM_Job_Store::queue( (int) $job['id'] ) ) {
                AGFO_AIM_Budget::settle( (int) $job['id'], 0.0 );
                wp_die( 'İş yeniden kuyruğa alınamadı.' );
            }
            AGFO_AIM_Job_Worker::kick();
            wp_safe_redirect( admin_url( 'admin.php?page=agfo-ai-jobs' ) );
            exit;
        }

        private static function guard(): void {
            if ( ! current_user_can( 'manage_options' ) ) {
                wp_die( esc_html__( 'Bu sayfaya erişim yetkiniz yok.', 'agfo-ai-manager' ) );
            }
        }
    }
}
