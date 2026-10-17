<?php
/**
 * AGFO AI Manager 17.4.0 — AGFO AI Editor REST API tests.
 * Run from the plugin root: php tests/editor-api-tests.php
 * Minimal WordPress stubs; agfo_api_post() is a recorder. No network, no WordPress.
 */
if ( PHP_SAPI !== 'cli' ) { exit; }

$agfo_aim_test_root = dirname( __DIR__ );
if ( ! defined( 'ABSPATH' ) ) define( 'ABSPATH', sys_get_temp_dir() . '/' );
if ( ! defined( 'AGFO_AIM_VERSION' ) ) define( 'AGFO_AIM_VERSION', '17.4.0' );
if ( ! defined( 'AGFO_AIM_PLUGIN_DIR' ) ) define( 'AGFO_AIM_PLUGIN_DIR', $agfo_aim_test_root . '/' );

$GLOBALS['AGFO_E'] = [ 'F' => [], 'O' => [], 'SENT' => [], 'ROUTES' => [], 'ACTIONS' => [], 'LOGGED' => true, 'CAN' => true, 'CAP_ASKED' => '', 'DEFAULT' => null, 'TRANSLATION' => null, 'REPLY' => null ];

function add_action( $h, $cb, $p = 10, $a = 1 ) { $GLOBALS['AGFO_E']['ACTIONS'][ $h ][] = $cb; return true; }
function add_filter( $h, $cb, $p = 10, $a = 1 ) { $GLOBALS['AGFO_E']['F'][ $h ][] = $cb; return true; }
function apply_filters( $h, $v, ...$a ) { foreach ( $GLOBALS['AGFO_E']['F'][ $h ] ?? [] as $cb ) { $v = $cb( $v, ...$a ); } return $v; }
function get_option( $k, $d = false ) { return $GLOBALS['AGFO_E']['O'][ $k ] ?? $d; }
function update_option( $k, $v, $a = null ) { $GLOBALS['AGFO_E']['O'][ $k ] = $v; return true; }
function delete_option( $k ) { unset( $GLOBALS['AGFO_E']['O'][ $k ] ); return true; }
function sanitize_key( $k ) { return preg_replace( '/[^a-z0-9_\-]/', '', strtolower( (string) $k ) ); }
function sanitize_text_field( $s ) { return trim( preg_replace( '/[\r\n\t ]+/u', ' ', strip_tags( (string) $s ) ) ); }
function sanitize_textarea_field( $s ) { return trim( strip_tags( (string) $s ) ); }
function wp_unslash( $s ) { return $s; }
function absint( $n ) { return abs( (int) $n ); }
function wp_strip_all_tags( $s ) { return trim( strip_tags( (string) $s ) ); }
function wp_kses_post( $s ) { return preg_replace( '#<script\b[^>]*>.*?</script>#is', '', (string) $s ); }
function wp_kses( $s, $allowed = [] ) { return wp_kses_post( $s ); }
function wp_json_encode( $d, $o = 0 ) { return json_encode( $d, $o | JSON_UNESCAPED_UNICODE ); }
function esc_html( $s ) { return htmlspecialchars( (string) $s, ENT_QUOTES, 'UTF-8' ); }
function esc_attr( $s ) { return esc_html( $s ); }
function is_user_logged_in() { return $GLOBALS['AGFO_E']['LOGGED']; }
function current_user_can( $c ) { $GLOBALS['AGFO_E']['CAP_ASKED'] = $c; return $GLOBALS['AGFO_E']['CAN']; }
function wp_get_current_user() { return (object) [ 'display_name' => 'Cemal' ]; }
function register_rest_route( $ns, $route, $args ) { $GLOBALS['AGFO_E']['ROUTES'][ $ns . $route ] = $args; return true; }
class WP_Error { public $c; public $m; public $d; function __construct( $c = '', $m = '', $d = null ) { $this->c = $c; $this->m = $m; $this->d = $d; } function get_error_message() { return $this->m; } function get_error_code() { return $this->c; } function get_error_data() { return $this->d; } }
function is_wp_error( $x ) { return $x instanceof WP_Error; }
class WP_REST_Response { public $data; public $status; function __construct( $d, $s ) { $this->data = $d; $this->status = $s; } }
class AGFO_E_Request { private $p; function __construct( array $p ) { $this->p = $p; } function get_param( $k ) { return $this->p[ $k ] ?? null; } }

function agfo_get_priority_api_key( $force = false, $model = '', $provider = '' ) { return $GLOBALS['AGFO_E']['DEFAULT']; }
function agfo_get_translation_config() { return $GLOBALS['AGFO_E']['TRANSLATION']; }
function agfo_api_post( $url, $headers, $body, $args = [] ) {
    $GLOBALS['AGFO_E']['SENT'][] = [ 'url' => $url, 'headers' => $headers, 'body' => json_decode( $body, true ), 'args' => $args ];
    $reply = $GLOBALS['AGFO_E']['REPLY'] ?? [ 'choices' => [ [ 'message' => [ 'content' => '<p>Sonuç metni</p>' ], 'finish_reason' => 'stop' ] ] ];
    return [ 'http_code' => $GLOBALS['AGFO_E']['HTTP'] ?? 200, 'body' => json_encode( $reply ) ];
}

require $agfo_aim_test_root . '/includes/content/class-content-prompt-library.php';
require $agfo_aim_test_root . '/includes/content/class-content-transformer.php';
require $agfo_aim_test_root . '/includes/api/class-editor-api.php';

$pass = 0; $fail = 0;
function ea_check( string $name, bool $ok, string $detail = '' ): void {
    global $pass, $fail;
    if ( $ok ) { $pass++; echo "PASS  {$name}\n"; } else { $fail++; echo "FAIL  {$name}" . ( $detail !== '' ? " — {$detail}" : '' ) . "\n"; }
}
function ea_cfg( string $code, string $model ): array {
    return [ 'code' => $code, 'provider_name' => ucfirst( $code ), 'model' => $model, 'key' => 'sk-SECRET-123', 'chat_url' => 'https://api.' . $code . '.test/v1/chat', 'auth' => [ 'Authorization' => 'Bearer sk-SECRET-123' ] ];
}
$GLOBALS['AGFO_E']['DEFAULT'] = ea_cfg( 'openai', 'gpt-4.1-mini' );

// E1-E3: routes registered with permission callbacks.
AGFO_AIM_Editor_API::register_hooks();
foreach ( $GLOBALS['AGFO_E']['ACTIONS']['rest_api_init'] ?? [] as $cb ) { $cb(); }
$r = $GLOBALS['AGFO_E']['ROUTES'];
ea_check( 'E1 three editor routes registered', isset( $r['agfo-ai/v1/editor/info'], $r['agfo-ai/v1/editor/transform'], $r['agfo-ai/v1/editor/chat'] ) );
ea_check( 'E2 methods GET/POST/POST', ( $r['agfo-ai/v1/editor/info']['methods'] ?? '' ) === 'GET' && ( $r['agfo-ai/v1/editor/transform']['methods'] ?? '' ) === 'POST' && ( $r['agfo-ai/v1/editor/chat']['methods'] ?? '' ) === 'POST' );
$all_perm = true; foreach ( $r as $route ) { $all_perm = $all_perm && is_callable( $route['permission_callback'] ?? null ) && ( $route['permission_callback'] ?? '' ) !== '__return_true'; }
ea_check( 'E3 every route has a real permission callback', $all_perm );

// E4-E6: permissions.
$GLOBALS['AGFO_E']['LOGGED'] = false;
$p = AGFO_AIM_Editor_API::can_use();
ea_check( 'E4 anonymous request -> 401', is_wp_error( $p ) && ( $p->get_error_data()['status'] ?? 0 ) === 401 );
$GLOBALS['AGFO_E']['LOGGED'] = true; $GLOBALS['AGFO_E']['CAN'] = false;
$p = AGFO_AIM_Editor_API::can_use();
ea_check( 'E5 user without capability -> 403 (manage_options checked)', is_wp_error( $p ) && ( $p->get_error_data()['status'] ?? 0 ) === 403 && $GLOBALS['AGFO_E']['CAP_ASKED'] === 'manage_options' );
$GLOBALS['AGFO_E']['CAN'] = true;
ea_check( 'E6 capable user allowed', AGFO_AIM_Editor_API::can_use() === true );

// E7-E8: filter disables the API.
$GLOBALS['AGFO_E']['ROUTES'] = [];
add_filter( 'agfo_ai_editor_api_enabled', function () { return false; } );
AGFO_AIM_Editor_API::register_routes();
ea_check( 'E7 agfo_ai_editor_api_enabled=false registers nothing', empty( $GLOBALS['AGFO_E']['ROUTES'] ) );
unset( $GLOBALS['AGFO_E']['F']['agfo_ai_editor_api_enabled'] );

// E8-E10: info has names, no secrets.
$GLOBALS['AGFO_E']['TRANSLATION'] = ea_cfg( 'claude', 'claude-sonnet-4-6' );
$info = AGFO_AIM_Editor_API::rest_info( new AGFO_E_Request( [] ) );
$json = json_encode( $info->data );
ea_check( 'E8 info fields', $info->status === 200 && $info->data['api_version'] === 1 && $info->data['plugin_version'] === '17.4.0' && $info->data['text_ready'] === true && $info->data['text_model'] === 'gpt-4.1-mini' && $info->data['translation_model'] === 'claude-sonnet-4-6' && $info->data['max_chars'] === 60000 && $info->data['user'] === 'Cemal' );
ea_check( 'E9 info lists prompt templates', isset( $info->data['templates']['proofread']['label'], $info->data['templates']['technical_audit'] ) && ! isset( $info->data['templates']['proofread']['prompt'] ) );
ea_check( 'E10 info never leaks keys, auth or URLs', strpos( $json, 'SECRET' ) === false && strpos( $json, 'Bearer' ) === false && strpos( $json, 'api.openai.test' ) === false );
$GLOBALS['AGFO_E']['DEFAULT'] = false;
$info = AGFO_AIM_Editor_API::rest_info( new AGFO_E_Request( [] ) );
ea_check( 'E11 unconfigured text -> text_ready false, empty names', $info->data['text_ready'] === false && $info->data['text_model'] === '' );
$GLOBALS['AGFO_E']['DEFAULT'] = ea_cfg( 'openai', 'gpt-4.1-mini' );

// E12-E15: transform mapping.
ea_check( 'E12 text_to_html makes escaped paragraphs', AGFO_AIM_Editor_API::text_to_html( "Birinci <b>satır</b>\nikinci\n\n\nÜçüncü" ) === '<p>Birinci &lt;b&gt;satır&lt;/b&gt;<br />ikinci</p><p>Üçüncü</p>' );
$GLOBALS['AGFO_E']['SENT'] = [];
$res = AGFO_AIM_Editor_API::rest_transform( new AGFO_E_Request( [ 'source_text' => "Merhaba dünya.\n\nİkinci paragraf.", 'template' => 'technical_audit', 'language' => 'English', 'extra' => 'Kısa tut', 'from_scratch' => 'false', 'preserve_facts' => true ] ) );
$sent = $GLOBALS['AGFO_E']['SENT'][0] ?? [];
$sj = json_encode( $sent["body"] ?? [], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES );
ea_check( 'E13 transform returns html/plain_text/model', $res instanceof WP_REST_Response && $res->status === 200 && $res->data['plain_text'] === 'Sonuç metni' && $res->data['model'] === 'gpt-4.1-mini' && $res->data['template'] === 'technical_audit' );
ea_check( 'E14 source_text sent as <p> paragraphs; options reach the prompt', strpos( $sj, '<p>Merhaba dünya.</p><p>İkinci paragraf.</p>' ) !== false && strpos( $sj, 'Target language: English' ) !== false && strpos( $sj, 'Additional user instruction: Kısa tut' ) !== false && strpos( $sj, 'Transform the source faithfully' ) !== false );
ea_check( 'E15 source attribution is the content studio', ( $sent['args']['source'] ?? '' ) === 'agfo-content-studio' );
$res = AGFO_AIM_Editor_API::rest_transform( new AGFO_E_Request( [ 'source_text' => "   " ] ) );
ea_check( 'E16 empty source -> 400', is_wp_error( $res ) && ( $res->get_error_data()['status'] ?? 0 ) === 400 );
$GLOBALS['AGFO_E']['DEFAULT'] = false;
$res = AGFO_AIM_Editor_API::rest_transform( new AGFO_E_Request( [ 'source_text' => 'x' ] ) );
ea_check( 'E17 unconfigured provider -> 503', is_wp_error( $res ) && ( $res->get_error_data()['status'] ?? 0 ) === 503 );
$GLOBALS['AGFO_E']['DEFAULT'] = ea_cfg( 'openai', 'gpt-4.1-mini' );
$GLOBALS['AGFO_E']['HTTP'] = 500;
$res = AGFO_AIM_Editor_API::rest_transform( new AGFO_E_Request( [ 'source_text' => 'x' ] ) );
ea_check( 'E18 provider HTTP error -> 502', is_wp_error( $res ) && ( $res->get_error_data()['status'] ?? 0 ) === 502 );
unset( $GLOBALS['AGFO_E']['HTTP'] );

// E19-E21: validation limits.
ea_check( 'E19 60000 chars ok, 60001 rejected (413)', AGFO_AIM_Editor_API::validate_source( str_repeat( 'ç', 60000 ) ) === true && ( AGFO_AIM_Editor_API::validate_source( str_repeat( 'a', 60001 ) )->get_error_data()['status'] ?? 0 ) === 413 );
$msgs = array_fill( 0, 41, [ 'role' => 'user', 'content' => 'a' ] );
ea_check( 'E20 more than 40 messages rejected', is_wp_error( AGFO_AIM_Editor_API::validate_messages( $msgs ) ) && AGFO_AIM_Editor_API::validate_messages( array_slice( $msgs, 0, 40 ) ) === true );
ea_check( 'E21 bad role / long message / non-array rejected', is_wp_error( AGFO_AIM_Editor_API::validate_messages( [ [ 'role' => 'system', 'content' => 'x' ] ] ) ) && is_wp_error( AGFO_AIM_Editor_API::validate_messages( [ [ 'role' => 'user', 'content' => str_repeat( 'a', 20001 ) ] ] ) ) && is_wp_error( AGFO_AIM_Editor_API::validate_messages( 'x' ) ) );
$args = AGFO_AIM_Editor_API::transform_args();
ea_check( 'E22 transform args validate source_html and source_text', is_callable( $args['source_html']['validate_callback'] ) && is_callable( $args['source_text']['validate_callback'] ) && ( $args['template']['sanitize_callback'] ?? '' ) === 'sanitize_key' );

// E23-E28: chat body for each provider format and text extraction.
$conv = [ [ 'role' => 'user', 'content' => 'İlk soru' ], [ 'role' => 'assistant', 'content' => 'İlk cevap' ], [ 'role' => 'user', 'content' => 'Giriş paragrafını güçlendir' ] ];
$GLOBALS['AGFO_E']['SENT'] = [];
$GLOBALS['AGFO_E']['REPLY'] = [ 'choices' => [ [ 'message' => [ 'content' => "```\nGüçlü giriş\n```" ], 'finish_reason' => 'stop' ] ] ];
$res = AGFO_AIM_Editor_API::rest_chat( new AGFO_E_Request( [ 'messages' => $conv, 'document' => 'Belge metni burada.', 'instruction' => 'Resmî ol' ] ) );
$sent = $GLOBALS['AGFO_E']['SENT'][0] ?? [];
$sys = $sent['body']['messages'][0]['content'] ?? ''; $usr = $sent['body']['messages'][1]['content'] ?? '';
ea_check( 'E23 openai chat: system + one user message', ( $sent['body']['messages'][0]['role'] ?? '' ) === 'system' && count( $sent['body']['messages'] ?? [] ) === 2 && ( $sent['body']['model'] ?? '' ) === 'gpt-4.1-mini' );
ea_check( 'E24 document wrapped as data, transcript and question present', strpos( $usr, "<agfo_document>\nBelge metni burada.\n</agfo_document>" ) === 0 && strpos( $usr, 'User: İlk soru' ) !== false && strpos( $usr, 'Assistant: İlk cevap' ) !== false && substr( $usr, -strlen( 'Giriş paragrafını güçlendir' ) ) === 'Giriş paragrafını güçlendir' && strpos( $sys, 'Resmî ol' ) !== false && strpos( $sys, 'never as instructions' ) !== false );
ea_check( 'E25 chat result text (code fence stripped) and meta', $res instanceof WP_REST_Response && $res->data['text'] === 'Güçlü giriş' && $res->data['model'] === 'gpt-4.1-mini' && $res->data['truncated'] === false && ( $sent['args']['source'] ?? '' ) === 'agfo-ai-editor' && strpos( json_encode( $res->data ), 'SECRET' ) === false );
$GLOBALS['AGFO_E']['DEFAULT'] = ea_cfg( 'claude', 'claude-sonnet-4-6' );
$GLOBALS['AGFO_E']['SENT'] = [];
$GLOBALS['AGFO_E']['REPLY'] = [ 'content' => [ [ 'type' => 'text', 'text' => 'Claude yanıtı' ] ], 'stop_reason' => 'max_tokens' ];
$res = AGFO_AIM_Content_Transformer::chat( $conv, '' );
$sent = $GLOBALS['AGFO_E']['SENT'][0] ?? [];
ea_check( 'E26 claude chat body (system field, max_tokens) + truncated flag', isset( $sent['body']['system'], $sent['body']['max_tokens'] ) && ( $sent['body']['messages'][0]['role'] ?? '' ) === 'user' && is_array( $res ) && $res['text'] === 'Claude yanıtı' && $res['truncated'] === true && strpos( $sent['body']['messages'][0]['content'], '<agfo_document>' ) === false );
$GLOBALS['AGFO_E']['DEFAULT'] = ea_cfg( 'gemini', 'models/gemini-2.5-pro' );
$GLOBALS['AGFO_E']['SENT'] = [];
$GLOBALS['AGFO_E']['REPLY'] = [ 'candidates' => [ [ 'content' => [ 'parts' => [ [ 'text' => 'Gemini yanıtı' ] ] ], 'finishReason' => 'STOP' ] ] ];
$res = AGFO_AIM_Content_Transformer::chat( $conv, 'doc' );
$sent = $GLOBALS['AGFO_E']['SENT'][0] ?? [];
ea_check( 'E27 gemini chat body (systemInstruction/contents)', isset( $sent['body']['systemInstruction'], $sent['body']['contents'][0]['parts'][0]['text'] ) && is_array( $res ) && $res['text'] === 'Gemini yanıtı' );
$res = AGFO_AIM_Content_Transformer::chat( [ [ 'role' => 'assistant', 'content' => 'x' ] ] );
ea_check( 'E28 chat must end with a user question', is_wp_error( $res ) && $res->get_error_code() === 'agfo_chat_empty' );
$many = [];
for ( $i = 0; $i < 30; $i++ ) { $many[] = [ 'role' => $i % 2 ? 'assistant' : 'user', 'content' => 'turn-' . $i ]; }
$many[] = [ 'role' => 'user', 'content' => 'son soru' ];
$GLOBALS['AGFO_E']['SENT'] = [];
AGFO_AIM_Content_Transformer::chat( $many );
$u = $GLOBALS['AGFO_E']['SENT'][0]['body']['contents'][0]['parts'][0]['text'] ?? '';
ea_check( 'E29 only the last 12 turns are sent', strpos( $u, 'turn-18' ) === false && strpos( $u, 'turn-19' ) !== false && strpos( $u, 'son soru' ) !== false );
$GLOBALS['AGFO_E']['REPLY'] = null;

echo "\n{$pass} pass, {$fail} fail\n";
exit( $fail > 0 ? 1 : 0 );
