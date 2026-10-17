<?php
/**
 * AGFO AI Manager 17.4.0 — GitHub Releases updater tests.
 * Run from the plugin root: php tests/github-updater-tests.php
 * Minimal WordPress stubs; HTTP is faked. No network, no WordPress.
 */
if ( PHP_SAPI !== 'cli' ) { exit; }

$agfo_aim_test_root = dirname( __DIR__ );
$tmp_root = sys_get_temp_dir() . '/agfo-gh-upd-' . getmypid();
@mkdir( $tmp_root . '/plugin/data', 0777, true );
@mkdir( $tmp_root . '/uploads', 0777, true );
if ( ! defined( 'ABSPATH' ) ) define( 'ABSPATH', $tmp_root . '/' );
if ( ! defined( 'AGFO_AIM_VERSION' ) ) define( 'AGFO_AIM_VERSION', '17.4.0' );
if ( ! defined( 'AGFO_AIM_DATA_FILE' ) ) define( 'AGFO_AIM_DATA_FILE', $tmp_root . '/plugin/data/data.json' );

$GLOBALS['G'] = [ 'F' => [], 'O' => [], 'T' => [], 'HTTP' => [], 'GETS' => 0, 'DL' => null ];
function add_filter( $h, $cb, $p = 10, $a = 1 ) { $GLOBALS['G']['F'][ $h ][] = $cb; return true; }
function add_action( $h, $cb, $p = 10, $a = 1 ) { return add_filter( $h, $cb, $p, $a ); }
function apply_filters( $h, $v, ...$a ) { foreach ( $GLOBALS['G']['F'][ $h ] ?? [] as $cb ) { $v = $cb( $v, ...$a ); } return $v; }
function get_option( $k, $d = false ) { return $GLOBALS['G']['O'][ $k ] ?? $d; }
function plugin_basename( $f ) { return 'agfo-ai-manager/agfo-ai-manager.php'; }
function get_site_transient( $k ) { return $GLOBALS['G']['T'][ $k ] ?? false; }
function set_site_transient( $k, $v, $e = 0 ) { $GLOBALS['G']['T'][ $k ] = $v; return true; }
function esc_html( $s ) { return htmlspecialchars( (string) $s, ENT_QUOTES, 'UTF-8' ); }
function wp_upload_dir( $t = null, $c = true ) { return [ 'basedir' => $GLOBALS['tmp_root'] . '/uploads' ]; }
function wp_mkdir_p( $d ) { return is_dir( $d ) || mkdir( $d, 0777, true ); }
function trailingslashit( $p ) { return rtrim( $p, '/\\' ) . '/'; }
class WP_Error { public $c; public $m; function __construct( $c = '', $m = '', $d = null ) { $this->c = $c; $this->m = $m; } function get_error_message() { return $this->m; } function get_error_code() { return $this->c; } }
function is_wp_error( $x ) { return $x instanceof WP_Error; }
function wp_remote_get( $url, $args = [] ) { $GLOBALS['G']['GETS']++; return $GLOBALS['G']['HTTP'][ $url ] ?? new WP_Error( 'http', 'no fake for ' . $url ); }
function wp_remote_retrieve_response_code( $r ) { return $r['code'] ?? 0; }
function wp_remote_retrieve_body( $r ) { return $r['body'] ?? ''; }
function download_url( $url, $timeout = 300 ) {
    $GLOBALS['G']['DL_URL'] = $url;
    $f = $GLOBALS['tmp_root'] . '/dl-' . uniqid() . '.zip';
    file_put_contents( $f, $GLOBALS['G']['DL'] );
    $GLOBALS['G']['DL_FILE'] = $f;
    return $f;
}

require $agfo_aim_test_root . '/includes/core/class-github-updater.php';
$U = 'AGFO_AIM_GitHub_Updater';

$pass = 0; $fail = 0;
function gu( string $name, bool $ok, string $detail = '' ): void {
    global $pass, $fail;
    if ( $ok ) { $pass++; echo "PASS  {$name}\n"; } else { $fail++; echo "FAIL  {$name}" . ( $detail !== '' ? " — {$detail}" : '' ) . "\n"; }
}
$zip = 'PK-fake-zip-17.5.0';
$sha = hash( 'sha256', $zip );
function rel( $tag, $assets, $draft = false, $pre = false ) { return [ 'tag_name' => $tag, 'draft' => $draft, 'prerelease' => $pre, 'body' => "Notlar <script>x</script>", 'html_url' => 'https://github.com/downtownck/agfo-windows-apps/releases/tag/' . $tag, 'published_at' => '2026-10-18T10:00:00Z', 'assets' => $assets ]; }
function asset( $name, $digest = null, $host = 'github.com' ) { $a = [ 'name' => $name, 'browser_download_url' => 'https://' . $host . '/downtownck/agfo-windows-apps/releases/download/x/' . $name ]; if ( $digest ) $a['digest'] = 'sha256:' . $digest; return $a; }
$releases = [
    rel( 'ai-manager-v17.9.0', [ asset( 'agfo-ai-manager-17.9.0.zip', $sha ) ], true ),       // draft
    rel( 'ai-manager-v17.8.0', [ asset( 'agfo-ai-manager-17.8.0.zip', $sha ) ], false, true ), // prerelease
    rel( 'system-care-v9.0.0', [ asset( 'AGFO-System-Care-v9.0.0.zip', $sha ) ] ),
    rel( 'ai-manager-v17.10.0-rc', [ asset( 'agfo-ai-manager-17.10.0.zip', $sha ) ] ),
    rel( 'ai-manager-v17.6.0', [ asset( 'agfo-ai-manager-17.6.0.zip', $sha, 'evil.example.com' ) ] ), // bad host
    rel( 'ai-manager-v17.5.0', [ asset( 'agfo-ai-manager-17.5.0.zip', $sha ), asset( 'SHA256SUMS.txt' ) ] ),
    rel( 'ai-manager-v17.4.1', [ asset( 'agfo-ai-manager-17.4.1.zip', $sha ) ] ),
    rel( 'ai-manager-v17.7.0', [ asset( 'readme.txt' ) ] ), // no package
    'junk',
];

// G1-G6: selection.
$best = $U::select_release( $releases );
gu( 'G1 picks highest published ai-manager release (17.5.0)', is_array( $best ) && $best['version'] === '17.5.0' && $best['tag'] === 'ai-manager-v17.5.0', json_encode( $best['version'] ?? null ) );
gu( 'G2 package url, digest and SHA256SUMS url captured', $best['package'] === 'https://github.com/downtownck/agfo-windows-apps/releases/download/x/agfo-ai-manager-17.5.0.zip' && $best['sha256'] === $sha && strpos( $best['sums_url'], 'SHA256SUMS.txt' ) !== false );
gu( 'G3 tag parsing rejects other prefixes and suffixes', $U::parse_tag( 'ai-manager-v17.4.0' ) === '17.4.0' && $U::parse_tag( 'ai-manager-v17.4.0-rc' ) === null && $U::parse_tag( 'supertools-v1.7.0' ) === null && $U::parse_tag( null ) === null );
gu( 'G4 version compare is numeric (17.10 > 17.9)', $U::select_release( [ rel( 'ai-manager-v17.9.0', [ asset( 'agfo-ai-manager-17.9.0.zip', $sha ) ] ), rel( 'ai-manager-v17.10.0', [ asset( 'agfo-ai-manager-17.10.0.zip', $sha ) ] ) ] )['version'] === '17.10.0' );
gu( 'G5 non-array / empty input -> null', $U::select_release( null ) === null && $U::select_release( [] ) === null && $U::select_release( [ 'x' ] ) === null );
gu( 'G6 host allowlist', $U::host_allowed( 'https://github.com/a' ) && $U::host_allowed( 'https://objects.githubusercontent.com/a' ) && $U::host_allowed( 'https://api.github.com/x' ) && ! $U::host_allowed( 'http://github.com/a' ) && ! $U::host_allowed( 'https://github.com.evil.io/a' ) && ! $U::host_allowed( 'https://evilgithub.com/a' ) && ! $U::host_allowed( 'ftp://github.com/a' ) );

// G7-G10: transient injection.
$api = 'https://api.github.com/repos/downtownck/agfo-windows-apps/releases?per_page=50';
$GLOBALS['G']['HTTP'][ $api ] = [ 'code' => 200, 'body' => json_encode( $releases ) ];
$t = $U::inject_update( (object) [ 'response' => [], 'no_update' => [], 'checked' => [] ] );
$item = $t->response['agfo-ai-manager/agfo-ai-manager.php'] ?? null;
gu( 'G7 newer release injected into response', is_object( $item ) && $item->new_version === '17.5.0' && $item->slug === 'agfo-ai-manager' && $item->plugin === 'agfo-ai-manager/agfo-ai-manager.php' && strpos( $item->package, 'agfo-ai-manager-17.5.0.zip' ) !== false );
$gets = $GLOBALS['G']['GETS'];
$U::inject_update( (object) [] );
gu( 'G8 release cached in site transient (no second request)', $GLOBALS['G']['GETS'] === $gets );
$_GET['force-check'] = '1';
$U::inject_update( (object) [] );
gu( 'G9 force-check bypasses the cache', $GLOBALS['G']['GETS'] === $gets + 1 );
unset( $_GET['force-check'] );
$GLOBALS['G']['T'] = [];
$GLOBALS['G']['HTTP'][ $api ] = [ 'code' => 200, 'body' => json_encode( [ rel( 'ai-manager-v17.4.0', [ asset( 'agfo-ai-manager-17.4.0.zip', $sha ) ] ) ] ) ];
$t = $U::inject_update( (object) [ 'response' => [ 'agfo-ai-manager/agfo-ai-manager.php' => 'stale' ] ] );
gu( 'G10 same version -> no_update entry, stale response removed', ! isset( $t->response['agfo-ai-manager/agfo-ai-manager.php'] ) && isset( $t->no_update['agfo-ai-manager/agfo-ai-manager.php'] ) && $t->no_update['agfo-ai-manager/agfo-ai-manager.php']->package === '' );
$GLOBALS['G']['T'] = [];
$GLOBALS['G']['HTTP'][ $api ] = [ 'code' => 403, 'body' => '' ];
$t = $U::inject_update( (object) [ 'response' => [] ] );
gu( 'G11 GitHub error -> nothing injected, short negative cache', empty( $t->response ) && isset( $GLOBALS['G']['T']['agfo_aim_github_release'] ) );
gu( 'G12 non-object transient passes through', $U::inject_update( false ) === false );

// G13-G14: plugins_api.
$GLOBALS['G']['T'] = [];
$GLOBALS['G']['HTTP'][ $api ] = [ 'code' => 200, 'body' => json_encode( $releases ) ];
$info = $U::plugins_api( false, 'plugin_information', (object) [ 'slug' => 'agfo-ai-manager' ] );
gu( 'G13 plugins_api details, notes escaped', is_object( $info ) && $info->version === '17.5.0' && strpos( $info->sections['changelog'], '<script>' ) === false && strpos( $info->sections['changelog'], '&lt;script&gt;' ) !== false );
gu( 'G14 plugins_api ignores other slugs', $U::plugins_api( 'orig', 'plugin_information', (object) [ 'slug' => 'akismet' ] ) === 'orig' );

// G15-G20: verified download.
$best = $U::latest();
$GLOBALS['G']['DL'] = $zip;
$GLOBALS['G']['HTTP'][ $best['sums_url'] ] = [ 'code' => 200, 'body' => $sha . "  agfo-ai-manager-17.5.0.zip\n" ];
$f = $U::pre_download( false, $best['package'] );
gu( 'G15 matching digest + SHA256SUMS -> local file returned', is_string( $f ) && is_file( $f ) && file_get_contents( $f ) === $zip );
gu( 'G16 other packages are not intercepted', $U::pre_download( false, 'https://downloads.wordpress.org/plugin/akismet.zip' ) === false && $U::pre_download( true, $best['package'] ) === true );
$GLOBALS['G']['DL'] = 'tampered';
$r = $U::pre_download( false, $best['package'] );
gu( 'G17 hash mismatch -> WP_Error and temp file deleted', is_wp_error( $r ) && $r->get_error_code() === 'agfo_aim_update_hash' && ! is_file( $GLOBALS['G']['DL_FILE'] ) );
$GLOBALS['G']['HTTP'][ $best['sums_url'] ] = [ 'code' => 200, 'body' => str_repeat( '0', 64 ) . "  agfo-ai-manager-17.5.0.zip\n" ];
$r = $U::expected_sha256( $best );
gu( 'G18 digest vs SHA256SUMS disagreement -> error', is_wp_error( $r ) );
$GLOBALS['G']['HTTP'][ $best['sums_url'] ] = [ 'code' => 200, 'body' => $sha . " *agfo-ai-manager-17.5.0.zip\n" ];
gu( 'G19 SHA256SUMS alone is accepted', $U::expected_sha256( array_merge( $best, [ 'sha256' => '' ] ) ) === $sha );
$r = $U::expected_sha256( array_merge( $best, [ 'sha256' => '', 'sums_url' => '' ] ) );
gu( 'G20 no hash anywhere -> refuse', is_wp_error( $r ) && strpos( $r->get_error_message(), 'SHA-256' ) !== false );
$r = $U::download_verified( array_merge( $best, [ 'package' => 'https://evil.example.com/a.zip' ] ) );
gu( 'G21 package outside allowlist refused', is_wp_error( $r ) && $r->get_error_code() === 'agfo_aim_update_host' );
gu( 'G22 parse_sums', $U::parse_sums( "x\n$sha  other.zip\n" . strtoupper( $sha ) . "  agfo-ai-manager-1.zip", 'agfo-ai-manager-1.zip' ) === $sha && $U::parse_sums( 'junk', 'a' ) === '' );

// G23-G27: data.json preservation.
$ours  = [ 'plugin' => 'agfo-ai-manager/agfo-ai-manager.php' ];
$site  = json_encode( [ 'models' => [ 'openai' => [ 'gpt-site-only' ] ], 'blacklist' => [ 'x' ] ] );
file_put_contents( AGFO_AIM_DATA_FILE, $site );
$U::pre_install( true, [ 'plugin' => 'akismet/akismet.php' ] );
gu( 'G23 other plugins do not trigger a backup', ! is_file( $tmp_root . '/uploads/agfo-ai-manager-backup/data.json' ) );
$U::pre_install( true, $ours );
gu( 'G24 backup written to uploads with deny files', is_file( $tmp_root . '/uploads/agfo-ai-manager-backup/data.json' ) && is_file( $tmp_root . '/uploads/agfo-ai-manager-backup/.htaccess' ) && is_file( $tmp_root . '/uploads/agfo-ai-manager-backup/index.php' ) );
file_put_contents( AGFO_AIM_DATA_FILE, json_encode( [ 'models' => [ 'openai' => [ 'packaged-default' ] ] ] ) ); // new package overwrote it
$U::post_install( true, $ours, [] );
gu( 'G25 site data.json restored after install', file_get_contents( AGFO_AIM_DATA_FILE ) === $site );
file_put_contents( $tmp_root . '/uploads/agfo-ai-manager-backup/data.json', '{broken' );
file_put_contents( AGFO_AIM_DATA_FILE, '{"ok":1}' );
gu( 'G26 corrupt backup never overwrites a valid file', $U::restore_data() === false && file_get_contents( AGFO_AIM_DATA_FILE ) === '{"ok":1}' );

// G27-G28: extracted folder normalised to agfo-ai-manager/.
$rs = $tmp_root . '/remote'; @mkdir( $rs . '/agfo-ai-manager-main', 0777, true ); file_put_contents( $rs . '/agfo-ai-manager-main/agfo-ai-manager.php', '<?php' );
$out = $U::source_selection( $rs . '/agfo-ai-manager-main/', $rs, null, $ours );
gu( 'G27 odd folder renamed to agfo-ai-manager/', $out === $rs . '/agfo-ai-manager/' && is_file( $rs . '/agfo-ai-manager/agfo-ai-manager.php' ) );
gu( 'G28 correct folder untouched, other plugins ignored', $U::source_selection( $rs . '/agfo-ai-manager/', $rs, null, $ours ) === $rs . '/agfo-ai-manager/' && $U::source_selection( '/x/y/', $rs, null, [ 'plugin' => 'a/b.php' ] ) === '/x/y/' );

// G29-G30: enable switch and hooks.
$GLOBALS['G']['F'] = [];
$U::register_hooks( $agfo_aim_test_root . '/agfo-ai-manager.php' );
gu( 'G29 hooks registered when enabled', isset( $GLOBALS['G']['F']['pre_set_site_transient_update_plugins'], $GLOBALS['G']['F']['upgrader_pre_download'], $GLOBALS['G']['F']['upgrader_post_install'], $GLOBALS['G']['F']['plugins_api'] ) );
$GLOBALS['G']['F'] = []; $GLOBALS['G']['O']['agfo_aim_github_updates'] = 0;
$U::register_hooks( $agfo_aim_test_root . '/agfo-ai-manager.php' );
gu( 'G30 option 0 disables all update hooks', empty( $GLOBALS['G']['F'] ) );

// cleanup
$it = new RecursiveIteratorIterator( new RecursiveDirectoryIterator( $tmp_root, FilesystemIterator::SKIP_DOTS ), RecursiveIteratorIterator::CHILD_FIRST );
foreach ( $it as $p ) { $p->isDir() ? @rmdir( $p->getPathname() ) : @unlink( $p->getPathname() ); }
@rmdir( $tmp_root );

echo "\n{$pass} pass, {$fail} fail\n";
exit( $fail > 0 ? 1 : 0 );
