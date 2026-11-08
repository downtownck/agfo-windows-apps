<?php
/**
 * AGFO AI Manager 17.14.0 — AI Editor seslendirme sağlayıcıları (OpenAI / ElevenLabs / MiniMax) testleri.
 * Run from the plugin root: php tests/editor-voice-tests.php
 * Minimal WordPress stubs, fake adapter registry; no network, no WordPress.
 */
if ( PHP_SAPI !== 'cli' ) { exit; }
$root = dirname( __DIR__ );
if ( ! defined( 'ABSPATH' ) ) define( 'ABSPATH', sys_get_temp_dir() . '/' );

$GLOBALS['KEYS'] = [ 'openai' => 'sk-test' ]; $GLOBALS['USAGE'] = []; $GLOBALS['DISPATCH'] = []; $GLOBALS['KILL'] = true;
function sanitize_key( $k ) { return preg_replace( '/[^a-z0-9_\-]/', '', strtolower( (string) $k ) ); }
function sanitize_text_field( $s ) { return trim( preg_replace( '/[\r\n\t ]+/u', ' ', strip_tags( (string) $s ) ) ); }
function sanitize_textarea_field( $s ) { return trim( strip_tags( (string) $s ) ); }
function agfo_get_api_key( $code ) { return $GLOBALS['KEYS'][ $code ] ?? null; }
class WP_Error { public $c; public $m; function __construct( $c = '', $m = '' ) { $this->c = $c; $this->m = $m; } function get_error_message() { return $this->m; } function get_error_code() { return $this->c; } }
function is_wp_error( $x ) { return $x instanceof WP_Error; }
final class AGFO_AIM_Kill_Switch { public static function is_enabled( $c ) { return $GLOBALS['KILL']; } }
final class AGFO_AIM_Usage { public static function record( array $e ): bool { $GLOBALS['USAGE'][] = $e; return true; } }
class Fake_TTS_Adapter {
    public $code; function __construct( $c ) { $this->code = $c; }
    function supports( $cap ) { return 'speech_synthesize' === $cap; }
    function validate_payload( $cap, $p ) { return '' === trim( (string) ( $p['voice'] ?? '' ) ) ? new WP_Error( 'agfo_tts_voice_required', 'voice' ) : true; }
    function estimate_cost( $cap, $p, $ctx = [] ) { return [ 'cost' => 0.015, 'units' => mb_strlen( $p['text'] ) ]; }
    function dispatch( $cap, $p, $ctx = [] ) {
        $GLOBALS['DISPATCH'][] = [ $this->code, $p, $ctx ];
        $tmp = tempnam( sys_get_temp_dir(), 'tts' );
        file_put_contents( $tmp, $GLOBALS['MP3'] );
        return [ 'temp_file' => $tmp, 'mime' => 'audio/mpeg', 'bytes' => strlen( $GLOBALS['MP3'] ), 'usage' => [ 'input_units' => 42, 'output_units' => 1, 'unit_name' => 'character' ], 'cost_actual' => 0.02 ];
    }
}
final class AGFO_AIM_Adapter_Registry {
    public static function get( $p ) { return in_array( $p, [ 'openai', 'elevenlabs', 'minimax' ], true ) ? new Fake_TTS_Adapter( $p ) : new WP_Error( 'agfo_adapter_missing', $p ); }
    public static function supports( $p, $c ) { return ! is_wp_error( self::get( $p ) ); }
}
require $root . '/includes/api/class-editor-voice.php';

$pass = 0; $fail = 0;
function t( $name, $cond ) { global $pass, $fail; if ( $cond ) { $pass++; echo "PASS $name\n"; } else { $fail++; echo "FAIL $name\n"; } }

/** n adet MPEG-1 Layer III 128 kbps 44.1 kHz kare; xing verilirse ilk karede Xing başlığı. */
function fake_mp3( int $n, ?int $xing = null ): string {
    $frame = "\xFF\xFB\x90\x00" . str_repeat( "\x00", 413 );
    $out = '';
    for ( $i = 0; $i < $n; $i++ ) {
        $f = $frame;
        if ( 0 === $i && null !== $xing ) {
            $f = substr_replace( $f, 'Xing' . pack( 'N', 1 ) . pack( 'N', $xing ), 4 + 32, 12 );
        }
        $out .= $f;
    }
    return $out;
}
$GLOBALS['MP3'] = fake_mp3( 100 );
$V = 'AGFO_AIM_Editor_Voice';

// Sağlayıcı listesi
$prov = array_column( $V::providers(), null, 'id' );
t( 'V01 five providers, ema first, openrouter last', array_keys( $prov ) === [ 'ema', 'openai', 'elevenlabs', 'minimax', 'openrouter' ] );
t( 'V02 openai ready with key, others not', $prov['openai']['ready'] && ! $prov['elevenlabs']['ready'] && ! $prov['minimax']['ready'] );
t( 'V03 ema not ready without adapter class', false === $prov['ema']['ready'] );
t( 'V04 pauses and lexicon only on ema', $prov['ema']['pauses'] && $prov['ema']['lexicon'] && ! $prov['openai']['pauses'] && ! $prov['minimax']['lexicon'] );
t( 'V05 quick max 4000 everywhere, job max per provider', 4000 === $prov['minimax']['max_chars'] && 9000 === $prov['minimax']['job_max_chars'] && 4000 === $prov['openai']['job_max_chars'] );

// Hız sınırları
t( 'V06 elevenlabs speed clamped to 1.2', 1.2 === $V::clamp_speed( 'elevenlabs', 1.4 ) );
t( 'V07 minimax speed 0.5 floor', 0.5 === $V::clamp_speed( 'minimax', 0.2 ) );
t( 'V08 openai speed passes 1.15', 1.15 === $V::clamp_speed( 'openai', 1.15 ) );

// Yük
list( $p, $ctx ) = $V::payload( 'openai', 'Merhaba', [ 'voice' => '', 'model' => '', 'speed' => 1.1, 'instructions' => 'Sakin oku.' ] );
t( 'V09 openai default voice/model', 'marin' === $p['voice'] && 'gpt-4o-mini-tts' === $ctx['model'] && 'mp3' === $p['format'] );
t( 'V10 openai instructions kept', 'Sakin oku.' === ( $p['instructions'] ?? '' ) );
list( $p, $ctx ) = $V::payload( 'minimax', 'Merhaba', [ 'voice' => 'Turkish_Man', 'model' => 'speech-02-hd', 'instructions' => 'x' ] );
t( 'V11 minimax voice, model, turkish boost, no instructions', 'Turkish_Man' === $p['voice'] && 'speech-02-hd' === $ctx['model'] && 'Turkish' === $p['language_boost'] && ! isset( $p['instructions'] ) );
list( $p, $ctx ) = $V::payload( 'elevenlabs', 'Merhaba', [ 'voice' => 'abc123' ] );
t( 'V12 elevenlabs language tr', 'tr' === $p['language'] && 'eleven_multilingual_v2' === $ctx['model'] );
$e = $V::payload( 'elevenlabs', 'Merhaba', [ 'voice' => '' ] );
t( 'V13 elevenlabs needs a voice', is_wp_error( $e ) && 'agfo_editor_voice_required' === $e->get_error_code() );
t( 'V14 ema and unknown refused by payload', is_wp_error( $V::payload( 'ema', 'x', [] ) ) && is_wp_error( $V::payload( 'foo', 'x', [] ) ) );

// Seslendirme
$r = $V::synthesize( 'openai', 'Merhaba dünya', [ 'voice' => 'cedar', 'speed' => 1.0 ] );
t( 'V15 synthesize returns audio bytes', is_array( $r ) && $r['audio'] === $GLOBALS['MP3'] );
t( 'V16 seconds estimated from bitrate', is_array( $r ) && abs( $r['seconds'] - 100 * 417 * 8 / 128000 ) < 0.01 );
t( 'V17 dispatch got voice and model', 'openai' === $GLOBALS['DISPATCH'][0][0] && 'cedar' === $GLOBALS['DISPATCH'][0][1]['voice'] && 'agfo-ai-editor' === $GLOBALS['DISPATCH'][0][2]['source_plugin'] );
$u = $GLOBALS['USAGE'][0] ?? [];
t( 'V18 usage recorded with actual cost', 'openai' === ( $u['provider'] ?? '' ) && 'speech_synthesize' === $u['capability'] && 0.02 === $u['cost_actual'] && 42.0 === $u['input_units'] );
$e = $V::synthesize( 'elevenlabs', 'Merhaba', [ 'voice' => 'abc' ] );
t( 'V19 missing key refused', is_wp_error( $e ) && 'agfo_no_api_key' === $e->get_error_code() );
$GLOBALS['KILL'] = false;
$e = $V::synthesize( 'openai', 'Merhaba', [] );
t( 'V20 kill switch respected', is_wp_error( $e ) && 'agfo_kill_switch' === $e->get_error_code() );
$GLOBALS['KILL'] = true;

// MP3 süresi
t( 'V21 xing frame count wins', abs( $V::mp3_seconds( fake_mp3( 10, 500 ) ) - 500 * 1152 / 44100 ) < 0.001 );
t( 'V22 id3 tag skipped', abs( $V::mp3_seconds( "ID3\x04\x00\x00\x00\x00\x00\x0A" . str_repeat( "\x00", 10 ) . fake_mp3( 50 ) ) - 50 * 417 * 8 / 128000 ) < 0.01 );
t( 'V23 garbage -> 0', 0.0 === $V::mp3_seconds( 'not audio' ) );

// NEW 17.15.0: OpenRouter
final class AGFO_AIM_Adapter_OpenRouter { const MAX_CHARS = 4000; }
require $root . '/includes/tts/class-openrouter-tts-catalog.php';
$prov = array_column( $V::providers(), null, 'id' );
t( 'V24 openrouter instructions + voices_by_model, no key', $prov['openrouter']['instructions'] && $prov['openrouter']['voices_by_model'] && ! $prov['openrouter']['ready'] && 4000 === $prov['openrouter']['job_max_chars'] );
list( $p, $ctx ) = $V::payload( 'openrouter', 'مرحبا', [ 'voice' => '', 'model' => '', 'instructions' => 'Mısır Arapçasıyla oku' ] );
t( 'V25 openrouter defaults gemini + Kore + instructions', 'Kore' === $p['voice'] && 'google/gemini-3.8-flash-tts' === $ctx['model'] && 'Mısır Arapçasıyla oku' === $p['instructions'] );
list( $p, $ctx ) = $V::payload( 'openrouter', 'Hola', [ 'voice' => 'Kore', 'model' => 'x-ai/grok-voice-tts-1.0' ] );
t( 'V26 voice outside model family replaced', 'Eve' === $p['voice'] );
list( $p, $ctx ) = $V::payload( 'openrouter', 'Hi', [ 'voice' => 'en-US-Harper:MAI-Voice-2.1', 'model' => 'microsoft/mai-voice-2.1' ] );
t( 'V27 unknown family keeps voice', 'en-US-Harper:MAI-Voice-2.1' === $p['voice'] );
$wav = 'RIFF' . pack( 'V', 36 + 48000 ) . 'WAVEfmt ' . pack( 'VvvVVvv', 16, 1, 1, 24000, 48000, 2, 16 ) . 'data' . pack( 'V', 48000 ) . str_repeat( "\0", 48000 );
t( 'V28 wav seconds', 1.0 === $V::mp3_seconds( $wav ) );

echo "\n{$pass} passed, {$fail} failed\n";
exit( $fail ? 1 : 0 );
