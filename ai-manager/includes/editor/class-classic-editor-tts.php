<?php
/**
 * Classic page editor TTS modal integration.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Classic_Editor_TTS' ) ) {
    final class AGFO_AIM_Classic_Editor_TTS {
        private static bool $rendered = false;

        public static function register_hooks(): void {
            add_action( 'admin_enqueue_scripts', [ __CLASS__, 'enqueue_assets' ], 30 );
            add_action( 'media_buttons', [ __CLASS__, 'render_media_button' ], 25, 1 );
            add_action( 'edit_form_after_title', [ __CLASS__, 'render_guaranteed_launcher' ], 5, 1 );
            add_action( 'admin_footer-post.php', [ __CLASS__, 'render_modal' ] );
            add_action( 'admin_footer-post-new.php', [ __CLASS__, 'render_modal' ] );
        }

        public static function enqueue_assets( string $hook ): void {
            if ( ! self::is_target_screen( $hook ) ) {
                return;
            }

            $css             = AGFO_AIM_PLUGIN_DIR . 'assets/css/classic-editor-tts.css';
            $js              = AGFO_AIM_PLUGIN_DIR . 'assets/js/classic-editor-tts.js';

            wp_enqueue_style(
                'agfo-ai-classic-editor-tts',
                AGFO_AIM_PLUGIN_URL . 'assets/css/classic-editor-tts.css',
                [],
                file_exists( $css ) ? AGFO_AIM_VERSION . '.' . filemtime( $css ) : AGFO_AIM_VERSION
            );
            wp_enqueue_script(
                'agfo-ai-classic-editor-tts',
                AGFO_AIM_PLUGIN_URL . 'assets/js/classic-editor-tts.js',
                [ 'jquery' ],
                file_exists( $js ) ? AGFO_AIM_VERSION . '.' . filemtime( $js ) : AGFO_AIM_VERSION,
                true
            );

            $post_id    = isset( $_GET['post'] ) ? absint( $_GET['post'] ) : 0;
            $post_title = $post_id ? get_the_title( $post_id ) : '';
            $routing    = function_exists( 'agfo_get_capability_routing' ) ? agfo_get_capability_routing() : [];
            $saved      = is_array( $routing['speech_synthesize'] ?? null ) ? $routing['speech_synthesize'] : [];
            $openai     = function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'openai' ) );
            $eleven     = function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'elevenlabs' ) );
            $minimax    = function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'minimax' ) );
            $ema        = class_exists( 'AGFO_AIM_Adapter_EMA' ) && function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'ema' ) );
            $default    = sanitize_key( (string) ( $saved['provider'] ?? '' ) );
            $effects    = class_exists( 'AGFO_AIM_Audio_Effects' ) ? AGFO_AIM_Audio_Effects::status() : [ 'available' => false, 'reason' => 'Ses efekti motoru yüklenmedi.', 'path' => '' ];
            $allowed    = [ 'openai' => $openai, 'elevenlabs' => $eleven, 'minimax' => $minimax, 'ema' => $ema ];
            if ( empty( $allowed[ $default ] ) ) {
                $default = $eleven ? 'elevenlabs' : ( $minimax ? 'minimax' : ( $openai ? 'openai' : ( $ema ? 'ema' : '' ) ) );
            }

            wp_localize_script(
                'agfo-ai-classic-editor-tts',
                'agfoClassicTts',
                [
                    'ajaxUrl'         => admin_url( 'admin-ajax.php' ),
                    'nonce'           => wp_create_nonce( 'agfo_ajax_nonce' ),
                    'pollMs'          => 2500,
                    'postId'          => $post_id,
                    'postTitle'       => sanitize_text_field( (string) $post_title ),
                    'defaultProvider' => $default,
                    'catalogs'        => [
                        'openai'     => class_exists( 'AGFO_AIM_TTS_Catalog' ) ? AGFO_AIM_TTS_Catalog::openai_catalog() : [],
                        'elevenlabs' => class_exists( 'AGFO_AIM_TTS_Catalog' ) ? AGFO_AIM_TTS_Catalog::elevenlabs_fallback_catalog() : [],
                        'minimax'     => class_exists( 'AGFO_AIM_TTS_Catalog' ) ? AGFO_AIM_TTS_Catalog::minimax_fallback_catalog() : [],
                        'ema'         => class_exists( 'AGFO_AIM_Adapter_EMA' ) ? AGFO_AIM_Adapter_EMA::catalog( false ) : [],
                    ],
                    'hasKeys'         => [
                        'openai'     => $openai,
                        'elevenlabs' => $eleven,
                        'minimax'     => $minimax,
                        'ema'         => $ema,
                    ],
                    'audioEffects'    => [
                        'available' => ! empty( $effects['available'] ),
                        'reason'    => sanitize_text_field( (string) ( $effects['reason'] ?? '' ) ),
                    ],
                    'messages'        => [
                        'queued'         => 'İş kuyruğa alındı.',
                        'processing'     => 'Ses üretiliyor…',
                        'storing'        => 'Ses Medya Kütüphanesine ve güvenli depoya aktarılıyor…',
                        'complete'       => 'Ses üretimi tamamlandı.',
                        'failed'         => 'Ses üretimi başarısız oldu.',
                        'catalogLoading' => 'Model ve ses seçenekleri yükleniyor…',
                        'catalogReady'   => 'Model ve ses seçenekleri hazır.',
                        'catalogEmpty'   => 'Bu hesap için ses bulunamadı.',
                    ],
                ]
            );
        }

        public static function render_media_button( string $editor_id ): void {
            if ( ! current_user_can( self::required_capability() ) ) {
                return;
            }
            if ( 'content' !== $editor_id ) {
                return;
            }
            printf(
                '<button type="button" class="button agfo-classic-tts-open agfo-classic-tts-toolbar-button" data-editor="%1$s" aria-haspopup="dialog" aria-controls="agfo-classic-tts-modal"><span class="dashicons dashicons-controls-volumeon" aria-hidden="true"></span> %2$s</button>',
                esc_attr( $editor_id ),
                esc_html__( 'Seslendir', 'agfo-ai-manager' )
            );
        }

        public static function render_guaranteed_launcher( $post = null ): void {
            if ( ! current_user_can( self::required_capability() ) ) {
                return;
            }
            ?>
            <div class="agfo-classic-tts-guaranteed-launcher" data-agfo-tts-launcher="1">
                <div class="agfo-classic-tts-guaranteed-copy">
                    <strong><span class="dashicons dashicons-superhero-alt" aria-hidden="true"></span> AGFO İçerik Stüdyosu</strong>
                    <span class="agfo-content-launcher-note">Metni AI ile düzenleyin veya OpenAI, ElevenLabs, MiniMax ve EMA Lightning ile seslendirin.</span>
                </div>
                <div class="agfo-classic-tts-guaranteed-actions">
                    <button type="button" class="button agfo-classic-content-open" data-editor="content" aria-haspopup="dialog" aria-controls="agfo-classic-content-modal"><span class="dashicons dashicons-edit-page" aria-hidden="true"></span> AI Düzenle</button>
                    <button type="button" class="button button-primary agfo-classic-tts-open agfo-classic-tts-guaranteed-button" data-editor="content" aria-haspopup="dialog" aria-controls="agfo-classic-tts-modal">Seslendir</button>
                </div>
            </div>
            <?php
        }

        public static function render_modal(): void {
            if ( self::$rendered || ! current_user_can( self::required_capability() ) ) {
                return;
            }
            self::$rendered = true;
            $openai         = function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'openai' ) );
            $eleven         = function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'elevenlabs' ) );
            $minimax        = function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'minimax' ) );
            $ema            = class_exists( 'AGFO_AIM_Adapter_EMA' ) && function_exists( 'agfo_get_api_key' ) && ! empty( agfo_get_api_key( 'ema' ) );
            $ema_available  = class_exists( 'AGFO_AIM_Adapter_EMA' );
            $ema_settings   = $ema_available ? AGFO_AIM_Adapter_EMA::settings() : [];
            $effects        = class_exists( 'AGFO_AIM_Audio_Effects' ) ? AGFO_AIM_Audio_Effects::status() : [ 'available' => false, 'reason' => 'Ses efekti motoru yüklenmedi.' ];
            ?>
            <div id="agfo-classic-tts-overlay" class="agfo-classic-tts-overlay" hidden></div>
            <section id="agfo-classic-tts-modal" class="agfo-classic-tts-modal" role="dialog" aria-modal="true" aria-labelledby="agfo-classic-tts-title" hidden>
                <header class="agfo-classic-tts-header">
                    <div>
                        <h2 id="agfo-classic-tts-title"><span class="dashicons dashicons-controls-volumeon" aria-hidden="true"></span> Sayfayı Seslendir</h2>
                        <p>Seçili metni veya sayfa içeriğini OpenAI, ElevenLabs, MiniMax veya EMA Lightning (Türkçe, ücretsiz) ile sese dönüştürün.</p>
                    </div>
                    <button type="button" class="agfo-classic-tts-close" aria-label="Kapat">×</button>
                </header>

                <div class="agfo-classic-tts-body">
                    <?php if ( ! $openai && ! $eleven && ! $minimax && ! $ema ) : ?>
                        <div class="notice notice-error inline"><p>Önce AGFO AI → Sağlayıcılar ekranında OpenAI, ElevenLabs veya MiniMax API anahtarı ya da EMA Lightning servis token’ı kaydedin.</p></div>
                    <?php endif; ?>

                    <div class="agfo-classic-tts-quota-bar" aria-label="TTS kredi durumu">
                        <div class="agfo-classic-tts-quota-item" data-quota-provider="elevenlabs">
                            <strong>ElevenLabs</strong>
                            <span class="agfo-classic-tts-quota-value">—</span>
                            <small>canlı kredi bekleniyor</small>
                        </div>
                        <div class="agfo-classic-tts-quota-item" data-quota-provider="minimax">
                            <strong>MiniMax</strong>
                            <span class="agfo-classic-tts-quota-value">—</span>
                            <small>yerel tahmin bekleniyor</small>
                        </div>
                        <button type="button" class="button button-small" id="agfo-classic-tts-refresh-quota">Kredileri yenile</button>
                    </div>

                    <div class="agfo-classic-tts-sourcebar">
                        <button type="button" class="button" id="agfo-classic-tts-use-selection">Seçili metni al</button>
                        <button type="button" class="button" id="agfo-classic-tts-use-all">Tüm sayfayı al</button>
                        <span id="agfo-classic-tts-source-note">Metin editörden alınacak.</span>
                    </div>

                    <form id="agfo-classic-tts-form">
                        <input type="hidden" id="agfo-classic-tts-editor-id" value="content">

                        <div class="agfo-classic-tts-grid agfo-classic-tts-grid-three">
                            <label>
                                <span>Sağlayıcı</span>
                                <select id="agfo-classic-tts-provider" name="provider" <?php disabled( ! $openai && ! $eleven && ! $minimax && ! $ema_available ); ?>>
                                    <?php if ( $eleven ) : ?><option value="elevenlabs">ElevenLabs</option><?php endif; ?>
                                    <?php if ( $minimax ) : ?><option value="minimax">MiniMax</option><?php endif; ?>
                                    <?php if ( $openai ) : ?><option value="openai">OpenAI</option><?php endif; ?>
                                    <?php if ( $ema_available ) : ?><option value="ema"><?php echo esc_html( 'EMA Lightning (yerel, Türkçe)' . ( $ema ? '' : ' — token gerekli' ) ); ?></option><?php endif; ?>
                                </select>
                            </label>
                            <label>
                                <span>Ses biçimi</span>
                                <select id="agfo-classic-tts-format" name="format">
                                    <option value="mp3">MP3</option>
                                    <option value="wav">WAV</option>
                                    <option value="opus">Opus</option>
                                    <option value="aac">AAC</option>
                                    <option value="flac">FLAC</option>
                                    <option value="pcm">PCM</option>
                                    <option value="ulaw">μ-law</option>
                                    <option value="alaw">A-law</option>
                                </select>
                            </label>
                            <label>
                                <span>Hız</span>
                                <input id="agfo-classic-tts-speed" name="speed" type="number" min="0.25" max="4" step="0.05" value="1">
                            </label>
                        </div>

                        <section class="agfo-classic-tts-effects-panel" aria-labelledby="agfo-classic-tts-effects-title">
                            <div class="agfo-classic-tts-effects-heading">
                                <div>
                                    <strong id="agfo-classic-tts-effects-title">Reverb / Echo</strong>
                                    <small>Efekt, üretim tamamlandıktan sonra FFmpeg ile nihai ses dosyasına kalıcı olarak uygulanır.</small>
                                </div>
                                <span class="agfo-classic-tts-effects-state <?php echo ! empty( $effects['available'] ) ? 'is-ready' : 'is-unavailable'; ?>">
                                    <?php echo ! empty( $effects['available'] ) ? 'FFmpeg hazır' : 'FFmpeg kullanılamıyor'; ?>
                                </span>
                            </div>
                            <div class="agfo-classic-tts-grid agfo-classic-tts-grid-two">
                                <label>
                                    <span>Ses efekti</span>
                                    <select id="agfo-classic-tts-audio-effect" name="audio_effect">
                                        <option value="none">Efektsiz / kuru</option>
                                        <option value="warm_room" <?php disabled( empty( $effects['available'] ) ); ?>>Hafif reverb · sıcak oda</option>
                                        <option value="soft_echo" <?php disabled( empty( $effects['available'] ) ); ?>>Yumuşak echo</option>
                                        <option value="hall" <?php disabled( empty( $effects['available'] ) ); ?>>Belirgin salon reverbü</option>
                                    </select>
                                </label>
                                <label>
                                    <span>Etki miktarı: <output id="agfo-classic-tts-effect-amount-output" for="agfo-classic-tts-effect-amount">35%</output></span>
                                    <input id="agfo-classic-tts-effect-amount" name="effect_amount" type="range" min="0" max="100" step="1" value="35" disabled>
                                    <small id="agfo-classic-tts-effect-help"><?php echo esc_html( (string) ( $effects['reason'] ?? '' ) ); ?></small>
                                </label>
                            </div>
                        </section>

                        <section class="agfo-classic-tts-provider-panel" data-provider-panel="openai" hidden>
                            <div class="agfo-classic-tts-grid agfo-classic-tts-grid-two">
                                <label>
                                    <span>OpenAI TTS modeli</span>
                                    <select id="agfo-classic-tts-model-openai"></select>
                                    <input id="agfo-classic-tts-model-openai-manual" type="text" placeholder="OpenAI model kimliği" hidden>
                                    <small id="agfo-classic-tts-openai-model-help"></small>
                                </label>
                                <label>
                                    <span>OpenAI sesi</span>
                                    <select id="agfo-classic-tts-voice-openai"></select>
                                </label>
                            </div>
                        </section>

                        <section class="agfo-classic-tts-provider-panel" data-provider-panel="elevenlabs" hidden>
                            <div id="agfo-classic-tts-eleven-status" class="agfo-classic-tts-catalog-status">ElevenLabs seçenekleri hazırlanıyor…</div>
                            <div class="agfo-classic-tts-grid agfo-classic-tts-grid-two">
                                <label>
                                    <span>ElevenLabs TTS modeli</span>
                                    <select id="agfo-classic-tts-model-elevenlabs"></select>
                                    <input id="agfo-classic-tts-model-elevenlabs-manual" type="text" placeholder="ElevenLabs model kimliği" hidden>
                                    <small id="agfo-classic-tts-eleven-model-help"></small>
                                </label>
                                <label>
                                    <span>ElevenLabs sesi</span>
                                    <input id="agfo-classic-tts-voice-search" type="search" placeholder="Ses, dil, aksan veya kategori ara" autocomplete="off">
                                    <select id="agfo-classic-tts-voice-elevenlabs"></select>
                                    <input id="agfo-classic-tts-voice-elevenlabs-manual" type="text" placeholder="ElevenLabs Voice ID" hidden>
                                    <small id="agfo-classic-tts-eleven-voice-help"></small>
                                </label>
                            </div>
                            <p><button type="button" class="button button-small" id="agfo-classic-tts-refresh-eleven">ElevenLabs listesini yenile</button></p>

                            <details class="agfo-classic-tts-details">
                                <summary>ElevenLabs gelişmiş ayarları</summary>
                                <div class="agfo-classic-tts-grid agfo-classic-tts-grid-three">
                                    <label><span>Dil</span><select id="agfo-classic-tts-language" name="language"><option value="">Otomatik algıla</option></select></label>
                                    <label><span>Stability</span><input id="agfo-classic-tts-stability" name="stability" type="number" min="0" max="1" step="0.01" placeholder="Ses varsayılanı"></label>
                                    <label><span>Similarity boost</span><input id="agfo-classic-tts-similarity" name="similarity_boost" type="number" min="0" max="1" step="0.01" placeholder="Ses varsayılanı"></label>
                                    <label><span>Style</span><input id="agfo-classic-tts-style" name="style" type="number" min="0" max="1" step="0.01" placeholder="Model varsayılanı"></label>
                                    <label><span>Speaker boost</span><select id="agfo-classic-tts-speaker-boost" name="use_speaker_boost"><option value="">Ses varsayılanı</option><option value="1">Açık</option><option value="0">Kapalı</option></select></label>
                                </div>
                            </details>
                        </section>

                        <section class="agfo-classic-tts-provider-panel" data-provider-panel="minimax" hidden>
                            <div id="agfo-classic-tts-minimax-status" class="agfo-classic-tts-catalog-status">MiniMax seçenekleri hazırlanıyor…</div>
                            <div class="agfo-classic-tts-grid agfo-classic-tts-grid-two">
                                <label>
                                    <span>MiniMax TTS modeli</span>
                                    <select id="agfo-classic-tts-model-minimax"></select>
                                    <input id="agfo-classic-tts-model-minimax-manual" type="text" placeholder="MiniMax model kimliği" hidden>
                                    <small id="agfo-classic-tts-minimax-model-help"></small>
                                </label>
                                <label>
                                    <span>MiniMax sesi</span>
                                    <input id="agfo-classic-tts-voice-minimax-search" type="search" placeholder="Ses adı, Voice ID veya kategori ara" autocomplete="off">
                                    <select id="agfo-classic-tts-voice-minimax"></select>
                                    <input id="agfo-classic-tts-voice-minimax-manual" type="text" placeholder="MiniMax Voice ID" hidden>
                                    <small id="agfo-classic-tts-minimax-voice-help"></small>
                                </label>
                            </div>
                            <p><button type="button" class="button button-small" id="agfo-classic-tts-refresh-minimax" <?php disabled( ! $minimax ); ?>>MiniMax listesini yenile</button></p>

                            <details class="agfo-classic-tts-details">
                                <summary>MiniMax gelişmiş ayarları</summary>
                                <div class="agfo-classic-tts-grid agfo-classic-tts-grid-three">
                                    <label><span>Dil güçlendirme</span><select id="agfo-classic-tts-minimax-language"><option value="auto">Otomatik algıla</option><option value="Turkish">Türkçe</option><option value="English">İngilizce</option><option value="German">Almanca</option><option value="French">Fransızca</option><option value="Spanish">İspanyolca</option><option value="Italian">İtalyanca</option><option value="Arabic">Arapça</option><option value="Russian">Rusça</option></select></label>
                                    <label><span>Ses düzeyi</span><input id="agfo-classic-tts-minimax-volume" type="number" min="0.1" max="10" step="0.1" value="1"></label>
                                    <label><span>Perde</span><input id="agfo-classic-tts-minimax-pitch" type="number" min="-12" max="12" step="1" value="0"></label>
                                    <label><span>Duygu</span><select id="agfo-classic-tts-minimax-emotion"><option value="">Model varsayılanı</option><option value="happy">Mutlu</option><option value="sad">Hüzünlü</option><option value="angry">Öfkeli</option><option value="fearful">Korkulu</option><option value="surprised">Şaşkın</option><option value="calm">Sakin</option><option value="fluent">Akıcı</option><option value="whisper">Fısıltı</option></select></label>
                                    <label><span>Örnekleme</span><select id="agfo-classic-tts-minimax-sample-rate"><option value="32000">32000 Hz</option><option value="44100">44100 Hz</option><option value="24000">24000 Hz</option><option value="22050">22050 Hz</option><option value="16000">16000 Hz</option><option value="8000">8000 Hz</option></select></label>
                                    <label><span>Bitrate</span><select id="agfo-classic-tts-minimax-bitrate"><option value="128000">128 kbps</option><option value="256000">256 kbps</option><option value="64000">64 kbps</option><option value="32000">32 kbps</option></select></label>
                                    <label><span>Kanal</span><select id="agfo-classic-tts-minimax-channel"><option value="1">Mono</option><option value="2">Stereo</option></select></label>
                                </div>
                                <p class="description">MiniMax seçiliyken hız aralığı 0.5–2.0 olarak uygulanır.</p>
                            </details>
                        </section>

                        <?php if ( $ema_available ) : ?>
                        <section class="agfo-classic-tts-provider-panel" data-provider-panel="ema" hidden>
                            <?php if ( ! $ema ) : ?>
                                <div class="notice notice-warning inline"><p>EMA servis token’ı tanımlı değil. <a href="<?php echo esc_url( admin_url( 'admin.php?page=agfo-ai-manager' ) ); ?>" target="_blank" rel="noopener">AGFO AI › Sağlayıcılar</a> ekranındaki “EMA Lightning (yerel TTS)” alanına sunucudaki TTS servisinin token’ını girin (veya wp-config.php içinde AGFO_TTS_TOKEN tanımlayın), sonra bu sayfayı yenileyin.</p></div>
                            <?php endif; ?>
                            <div id="agfo-classic-tts-ema-status" class="agfo-classic-tts-catalog-status">EMA servisi: <?php echo esc_html( (string) ( $ema_settings['endpoint'] ?? '' ) ); ?></div>
                            <div class="agfo-classic-tts-grid agfo-classic-tts-grid-two">
                                <label>
                                    <span>EMA modeli</span>
                                    <select id="agfo-classic-tts-model-ema"><option value="ema-lightning" selected>EMA Lightning (yerel, Türkçe)</option></select>
                                    <input id="agfo-classic-tts-voice-ema" type="hidden" value="ema">
                                    <small>Tek ses, yalnız Türkçe; karakter ücreti yok. Tek işte en fazla <?php echo esc_html( number_format_i18n( AGFO_AIM_Adapter_EMA::MAX_CHARS ) ); ?> karakter.</small>
                                </label>
                                <div class="agfo-classic-tts-grid agfo-classic-tts-grid-two">
                                    <label><span>Cümle arası (ms)</span><input id="agfo-classic-tts-ema-pause" type="number" min="0" max="2000" step="50" value="<?php echo esc_attr( (string) ( $ema_settings['pause_ms'] ?? 350 ) ); ?>"></label>
                                    <label><span>Paragraf arası (ms)</span><input id="agfo-classic-tts-ema-paragraph-pause" type="number" min="0" max="3000" step="50" value="<?php echo esc_attr( (string) ( $ema_settings['paragraph_pause_ms'] ?? 700 ) ); ?>"></label>
                                </div>
                            </div>
                            <?php if ( class_exists( 'AGFO_AIM_Speech_Script' ) ) : ?>
                            <label class="agfo-classic-tts-publish-row">
                                <input id="agfo-classic-tts-ema-script" type="checkbox" <?php checked( ! empty( $ema_settings['script_enabled'] ) ); ?>>
                                <span>Okuma metnini AI ile hazırla: yabancı adlar, sayılar, tarihler, birimler ve kısaltmalar okunduğu gibi yazılır.</span>
                            </label>
                            <p>
                                <button type="button" class="button button-small" id="agfo-classic-tts-ema-script-preview">Okuma metnini önizle</button>
                                <button type="button" class="button-link" id="agfo-classic-tts-ema-script-undo" hidden>Özgün metne dön</button>
                                <small id="agfo-classic-tts-ema-script-status" aria-live="polite"></small>
                            </p>
                            <?php endif; ?>
                            <p><button type="button" class="button button-small" id="agfo-classic-tts-refresh-ema">Bağlantıyı test et</button> <small>Telaffuz sözlüğü ve servis adresi: AGFO AI → Ses Stüdyosu → EMA servis ayarları. Hız 0.7–1.4.</small></p>
                        </section>
                        <?php endif; ?>

                        <label class="agfo-classic-tts-block-label">
                            <span>Okuma talimatı</span>
                            <textarea id="agfo-classic-tts-instructions" name="instructions" rows="2" placeholder="Örn. Sakin, olgun ve İstanbul Türkçesiyle oku."></textarea>
                            <small id="agfo-classic-tts-instructions-help"></small>
                        </label>

                        <label class="agfo-classic-tts-block-label">
                            <span>Seslendirilecek metin</span>
                            <textarea id="agfo-classic-tts-text" name="text" rows="10" maxlength="40000" required></textarea>
                            <small><strong id="agfo-classic-tts-char-count">0</strong> / <span id="agfo-classic-tts-char-limit">40000</span> karakter</small>
                        </label>

                        <label class="agfo-classic-tts-publish-row">
                            <input id="agfo-classic-tts-publish" type="checkbox" checked>
                            <span>Medya Kütüphanesine ekle ve tamamlandığında sayfa editörüne yerleştirilebilir kalıcı bir ses URL'si oluştur.</span>
                        </label>
                        <p class="description">Bu seçenek kapalıysa çıktı özel depoda kalır; önizlenebilir fakat sayfa içeriğine kalıcı olarak eklenemez.</p>
                    </form>

                    <div class="agfo-classic-tts-result" aria-live="polite">
                        <div id="agfo-classic-tts-status" class="agfo-classic-tts-status is-idle">Henüz iş başlatılmadı.</div>
                        <audio id="agfo-classic-tts-player" controls preload="metadata" hidden></audio>
                        <div class="agfo-classic-tts-result-actions">
                            <a id="agfo-classic-tts-download" class="button" href="#" hidden>Dosyayı indir</a>
                            <button type="button" id="agfo-classic-tts-insert" class="button button-primary" hidden>Editöre Ekle</button>
                            <button type="button" id="agfo-classic-tts-cancel" class="button button-link-delete" hidden>İşi iptal et</button>
                        </div>
                    </div>
                </div>

                <footer class="agfo-classic-tts-footer">
                    <span>Yapay ses kullanıldığını yayımlanan içerikte açıkça belirtmeniz önerilir.</span>
                    <div>
                        <button type="button" class="button agfo-classic-tts-close">Kapat</button>
                        <button type="submit" form="agfo-classic-tts-form" id="agfo-classic-tts-submit" class="button button-primary" <?php disabled( ! $openai && ! $eleven && ! $minimax && ! $ema ); ?>>Sesi Üret</button>
                    </div>
                </footer>
            </section>
            <?php
        }

        private static function is_target_screen( string $hook ): bool {
            // Do not depend on get_current_screen(), post type resolution or editor-mode probes here.
            // WordPress can expose those values differently when Classic Editor, page builders or
            // custom post-type integrations alter the edit screen. The UI is harmless on other
            // post edit screens and the JavaScript activates only when a content editor is present.
            return in_array( $hook, [ 'post.php', 'post-new.php' ], true )
                && current_user_can( self::required_capability() );
        }

        private static function required_capability(): string {
            return sanitize_key( (string) apply_filters( 'agfo_ai_classic_editor_tts_capability', 'manage_options' ) );
        }
    }
}
