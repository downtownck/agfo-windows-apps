<?php
/**
 * Classic Editor featured image studio integration.
 *
 * Added in 16.16.0. Mirrors the Content Studio integration: a media button on
 * the editor toolbar, a second entry point inside the Featured Image metabox
 * and one shared modal rendered on post.php / post-new.php.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Classic_Editor_Image' ) ) {
    final class AGFO_AIM_Classic_Editor_Image {
        private static bool $rendered = false;

        public static function register_hooks(): void {
            add_action( 'admin_enqueue_scripts', [ __CLASS__, 'enqueue_assets' ], 32 );
            add_action( 'media_buttons', [ __CLASS__, 'render_media_button' ], 26, 1 );
            add_action( 'admin_footer-post.php', [ __CLASS__, 'render_modal' ] );
            add_action( 'admin_footer-post-new.php', [ __CLASS__, 'render_modal' ] );
        }

        private static function is_target_screen( string $hook ): bool {
            return in_array( $hook, [ 'post.php', 'post-new.php' ], true )
                && current_user_can( AGFO_AIM_Image_Generator::required_capability() );
        }

        /**
         * Image models offered in the studio, per provider.
         *
         * Added in 17.0.1. Starts from the curated catalog and adds image-capable ids found in
         * the provider model lists downloaded under AI Kontrol Merkezi, so new image models
         * appear without a code change.
         *
         * @return array<string,array<int,array{id:string,label:string}>>
         */
        public static function model_options(): array {
            $catalog = AGFO_AIM_Image_Adapter::model_catalog();
            foreach ( AGFO_AIM_Image_Adapter::supported_providers() as $provider ) {
                $rows  = isset( $catalog[ $provider ] ) && is_array( $catalog[ $provider ] ) ? $catalog[ $provider ] : [];
                $known = array_map( static function ( $row ) { return strtolower( (string) ( $row['id'] ?? '' ) ); }, $rows );
                $list  = get_option( 'agfo_models_' . $provider, [] );
                if ( is_array( $list ) ) {
                    foreach ( $list as $item ) {
                        $id = is_array( $item ) ? (string) ( $item['id'] ?? $item['name'] ?? '' ) : (string) $item;
                        $id = trim( str_replace( 'models/', '', $id ) );
                        if ( '' === $id || in_array( strtolower( $id ), $known, true ) ) {
                            continue;
                        }
                        if ( ! preg_match( '/gpt-image|dall-e|imagen|-image(-|$)|flux|recraft|image-0/i', $id ) ) {
                            continue;
                        }
                        $rows[]  = [ 'id' => $id, 'label' => $id ];
                        $known[] = strtolower( $id );
                    }
                }
                $catalog[ $provider ] = $rows;
            }
            return $catalog;
        }

        public static function enqueue_assets( string $hook ): void {
            if ( ! self::is_target_screen( $hook ) ) {
                return;
            }

            $css = AGFO_AIM_PLUGIN_DIR . 'assets/css/classic-editor-image.css';
            $js  = AGFO_AIM_PLUGIN_DIR . 'assets/js/classic-editor-image.js';

            wp_enqueue_style(
                'agfo-ai-classic-editor-image',
                AGFO_AIM_PLUGIN_URL . 'assets/css/classic-editor-image.css',
                [],
                file_exists( $css ) ? AGFO_AIM_VERSION . '.' . filemtime( $css ) : AGFO_AIM_VERSION
            );
            wp_enqueue_script(
                'agfo-ai-classic-editor-image',
                AGFO_AIM_PLUGIN_URL . 'assets/js/classic-editor-image.js',
                [ 'jquery' ],
                file_exists( $js ) ? AGFO_AIM_VERSION . '.' . filemtime( $js ) : AGFO_AIM_VERSION,
                true
            );

            $effective = AGFO_AIM_Image_Generator::effective_default();
            $settings  = AGFO_AIM_Image_Generator::settings();

            wp_localize_script(
                'agfo-ai-classic-editor-image',
                'agfoClassicImage',
                [
                    'ajaxUrl'   => admin_url( 'admin-ajax.php' ),
                    'nonce'     => wp_create_nonce( 'agfo_ajax_nonce' ),
                    'postId'    => (int) get_the_ID(),
                    'presets'   => AGFO_AIM_Image_Prompt_Library::public_catalog(),
                    'models'    => self::model_options(), // CHANGED 17.0.1: catalog + image models found in downloaded lists.
                    'defaults'  => [
                        'provider' => $effective['provider'],
                        'model'    => $effective['model'],
                        'aspect'   => $settings['aspect'],
                        'preset'   => $settings['preset'],
                        'quality'  => $settings['quality'],
                    ],
                    'promptUrl' => admin_url( 'admin.php?page=agfo-image-prompts' ),
                    'messages'  => [
                        'idle'      => 'Henüz görsel üretilmedi.',
                        'working'   => 'Görsel üretiliyor… Bu işlem bir dakikayı aşabilir.',
                        'briefing'  => 'Yazının içeriğinden görsel özeti çıkarılıyor…',
                        'complete'  => 'Görsel hazır ve medya kütüphanesine kaydedildi.',
                        'failed'    => 'Görsel üretilemedi.',
                        'featured'  => 'Öne çıkan görsel olarak atandı.',
                        'noSubject' => 'Konu bulunamadı. Yazıya başlık ekleyin ya da bir prompt yazın.',
                    ],
                ]
            );
        }

        public static function render_media_button( string $editor_id ): void {
            if ( ! current_user_can( AGFO_AIM_Image_Generator::required_capability() ) || 'content' !== $editor_id ) {
                return;
            }
            printf(
                '<button type="button" class="button agfo-classic-image-open agfo-classic-image-toolbar-button" data-editor="%1$s" aria-haspopup="dialog" aria-controls="agfo-classic-image-modal"><span class="dashicons dashicons-format-image" aria-hidden="true"></span> %2$s</button>',
                esc_attr( $editor_id ),
                esc_html__( 'AI Görsel', 'agfo-ai-manager' )
            );
        }

        public static function render_modal(): void {
            if ( self::$rendered || ! current_user_can( AGFO_AIM_Image_Generator::required_capability() ) ) {
                return;
            }
            self::$rendered = true;

            $presets   = AGFO_AIM_Image_Prompt_Library::get_all();
            $aspects   = AGFO_AIM_Image_Adapter::aspect_presets();
            $providers = AGFO_AIM_Image_Generator::available_providers();
            $settings  = AGFO_AIM_Image_Generator::settings();
            $effective = AGFO_AIM_Image_Generator::effective_default();
            ?>
            <div id="agfo-classic-image-overlay" class="agfo-classic-image-overlay" hidden></div>
            <section id="agfo-classic-image-modal" class="agfo-classic-image-modal" role="dialog" aria-modal="true" aria-labelledby="agfo-classic-image-title" hidden>
                <header class="agfo-classic-image-header">
                    <div>
                        <h2 id="agfo-classic-image-title"><span class="dashicons dashicons-format-image" aria-hidden="true"></span> AGFO Görsel Stüdyosu</h2>
                        <p>Yazının içeriğinden ya da kendi promptunuzdan öne çıkan görsel üretin.</p>
                    </div>
                    <button type="button" class="agfo-classic-image-close" aria-label="Kapat">&times;</button>
                </header>

                <div class="agfo-classic-image-body">
                    <?php if ( empty( $providers ) ) : ?>
                        <div class="notice notice-error inline"><p>Görsel üretebilen bir sağlayıcı için API anahtarı tanımlı değil. OpenAI, OpenRouter, Gemini, fal.ai veya MiniMax anahtarlarından birini ekleyin.</p></div>
                    <?php endif; ?>

                    <div class="agfo-classic-image-topbar">
                        <div class="agfo-classic-image-model">
                            <span>Aktif görsel modeli</span>
                            <strong id="agfo-classic-image-active-model"><?php echo esc_html( $effective['provider'] !== '' ? $effective['provider'] . ' · ' . $effective['model'] : 'Yapılandırılmadı' ); ?></strong>
                        </div>
                        <a class="button" href="<?php echo esc_url( admin_url( 'admin.php?page=agfo-image-prompts' ) ); ?>">Promptları yönet</a>
                    </div>

                    <form id="agfo-classic-image-form">
                        <div class="agfo-classic-image-grid agfo-classic-image-grid-four">
                            <label>
                                <span>Görsel türü</span>
                                <select id="agfo-classic-image-preset" name="preset">
                                    <?php foreach ( $presets as $key => $row ) : ?>
                                        <option value="<?php echo esc_attr( $key ); ?>" <?php selected( $settings['preset'], $key ); ?>><?php echo esc_html( $row['label'] ); ?></option>
                                    <?php endforeach; ?>
                                </select>
                                <small id="agfo-classic-image-preset-help"></small>
                            </label>
                            <label>
                                <span>Oran</span>
                                <select id="agfo-classic-image-aspect" name="aspect">
                                    <?php foreach ( $aspects as $key => $row ) : ?>
                                        <option value="<?php echo esc_attr( $key ); ?>" <?php selected( $settings['aspect'], $key ); ?>><?php echo esc_html( $row['label'] ); ?></option>
                                    <?php endforeach; ?>
                                </select>
                            </label>
                            <label>
                                <span>Sağlayıcı</span>
                                <select id="agfo-classic-image-provider" name="provider">
                                    <?php foreach ( $providers as $code => $label ) : ?>
                                        <option value="<?php echo esc_attr( $code ); ?>" <?php selected( $effective['provider'], $code ); ?>><?php echo esc_html( $label ); ?></option>
                                    <?php endforeach; ?>
                                </select>
                            </label>
                            <label>
                                <span>Model</span>
                                <?php // CHANGED 17.0.1: the former datalist filtered its options by the current value, so only the selected model was offered. A real select lists every model; "Diğer" reveals a free-text field. ?>
                                <select id="agfo-classic-image-model-select" aria-label="Görsel modeli">
                                    <option value="<?php echo esc_attr( $effective['model'] ); ?>"><?php echo esc_html( $effective['model'] !== '' ? $effective['model'] : 'Model seçin' ); ?></option>
                                </select>
                                <input id="agfo-classic-image-model" class="agfo-classic-image-model-custom" name="model" type="text" value="<?php echo esc_attr( $effective['model'] ); ?>" placeholder="Model kimliğini yazın, örn. gpt-image-2" hidden>
                            </label>
                        </div>

                        <div class="agfo-classic-image-grid agfo-classic-image-grid-three">
                            <label>
                                <span>Konu kaynağı</span>
                                <select id="agfo-classic-image-scope" name="subject_scope">
                                    <option value="content">Başlık + içerik</option>
                                    <option value="title">Yalnızca başlık</option>
                                    <option value="prompt">Yalnızca aşağıdaki prompt</option>
                                </select>
                            </label>
                            <label>
                                <span>Kalite</span>
                                <select id="agfo-classic-image-quality" name="quality">
                                    <option value="high" <?php selected( $settings['quality'], 'high' ); ?>>Yüksek</option>
                                    <option value="medium" <?php selected( $settings['quality'], 'medium' ); ?>>Orta</option>
                                    <option value="low" <?php selected( $settings['quality'], 'low' ); ?>>Düşük — hızlı taslak</option>
                                </select>
                            </label>
                            <label>
                                <span>Görselde yazı dili</span>
                                <select id="agfo-classic-image-language" name="language">
                                    <option value="">Otomatik</option>
                                    <option value="Turkish">Türkçe</option>
                                    <option value="English">English</option>
                                    <option value="Spanish">Español</option>
                                    <option value="Azerbaijani">Azərbaycanca</option>
                                    <option value="Italian">Italiano</option>
                                    <option value="German">Deutsch</option>
                                    <option value="French">Français</option>
                                </select>
                            </label>
                        </div>

                        <div class="agfo-classic-image-title-row" id="agfo-classic-image-title-row" hidden>
                            <label>
                                <span>Görsel üzerindeki başlık</span>
                                <input id="agfo-classic-image-title-text" name="title_text" type="text" maxlength="120" placeholder="Boş bırakılırsa model kendi başlığını yerleştirir">
                            </label>
                        </div>

                        <label class="agfo-classic-image-prompt-label">
                            <span>Ek prompt <small>— boş bırakılırsa görsel yazının içeriğinden üretilir</small></span>
                            <textarea id="agfo-classic-image-extra" name="extra" rows="5" maxlength="4000" placeholder="Örn. Alacakaranlıkta bir kıyı kasabasında tek başına yürüyen yaşlı bir adam"></textarea>
                            <small><strong id="agfo-classic-image-extra-count">0</strong> / 4000 karakter</small>
                        </label>

                        <div class="agfo-classic-image-workspace">
                            <div class="agfo-classic-image-preview" id="agfo-classic-image-preview">
                                <div class="agfo-classic-image-placeholder">Önizleme burada görünecek.</div>
                            </div>
                            <div class="agfo-classic-image-meta">
                                <div class="agfo-classic-image-meta-head">
                                    <span>Kullanılan prompt</span>
                                    <button type="button" class="button-link" id="agfo-classic-image-toggle-prompt">Göster / gizle</button>
                                </div>
                                <pre id="agfo-classic-image-prompt-view" hidden></pre>
                                <small id="agfo-classic-image-result-meta"></small>
                            </div>
                        </div>
                    </form>

                    <div id="agfo-classic-image-status" class="agfo-classic-image-status is-idle" aria-live="polite">Henüz görsel üretilmedi.</div>
                </div>

                <footer class="agfo-classic-image-footer">
                    <div class="agfo-classic-image-secondary-actions">
                        <button type="button" class="button" id="agfo-classic-image-preview-prompt">Promptu Önizle</button>
                        <a class="button" id="agfo-classic-image-open-media" href="#" target="_blank" rel="noopener" hidden>Medyada Aç</a>
                    </div>
                    <div class="agfo-classic-image-primary-actions">
                        <button type="button" class="button agfo-classic-image-close">Kapat</button>
                        <button type="button" class="button" id="agfo-classic-image-set-featured" disabled>Öne Çıkan Görsel Yap</button>
                        <button type="button" class="button button-primary" id="agfo-classic-image-generate" <?php disabled( empty( $providers ) ); ?>>Görsel Üret</button>
                    </div>
                </footer>
            </section>
            <?php
        }
    }
}
