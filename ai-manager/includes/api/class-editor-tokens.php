<?php
/**
 * NEW 17.5.0: AGFO AI Editor connection keys.
 *
 * A simpler and more robust alternative to WordPress Application Passwords for the Windows editor:
 * the administrator creates a key on "AI Manager › AI Editor bağlantısı", pastes it into the editor,
 * and the editor sends it in the X-AGFO-Editor-Token header. Keys are bound to the WordPress user who
 * created them, stored only as an HMAC (wp_salt), can be revoked one by one, and are accepted ONLY on
 * /agfo-ai/v1/editor/* routes. This avoids servers or security plugins that strip the Authorization
 * header or disable Application Passwords.
 *
 * Key format: agfoed.<user_id>.<key_id>.<secret>   (secret: 40 random alphanumerics)
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Editor_Tokens' ) ) {
    final class AGFO_AIM_Editor_Tokens {
        public const META       = 'agfo_aim_editor_tokens';
        public const HEADER     = 'HTTP_X_AGFO_EDITOR_TOKEN';
        public const MAX_TOKENS = 10;
        public const PAGE       = 'agfo-ai-editor';

        /** @var string|null last failure reason for diagnostics (never contains the key) */
        private static $last_error = null;

        public static function register_hooks(): void {
            add_action( 'admin_menu', [ __CLASS__, 'register_page' ], 30 );
            add_action( 'admin_post_agfo_aim_editor_token', [ __CLASS__, 'handle_form' ] );
            // Resolve the key while WordPress determines the current user, so security plugins that block
            // anonymous REST requests (rest_authentication_errors) already see an authenticated user.
            add_filter( 'determine_current_user', [ __CLASS__, 'determine_user' ], 31 );
        }

        /**
         * @param int|false $user_id
         * @return int|false
         */
        public static function determine_user( $user_id ) {
            if ( ! empty( $user_id ) || ! class_exists( 'AGFO_AIM_Editor_API' ) || ! AGFO_AIM_Editor_API::is_editor_request() ) {
                return $user_id;
            }
            $token = self::header_token();
            if ( $token === '' ) {
                return $user_id;
            }
            $uid = self::verify( $token );
            return ( $uid > 0 && function_exists( 'get_userdata' ) && get_userdata( $uid ) ) ? $uid : $user_id;
        }

        public static function capability(): string {
            return class_exists( 'AGFO_AIM_Editor_API' ) ? AGFO_AIM_Editor_API::required_capability() : 'manage_options';
        }

        // ------------------------------------------------------------------ keys

        private static function hash_secret( string $secret ): string {
            return hash_hmac( 'sha256', $secret, wp_salt( 'auth' ) . '|agfo-ai-editor' );
        }

        private static function random( int $len ): string {
            $chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';
            $out   = '';
            $max   = strlen( $chars ) - 1;
            for ( $i = 0; $i < $len; $i++ ) {
                $out .= $chars[ random_int( 0, $max ) ];
            }
            return $out;
        }

        public static function list_for( int $user_id ): array {
            $rows = get_user_meta( $user_id, self::META, true );
            return is_array( $rows ) ? $rows : [];
        }

        /** @return string|WP_Error the full key (shown once) */
        public static function create( int $user_id, string $label = '' ) {
            $rows = self::list_for( $user_id );
            if ( count( $rows ) >= self::MAX_TOKENS ) {
                return new WP_Error( 'agfo_editor_token_limit', 'En fazla ' . self::MAX_TOKENS . ' anahtar oluşturulabilir; kullanılmayanları silin.' );
            }
            $id     = strtolower( self::random( 8 ) );
            $secret = self::random( 40 );
            $rows[ $id ] = [
                'hash'      => self::hash_secret( $secret ),
                'label'     => mb_substr( sanitize_text_field( $label ), 0, 60 ) ?: 'AI Editor',
                'created'   => gmdate( 'c' ),
                'last_used' => '',
            ];
            update_user_meta( $user_id, self::META, $rows );
            return 'agfoed.' . $user_id . '.' . $id . '.' . $secret;
        }

        public static function revoke( int $user_id, string $id ): bool {
            $rows = self::list_for( $user_id );
            $id   = sanitize_key( $id );
            if ( ! isset( $rows[ $id ] ) ) {
                return false;
            }
            unset( $rows[ $id ] );
            update_user_meta( $user_id, self::META, $rows );
            return true;
        }

        public static function header_token(): string {
            $raw = isset( $_SERVER[ self::HEADER ] ) ? trim( (string) wp_unslash( $_SERVER[ self::HEADER ] ) ) : '';
            if ( $raw === '' && isset( $_SERVER['HTTP_AUTHORIZATION'] ) && stripos( (string) $_SERVER['HTTP_AUTHORIZATION'], 'Bearer agfoed.' ) === 0 ) {
                $raw = trim( substr( (string) wp_unslash( $_SERVER['HTTP_AUTHORIZATION'] ), 7 ) );
            }
            return ( strlen( $raw ) <= 200 && preg_match( '/^agfoed\.\d{1,12}\.[a-z0-9]{8}\.[A-Za-z0-9]{40}$/', $raw ) ) ? $raw : '';
        }

        public static function token_sent(): bool {
            return ! empty( $_SERVER[ self::HEADER ] );
        }

        /** @return int user id or 0 */
        public static function verify( string $token ): int {
            self::$last_error = null;
            if ( ! preg_match( '/^agfoed\.(\d{1,12})\.([a-z0-9]{8})\.([A-Za-z0-9]{40})$/', $token, $m ) ) {
                self::$last_error = 'format';
                return 0;
            }
            $user_id = (int) $m[1];
            $rows    = self::list_for( $user_id );
            if ( empty( $rows[ $m[2] ]['hash'] ) || ! hash_equals( (string) $rows[ $m[2] ]['hash'], self::hash_secret( $m[3] ) ) ) {
                self::$last_error = 'unknown';
                return 0;
            }
            $now  = time();
            $last = strtotime( (string) ( $rows[ $m[2] ]['last_used'] ?? '' ) ) ?: 0;
            if ( $now - $last > 300 ) {      // write at most every 5 minutes
                $rows[ $m[2] ]['last_used'] = gmdate( 'c', $now );
                update_user_meta( $user_id, self::META, $rows );
            }
            return $user_id;
        }

        /**
         * Called by AGFO_AIM_Editor_API::can_use() when no user is logged in.
         *
         * @return bool true when a valid key switched the current user
         */
        public static function authenticate_request(): bool {
            $token = self::header_token();
            if ( $token === '' ) {
                if ( self::token_sent() ) {
                    self::$last_error = 'format';
                }
                return false;
            }
            $user_id = self::verify( $token );
            if ( $user_id <= 0 || ! function_exists( 'get_userdata' ) || ! get_userdata( $user_id ) ) {
                self::$last_error = self::$last_error ?: 'unknown';
                return false;
            }
            wp_set_current_user( $user_id );
            return true;
        }

        public static function last_error(): ?string {
            return self::$last_error;
        }

        // ------------------------------------------------------------------ admin page

        public static function register_page(): void {
            add_submenu_page(
                'agfo-ai-manager',
                'AI Editor bağlantısı',
                '🖊️ AI Editor bağlantısı',
                self::capability(),
                self::PAGE,
                [ __CLASS__, 'render_page' ]
            );
        }

        public static function handle_form(): void {
            if ( ! current_user_can( self::capability() ) ) {
                wp_die( esc_html__( 'Bu işlem için yetkiniz yok.', 'agfo-ai-manager' ) );
            }
            check_admin_referer( 'agfo_aim_editor_token' );
            $user_id = get_current_user_id();
            $do      = sanitize_key( wp_unslash( $_POST['do'] ?? '' ) );
            $args    = [ 'page' => self::PAGE ];
            if ( 'create' === $do ) {
                $key = self::create( $user_id, (string) wp_unslash( $_POST['label'] ?? '' ) );
                if ( is_wp_error( $key ) ) {
                    $args['agfo_err'] = 'limit';
                } else {
                    // Shown once: kept for 10 minutes in a user-scoped transient, then gone.
                    set_transient( 'agfo_aim_editor_newkey_' . $user_id, $key, 600 );
                    $args['agfo_new'] = '1';
                }
            } elseif ( 'revoke' === $do ) {
                self::revoke( $user_id, (string) wp_unslash( $_POST['id'] ?? '' ) );
                $args['agfo_revoked'] = '1';
            }
            wp_safe_redirect( add_query_arg( $args, admin_url( 'admin.php' ) ) );
            exit;
        }

        public static function render_page(): void {
            if ( ! current_user_can( self::capability() ) ) {
                return;
            }
            $user_id = get_current_user_id();
            $new     = '';
            if ( ! empty( $_GET['agfo_new'] ) ) {
                $new = (string) get_transient( 'agfo_aim_editor_newkey_' . $user_id );
                delete_transient( 'agfo_aim_editor_newkey_' . $user_id );
            }
            $rows = self::list_for( $user_id );
            $site = home_url();
            echo '<div class="wrap"><h1>AI Editor bağlantısı</h1>';
            echo '<p>Windows için <strong>AGFO AI Editor</strong> bu siteye bir <em>bağlantı anahtarı</em> ile bağlanır. '
                . 'API anahtarlarınız sitede kalır; editör yalnızca metin düzenleme, çeviri ve sohbet uçlarını kullanabilir. '
                . 'Anahtar, onu oluşturan kullanıcının (' . esc_html( wp_get_current_user()->user_login ) . ') yetkileriyle çalışır.</p>';
            if ( $new !== '' ) {
                echo '<div class="notice notice-success"><p><strong>Yeni anahtar oluşturuldu. Şimdi kopyalayın — bir daha gösterilmez.</strong></p>'
                    . '<p><input type="text" readonly class="large-text code" style="font-size:14px" onclick="this.select()" value="' . esc_attr( $new ) . '"></p>'
                    . '<p>Editörde: <em>Ayarlar › Bağlantı</em> › Site adresi: <code>' . esc_html( $site ) . '</code> › Bağlantı anahtarı: yukarıdaki değer.</p></div>';
            }
            if ( ! empty( $_GET['agfo_err'] ) ) {
                echo '<div class="notice notice-error"><p>En fazla ' . (int) self::MAX_TOKENS . ' anahtar oluşturulabilir; kullanılmayanları silin.</p></div>';
            }
            if ( ! empty( $_GET['agfo_revoked'] ) ) {
                echo '<div class="notice notice-info"><p>Anahtar silindi; o anahtarı kullanan editör artık bağlanamaz.</p></div>';
            }
            echo '<h2>Yeni anahtar</h2><form method="post" action="' . esc_url( admin_url( 'admin-post.php' ) ) . '">';
            wp_nonce_field( 'agfo_aim_editor_token' );
            echo '<input type="hidden" name="action" value="agfo_aim_editor_token"><input type="hidden" name="do" value="create">'
                . '<input type="text" name="label" maxlength="60" placeholder="Etiket (ör. Ofis bilgisayarı)" class="regular-text"> '
                . '<button class="button button-primary">Anahtar oluştur</button></form>';
            echo '<h2>Anahtarlarınız</h2>';
            if ( empty( $rows ) ) {
                echo '<p>Henüz anahtar yok.</p>';
            } else {
                echo '<table class="widefat striped" style="max-width:900px"><thead><tr><th>Etiket</th><th>Oluşturuldu</th><th>Son kullanım</th><th></th></tr></thead><tbody>';
                foreach ( $rows as $id => $r ) {
                    echo '<tr><td>' . esc_html( (string) ( $r['label'] ?? '' ) ) . ' <code>…' . esc_html( (string) $id ) . '</code></td>'
                        . '<td>' . esc_html( (string) ( $r['created'] ?? '' ) ) . '</td><td>' . esc_html( (string) ( $r['last_used'] ?: '—' ) ) . '</td><td>'
                        . '<form method="post" action="' . esc_url( admin_url( 'admin-post.php' ) ) . '" onsubmit="return confirm(\'Anahtar silinsin mi?\')">';
                    wp_nonce_field( 'agfo_aim_editor_token' );
                    echo '<input type="hidden" name="action" value="agfo_aim_editor_token"><input type="hidden" name="do" value="revoke">'
                        . '<input type="hidden" name="id" value="' . esc_attr( (string) $id ) . '"><button class="button button-link-delete">Sil</button></form></td></tr>';
                }
                echo '</tbody></table>';
            }
            echo '<p style="margin-top:18px;color:#646970">Bağlantı denetimi: <code>' . esc_html( rest_url( 'agfo-ai/v1/editor/ping' ) ) . '</code></p></div>';
        }
    }
}
