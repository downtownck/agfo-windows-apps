<?php
/**
 * ACL-controlled asset delivery.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Asset_Delivery' ) ) {
    final class AGFO_AIM_Asset_Delivery {
        public static function register_hooks(): void {
            add_action( 'admin_post_agfo_ai_asset_download', [ __CLASS__, 'download' ] );
        }

        public static function url( string $asset_uuid, bool $download = false ): string {
            $asset_uuid = sanitize_text_field( $asset_uuid );
            if ( '' === $asset_uuid ) {
                return '';
            }

            // wp_nonce_url() returns an HTML-escaped URL. That is correct inside
            // rendered markup, but an AJAX response assigned directly to an
            // audio element treats "&#038;" as a fragment and drops the nonce.
            // Build the raw URL here; callers rendering HTML must escape it.
            return add_query_arg(
                [
                    'action'      => 'agfo_ai_asset_download',
                    'asset_uuid'  => $asset_uuid,
                    'download'    => $download ? '1' : '0',
                    '_agfo_nonce' => wp_create_nonce( 'agfo_ai_asset_' . $asset_uuid ),
                ],
                admin_url( 'admin-post.php' )
            );
        }

        public static function can_access( array $asset, int $user_id ): bool {
            if ( user_can( $user_id, 'manage_options' ) ) {
                return true;
            }
            return $user_id > 0 && (int) ( $asset['created_by'] ?? 0 ) === $user_id;
        }

        public static function download(): void {
            $asset_uuid = isset( $_GET['asset_uuid'] ) ? sanitize_text_field( wp_unslash( $_GET['asset_uuid'] ) ) : '';
            if ( '' === $asset_uuid || ! wp_verify_nonce( sanitize_text_field( wp_unslash( $_GET['_agfo_nonce'] ?? '' ) ), 'agfo_ai_asset_' . $asset_uuid ) ) {
                wp_die( 'Geçersiz veya süresi dolmuş medya bağlantısı.', 'AGFO AI', [ 'response' => 403 ] );
            }

            $asset = class_exists( 'AGFO_AIM_Asset_Store' ) ? AGFO_AIM_Asset_Store::get( $asset_uuid ) : null;
            if ( ! is_array( $asset ) || ! self::can_access( $asset, get_current_user_id() ) ) {
                wp_die( 'Bu medyaya erişim yetkiniz yok.', 'AGFO AI', [ 'response' => 403 ] );
            }

            $path = wp_normalize_path( (string) $asset['storage_path'] );
            if ( ! AGFO_AIM_Asset_Store::path_is_inside_store( $path ) || ! is_file( $path ) || ! is_readable( $path ) ) {
                wp_die( 'Medya dosyası bulunamadı.', 'AGFO AI', [ 'response' => 404 ] );
            }

            $download = ! empty( $_GET['download'] );
            $filename = 'agfo-ai-' . preg_replace( '/[^a-zA-Z0-9_-]/', '', $asset_uuid ) . '.' . pathinfo( $path, PATHINFO_EXTENSION );

            nocache_headers();
            header( 'Content-Type: ' . (string) $asset['mime'] );
            header( 'Content-Length: ' . (string) filesize( $path ) );
            header( 'X-Content-Type-Options: nosniff' );
            header( 'Content-Disposition: ' . ( $download ? 'attachment' : 'inline' ) . '; filename="' . $filename . '"' );

            $handle = fopen( $path, 'rb' );
            if ( false === $handle ) {
                wp_die( 'Medya akışı açılamadı.', 'AGFO AI', [ 'response' => 500 ] );
            }
            while ( ! feof( $handle ) ) {
                echo fread( $handle, 1024 * 1024 ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
                if ( function_exists( 'fastcgi_finish_request' ) ) {
                    // Do not call; the stream must remain open until the file is complete.
                }
                flush();
            }
            fclose( $handle );
            exit;
        }
    }
}

if ( ! function_exists( 'agfo_asset_url' ) ) {
    function agfo_asset_url( string $asset_uuid, bool $download = false ): string {
        return class_exists( 'AGFO_AIM_Asset_Delivery' ) ? AGFO_AIM_Asset_Delivery::url( $asset_uuid, $download ) : '';
    }
}
