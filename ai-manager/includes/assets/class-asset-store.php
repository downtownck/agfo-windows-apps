<?php
/**
 * Private generated-asset storage outside the web root.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Asset_Store' ) ) {
    final class AGFO_AIM_Asset_Store {
        const DEFAULT_RETENTION_DAYS = 30;

        public static function storage_root(): string {
            if ( defined( 'AGFO_AI_STORE_PATH' ) && is_string( AGFO_AI_STORE_PATH ) && '' !== AGFO_AI_STORE_PATH ) {
                $root = AGFO_AI_STORE_PATH;
            } else {
                $root = trailingslashit( dirname( untrailingslashit( ABSPATH ) ) ) . 'agfo-ai-store';
            }
            return wp_normalize_path( (string) apply_filters( 'agfo_ai_store_path', $root ) );
        }

        /**
         * @return true|WP_Error
         */
        public static function ensure_storage_root() {
            $root = self::storage_root();
            $web  = wp_normalize_path( realpath( ABSPATH ) ?: ABSPATH );

            if ( 0 === strpos( trailingslashit( $root ), trailingslashit( $web ) ) ) {
                return new WP_Error( 'agfo_store_inside_webroot', 'AGFO AI depolama dizini web root dışında olmalıdır.' );
            }

            if ( ! is_dir( $root ) && ! wp_mkdir_p( $root ) ) {
                return new WP_Error( 'agfo_store_create', 'AGFO AI özel depolama dizini oluşturulamadı: ' . esc_html( $root ) );
            }

            $root_real = wp_normalize_path( realpath( $root ) ?: $root );
            if ( 0 === strpos( trailingslashit( $root_real ), trailingslashit( $web ) ) ) {
                return new WP_Error( 'agfo_store_symlink_webroot', 'AGFO AI depolama dizini veya symlink hedefi web root içinde olamaz.' );
            }
            if ( ! is_writable( $root_real ) ) {
                return new WP_Error( 'agfo_store_not_writable', 'AGFO AI özel depolama dizini yazılabilir değil.' );
            }

            $index = trailingslashit( $root_real ) . 'index.php';
            if ( ! file_exists( $index ) ) {
                @file_put_contents( $index, "<?php\n// Silence is golden.\n" );
            }

            return true;
        }

        /**
         * Moves a provider temp file to private storage and records the asset.
         *
         * @return array|WP_Error
         */
        public static function store_temp_file( int $job_id, string $temp_file, array $args ) {
            global $wpdb;

            $ready = self::ensure_storage_root();
            if ( is_wp_error( $ready ) ) {
                return $ready;
            }
            if ( ! is_file( $temp_file ) || ! is_readable( $temp_file ) ) {
                return new WP_Error( 'agfo_asset_temp_missing', 'Sağlayıcı ses dosyası bulunamadı.' );
            }

            $mime       = sanitize_text_field( (string) ( $args['mime'] ?? 'application/octet-stream' ) );
            $extension  = self::extension_for_mime( $mime );
            $asset_uuid = wp_generate_uuid4();
            $year       = wp_date( 'Y' );
            $month      = wp_date( 'm' );
            $dir        = trailingslashit( self::storage_root() ) . $year . '/' . $month;

            if ( ! is_dir( $dir ) && ! wp_mkdir_p( $dir ) ) {
                return new WP_Error( 'agfo_asset_dir', 'Özel medya alt dizini oluşturulamadı.' );
            }

            $final   = wp_normalize_path( trailingslashit( $dir ) . str_replace( '-', '', $asset_uuid ) . '.' . $extension );
            $partial = $final . '.partial';

            if ( ! @rename( $temp_file, $partial ) ) {
                if ( ! @copy( $temp_file, $partial ) ) {
                    return new WP_Error( 'agfo_asset_move', 'Ses dosyası özel depolamaya taşınamadı.' );
                }
                @unlink( $temp_file );
            }

            $bytes     = (int) filesize( $partial );
            $max_bytes = (int) apply_filters( 'agfo_ai_asset_max_bytes', 100 * 1024 * 1024, 'audio' );
            $sha256    = hash_file( 'sha256', $partial );
            if ( $bytes < 1 || ! is_string( $sha256 ) || 64 !== strlen( $sha256 ) ) {
                @unlink( $partial );
                return new WP_Error( 'agfo_asset_integrity', 'Ses dosyası bütünlük kontrolünden geçemedi.' );
            }
            if ( $max_bytes > 0 && $bytes > $max_bytes ) {
                @unlink( $partial );
                return new WP_Error( 'agfo_asset_too_large', 'Ses dosyası izin verilen azami boyutu aşıyor.' );
            }
            if ( class_exists( 'finfo' ) ) {
                $finfo    = new finfo( FILEINFO_MIME_TYPE );
                $detected = (string) $finfo->file( $partial );
                if ( 0 === strpos( $detected, 'text/' ) || in_array( $detected, [ 'application/json', 'text/html' ], true ) ) {
                    @unlink( $partial );
                    return new WP_Error( 'agfo_asset_mime', 'Sağlayıcı ses yerine metin veya hata gövdesi döndürdü.' );
                }
            }

            if ( ! @rename( $partial, $final ) ) {
                @unlink( $partial );
                return new WP_Error( 'agfo_asset_finalize', 'Ses dosyası atomik olarak tamamlanamadı.' );
            }

            $provenance = $args['provenance'] ?? [];
            if ( ! is_array( $provenance ) || empty( $provenance['generated_by'] ) || empty( $provenance['capability'] ) ) {
                @unlink( $final );
                return new WP_Error( 'agfo_asset_provenance', 'Üretilen medya için zorunlu provenance bilgisi eksik.' );
            }

            $visibility    = in_array( (string) ( $args['visibility'] ?? 'private' ), [ 'private', 'public' ], true ) ? (string) $args['visibility'] : 'private';
            $retention     = max( 1, min( 3650, (int) ( $args['retention_days'] ?? self::DEFAULT_RETENTION_DAYS ) ) );
            $retention_at  = wp_date( 'Y-m-d H:i:s', time() + ( $retention * DAY_IN_SECONDS ) );
            $created_by    = absint( $args['created_by'] ?? get_current_user_id() );
            $attachment_id = null;

            if ( 'public' === $visibility && ! empty( $args['publish_to_media_library'] ) ) {
                $attachment_id = self::publish_copy_to_media_library( $final, $mime, (string) ( $args['title'] ?? 'AGFO AI Speech' ), $provenance );
                if ( is_wp_error( $attachment_id ) ) {
                    $attachment_id = null;
                }
            }

            $table = AGFO_AIM_Schema::assets_table();
            $ok    = $wpdb->insert(
                $table,
                [
                    'asset_uuid'      => $asset_uuid,
                    'job_id'          => $job_id,
                    'kind'            => sanitize_key( (string) ( $args['kind'] ?? 'audio' ) ),
                    'storage_path'    => $final,
                    'original_name'   => sanitize_file_name( (string) ( $args['original_name'] ?? '' ) ),
                    'mime'            => $mime,
                    'bytes'           => $bytes,
                    'sha256'          => $sha256,
                    'attachment_id'   => $attachment_id,
                    'visibility'      => $visibility,
                    'provenance_json' => wp_json_encode( $provenance, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ),
                    'retention_until' => $retention_at,
                    'created_by'      => $created_by,
                    'created_at'      => current_time( 'mysql' ),
                ],
                [ '%s', '%d', '%s', '%s', '%s', '%s', '%d', '%s', '%d', '%s', '%s', '%s', '%d', '%s' ]
            );

            if ( false === $ok ) {
                @unlink( $final );
                return new WP_Error( 'agfo_asset_db', 'Özel medya kaydı veri tabanına yazılamadı.' );
            }

            return self::get( $asset_uuid );
        }

        public static function get( string $asset_uuid ): ?array {
            global $wpdb;
            if ( ! class_exists( 'AGFO_AIM_Schema' ) ) {
                return null;
            }
            $table = AGFO_AIM_Schema::assets_table();
            $row   = $wpdb->get_row( $wpdb->prepare( "SELECT * FROM {$table} WHERE asset_uuid = %s", sanitize_text_field( $asset_uuid ) ), ARRAY_A );
            return is_array( $row ) ? $row : null;
        }

        public static function get_by_job( int $job_id ): ?array {
            global $wpdb;
            if ( ! class_exists( 'AGFO_AIM_Schema' ) ) {
                return null;
            }
            $table = AGFO_AIM_Schema::assets_table();
            $row   = $wpdb->get_row( $wpdb->prepare( "SELECT * FROM {$table} WHERE job_id = %d ORDER BY id DESC LIMIT 1", $job_id ), ARRAY_A );
            return is_array( $row ) ? $row : null;
        }

        public static function cleanup_expired(): void {
            global $wpdb;
            if ( ! class_exists( 'AGFO_AIM_Schema' ) ) {
                return;
            }
            $table = AGFO_AIM_Schema::assets_table();
            $rows  = $wpdb->get_results(
                $wpdb->prepare(
                    "SELECT id, storage_path FROM {$table} WHERE retention_until IS NOT NULL AND retention_until < %s LIMIT 100",
                    current_time( 'mysql' )
                ),
                ARRAY_A
            );
            foreach ( is_array( $rows ) ? $rows : [] as $row ) {
                $path = wp_normalize_path( (string) $row['storage_path'] );
                if ( self::path_is_inside_store( $path ) && is_file( $path ) ) {
                    @unlink( $path );
                }
                $wpdb->delete( $table, [ 'id' => (int) $row['id'] ], [ '%d' ] );
            }
        }

        public static function path_is_inside_store( string $path ): bool {
            $root_real = realpath( self::storage_root() );
            $path_real = realpath( $path );
            if ( false === $root_real || false === $path_real ) {
                return false;
            }
            return 0 === strpos( trailingslashit( wp_normalize_path( $path_real ) ), trailingslashit( wp_normalize_path( $root_real ) ) );
        }

        private static function extension_for_mime( string $mime ): string {
            $map = [
                'audio/mpeg'              => 'mp3',
                'audio/mp3'               => 'mp3',
                'audio/wav'               => 'wav',
                'audio/x-wav'             => 'wav',
                'audio/ogg'               => 'ogg',
                'audio/opus'              => 'opus',
                'audio/aac'               => 'aac',
                'audio/flac'              => 'flac',
                'audio/l16'               => 'pcm',
                'application/octet-stream'=> 'bin',
            ];
            return $map[ strtolower( $mime ) ] ?? 'bin';
        }

        /**
         * Explicit opt-in public copy.
         *
         * @return int|WP_Error
         */
        private static function publish_copy_to_media_library( string $source, string $mime, string $title, array $provenance ) {
            if ( ! function_exists( 'media_handle_sideload' ) ) {
                require_once ABSPATH . 'wp-admin/includes/file.php';
                require_once ABSPATH . 'wp-admin/includes/media.php';
                require_once ABSPATH . 'wp-admin/includes/image.php';
            }

            $ext      = self::extension_for_mime( $mime );
            $tmp_copy = wp_tempnam( 'agfo-ai-public.' . $ext );
            if ( ! $tmp_copy || ! @copy( $source, $tmp_copy ) ) {
                return new WP_Error( 'agfo_asset_public_copy', 'Medya Kütüphanesi kopyası hazırlanamadı.' );
            }

            $attachment_id = media_handle_sideload(
                [ 'name' => sanitize_file_name( $title ) . '.' . $ext, 'tmp_name' => $tmp_copy ],
                0,
                $title
            );
            if ( is_wp_error( $attachment_id ) ) {
                @unlink( $tmp_copy );
                return $attachment_id;
            }

            update_post_meta( $attachment_id, '_agfo_ai_generated', 1 );
            update_post_meta( $attachment_id, '_agfo_ai_provenance', wp_json_encode( $provenance ) );
            return (int) $attachment_id;
        }
    }
}
