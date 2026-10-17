<?php
if (!defined('ABSPATH')) exit;

class AGFO_AIM_Ajax_Data {

    // CHANGED 16.2.0: async job katmani icin opsiyonel asama bildirimi; null iken davranis birebir eski.
    public static $dispatch_progress = null;

    /**
     * CHANGED 16.2.0: chat_test()'in yonlendirme blogunun public sarmalayicisi.
     * Async job worker'i buradan cagirir; chat_test() akisina DOKUNULMADI.
     */
    public static function chat_dispatch(string $provider_code, string $model, array $messages, string $system_prompt, float $temperature, int $max_tokens, ?callable $progress = null): array {
        $providers = agfo_api_registry();
        if (!isset($providers[$provider_code])) return ['error' => 'Geçersiz sağlayıcı: ' . $provider_code];
        $api_key = agfo_get_api_key($provider_code);
        if (empty($api_key)) return ['error' => 'API anahtarı bulunamadı'];
        $provider = $providers[$provider_code];
        $headers  = ['Content-Type' => 'application/json'];
        foreach (($provider['auth'] ?? []) as $hk => $hv) $headers[$hk] = str_replace('{key}', $api_key, $hv);

        self::$dispatch_progress = $progress;
        $start_time = microtime(true);
        try {
            if ($provider_code === 'gemini') {
                $result = self::chat_gemini($api_key, $model, $messages, $system_prompt, $temperature, $max_tokens);
            } elseif ($provider_code === 'claude') {
                $result = self::chat_claude($headers, $provider, $model, $messages, $system_prompt, $temperature, $max_tokens);
            } else {
                $result = self::chat_openai_compat($headers, $provider, $model, $messages, $system_prompt, $temperature, $max_tokens, $provider_code);
            }
        } finally {
            self::$dispatch_progress = null;
        }
        if (!isset($result['error'])) $result['elapsed_ms'] = (int) round((microtime(true) - $start_time) * 1000);
        return $result;
    }

    public static function register_hooks(): void {
        add_action('wp_ajax_agfo_refresh_provider_models', [__CLASS__, 'refresh_provider']);
        add_action('wp_ajax_agfo_refresh_all_models',      [__CLASS__, 'refresh_all']);
        add_action('wp_ajax_agfo_clear_model_cache',       [__CLASS__, 'clear_cache']);
        add_action('wp_ajax_agfo_download_models',         [__CLASS__, 'download_models']);
        add_action('wp_ajax_agfo_qs_get_data',             [__CLASS__, 'qs_get_data']);
        add_action('wp_ajax_agfo_qs_get_models_only',      [__CLASS__, 'qs_get_models_only']);
        add_action('wp_ajax_agfo_qs_get_compatible_models', [__CLASS__, 'qs_get_compatible_models']);
        add_action('wp_ajax_agfo_probe_model_capabilities', [__CLASS__, 'probe_model_capabilities']);
        add_action('wp_ajax_agfo_qs_save',                 [__CLASS__, 'qs_save']);
        add_action('wp_ajax_agfo_get_model_score',         [__CLASS__, 'get_model_score']);
        add_action('wp_ajax_agfo_chat_test',               [__CLASS__, 'chat_test']);
    }

    /* ════════════════════════════════════════════════════
     * MODEL YENİLEME
     * ════════════════════════════════════════════════════ */

    public static function refresh_models_for_provider(string $provider_code): array {
        $providers = agfo_api_registry();
        if (!isset($providers[$provider_code])) {
            return ['error' => 'Geçersiz sağlayıcı'];
        }

        $provider = $providers[$provider_code];
        if (($provider['type'] ?? '') !== 'llm' || empty($provider['url'])) {
            return ['error' => 'Bu sağlayıcı LLM tipi değil'];
        }

        $key = agfo_get_api_key($provider_code);
        if (empty($key)) {
            return ['error' => 'API anahtarı tanımlanmamış'];
        }

        $url     = str_replace('{key}', trim($key), $provider['url']);
        // CHANGED 17.0.0: probes bypass the request guard so their evidence stays genuine.
        $headers = ['Content-Type' => 'application/json', 'Accept' => 'application/json', 'X-AGFO-Raw-Probe' => '1'];
        foreach (($provider['auth'] ?? []) as $hk => $hv) {
            $headers[$hk] = str_replace('{key}', trim($key), $hv);
        }

        $response = wp_remote_get($url, [
            'timeout'   => 30,
            'sslverify' => true,
            'headers'   => $headers,
        ]);

        if (is_wp_error($response)) {
            return ['error' => 'Bağlantı hatası: ' . $response->get_error_message()];
        }

        $http_code = (int) wp_remote_retrieve_response_code($response);
        $body      = (string) wp_remote_retrieve_body($response);

        if ($http_code < 200 || $http_code >= 300) {
            return ['error' => "HTTP {$http_code} | " . substr($body, 0, 200)];
        }

        $data = json_decode($body, true);
        if (empty($data)) {
            return ['error' => 'JSON parse hatası | ' . substr($body, 0, 200)];
        }

        $raw_list = [];
        if (isset($data['data']) && is_array($data['data'])) {
            $raw_list = $data['data'];
        } elseif (isset($data['models']) && is_array($data['models'])) {
            $raw_list = $data['models'];
        } elseif (is_array($data)) {
            $raw_list = $data;
        }

        $model_list = [];
        foreach ($raw_list as $item) {
            if (is_array($item)) {
                $id = $item['id'] ?? $item['name'] ?? $item['model'] ?? null;
                if ($id !== null && $id !== '') {
                    $model_list[] = (string) $id;
                }
            } elseif (is_string($item) && $item !== '') {
                $model_list[] = $item;
            }
        }

        if (empty($model_list)) {
            return ['error' => 'Model bulunamadı | ' . substr($body, 0, 200)];
        }

        // NEW 17.1.0: keep release time, prices and modalities the provider returned.
        if (class_exists('AGFO_AIM_Model_Catalog')) {
            AGFO_AIM_Model_Catalog::capture_meta($provider_code, $raw_list);
        }

        return self::save_model_list($provider_code, array_values(array_unique($model_list)));
    }

    private static function save_model_list(string $provider_code, array $model_list): array {
        $raw_count      = count($model_list);
        $filtered       = agfo_clean_model_list($model_list);
        sort($filtered);
        $filtered_count = $raw_count - count($filtered);
        $final_count    = count($filtered);

        update_option("agfo_models_{$provider_code}",                $filtered);
        update_option("agfo_models_{$provider_code}_updated",        current_time('mysql'));
        update_option("agfo_models_{$provider_code}_raw_count",      $raw_count);
        update_option("agfo_models_{$provider_code}_filtered_count", $filtered_count);

        $all_models                 = agfo_read_data_section('models');
        $all_models[$provider_code] = $filtered;
        agfo_write_data_section('models', $all_models);

        return [
            'success'        => true,
            'provider'       => $provider_code,
            'raw_count'      => $raw_count,
            'filtered_count' => $filtered_count,
            'final_count'    => $final_count,
            'models'         => $filtered,
        ];
    }

    /* ════════════════════════════════════════════════════
     * AJAX HANDLERS – Model Yönetimi
     * ════════════════════════════════════════════════════ */

    public static function refresh_provider(): void {
        if (!current_user_can('manage_options')) wp_send_json_error('Yetki yok');
        check_ajax_referer('agfo_ajax_nonce', 'nonce');
        $provider = sanitize_text_field($_POST['provider'] ?? '');
        if (empty($provider)) wp_send_json_error('Sağlayıcı belirtilmedi');
        $result = self::refresh_models_for_provider($provider);
        isset($result['error'])
            ? wp_send_json_error($result['error'])
            : wp_send_json_success($result);
    }

    public static function refresh_all(): void {
        if (!current_user_can('manage_options')) wp_send_json_error('Yetki yok');
        check_ajax_referer('agfo_ajax_nonce', 'nonce');
        $results = [];
        foreach (agfo_api_registry() as $code => $info) {
            if (($info['type'] ?? '') !== 'llm') continue;
            if (empty(agfo_get_api_key($code))) {
                $results[$code] = ['success' => false, 'error' => 'API key yok'];
                continue;
            }
            $results[$code] = self::refresh_models_for_provider($code);
        }
        wp_send_json_success($results);
    }

    public static function clear_cache(): void {
        if (!current_user_can('manage_options')) wp_send_json_error('Yetki yok');
        check_ajax_referer('agfo_ajax_nonce', 'nonce');
        foreach (array_keys(agfo_api_registry()) as $code) {
            delete_option("agfo_models_{$code}");
            delete_option("agfo_models_{$code}_updated");
            delete_option("agfo_models_{$code}_raw_count");
            delete_option("agfo_models_{$code}_filtered_count");
        }
        agfo_write_data_section('models', []);
        wp_send_json_success('Önbellek temizlendi');
    }

    public static function download_models(): void {
        if (!current_user_can('manage_options')) {
            wp_send_json(['ok' => false, 'error' => 'Yetki yok']);
        }
        // CHANGED 16.6.0: Nonce eklendi. Bu uc model listesini yeniler ve disari
        // API cagrisi yapar; nonce olmadan CSRF ile tetiklenebiliyordu.
        check_ajax_referer('agfo_ajax_nonce', 'nonce');
        $code = sanitize_text_field($_GET['code'] ?? '');
        if (empty($code) || !isset(agfo_api_registry()[$code])) {
            wp_send_json(['ok' => false, 'error' => 'Geçersiz sağlayıcı']);
        }
        $result = self::refresh_models_for_provider($code);
        if (isset($result['error'])) {
            wp_send_json(['ok' => false, 'error' => $result['error']]);
        }
        wp_send_json([
            'ok'      => true,
            'message' => "{$result['final_count']}/{$result['raw_count']} model kaydedildi ({$result['filtered_count']} filtrelendi)",
        ]);
    }

    /* ════════════════════════════════════════════════════
     * AJAX HANDLERS – Quick Switch
     * ════════════════════════════════════════════════════ */

    public static function qs_get_data(): void {
        if (!current_user_can('manage_options')) wp_send_json_error();
        check_ajax_referer('agfo_ajax_nonce', 'nonce'); // CHANGED 16.6.0: eksik nonce eklendi.
        $provider = (string) get_option('agfo_selected_provider', 'openai');
        wp_send_json_success([
            'provider'      => $provider,
            'current_model' => (string) get_option('agfo_global_preferred_model', ''),
            'reasoning'     => (int) get_option('agfo_reasoning_mode', 0),
            // CHANGED: Quick Switch now receives OpenRouter Fusion state for compact mode/profile controls.
            'fusion'        => function_exists('agfo_openrouter_get_fusion_config') ? agfo_openrouter_get_fusion_config() : [],
            'all_models'    => self::get_models_for_provider($provider),
            'context_tags'  => agfo_read_context_tags(),
        ]);
    }

    public static function qs_get_models_only(): void {
        if (!current_user_can('manage_options')) wp_send_json_error();
        check_ajax_referer('agfo_ajax_nonce', 'nonce'); // CHANGED 16.6.0: eksik nonce eklendi.
        $provider  = sanitize_text_field($_POST['provider'] ?? '');
        $chat_only = !empty($_POST['chat_only']);
        $docx_only = !empty($_POST['docx_only']);
        wp_send_json_success(self::get_models_for_provider($provider, [
            'chat_only' => $chat_only,
            'docx_only' => $docx_only,
        ]));
    }

    public static function qs_get_compatible_models(): void {
        if (!current_user_can('manage_options')) wp_send_json_error();
        check_ajax_referer('agfo_ajax_nonce', 'nonce'); // CHANGED 16.6.0: eksik nonce eklendi.
        $provider = sanitize_text_field($_POST['provider'] ?? '');
        $mode     = sanitize_key($_POST['mode'] ?? 'chat');
        wp_send_json_success(self::get_models_for_provider($provider, [
            'chat_only' => ($mode === 'chat' || $mode === 'docx'),
            'docx_only' => ($mode === 'docx'),
        ]));
    }

    public static function probe_model_capabilities(): void {
        if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'Yetki yok']);
        check_ajax_referer('agfo_ajax_nonce', 'nonce');

        $provider = sanitize_key($_POST['provider'] ?? '');
        $model    = sanitize_text_field(wp_unslash($_POST['model'] ?? ''));

        if ($provider === '' || $model === '') {
            wp_send_json_error(['message' => 'Sağlayıcı ve model gerekli.']);
        }

        $result = self::run_capability_probe($provider, $model);
        if (!empty($result['error'])) {
            wp_send_json_error($result);
        }

        wp_send_json_success($result);
    }

    private static function run_capability_probe(string $provider_code, string $model): array {
        $provider_code = sanitize_key($provider_code);
        $model         = trim($model);
        $providers     = agfo_api_registry();

        if (!isset($providers[$provider_code])) {
            return ['error' => 'Geçersiz sağlayıcı.'];
        }

        $provider = $providers[$provider_code];
        $key      = agfo_get_api_key($provider_code);
        if (empty($key)) {
            return ['error' => 'API anahtarı tanımlanmamış.'];
        }

        if ($provider_code !== 'openai') {
            $defaults = function_exists('agfo_get_model_capabilities')
                ? agfo_get_model_capabilities($provider_code, $model)
                : [];
            $capabilities = array_merge($defaults, [
                'capability_source'    => 'live_probe_not_supported_for_provider',
                'probe_status'         => 'not_tested',
                'probed_at'            => current_time('mysql'),
                'compatibility_level'  => $defaults['compatibility_level'] ?? 'unknown',
                'compatibility_notes'  => array_merge($defaults['compatibility_notes'] ?? [], ['Canlı probe şu an yalnız OpenAI chat endpointi için uygulanır.']),
            ]);
            if (function_exists('agfo_save_model_capabilities')) {
                agfo_save_model_capabilities($provider_code, $model, $capabilities);
            }
            return [
                'provider'     => $provider_code,
                'model'        => $model,
                'capabilities' => $capabilities,
                'message'      => 'Bu sağlayıcı için canlı probe uygulanmadı; mevcut metadata JSON’a yazıldı.',
            ];
        }

        $headers = ['Content-Type' => 'application/json', 'Accept' => 'application/json'];
        foreach (($provider['auth'] ?? []) as $hk => $hv) {
            $headers[$hk] = str_replace('{key}', trim($key), $hv);
        }
        $url = (string)($provider['chat_url'] ?? '');
        if ($url === '') {
            return ['error' => 'Chat endpoint tanımlı değil.'];
        }

        $base_body = [
            'model'    => $model,
            'messages' => [
                ['role' => 'user', 'content' => 'Reply exactly: OK']
            ],
        ];
        // CHANGED 17.0.0: 8 tokens were spent on reasoning before any answer, so working reasoning
        // models were recorded as "chat ✗" ("max_tokens or model output limit was reached").
        $probe_reasoning = function_exists('agfo_openai_model_is_reasoning') && agfo_openai_model_is_reasoning($model);
        $probe_tokens    = $probe_reasoning ? 512 : 16;
        if (function_exists('agfo_uses_max_completion_tokens') && agfo_uses_max_completion_tokens($model)) {
            $base_body['max_completion_tokens'] = $probe_tokens;
        } else {
            $base_body['max_tokens'] = $probe_tokens;
        }
        if ($probe_reasoning) {
            $base_body['reasoning_effort'] = 'low';
        }

        $chat = self::probe_openai_chat_request($url, $headers, $base_body);
        // A length stop still proves the chat endpoint serves this model.
        if (empty($chat['ok']) && stripos((string) ($chat['error'] ?? ''), 'output limit') !== false) {
            $chat['ok'] = true;
        }

        $capabilities = function_exists('agfo_get_model_capabilities')
            ? agfo_get_model_capabilities($provider_code, $model)
            : [];

        $capabilities = array_merge($capabilities, [
            'provider'            => $provider_code,
            'id'                  => $model,
            'capability_source'   => 'live_probe',
            'probed_at'           => current_time('mysql'),
            'probe_status'        => 'completed',
            'probe_chat_http_code'=> (int)($chat['http_code'] ?? 0),
            'probe_chat_error'    => (string)($chat['error'] ?? ''),
        ]);

        if (!empty($chat['ok'])) {
            $capabilities['endpoint_type']        = 'chat';
            $capabilities['supports_chat']        = true;
            $capabilities['docx_allowed']         = true;
            $capabilities['compatibility_level']  = 'ok';
            $capabilities['compatibility_notes']  = ['Canlı chat probe başarılı.'];

            $temp_body = $base_body;
            $temp_body['temperature'] = 0.2;
            $temp = self::probe_openai_chat_request($url, $headers, $temp_body);

            $capabilities['probe_temperature_http_code'] = (int)($temp['http_code'] ?? 0);
            $capabilities['probe_temperature_error']     = (string)($temp['error'] ?? '');

            if (!empty($temp['ok'])) {
                $capabilities['supports_temperature'] = true;
                $capabilities['temperature_status']   = 'supported';
                $capabilities['compatibility_notes'][] = 'Canlı temperature probe başarılı.';
            } elseif (self::is_temperature_unsupported_error((string)($temp['error'] ?? ''))) {
                $capabilities['supports_temperature'] = false;
                $capabilities['temperature_status']   = 'unsupported';
                $capabilities['compatibility_notes'][] = 'Canlı temperature probe: model temperature parametresini reddetti.';
            } else {
                $capabilities['supports_temperature'] = true;
                $capabilities['temperature_status']   = 'unknown';
                $capabilities['compatibility_level']  = 'warn';
                $capabilities['compatibility_notes'][] = 'Temperature probe kesin sonuç vermedi; temperature geçici olarak destekleniyor varsayıldı.';
            }
        } else {
            $err = (string)($chat['error'] ?? '');
            $capabilities['supports_chat']        = false;
            $capabilities['docx_allowed']         = false;
            $capabilities['supports_temperature'] = false;
            $capabilities['temperature_status']   = 'unsupported';
            $capabilities['compatibility_level']  = 'warn';
            $capabilities['compatibility_notes']  = ['Canlı chat probe başarısız: ' . $err];
            $capabilities['endpoint_type']        = self::guess_endpoint_from_openai_error($err);
        }

        if (function_exists('agfo_save_model_capabilities')) {
            agfo_save_model_capabilities($provider_code, $model, $capabilities);
        }

        // NEW 17.0.0: feed probe evidence into the request guard so live traffic benefits at once.
        if (class_exists('AGFO_AIM_Request_Guard')) {
            if (!empty($chat['ok'])) {
                AGFO_AIM_Request_Guard::remember_route($provider_code, $model, 'chat');
                if (($capabilities['temperature_status'] ?? '') === 'unsupported') {
                    AGFO_AIM_Request_Guard::remember_param($provider_code, $model, 'temperature', 'live probe');
                }
            } else {
                $endpoint_guess = (string) ($capabilities['endpoint_type'] ?? '');
                if ($endpoint_guess === 'responses') {
                    AGFO_AIM_Request_Guard::remember_route($provider_code, $model, 'responses', (string) ($chat['error'] ?? ''));
                } elseif ($endpoint_guess === 'completions') {
                    AGFO_AIM_Request_Guard::remember_route($provider_code, $model, 'not_chat', (string) ($chat['error'] ?? ''));
                } elseif (in_array((int) ($chat['http_code'] ?? 0), [403, 404], true)) {
                    AGFO_AIM_Request_Guard::remember_route($provider_code, $model, 'unavailable', (string) ($chat['error'] ?? ''));
                }
            }
            $capabilities = agfo_get_model_capabilities($provider_code, $model);
        }

        return [
            'provider'     => $provider_code,
            'model'        => $model,
            'capabilities' => $capabilities,
            'message'      => 'Canlı capability diagnose tamamlandı ve data.json içine yazıldı.',
        ];
    }

    private static function probe_openai_chat_request(string $url, array $headers, array $body): array {
        $runner = function () use ($url, $headers, $body) {
            return wp_remote_post($url, [
                'timeout'   => 45,
                'sslverify' => true,
                'headers'   => $headers,
                'body'      => wp_json_encode($body),
            ]);
        };

        $response = function_exists('agfo_ai_manager_without_connector_guard')
            ? agfo_ai_manager_without_connector_guard($runner)
            : $runner();

        if (is_wp_error($response)) {
            return ['ok' => false, 'http_code' => 0, 'error' => $response->get_error_message()];
        }

        $http_code = (int) wp_remote_retrieve_response_code($response);
        $raw       = (string) wp_remote_retrieve_body($response);
        $data      = json_decode($raw, true);

        if ($http_code >= 200 && $http_code < 300) {
            return ['ok' => true, 'http_code' => $http_code, 'raw' => substr($raw, 0, 500)];
        }

        $err = '';
        if (isset($data['error']['message']) && is_string($data['error']['message'])) {
            $err = $data['error']['message'];
        } else {
            $err = 'HTTP ' . $http_code . ': ' . substr($raw, 0, 300);
        }

        return ['ok' => false, 'http_code' => $http_code, 'error' => $err];
    }

    private static function is_temperature_unsupported_error(string $message): bool {
        $m = strtolower($message);
        return strpos($m, 'temperature') !== false && (
            strpos($m, 'unsupported') !== false ||
            strpos($m, 'not support') !== false ||
            strpos($m, 'does not support') !== false ||
            strpos($m, 'invalid parameter') !== false ||
            strpos($m, 'unknown parameter') !== false
        );
    }

    private static function guess_endpoint_from_openai_error(string $message): string {
        $m = strtolower($message);
        if (strpos($m, 'not a chat model') !== false || strpos($m, 'v1/completions') !== false) {
            return 'completions';
        }
        if (strpos($m, 'responses') !== false) {
            return 'responses';
        }
        return 'not_chat';
    }

    public static function qs_save(): void {
        if (!current_user_can('manage_options')) wp_send_json_error();
        check_ajax_referer('agfo_ajax_nonce', 'nonce');
        // CHANGED 16.6.0: Saglayici kodu dogrulanmadan kaydediliyordu. Artik yalnizca
        // registry'de tanimli ve chat yapabilen ('llm') bir kod kabul edilir; gecersiz
        // deger gelirse mevcut secim korunur.
        $posted_provider = sanitize_key((string) ($_POST['provider'] ?? ''));
        $registry        = agfo_api_registry();
        if ($posted_provider !== ''
            && isset($registry[$posted_provider])
            && (($registry[$posted_provider]['type'] ?? 'llm') === 'llm')) {
            update_option('agfo_selected_provider', $posted_provider);
        }
        update_option('agfo_global_preferred_model', sanitize_text_field($_POST['model']    ?? ''));
        update_option('agfo_reasoning_mode',         (int) ($_POST['reasoning'] ?? 0));
        // CHANGED: Save compact Fusion controls from the Quick Switch modal without touching API keys.
        if (isset($_POST['fusion_mode'])) {
            $mode = sanitize_key((string) wp_unslash($_POST['fusion_mode']));
            if (in_array($mode, ['off', 'auto', 'force'], true)) {
                update_option('agfo_openrouter_fusion_mode', $mode);
            }
        }
        if (isset($_POST['fusion_profile'])) {
            $profile = sanitize_key((string) wp_unslash($_POST['fusion_profile']));
            $profiles = function_exists('agfo_openrouter_get_fusion_profiles') ? agfo_openrouter_get_fusion_profiles() : [];
            if (isset($profiles[$profile])) {
                update_option('agfo_openrouter_fusion_profile', $profile);
            }
        }
        wp_send_json_success();
    }

    public static function get_model_score(): void {
        if (!current_user_can('manage_options')) wp_send_json_error();
        // CHANGED 16.17.0: Benchmark tab is interactive; protect the existing score endpoint with the shared admin nonce.
        check_ajax_referer('agfo_ajax_nonce', 'nonce');
        $provider = sanitize_key((string) wp_unslash($_POST['provider'] ?? ''));
        $model    = sanitize_text_field(wp_unslash($_POST['model'] ?? ''));
        if (empty($provider) || empty($model)) {
            wp_send_json_error(['message' => 'Geçersiz parametreler']);
        }
        $score = agfo_calculate_combined_score($provider, $model);
        $score
            ? wp_send_json_success($score)
            : wp_send_json_error(['message' => 'Skor bulunamadı']);
    }

    /* ════════════════════════════════════════════════════
     * AJAX HANDLER – Chat Test
     * ════════════════════════════════════════════════════ */

    public static function chat_test(): void {
        if (!current_user_can('manage_options')) wp_send_json_error('Yetki yok');
        check_ajax_referer('agfo_ajax_nonce', 'nonce');

        $provider_code = sanitize_text_field($_POST['provider']   ?? '');
        $model         = sanitize_text_field($_POST['model']      ?? '');
        $system_prompt = sanitize_textarea_field($_POST['system'] ?? '');
        $temperature   = (float) ($_POST['temperature']           ?? 0.7);
        $max_tokens    = (int)   ($_POST['max_tokens']            ?? 1024);
        $messages_raw  = isset($_POST['messages']) ? stripslashes($_POST['messages']) : '[]';

        if (empty($provider_code) || empty($model)) {
            wp_send_json_error('Sağlayıcı ve model gerekli');
        }

        $providers = agfo_api_registry();
        if (!isset($providers[$provider_code])) {
            wp_send_json_error('Geçersiz sağlayıcı: ' . $provider_code);
        }

        $api_key = agfo_get_api_key($provider_code);
        if (empty($api_key)) {
            wp_send_json_error('API anahtarı bulunamadı');
        }

        $provider = $providers[$provider_code];
        $messages = json_decode($messages_raw, true);
        if (!is_array($messages)) $messages = [];

        // Auth headers
        $headers = ['Content-Type' => 'application/json'];
        foreach (($provider['auth'] ?? []) as $hk => $hv) {
            $headers[$hk] = str_replace('{key}', $api_key, $hv);
        }

        $start_time = microtime(true);

        if ($provider_code === 'gemini') {
            $result = self::chat_gemini($api_key, $model, $messages, $system_prompt, $temperature, $max_tokens);
        } elseif ($provider_code === 'claude') {
            $result = self::chat_claude($headers, $provider, $model, $messages, $system_prompt, $temperature, $max_tokens);
        } else {
            $result = self::chat_openai_compat($headers, $provider, $model, $messages, $system_prompt, $temperature, $max_tokens, $provider_code);
        }

        $elapsed = (int) round((microtime(true) - $start_time) * 1000);

        if (isset($result['error'])) {
            wp_send_json_error($result['error']);
        }

        $result['elapsed_ms'] = $elapsed;
        wp_send_json_success($result);
    }

    /* ════════════════════════════════════════════════════
     * CHAT – Provider Formatları
     * ════════════════════════════════════════════════════ */

    private static function chat_openai_compat(
        array $headers, array $provider, string $model,
        array $messages, string $system, float $temp,
        int $max_tokens, string $provider_code
    ): array {
        $msg_list = [];
        if (!empty($system)) {
            $msg_list[] = ['role' => 'system', 'content' => $system];
        }
        foreach ($messages as $m) {
            if (isset($m['role'], $m['content'])) {
                $msg_list[] = ['role' => $m['role'], 'content' => $m['content']];
            }
        }

        $body = ['model' => $model, 'messages' => $msg_list, 'temperature' => $temp];

        // CHANGED: OpenAI chat-latest/frontier models and OpenRouter-routed frontier models may reject max_tokens.
        if (($provider_code === 'openai' && agfo_uses_max_completion_tokens($model)) || in_array($provider_code, ['openrouter', 'minimax'], true)) {
            if ('minimax' === $provider_code) {
                $minimax_limit = false !== stripos($model, 'MiniMax-M3') ? 524288 : 204800;
                $body['max_completion_tokens'] = min($minimax_limit, max(1, $max_tokens));
            } else {
                $body['max_completion_tokens'] = $max_tokens;
            }
        } else {
            $body['max_tokens'] = $max_tokens;
        }
        if ('minimax' === $provider_code) {
            $body['temperature'] = max(0.0, min(2.0, $temp));
        }

        $chat_url = $provider['chat_url'] ?? '';
        // CHANGED: Chat test now uses the central AGFO transport gate to avoid WP AI Connector approval traps.
        // CHANGED 16.1.1: NVIDIA NIM kuyruklu; chat test'in sabit 60sn'i nvidia'da cURL 28 uretiyordu -> 150sn (poll butcesi de ayni degeri kullanir).
        $response = agfo_api_post($chat_url, $headers, wp_json_encode($body), [
            'provider_code' => $provider_code,
            'model'         => $model,
            'timeout'       => ($provider_code === 'nvidia') ? 150 : 60,
            'source'        => 'agfo_chat_test',
            'progress'      => self::$dispatch_progress, // CHANGED 16.2.0
        ]);

        if (isset($response['error'])) {
            return ['error' => $response['error']];
        }

        $code = (int) ($response['http_code'] ?? 0);
        $raw  = (string) ($response['body'] ?? '');
        $data = json_decode($raw, true);

        if ($code < 200 || $code >= 300) {
            $err = (isset($data['error']['message']) && is_string($data['error']['message']))
                ? $data['error']['message']
                : "HTTP {$code}: " . substr($raw, 0, 300);
            return ['error' => $err];
        }

        return [
            'content'           => (string) ($data['choices'][0]['message']['content'] ?? ''),
            'prompt_tokens'     => (int) ($data['usage']['prompt_tokens']     ?? 0),
            'completion_tokens' => (int) ($data['usage']['completion_tokens'] ?? 0),
            'total_tokens'      => (int) ($data['usage']['total_tokens']      ?? 0),
            'model'             => (string) ($data['model'] ?? $model),
        ];
    }

    private static function chat_claude(
        array $headers, array $provider, string $model,
        array $messages, string $system, float $temp, int $max_tokens
    ): array {
        $msg_list = [];
        foreach ($messages as $m) {
            if (isset($m['role'], $m['content'])) {
                $msg_list[] = ['role' => $m['role'], 'content' => $m['content']];
            }
        }

        $body = [
            'model'       => $model,
            'max_tokens'  => $max_tokens,
            'temperature' => $temp,
            'messages'    => $msg_list,
        ];
        if (!empty($system)) $body['system'] = $system;

        // CHANGED: Chat test now uses the central AGFO transport gate to avoid WP AI Connector approval traps.
        $response = agfo_api_post($provider['chat_url'] ?? '', $headers, wp_json_encode($body), [
            'provider_code' => 'claude',
            'model'         => $model,
            'timeout'       => 60,
            'source'        => 'agfo_chat_test',
            'progress'      => self::$dispatch_progress, // CHANGED 16.2.0
        ]);

        if (isset($response['error'])) return ['error' => $response['error']];

        $code = (int) ($response['http_code'] ?? 0);
        $raw  = (string) ($response['body'] ?? '');
        $data = json_decode($raw, true);

        if ($code < 200 || $code >= 300) {
            $err = (isset($data['error']['message']) && is_string($data['error']['message']))
                ? $data['error']['message']
                : "HTTP {$code}: " . substr($raw, 0, 300);
            return ['error' => $err];
        }

        $input_t  = (int) ($data['usage']['input_tokens']  ?? 0);
        $output_t = (int) ($data['usage']['output_tokens'] ?? 0);

        return [
            'content'           => (string) ($data['content'][0]['text'] ?? ''),
            'prompt_tokens'     => $input_t,
            'completion_tokens' => $output_t,
            'total_tokens'      => $input_t + $output_t,
            'model'             => (string) ($data['model'] ?? $model),
        ];
    }

    private static function chat_gemini(
        string $api_key, string $model,
        array $messages, string $system, float $temp, int $max_tokens
    ): array {
        $model_id = str_replace('models/', '', $model);
        $url      = "https://generativelanguage.googleapis.com/v1beta/models/{$model_id}:generateContent?key={$api_key}";

        $contents = [];
        foreach ($messages as $m) {
            if (!isset($m['role'], $m['content'])) continue;
            $role       = ($m['role'] === 'assistant') ? 'model' : 'user';
            $contents[] = ['role' => $role, 'parts' => [['text' => (string) $m['content']]]];
        }

        $body = [
            'contents'         => $contents,
            'generationConfig' => [
                'temperature'     => $temp,
                'maxOutputTokens' => $max_tokens,
            ],
        ];
        if (!empty($system)) {
            $body['systemInstruction'] = ['parts' => [['text' => $system]]];
        }

        // CHANGED: Gemini remains optional, but when used it also passes through the central AGFO transport gate.
        $response = agfo_api_post($url, ['Content-Type' => 'application/json'], wp_json_encode($body), [
            'provider_code' => 'gemini',
            'model'         => $model,
            'timeout'       => 60,
            'source'        => 'agfo_chat_test',
            'progress'      => self::$dispatch_progress, // CHANGED 16.2.0
        ]);

        if (isset($response['error'])) return ['error' => $response['error']];

        $code = (int) ($response['http_code'] ?? 0);
        $raw  = (string) ($response['body'] ?? '');
        $data = json_decode($raw, true);

        if ($code < 200 || $code >= 300) {
            $err = (isset($data['error']['message']) && is_string($data['error']['message']))
                ? $data['error']['message']
                : "HTTP {$code}: " . substr($raw, 0, 300);
            return ['error' => $err];
        }

        $usage = $data['usageMetadata'] ?? [];

        return [
            'content'           => (string) ($data['candidates'][0]['content']['parts'][0]['text'] ?? ''),
            'prompt_tokens'     => (int) ($usage['promptTokenCount']     ?? 0),
            'completion_tokens' => (int) ($usage['candidatesTokenCount'] ?? 0),
            'total_tokens'      => (int) ($usage['totalTokenCount']      ?? 0),
            'model'             => $model,
        ];
    }

    /* ════════════════════════════════════════════════════
     * YARDIMCI
     * ════════════════════════════════════════════════════ */
private static function resolve_model_context(string $provider, string $id, array $provider_contexts): string {
    if (isset($provider_contexts[$id])) {
        return strtolower((string) $provider_contexts[$id]);
    }

    $id_lower = strtolower($id);

    foreach ($provider_contexts as $key => $ctx) {
        if (strtolower((string) $key) === $id_lower) {
            return strtolower((string) $ctx);
        }
    }

    foreach ($provider_contexts as $key => $ctx) {
        $key_lower = strtolower((string) $key);

        if (
            $key_lower === $id_lower ||
            str_replace('models/', '', $key_lower) === str_replace('models/', '', $id_lower)
        ) {
            return strtolower((string) $ctx);
        }
    }

    if (strpos($id_lower, 'gemini') !== false) return '1m';

    if (
        strpos($id_lower, 'claude') !== false ||
        strpos($id_lower, 'anthropic') !== false
    ) {
        return '200k';
    }

    if (
        strpos($id_lower, 'gpt-5') !== false ||
        strpos($id_lower, 'gpt-4.1') !== false ||
        strpos($id_lower, 'gpt-4o') !== false ||
        strpos($id_lower, 'llama-4') !== false ||
        strpos($id_lower, 'llama-3.3') !== false ||
        strpos($id_lower, 'llama-3.1') !== false
    ) {
        return '100k';
    }

    if (
        strpos($id_lower, 'deepseek') !== false ||
        strpos($id_lower, 'r1') !== false
    ) {
        return '64k';
    }

    return '32k';
}
/**
 * Public read access to the normalised model list (17.1.0, used by the Translation board).
 */
public static function models_for_provider(string $provider, array $args = []): array {
    return self::get_models_for_provider(sanitize_key($provider), $args);
}

private static function get_models_for_provider(string $provider, array $args = []): array {
    if (empty($provider)) return [];

    $all_data     = agfo_read_data_json();
    $all_models   = isset($all_data['models'])       && is_array($all_data['models'])       ? $all_data['models']       : [];
    $context_tags = isset($all_data['context_tags']) && is_array($all_data['context_tags']) ? $all_data['context_tags'] : [];
    $rankings     = isset($all_data['rankings'])     && is_array($all_data['rankings'])     ? $all_data['rankings']     : [];
    $blacklist    = isset($all_data['blacklist'])     && is_array($all_data['blacklist'])    ? $all_data['blacklist']    : [];

    $models = get_option("agfo_models_{$provider}", []);
    if (empty($models)) $models = $all_models[$provider] ?? [];
    if (!is_array($models)) return [];

    $provider_contexts  = isset($context_tags[$provider]) && is_array($context_tags[$provider]) ? $context_tags[$provider] : [];
    $provider_rankings  = isset($rankings[$provider])     && is_array($rankings[$provider])     ? $rankings[$provider]     : [];
    $provider_blacklist = isset($blacklist[$provider])    && is_array($blacklist[$provider])     ? $blacklist[$provider]    : [];
    $blacklist_lower    = array_map('strtolower', $provider_blacklist);
    // CHANGED 16.7.0: Dropdown etiketine islevsel bilgi (fiyat/hiz) icin Model Intelligence
    // deposu. $all_data zaten okunmus durumda — model basina EK dosya okumasi yapilmaz.
    $intel_store        = isset($all_data['model_intelligence'][$provider]) && is_array($all_data['model_intelligence'][$provider])
        ? $all_data['model_intelligence'][$provider]
        : [];

    $normalized = [];

    foreach ($models as $model) {
        $id = '';
        if (is_string($model))     $id = trim($model);
        elseif (is_array($model))  $id = trim((string)($model['id'] ?? $model['name'] ?? ''));
        if ($id === '') continue;
        if (in_array(strtolower($id), $blacklist_lower, true)) continue;

        $rank_score  = 50;
        $tier        = 'D';
        $input_price = null;
        $price_label = '';
        $fp          = null;
        $reasons     = [];

        if (isset($provider_rankings[$id]) && is_array($provider_rankings[$id])) {
            $r          = $provider_rankings[$id];
            $rank_score = isset($r['score'])       ? (int)$r['score']         : 50;
            $tier       = isset($r['tier'])        ? (string)$r['tier']       : 'D';
            $input_price= isset($r['input_price']) ? (float)$r['input_price'] : null;
            $price_label= isset($r['price_label']) ? (string)$r['price_label']: '';
            $fp         = isset($r['fp'])          ? (int)$r['fp']            : null;
            $reasons    = isset($r['reasons'])     && is_array($r['reasons'])  ? $r['reasons'] : [];
        } elseif (function_exists('agfo_rank_model')) {
            $rank_score = (int)agfo_rank_model($provider, $id);
            $tier       = function_exists('agfo_model_tier_from_score')
                ? agfo_model_tier_from_score($rank_score)
                : 'D';
        }

        // ── 70 ALTI GİZLE ──
        if ($rank_score < 70) continue;

        $capabilities = function_exists('agfo_get_model_capabilities')
            ? agfo_get_model_capabilities($provider, $id)
            : [];

        if (!empty($args['chat_only']) && empty($capabilities['supports_chat'])) continue;
        if (!empty($args['docx_only']) && empty($capabilities['docx_allowed'])) continue;

        $context = self::resolve_model_context($provider, $id, $provider_contexts);

        // CHANGED 16.7.0: Intelligence satirindan islevsel alanlar (varsa) dropdown'a tasinir.
        $intel       = isset($intel_store[$id]) && is_array($intel_store[$id]) ? $intel_store[$id] : [];
        $speed_score = isset($intel['speed_score']) && is_numeric($intel['speed_score']) ? (int) $intel['speed_score'] : null;
        $in_price    = isset($intel['input_price_per_1m'])  && is_numeric($intel['input_price_per_1m'])  ? (float) $intel['input_price_per_1m']  : null;
        $out_price   = isset($intel['output_price_per_1m']) && is_numeric($intel['output_price_per_1m']) ? (float) $intel['output_price_per_1m'] : null;

        // NEW 17.1.0: fall back to provider-API / ranking prices when intelligence has none.
        if (($in_price === null || $out_price === null) && class_exists('AGFO_AIM_Model_Catalog')) {
            $tp = AGFO_AIM_Model_Catalog::token_price($provider, $id);
            if ($tp['in'] !== null) {
                $in_price  = $in_price  ?? $tp['in'];
                $out_price = $out_price ?? $tp['out'];
            }
        }

        $normalized[] = array_merge([
            'id'          => $id,
            'name'        => $id,
            'context'     => $context,
            'rank_score'  => $rank_score,
            'tier'        => $tier,
            'input_price' => $input_price,
            'price_label' => $price_label,
            'fp'          => $fp,
            'reasons'     => $reasons,
            'speed_score' => $speed_score, // CHANGED 16.7.0
            'in_price'    => $in_price,    // CHANGED 16.7.0: $/1M girdi
            'out_price'   => $out_price,   // CHANGED 16.7.0: $/1M cikti
        ], $capabilities);
    }

    usort($normalized, function ($a, $b) {
        $sa = (int)($a['rank_score'] ?? 0);
        $sb = (int)($b['rank_score'] ?? 0);
        return $sa === $sb ? strcmp($a['id'], $b['id']) : $sb <=> $sa;
    });

    // NEW 17.1.0: release time, family version and "new" flag for newest-first sorting.
    if (class_exists('AGFO_AIM_Model_Catalog')) {
        $normalized = AGFO_AIM_Model_Catalog::annotate_recency($provider, $normalized);
    }

    return $normalized;
}
}