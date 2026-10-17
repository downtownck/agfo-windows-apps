<?php
/**
 * Classic Editor Content Studio integration.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Classic_Editor_Content' ) ) {
    final class AGFO_AIM_Classic_Editor_Content {
        private static bool $rendered = false;

        public static function register_hooks(): void {
            add_action( 'admin_enqueue_scripts', [ __CLASS__, 'enqueue_assets' ], 31 );
            add_action( 'media_buttons', [ __CLASS__, 'render_media_button' ], 24, 1 );
            add_action( 'admin_footer-post.php', [ __CLASS__, 'render_modal' ] );
            add_action( 'admin_footer-post-new.php', [ __CLASS__, 'render_modal' ] );
        }

        public static function enqueue_assets( string $hook ): void {
            if ( ! self::is_target_screen( $hook ) ) {
                return;
            }
            $css = AGFO_AIM_PLUGIN_DIR . 'assets/css/classic-editor-content.css';
            $js  = AGFO_AIM_PLUGIN_DIR . 'assets/js/classic-editor-content.js';

            wp_enqueue_style(
                'agfo-ai-classic-editor-content',
                AGFO_AIM_PLUGIN_URL . 'assets/css/classic-editor-content.css',
                [ 'agfo-ai-classic-editor-tts' ],
                file_exists( $css ) ? AGFO_AIM_VERSION . '.' . filemtime( $css ) : AGFO_AIM_VERSION
            );
            wp_enqueue_script(
                'agfo-ai-classic-editor-content',
                AGFO_AIM_PLUGIN_URL . 'assets/js/classic-editor-content.js',
                [ 'jquery', 'agfo-ai-classic-editor-tts' ],
                file_exists( $js ) ? AGFO_AIM_VERSION . '.' . filemtime( $js ) : AGFO_AIM_VERSION,
                true
            );

            $config = function_exists( 'agfo_get_priority_api_key' ) ? agfo_get_priority_api_key() : false;
            // NEW 17.3.0: the translation route may point at a different model than the default.
            $translation = self::translation_model_info( $config );
            wp_localize_script(
                'agfo-ai-classic-editor-content',
                'agfoClassicContent',
                [
                    'ajaxUrl'   => admin_url( 'admin-ajax.php' ),
                    'nonce'     => wp_create_nonce( 'agfo_ajax_nonce' ),
                    'templates' => class_exists( 'AGFO_AIM_Content_Prompt_Library' ) ? AGFO_AIM_Content_Prompt_Library::public_catalog() : [],
                    'provider'  => is_array( $config ) ? sanitize_text_field( (string) ( $config['provider_name'] ?? $config['code'] ) ) : '',
                    'model'     => is_array( $config ) ? sanitize_text_field( (string) ( $config['model'] ?? '' ) ) : '',
                    'promptUrl' => admin_url( 'admin.php?page=agfo-content-prompts' ),
                    'translateTemplate' => 'translate_polish',
                    'translateProvider' => $translation['provider'],
                    'translateModel'    => $translation['model'],
                    'languages'         => self::languages(),
                    'postId'    => isset( $_GET['post'] ) ? absint( $_GET['post'] ) : 0,
                    'messages'  => [
                        'idle'       => 'Henüz işlem yok.',
                        'working'    => 'İçerik dönüştürülüyor…',
                        'complete'   => 'Yeni metin hazır.',
                        'failed'     => 'İçerik dönüştürülemedi.',
                        'noSource'   => 'Dönüştürülecek metin bulunamadı.',
                        'copied'     => 'Sonuç panoya kopyalandı.',
                        'applied'    => 'Sonuç editöre uygulandı.',
                        'undo'       => 'Son editör değişikliği geri alındı.',
                        'translating'=> 'Çevriliyor…',
                        'translated' => 'Çeviri hazır. "Editörde Değiştir" ile uygulayın.',
                        'truncated'  => 'Sonuç uzunluk sınırına takıldı; metnin sonu eksik olabilir. Daha kısa bir bölüm seçip tekrar çevirin.',
                    ],
                ]
            );
        }

        public static function render_media_button( string $editor_id ): void {
            if ( ! current_user_can( AGFO_AIM_Content_Transformer::required_capability() ) || 'content' !== $editor_id ) {
                return;
            }
            printf(
                '<button type="button" class="button agfo-classic-content-open agfo-classic-content-toolbar-button" data-editor="%1$s" aria-haspopup="dialog" aria-controls="agfo-classic-content-modal"><span class="dashicons dashicons-edit-page" aria-hidden="true"></span> %2$s</button>',
                esc_attr( $editor_id ),
                esc_html__( 'AI Düzenle', 'agfo-ai-manager' )
            );
            // NEW 17.3.0: one-click translation with its own target-language picker.
            echo self::translate_controls_html( $editor_id ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped inside.
        }

        /**
         * NEW 17.3.0: target languages offered by the editor (value => label).
         *
         * @return array<string,string>
         */
        public static function languages(): array {
            $languages = [
                'Türkçe'   => 'Türkçe',
                'English'  => 'English',
                'Español'  => 'Español',
                'Italiano' => 'Italiano',
                'Deutsch'  => 'Deutsch',
                'Français' => 'Français',
            ];
            $filtered = apply_filters( 'agfo_ai_content_languages', $languages );
            if ( ! is_array( $filtered ) || ! $filtered ) {
                return $languages;
            }
            $clean = [];
            foreach ( $filtered as $value => $label ) {
                $value = sanitize_text_field( (string) $value );
                if ( $value !== '' ) {
                    $clean[ $value ] = sanitize_text_field( (string) $label );
                }
            }
            return $clean ?: $languages;
        }

        /**
         * NEW 17.3.0: markup for the toolbar "Çevir" button and its language select.
         */
        public static function translate_controls_html( string $editor_id ): string {
            $options = '';
            foreach ( self::languages() as $value => $label ) {
                $options .= sprintf( '<option value="%1$s">%2$s</option>', esc_attr( $value ), esc_html( $label ) );
            }
            return sprintf(
                '<span class="agfo-classic-translate-group" data-editor="%1$s"><button type="button" class="button agfo-classic-translate-open" data-editor="%1$s" aria-haspopup="dialog" aria-controls="agfo-classic-content-modal" title="%3$s"><span class="dashicons dashicons-translation" aria-hidden="true"></span> %2$s</button><select class="agfo-classic-translate-lang" aria-label="%4$s">%5$s</select></span>',
                esc_attr( $editor_id ),
                esc_html__( 'Çevir', 'agfo-ai-manager' ),
                esc_attr__( 'Seçili metni (seçim yoksa tüm içeriği) hedef dile çevirir', 'agfo-ai-manager' ),
                esc_attr__( 'Hedef dil', 'agfo-ai-manager' ),
                $options
            );
        }

        /**
         * NEW 17.3.0: provider/model shown for translation jobs.
         *
         * @param array|false $default_config Default text config.
         * @return array{provider:string,model:string}
         */
        private static function translation_model_info( $default_config ): array {
            $config = class_exists( 'AGFO_AIM_Content_Transformer' ) && method_exists( 'AGFO_AIM_Content_Transformer', 'translation_config' )
                ? AGFO_AIM_Content_Transformer::translation_config()
                : false;
            if ( ! is_array( $config ) ) {
                $config = $default_config;
            }
            if ( ! is_array( $config ) ) {
                return [ 'provider' => '', 'model' => '' ];
            }
            return [
                'provider' => sanitize_text_field( (string) ( $config['provider_name'] ?? $config['code'] ?? '' ) ),
                'model'    => sanitize_text_field( (string) ( $config['model'] ?? '' ) ),
            ];
        }

        public static function render_modal(): void {
            if ( self::$rendered || ! current_user_can( AGFO_AIM_Content_Transformer::required_capability() ) ) {
                return;
            }
            self::$rendered = true;
            $templates      = AGFO_AIM_Content_Prompt_Library::get_all();
            $config         = function_exists( 'agfo_get_priority_api_key' ) ? agfo_get_priority_api_key() : false;
            ?>
            <div id="agfo-classic-content-overlay" class="agfo-classic-content-overlay" hidden></div>
            <section id="agfo-classic-content-modal" class="agfo-classic-content-modal" role="dialog" aria-modal="true" aria-labelledby="agfo-classic-content-title" hidden>
                <header class="agfo-classic-content-header">
                    <div>
                        <h2 id="agfo-classic-content-title"><span class="dashicons dashicons-edit-page" aria-hidden="true"></span> AGFO İçerik Stüdyosu</h2>
                        <p>Metni düzeltin, yeniden yapılandırın ve sonucu doğrudan seslendirme akışına gönderin.</p>
                    </div>
                    <button type="button" class="agfo-classic-content-close" aria-label="Kapat">×</button>
                </header>

                <div class="agfo-classic-content-body">
                    <?php if ( ! is_array( $config ) ) : ?>
                        <div class="notice notice-error inline"><p>AGFO AI Manager için aktif bir metin sağlayıcısı ve model seçin.</p></div>
                    <?php endif; ?>

                    <div class="agfo-classic-content-topbar">
                        <div class="agfo-classic-content-model">
                            <span id="agfo-classic-content-model-label">Aktif model</span>
                            <strong id="agfo-classic-content-model-name"><?php echo is_array( $config ) ? esc_html( (string) ( $config['provider_name'] ?? $config['code'] ) . ' · ' . (string) $config['model'] ) : 'Yapılandırılmadı'; ?></strong>
                        </div>
                        <div class="agfo-classic-content-source-actions">
                            <button type="button" class="button" id="agfo-classic-content-use-selection">Seçili metni al</button>
                            <button type="button" class="button" id="agfo-classic-content-use-all">Tüm içeriği al</button>
                            <a class="button" href="<?php echo esc_url( admin_url( 'admin.php?page=agfo-content-prompts' ) ); ?>">Promptları yönet</a>
                        </div>
                    </div>

                    <form id="agfo-classic-content-form">
                        <input type="hidden" id="agfo-classic-content-editor-id" value="content">
                        <div class="agfo-classic-content-grid agfo-classic-content-grid-four">
                            <label>
                                <span>İşlem</span>
                                <select id="agfo-classic-content-template" name="template">
                                    <?php foreach ( $templates as $key => $row ) : ?>
                                        <option value="<?php echo esc_attr( $key ); ?>"><?php echo esc_html( $row['label'] ); ?></option>
                                    <?php endforeach; ?>
                                </select>
                                <small id="agfo-classic-content-template-help"></small>
                            </label>
                            <label>
                                <span>Dil</span>
                                <select id="agfo-classic-content-language" name="language">
                                    <?php foreach ( self::languages() as $lang_value => $lang_label ) : ?>
                                        <option value="<?php echo esc_attr( $lang_value ); ?>"><?php echo esc_html( $lang_label ); ?></option>
                                    <?php endforeach; ?>
                                </select>
                            </label>
                            <label>
                                <span>Ton</span>
                                <select id="agfo-classic-content-tone" name="tone">
                                    <option value="Doğal ve dengeli">Doğal ve dengeli</option>
                                    <option value="Profesyonel ve doğrudan">Profesyonel ve doğrudan</option>
                                    <option value="Akademik ve temkinli">Akademik ve temkinli</option>
                                    <option value="Sıcak ve samimi">Sıcak ve samimi</option>
                                    <option value="İkna edici fakat ölçülü">İkna edici fakat ölçülü</option>
                                    <option value="Teknik ve nesnel">Teknik ve nesnel</option>
                                </select>
                            </label>
                            <label>
                                <span>Uzunluk</span>
                                <select id="agfo-classic-content-length" name="length">
                                    <option value="Benzer uzunluk">Benzer uzunluk</option>
                                    <option value="Yaklaşık yüzde 30 daha kısa">%30 daha kısa</option>
                                    <option value="Mümkün olan en kısa biçim">Çok kısa</option>
                                    <option value="Yaklaşık yüzde 30 daha ayrıntılı">%30 daha ayrıntılı</option>
                                    <option value="Gerekli açıklamalarla kapsamlı">Kapsamlı</option>
                                </select>
                            </label>
                        </div>

                        <div class="agfo-classic-content-grid agfo-classic-content-grid-two">
                            <label>
                                <span>Hedef okuyucu</span>
                                <select id="agfo-classic-content-audience" name="audience">
                                    <option value="Genel okuyucu">Genel okuyucu</option>
                                    <option value="Sektör profesyoneli">Sektör profesyoneli</option>
                                    <option value="Teknik uzman veya denetçi">Teknik uzman / denetçi</option>
                                    <option value="Müşteri veya karar verici">Müşteri / karar verici</option>
                                    <option value="Öğrenci veya yeni başlayan">Öğrenci / yeni başlayan</option>
                                </select>
                            </label>
                            <label>
                                <span>Ek düzeltme talebi</span>
                                <input id="agfo-classic-content-extra" name="extra" type="text" placeholder="Örn. İkinci bölümü kısalt, teknik terimleri koru">
                            </label>
                        </div>

                        <div class="agfo-classic-content-flags">
                            <label><input type="checkbox" id="agfo-classic-content-preserve" checked> İsimleri, tarihleri, sayıları, teknik terimleri ve iddiaları koru</label>
                            <label><input type="checkbox" id="agfo-classic-content-from-scratch"> Kaynağı yalnız brief olarak kullan; yeni bir metin üret</label>
                        </div>

                        <div class="agfo-classic-content-workspace">
                            <label class="agfo-classic-content-pane">
                                <span>Kaynak</span>
                                <textarea id="agfo-classic-content-source" rows="16" maxlength="60000" required></textarea>
                                <small><strong id="agfo-classic-content-source-count">0</strong> karakter</small>
                            </label>
                            <div class="agfo-classic-content-pane agfo-classic-content-result-pane">
                                <div class="agfo-classic-content-result-head">
                                    <span>Sonuç</span>
                                    <small id="agfo-classic-content-result-meta"></small>
                                </div>
                                <div id="agfo-classic-content-result" class="agfo-classic-content-result" contenteditable="true" aria-label="AI sonucu"></div>
                            </div>
                        </div>
                    </form>

                    <div id="agfo-classic-content-status" class="agfo-classic-content-status is-idle" aria-live="polite">Henüz işlem yok.</div>
                </div>

                <footer class="agfo-classic-content-footer">
                    <div class="agfo-classic-content-secondary-actions">
                        <button type="button" class="button" id="agfo-classic-content-copy" disabled>Kopyala</button>
                        <button type="button" class="button" id="agfo-classic-content-undo" disabled>Geri Al</button>
                        <button type="button" class="button" id="agfo-classic-content-speak" disabled>Sonucu Seslendir</button>
                    </div>
                    <div class="agfo-classic-content-primary-actions">
                        <button type="button" class="button agfo-classic-content-close">Kapat</button>
                        <button type="button" class="button" id="agfo-classic-content-insert" disabled>Altına Ekle</button>
                        <button type="button" class="button button-primary" id="agfo-classic-content-apply" disabled>Editörde Değiştir</button>
                        <button type="button" class="button button-primary" id="agfo-classic-content-submit" <?php disabled( ! is_array( $config ) ); ?>>Yeniden Yaz</button>
                    </div>
                </footer>
            </section>
            <?php
        }

        private static function is_target_screen( string $hook ): bool {
            return in_array( $hook, [ 'post.php', 'post-new.php' ], true )
                && current_user_can( AGFO_AIM_Content_Transformer::required_capability() );
        }
    }
}
