<?php
/**
 * Telaffuz Sözlüğü — manage the shared EMA pronunciation lexicon on the TTS server.
 *
 * Every change is written by the AGFO TTS Service (1.1.0+) to data/lexicon.custom.json on
 * the server and is live for all sites immediately. Shipped words can be changed, removed
 * (masked so a service update cannot bring them back) and restored.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_EMA_Lexicon_Admin' ) ) {
    final class AGFO_AIM_EMA_Lexicon_Admin {
        const SLUG = 'agfo-ai-ema-lexicon';

        public static function register_hooks(): void {
            add_action( 'admin_menu', [ __CLASS__, 'add_menu' ], 21 );
            add_action( 'admin_enqueue_scripts', [ __CLASS__, 'enqueue' ] );
            add_action( 'wp_ajax_agfo_ai_ema_lexicon', [ __CLASS__, 'ajax' ] );
        }

        public static function add_menu(): void {
            add_submenu_page( 'agfo-ai-manager', 'Telaffuz Sözlüğü', '🗣 Telaffuz Sözlüğü', 'manage_options', self::SLUG, [ __CLASS__, 'render' ] );
        }

        public static function enqueue( string $hook ): void {
            $page = isset( $_GET['page'] ) ? sanitize_key( wp_unslash( (string) $_GET['page'] ) ) : '';
            if ( self::SLUG !== $page ) {
                return;
            }
            $css = AGFO_AIM_PLUGIN_DIR . 'assets/css/operations.css';
            wp_enqueue_style( 'agfo-ai-operations', AGFO_AIM_PLUGIN_URL . 'assets/css/operations.css', [], file_exists( $css ) ? AGFO_AIM_VERSION . '.' . filemtime( $css ) : AGFO_AIM_VERSION );
            $js = AGFO_AIM_PLUGIN_DIR . 'assets/js/ema-lexicon.js';
            wp_enqueue_script( 'agfo-ai-ema-lexicon', AGFO_AIM_PLUGIN_URL . 'assets/js/ema-lexicon.js', [ 'jquery' ], file_exists( $js ) ? AGFO_AIM_VERSION . '.' . filemtime( $js ) : AGFO_AIM_VERSION, true );
            wp_localize_script(
                'agfo-ai-ema-lexicon',
                'agfoEmaLexicon',
                [
                    'ajaxUrl' => admin_url( 'admin-ajax.php' ),
                    'nonce'   => wp_create_nonce( 'agfo_ajax_nonce' ),
                    'perPage' => 50,
                ]
            );
        }

        public static function render(): void {
            if ( ! current_user_can( 'manage_options' ) ) {
                wp_die( 'Yetki yok.' );
            }
            $has_token = class_exists( 'AGFO_AIM_Adapter_EMA' ) && '' !== AGFO_AIM_Adapter_EMA::token();
            ?>
            <div class="wrap agfo-ops-wrap">
                <h1>Telaffuz Sözlüğü</h1>
                <p class="description">EMA Lightning’in bütün sitelerde kullandığı ortak sözlük. Buradaki her değişiklik sunucudaki listeye yazılır ve hemen geçerli olur; servis güncellemeleri eklediğiniz kayıtları silmez. Yalnız bu siteye özel okunuşlar için Ses Stüdyosu › EMA servis ayarlarındaki sözlük alanını kullanın.</p>
                <?php if ( ! $has_token ) : ?>
                    <div class="notice notice-warning inline"><p>EMA servis token’ı tanımlı değil. <a href="<?php echo esc_url( admin_url( 'admin.php?page=agfo-ai-manager' ) ); ?>">Sağlayıcılar</a> ekranındaki “EMA Lightning (yerel TTS)” alanına girin.</p></div>
                <?php endif; ?>

                <section class="agfo-ops-card">
                    <h2>Kelime ekle veya değiştir</h2>
                    <form id="agfo-lex-form" class="agfo-inline-fields" autocomplete="off">
                        <div class="agfo-field-row">
                            <label for="agfo-lex-word">Kelime (metinde göründüğü gibi)</label>
                            <input id="agfo-lex-word" type="text" maxlength="80" required placeholder="Örn. HACCP, Chicago, Kaya Gıda">
                        </div>
                        <div class="agfo-field-row">
                            <label for="agfo-lex-reading">Okunuş (Türkçe harflerle)</label>
                            <input id="agfo-lex-reading" type="text" maxlength="160" required placeholder="Örn. hasip, Şikago">
                        </div>
                        <div class="agfo-field-row agfo-lex-actions">
                            <span class="agfo-lex-label-spacer" aria-hidden="true">&nbsp;</span>
                            <div>
                                <button type="button" id="agfo-lex-listen" class="button button-secondary" <?php disabled( ! $has_token ); ?>>Dinle</button>
                                <button type="submit" id="agfo-lex-save" class="button button-primary" <?php disabled( ! $has_token ); ?>>Kaydet</button>
                            </div>
                        </div>
                    </form>
                    <p class="description">Büyük/küçük harf ayrımı vardır: “HACCP” ve “haccp” ayrı kayıtlardır. Eklere dokunulmaz; “Chicago” kaydı “Chicago’da”yı da “Şikago’da” yapar. Kelime zaten varsa okunuşu güncellenir.</p>
                    <div id="agfo-lex-status" class="agfo-status is-idle" aria-live="polite">Hazır.</div>
                    <audio id="agfo-lex-player" controls hidden></audio>
                </section>

                <section class="agfo-ops-card">
                    <div class="agfo-lex-toolbar">
                        <h2>Sözlük <span id="agfo-lex-counts" class="description"></span></h2>
                        <div class="agfo-inline-fields">
                            <div class="agfo-field-row">
                                <label for="agfo-lex-search">Ara</label>
                                <input id="agfo-lex-search" type="search" placeholder="Kelime veya okunuş">
                            </div>
                            <div class="agfo-field-row">
                                <label for="agfo-lex-filter">Göster</label>
                                <select id="agfo-lex-filter">
                                    <option value="">Tümü</option>
                                    <option value="mine">Eklenen ve değiştirilen</option>
                                    <option value="removed">Kaldırılan</option>
                                    <option value="base">Hazır gelen</option>
                                </select>
                            </div>
                            <div class="agfo-field-row">
                                <span class="agfo-lex-label-spacer" aria-hidden="true">&nbsp;</span>
                                <button type="button" id="agfo-lex-reload" class="button button-secondary" <?php disabled( ! $has_token ); ?>>Yenile</button>
                            </div>
                        </div>
                    </div>
                    <table class="widefat striped agfo-lex-table">
                        <thead><tr><th>Kelime</th><th>Okunuş</th><th>Kaynak</th><th class="agfo-lex-col-actions">İşlem</th></tr></thead>
                        <tbody id="agfo-lex-rows"><tr><td colspan="4">Yükleniyor…</td></tr></tbody>
                    </table>
                    <div class="agfo-lex-pager">
                        <button type="button" id="agfo-lex-prev" class="button">‹ Önceki</button>
                        <span id="agfo-lex-page"></span>
                        <button type="button" id="agfo-lex-next" class="button">Sonraki ›</button>
                    </div>
                </section>
            </div>
            <?php
        }

        public static function ajax(): void {
            if ( ! is_user_logged_in() || ! current_user_can( 'manage_options' ) ) {
                wp_send_json_error( [ 'message' => 'Yetki yok.' ], 403 );
            }
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );
            if ( ! class_exists( 'AGFO_AIM_Adapter_EMA' ) ) {
                wp_send_json_error( [ 'message' => 'EMA adaptörü yüklenmedi.' ], 500 );
            }
            $op      = sanitize_key( (string) ( $_POST['op'] ?? '' ) );
            $word    = self::clean( wp_unslash( (string) ( $_POST['word'] ?? '' ) ), 80 );
            $reading = self::clean( wp_unslash( (string) ( $_POST['reading'] ?? '' ) ), 160 );

            switch ( $op ) {
                case 'list':
                    $res = AGFO_AIM_Adapter_EMA::service_call( 'GET', '/lexicon' );
                    break;
                case 'save':
                    if ( '' === $word || '' === $reading ) {
                        wp_send_json_error( [ 'message' => 'Kelime ve okunuş gerekli.' ], 400 );
                    }
                    $res = AGFO_AIM_Adapter_EMA::service_call( 'POST', '/lexicon/entry', [ 'word' => $word, 'reading' => $reading ] );
                    break;
                case 'delete':
                case 'restore':
                    if ( '' === $word ) {
                        wp_send_json_error( [ 'message' => 'Kelime gerekli.' ], 400 );
                    }
                    $res = AGFO_AIM_Adapter_EMA::service_call( 'POST', '/lexicon/delete', [ 'word' => $word, 'reading' => 'restore' === $op ? '__restore__' : '' ] );
                    break;
                case 'listen':
                    $audio = AGFO_AIM_Adapter_EMA::listen( '' !== $reading ? $reading : $word );
                    if ( is_wp_error( $audio ) ) {
                        wp_send_json_error( [ 'message' => $audio->get_error_message() ], 400 );
                    }
                    wp_send_json_success( [ 'audio' => 'data:audio/mpeg;base64,' . base64_encode( $audio ) ] ); // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions.obfuscation_base64_encode
                    return;
                default:
                    wp_send_json_error( [ 'message' => 'Geçersiz işlem.' ], 400 );
                    return;
            }
            if ( is_wp_error( $res ) ) {
                wp_send_json_error( [ 'message' => $res->get_error_message(), 'code' => $res->get_error_code() ], 400 );
            }
            wp_send_json_success( $res );
        }

        /** Single-line text: no tags or control characters; "%" sequences kept. */
        private static function clean( string $value, int $max ): string {
            $value = wp_check_invalid_utf8( $value );
            $value = wp_strip_all_tags( $value, true );
            $value = trim( (string) preg_replace( '/[\x00-\x1F\x7F]+|\s+/u', ' ', $value ) );
            return mb_substr( $value, 0, $max, 'UTF-8' );
        }
    }
}
