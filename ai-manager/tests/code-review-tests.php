<?php
/**
 * AGFO AI Manager 17.0.0 — isolated AI code review tests (17.2.0).
 * Run from the plugin root: php tests/code-review-tests.php
 * Uses a fake provider server and a minimal WordPress HTTP filter chain; no network, no WordPress.
 */
if (PHP_SAPI !== 'cli') { exit; }
// Fake chat provider for the review service: records the request, returns a canned review.
function agfo_aim_test_fake_server($url, $args) {
    $b = json_decode($args['body'], true);
    $GLOBALS['SENT'][] = ['url' => $url, 'body' => $b, 'raw' => $args['body']];
    if (!empty($GLOBALS['REJECT_KEYED']) && (($b['response_format']['json_schema']['schema']['properties']['findings']['type'] ?? '') === 'object')) {
        return ['response' => ['code' => 400], 'headers' => [], 'body' => json_encode(['error' => ['message' => "Invalid schema for response_format 'agfo_code_review': too many properties."]])];
    }
    $content = $GLOBALS['REVIEW_REPLY'] ?? '{}';
    return ['response' => ['code' => 200], 'headers' => [], 'body' => json_encode(['choices' => [['message' => ['content' => $content]]], 'usage' => ['prompt_tokens' => 15000, 'completion_tokens' => 2000]])];
}

$argv[1] = dirname(__DIR__);
if (!defined('ABSPATH')) define('ABSPATH', sys_get_temp_dir() . '/');
define('AGFO_AIM_PLUGIN_DIR', $argv[1] . '/');
define('AGFO_AIM_DATA_DIR', sys_get_temp_dir() . '/agfo-data-' . getmypid() . '/');
define('AGFO_AIM_DATA_FILE', AGFO_AIM_DATA_DIR . 'data.json');
define('WP_DEBUG', false);
@mkdir(AGFO_AIM_DATA_DIR);
copy($argv[1] . '/data/data.json', AGFO_AIM_DATA_FILE);
$GLOBALS['F'] = []; $GLOBALS['O'] = []; $GLOBALS['SENT'] = []; $GLOBALS['AGFO_ENC'] = null;
if (!function_exists('add_filter')) { function add_filter($h, $cb, $p = 10, $a = 1) { $GLOBALS['F'][$h][$p][] = [$cb, $a]; return true; } }
if (!function_exists('add_action')) { function add_action($h, $cb, $p = 10, $a = 1) { return add_filter($h, $cb, $p, $a); } }
if (!function_exists('apply_filters')) { function apply_filters($h, $v, ...$args) { if (empty($GLOBALS['F'][$h])) return $v; ksort($GLOBALS['F'][$h]); foreach ($GLOBALS['F'][$h] as $cbs) foreach ($cbs as [$cb, $n]) { $v = call_user_func_array($cb, array_slice(array_merge([$v], $args), 0, max(1,$n))); } return $v; } }
if (!function_exists('do_action')) { function do_action($h, ...$a) { apply_filters($h, null, ...$a); } }
if (!function_exists('get_option')) { function get_option($k, $d = false) { return array_key_exists($k, $GLOBALS['O']) ? $GLOBALS['O'][$k] : $d; } }
if (!function_exists('update_option')) { function update_option($k, $v, $a = null) { $GLOBALS['O'][$k] = $v; return true; } }
if (!function_exists('delete_option')) { function delete_option($k) { unset($GLOBALS['O'][$k]); return true; } }
if (!function_exists('sanitize_key')) { function sanitize_key($k) { return preg_replace('/[^a-z0-9_\-]/', '', strtolower((string)$k)); } }
if (!function_exists('sanitize_text_field')) { function sanitize_text_field($s) { return trim(strip_tags((string)$s)); } }
if (!function_exists('wp_parse_url')) { function wp_parse_url($u, $c = -1) { return parse_url($u, $c); } }
if (!function_exists('wp_json_encode')) { function wp_json_encode($d, $o = 0) { return json_encode($d, $o); } }
if (!function_exists('wp_generate_password')) { function wp_generate_password($n = 12, $a = true, $b = false) { return substr(str_repeat('abcdef123456', 5), 0, $n); } }
if (!function_exists('current_time')) { function current_time($t) { return date('Y-m-d H:i:s'); } }
if (!function_exists('wp_mkdir_p')) { function wp_mkdir_p($d) { return @mkdir($d, 0777, true); } }
if (!class_exists('WP_Error', false)) { class WP_Error { public $c; public $m; function __construct($c = '', $m = '') { $this->c = $c; $this->m = $m; } function get_error_message() { return $this->m; } function get_error_code() { return $this->c; } } }
if (!function_exists('is_wp_error')) { function is_wp_error($x) { return $x instanceof WP_Error; } }
if (!function_exists('wp_remote_retrieve_response_code')) { function wp_remote_retrieve_response_code($r) { return is_array($r) ? ($r['response']['code'] ?? 0) : 0; } }
if (!function_exists('wp_remote_retrieve_body')) { function wp_remote_retrieve_body($r) { return is_array($r) ? ($r['body'] ?? '') : ''; } }
if (!function_exists('wp_remote_retrieve_header')) { function wp_remote_retrieve_header($r, $h) { return ''; } }
if (!function_exists('wp_remote_request')) { function wp_remote_request($url, $args = []) {
    $args = apply_filters('http_request_args', $args, $url);
    $pre = apply_filters('pre_http_request', false, $args, $url);
    if ($pre !== false) return $pre;
    $resp = agfo_aim_test_fake_server($url, $args);
    return apply_filters('http_response', $resp, $args, $url);
} }
if (!function_exists('wp_remote_post')) { function wp_remote_post($url, $args = []) { $args['method'] = 'POST'; return wp_remote_request($url, $args); } }
if (!function_exists('agfo_aim_test_response')) { function agfo_aim_test_response($code, $body) { return ['response' => ['code' => $code], 'body' => json_encode($body), 'headers' => []]; } }
if (!function_exists('agfo_aim_test_fake_server')) { function agfo_aim_test_fake_server($url, $args) {
    $b = json_decode($args['body'], true);
    $GLOBALS['SENT'][] = ['url' => $url, 'body' => $b, 'raw' => $args['body']];
    $path = parse_url($url, PHP_URL_PATH);
    if (strpos($url, 'api.openai.com') !== false && substr($path, -17) === '/chat/completions') {
        $m = $b['model'];
        if (preg_match('/-pro|codex/', $m)) return agfo_aim_test_response(404, ['error' => ['message' => 'This model is only supported in v1/responses and not in v1/chat/completions.', 'type' => 'invalid_request_error', 'param' => 'model', 'code' => null]]);
        if ($m === 'ghost-model') return agfo_aim_test_response(404, ['error' => ['message' => 'The model `ghost-model` does not exist or you do not have access to it.', 'code' => 'model_not_found']]);
        if ($m === 'gpt-3.5-turbo-instruct') return agfo_aim_test_response(404, ['error' => ['message' => 'This is not a chat model and thus not supported in the v1/chat/completions endpoint. Did you mean to use v1/completions?']]);
        if (isset($b['temperature']) && !preg_match('/^gpt-4|^gpt-3\.5/', $m)) return agfo_aim_test_response(400, ['error' => ['message' => "Unsupported value: 'temperature' does not support 0.2 with this model. Only the default (1) value is supported.", 'param' => 'temperature', 'code' => 'unsupported_value']]);
        if (isset($b['max_tokens']) && strpos($m, 'gpt-5') === 0) return agfo_aim_test_response(400, ['error' => ['message' => "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.", 'param' => 'max_tokens', 'code' => 'unsupported_parameter']]);
        if (isset($b['reasoning_effort']) && strpos($m, 'gpt-4') === 0) return agfo_aim_test_response(400, ['error' => ['message' => 'Unrecognized request argument supplied: reasoning_effort']]);
        if (isset($b['tools']) && is_array($b['tools'][0]['function']['parameters']['properties'] ?? null) && strpos($args['body'], '"properties":[]') !== false) return agfo_aim_test_response(400, ['error' => ['message' => "Invalid schema: properties must be object"]]);
        return agfo_aim_test_response(200, ['id' => 'c1', 'model' => $m, 'choices' => [['message' => ['role' => 'assistant', 'content' => 'OK chat ' . $m]]], 'usage' => ['prompt_tokens' => 3, 'completion_tokens' => 2, 'total_tokens' => 5]]);
    }
    if (strpos($url, 'api.openai.com') !== false && substr($path, -10) === '/responses') {
        if (isset($b['messages'])) return agfo_aim_test_response(400, ['error' => ['message' => 'messages not allowed']]);
        if (isset($b['temperature'])) return agfo_aim_test_response(400, ['error' => ['message' => "Unsupported parameter: 'temperature'", 'param' => 'temperature']]);
        return agfo_aim_test_response(200, ['id' => 'resp_1', 'model' => $b['model'], 'status' => 'completed', 'output' => [['type' => 'reasoning'], ['type' => 'message', 'content' => [['type' => 'output_text', 'text' => 'OK responses ' . $b['model'] . ' instr=' . ($b['instructions'] ?? '-') . ' max=' . ($b['max_output_tokens'] ?? '-') . ' eff=' . ($b['reasoning']['effort'] ?? '-')]]]], 'usage' => ['input_tokens' => 7, 'output_tokens' => 4, 'total_tokens' => 11]]);
    }
    if (strpos($url, 'api.anthropic.com') !== false) {
        if (isset($b['temperature'], $b['top_p'])) return agfo_aim_test_response(400, ['error' => ['type' => 'invalid_request_error', 'message' => '`temperature` and `top_p` cannot both be specified for this model. Please use only one.']]);
        return agfo_aim_test_response(200, ['content' => [['type' => 'text', 'text' => 'OK claude']]]);
    }
    if (strpos($url, 'generativelanguage') !== false) {
        if (strpos($path, 'gemini-old') !== false) return agfo_aim_test_response(404, ['error' => ['code' => 404, 'message' => 'models/gemini-old is not found for API version v1beta, or is not supported for generateContent.', 'status' => 'NOT_FOUND']]);
        if (isset($b['generationConfig']['topK']) ) return agfo_aim_test_response(400, ['error' => ['message' => 'Invalid JSON payload received. Unknown name "topK" at generation_config: Cannot find field.', 'status' => 'INVALID_ARGUMENT']]);
        return agfo_aim_test_response(200, ['candidates' => [['content' => ['parts' => [['text' => 'OK gemini ' . $path]]]]]]);
    }
    if (strpos($url, 'api.groq.com') !== false) {
        if (isset($b['logit_bias'])) return agfo_aim_test_response(400, ['error' => ['message' => "'logit_bias' : property 'logit_bias' is unsupported", 'type' => 'invalid_request_error']]);
        return agfo_aim_test_response(200, ['choices' => [['message' => ['content' => 'OK groq']]]]);
    }
    return agfo_aim_test_response(500, ['error' => 'unexpected ' . $url]);
} }
require AGFO_AIM_PLUGIN_DIR . 'includes/functions.php';
require AGFO_AIM_PLUGIN_DIR . 'includes/class-ai-capability.php';
require AGFO_AIM_PLUGIN_DIR . 'includes/core/class-request-guard.php';
AGFO_AIM_Request_Guard::register_hooks();
if (!function_exists('current_user_can')) { function current_user_can($c){return true;} } if (!function_exists('check_ajax_referer')) { function check_ajax_referer(){return true;} } if (!function_exists('wp_unslash')) { function wp_unslash($v){return $v;} }
if (!defined('DAY_IN_SECONDS')) define('DAY_IN_SECONDS', 86400);
foreach (['ajax/class-data.php','class-model-catalog.php','class-ai-image.php','adapters/class-adapter-image.php','image/class-image-prompt-library.php','image/class-image-generator.php','editor/class-classic-editor-image.php','class-code-review.php'] as $f) require_once AGFO_AIM_PLUGIN_DIR . 'includes/' . $f;

$agfo_aim_test_pass = 0; $agfo_aim_test_fail = 0;
if (!function_exists('agfo_aim_test_ok')) { function agfo_aim_test_ok($cond, $name) { global $agfo_aim_test_pass, $agfo_aim_test_fail; if ($cond) { $agfo_aim_test_pass++; echo "PASS $name\n"; } else { $agfo_aim_test_fail++; echo "FAIL $name\n"; } } }
$O = &$GLOBALS['O'];
$O['agfo_openai_api_key'] = 'k-xxxxxxxxxxxx';
$O['agfo_selected_provider'] = 'openai'; $O['agfo_global_preferred_model'] = 'gpt-5.6-sol';
$O['agfo_models_openai'] = ['gpt-5.6-sol', 'gpt-4.1-mini', 'gpt-4.1'];
$R = 'AGFO_AIM_Code_Review';

$payload = [
    'plugin'   => ['name' => 'Demo', 'version' => '2.0.0', 'previous_version' => '1.9.0', 'requires_php' => '7.4'],
    'install'  => ['mode' => 'replace', 'changed' => 2, 'added' => 1, 'removed' => 0],
    'findings' => [
        ['file' => 'includes/img.php', 'line' => 12, 'level' => 'warning', 'message' => 'Riskli yürütme/obfuscation fonksiyonu', 'snippet' => "    11: \$raw = \$resp['b64'];\n>>> 12: \$bin = base64_decode( \$raw, true );\n    13: file_put_contents( \$tmp, \$bin );"],
        ['file' => 'tests/a-tests.php', 'line' => 5, 'level' => 'notice', 'message' => 'Global function pluggable-risk', 'snippet' => ">>> 5: function r() {}"],
    ],
    'hunks'    => [
        ['file' => 'includes/ajax.php', 'kind' => 'added', 'from' => 40, 'to' => 42, 'text' => "+ 40: add_action( 'wp_ajax_demo_save', 'demo_save' );\n+ 41: function demo_save() { update_option( 'demo', \$_POST['v'] ); }\n+ 42: define( 'DEMO_API_KEY', 'sk-live-abcdefghijklmnopqrstuvwxyz' );"],
    ],
    'surfaces' => ['added' => ['ajax:demo_save'], 'removed' => ['function:demo_old_helper']],
    'revision' => "Tarih: 2026-10-07\npassword => 'hunter2hunter2'",
];

// R1 quick model defaults to gpt-4.1-mini
$m = agfo_ai_code_review_model('quick');
agfo_aim_test_ok($m['provider'] === 'openai' && $m['model'] === 'gpt-4.1-mini', 'R1 quick review defaults to gpt-4.1-mini');
agfo_aim_test_ok(agfo_ai_code_review_model('deep')['model'] === 'gpt-5.6-sol', 'R1 deep review uses default chat model');

// R2 routed model wins
$routing = agfo_get_capability_routing(); $routing['code_review'] = ['provider' => 'openai', 'model' => 'gpt-4.1']; agfo_save_capability_routing($routing);
agfo_aim_test_ok(agfo_ai_code_review_model('quick')['model'] === 'gpt-4.1', 'R2 Yetenek Yönlendirme route overrides default');
$routing['code_review'] = ['provider' => '', 'model' => '']; agfo_save_capability_routing($routing);

// R3 full review round trip
$GLOBALS['REVIEW_REPLY'] = json_encode([
    'verdict' => 'rollback',
    'summary' => 'Yeni AJAX ucunda nonce yok.',
    'findings' => [
        ['ref' => 'F1', 'classification' => 'justified', 'severity' => 'info', 'explanation' => 'Sağlayıcı görsel verisi çözülüyor.', 'fix' => ''],
        ['ref' => 'F2', 'classification' => 'false_positive', 'severity' => 'info', 'explanation' => 'Test dosyası.', 'fix' => ''],
        ['ref' => 'F9', 'classification' => 'issue', 'severity' => 'high', 'explanation' => 'Uydurma ref', 'fix' => ''],
    ],
    'risks' => [
        ['title' => 'AJAX ucunda nonce ve yetki kontrolü yok', 'severity' => 'high', 'file' => 'includes/ajax.php', 'line' => 41, 'explanation' => 'update_option doğrudan $_POST ile.', 'fix' => 'check_ajax_referer + current_user_can'],
        ['title' => 'Uydurma risk', 'severity' => 'high', 'file' => 'includes/other.php', 'line' => 99, 'explanation' => 'gösterilmemiş kod', 'fix' => ''],
    ],
    'actions' => ['demo_save için nonce ekle'],
]);
$GLOBALS['SENT'] = [];
$rep = agfo_ai_code_review($payload, ['mode' => 'quick']);
agfo_aim_test_ok(is_array($rep) && !is_wp_error($rep), 'R3 review returns a report');
$sent = $GLOBALS['SENT'][0]['body'] ?? [];
agfo_aim_test_ok(($sent['model'] ?? '') === 'gpt-4.1-mini' && ($sent['response_format']['type'] ?? '') === 'json_schema' && ($sent['temperature'] ?? null) === 0, 'R3 request: gpt-4.1-mini, strict JSON schema, temperature 0');
$raw = $GLOBALS['SENT'][0]['raw'] ?? '';
agfo_aim_test_ok(strpos($raw, 'abcdefghijklmnopqrstuvwxyz') === false && strpos($raw, 'hunter2hunter2') === false && strpos($raw, 'REDACTED') !== false, 'R3 secrets masked before sending');
agfo_aim_test_ok(count($rep['risks']) === 1 && $rep['risks'][0]['line'] === 41 && $rep['unverified'] === 1, 'R3 risk without evidence dropped');
agfo_aim_test_ok($rep['counts']['justified'] === 1 && $rep['counts']['false_positive'] === 1 && count($rep['findings']) === 2, 'R3 invented finding ref ignored, real ones classified');
agfo_aim_test_ok($rep['verdict'] === 'rollback', 'R3 rollback kept when a verified high risk exists');
agfo_aim_test_ok(strpos($rep['fix_prompt'], 'includes/ajax.php:41') !== false, 'R3 fix prompt built from verified items');
agfo_aim_test_ok($rep['meta']['tokens_in'] === 15000 && abs($rep['meta']['cost'] - (15000 * 0.4 + 2000 * 1.6) / 1e6) < 1e-6 || $rep['meta']['cost'] === null, 'R3 cost computed from token prices when known');

// R4 hallucination-only reply cannot raise the verdict
$GLOBALS['REVIEW_REPLY'] = json_encode(['verdict' => 'rollback', 'summary' => 'x', 'findings' => [['ref' => 'F1', 'classification' => 'justified', 'severity' => 'info', 'explanation' => 'ok', 'fix' => '']], 'risks' => [['title' => 'fake', 'severity' => 'high', 'file' => 'nope.php', 'line' => 1, 'explanation' => '', 'fix' => '']], 'actions' => []]);
$rep = agfo_ai_code_review($payload);
agfo_aim_test_ok($rep['verdict'] === 'ok' && $rep['counts']['not_reviewed'] === 1 && $rep['fix_prompt'] === '', 'R4 unbacked rollback downgraded to ok; skipped finding marked not reviewed');

// R5 garbage reply
$GLOBALS['REVIEW_REPLY'] = 'Sorry, I cannot.';
$rep = agfo_ai_code_review($payload);
agfo_aim_test_ok(is_wp_error($rep) && $rep->get_error_code() === 'agfo_review_parse', 'R5 non-JSON reply is an error, not a report');

// R6 fenced JSON accepted
$GLOBALS['REVIEW_REPLY'] = "```json\n" . json_encode(['verdict' => 'ok', 'summary' => 's', 'findings' => [], 'risks' => [], 'actions' => []]) . "\n```";
agfo_aim_test_ok(!is_wp_error(agfo_ai_code_review($payload)), 'R6 fenced JSON parsed');

// R7 provider body shapes
$g = $R::build_body('gemini', 'gemini-2.5-flash', 'sys', 'u');
$c = $R::build_body('claude', 'claude-sonnet-4-5', 'sys', 'u');
$d = $R::build_body('deepseek', 'deepseek-chat', 'sys', 'u');
agfo_aim_test_ok($g['generationConfig']['responseMimeType'] === 'application/json' && isset($c['system']) && $d['response_format']['type'] === 'json_object', 'R7 provider-specific JSON modes');
$x = $R::build_body('openai', 'gpt-5.6-sol', 'sys', 'u');
agfo_aim_test_ok(($x['reasoning_effort'] ?? '') === 'low' && $x['max_tokens'] === 12000, 'R7 reasoning model gets effort + room');

// R8 (17.3.1) "missing nonce/capability" risk refuted by the shown code is dropped.
$pl8 = ['plugin' => ['name' => 'X'], 'findings' => [], 'hunks' => [[
    'kind' => 'added', 'file' => 'includes/x.php', 'from' => 700, 'to' => 712,
    'text' => "  704:        public static function legacy_save_prompts(): void {\n  705:            self::verify_legacy_nonce();\n  706:            if ( ! current_user_can( self::required_capability() ) ) {\n  707:                wp_send_json_error( 'no' );\n  708:            }\n+ 709:            \$raw = \$_POST['prompts'];\n  710:            update_option( 'x', \$raw );",
], [
    'kind' => 'added', 'file' => 'includes/y.php', 'from' => 10, 'to' => 12,
    'text' => "  10:    public static function save(): void {\n+ 11:        update_option( 'y', \$_POST['v'] );\n  12:    }",
], [
    'kind' => 'added', 'file' => 'includes/x.php', 'from' => 733, 'to' => 738,
    'text' => "  733:        private static function verify_legacy_nonce(): void {\n  734:            \$nonce = \$_POST['security'] ?? '';\n  735:            if ( ! wp_verify_nonce( \$nonce, 'a' ) ) {\n  736:                wp_send_json_error( 'x', 403 );\n  737:            }\n  738:        }",
]]];
[$txt8, $ev8] = $R::render_payload($pl8);
$parsed8 = ['verdict' => 'review', 'summary' => 's', 'findings' => [], 'actions' => [], 'risks' => [
    ['title' => 'AJAX handlerda nonce ve yetki kontrolü görünmüyor', 'severity' => 'medium', 'file' => 'includes/x.php', 'line' => 709, 'explanation' => 'Nonce veya current_user_can kontrolü yok.', 'fix' => 'Ekleyin.'],
    ['title' => 'Kaydetme işleminde nonce kontrolü eksik', 'severity' => 'medium', 'file' => 'includes/y.php', 'line' => 11, 'explanation' => 'Nonce yok.', 'fix' => 'Ekleyin.'],
    ['title' => 'Girdi sanitize edilmeden kaydediliyor', 'severity' => 'medium', 'file' => 'includes/x.php', 'line' => 709, 'explanation' => 'Sanitize yok.', 'fix' => 'sanitize_text_field.'],
]];
$v8 = $R::validate($parsed8, $pl8, $ev8);
$titles8 = array_column($v8['risks'], 'title');
agfo_aim_test_ok($v8['contradicted'] === 1 && !in_array('AJAX handlerda nonce ve yetki kontrolü görünmüyor', $titles8, true), 'R8 refuted "no nonce/capability" claim dropped');
agfo_aim_test_ok(in_array('Kaydetme işleminde nonce kontrolü eksik', $titles8, true) && in_array('Girdi sanitize edilmeden kaydediliyor', $titles8, true), 'R8 unrefuted and unrelated risks kept');
agfo_aim_test_ok(!$R::contradicted(['title' => 'Yetki kontrolü yok', 'explanation' => ''], "function a() {\n  check_ajax_referer('x');\n}"), 'R8 nonce present does not refute a capability claim');

// R9 (17.3.1) source_root: the installed file is read for context, confined to the root.
$root9 = sys_get_temp_dir() . '/agfo-cr-root-' . getmypid();
@mkdir($root9 . '/inc', 0777, true);
file_put_contents($root9 . '/inc/h.php', "<?php\nfunction h() {\n    check_ajax_referer( 'n', 'nonce' );\n" . str_repeat("    \$a = 1;\n", 30) . "    update_option( 'z', \$_POST['z'] );\n}\n");
$ctx9 = $R::context_lines(['source_root' => $root9], [], 'inc/h.php', 34);
agfo_aim_test_ok(strpos($ctx9, 'check_ajax_referer') !== false && strpos($ctx9, 'function h()') !== false, 'R9 context read from the installed file back to the function line');
agfo_aim_test_ok($R::context_lines(['source_root' => $root9], [], '../../etc/passwd', 1) === '' && $R::context_lines(['source_root' => $root9], [], 'inc/h.txt', 1) === '', 'R9 traversal and non-code paths refused');
@unlink($root9 . '/inc/h.php'); @rmdir($root9 . '/inc'); @rmdir($root9);

// R10 (17.3.2) only real enforcement refutes a claim.
$claimBoth = ['title' => 'Nonce ve yetki kontrolü yok', 'explanation' => ''];
$claimCap  = ['title' => 'Yetki kontrolü eksik', 'explanation' => ''];
agfo_aim_test_ok(!$R::contradicted($claimBoth, "function a() {\n  self::verify_legacy_nonce();\n  current_user_can( 'x' );\n}"), 'R10 unresolvable nonce wrapper does not refute');
agfo_aim_test_ok(!$R::contradicted($claimCap, "function a() {\n  \$cap = self::required_capability();\n  register_rest_route( 'a', 'b', [ 'permission_callback' => '__return_true' ] );\n}"), 'R10 required_capability / permission_callback names alone do not refute');
agfo_aim_test_ok($R::contradicted($claimBoth, "function a() {\n  self::verify_x_nonce();\n  if ( ! current_user_can( 'manage_options' ) ) return;\n}", function ($n) { return $n === 'verify_x_nonce' ? "function verify_x_nonce() {\n check_ajax_referer( 'a' );\n}" : ''; }), 'R10 wrapper calling a core nonce function refutes');
agfo_aim_test_ok(!$R::contradicted($claimBoth, "function a() {\n  self::verify_x_nonce();\n  current_user_can( 'x' );\n}", function ($n) { return "function verify_x_nonce() {\n return true;\n}"; }), 'R10 no-op wrapper does not refute');

// R11 (17.3.2) jail uses a directory boundary: wp-content-evil is outside wp-content.
$t11 = sys_get_temp_dir() . '/agfo-cr-jail-' . getmypid();
@mkdir($t11 . '/wp-content/plugins/p', 0777, true);
@mkdir($t11 . '/wp-content-evil/p', 0777, true);
file_put_contents($t11 . '/wp-content/plugins/p/a.php', "<?php\nfunction a() {\n  check_ajax_referer('n');\n}\n");
file_put_contents($t11 . '/wp-content-evil/p/a.php', "<?php\nfunction a() {\n  check_ajax_referer('n');\n}\n");
if (!defined('WP_CONTENT_DIR')) define('WP_CONTENT_DIR', $t11 . '/wp-content');
agfo_aim_test_ok(strpos($R::context_lines(['source_root' => $t11 . '/wp-content/plugins/p'], [], 'a.php', 3), 'check_ajax_referer') !== false, 'R11 plugin folder inside wp-content readable');
agfo_aim_test_ok($R::context_lines(['source_root' => $t11 . '/wp-content-evil/p'], [], 'a.php', 3) === '', 'R11 sibling folder with wp-content prefix refused');
foreach (['/wp-content/plugins/p/a.php', '/wp-content-evil/p/a.php'] as $f) { @unlink($t11 . $f); }
foreach (['/wp-content/plugins/p', '/wp-content/plugins', '/wp-content', '/wp-content-evil/p', '/wp-content-evil', ''] as $d) { @rmdir($t11 . $d); }

// R12 (17.3.2) keyed findings schema: one required key per finding; keyed replies parsed.
$sc = $R::schema(3);
agfo_aim_test_ok(($sc['properties']['findings']['required'] ?? []) === ['F1', 'F2', 'F3'] && $sc['required'][0] === 'findings' && $R::schema(0)['properties']['findings']['type'] === 'array', 'R12 schema requires F1..Fn, findings first, list form when none');
$b12 = $R::build_body('openai', 'gpt-4.1-mini', 'sys', 'u', 2);
agfo_aim_test_ok(($b12['response_format']['json_schema']['schema']['properties']['findings']['required'] ?? []) === ['F1', 'F2'], 'R12 request body carries the keyed schema');
$pl12 = ['findings' => [['file' => 'a.php', 'line' => 1, 'message' => 'm1'], ['file' => 'tests/b.php', 'line' => 0, 'message' => 'm2']]];
$v12 = $R::validate(['verdict' => 'ok', 'summary' => 's', 'risks' => [], 'actions' => [], 'findings' => ['F1' => ['classification' => 'justified', 'severity' => 'low', 'explanation' => 'e', 'fix' => ''], 'F2' => ['classification' => 'false_positive', 'severity' => 'info', 'explanation' => 'e', 'fix' => '']]], $pl12, []);
agfo_aim_test_ok($v12['counts']['justified'] === 1 && $v12['counts']['false_positive'] === 1 && $v12['counts']['not_reviewed'] === 0, 'R12 keyed reply classified, nothing left unreviewed');

// R13 (17.3.2) keyed schema rejected by the provider → one retry with the list form.
$GLOBALS['REJECT_KEYED'] = true; $GLOBALS['SENT'] = [];
$GLOBALS['REVIEW_REPLY'] = json_encode(['verdict' => 'ok', 'summary' => 's', 'findings' => [], 'risks' => [], 'actions' => []]);
$rep13 = agfo_ai_code_review($payload);
$GLOBALS['REJECT_KEYED'] = false;
$types13 = array_map(function ($x) { return $x['body']['response_format']['json_schema']['schema']['properties']['findings']['type'] ?? '?'; }, array_values(array_filter($GLOBALS['SENT'], function ($x) { return isset($x['body']['response_format']); })));
agfo_aim_test_ok(is_array($rep13) && !is_wp_error($rep13) && $types13 === ['object', 'array'], 'R13 schema rejection falls back to list form once (' . implode(',', $types13) . ')');

// R14 (17.3.3) a risk that admits it cannot be verified is dropped as unverified.
$pl14 = ['findings' => [], 'hunks' => [['kind' => 'added', 'file' => 'inc/r.php', 'from' => 24, 'to' => 26, 'text' => "  24:        public static function register(): void {\n+ 25:            add_action( 'wp_ajax_agfo_x', [ __CLASS__, 'ajax_review' ] );\n  26:        }"]]];
[$t14, $e14] = $R::render_payload($pl14);
$v14 = $R::validate(['verdict' => 'review', 'summary' => 's', 'findings' => [], 'actions' => [], 'risks' => [
    ['title' => 'AJAX aksiyonu nonce ve yetki kontrolü eksik', 'severity' => 'high', 'file' => 'inc/r.php', 'line' => 25, 'explanation' => 'Fonksiyonun tamamı verilmemiş. Bu nedenle nonce ve yetki kontrolü olup olmadığı doğrulanamıyor.', 'fix' => ''],
    ['title' => 'Girdi doğrulanmıyor', 'severity' => 'medium', 'file' => 'inc/r.php', 'line' => 25, 'explanation' => '$_POST değeri sanitize edilmeden kullanılıyor.', 'fix' => ''],
]], $pl14, $e14);
agfo_aim_test_ok($v14['unverified'] === 1 && count($v14['risks']) === 1 && $v14['risks'][0]['title'] === 'Girdi doğrulanmıyor' && $v14['verdict'] === 'review', 'R14 self-declared unverifiable risk dropped; "doğrulanmıyor" claim kept');

// R15 (17.3.3) hook registration lines are judged on the callback body (source_root).
$root15 = (defined('WP_CONTENT_DIR') ? WP_CONTENT_DIR . '/plugins' : sys_get_temp_dir()) . '/agfo-cr-hook-' . getmypid();
@mkdir($root15, 0777, true);
file_put_contents($root15 . '/r.php', "<?php\nclass X {\n    public static function register() {\n        add_action( 'wp_ajax_agfo_x', [ __CLASS__, 'ajax_review' ] );\n        add_action( 'wp_ajax_agfo_y', array( \$this, 'open' ) );\n    }\n    public static function ajax_review() {\n        check_ajax_referer( 'agfo_sn_modal_nonce', 'nonce' );\n        if ( ! current_user_can( 'edit_post', 1 ) ) { wp_send_json_error( 'no' ); }\n    }\n    public function open() {\n        update_option( 'y', 1 );\n    }\n}\n");
$claim15 = ['title' => 'AJAX aksiyonunda nonce ve yetki kontrolü eksik', 'severity' => 'high', 'line' => 4, 'explanation' => '', 'fix' => '', 'file' => 'r.php'];
$ev15 = ['r.php:4' => "        add_action( 'wp_ajax_agfo_x', [ __CLASS__, 'ajax_review' ] );", 'r.php:5' => "        add_action( 'wp_ajax_agfo_y', array( \$this, 'open' ) );"];
$pl15 = ['findings' => [], 'source_root' => $root15];
$v15 = $R::validate(['verdict' => 'review', 'summary' => 's', 'findings' => [], 'actions' => [], 'risks' => [$claim15, array_merge($claim15, ['line' => 5])]], $pl15, $ev15);
agfo_aim_test_ok($v15['contradicted'] === 1 && count($v15['risks']) === 1 && $v15['risks'][0]['line'] === 5, 'R15 callback with checks refutes the claim; callback without checks keeps it');
agfo_aim_test_ok($R::hook_callback("add_action('wp_ajax_a', 'my_func');") === 'my_func' && $R::hook_callback("add_action( 'admin_post_b', [ self::class, 'save' ] );") === 'save' && $R::hook_callback("add_action( 'wp_ajax_nopriv_c', 'Foo\\\\Bar::run' );") === 'run' && $R::hook_callback("add_action( 'init', 'x' );") === '', 'R16 hook callback names resolved; non-AJAX hooks ignored');
@unlink($root15 . '/r.php'); @rmdir($root15);
if (defined('WP_CONTENT_DIR')) { @rmdir(WP_CONTENT_DIR . '/plugins'); @rmdir(WP_CONTENT_DIR); @rmdir(dirname(WP_CONTENT_DIR)); }
// R17 (17.3.3) without source_root the shown lines are used; the callback body must be visible.
$ev17 = ['r.php:4' => "        add_action( 'wp_ajax_agfo_x', [ __CLASS__, 'ajax_review' ] );", 'r.php:7' => '    public static function ajax_review() {', 'r.php:8' => "        check_ajax_referer( 'n', 'nonce' );", 'r.php:9' => "        if ( ! current_user_can( 'edit_post', 1 ) ) { return; }"];
$v17 = $R::validate(['verdict' => 'review', 'summary' => 's', 'findings' => [], 'actions' => [], 'risks' => [$claim15]], ['findings' => []], $ev17);
$v17b = $R::validate(['verdict' => 'review', 'summary' => 's', 'findings' => [], 'actions' => [], 'risks' => [$claim15]], ['findings' => []], ['r.php:4' => $ev17['r.php:4']]);
agfo_aim_test_ok($v17['contradicted'] === 1 && $v17b['contradicted'] === 0 && count($v17b['risks']) === 1, 'R17 shown callback body refutes; unseen body keeps the claim (other filters decide)');

// R18 (17.3.3) the context ends at the enclosing function's closing brace: a check in the next
// method does not refute a claim about this one.
$ev18 = ['m.php:1' => 'class M {', 'm.php:2' => '    public function save() {', 'm.php:3' => "        update_option( 'a', \$_POST['a'] ); // { not a brace", 'm.php:4' => '    }', 'm.php:5' => '    public function guarded() {', 'm.php:6' => "        check_ajax_referer( 'x' );", 'm.php:7' => "        current_user_can( 'manage_options' );", 'm.php:8' => '    }'];
$ctx18 = $R::context_lines(['findings' => []], $ev18, 'm.php', 3);
agfo_aim_test_ok(strpos($ctx18, 'save()') !== false && strpos($ctx18, 'check_ajax_referer') === false && !$R::contradicted(['title' => 'Nonce ve yetki kontrolü yok', 'explanation' => ''], $ctx18), 'R18 neighbouring method cannot refute the claim');

echo "\n$agfo_aim_test_pass pass / $agfo_aim_test_fail fail\n";
exit($agfo_aim_test_fail ? 1 : 0);
