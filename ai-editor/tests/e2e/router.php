<?php
/**
 * Minimal WordPress REST stand-in for the editor <-> AI Manager end-to-end test (php -S).
 * Loads the REAL AI Manager editor API + connection key classes; WordPress functions are stubbed.
 * One user (id 5, "agfoai") with app password "abcd efgh ijkl mnop qrst uvwx" and manage_options.
 */
define( 'ABSPATH', sys_get_temp_dir() . '/' );
define( 'AGFO_AIM_VERSION', 'e2e' );
$root = getenv( 'AIM_ROOT' );
$state_file = getenv( 'E2E_STATE' ) ?: ( sys_get_temp_dir() . '/agfo-e2e-meta.json' );
$GLOBALS['META'] = is_file( $state_file ) ? json_decode( file_get_contents( $state_file ), true ) : [];
$GLOBALS['F'] = []; $GLOBALS['A'] = []; $GLOBALS['ROUTES'] = []; $GLOBALS['UID'] = 0;
function add_action( $h, $cb, $p = 10, $a = 1 ) { $GLOBALS['A'][ $h ][] = $cb; return true; }
function add_filter( $h, $cb, $p = 10, $a = 1 ) { $GLOBALS['F'][ $h ][ $p ][] = $cb; return true; }
function apply_filters( $h, $v, ...$a ) { $l = $GLOBALS['F'][ $h ] ?? []; ksort( $l ); foreach ( $l as $cbs ) { foreach ( $cbs as $cb ) { $v = $cb( $v, ...$a ); } } return $v; }
function get_user_meta( $u, $k, $s = false ) { return $GLOBALS['META'][ $u ][ $k ] ?? ''; }
function update_user_meta( $u, $k, $v ) { global $state_file; $GLOBALS['META'][ $u ][ $k ] = $v; file_put_contents( $state_file, json_encode( $GLOBALS['META'] ) ); return true; }
function get_option( $k, $d = false ) { return $d; }
function update_option( $k, $v, $a = null ) { return true; }
function delete_option( $k ) { return true; }
function wp_salt( $s = 'auth' ) { return 'e2e-salt'; }
function sanitize_text_field( $s ) { return trim( strip_tags( (string) $s ) ); }
function sanitize_textarea_field( $s ) { return trim( strip_tags( (string) $s ) ); }
function sanitize_key( $k ) { return preg_replace( '/[^a-z0-9_\-]/', '', strtolower( (string) $k ) ); }
function wp_unslash( $s ) { return $s; }
function absint( $n ) { return abs( (int) $n ); }
function wp_strip_all_tags( $s ) { return trim( strip_tags( (string) $s ) ); }
function wp_kses_post( $s ) { return (string) $s; }
function esc_html( $s ) { return htmlspecialchars( (string) $s, ENT_QUOTES, 'UTF-8' ); }
function get_userdata( $id ) { return (int) $id === 5 ? (object) [ 'ID' => 5, 'user_login' => 'agfoai' ] : false; }
function wp_set_current_user( $id ) { $GLOBALS['UID'] = (int) $id; }
function is_user_logged_in() { return $GLOBALS['UID'] > 0; }
function current_user_can( $c ) { return $GLOBALS['UID'] === 5; }
function wp_get_current_user() { return (object) [ 'display_name' => 'AGFO AI', 'user_login' => 'agfoai' ]; }
function is_ssl() { return false; }
function wp_is_application_passwords_available() { return true; }
function register_rest_route( $ns, $r, $args ) { $GLOBALS['ROUTES'][ '/' . $ns . $r ] = $args; }
function agfo_get_priority_api_key( $f = false, $model = '', $provider = '' ) {
    if ( $provider !== '' ) {   // AI Manager 17.8: is basina secilen ceviri modeli
        return [ 'code' => $provider, 'provider_name' => ucfirst( $provider ), 'model' => $model, 'key' => 'k-x', 'chat_url' => 'x' ];
    }
    return [ 'code' => 'openai', 'provider_name' => 'OpenAI', 'model' => 'gpt-e2e', 'key' => 'sk-x', 'chat_url' => 'x' ];
}
function agfo_api_registry() { return [ 'openai' => [ 'type' => 'llm' ], 'groq' => [ 'type' => 'llm' ] ]; }
function agfo_get_api_key( $c ) { return in_array( $c, [ 'openai', 'groq' ], true ) ? 'k' : ''; }
function agfo_get_translation_config() {
    // E2E_ROUTE=dead: AI Kontrol Merkezi'nde Ceviri rotasi Together'da sunulmayan bir modele ayarli (gercek hata)
    return getenv( 'E2E_ROUTE' ) === 'dead'
        ? [ 'code' => 'together', 'provider_name' => 'Together AI', 'model' => 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B', 'key' => 'tg-x', 'chat_url' => 'x' ]
        : false;
}
function wp_authenticate_application_password( $in, $login, $pw ) {
    if ( $login !== 'agfoai' ) return new WP_Error( 'invalid_username', 'Unknown username.' );
    if ( preg_replace( '/\s+/', '', $pw ) !== 'abcdefghijklmnopqrstuvwx' ) return new WP_Error( 'incorrect_password', 'The provided password is an invalid application password.' );
    return (object) [ 'ID' => 5 ];
}
class WP_Error { public $c; public $m; public $d; function __construct( $c = '', $m = '', $d = null ) { $this->c = $c; $this->m = $m; $this->d = $d; } function get_error_message() { return $this->m; } function get_error_code() { return $this->c; } function get_error_data() { return $this->d; } }
function is_wp_error( $x ) { return $x instanceof WP_Error; }
class WP_REST_Response { public $data; public $status; function __construct( $d, $s = 200 ) { $this->data = $d; $this->status = $s; } }
class E2E_Request { private $p; function __construct( $p ) { $this->p = $p; } function get_param( $k ) { return $this->p[ $k ] ?? null; } function get_json_params() { return $this->p; } }
// AI transport stand-in: echoes the source upper-cased (proves the real transform path ran).
function agfo_api_post( $url, $headers, $body, $args = [] ) {
    if ( ( $args['model'] ?? '' ) === 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B' ) {
        return [ 'http_code' => 400, 'body' => json_encode( [ 'error' => [ 'message' => 'Unable to access non-serverless model deepseek-ai/DeepSeek-R1-Distill-Qwen-7B. Please visit https://api.together.ai/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B to create and start a new dedicated endpoint for the model.' ] ] ) ];
    }
    $b = json_decode( $body, true );
    $sys = $b['messages'][0]['content'] ?? '';
    $u = $b['messages'][1]['content'] ?? '';
    preg_match_all( '#<agfo_source>\n(.*?)\n</agfo_source>#s', $u, $m );
    if ( strpos( $sys, 'OUTPUT FORMAT OVERRIDE' ) !== false && ! empty( $m[1] ) ) {     // Markdown kipi: Markdown don
        $md = mb_strtoupper( end( $m[1] ) );
        return [ 'http_code' => 200, 'body' => json_encode( [ 'choices' => [ [ 'message' => [ 'content' => "<think>plan</think>\n" . $md ], 'finish_reason' => 'stop' ] ] ] ) ];
    }
    $txt = ! empty( $m[1] ) ? mb_strtoupper( strip_tags( end( $m[1] ) ) ) : 'CHAT-OK';
    return [ 'http_code' => 200, 'body' => json_encode( [ 'choices' => [ [ 'message' => [ 'content' => '<p>' . $txt . '</p>' ], 'finish_reason' => 'stop' ] ] ] ) ];
}
function wp_json_encode( $d, $o = 0 ) { return json_encode( $d, $o ); }
function wp_kses( $s, $a = [] ) { return (string) $s; }

require $root . '/includes/content/class-content-prompt-library.php';
require $root . '/includes/content/class-content-transformer.php';
require $root . '/includes/api/class-editor-api.php';
require $root . '/includes/api/class-editor-tokens.php';
AGFO_AIM_Editor_API::register_hooks();
AGFO_AIM_Editor_Tokens::register_hooks();
foreach ( $GLOBALS['A']['rest_api_init'] as $cb ) { $cb(); }

$path = parse_url( $_SERVER['REQUEST_URI'], PHP_URL_PATH );
if ( $path === '/__mkkey' ) { header( 'Content-Type: text/plain' ); echo AGFO_AIM_Editor_Tokens::create( 5, 'e2e' ); exit; }
// WordPress core: Basic auth -> application password (only when the header reaches PHP)
$uid = false;
if ( ! empty( $_SERVER['PHP_AUTH_USER'] ) && getenv( 'STRIP_AUTH' ) !== '1' ) {
    $r = wp_authenticate_application_password( null, $_SERVER['PHP_AUTH_USER'], $_SERVER['PHP_AUTH_PW'] ?? '' );
    if ( is_wp_error( $r ) ) { http_response_code( 401 ); header( 'Content-Type: application/json' ); echo json_encode( [ 'code' => $r->get_error_code(), 'message' => $r->get_error_message(), 'data' => [ 'status' => 401 ] ] ); exit; }
    $uid = $r->ID;
}
if ( getenv( 'STRIP_AUTH' ) === '1' ) { unset( $_SERVER['HTTP_AUTHORIZATION'], $_SERVER['PHP_AUTH_USER'], $_SERVER['PHP_AUTH_PW'] ); }
$uid = apply_filters( 'determine_current_user', $uid );
if ( $uid ) { wp_set_current_user( $uid ); }
$route = substr( $path, strlen( '/wp-json' ) );
header( 'Content-Type: application/json' );
if ( strpos( $path, '/wp-json/' ) !== 0 || ! isset( $GLOBALS['ROUTES'][ $route ] ) ) { http_response_code( 404 ); echo json_encode( [ 'code' => 'rest_no_route', 'message' => 'No route', 'data' => [ 'status' => 404 ] ] ); exit; }
$def = $GLOBALS['ROUTES'][ $route ];
$perm = is_callable( $def['permission_callback'] ) ? call_user_func( $def['permission_callback'] ) : true;
if ( is_wp_error( $perm ) ) { http_response_code( $perm->get_error_data()['status'] ?? 401 ); echo json_encode( [ 'code' => $perm->get_error_code(), 'message' => $perm->get_error_message(), 'data' => $perm->get_error_data() ] ); exit; }
$params = json_decode( file_get_contents( 'php://input' ), true ) ?: [];
$res = call_user_func( $def['callback'], new E2E_Request( $params ) );
if ( is_wp_error( $res ) ) { http_response_code( $res->get_error_data()['status'] ?? 400 ); echo json_encode( [ 'code' => $res->get_error_code(), 'message' => $res->get_error_message() ] ); exit; }
http_response_code( $res->status ?? 200 );
echo json_encode( $res instanceof WP_REST_Response ? $res->data : $res );
