<?php
/**
 * AGFO AI Manager 17.0.0 — isolated request-guard regression tests.
 * Run from the plugin root: php tests/request-guard-tests.php
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
$pass = 0; $fail = 0;
if (!function_exists('agfo_aim_test_ok')) { function agfo_aim_test_ok($cond, $name) { global $pass, $fail; if ($cond) { $pass++; echo "PASS $name\n"; } else { $fail++; echo "FAIL $name\n"; } } }
if (!function_exists('agfo_aim_test_body')) { function agfo_aim_test_body($r) { return json_decode(wp_remote_retrieve_body($r), true); } }
$O = &$GLOBALS['O'];
$O['agfo_openai_api_key'] = 'sk-test-xxxxxxxxxxxxxxxxxxxx';
$O['agfo_selected_provider'] = 'openai';
$O['agfo_models_openai'] = [['id' => 'gpt-5.6-sol'], ['id' => 'gpt-5.4-pro-2026-03-05'], ['id' => 'gpt-5-mini'], ['id' => 'gpt-4.1'], ['id' => 'text-embedding-3-large']];
$O['agfo_models_gemini'] = [['id' => 'gemini-old'], ['id' => 'gemini-2.5-flash']];
$OA = 'https://api.openai.com/v1/chat/completions';
$H = ['Authorization' => 'Bearer x', 'Content-Type' => 'application/json'];

// T1: future OpenAI model + temperature via direct wp_remote_post (dependent plugin) — stripped pre-flight
$GLOBALS['SENT'] = [];
$r = wp_remote_post($OA, ['headers' => $H, 'body' => json_encode(['model' => 'gpt-5.6-sol', 'messages' => [['role' => 'user', 'content' => 'hi']], 'temperature' => 0.7, 'top_p' => 0.9, 'max_completion_tokens' => 50])]);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200, 'T1 future gpt-5.6 + temperature succeeds');
agfo_aim_test_ok(count($GLOBALS['SENT']) === 1 && !isset($GLOBALS['SENT'][0]['body']['temperature']) && !isset($GLOBALS['SENT'][0]['body']['top_p']), 'T1 temperature/top_p stripped before first send (no wasted call)');

// T2: brand-new family gpt-7-x unknown -> also stripped
$GLOBALS['SENT'] = [];
$r = wp_remote_post($OA, ['headers' => $H, 'body' => json_encode(['model' => 'gpt-7-nova', 'messages' => [['role' => 'user', 'content' => 'hi']], 'temperature' => 0.3])]);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200 && count($GLOBALS['SENT']) === 1, 'T2 unknown future family protected deny-by-default');

// T3: gpt-4.1 keeps temperature
$GLOBALS['SENT'] = [];
$r = wp_remote_post($OA, ['headers' => $H, 'body' => json_encode(['model' => 'gpt-4.1', 'messages' => [['role' => 'user', 'content' => 'hi']], 'temperature' => 0.3])]);
agfo_aim_test_ok(($GLOBALS['SENT'][0]['body']['temperature'] ?? null) === 0.3, 'T3 classic gpt-4.1 keeps temperature');

// T4: learning — groq model rejects logit_bias: same call repaired, next call pre-stripped
$GLOBALS['SENT'] = [];
$G = 'https://api.groq.com/openai/v1/chat/completions';
$r = wp_remote_post($G, ['headers' => $H, 'body' => json_encode(['model' => 'llama-x', 'messages' => [['role' => 'user', 'content' => 'hi']], 'logit_bias' => ['1' => 2]])]);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200 && count($GLOBALS['SENT']) === 2, 'T4 first refusal repaired inside the same call');
$GLOBALS['SENT'] = [];
$r = wp_remote_post($G, ['headers' => $H, 'body' => json_encode(['model' => 'llama-x', 'messages' => [['role' => 'user', 'content' => 'hi']], 'logit_bias' => ['1' => 2]])]);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200 && count($GLOBALS['SENT']) === 1, 'T4 learned: second call stripped pre-flight');

// T5: responses-only model via chat body -> bridged transparently
$GLOBALS['SENT'] = [];
$r = wp_remote_post($OA, ['headers' => $H, 'body' => json_encode(['model' => 'gpt-5.4-pro-2026-03-05', 'messages' => [['role' => 'system', 'content' => 'Be brief'], ['role' => 'user', 'content' => 'hi']], 'temperature' => 0.5, 'max_tokens' => 100, 'reasoning_effort' => 'low'])]);
$b = agfo_aim_test_body($r);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200, 'T5 pro model returns 200');
agfo_aim_test_ok(strpos($b['choices'][0]['message']['content'] ?? '', 'OK responses gpt-5.4-pro') === 0, 'T5 answer in chat.completions shape');
agfo_aim_test_ok(strpos($b['choices'][0]['message']['content'], 'instr=Be brief') !== false && strpos($b['choices'][0]['message']['content'], 'max=256') !== false && strpos($b['choices'][0]['message']['content'], 'eff=low') !== false, 'T5 system->instructions, max_output_tokens floor, reasoning effort mapped');
agfo_aim_test_ok(count($GLOBALS['SENT']) === 1 && strpos($GLOBALS['SENT'][0]['url'], '/v1/responses') !== false, 'T5 known pro model goes straight to /v1/responses');
agfo_aim_test_ok(($b['usage']['total_tokens'] ?? 0) === 11, 'T5 usage mapped');

// T6: unknown model that provider says is responses-only (learned from 404)
$GLOBALS['SENT'] = [];
$r = wp_remote_post($OA, ['headers' => $H, 'body' => json_encode(['model' => 'gpt-5.5-codexlike', 'messages' => [['role' => 'user', 'content' => 'hi']]])]);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200, 'T6 codex model bridged');

// T7: model_not_found -> fallback to a working model, learned
$GLOBALS['SENT'] = [];
$r = wp_remote_post($OA, ['headers' => $H, 'body' => json_encode(['model' => 'ghost-model', 'messages' => [['role' => 'user', 'content' => 'hi']]])]);
$b = agfo_aim_test_body($r);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200, 'T7 unavailable model recovered via fallback');
agfo_aim_test_ok(AGFO_AIM_Request_Guard::model_route('openai', 'ghost-model') === 'unavailable', 'T7 unavailable learned');
$GLOBALS['SENT'] = [];
$r = wp_remote_post($OA, ['headers' => $H, 'body' => json_encode(['model' => 'ghost-model', 'messages' => [['role' => 'user', 'content' => 'hi']]])]);
agfo_aim_test_ok(count($GLOBALS['SENT']) === 1 && $GLOBALS['SENT'][0]['body']['model'] !== 'ghost-model', 'T7 second call swapped pre-flight');

// T8: fallback disabled -> error passes through
$O['agfo_aim_model_fallback_enabled'] = 0;
$r = wp_remote_post($OA, ['headers' => $H, 'body' => json_encode(['model' => 'ghost-model', 'messages' => [['role' => 'user', 'content' => 'hi']]])]);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 404, 'T8 fallback can be switched off');
$O['agfo_aim_model_fallback_enabled'] = 1;

// T9: raw probe header bypasses everything
$GLOBALS['SENT'] = [];
$r = wp_remote_post($OA, ['headers' => $H + ['X-AGFO-Raw-Probe' => '1'], 'body' => json_encode(['model' => 'gpt-5.6-sol', 'messages' => [['role' => 'user', 'content' => 'hi']], 'temperature' => 0.2])]);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 400 && isset($GLOBALS['SENT'][0]['body']['temperature']), 'T9 probes stay genuine');

// T10: empty JSON objects survive ({} not [])
$GLOBALS['SENT'] = [];
$raw = '{"model":"gpt-5-mini","messages":[{"role":"user","content":"x"}],"temperature":0.4,"tools":[{"type":"function","function":{"name":"f","parameters":{"type":"object","properties":{}}}}]}';
$r = wp_remote_post($OA, ['headers' => $H, 'body' => $raw]);
agfo_aim_test_ok(strpos($GLOBALS['SENT'][0]['raw'], '"properties":{}') !== false && strpos($GLOBALS['SENT'][0]['raw'], 'temperature') === false, 'T10 tool schema {} preserved while temperature removed');

// T11: unchanged body is not rewritten byte-wise
$GLOBALS['SENT'] = [];
$raw = '{"model":"gpt-4.1","messages":[{"role":"user","content":"x"}],"temperature":0.4, "metadata":{}}';
wp_remote_post($OA, ['headers' => $H, 'body' => $raw]);
agfo_aim_test_ok($GLOBALS['SENT'][0]['raw'] === $raw, 'T11 untouched body sent byte-identical');

// T12: Claude temperature + top_p
$GLOBALS['SENT'] = [];
$r = wp_remote_post('https://api.anthropic.com/v1/messages', ['headers' => $H, 'body' => json_encode(['model' => 'claude-opus-4-1', 'max_tokens' => 10, 'messages' => [['role' => 'user', 'content' => 'x']], 'temperature' => 0.3, 'top_p' => 0.9])]);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200 && count($GLOBALS['SENT']) === 1 && !isset($GLOBALS['SENT'][0]['body']['top_p']) && isset($GLOBALS['SENT'][0]['body']['temperature']), 'T12 Claude keeps temperature, drops top_p pre-flight');

// T13: Gemini unknown field learned and repaired
$GLOBALS['SENT'] = [];
$GU = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=AIzaXXXXXXXXXXXXXXXXXXXXXXXX';
$r = wp_remote_post($GU, ['headers' => $H, 'body' => json_encode(['contents' => [['parts' => [['text' => 'x']]]], 'generationConfig' => ['temperature' => 0.2, 'topK' => 4]])]);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200 && !isset($GLOBALS['SENT'][1]['body']['generationConfig']['topK']) && isset($GLOBALS['SENT'][1]['body']['generationConfig']['temperature']), 'T13 Gemini generationConfig.topK repaired');

// T14: Gemini model not found -> fallback rewrites URL
$GLOBALS['SENT'] = [];
$GO = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-old:generateContent?key=AIzaXXXXXXXXXXXXXXXXXXXXXXXX';
$r = wp_remote_post($GO, ['headers' => $H, 'body' => json_encode(['contents' => [['parts' => [['text' => 'x']]]]])]);
$b = agfo_aim_test_body($r);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200 && strpos($b['candidates'][0]['content']['parts'][0]['text'], 'gemini-2.5-flash') !== false, 'T14 Gemini unavailable model -> fallback URL');
agfo_aim_test_ok(!isset(end($GLOBALS['SENT'])['body']['__agfo_model']), 'T14 internal marker never reaches provider');

// T15: max_tokens refusal converted
$GLOBALS['SENT'] = [];
$r = wp_remote_post($OA, ['headers' => $H, 'body' => json_encode(['model' => 'gpt-5-mini', 'messages' => [['role' => 'user', 'content' => 'x']], 'max_tokens' => 20])]);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200 && isset(end($GLOBALS['SENT'])['body']['max_completion_tokens']), 'T15 max_tokens converted to max_completion_tokens');

// T16: reasoning_effort refused by gpt-4.1 repaired
$GLOBALS['SENT'] = [];
$r = wp_remote_post($OA, ['headers' => $H, 'body' => json_encode(['model' => 'gpt-4.1', 'messages' => [['role' => 'user', 'content' => 'x']], 'reasoning_effort' => 'low'])]);
agfo_aim_test_ok(wp_remote_retrieve_response_code($r) === 200, 'T16 reasoning_effort refusal repaired');

// T17: agfo_api_post end-to-end with future model + temperature
$GLOBALS['SENT'] = [];
$res = agfo_api_post($OA, $H, json_encode(['model' => 'gpt-5.6-sol', 'messages' => [['role' => 'user', 'content' => 'x']], 'temperature' => 0.9, 'max_tokens' => 30]), ['provider_code' => 'openai', 'model' => 'gpt-5.6-sol']);
agfo_aim_test_ok(($res['http_code'] ?? 0) === 200 && count($GLOBALS['SENT']) === 1, 'T17 agfo_api_post future model single clean call');

// T18: agfo_get_priority_api_key never returns unavailable / non-chat model
$O['agfo_global_preferred_model'] = 'text-embedding-3-large';
$cfg = agfo_get_priority_api_key();
agfo_aim_test_ok($cfg['model'] !== 'text-embedding-3-large' && $cfg['model_fallback_from'] === 'text-embedding-3-large', 'T18 non-chat global model replaced for dependent plugins');
$O['agfo_global_preferred_model'] = 'gpt-5.4-pro-2026-03-05';
$cfg = agfo_get_priority_api_key();
agfo_aim_test_ok($cfg['model'] === 'gpt-5.4-pro-2026-03-05' && $cfg['transport_route'] === 'responses_bridge' && $cfg['supports_temperature'] === false, 'T18 pro model kept, flagged responses_bridge, no temperature');
$O['agfo_global_preferred_model'] = 'gpt-5.6-sol';
$cfg = agfo_get_priority_api_key();
agfo_aim_test_ok($cfg['supports_temperature'] === false && $cfg['sampling_policy'] === 'provider_default', 'T18 dependent plugins told not to send temperature');

// T19: temperature status API
agfo_aim_test_ok(agfo_model_temperature_status('openai', 'gpt-6-whatever') === 'unsupported', 'T19 status unsupported for future family');
agfo_aim_test_ok(agfo_model_temperature_status('gpt-5.6-sol') !== '', 'T19 single-arg legacy signature still works');

// T20: capabilities effective contract
$caps = agfo_get_model_capabilities('openai', 'gpt-5.4-pro-2026-03-05');
agfo_aim_test_ok($caps['supports_chat'] === true && $caps['transport_route'] === 'responses_bridge', 'T20 pro model chat-capable via bridge');
$caps = agfo_get_model_capabilities('openai', 'ghost-model');
agfo_aim_test_ok($caps['transport_route'] === 'unavailable' && $caps['supports_chat'] === false, 'T20 unavailable model flagged');

// T21: chat_to_responses with image parts and json_schema
$rb = AGFO_AIM_Request_Guard::chat_to_responses(['model' => 'o3-pro', 'messages' => [['role' => 'user', 'content' => [['type' => 'text', 'text' => 'a'], ['type' => 'image_url', 'image_url' => ['url' => 'https://x/y.png']]]], ['role' => 'assistant', 'content' => 'prev']], 'response_format' => ['type' => 'json_schema', 'json_schema' => ['name' => 's', 'schema' => ['type' => 'object']]]]);
agfo_aim_test_ok($rb['input'][0]['content'][1]['type'] === 'input_image' && $rb['text']['format']['type'] === 'json_schema' && $rb['input'][1]['content'] === 'prev', 'T21 multimodal + json_schema translation');

// T22: tools / stream are not bridged (left as-is)
agfo_aim_test_ok(!AGFO_AIM_Request_Guard::bridgeable(['messages' => [['role' => 'user', 'content' => 'x']], 'stream' => true]) && !AGFO_AIM_Request_Guard::bridgeable(['messages' => [['role' => 'user', 'content' => 'x']], 'tools' => [1]]), 'T22 stream/tools excluded from bridge');

// T23: non-managed host untouched
$GLOBALS['SENT'] = [];
$args = apply_filters('http_request_args', ['body' => '{"model":"gpt-5","temperature":1}'], 'https://example.com/v1/chat/completions');
agfo_aim_test_ok($args['body'] === '{"model":"gpt-5","temperature":1}', 'T23 non-AI hosts untouched');

// T24: data.json cache: write then read returns new data without disk read
$d = agfo_read_data_json(); $d['__t'] = 1; agfo_write_data_json($d);
agfo_aim_test_ok((agfo_read_data_json()['__t'] ?? 0) === 1, 'T24 data cache invalidated on write');

// T25: rules cap & reset
AGFO_AIM_Request_Guard::reset();
agfo_aim_test_ok(AGFO_AIM_Request_Guard::learned_route('openai', 'ghost-model') === '' , 'T25 reset clears learned rules');

// T26: out-of-range value is not learned as an unsupported parameter
$o = AGFO_AIM_Request_Guard::learn('openai', 'gpt-4.1', 400, json_encode(['error' => ['message' => 'max_tokens is too large: 90000. This model supports at most 32768 completion tokens.', 'param' => 'max_tokens', 'code' => 'invalid_value']]), ['model' => 'gpt-4.1', 'max_tokens' => 90000]);
agfo_aim_test_ok($o['action'] === 'none' && !AGFO_AIM_Request_Guard::learned_param('openai', 'gpt-4.1', 'max_tokens'), 'T26 range error not learned as refusal');

// T27: pro model answered "not a chat model" is classified as responses, not not_chat
AGFO_AIM_Request_Guard::remember_route('openai', 'gpt-5.2-pro', 'not_chat', 'This is not a chat model');
agfo_aim_test_ok(AGFO_AIM_Request_Guard::model_route('openai', 'gpt-5.2-pro') === 'responses', 'T27 pro model stays on Responses bridge');
agfo_aim_test_ok(AGFO_AIM_Request_Guard::model_route('groq', 'llama-3.3-70b-instruct') === 'chat' && AGFO_AIM_Request_Guard::model_route('openai', 'gpt-3.5-turbo-instruct') === 'not_chat', 'T27 instruct rule is OpenAI-only');

// T28: stale probe false negative (length stop) corrected
agfo_save_model_capabilities('openai', 'gpt-5.1-x', ['supports_chat' => false, 'compatibility_notes' => 'Could not finish the message because max_tokens or model output limit was reached.']);
agfo_aim_test_ok(agfo_get_model_capabilities('openai', 'gpt-5.1-x')['supports_chat'] === true, 'T28 stale chat false-negative corrected');

echo "\n$pass pass / $fail fail\n";
exit($fail ? 1 : 0);
