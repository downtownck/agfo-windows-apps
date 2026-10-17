<?php
/**
 * AGFO AI Manager 17.0.0 — isolated model catalogue regression tests (17.1.0).
 * Run from the plugin root: php tests/model-catalog-tests.php
 * Uses a fake provider server and a minimal WordPress HTTP filter chain; no network, no WordPress.
 */
if (PHP_SAPI !== 'cli') { exit; }
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
foreach (['ajax/class-data.php','class-model-catalog.php','class-ai-image.php','adapters/class-adapter-image.php','image/class-image-prompt-library.php','image/class-image-generator.php','editor/class-classic-editor-image.php'] as $f) require_once AGFO_AIM_PLUGIN_DIR . 'includes/' . $f;
$pass = 0; $fail = 0;
if (!function_exists('agfo_aim_test_ok')) { function agfo_aim_test_ok($cond, $name) { global $pass, $fail; if ($cond) { $pass++; echo "PASS $name\n"; } else { $fail++; echo "FAIL $name\n"; } } }
$O = &$GLOBALS['O'];
foreach (['openai','claude','gemini','deepseek','fal'] as $p) $O['agfo_' . $p . '_api_key'] = 'k-xxxxxxxxxxxx';
$O['agfo_selected_provider'] = 'openai'; $O['agfo_global_preferred_model'] = 'gpt-5.6-sol';
$d = json_decode(file_get_contents(AGFO_AIM_DATA_FILE), true);
$O['agfo_models_openai'] = array_merge($d['models']['openai'], ['gpt-5.7', 'gpt-5.7-mini']);
$C = 'AGFO_AIM_Model_Catalog';

// C1 version keys
agfo_aim_test_ok($C::version_key('gpt-5.6-sol') < $C::version_key('gpt-5.7') && $C::version_key('gpt-5.9') < $C::version_key('gpt-5.10'), 'C1 5.6 < 5.7 and 5.9 < 5.10');
agfo_aim_test_ok(abs($C::version_key('claude-opus-4-5-20251101') - 4.05) < 1e-9 && $C::version_key('gpt-5-2025-08-07') == 5.0, 'C1 dates never read as versions');

// C2 newest first without release data: new family on top
$rows = $C::sort_newest(AGFO_AIM_Ajax_Data::models_for_provider('openai'));
agfo_aim_test_ok(strpos($rows[0]['id'], 'gpt-5.7') === 0 && !empty($rows[0]['is_new']), 'C2 gpt-5.7 on top and flagged new');
$o4 = array_values(array_filter($rows, function ($r) { return $r['id'] === 'o4-mini'; }));
agfo_aim_test_ok(!$o4 || empty($o4[0]['is_new']), 'C2 o-series not flagged new next to gpt-5.7');

// C3 release data from provider wins
$C::capture_meta('openai', [['id' => 'gpt-5.6-luna', 'created' => time() - 3 * 86400], ['id' => 'gpt-4o', 'created' => 1715000000]]);
agfo_aim_test_ok($C::release_ts('openai', 'gpt-5.6-luna') > time() - 4 * 86400, 'C3 created timestamp captured');
agfo_aim_test_ok($C::release_ts('openai', 'gpt-5.4-2026-03-05') === gmmktime(0, 0, 0, 3, 5, 2026), 'C3 date in id parsed');
agfo_aim_test_ok($C::release_ts('gemini', 'models/antigravity-preview-05-2026') === gmmktime(0, 0, 0, 5, 1, 2026), 'C3 MM-YYYY parsed');

// C4 OpenRouter pricing captured per 1M
$C::capture_meta('openrouter', [['id' => 'google/gemini-2.5-flash', 'created' => 1750000000, 'pricing' => ['prompt' => '0.0000003', 'completion' => '0.0000025', 'image' => '0.039']]]);
$tp = $C::token_price('openrouter', 'google/gemini-2.5-flash');
agfo_aim_test_ok(abs($tp['in'] - 0.3) < 1e-6 && abs($tp['out'] - 2.5) < 1e-6 && $tp['source'] === 'Sağlayıcı API', 'C4 OpenRouter prices normalised');
agfo_aim_test_ok($C::image_price('openrouter', 'google/gemini-2.5-flash')['price'] == 0.039, 'C4 per-image price captured');

// C5 benchmark quality uses the longest key
$q = $C::quality('openai', 'gpt-5.4-nano-2026-03-17', 99);
agfo_aim_test_ok($q['source'] === 'benchmark' && $q['key'] === 'gpt-5.4-nano' && $q['score'] < $C::quality('openai', 'gpt-5', 0)['score'], 'C5 nano does not inherit gpt-5 score');
agfo_aim_test_ok($C::quality('openai', 'totally-unknown-model', 90) === ['score' => 82, 'source' => 'estimate', 'key' => ''], 'C5 unknown model gets penalised estimate');

// C6 translation board
$tb = $C::translation_board(85);
agfo_aim_test_ok($tb['eligible'] > 0 && $tb['picks']['value'] && $tb['picks']['quality'] && $tb['picks']['cheapest'], 'C6 three picks produced');
agfo_aim_test_ok($tb['picks']['cheapest']['cost_1k_words'] <= $tb['picks']['value']['cost_1k_words'] && $tb['picks']['quality']['quality'] >= $tb['picks']['value']['quality'], 'C6 picks are consistent');
$ids = array_map(function ($r) { return $r['provider'] . '|' . $r['id']; }, $tb['rows']);
agfo_aim_test_ok(!in_array('openai|gpt-5-mini-2025-08-07', $ids, true) && count($ids) === count(array_unique($ids)), 'C6 dated duplicates collapsed');
agfo_aim_test_ok(!array_filter($tb['rows'], function ($r) { return preg_match('/codex|image|tts|embed/', $r['id']); }), 'C6 coding/media models excluded');
$all_eligible_ok = true; foreach ($tb['rows'] as $r) { if ($r['eligible'] && ($r['quality'] < 85 || $r['cost_1k_words'] === null)) $all_eligible_ok = false; }
agfo_aim_test_ok($all_eligible_ok, 'C6 eligibility respects threshold and price');

// C7 translation routing
$cfg = agfo_get_translation_config();
agfo_aim_test_ok($cfg['code'] === 'openai' && $cfg['model'] === 'gpt-5.6-sol' && $cfg['capability'] === 'text_translate', 'C7 default translation config = default chat model');
$_POST = ['provider' => 'deepseek', 'model' => 'deepseek-v4-pro'];
$routing = agfo_get_capability_routing(); $routing['text_translate'] = ['provider' => 'deepseek', 'model' => 'deepseek-v4-pro']; agfo_save_capability_routing($routing);
$cfg = agfo_get_translation_config();
agfo_aim_test_ok($cfg['code'] === 'deepseek' && $cfg['model'] === 'deepseek-v4-pro' && strpos($cfg['chat_url'], 'api.deepseek.com') !== false, 'C7 routed translation config');
agfo_aim_test_ok(agfo_get_priority_api_key()['model'] === 'gpt-5.6-sol', 'C7 default chat untouched by translation route');

// C8 image board
$O['agfo_ai_pricing_rates'] = ['fal' => ['fal-ai/flux/dev' => ['per_image' => 0.025]], 'openai' => ['gpt-image-2' => ['per_image' => 0.04]]];
$ib = $C::image_board();
agfo_aim_test_ok($ib['rows'][0]['has_key'] && $ib['rows'][0]['tier'] === 'A', 'C8 keyed A-tier first');
agfo_aim_test_ok($ib['picks']['cheapest']['id'] === 'fal-ai/flux/dev' && $ib['picks']['value']['id'] === 'gpt-image-2', 'C8 cheapest and value picks use admin prices');

echo "\n$pass pass / $fail fail\n";
exit($fail ? 1 : 0);
