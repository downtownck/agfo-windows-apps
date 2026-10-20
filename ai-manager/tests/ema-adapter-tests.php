<?php
/**
 * AGFO AI Manager 17.9.0 — EMA Lightning adapter regression tests.
 * Run from the plugin root: php tests/ema-adapter-tests.php
 * Isolated: minimal WordPress stubs and a fake HTTP layer; no network, no WordPress.
 */
if ( PHP_SAPI !== 'cli' ) { exit; }
$root = dirname( __DIR__ );
if ( ! defined( 'ABSPATH' ) ) define( 'ABSPATH', sys_get_temp_dir() . '/' );
define( 'AGFO_AIM_PLUGIN_DIR', $root . '/' );

$GLOBALS['O'] = []; $GLOBALS['HTTP'] = []; $GLOBALS['NEXT'] = null; $GLOBALS['AGFO_ENC'] = null;
function get_option( $k, $d = false ) { return array_key_exists( $k, $GLOBALS['O'] ) ? $GLOBALS['O'][ $k ] : $d; }
function update_option( $k, $v, $a = null ) { $GLOBALS['O'][ $k ] = $v; return true; }
function sanitize_key( $k ) { return preg_replace( '/[^a-z0-9_\-]/', '', strtolower( (string) $k ) ); }
function sanitize_text_field( $s ) { return trim( strip_tags( (string) $s ) ); }
function wp_strip_all_tags( $s ) { return strip_tags( (string) $s ); }
function esc_url_raw( $u ) { return (string) $u; }
function untrailingslashit( $s ) { return rtrim( (string) $s, '/\\' ); }
function absint( $n ) { return abs( (int) $n ); }
function wp_json_encode( $d, $o = 0 ) { return json_encode( $d, $o ); }
function current_time( $t ) { return date( 'Y-m-d H:i:s' ); }
function agfo_redact_secrets( $s ) { return (string) $s; }
function wp_tempnam( $f = '' ) { return tempnam( sys_get_temp_dir(), 'ema' ); }
class WP_Error { public $c; public $m; function __construct( $c = '', $m = '' ) { $this->c = $c; $this->m = $m; } function get_error_message() { return $this->m; } function get_error_code() { return $this->c; } }
function is_wp_error( $x ) { return $x instanceof WP_Error; }
function wp_remote_post( $url, $args ) {
    $GLOBALS['HTTP'][] = [ 'url' => $url, 'args' => $args ];
    $r = $GLOBALS['NEXT'];
    if ( is_array( $r ) && ! empty( $args['filename'] ) ) { file_put_contents( $args['filename'], $r['body'] ); }
    return $r;
}
function wp_remote_get( $url, $args ) { $GLOBALS['HTTP'][] = [ 'url' => $url, 'args' => $args ]; return $GLOBALS['NEXT']; }
function wp_remote_retrieve_response_code( $r ) { return is_array( $r ) ? $r['code'] : 0; }
function wp_remote_retrieve_body( $r ) { return is_array( $r ) ? $r['body'] : ''; }
function wp_remote_retrieve_header( $r, $h ) { return is_array( $r ) ? ( $r['headers'][ strtolower( $h ) ] ?? '' ) : ''; }

// Registry entry + key lookup come from the real functions.php; load only what we need.
$functions = file_get_contents( $root . '/includes/functions.php' );
preg_match( '/function agfo_api_registry\(\)[^{]*\{.*?\n\}\n/s', $functions, $m1 );
preg_match( '/function agfo_get_api_key\(string \$code\)[^{]*\{.*?\n\}\n/s', $functions, $m2 );
eval( $m1[0] . $m2[0] ); // phpcs:ignore Squiz.PHP.Eval.Discouraged

require $root . '/includes/adapters/interface-adapter.php';
require $root . '/includes/adapters/class-adapter-ema.php';

$pass = 0; $fail = 0;
function t( $name, $cond ) { global $pass, $fail; if ( $cond ) { $pass++; echo "PASS $name\n"; } else { $fail++; echo "FAIL $name\n"; } }

$tr = "Merhaba. Bu bir deneme metnidir; ağaçların gölgesinde öğle güneşi ışıldıyor. Çiçekler ve böcekler şarkı söylüyor. "
    . "Denetim raporu hazırlanırken gıda güvenliği yönetim sisteminin tüm adımları incelenir ve bulgular yazılır.";
$en = str_repeat( 'The quick brown fox jumps over the lazy dog while auditors review the food safety system. ', 4 );
$a  = new AGFO_AIM_Adapter_EMA();

// Registry
$reg = agfo_api_registry();
t( 'E01 registry has ema', isset( $reg['ema'] ) );
t( 'E02 ema is media, speech only', ( $reg['ema']['type'] ?? '' ) === 'media' && ( $reg['ema']['capabilities'] ?? [] ) === [ 'speech_synthesize' ] );
t( 'E03 ema default model', ( $reg['ema']['default_models']['speech_synthesize'] ?? '' ) === 'ema-lightning' );
t( 'E04 existing providers kept', isset( $reg['openai'], $reg['elevenlabs'], $reg['minimax'] ) );

// Adapter contract
t( 'E05 provider code', 'ema' === $a->provider_code() );
t( 'E06 supports speech only', $a->supports( 'speech_synthesize' ) && ! $a->supports( 'chat' ) && ! $a->supports( 'music_generate' ) );
t( 'E07 turkish text valid', true === $a->validate_payload( 'speech_synthesize', [ 'text' => $tr ] ) );
$e = $a->validate_payload( 'speech_synthesize', [ 'text' => $en ] );
t( 'E08 english text refused with non-failover code', is_wp_error( $e ) && 'agfo_ema_language' === $e->get_error_code() && ! preg_match( '/_(429|500|502|503|504)$/', $e->get_error_code() ) );
t( 'E09 explicit tr language accepted for any text', true === $a->validate_payload( 'speech_synthesize', [ 'text' => $en, 'language' => 'tr' ] ) );
t( 'E10 explicit en language refused', is_wp_error( $a->validate_payload( 'speech_synthesize', [ 'text' => $tr, 'language' => 'en' ] ) ) );
t( 'E11 minimax language boost English refused', is_wp_error( $a->validate_payload( 'speech_synthesize', [ 'text' => $tr, 'language_boost' => 'English' ] ) ) );
t( 'E12 language boost auto ok', true === $a->validate_payload( 'speech_synthesize', [ 'text' => $tr, 'language_boost' => 'auto' ] ) );
t( 'E13 short text benefit of doubt', true === $a->validate_payload( 'speech_synthesize', [ 'text' => 'BRCGS IFS' ] ) );
t( 'E14 empty text refused', is_wp_error( $a->validate_payload( 'speech_synthesize', [ 'text' => '  ' ] ) ) );
t( 'E15 opus refused', is_wp_error( $a->validate_payload( 'speech_synthesize', [ 'text' => $tr, 'format' => 'opus' ] ) ) );
t( 'E16 speed 2 refused, 1.4 ok', is_wp_error( $a->validate_payload( 'speech_synthesize', [ 'text' => $tr, 'speed' => 2 ] ) ) && true === $a->validate_payload( 'speech_synthesize', [ 'text' => $tr, 'speed' => 1.4 ] ) );
t( 'E17 too long refused', is_wp_error( $a->validate_payload( 'speech_synthesize', [ 'text' => str_repeat( 'ı', 60001 ) ] ) ) );
t( 'E18 cost is zero', 0.0 === $a->estimate_cost( 'speech_synthesize', [ 'text' => $tr ] )['cost'] );

// Token resolution
t( 'E19 no token -> empty', '' === AGFO_AIM_Adapter_EMA::token() );
update_option( 'agfo_ema_api_key', 'stored-token' );
t( 'E20 provider key used', 'stored-token' === AGFO_AIM_Adapter_EMA::token() );

// Dispatch: request shape + lexicon + pauses
update_option( 'agfo_ai_ema_lexicon', "BRCGS = Bi Ar Si Ci Es\nbozuk\n = boş\nIFS = Ay Ef Es" );
update_option( 'agfo_ai_ema_pauses', [ 'sentence' => 400, 'paragraph' => 900 ] );
update_option( 'agfo_ai_ema_endpoint', 'http://10.0.0.5:9000/' );
$GLOBALS['HTTP'] = [];
$GLOBALS['NEXT'] = [ 'code' => 200, 'body' => 'ID3fakeaudio', 'headers' => [ 'x-agfo-seconds' => '12.5', 'x-agfo-cached' => '1' ] ];
$r    = $a->dispatch( 'speech_synthesize', [ 'text' => $tr, 'speed' => 1.1 ] );
$call = $GLOBALS['HTTP'][0] ?? [];
$body = json_decode( (string) ( $call['args']['body'] ?? '' ), true );
t( 'E21 posts to saved endpoint /tts', 'http://10.0.0.5:9000/tts' === ( $call['url'] ?? '' ) );
t( 'E22 token header', 'stored-token' === ( $call['args']['headers']['X-AGFO-Token'] ?? '' ) );
t( 'E23 lexicon parsed (2 valid)', [ 'BRCGS' => 'Bi Ar Si Ci Es', 'IFS' => 'Ay Ef Es' ] === ( $body['lexicon'] ?? null ) );
t( 'E24 saved pause defaults applied', 400 === ( $body['pause_ms'] ?? 0 ) && 900 === ( $body['paragraph_pause_ms'] ?? 0 ) );
t( 'E25 result shape', is_array( $r ) && 'audio/mpeg' === $r['mime'] && 12 === $r['bytes'] && 0.0 === $r['cost_actual'] && 12500 === $r['metadata']['duration_ms'] && true === $r['metadata']['cached'] );
@unlink( $r['temp_file'] ?? '' );
$GLOBALS['HTTP'] = [];
$a->dispatch( 'speech_synthesize', [ 'text' => $tr, 'pause_ms' => 100, 'paragraph_pause_ms' => 5000 ] );
$body = json_decode( (string) ( $GLOBALS['HTTP'][0]['args']['body'] ?? '' ), true );
t( 'E26 job pauses clamp', 100 === $body['pause_ms'] && 3000 === $body['paragraph_pause_ms'] );

// Error mapping keeps the worker's failover/retry contract.
$GLOBALS['NEXT'] = [ 'code' => 503, 'body' => '{"detail":"busy"}', 'headers' => [] ];
$r = $a->dispatch( 'speech_synthesize', [ 'text' => $tr ] );
t( 'E27 503 -> failover-able code', is_wp_error( $r ) && 'agfo_ema_tts_503' === $r->get_error_code() && false !== strpos( $r->get_error_message(), 'busy' ) );
$GLOBALS['NEXT'] = new WP_Error( 'http_request_failed', 'Connection refused' );
$r = $a->dispatch( 'speech_synthesize', [ 'text' => $tr ] );
t( 'E28 unreachable -> http error', is_wp_error( $r ) && 'agfo_ema_tts_http' === $r->get_error_code() );

// Catalog: no network unless probed.
$GLOBALS['HTTP'] = [];
$c = AGFO_AIM_Adapter_EMA::catalog( false );
t( 'E29 catalog without probe makes no request', [] === $GLOBALS['HTTP'] && null === $c['healthy'] && 60000 === $c['models'][0]['max_characters'] );
$GLOBALS['NEXT'] = [ 'code' => 200, 'body' => '{"ok":true,"lexicon_entries":26}', 'headers' => [] ];
$c = AGFO_AIM_Adapter_EMA::catalog( true );
t( 'E30 probed catalog healthy', true === $c['healthy'] && false !== strpos( $c['notice'], '26' ) );
$GLOBALS['NEXT'] = [ 'code' => 401, 'body' => '{}', 'headers' => [] ];
$c = AGFO_AIM_Adapter_EMA::catalog( true );
t( 'E31 bad token reported', false === $c['healthy'] && false !== strpos( $c['notice'], 'reddetti' ) );

// wp-config constant wins.
define( 'AGFO_TTS_TOKEN', 'const-token' );
t( 'E32 AGFO_TTS_TOKEN wins', 'const-token' === AGFO_AIM_Adapter_EMA::token() );
unset( $GLOBALS['O']['agfo_ema_api_key'] );
t( 'E33 agfo_get_api_key(ema) falls back to constant', 'const-token' === agfo_get_api_key( 'ema' ) && null === agfo_get_api_key( 'openai' ) );

echo "\n$pass pass / $fail fail\n";
exit( $fail ? 1 : 0 );
