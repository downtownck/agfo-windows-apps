<?php
/**
 * AGFO AI Manager 17.15.0 — OpenRouter seslendirme adaptörü ve ses kataloğu testleri.
 * Run from the plugin root: php tests/openrouter-tts-tests.php
 * Minimal WordPress stubs; wp_remote_post / wp_remote_get sahte yanıt döndürür; ağ yok.
 */
if ( PHP_SAPI !== 'cli' ) { exit; }
$root = dirname( __DIR__ );
if ( ! defined( 'ABSPATH' ) ) define( 'ABSPATH', sys_get_temp_dir() . '/agfo-or-none/' );

$GLOBALS['KEYS'] = [ 'openrouter' => 'sk-or-test' ];
$GLOBALS['POSTS'] = [];
$GLOBALS['REPLIES'] = [];   // sırayla: [code, body, content-type]
$GLOBALS['GET'] = null;
$GLOBALS['TRANSIENT'] = [];
function sanitize_key( $k ) { return preg_replace( '/[^a-z0-9_\-]/', '', strtolower( (string) $k ) ); }
function sanitize_text_field( $s ) { return trim( preg_replace( '/[\r\n\t ]+/u', ' ', strip_tags( (string) $s ) ) ); }
function sanitize_textarea_field( $s ) { return trim( strip_tags( (string) $s ) ); }
function wp_strip_all_tags( $s ) { return strip_tags( (string) $s ); }
function wp_json_encode( $d ) { return json_encode( $d ); }
function agfo_get_api_key( $c ) { return $GLOBALS['KEYS'][ $c ] ?? null; }
function agfo_redact_secrets( $s ) { return $s; }
function get_option( $k, $d = false ) { return $d; }
function get_transient( $k ) { return $GLOBALS['TRANSIENT'][ $k ] ?? false; }
function set_transient( $k, $v, $t = 0 ) { $GLOBALS['TRANSIENT'][ $k ] = $v; return true; }
function home_url( $p = '' ) { return 'https://ornek.test/'; }
function current_time( $t ) { return '2026-11-08 20:00:00'; }
function wp_tempnam( $n = '' ) { return tempnam( sys_get_temp_dir(), 'agfo' ); }
class WP_Error { public $c; public $m; function __construct( $c = '', $m = '' ) { $this->c = $c; $this->m = $m; } function get_error_message() { return $this->m; } function get_error_code() { return $this->c; } }
function is_wp_error( $x ) { return $x instanceof WP_Error; }
function wp_remote_post( $url, $args ) {
    $GLOBALS['POSTS'][] = [ $url, json_decode( $args['body'], true ), $args['headers'] ];
    $r = array_shift( $GLOBALS['REPLIES'] ) ?: [ 500, '{"error":{"message":"no reply"}}', 'application/json' ];
    file_put_contents( $args['filename'], $r[1] );
    return [ 'code' => $r[0], 'ct' => $r[2] ];
}
function wp_remote_get( $url, $args ) { $GLOBALS['GETURL'] = $url; return $GLOBALS['GET']; }
function wp_remote_retrieve_response_code( $r ) { return $r['code']; }
function wp_remote_retrieve_header( $r, $h ) { return 'content-type' === $h ? $r['ct'] : ( 'x-generation-id' === $h ? 'gen-1' : '' ); }
function wp_remote_retrieve_body( $r ) { return $r['body'] ?? ''; }
interface AGFO_AIM_Adapter_Interface {}
require $root . '/includes/adapters/class-adapter-openrouter.php';
require $root . '/includes/tts/class-openrouter-tts-catalog.php';

$pass = 0; $fail = 0;
function t( $name, $cond ) { global $pass, $fail; if ( $cond ) { $pass++; echo "PASS $name\n"; } else { $fail++; echo "FAIL $name\n"; } }
$A = new AGFO_AIM_Adapter_OpenRouter();
$MP3 = "ID3\x03\x00\x00\x00\x00\x00\x00" . str_repeat( "\xFF\xFB\x90\x00" . str_repeat( "\x00", 413 ), 3 );

// Gövde
$b = AGFO_AIM_Adapter_OpenRouter::request_body( [ 'text' => 'Merhaba', 'voice' => '', 'speed' => 1.0 ], 'google/gemini-3.8-flash-tts', 'mp3', true );
t( 'O01 default voice Kore, no speed at 1.0', 'Kore' === $b['voice'] && ! isset( $b['speed'] ) && 'mp3' === $b['response_format'] && 'Merhaba' === $b['input'] );
$b = AGFO_AIM_Adapter_OpenRouter::request_body( [ 'text' => 'x', 'voice' => 'Puck', 'speed' => 1.2, 'instructions' => 'Sakin oku' ], 'm', 'mp3', true );
t( 'O02 speed and instructions sent', 1.2 === $b['speed'] && 'Sakin oku' === $b['instructions'] && 'Puck' === $b['voice'] );

// Doğrulama
t( 'O03 empty text rejected', is_wp_error( $A->validate_payload( 'speech_synthesize', [ 'text' => ' ' ] ) ) );
t( 'O04 too long rejected', is_wp_error( $A->validate_payload( 'speech_synthesize', [ 'text' => str_repeat( 'a', 4001 ) ] ) ) );
t( 'O05 only speech', ! $A->supports( 'chat' ) && $A->supports( 'speech_synthesize' ) );

// Başarılı MP3
$GLOBALS['REPLIES'] = [ [ 200, $MP3, 'audio/mpeg' ] ];
$r = $A->dispatch( 'speech_synthesize', [ 'text' => 'Merhaba', 'voice' => 'Kore', 'format' => 'mp3', 'speed' => 1.0 ], [ 'model' => 'google/gemini-3.8-flash-tts' ] );
t( 'O06 mp3 returned', ! is_wp_error( $r ) && 'audio/mpeg' === $r['mime'] && file_get_contents( $r['temp_file'] ) === $MP3 && 'gen-1' === $r['provider_ref'] );
t( 'O07 endpoint, auth, model', 'https://openrouter.ai/api/v1/audio/speech' === $GLOBALS['POSTS'][0][0]
    && 'Bearer sk-or-test' === $GLOBALS['POSTS'][0][2]['Authorization'] && 'google/gemini-3.8-flash-tts' === $GLOBALS['POSTS'][0][1]['model'] );

// Hız reddi -> hızsız yeniden dene
$GLOBALS['POSTS'] = [];
$GLOBALS['REPLIES'] = [ [ 400, '{"error":{"message":"speed is not supported for this model"}}', 'application/json' ], [ 200, $MP3, 'audio/mpeg' ] ];
$r = $A->dispatch( 'speech_synthesize', [ 'text' => 'Hola', 'voice' => 'Eve', 'speed' => 1.3 ], [ 'model' => 'x-ai/grok-voice-tts-1.0' ] );
t( 'O08 retried without speed', ! is_wp_error( $r ) && 2 === count( $GLOBALS['POSTS'] ) && isset( $GLOBALS['POSTS'][0][1]['speed'] ) && ! isset( $GLOBALS['POSTS'][1][1]['speed'] ) );

// MP3 reddi -> PCM -> WAV (FFmpeg yok)
$GLOBALS['POSTS'] = [];
$pcm = str_repeat( "\x01\x00", 24000 );                      // 1 sn, 24 kHz, 16 bit
$GLOBALS['REPLIES'] = [ [ 400, '{"error":{"message":"Only pcm response_format is supported"}}', 'application/json' ], [ 200, $pcm, 'audio/pcm' ] ];
$r = $A->dispatch( 'speech_synthesize', [ 'text' => 'مرحبا', 'voice' => 'Kore', 'format' => 'mp3' ], [ 'model' => 'google/gemini-3.1-flash-tts-preview' ] );
$wav = is_wp_error( $r ) ? '' : file_get_contents( $r['temp_file'] );
t( 'O09 pcm fallback wrapped as wav', ! is_wp_error( $r ) && 'pcm' === $GLOBALS['POSTS'][1][1]['response_format'] && 'audio/wav' === $r['mime']
    && 'RIFF' === substr( $wav, 0, 4 ) && strlen( $wav ) === 44 + strlen( $pcm ) && 48000 === unpack( 'V', substr( $wav, 28, 4 ) )[1] );

// Başka hata olduğu gibi döner
$GLOBALS['REPLIES'] = [ [ 401, '{"error":{"message":"No auth credentials found"}}', 'application/json' ] ];
$r = $A->dispatch( 'speech_synthesize', [ 'text' => 'x' ], [] );
t( 'O10 auth error surfaced', is_wp_error( $r ) && false !== strpos( $r->get_error_message(), 'HTTP 401' ) && false !== strpos( $r->get_error_message(), 'No auth' ) );
$GLOBALS['KEYS'] = [];
t( 'O11 missing key', is_wp_error( $A->dispatch( 'speech_synthesize', [ 'text' => 'x' ], [] ) ) );

// Katalog: anahtar yok -> yedek
$C = 'AGFO_AIM_OpenRouter_TTS_Catalog';
$cat = $C::catalog();
$ids = array_column( $cat['models'], 'id' );
t( 'C01 fallback without key', 'fallback' === $cat['source'] && 'google/gemini-3.8-flash-tts' === $ids[0] && $cat['models'][0]['recommended'] );
$gem = $cat['models'][0];
$kok = $cat['models'][ array_search( 'hexgrad/kokoro-82m', $ids, true ) ];
t( 'C02 voices per model', 30 === count( $gem['voice_ids'] ) && in_array( 'Kore', $gem['voice_ids'], true ) && ! in_array( 'Kore', $kok['voice_ids'], true )
    && in_array( 'ef_dora', $kok['voice_ids'], true ) );
t( 'C03 instructions only gemini/openai', $gem['supports_instructions'] && ! $kok['supports_instructions'] );

// Katalog: OpenRouter /models yanıtı
$GLOBALS['KEYS'] = [ 'openrouter' => 'sk-or-test' ];
$GLOBALS['GET'] = [ 'code' => 200, 'body' => json_encode( [ 'data' => [
    [ 'id' => 'google/gemini-3.8-flash-tts', 'name' => 'Google: Gemini 3.8 Flash TTS', 'architecture' => [ 'output_modalities' => [ 'speech' ] ],
      'pricing' => [ 'prompt' => '0.0000005', 'completion' => '0.000009' ], 'description' => 'Fast TTS.' ],
    [ 'id' => 'microsoft/mai-voice-2.1', 'name' => 'MAI-Voice 2.1', 'architecture' => [ 'output_modalities' => [ 'speech' ] ],
      'supported_voices' => [ 'en-US-Harper:MAI-Voice-2.1', [ 'id' => 'tr-TR-Emel:MAI-Voice-2.1', 'description' => 'Türkçe' ] ] ],
    [ 'id' => 'mistralai/voxtral-mini-tts-3-0', 'name' => 'Voxtral', 'architecture' => [ 'output_modalities' => [ 'speech' ] ] ],
    [ 'id' => 'anthropic/claude-sonnet-5.5', 'name' => 'Sonnet', 'architecture' => [ 'output_modalities' => [ 'text' ] ] ],
] ] ) ];
$cat = $C::catalog( true );
$ids = array_column( $cat['models'], 'id' );
t( 'C04 api models with known voices only', [ 'google/gemini-3.8-flash-tts', 'microsoft/mai-voice-2.1' ] === $ids && 'openrouter_models_api' === $cat['source'] );
t( 'C05 supported_voices used', [ 'en-US-Harper:MAI-Voice-2.1', 'tr-TR-Emel:MAI-Voice-2.1' ] === $cat['models'][1]['voice_ids'] );
t( 'C06 price note', 0 === strpos( $cat['models'][0]['description'], '$0.5/M girdi' ) );
t( 'C07 cached', $C::catalog()['cached'] === true && false !== strpos( $GLOBALS['GETURL'], 'output_modalities=speech' ) );
t( 'C08 family voice helpers', 'Kore' === $C::default_voice( 'google/gemini-3.8-flash-lite-tts' ) && null === $C::family_voices( 'fish-audio/drama-3' ) );
$GLOBALS['TRANSIENT'] = [];
$GLOBALS['GET'] = [ 'code' => 500, 'body' => '' ];
t( 'C09 api failure -> fallback', 'fallback' === $C::catalog( true )['source'] );

echo "\n$pass passed, $fail failed\n";
exit( $fail ? 1 : 0 );
