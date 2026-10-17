<?php
/**
 * NEW 17.4.0: plugin updates from GitHub Releases (downtownck/agfo-windows-apps).
 *
 * - Release tag:  ai-manager-vX.Y.Z   (drafts and pre-releases are ignored)
 * - Asset:        agfo-ai-manager-X.Y.Z.zip  (root folder agfo-ai-manager/)
 * - Integrity:    the ZIP is downloaded by this class and checked against GitHub's SHA-256 asset
 *                 digest, or the release's SHA256SUMS.txt. No hash or a mismatch aborts the update.
 * - Site data:    data/data.json (model catalog, rankings, blacklist) is backed up before the
 *                 package is installed and restored afterwards, so an update never resets it.
 *
 * Disable with update_option( 'agfo_aim_github_updates', 0 ) or the
 * 'agfo_ai_manager_github_updates' filter.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_GitHub_Updater' ) ) {
    final class AGFO_AIM_GitHub_Updater {
        public const REPO        = 'downtownck/agfo-windows-apps';
        public const TAG_PREFIX  = 'ai-manager-v';
        public const SLUG        = 'agfo-ai-manager';
        public const TRANSIENT   = 'agfo_aim_github_release';
        public const CACHE_TTL   = 21600; // 6 h
        public const OPTION      = 'agfo_aim_github_updates';
        public const BACKUP_DIR  = 'agfo-ai-manager-backup';
        public const ALLOWED_HOSTS = [ 'api.github.com', 'github.com', 'githubusercontent.com' ];

        /** @var string plugin basename, e.g. agfo-ai-manager/agfo-ai-manager.php */
        private static $basename = '';
        /** @var string|null backup path of data.json during an update */
        private static $data_backup = null;

        public static function register_hooks( string $main_file ): void {
            self::$basename = function_exists( 'plugin_basename' ) ? plugin_basename( $main_file ) : self::SLUG . '/' . basename( $main_file );
            if ( ! self::enabled() ) {
                return;
            }
            add_filter( 'pre_set_site_transient_update_plugins', [ __CLASS__, 'inject_update' ] );
            add_filter( 'plugins_api', [ __CLASS__, 'plugins_api' ], 20, 3 );
            add_filter( 'upgrader_pre_download', [ __CLASS__, 'pre_download' ], 10, 4 );
            add_filter( 'upgrader_pre_install', [ __CLASS__, 'pre_install' ], 10, 2 );
            add_filter( 'upgrader_source_selection', [ __CLASS__, 'source_selection' ], 10, 4 );
            add_filter( 'upgrader_post_install', [ __CLASS__, 'post_install' ], 10, 3 );
        }

        public static function basename(): string {
            return self::$basename !== '' ? self::$basename : self::SLUG . '/agfo-ai-manager.php';
        }

        public static function enabled(): bool {
            $opt = function_exists( 'get_option' ) ? get_option( self::OPTION, 1 ) : 1;
            return (bool) apply_filters( 'agfo_ai_manager_github_updates', (bool) $opt );
        }

        // ------------------------------------------------------------------ release lookup

        public static function host_allowed( string $url ): bool {
            $parts = parse_url( $url );
            if ( ! is_array( $parts ) || strtolower( (string) ( $parts['scheme'] ?? '' ) ) !== 'https' || empty( $parts['host'] ) ) {
                return false;
            }
            $host = strtolower( (string) $parts['host'] );
            foreach ( self::ALLOWED_HOSTS as $d ) {
                if ( $host === $d || substr( $host, -strlen( '.' . $d ) ) === '.' . $d ) {
                    return true;
                }
            }
            return false;
        }

        public static function parse_tag( $tag ): ?string {
            if ( ! is_string( $tag ) || strpos( $tag, self::TAG_PREFIX ) !== 0 ) {
                return null;
            }
            $v = substr( $tag, strlen( self::TAG_PREFIX ) );
            return preg_match( '/^\d+(?:\.\d+){1,3}$/', $v ) ? $v : null;
        }

        /**
         * Pick the highest published (non-draft, non-prerelease) ai-manager release.
         * @return array|null [ version, tag, notes, url, published, package, sha256, sums_url ]
         */
        public static function select_release( $releases ): ?array {
            if ( ! is_array( $releases ) ) {
                return null;
            }
            $best = null;
            foreach ( $releases as $r ) {
                if ( ! is_array( $r ) || ! empty( $r['draft'] ) || ! empty( $r['prerelease'] ) ) {
                    continue;
                }
                $v = self::parse_tag( $r['tag_name'] ?? null );
                if ( null === $v || ( $best && version_compare( $v, $best['version'], '<=' ) ) ) {
                    continue;
                }
                $package = '';
                $sha     = '';
                $sums    = '';
                foreach ( (array) ( $r['assets'] ?? [] ) as $a ) {
                    if ( ! is_array( $a ) || empty( $a['name'] ) || empty( $a['browser_download_url'] ) ) {
                        continue;
                    }
                    $url = (string) $a['browser_download_url'];
                    if ( ! self::host_allowed( $url ) ) {
                        continue;
                    }
                    if ( $a['name'] === self::SLUG . '-' . $v . '.zip' ) {
                        $package = $url;
                        $dg      = (string) ( $a['digest'] ?? '' );
                        $sha     = ( strpos( $dg, 'sha256:' ) === 0 && preg_match( '/^[0-9a-f]{64}$/i', substr( $dg, 7 ) ) ) ? strtolower( substr( $dg, 7 ) ) : '';
                    } elseif ( preg_match( '/^SHA256SUMS(\.txt)?$/', (string) $a['name'] ) ) {
                        $sums = $url;
                    }
                }
                if ( $package === '' ) {
                    continue;
                }
                $best = [
                    'version'   => $v,
                    'tag'       => (string) $r['tag_name'],
                    'notes'     => substr( (string) ( $r['body'] ?? '' ), 0, 8000 ),
                    'url'       => self::host_allowed( (string) ( $r['html_url'] ?? '' ) ) ? (string) $r['html_url'] : 'https://github.com/' . self::REPO . '/releases',
                    'published' => substr( (string) ( $r['published_at'] ?? '' ), 0, 10 ),
                    'package'   => $package,
                    'sha256'    => $sha,
                    'sums_url'  => $sums,
                ];
            }
            return $best;
        }

        /** @return array|null cached latest release */
        public static function latest( bool $force = false ): ?array {
            if ( ! $force && function_exists( 'get_site_transient' ) ) {
                $cached = get_site_transient( self::TRANSIENT );
                if ( is_array( $cached ) ) {
                    return ! empty( $cached['version'] ) ? $cached : null;
                }
            }
            $url  = 'https://api.github.com/repos/' . self::REPO . '/releases?per_page=50';
            $resp = wp_remote_get( $url, [
                'timeout'    => 15,
                'headers'    => [ 'Accept' => 'application/vnd.github+json', 'X-GitHub-Api-Version' => '2022-11-28' ],
                'user-agent' => 'AGFO-AI-Manager/' . ( defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '0' ),
            ] );
            if ( is_wp_error( $resp ) || (int) wp_remote_retrieve_response_code( $resp ) !== 200 ) {
                // Short negative cache so a GitHub outage does not slow every admin page.
                if ( function_exists( 'set_site_transient' ) ) {
                    set_site_transient( self::TRANSIENT, [ 'version' => '' ], 1800 );
                }
                return null;
            }
            $release = self::select_release( json_decode( (string) wp_remote_retrieve_body( $resp ), true ) );
            if ( function_exists( 'set_site_transient' ) ) {
                set_site_transient( self::TRANSIENT, $release ?: [ 'version' => '' ], self::CACHE_TTL );
            }
            return $release;
        }

        private static function force_check(): bool {
            return ! empty( $_GET['force-check'] ); // phpcs:ignore WordPress.Security.NonceVerification -- read-only flag set by core's "Check again".
        }

        // ------------------------------------------------------------------ WordPress update hooks

        public static function inject_update( $transient ) {
            if ( ! is_object( $transient ) ) {
                return $transient;
            }
            $release = self::latest( self::force_check() );
            $current = defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '0';
            $item    = (object) [
                'id'           => 'github.com/' . self::REPO . '/' . self::SLUG,
                'slug'         => self::SLUG,
                'plugin'       => self::basename(),
                'new_version'  => $release ? $release['version'] : $current,
                'url'          => $release ? $release['url'] : 'https://github.com/' . self::REPO,
                'package'      => $release ? $release['package'] : '',
                'requires_php' => '7.4',
                'icons'        => [],
                'banners'      => [],
            ];
            if ( $release && version_compare( $release['version'], $current, '>' ) ) {
                if ( ! isset( $transient->response ) || ! is_array( $transient->response ) ) {
                    $transient->response = [];
                }
                $transient->response[ self::basename() ] = $item;
                if ( isset( $transient->no_update[ self::basename() ] ) ) {
                    unset( $transient->no_update[ self::basename() ] );
                }
            } else {
                $item->package = '';
                if ( ! isset( $transient->no_update ) || ! is_array( $transient->no_update ) ) {
                    $transient->no_update = [];
                }
                $transient->no_update[ self::basename() ] = $item;
                if ( isset( $transient->response[ self::basename() ] ) ) {
                    unset( $transient->response[ self::basename() ] );
                }
            }
            return $transient;
        }

        public static function plugins_api( $result, $action, $args ) {
            if ( 'plugin_information' !== $action || ! is_object( $args ) || ( $args->slug ?? '' ) !== self::SLUG ) {
                return $result;
            }
            $release = self::latest();
            if ( ! $release ) {
                return $result;
            }
            $notes = function_exists( 'esc_html' ) ? esc_html( $release['notes'] ) : htmlspecialchars( $release['notes'], ENT_QUOTES, 'UTF-8' );
            return (object) [
                'name'          => 'AGFO AI Manager',
                'slug'          => self::SLUG,
                'version'       => $release['version'],
                'author'        => 'AGFOCERT',
                'homepage'      => $release['url'],
                'requires_php'  => '7.4',
                'last_updated'  => $release['published'],
                'download_link' => $release['package'],
                'sections'      => [
                    'changelog'   => '<pre style="white-space:pre-wrap">' . $notes . '</pre>',
                    'description' => 'AGFO AI Manager — GitHub üzerinden SHA-256 doğrulamalı güncelleme.',
                ],
            ];
        }

        /**
         * Download our package ourselves and verify SHA-256. Other packages pass through untouched.
         * @return bool|string|WP_Error
         */
        public static function pre_download( $reply, $package, $upgrader = null, $hook_extra = [] ) {
            if ( false !== $reply || ! is_string( $package ) ) {
                return $reply;
            }
            $release = self::latest();
            if ( ! $release || $package !== $release['package'] ) {
                return $reply;
            }
            return self::download_verified( $release );
        }

        /** @return string|WP_Error local file path */
        public static function download_verified( array $release ) {
            if ( ! self::host_allowed( $release['package'] ) ) {
                return new WP_Error( 'agfo_aim_update_host', 'Güncelleme adresi izin verilen GitHub alanlarında değil.' );
            }
            $expected = self::expected_sha256( $release );
            if ( is_wp_error( $expected ) ) {
                return $expected;
            }
            if ( ! function_exists( 'download_url' ) && defined( 'ABSPATH' ) && file_exists( ABSPATH . 'wp-admin/includes/file.php' ) ) {
                require_once ABSPATH . 'wp-admin/includes/file.php';
            }
            $tmp = download_url( $release['package'], 300 );
            if ( is_wp_error( $tmp ) ) {
                return $tmp;
            }
            $actual = strtolower( (string) hash_file( 'sha256', $tmp ) );
            if ( ! hash_equals( $expected, $actual ) ) {
                @unlink( $tmp ); // phpcs:ignore
                return new WP_Error( 'agfo_aim_update_hash', 'Güncelleme paketi SHA-256 doğrulamasından geçmedi; dosya silindi.' );
            }
            return $tmp;
        }

        /** @return string|WP_Error */
        public static function expected_sha256( array $release ) {
            $from_sums = '';
            if ( ! empty( $release['sums_url'] ) && self::host_allowed( $release['sums_url'] ) ) {
                $resp = wp_remote_get( $release['sums_url'], [ 'timeout' => 15, 'redirection' => 5 ] );
                if ( ! is_wp_error( $resp ) && (int) wp_remote_retrieve_response_code( $resp ) === 200 ) {
                    $from_sums = self::parse_sums( (string) wp_remote_retrieve_body( $resp ), self::SLUG . '-' . $release['version'] . '.zip' );
                }
            }
            $digest = (string) ( $release['sha256'] ?? '' );
            if ( $digest !== '' && $from_sums !== '' && $digest !== $from_sums ) {
                return new WP_Error( 'agfo_aim_update_hash', 'GitHub özeti ile SHA256SUMS uyuşmuyor; güncelleme durduruldu.' );
            }
            $sha = $digest !== '' ? $digest : $from_sums;
            if ( $sha === '' ) {
                return new WP_Error( 'agfo_aim_update_hash', 'Güncelleme paketi için SHA-256 özeti bulunamadı; doğrulanamayan paket kurulmaz.' );
            }
            return $sha;
        }

        public static function parse_sums( string $text, string $name ): string {
            foreach ( preg_split( '/\R/', $text ) as $line ) {
                if ( preg_match( '/^\s*([0-9a-fA-F]{64})\s+\*?(\S+)\s*$/', $line, $m ) && $m[2] === $name ) {
                    return strtolower( $m[1] );
                }
            }
            return '';
        }

        // ------------------------------------------------------------------ data.json preservation

        private static function is_ours( $hook_extra ): bool {
            return is_array( $hook_extra ) && isset( $hook_extra['plugin'] ) && $hook_extra['plugin'] === self::basename();
        }

        public static function backup_dir(): string {
            $up = function_exists( 'wp_upload_dir' ) ? wp_upload_dir( null, false ) : [ 'basedir' => sys_get_temp_dir() ];
            return rtrim( (string) ( $up['basedir'] ?? sys_get_temp_dir() ), '/\\' ) . '/' . self::BACKUP_DIR;
        }

        public static function data_file(): string {
            return defined( 'AGFO_AIM_DATA_FILE' ) ? AGFO_AIM_DATA_FILE : dirname( __DIR__, 2 ) . '/data/data.json';
        }

        public static function pre_install( $response, $hook_extra ) {
            if ( self::is_ours( $hook_extra ) ) {
                self::backup_data();
            }
            return $response;
        }

        /** Copy data/data.json to uploads/agfo-ai-manager-backup/data.json. */
        public static function backup_data(): bool {
            self::$data_backup = null;
            $src = self::data_file();
            if ( ! is_file( $src ) || filesize( $src ) === 0 ) {
                return false;
            }
            $dir = self::backup_dir();
            if ( ! is_dir( $dir ) && ! ( function_exists( 'wp_mkdir_p' ) ? wp_mkdir_p( $dir ) : @mkdir( $dir, 0755, true ) ) ) { // phpcs:ignore
                return false;
            }
            if ( ! is_file( $dir . '/index.php' ) ) {
                @file_put_contents( $dir . '/index.php', "<?php\n// Silence is golden.\n" ); // phpcs:ignore
            }
            if ( ! is_file( $dir . '/.htaccess' ) ) {
                @file_put_contents( $dir . '/.htaccess', "Require all denied\nDeny from all\n" ); // phpcs:ignore
            }
            $dst = $dir . '/data.json';
            if ( ! @copy( $src, $dst ) ) { // phpcs:ignore
                return false;
            }
            self::$data_backup = $dst;
            return true;
        }

        /** Rename the extracted folder to agfo-ai-manager/ if GitHub produced another name. */
        public static function source_selection( $source, $remote_source, $upgrader = null, $hook_extra = [] ) {
            if ( ! self::is_ours( $hook_extra ) || ! is_string( $source ) ) {
                return $source;
            }
            $source = rtrim( $source, '/\\' );
            if ( basename( $source ) === self::SLUG ) {
                return agfo_aim_trailingslashit( $source );
            }
            $target = rtrim( (string) $remote_source, '/\\' ) . '/' . self::SLUG;
            if ( ! file_exists( $source . '/agfo-ai-manager.php' ) ) {
                return new WP_Error( 'agfo_aim_update_layout', 'Güncelleme paketinde agfo-ai-manager.php bulunamadı.' );
            }
            if ( @rename( $source, $target ) ) { // phpcs:ignore
                return agfo_aim_trailingslashit( $target );
            }
            return new WP_Error( 'agfo_aim_update_layout', 'Güncelleme klasörü yeniden adlandırılamadı.' );
        }

        public static function post_install( $response, $hook_extra, $result ) {
            if ( self::is_ours( $hook_extra ) ) {
                self::restore_data();
            }
            return $response;
        }

        /** Put the site's data.json back over the packaged default. */
        public static function restore_data(): bool {
            $bak = self::$data_backup ?: ( self::backup_dir() . '/data.json' );
            if ( ! is_file( $bak ) || filesize( $bak ) === 0 ) {
                return false;
            }
            $json = json_decode( (string) file_get_contents( $bak ), true );
            if ( ! is_array( $json ) ) {
                return false; // never restore a corrupt backup over a valid file
            }
            $dst = self::data_file();
            if ( ! is_dir( dirname( $dst ) ) ) {
                @mkdir( dirname( $dst ), 0755, true ); // phpcs:ignore
            }
            $ok = @copy( $bak, $dst ); // phpcs:ignore
            self::$data_backup = null;
            return (bool) $ok;
        }
    }
}

if ( ! function_exists( 'agfo_aim_trailingslashit' ) ) {
    function agfo_aim_trailingslashit( string $path ): string {
        return function_exists( 'trailingslashit' ) ? trailingslashit( $path ) : rtrim( $path, '/\\' ) . '/';
    }
}
