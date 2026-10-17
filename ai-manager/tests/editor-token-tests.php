<?php
/**
 * AGFO AI Manager 17.5.0 — AI Editor connection key tests.
 * Run from the plugin root: php tests/editor-token-tests.php   (minimal WordPress stubs, no network)
 */
if ( PHP_SAPI !== 'cli' ) { exit; }
$root = dirname( __DIR__ );
if ( ! defined( 'ABSPATH' ) ) define( 'ABSPATH', sys_get_temp_dir() . '/' );
if ( ! defined( 'AGFO_AIM_VERSION' ) ) define( 'AGFO_AIM_VERSION', '17.5.0' );
$GLOBALS['T'] = [ 'META' => [], 'USER' => 0, 'F' => [], 'A' => [], 'ROUTES' => [], 'CAN' => true ];
function add_action( $h, $cb, $p = 10, $a = 1 ) { $GLOBALS['T']['A'][ $h ][] = $cb; return true; }
function add_filter( $h, $cb, $p = 10, $a = 1 ) { $GLOBALS['T']['F'][ $h ][] = $cb; return true; }
function apply_filters( $h, $v, ...$a ) { foreach ( $GLOBALS['T']['F'][ $h ] ?? [] as $cb ) { $v = $cb( $v, ...$a ); } return $v; }
function get_user_meta( $u, $k, $single = false ) { return $GLOBALS['T']['META'][ $u ][ $k ] ?? ''; }
function update_user_meta( $u, $k, $v ) { $GLOBALS['T']['META'][ $u ][ $k ] = $v; return true; }
function wp_salt( $s = 'auth' ) { return 'test-salt-' . $s; }
function sanitize_text_field( $s ) { return trim( strip_tags( (string) $s ) ); }
function sanitize_key( $k ) { return preg_replace( '/[^a-z0-9_\-]/', '', strtolower( (string) $k ) ); }
function wp_unslash( $s ) { return $s; }
function get_userdata( $id ) { return in_array( (int) $id, [ 5, 9 ], true ) ? (object) [ 'ID' => (int) $id ] : false; }
function wp_set_current_user( $id ) { $GLOBALS['T']['USER'] = (int) $id; return (object) [ 'ID' => (int) $id ]; }
function is_user_logged_in() { return $GLOBALS['T']['USER'] > 0; }
function current_user_can( $c ) { return $GLOBALS['T']['CAN']; }
function register_rest_route( $ns, $r, $args ) { $GLOBALS['T']['ROUTES'][ $ns . $r ] = $args; return true; }
function is_ssl() { return true; }
function wp_is_application_passwords_available() { return false; }
class WP_Error { public $c; public $m; public $d; function __construct( $c = '', $m = '', $d = null ) { $this->c = $c; $this->m = $m; $this->d = $d; } function get_error_message() { return $this->m; } function get_error_code() { return $this->c; } function get_error_data() { return $this->d; } }
function is_wp_error( $x ) { return $x instanceof WP_Error; }
class WP_REST_Response { public $data; public $status; function __construct( $d, $s ) { $this->data = $d; $this->status = $s; } }

require $root . '/includes/api/class-editor-api.php';
require $root . '/includes/api/class-editor-tokens.php';
$pass = 0; $fail = 0;
function ok( $n, $c ) { global $pass, $fail; if ( $c ) { $pass++; echo "PASS  $n\n"; } else { $fail++; echo "FAIL  $n\n"; } }
$K = 'AGFO_AIM_Editor_Tokens';

AGFO_AIM_Editor_API::register_hooks();
foreach ( $GLOBALS['T']['A']['rest_api_init'] as $cb ) { $cb(); }
ok( 'K1 ping route is public, others protected', ( $GLOBALS['T']['ROUTES']['agfo-ai/v1/editor/ping']['permission_callback'] ?? '' ) === '__return_true'
    && ( $GLOBALS['T']['ROUTES']['agfo-ai/v1/editor/info']['permission_callback'][1] ?? '' ) === 'can_use' );

$key = $K::create( 5, '<b>Ofis</b>' );
ok( 'K2 key format', is_string( $key ) && preg_match( '/^agfoed\.5\.[a-z0-9]{8}\.[A-Za-z0-9]{40}$/', $key ) === 1 );
$rows = $K::list_for( 5 );
$row = reset( $rows );
ok( 'K3 only HMAC stored, label sanitised', count( $rows ) === 1 && strpos( json_encode( $rows ), substr( $key, -40 ) ) === false && strlen( $row['hash'] ) === 64 && $row['label'] === 'Ofis' );
ok( 'K4 verify ok', $K::verify( $key ) === 5 );
ok( 'K5 last_used recorded', $K::list_for( 5 )[ explode( '.', $key )[2] ]['last_used'] !== '' );
$bad = substr( $key, 0, -1 ) . ( substr( $key, -1 ) === 'A' ? 'B' : 'A' );
ok( 'K6 wrong secret rejected', $K::verify( $bad ) === 0 && $K::last_error() === 'unknown' );
ok( 'K7 key of another user id rejected', $K::verify( preg_replace( '/^agfoed\.5\./', 'agfoed.9.', $key ) ) === 0 );
ok( 'K8 malformed rejected', $K::verify( 'agfoed.5.x.y' ) === 0 && $K::last_error() === 'format' );

// request flow through can_use()
$_SERVER['HTTP_X_AGFO_EDITOR_TOKEN'] = $key;
$GLOBALS['T']['USER'] = 0;
ok( 'K9 valid header -> can_use true, user switched', AGFO_AIM_Editor_API::can_use() === true && $GLOBALS['T']['USER'] === 5 );
$GLOBALS['T']['USER'] = 0;
$_SERVER['HTTP_X_AGFO_EDITOR_TOKEN'] = $bad;
$e = AGFO_AIM_Editor_API::can_use();
ok( 'K10 invalid key -> 401 agfo_editor_token_invalid', is_wp_error( $e ) && $e->get_error_code() === 'agfo_editor_token_invalid' && $e->get_error_data()['status'] === 401 && $GLOBALS['T']['USER'] === 0 );
$_SERVER['HTTP_X_AGFO_EDITOR_TOKEN'] = $key;
$GLOBALS['T']['CAN'] = false;
$e = AGFO_AIM_Editor_API::can_use();
ok( 'K11 valid key but no capability -> 403', is_wp_error( $e ) && $e->get_error_code() === 'agfo_editor_forbidden' );
$GLOBALS['T']['CAN'] = true;
unset( $_SERVER['HTTP_X_AGFO_EDITOR_TOKEN'] );
$GLOBALS['T']['USER'] = 0;
$_SERVER['HTTP_AUTHORIZATION'] = 'Bearer ' . $key;
ok( 'K12 Authorization: Bearer accepted too', AGFO_AIM_Editor_API::can_use() === true );
unset( $_SERVER['HTTP_AUTHORIZATION'] );
$GLOBALS['T']['USER'] = 0;
$e = AGFO_AIM_Editor_API::can_use();
ok( 'K13 nothing sent -> agfo_editor_auth', is_wp_error( $e ) && $e->get_error_code() === 'agfo_editor_auth' );

$id = explode( '.', $key )[2];
ok( 'K14 revoke', $K::revoke( 5, $id ) && $K::verify( $key ) === 0 && ! $K::revoke( 5, $id ) );
for ( $i = 0; $i < 10; $i++ ) { $K::create( 9 ); }
ok( 'K15 max 10 keys per user', is_wp_error( $K::create( 9 ) ) );

$_SERVER['HTTP_X_AGFO_EDITOR_TOKEN'] = 'x';
$p = AGFO_AIM_Editor_API::rest_ping()->data;
ok( 'K16 ping: version + booleans only', $p['plugin_version'] === '17.5.0' && $p['token_auth'] === true && $p['received']['token'] === true
    && $p['received']['authorization'] === false && $p['app_passwords'] === false && count( $p ) === 7 );

$key2 = $K::create( 5, 'det' );
$_SERVER['HTTP_X_AGFO_EDITOR_TOKEN'] = $key2;
$_SERVER['REQUEST_URI'] = '/wp-json/agfo-ai/v1/editor/info';
$K::register_hooks();
ok( 'K17 determine_current_user resolves key on editor routes', $K::determine_user( false ) === 5 && $K::determine_user( 2 ) === 2 );
$_SERVER['REQUEST_URI'] = '/wp-json/wp/v2/users/me';
ok( 'K18 key ignored on other routes', $K::determine_user( false ) === false );
ok( 'K19 filter registered', isset( $GLOBALS['T']['F']['determine_current_user'] ) );
echo "\n$pass pass, $fail fail\n";
exit( $fail > 0 ? 1 : 0 );
