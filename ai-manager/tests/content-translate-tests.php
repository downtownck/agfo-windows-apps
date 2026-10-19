<?php
/**
 * AGFO AI Manager 17.3.0 — editor translation tests.
 * Run from the plugin root: php tests/content-translate-tests.php
 * Loads only the content prompt library, the transformer and the classic editor class with
 * minimal WordPress stubs. agfo_api_post() is a recorder; no network, no WordPress.
 */
if ( PHP_SAPI !== 'cli' ) { exit; }

$agfo_aim_test_root = dirname( __DIR__ );
if ( ! defined( 'ABSPATH' ) ) define( 'ABSPATH', sys_get_temp_dir() . '/' );
if ( ! defined( 'AGFO_AIM_VERSION' ) ) define( 'AGFO_AIM_VERSION', 'test' );
if ( ! defined( 'AGFO_AIM_PLUGIN_DIR' ) ) define( 'AGFO_AIM_PLUGIN_DIR', $agfo_aim_test_root . '/' );
if ( ! defined( 'AGFO_AIM_PLUGIN_URL' ) ) define( 'AGFO_AIM_PLUGIN_URL', 'https://example.test/wp-content/plugins/agfo-ai-manager/' );

$GLOBALS['AGFO_T'] = [ 'F' => [], 'O' => [], 'SENT' => [], 'TRANSLATION' => null, 'DEFAULT' => null, 'REPLY' => null ];

if ( ! function_exists( 'add_action' ) ) { function add_action( $h, $cb, $p = 10, $a = 1 ) { return true; } }
if ( ! function_exists( 'add_filter' ) ) { function add_filter( $h, $cb, $p = 10, $a = 1 ) { $GLOBALS['AGFO_T']['F'][ $h ][] = $cb; return true; } }
if ( ! function_exists( 'apply_filters' ) ) { function apply_filters( $h, $v, ...$a ) { foreach ( $GLOBALS['AGFO_T']['F'][ $h ] ?? [] as $cb ) { $v = $cb( $v, ...$a ); } return $v; } }
if ( ! function_exists( 'get_option' ) ) { function get_option( $k, $d = false ) { return $GLOBALS['AGFO_T']['O'][ $k ] ?? $d; } }
if ( ! function_exists( 'update_option' ) ) { function update_option( $k, $v, $a = null ) { $GLOBALS['AGFO_T']['O'][ $k ] = $v; return true; } }
if ( ! function_exists( 'delete_option' ) ) { function delete_option( $k ) { unset( $GLOBALS['AGFO_T']['O'][ $k ] ); return true; } }
if ( ! function_exists( 'sanitize_key' ) ) { function sanitize_key( $k ) { return preg_replace( '/[^a-z0-9_\-]/', '', strtolower( (string) $k ) ); } }
if ( ! function_exists( 'sanitize_text_field' ) ) { function sanitize_text_field( $s ) { return trim( preg_replace( '/[\r\n\t ]+/u', ' ', strip_tags( (string) $s ) ) ); } }
if ( ! function_exists( 'sanitize_textarea_field' ) ) { function sanitize_textarea_field( $s ) { return trim( strip_tags( (string) $s ) ); } }
if ( ! function_exists( 'wp_unslash' ) ) { function wp_unslash( $s ) { return $s; } }
if ( ! function_exists( 'absint' ) ) { function absint( $n ) { return abs( (int) $n ); } }
if ( ! function_exists( 'wp_strip_all_tags' ) ) { function wp_strip_all_tags( $s ) { return trim( strip_tags( (string) $s ) ); } }
if ( ! function_exists( 'wp_kses_post' ) ) { function wp_kses_post( $s ) { return preg_replace( '#<script\b[^>]*>.*?</script>#is', '', (string) $s ); } }
if ( ! function_exists( 'wp_kses' ) ) { function wp_kses( $s, $allowed = [] ) { return wp_kses_post( $s ); } }
if ( ! function_exists( 'wp_json_encode' ) ) { function wp_json_encode( $d, $o = 0 ) { return json_encode( $d, $o | JSON_UNESCAPED_UNICODE ); } }
if ( ! function_exists( 'esc_attr' ) ) { function esc_attr( $s ) { return htmlspecialchars( (string) $s, ENT_QUOTES, 'UTF-8' ); } }
if ( ! function_exists( 'esc_html' ) ) { function esc_html( $s ) { return htmlspecialchars( (string) $s, ENT_QUOTES, 'UTF-8' ); } }
if ( ! function_exists( 'esc_html__' ) ) { function esc_html__( $s, $d = '' ) { return esc_html( $s ); } }
if ( ! function_exists( 'esc_attr__' ) ) { function esc_attr__( $s, $d = '' ) { return esc_attr( $s ); } }
if ( ! function_exists( 'current_user_can' ) ) { function current_user_can( $c ) { return true; } }
if ( ! class_exists( 'WP_Error', false ) ) { class WP_Error { public $c; public $m; public $d; function __construct( $c = '', $m = '', $d = null ) { $this->c = $c; $this->m = $m; $this->d = $d; } function get_error_message() { return $this->m; } function get_error_code() { return $this->c; } function get_error_data() { return $this->d; } } }
if ( ! function_exists( 'is_wp_error' ) ) { function is_wp_error( $x ) { return $x instanceof WP_Error; } }

if ( ! function_exists( 'agfo_get_priority_api_key' ) ) {
    function agfo_get_priority_api_key( $force = false, $model = '', $provider = '' ) {
        if ( '' !== $provider ) {   // 17.8.0: provider override for a per-job model choice
            return [ 'code' => $provider, 'provider_name' => ucfirst( $provider ), 'model' => $model ?: 'x', 'key' => 'k', 'chat_url' => 'https://api.' . $provider . '.test/chat', 'auth' => [] ];
        }
        return $GLOBALS['AGFO_T']['DEFAULT'];
    }
}
if ( ! function_exists( 'agfo_api_registry' ) ) {
    function agfo_api_registry() { return [ 'openai' => [ 'type' => 'llm', 'label' => 'OpenAI' ], 'groq' => [ 'type' => 'llm', 'label' => 'Groq' ], 'fal' => [ 'type' => 'media' ], 'nokey' => [ 'type' => 'llm' ] ]; }
}
if ( ! function_exists( 'agfo_get_api_key' ) ) {
    function agfo_get_api_key( $code ) { return 'nokey' === $code ? '' : 'sk-test'; }
}
if ( ! function_exists( 'agfo_get_translation_config' ) ) {
    function agfo_get_translation_config() { return $GLOBALS['AGFO_T']['TRANSLATION']; }
}
if ( ! function_exists( 'agfo_api_post' ) ) {
    function agfo_api_post( $url, $headers, $body, $args = [] ) {
        $GLOBALS['AGFO_T']['SENT'][] = [ 'url' => $url, 'body' => json_decode( $body, true ), 'args' => $args ];
        $model = (string) ( $args['model'] ?? '' );
        if ( isset( $GLOBALS['AGFO_T']['FAIL'][ $model ] ) ) {
            [ $code, $msg ] = $GLOBALS['AGFO_T']['FAIL'][ $model ];
            return [ 'http_code' => $code, 'body' => json_encode( [ 'error' => [ 'message' => $msg ] ] ) ];
        }
        $reply = $GLOBALS['AGFO_T']['REPLY'] ?? [ 'choices' => [ [ 'message' => [ 'content' => '<p>Hello world</p>' ], 'finish_reason' => 'stop' ] ] ];
        return [ 'http_code' => 200, 'body' => json_encode( $reply ) ];
    }
}

require $agfo_aim_test_root . '/includes/content/class-content-prompt-library.php';
require $agfo_aim_test_root . '/includes/content/class-content-transformer.php';
require $agfo_aim_test_root . '/includes/editor/class-classic-editor-content.php';

$agfo_aim_test_pass = 0;
$agfo_aim_test_fail = 0;
if ( ! function_exists( 'agfo_aim_test_ct_check' ) ) {
    function agfo_aim_test_ct_check( string $name, bool $ok, string $detail = '' ): void {
        global $agfo_aim_test_pass, $agfo_aim_test_fail;
        if ( $ok ) { $agfo_aim_test_pass++; echo "PASS  {$name}\n"; }
        else { $agfo_aim_test_fail++; echo "FAIL  {$name}" . ( $detail !== '' ? " — {$detail}" : '' ) . "\n"; }
    }
}
if ( ! function_exists( 'agfo_aim_test_ct_config' ) ) {
    function agfo_aim_test_ct_config( string $code, string $model ): array {
        return [ 'code' => $code, 'provider_name' => ucfirst( $code ), 'model' => $model, 'key' => 'k-test', 'chat_url' => 'https://api.' . $code . '.test/v1/chat/completions', 'auth' => [ 'Authorization' => 'Bearer k-test' ] ];
    }
}

$default = agfo_aim_test_ct_config( 'openai', 'gpt-5.6' );
$routed  = agfo_aim_test_ct_config( 'openai', 'gpt-4.1-mini' );
$GLOBALS['AGFO_T']['DEFAULT'] = $default;

// T1: translation template is recognised; other templates are not.
agfo_aim_test_ct_check( 'T1 translate_polish is a translation template', AGFO_AIM_Content_Transformer::is_translation_template( 'translate_polish' ) && ! AGFO_AIM_Content_Transformer::is_translation_template( 'rewrite_balanced' ) );

// T2: with a translation route the request goes to the routed model.
$GLOBALS['AGFO_T']['TRANSLATION'] = $routed;
$GLOBALS['AGFO_T']['SENT'] = [];
$r = AGFO_AIM_Content_Transformer::transform( '<p>Merhaba dünya</p>', [ 'template' => 'translate_polish', 'language' => 'English' ] );
$sent = $GLOBALS['AGFO_T']['SENT'][0] ?? [];
agfo_aim_test_ct_check( 'T2 translation uses the routed model', is_array( $r ) && ( $sent['body']['model'] ?? '' ) === 'gpt-4.1-mini' && ( $r['model'] ?? '' ) === 'gpt-4.1-mini', json_encode( $sent['body']['model'] ?? null ) );
agfo_aim_test_ct_check( 'T3 result flags translation_route', is_array( $r ) && ! empty( $r['translation'] ) && ! empty( $r['translation_route'] ) && empty( $r['truncated'] ) );
agfo_aim_test_ct_check( 'T4 translation timeout is 120 s', (int) ( $sent['args']['timeout'] ?? 0 ) === 120 );
agfo_aim_test_ct_check( 'T5 target language reaches the system prompt', strpos( wp_json_encode( $sent['body'] ?? [] ), 'Target language: English' ) !== false );

// T6: no usable route → default model, no route flag.
$GLOBALS['AGFO_T']['TRANSLATION'] = false;
$GLOBALS['AGFO_T']['SENT'] = [];
$r = AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'translate_polish', 'language' => 'Deutsch' ] );
$sent = $GLOBALS['AGFO_T']['SENT'][0] ?? [];
agfo_aim_test_ct_check( 'T6 no route falls back to the default model', is_array( $r ) && ( $sent['body']['model'] ?? '' ) === 'gpt-5.6' && empty( $r['translation_route'] ) && ! empty( $r['translation'] ) );

// T7: incomplete route (no key) is ignored.
$GLOBALS['AGFO_T']['TRANSLATION'] = [ 'code' => 'openai', 'model' => 'x', 'key' => '', 'chat_url' => 'u' ];
$GLOBALS['AGFO_T']['SENT'] = [];
AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'translate_polish' ] );
agfo_aim_test_ct_check( 'T7 route without key is ignored', ( $GLOBALS['AGFO_T']['SENT'][0]['body']['model'] ?? '' ) === 'gpt-5.6' );

// T8: non-translation templates never use the translation route.
$GLOBALS['AGFO_T']['TRANSLATION'] = $routed;
$GLOBALS['AGFO_T']['SENT'] = [];
$r = AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'rewrite_balanced' ] );
$sent = $GLOBALS['AGFO_T']['SENT'][0] ?? [];
agfo_aim_test_ct_check( 'T8 rewrite keeps the default model and 45 s timeout', ( $sent['body']['model'] ?? '' ) === 'gpt-5.6' && (int) ( $sent['args']['timeout'] ?? 0 ) === 45 && empty( $r['translation'] ) );

// T9-T10: output budget scales with the source and stays within 8000.
$m = new ReflectionMethod( 'AGFO_AIM_Content_Transformer', 'recommended_output_tokens' );
$m->setAccessible( true );
$small = $m->invoke( null, 'translate_polish', 100, false, false );
$mid   = $m->invoke( null, 'translate_polish', 2000, false, false );
$huge  = $m->invoke( null, 'translate_polish', 9000, false, false );
agfo_aim_test_ct_check( 'T9 translation budget scales (1200 / 4800)', $small === 1200 && $mid === 4800, "$small / $mid" );
agfo_aim_test_ct_check( 'T10 translation budget capped at 8000', $huge === 8000 );
agfo_aim_test_ct_check( 'T11 summarize budget unchanged', $m->invoke( null, 'summarize', 2000, false, false ) === 2600 );

// T12: truncation is reported for OpenAI, Claude and Gemini stop reasons.
$t = new ReflectionMethod( 'AGFO_AIM_Content_Transformer', 'is_truncated' );
$t->setAccessible( true );
agfo_aim_test_ct_check( 'T12 truncation detected across providers',
    $t->invoke( null, [ 'choices' => [ [ 'finish_reason' => 'length' ] ] ] )
    && $t->invoke( null, [ 'stop_reason' => 'max_tokens' ] )
    && $t->invoke( null, [ 'candidates' => [ [ 'finishReason' => 'MAX_TOKENS' ] ] ] )
    && ! $t->invoke( null, [ 'choices' => [ [ 'finish_reason' => 'stop' ] ] ] ) );
$GLOBALS['AGFO_T']['REPLY'] = [ 'choices' => [ [ 'message' => [ 'content' => '<p>Partial</p>' ], 'finish_reason' => 'length' ] ] ];
$r = AGFO_AIM_Content_Transformer::transform( '<p>Uzun metin</p>', [ 'template' => 'translate_polish' ] );
agfo_aim_test_ct_check( 'T13 transform returns truncated=true', is_array( $r ) && ! empty( $r['truncated'] ) );
$GLOBALS['AGFO_T']['REPLY'] = null;

// T14-T15: toolbar markup and language filter.
$html = AGFO_AIM_Classic_Editor_Content::translate_controls_html( 'content' );
agfo_aim_test_ct_check( 'T14 toolbar group has button and six languages', strpos( $html, 'agfo-classic-translate-open' ) !== false && substr_count( $html, '<option ' ) === 6 && strpos( $html, 'value="Français"' ) !== false );
add_filter( 'agfo_ai_content_languages', function ( $l ) { $l['Русский'] = 'Русский'; $l['"><script>'] = 'x'; return $l; } );
$html = AGFO_AIM_Classic_Editor_Content::translate_controls_html( 'content' );
agfo_aim_test_ct_check( 'T15 filtered languages are added and escaped', strpos( $html, 'value="Русский"' ) !== false && strpos( $html, '<script>' ) === false );

// T16: the editor JS wires the button, the language store and the preference guard.
$js = (string) file_get_contents( $agfo_aim_test_root . '/assets/js/classic-editor-content.js' );
agfo_aim_test_ct_check( 'T16 editor JS contains translate wiring',
    strpos( $js, ".agfo-classic-translate-open" ) !== false
    && strpos( $js, 'function openTranslate(' ) !== false
    && strpos( $js, 'if (!skipSave) savePreferences();' ) !== false
    && strpos( $js, 'data.truncated' ) !== false );

// T17 (17.3.1): malformed filter output never breaks translation detection.
add_filter( 'agfo_ai_content_translation_templates', function ( $ids ) { return [ [ 'x' ], new stdClass(), '', 'Translate_Polish', 'my_translate' ]; } );
agfo_aim_test_ct_check( 'T17 non-scalar filter values are ignored', AGFO_AIM_Content_Transformer::is_translation_template( 'translate_polish' ) && AGFO_AIM_Content_Transformer::is_translation_template( 'my_translate' ) && ! AGFO_AIM_Content_Transformer::is_translation_template( '' ) );
$GLOBALS['AGFO_T']['F']['agfo_ai_content_translation_templates'] = [ function () { return 'not-an-array'; } ];
agfo_aim_test_ct_check( 'T18 non-array filter output falls back to the default', AGFO_AIM_Content_Transformer::is_translation_template( 'translate_polish' ) );
unset( $GLOBALS['AGFO_T']['F']['agfo_ai_content_translation_templates'] );

// T19-T24 (17.7.0): Ceviri rotasi kullanilamazsa varsayilan modele dusme, <think> temizligi, Markdown kipi.
$together = agfo_aim_test_ct_config( 'together', 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B' );
$GLOBALS['AGFO_T']['TRANSLATION'] = $together;
$GLOBALS['AGFO_T']['FAIL'] = [ 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B' => [ 400, 'Unable to access non-serverless model deepseek-ai/DeepSeek-R1-Distill-Qwen-7B.' ] ];
$GLOBALS['AGFO_T']['SENT'] = [];
$r = AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'translate_polish', 'language' => 'English' ] );
agfo_aim_test_ct_check( 'T19 failing translation route falls back to the default model',
    is_array( $r ) && $r['model'] === 'gpt-5.6' && ! empty( $r['route_fallback'] ) && strpos( $r['route_error'], 'non-serverless' ) !== false
    && count( $GLOBALS['AGFO_T']['SENT'] ) === 2 && $GLOBALS['AGFO_T']['SENT'][0]['args']['model'] === 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B' );
$err = $GLOBALS['AGFO_T']['O']['agfo_aim_translation_route_error'] ?? null;
agfo_aim_test_ct_check( 'T19b dead route is recorded for the control center warning', is_array( $err ) && $err['model'] === 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B' && strpos( $err['message'], 'non-serverless' ) !== false );
$GLOBALS['AGFO_T']['FAIL'] = [];
AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'translate_polish' ] );
agfo_aim_test_ct_check( 'T19c warning is cleared once the route works again', ! isset( $GLOBALS['AGFO_T']['O']['agfo_aim_translation_route_error'] ) );
$GLOBALS['AGFO_T']['FAIL'] = [ 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B' => [ 429, 'rate limited' ] ];
$r = AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'translate_polish' ] );
agfo_aim_test_ct_check( 'T20 rate limit is reported, not silently rerouted', is_wp_error( $r ) && strpos( $r->get_error_message(), '429' ) !== false );
$GLOBALS['AGFO_T']['FAIL'] = [ 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B' => [ 400, 'bad' ], 'gpt-5.6' => [ 400, 'also bad' ] ];
$r = AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'translate_polish' ] );
agfo_aim_test_ct_check( 'T21 when both fail the original route error is returned', is_wp_error( $r ) && strpos( $r->get_error_message(), 'bad' ) !== false );
$GLOBALS['AGFO_T']['FAIL'] = [];
$GLOBALS['AGFO_T']['TRANSLATION'] = null;
$GLOBALS['AGFO_T']['REPLY'] = [ 'choices' => [ [ 'message' => [ 'content' => "<think>reasoning…</think>\n<p>Hello</p>" ], 'finish_reason' => 'stop' ] ] ];
$r = AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'translate_polish' ] );
agfo_aim_test_ct_check( 'T22 reasoning <think> block is removed', is_array( $r ) && $r['plain_text'] === 'Hello' );
$md_out = "```markdown\n⟦0⟧ # Scope\n\n⟦1⟧ **Cleaning** is verified\n\n| A | B |\n|---|---|\n| 1 | <u>2</u> |\n```";
$GLOBALS['AGFO_T']['REPLY'] = [ 'choices' => [ [ 'message' => [ 'content' => $md_out ], 'finish_reason' => 'stop' ] ] ];
$GLOBALS['AGFO_T']['SENT'] = [];
$r = AGFO_AIM_Content_Transformer::transform( "⟦0⟧ # Kapsam\n\n⟦1⟧ **Temizlik** doğrulanır", [ 'template' => 'translate_polish', 'format' => 'markdown' ] );
$sys = $GLOBALS['AGFO_T']['SENT'][0]['body']['messages'][0]['content'] ?? json_encode( $GLOBALS['AGFO_T']['SENT'][0]['body'] );
agfo_aim_test_ct_check( 'T23 markdown mode keeps tables, underline, markers and line structure',
    is_array( $r ) && $r['format'] === 'markdown' && strpos( $r['text'], "| 1 | <u>2</u> |" ) !== false
    && strpos( $r['text'], "⟦1⟧ **Cleaning**" ) !== false && strpos( $r['text'], '```' ) === false && substr_count( $r['text'], "\n" ) >= 5 );
agfo_aim_test_ct_check( 'T24 markdown mode sends source verbatim and the format override rule',
    strpos( json_encode( $GLOBALS['AGFO_T']['SENT'][0]['body'], JSON_UNESCAPED_UNICODE ), '**Temizlik**' ) !== false
    && strpos( json_encode( $GLOBALS['AGFO_T']['SENT'][0]['body'], JSON_UNESCAPED_UNICODE ), 'OUTPUT FORMAT OVERRIDE' ) !== false );
$GLOBALS['AGFO_T']['REPLY'] = null;

// T25-T29 (17.8.0): AI Editor picks the translation model per job.
$GLOBALS['AGFO_T']['TRANSLATION'] = $together;
$GLOBALS['AGFO_T']['SENT'] = [];
$r = AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'translate_polish', 'route_model' => 'groq|llama-3.1-8b-instant' ] );
agfo_aim_test_ct_check( 'T25 chosen model is used instead of the route', is_array( $r ) && $r['model'] === 'llama-3.1-8b-instant' && ! empty( $r['model_choice'] )
    && $GLOBALS['AGFO_T']['SENT'][0]['args']['model'] === 'llama-3.1-8b-instant' );
foreach ( [ 'fal|flux', 'nokey|m', 'unknown|m', 'openai', 'openai|bad model name;' ] as $bad ) {
    $r = AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'translate_polish', 'route_model' => $bad ] );
    agfo_aim_test_ct_check( 'T26 rejected choice ' . $bad, is_wp_error( $r ) && $r->get_error_code() === 'agfo_model_choice' );
}
$GLOBALS['AGFO_T']['SENT'] = [];
$r = AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'rewrite_balanced', 'route_model' => 'groq|llama-3.1-8b-instant' ] );
agfo_aim_test_ct_check( 'T27 choice only applies to translation templates', is_array( $r ) && $r['model'] === 'gpt-5.6' && empty( $r['model_choice'] ) );
$GLOBALS['AGFO_T']['FAIL'] = [ 'llama-3.1-8b-instant' => [ 404, 'model not found' ] ];
unset( $GLOBALS['AGFO_T']['O']['agfo_aim_translation_route_error'] );
$r = AGFO_AIM_Content_Transformer::transform( '<p>Merhaba</p>', [ 'template' => 'translate_polish', 'route_model' => 'groq|llama-3.1-8b-instant' ] );
agfo_aim_test_ct_check( 'T28 failing choice falls back to default', is_array( $r ) && $r['model'] === 'gpt-5.6' && ! empty( $r['route_fallback'] ) );
agfo_aim_test_ct_check( 'T29 failing choice does not mark the site route as broken', ! isset( $GLOBALS['AGFO_T']['O']['agfo_aim_translation_route_error'] ) );
$GLOBALS['AGFO_T']['FAIL'] = [];
$GLOBALS['AGFO_T']['TRANSLATION'] = null;

echo "\n{$agfo_aim_test_pass} pass, {$agfo_aim_test_fail} fail\n";
exit( $agfo_aim_test_fail > 0 ? 1 : 0 );
