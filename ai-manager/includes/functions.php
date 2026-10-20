<?php
if (!defined('ABSPATH')) exit;

// NEW 17.1.2: the key encryptor depends on the audited Base64 codec; load it here so this
// file works regardless of include order.
require_once __DIR__ . '/core/class-binary-codec.php';

/* ── ŞİFRELEME ─────────────────────────────────────────── */
class AGFO_AIM_Encryptor {
    private $method = 'AES-256-CBC';

    private function key(): string {
        return hash('sha256', defined('AUTH_SALT') ? AUTH_SALT : 'agfo_salt_key');
    }

    public function encrypt(string $plain): string {
        $iv_len = openssl_cipher_iv_length($this->method);
        $iv     = random_bytes($iv_len);
        $enc    = openssl_encrypt($plain, $this->method, $this->key(), OPENSSL_RAW_DATA, $iv);

        // CHANGED 17.1.2: Base64 goes through the single audited codec (byte-identical output).
        return AGFO_AIM_Binary_Codec::encode($iv . $enc);
    }

    public function decrypt(string $cipher): ?string {
        if (empty($cipher)) return null;

        // CHANGED 17.1.2: constant-time decode via the audited codec.
        $raw = AGFO_AIM_Binary_Codec::decode($cipher);
        if (!$raw) return null;

        $iv_len = openssl_cipher_iv_length($this->method);
        if (strlen($raw) <= $iv_len) return null;

        $iv      = substr($raw, 0, $iv_len);
        $payload = substr($raw, $iv_len);

        $result = openssl_decrypt($payload, $this->method, $this->key(), OPENSSL_RAW_DATA, $iv);
        if ($result !== false) return $result;

        $result2 = openssl_decrypt($payload, $this->method, $this->key(), 0, $iv);
        return ($result2 !== false) ? $result2 : null;
    }
}

$GLOBALS['AGFO_ENC'] = new AGFO_AIM_Encryptor();

/* ── MODEL AUTO RANKING ─────────────────────────────────── */
if (!function_exists('agfo_str_has')) {
    function agfo_str_has(string $haystack, string $needle): bool {
        return strpos($haystack, $needle) !== false;
    }
}

if (!function_exists('agfo_rank_model')) {
    function agfo_rank_model(string $provider, string $model): int {
        $m = strtolower($model);

        /*
         * CHANGED:
         * Bu bölüm artık "ham benchmark" değil, AGFO Assistant sıralaması üretir.
         * Amaç: canlı assistant için hızlı, dengeli, ucuz ve genel kullanıma uygun modelleri öne almak.
         */

        $assistant_overrides = [
            'qwen/qwen3.6-flash'                         => 90,
            'qwen/qwen3.6-plus'                          => 89,
            'qwen/qwen3.6-max-preview'                    => 87,
            'qwen/qwen3-235b-a22b-2507'                   => 86,
            'qwen/qwen3-max'                              => 86,
            'qwen/qwen-plus'                              => 83,
            'qwen/qwen-plus-2025-07-28'                   => 83,
            'qwen/qwen-plus-2025-07-28:thinking'          => 79,
            'qwen/qwen3-coder-flash'                      => 82,
            'qwen/qwen3-coder'                            => 80,
            'qwen/qwen3-coder-30b-a3b-instruct'           => 80,
            'qwen/qwen3-coder-next'                       => 80,
            'qwen/qwen3-coder-plus'                       => 80,
            'qwen/qwen3-coder:free'                       => 76,
            'qwen/qwen3-max-thinking'                     => 80,
            'qwen/qwen3-235b-a22b-thinking-2507'          => 79,
            'deepseek/deepseek-r1-distill-qwen-32b'       => 76,
            'qwen/qwen3.5-397b-a17b'                      => 84,
            'qwen/qwen3.5-122b-a10b'                      => 82,
            'qwen/qwen3.5-plus-02-15'                     => 81,
            'qwen/qwen3.5-plus-20260420'                  => 82,
            'qwen/qwen3.5-flash-02-23'                    => 79,
            'qwen/qwen3.6-35b-a3b'                        => 79,
            'qwen/qwen3.6-27b'                            => 78,
            'qwen/qwen3-next-80b-a3b-instruct'            => 81,
            'qwen/qwen3-next-80b-a3b-instruct:free'       => 77,
            'qwen/qwen3-next-80b-a3b-thinking'            => 78,
            'qwen/qwen3-30b-a3b'                          => 77,
            'qwen/qwen3-30b-a3b-instruct-2507'            => 78,
            'qwen/qwen3-30b-a3b-thinking-2507'            => 76,
            'qwen/qwen3-32b'                              => 77,
            'qwen/qwen3-235b-a22b'                        => 84,
        ];

        if (isset($assistant_overrides[$m])) {
            return $assistant_overrides[$m]; // CHANGED: Bilinen OpenRouter/Qwen modelleri assistant önceliğiyle sabitlenir.
        }

        foreach ($assistant_overrides as $needle => $score) {
            if (strpos($m, $needle) !== false || strpos($needle, $m) !== false) {
                return $score; // CHANGED: Versiyonlu/alias model adları da yakalanır.
            }
        }

        $known   = agfo_get_known_benchmarks();
        $sources = agfo_get_benchmark_sources();

        $bench = null;

        if (isset($known[$model])) {
            $bench = $known[$model];
        } elseif (isset($known[$m])) {
            $bench = $known[$m];
        } else {
            foreach ($known as $key => $data) {
                $key_lower = strtolower($key);
                if (
                    strpos($m, $key_lower) !== false ||
                    strpos($key_lower, $m) !== false
                ) {
                    $bench = $data;
                    break;
                }
            }
        }

        if ($bench) {
            $ws = 0.0;
            $tw = 0.0;

            foreach (['lmsys', 'openllm', 'artificialanalysis'] as $src) {
                if (!isset($bench[$src])) continue;

                $score = ($src === 'lmsys')
                    ? min(100, max(0, (($bench[$src] - 1000) / 400) * 100))
                    : (float) $bench[$src];

                $ws += $score * $sources[$src]['weight'];
                $tw += $sources[$src]['weight'];
            }

            $score = ($tw > 0) ? (int) round($ws / $tw) : 70;
        } else {
            $score = 50;

            if (agfo_str_has($m, 'gpt-5.5'))        $score += 46;
            elseif (agfo_str_has($m, 'gpt-5.4'))    $score += 45;
            elseif (agfo_str_has($m, 'gpt-5.3'))    $score += 40;
            elseif (agfo_str_has($m, 'gpt-5.2'))    $score += 36;
            elseif (agfo_str_has($m, 'gpt-5.1'))    $score += 34;
            elseif (agfo_str_has($m, 'gpt-5'))      $score += 32;
            elseif (agfo_str_has($m, 'gpt-4.1'))    $score += 25;
            elseif (agfo_str_has($m, 'gpt-4o'))     $score += 22;

            if (agfo_str_has($m, 'claude-opus'))    $score += 42;
            if (agfo_str_has($m, 'claude-sonnet'))  $score += 36;
            if (agfo_str_has($m, 'claude-haiku'))   $score += 26;

            if (agfo_str_has($m, 'gemini-3.1'))           $score += 36;
            elseif (agfo_str_has($m, 'gemini-3'))         $score += 34;
            elseif (agfo_str_has($m, 'gemini-2.5-pro'))   $score += 34;
            elseif (agfo_str_has($m, 'gemini-2.5-flash')) $score += 31;
            elseif (agfo_str_has($m, 'gemini-2.0-flash')) $score += 27;

            if (agfo_str_has($m, 'deepseek-r1'))       $score += 30;
            if (agfo_str_has($m, 'deepseek-reasoner')) $score += 30;
            if (agfo_str_has($m, 'deepseek-v4-pro'))   $score += 32;
            if (agfo_str_has($m, 'deepseek-v4'))       $score += 30;
            if (agfo_str_has($m, 'deepseek-v3'))       $score += 28;
            if (agfo_str_has($m, 'deepseek-chat'))     $score += 27;

            if (agfo_str_has($m, 'qwen3.6-flash'))       $score += 40; // CHANGED: Hızlı assistant modeli olarak yüksek öncelik.
            elseif (agfo_str_has($m, 'qwen3.6-plus'))    $score += 38; // CHANGED: Genel assistant kalitesi için yüksek öncelik.
            elseif (agfo_str_has($m, 'qwen3.6-max'))     $score += 36; // CHANGED: Güçlü ama daha ağır model.
            elseif (agfo_str_has($m, 'qwen3.6'))         $score += 32;

            if (agfo_str_has($m, 'qwen3-235b-a22b-2507')) $score += 34;
            elseif (agfo_str_has($m, 'qwen3-235b'))       $score += 31;

            if (agfo_str_has($m, 'qwen3-max'))          $score += 32;
            if (agfo_str_has($m, 'qwen3.5-397b'))       $score += 31;
            elseif (agfo_str_has($m, 'qwen3.5-122b'))   $score += 30;
            elseif (agfo_str_has($m, 'qwen3.5-plus'))   $score += 29;
            elseif (agfo_str_has($m, 'qwen3.5-flash'))  $score += 28;
            elseif (agfo_str_has($m, 'qwen3.5'))        $score += 25;

            if (agfo_str_has($m, 'qwen3-coder-flash')) $score += 28;
            elseif (agfo_str_has($m, 'qwen3-coder'))   $score += 25;

            if (agfo_str_has($m, 'qwen3-next'))      $score += 28;
            if (agfo_str_has($m, 'qwen3-32b'))       $score += 24;
            if (agfo_str_has($m, 'qwen3-30b'))       $score += 24;
            if (agfo_str_has($m, 'qwen3-14b'))       $score += 20;
            if (agfo_str_has($m, 'qwen3-8b'))        $score += 17;
            if (agfo_str_has($m, 'qwen-plus'))       $score += 29;
            if (agfo_str_has($m, 'qwen-turbo'))      $score += 25;

            if (agfo_str_has($m, 'llama-4'))         $score += 30;
            if (agfo_str_has($m, 'llama-3.3'))       $score += 26;
            if (agfo_str_has($m, 'llama-3.1'))       $score += 23;

            if (agfo_str_has($m, 'kimi-k2-thinking')) $score += 30;
            elseif (agfo_str_has($m, 'kimi-k2'))      $score += 29;

            if (agfo_str_has($m, 'glm-5'))           $score += 30;
            if (agfo_str_has($m, 'glm-4.7-flash'))   $score += 27;
            elseif (agfo_str_has($m, 'glm-4.7'))     $score += 25;
            if (agfo_str_has($m, 'glm-4.6'))         $score += 22;
            if (agfo_str_has($m, 'glm-4.5'))         $score += 20;

            if (agfo_str_has($m, 'minimax-m2.7'))    $score += 27;
            elseif (agfo_str_has($m, 'minimax-m2'))  $score += 24;

            if (agfo_str_has($m, 'step-3.5-flash'))  $score += 27;
            if (agfo_str_has($m, 'seed-2.0'))        $score += 26;
            if (agfo_str_has($m, 'seed-1.6-flash'))  $score += 24;
            if (agfo_str_has($m, 'mimo-v2-flash'))   $score += 24;
            if (agfo_str_has($m, 'reka-flash'))      $score += 23;
            if (agfo_str_has($m, 'nova-lite'))       $score += 22;
            if (agfo_str_has($m, 'nova-micro'))      $score += 18;

            if (agfo_str_has($m, 'grok-4.3'))        $score += 34;
            elseif (agfo_str_has($m, 'grok'))        $score += 30;

            if (agfo_str_has($m, 'mistral-medium'))       $score += 33;
            elseif (agfo_str_has($m, 'mistral-large'))    $score += 32;
            elseif (agfo_str_has($m, 'mistral-small'))    $score += 23;
            if (agfo_str_has($m, 'codestral'))            $score += 26;
            if (agfo_str_has($m, 'devstral'))             $score += 25;

            if (agfo_str_has($m, 'gpt-oss-120b'))    $score += 30;
            if (agfo_str_has($m, 'gpt-oss-20b'))     $score += 22;
        }

        /*
         * CHANGED:
         * Assistant modifiers.
         * Benchmark güçlü olsa bile canlı assistant için ağır/uzun düşünen modeller aşağı alınır.
         */

        if (agfo_str_has($m, 'flash'))   $score += 5;
        if (agfo_str_has($m, 'turbo'))   $score += 4;
        if (agfo_str_has($m, 'instant')) $score += 4;
        if (agfo_str_has($m, 'plus'))    $score += 2;

        if (agfo_str_has($m, 'thinking'))  $score -= 10;
        if (agfo_str_has($m, 'reasoner'))  $score -= 8;
        if (agfo_str_has($m, 'reasoning')) $score -= 8;

        if (agfo_str_has($m, 'coder')) {
            $score -= agfo_str_has($m, 'coder-flash') ? 3 : 7;
        }

        if (agfo_str_has($m, 'distill')) $score -= 10;
        if (agfo_str_has($m, 'free'))    $score -= 4;
        if (agfo_str_has($m, 'preview')) $score -= 1;

        if (agfo_str_has($m, '2026'))     $score += 3;
        elseif (agfo_str_has($m, '2025')) $score += 1;

        if (agfo_str_has($m, 'mini')) $score -= 2;
        if (agfo_str_has($m, 'nano')) $score -= 3;
        if (agfo_str_has($m, 'lite')) $score -= 3;
        if (agfo_str_has($m, 'base')) $score -= 25;

        if (preg_match('/\b(0\.6b|1b|1\.5b|2b|3b|4b)\b/i', $model)) {
            $score -= 18;
        } elseif (preg_match('/\b(7b|8b|9b)\b/i', $model)) {
            $score -= 12;
        }

        foreach ([
            'image', 'audio', 'speech', 'tts', 'stt', 'whisper', 'embed', 'embedding',
            'ocr', 'video', 'veo', 'sora', 'imagen', 'dall-e', 'dalle'
        ] as $bad) {
            if (agfo_str_has($m, $bad)) {
                $score -= 100;
            }
        }

        return max(0, min(100, (int) round($score)));
    }
}

if (!function_exists('agfo_model_tier_from_score')) {
    function agfo_model_tier_from_score(int $score): string {
        if ($score >= 90) return 'S';
        if ($score >= 80) return 'A';
        if ($score >= 70) return 'B';
        if ($score >= 55) return 'C';
        return 'D';
    }
}

/* ── DATA.JSON ──────────────────────────────────────────── */
/**
 * Request-scoped cache for data.json.
 *
 * CHANGED 17.0.0: data.json (~125 KB) was read from disk and decoded on every
 * capability lookup — once per model while the quick-switch list was built and several
 * times per agfo_api_post() call. The decoded array is now kept for the request and
 * invalidated by every write. Pass null to read, an array to replace, false to clear.
 *
 * @param array|false|null $set
 * @return array|null
 */
function agfo_aim_data_cache($set = null) {
    static $cache = null;
    if (is_array($set)) {
        $cache = $set;
    } elseif ($set === false) {
        $cache = null;
    }
    return $cache;
}

function agfo_read_data_json(): array {
    $cached = agfo_aim_data_cache();
    if (is_array($cached)) return $cached; // CHANGED 17.0.0: request-scoped cache.
    if (!file_exists(AGFO_AIM_DATA_FILE)) return [];
    $data = json_decode((string) file_get_contents(AGFO_AIM_DATA_FILE), true);
    $data = is_array($data) ? $data : [];
    agfo_aim_data_cache($data);
    return $data;
}

function agfo_write_data_json(array $data): bool {
    if (!is_dir(AGFO_AIM_DATA_DIR)) wp_mkdir_p(AGFO_AIM_DATA_DIR);
    // CHANGED 16.6.0: LOCK_EX eklendi. Es zamanli "Tum Modelleri Yenile" cagrilari
    // ayni dosyaya yazdiginda data.json yarim/bozuk kalabiliyordu.
    $ok = file_put_contents(
        AGFO_AIM_DATA_FILE,
        json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES),
        LOCK_EX
    ) !== false;
    // CHANGED 17.0.0: keep the request cache in step with the file.
    agfo_aim_data_cache($ok ? $data : false);
    return $ok;
}

function agfo_read_data_section(string $section): array {
    $all = agfo_read_data_json();
    return (isset($all[$section]) && is_array($all[$section])) ? $all[$section] : [];
}

function agfo_write_data_section(string $section, array $data): bool {
    $all           = agfo_read_data_json();
    $all[$section] = $data;
    return agfo_write_data_json($all);
}

function agfo_read_context_tags(): array {
    return agfo_read_data_section('context_tags');
}

/* ── API REGISTRY ───────────────────────────────────────── */
function agfo_api_registry(): array {
    return [
        'openai'         => [
            'label'    => 'OpenAI',
            'url'      => 'https://api.openai.com/v1/models',
            'chat_url' => 'https://api.openai.com/v1/chat/completions',
            'auth'     => ['Authorization' => 'Bearer {key}'],
            'type'     => 'llm',
            // CHANGED 16.16.0: 'image_generate' eklendi. Chat ve TTS davranisi degismedi.
            'capabilities' => ['chat', 'speech_synthesize', 'image_generate'],
            'default_models' => [ 'speech_synthesize' => 'gpt-4o-mini-tts', 'image_generate' => 'gpt-image-2' ],
        ],
        // CHANGED 16.6.0: OpenRouter muzik modellerini (Lyria 3 vb.) ayni
        // chat/completions ucundan sunar; bu yuzden 'music_generate' de tanimli.
        // 'type' => 'llm' korundu, chat davranisi degismedi.
        'openrouter'     => [
            'label'    => 'OpenRouter',
            'url'      => 'https://openrouter.ai/api/v1/models',
            'chat_url' => 'https://openrouter.ai/api/v1/chat/completions',
            'auth'     => ['Authorization' => 'Bearer {key}'],
            'type'     => 'llm',
            // CHANGED 16.16.0: 'image_generate' eklendi (gorsel uretebilen chat modelleri).
            'capabilities' => ['chat', 'music_generate', 'image_generate'],
            'default_models' => [ 'image_generate' => 'openai/gpt-5.4-image-2' ],
        ],
        'groq'           => [
            'label'    => 'Groq',
            'url'      => 'https://api.groq.com/openai/v1/models',
            'chat_url' => 'https://api.groq.com/openai/v1/chat/completions',
            'auth'     => ['Authorization' => 'Bearer {key}'],
            'type'     => 'llm',
            'capabilities' => ['chat'],
        ],
        'deepinfra'      => [
            'label'    => 'DeepInfra',
            'url'      => 'https://api.deepinfra.com/v1/openai/models',
            'chat_url' => 'https://api.deepinfra.com/v1/openai/chat/completions',
            'auth'     => ['Authorization' => 'Bearer {key}'],
            'type'     => 'llm',
            'capabilities' => ['chat'],
        ],
        'llama_together' => [
            'label'    => 'Together.ai',
            'url'      => 'https://api.together.xyz/v1/models',
            'chat_url' => 'https://api.together.xyz/v1/chat/completions',
            'auth'     => ['Authorization' => 'Bearer {key}'],
            'type'     => 'llm',
            'capabilities' => ['chat'],
        ],
        'claude'         => [
            'label'    => 'Claude',
            'url'      => 'https://api.anthropic.com/v1/models',
            'chat_url' => 'https://api.anthropic.com/v1/messages',
            'auth'     => ['x-api-key' => '{key}', 'anthropic-version' => '2023-06-01'],
            'type'     => 'llm',
            'capabilities' => ['chat'],
        ],
        'gemini'         => [
            'label'    => 'Gemini',
            'url'      => 'https://generativelanguage.googleapis.com/v1beta/models?key={key}',
            'chat_url' => 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}',
            'auth'     => [],
            'type'     => 'llm',
            // CHANGED 16.16.0: 'image_generate' eklendi (Imagen / Gemini image).
            'capabilities' => ['chat', 'music_generate', 'image_generate'],
            'default_models' => [ 'chat' => 'gemini-2.5-flash', 'music_generate' => 'lyria-3-clip-preview', 'image_generate' => 'imagen-4.0-generate-001' ],
        ],
        'deepseek'       => [
            'label'    => 'DeepSeek',
            'url'      => 'https://api.deepseek.com/models',
            'chat_url' => 'https://api.deepseek.com/chat/completions',
            'auth'     => ['Authorization' => 'Bearer {key}'],
            'type'     => 'llm',
            'capabilities' => ['chat'],
        ],
        // CHANGED 15.7.0: NVIDIA NIM (build.nvidia.com / integrate.api.nvidia.com) eklendi.
        // OpenAI-uyumlu chat/completions; Bearer auth (nvapi-... anahtari).
        // Kaynak: https://docs.api.nvidia.com/nim/reference/models-1
        'nvidia'         => [
            'label'    => 'NVIDIA NIM',
            'url'      => 'https://integrate.api.nvidia.com/v1/models',
            'chat_url' => 'https://integrate.api.nvidia.com/v1/chat/completions',
            'auth'     => ['Authorization' => 'Bearer {key}'],
            'type'     => 'llm',
            'capabilities' => ['chat'],
        ],
        // CHANGED 16.6.0: fal.ai — kuyruk tabanli medya saglayicisi.
        // 'type' KASITLA 'llm' DEGIL: model yenileme, chat saglayici secici ve
        // agfo_get_priority_api_key() bu girdiyi gormezden gelir, chat akisi
        // hicbir sekilde etkilenmez. Model kimligi endpoint'in parcasidir
        // (orn. fal-ai/stable-audio-25/text-to-audio), bu yuzden liste URL'i yoktur.
        'fal'            => [
            'label'         => 'fal.ai',
            'url'           => '',
            'chat_url'      => '',
            'submit_url'    => 'https://queue.fal.run/{model}',
            'auth'          => ['Authorization' => 'Key {key}'],
            'type'          => 'media',
            // CHANGED 16.16.0: 'image_generate' eklendi; kuyruk polling'i zaten merkezi.
            'capabilities'  => ['music_generate', 'audio_transform', 'image_generate'],
            'poll_style'    => 'fal_queue',
            'default_model' => 'fal-ai/stable-audio-25/text-to-audio',
        ],
        // CHANGED 16.8.0: TTS-only provider. Model discovery is intentionally
        // not coupled to the text-model list; voice IDs remain provider-specific.
        'elevenlabs'     => [
            'label'          => 'ElevenLabs',
            'url'            => 'https://api.elevenlabs.io/v1/models',
            'chat_url'       => '',
            'submit_url'     => 'https://api.elevenlabs.io/v1/text-to-speech/{voice}',
            'auth'           => ['xi-api-key' => '{key}'],
            'type'           => 'media',
            'capabilities'   => ['speech_synthesize', 'music_generate'],
            'default_model'  => 'eleven_multilingual_v2',
            'default_models' => [ 'speech_synthesize' => 'eleven_multilingual_v2', 'music_generate' => 'music_v1' ],
        ],
        // CHANGED 16.11.0: MiniMax OpenAI-compatible chat plus synchronous T2A.
        // The same encrypted API key is resolved server-side for both capabilities.
        'minimax'        => [
            'label'          => 'MiniMax',
            'url'            => 'https://api.minimax.io/v1/models',
            'chat_url'       => 'https://api.minimax.io/v1/chat/completions',
            'submit_url'     => 'https://api.minimax.io/v1/t2a_v2',
            'voice_url'      => 'https://api.minimax.io/v1/get_voice',
            'auth'           => ['Authorization' => 'Bearer {key}'],
            'type'           => 'llm',
            // CHANGED 16.16.0: 'image_generate' eklendi.
            'capabilities'   => ['chat', 'speech_synthesize', 'music_generate', 'image_generate'],
            'default_model'  => 'MiniMax-M3',
            'default_models' => [
                'chat'              => 'MiniMax-M3',
                'speech_synthesize' => 'speech-2.8-hd',
                'music_generate'    => 'music-2.6-free',
                'image_generate'    => 'image-01',
            ],
        ],
        // NEW 17.9.0: self-hosted Turkish TTS. The "key" is the AGFO TTS Service token
        // (or AGFO_TTS_TOKEN in wp-config.php); the endpoint lives in Ses Stüdyosu.
        'ema'            => [
            'label'          => 'EMA Lightning (yerel TTS)',
            'url'            => '',
            'chat_url'       => '',
            'submit_url'     => '',
            'auth'           => ['X-AGFO-Token' => '{key}'],
            'type'           => 'media',
            'capabilities'   => ['speech_synthesize'],
            'default_model'  => 'ema-lightning',
            'default_models' => [ 'speech_synthesize' => 'ema-lightning' ],
        ],
    ];
}

/* ── API KEY ────────────────────────────────────────────── */
function agfo_get_api_key(string $code): ?string {
    global $AGFO_ENC;
    $stored = get_option('agfo_' . $code . '_api_key', '');
    if (empty($stored)) {
        // NEW 17.9.0: the EMA service token may live only in wp-config.php.
        if ('ema' === $code && defined('AGFO_TTS_TOKEN') && '' !== trim((string) AGFO_TTS_TOKEN)) {
            return trim((string) AGFO_TTS_TOKEN);
        }
        return null;
    }
    if ($AGFO_ENC) {
        $dec = $AGFO_ENC->decrypt($stored);
        return ($dec !== null) ? $dec : $stored;
    }
    return $stored;
}

function agfo_get_selected_provider(): string {
    return get_option('agfo_selected_provider', 'openai');
}

/* ── MERKEZİ API POST ───────────────────────────────────── */
if (!function_exists('agfo_ai_manager_log_transport')) {
    function agfo_ai_manager_log_transport(string $stage, array $context = []): void {
        // CHANGED 16.6.0: (1) Anahtar redaksiyonu — Gemini chat_url'i API anahtarini
        // sorgu dizesinde tasir ve cURL hata mesajlari sik sik URL'i icerir; redaksiyon
        // olmadan bir baglanti hatasi anahtari wp_options'a dusurebiliyordu.
        // (2) Biriktirmeli yazim — her cagride get_option+update_option yapiliyordu;
        // uzun polling dongulerinde bu yuk katlaniyor. Kayitlar ayni, DB yazimi az.
        $entry = [
            'time'    => current_time('mysql'),
            'stage'   => $stage,
            'context' => agfo_redact_secrets($context),
        ];

        agfo_ai_manager_transport_log_buffer($entry);
    }
}

if (!function_exists('agfo_redact_secrets')) {
    /**
     * Bilinen API anahtarlarini ve yaygin anahtar bicimlerini metinden temizler.
     * Dizilerde ozyinelemeli calisir. Anahtar degeri asla log'a/ekrana dusmez.
     *
     * @param mixed $value
     * @return mixed
     */
    function agfo_redact_secrets($value) {
        if (is_array($value)) {
            $out = [];
            foreach ($value as $k => $v) $out[$k] = agfo_redact_secrets($v);
            return $out;
        }
        if (!is_string($value) || $value === '') return $value;

        $out = $value;

        // 1) Kayitli gercek anahtarlar — en guvenilir eslesme.
        static $known = null;
        if ($known === null) {
            $known = [];
            if (function_exists('agfo_api_registry') && function_exists('agfo_get_api_key')) {
                foreach (array_keys(agfo_api_registry()) as $code) {
                    $k = agfo_get_api_key($code);
                    if (is_string($k) && strlen($k) >= 8) $known[] = $k;
                }
            }
        }
        foreach ($known as $k) {
            if (strpos($out, $k) !== false) $out = str_replace($k, '[REDACTED]', $out);
        }

        // 2) Bicim tabanli guvenlik agi (kaydedilmemis/eski anahtarlar icin).
        $patterns = [
            '#([?&](?:key|api_key|apikey|access_token)=)[^&\s"\']+#i' => '$1[REDACTED]',
            '#(Bearer\s+)[A-Za-z0-9\-\._~\+/]{12,}#i'                 => '$1[REDACTED]',
            '#(Key\s+)[A-Za-z0-9\-\._~\+/:]{12,}#'                    => '$1[REDACTED]',
            '#\b(sk|nvapi|sk-or|sk-ant|gsk)-[A-Za-z0-9\-_]{12,}#i'    => '[REDACTED]',
            '#\bAIza[0-9A-Za-z\-_]{20,}#'                             => '[REDACTED]',
        ];
        foreach ($patterns as $pattern => $replacement) {
            $replaced = preg_replace($pattern, $replacement, $out);
            if ($replaced !== null) $out = $replaced;
        }

        return $out;
    }
}

if (!function_exists('agfo_ai_manager_transport_log_buffer')) {
    /**
     * Log kayitlarini istek suresince bellekte biriktirir, shutdown'da tek
     * seferde yazar. Beklenmedik sonlanmada kayip olmasin diye 20 kayitta bir
     * ara flush yapar. Saklama sekli ve 80 kayit tavani degismedi.
     *
     * @param array|null $entry Null ise flush edilir.
     */
    function agfo_ai_manager_transport_log_buffer(?array $entry = null): void {
        static $buffer   = [];
        static $attached = false;

        if ($entry !== null) {
            $buffer[] = $entry;
            if (!$attached && function_exists('add_action')) {
                add_action('shutdown', function () { agfo_ai_manager_transport_log_buffer(null); }, 99);
                $attached = true;
            }
            if (count($buffer) < 20) return;
        }

        if (empty($buffer)) return;

        $log = get_option('agfo_ai_manager_transport_log', []);
        if (!is_array($log)) $log = [];
        foreach ($buffer as $item) $log[] = $item;
        if (count($log) > 80) $log = array_slice($log, -80);
        update_option('agfo_ai_manager_transport_log', $log, false);

        $buffer = [];
    }
}

if (!function_exists('agfo_ai_manager_is_managed_ai_url')) {
    function agfo_ai_manager_is_managed_ai_url(string $url): bool {
        $host = strtolower((string) wp_parse_url($url, PHP_URL_HOST));
        if ($host === '') return false;

        $registry = function_exists('agfo_api_registry') ? agfo_api_registry() : [];
        foreach ($registry as $info) {
            foreach (['url', 'chat_url'] as $key) {
                if (empty($info[$key]) || !is_string($info[$key])) continue;
                $template = str_replace(['{key}', '{model}'], ['agfo_dummy_key', 'agfo_dummy_model'], $info[$key]);
                $allowed_host = strtolower((string) wp_parse_url($template, PHP_URL_HOST));
                if ($allowed_host !== '' && $allowed_host === $host) {
                    return true;
                }
            }
        }
        return false;
    }
}

if (!function_exists('agfo_ai_manager_connector_guard_callbacks')) {
    function agfo_ai_manager_connector_guard_callbacks(): array {
        global $wp_filter;
        $found = [];
        if (empty($wp_filter['pre_http_request']) || !is_object($wp_filter['pre_http_request']) || empty($wp_filter['pre_http_request']->callbacks)) {
            return $found;
        }
        foreach ($wp_filter['pre_http_request']->callbacks as $priority => $callbacks) {
            foreach ($callbacks as $item) {
                $callback = $item['function'] ?? null;
                $accepted_args = isset($item['accepted_args']) ? (int) $item['accepted_args'] : 3;
                $name = '';
                if (is_array($callback) && isset($callback[0], $callback[1])) {
                    $class = is_object($callback[0]) ? get_class($callback[0]) : (string) $callback[0];
                    $name = $class . '::' . (string) $callback[1];
                } elseif (is_string($callback)) {
                    $name = $callback;
                }
                if ($name !== '' && stripos($name, 'Connector_Approval') !== false && stripos($name, 'maybe_block_request') !== false) {
                    $found[] = [
                        'callback'      => $callback,
                        'priority'      => (int) $priority,
                        'accepted_args' => $accepted_args,
                        'name'          => $name,
                    ];
                }
            }
        }
        return $found;
    }
}

if (!function_exists('agfo_ai_manager_without_connector_guard')) {
    function agfo_ai_manager_without_connector_guard(callable $callback) {
        $guards = agfo_ai_manager_connector_guard_callbacks();
        foreach ($guards as $guard) {
            remove_filter('pre_http_request', $guard['callback'], $guard['priority']);
        }
        try {
            return $callback($guards);
        } finally {
            foreach ($guards as $guard) {
                add_filter('pre_http_request', $guard['callback'], $guard['priority'], $guard['accepted_args']);
            }
        }
    }
}

// CHANGED 16.1.0: NVIDIA NIM async (202) sonuc bekleme. NIM bazi cagrilarda HTTP 202 + NVCF-REQID
// basligi doner; sonuc GET https://integrate.api.nvidia.com/v1/status/{requestId} ile alinir.
// CHANGED 16.6.0: NVIDIA'ya gomulu polling mantigi genellestirildi. Ses uretimi
// dakikalar surdugu icin ayni desene ihtiyac var; iki kopya kod tutulmuyor.
// agfo_nvidia_poll_result() imzasi ve donen dizisi BIREBIR korundu (asagida).
if (!function_exists('agfo_async_poll_result')) {
    /**
     * Kuyruk tabanli saglayicilar icin genel sonuc bekleyici.
     *
     * @param string        $status_url  Durum sorgu adresi.
     * @param array         $headers     Auth dahil istek basliklari.
     * @param array         $options     'budget'      => saniye butcesi (varsayilan 90)
     *                                   'interval'    => bekleme araligi (varsayilan 2)
     *                                   'stage'       => log/progress asama adi
     *                                   'pending_codes' => devam sayilan HTTP kodlari
     *                                   'status_field'  => JSON durum alani adi
     *                                   'pending_values'=> devam sayilan durum degerleri
     *                                   'result_field'  => sonuc URL'i tasiyan alan
     *                                   'max_budget'    => ust sinir (varsayilan 900)
     * @param callable|null $progress    Asama bildirimi.
     * @return array http_code/body/stage/attempts veya error/stage
     */
    function agfo_async_poll_result(string $status_url, array $headers, array $options = [], ?callable $progress = null): array {
        $status_url = trim($status_url);
        $stage      = isset($options['stage']) ? (string) $options['stage'] : 'async_poll';

        if ($status_url === '' || !wp_http_validate_url($status_url)) {
            return ['error' => 'Gecersiz durum adresi.', 'stage' => $stage];
        }

        $max_budget = isset($options['max_budget']) ? (int) $options['max_budget'] : 900;
        $budget     = isset($options['budget']) ? (int) $options['budget'] : 90;
        $budget     = max(5, min($max_budget, $budget));
        $interval   = max(1, min(15, isset($options['interval']) ? (int) $options['interval'] : 2));

        $pending_codes  = isset($options['pending_codes']) && is_array($options['pending_codes'])
            ? array_map('intval', $options['pending_codes'])
            : [202];
        $status_field   = isset($options['status_field']) ? (string) $options['status_field'] : '';
        $pending_values = isset($options['pending_values']) && is_array($options['pending_values'])
            ? array_map('strtoupper', array_map('strval', $options['pending_values']))
            : [];
        $result_field   = isset($options['result_field']) ? (string) $options['result_field'] : '';

        $headers  = array_merge(['Accept' => 'application/json'], $headers);
        $deadline = time() + $budget;
        $attempt  = 0;

        while (time() < $deadline) {
            $attempt++;
            if ($progress) {
                try { $progress($stage, ['attempt' => $attempt, 'budget' => $budget]); } catch (Exception $e) {}
            }

            $res = wp_remote_get($status_url, ['timeout' => 30, 'sslverify' => true, 'headers' => $headers]);
            if (is_wp_error($res)) {
                return [
                    'error' => 'Poll hatasi: ' . agfo_redact_secrets($res->get_error_message()),
                    'stage' => $stage,
                ];
            }

            $code = (int) wp_remote_retrieve_response_code($res);
            $body = (string) wp_remote_retrieve_body($res);

            if (in_array($code, $pending_codes, true)) {
                sleep($interval);
                continue;
            }

            // JSON durum alani ile calisan saglayicilar (orn. fal.ai IN_QUEUE/IN_PROGRESS).
            if ($status_field !== '' && !empty($pending_values)) {
                $decoded = json_decode($body, true);
                if (is_array($decoded) && isset($decoded[$status_field])) {
                    $state = strtoupper((string) $decoded[$status_field]);
                    if (in_array($state, $pending_values, true)) {
                        sleep($interval);
                        continue;
                    }
                    // Tamamlandi: sonuc ayri bir adreste ise onu cek.
                    if ($result_field !== '' && !empty($decoded[$result_field]) && is_string($decoded[$result_field])) {
                        $final = wp_remote_get((string) $decoded[$result_field], [
                            'timeout'   => 60,
                            'sslverify' => true,
                            'headers'   => $headers,
                        ]);
                        if (is_wp_error($final)) {
                            return [
                                'error' => 'Sonuc alinamadi: ' . agfo_redact_secrets($final->get_error_message()),
                                'stage' => $stage,
                            ];
                        }
                        return [
                            'http_code' => (int) wp_remote_retrieve_response_code($final),
                            'body'      => (string) wp_remote_retrieve_body($final),
                            'stage'     => $stage,
                            'attempts'  => $attempt,
                        ];
                    }
                }
            }

            return [
                'http_code' => $code,
                'body'      => $body,
                'stage'     => $stage,
                'attempts'  => $attempt,
            ];
        }

        return [
            'error'    => 'Sonuc ' . $budget . 'sn icinde hazir olmadi.',
            'stage'    => $stage . '_timeout',
            'attempts' => $attempt,
        ];
    }
}

if (!function_exists('agfo_nvidia_poll_result')) {
    function agfo_nvidia_poll_result(string $request_id, array $auth_headers, int $budget_seconds = 90, ?callable $progress = null): array {
        $request_id = trim($request_id);
        if ($request_id === '') return ['error' => 'NVIDIA requestId bos', 'stage' => 'nvidia_poll'];

        // CHANGED 16.6.0: Ic mantik agfo_async_poll_result()'a tasindi.
        // Disaridan gorunen imza, hata metinleri ve donen alanlar korundu.
        $result = agfo_async_poll_result(
            'https://integrate.api.nvidia.com/v1/status/' . rawurlencode($request_id),
            $auth_headers,
            [
                'budget'        => $budget_seconds,
                'max_budget'    => 180,
                'interval'      => 2,
                'stage'         => 'nvidia_poll',
                'pending_codes' => [202],
            ],
            $progress
        );

        if (isset($result['error']) && ($result['stage'] ?? '') === 'nvidia_poll_timeout') {
            $result['error'] = 'NVIDIA sonucu ' . $budget_seconds . 'sn icinde hazir olmadi (requestId: ' . $request_id . ')';
        } elseif (isset($result['error'])) {
            $result['error'] = 'NVIDIA poll hatasi: ' . $result['error'];
        }

        return $result;
    }
}

function agfo_api_post(string $url, array $headers, $body, array $options = []): array {
    $provider_code = isset($options['provider_code']) ? sanitize_key((string) $options['provider_code']) : '';
    $temperature_retry_used = false;
    // CHANGED 16.1.0: NVIDIA NIM kuyruklu calisir; cagiran timeout belirtmediyse nvidia icin varsayilan 120sn.
    $default_timeout = ($provider_code === 'nvidia') ? 120 : 60;
    $timeout       = isset($options['timeout']) ? max(5, min(180, (int) $options['timeout'])) : $default_timeout;
    // CHANGED 16.2.0: opsiyonel gercek-zamanli asama bildirimi (async job / progress bar icin).
    $progress = (isset($options['progress']) && is_callable($options['progress'])) ? $options['progress'] : null;
    // CHANGED 16.6.0: opsiyonel yetenek etiketi. Gecirilmezse 'chat' kabul edilir;
    // boylece mevcut tum cagiricilar icin davranis degismez.
    $capability = isset($options['capability']) ? sanitize_key((string) $options['capability']) : 'chat';

    // CHANGED: Backward compatibility. Older callers may still pass an array body.
    if (is_array($body)) {
        $body = wp_json_encode($body);
    } elseif (!is_string($body)) {
        $body = (string) $body;
    }

    // CHANGED 15.7.0: NVIDIA NIM max_tokens tavani. NIM API max_tokens'i 1-4096 araliginda kabul eder;
    // daha buyuk deger gonderen bagimli pluginler HTTP 422 almasin diye merkezi olarak 4096'ya kirpilir.
    if ($provider_code === 'nvidia') {
        $decoded_nv = json_decode($body, true);
        if (is_array($decoded_nv) && isset($decoded_nv['max_tokens']) && (int) $decoded_nv['max_tokens'] > 4096) {
            $original_nv = (int) $decoded_nv['max_tokens'];
            $decoded_nv['max_tokens'] = 4096;
            $body = wp_json_encode($decoded_nv);
            agfo_ai_manager_log_transport('AGFO_API_POST_NVIDIA_MAX_TOKENS_CLAMPED', [
                'provider' => $provider_code,
                'model'    => !empty($options['model']) ? (string) $options['model'] : (string)($decoded_nv['model'] ?? ''),
                'from'     => $original_nv,
                'to'       => 4096,
            ]);
        }
    }

    // CHANGED 16.11.0: MiniMax OpenAI-compatible Chat Completions deprecates
    // max_tokens in favour of max_completion_tokens. Current limits are model-aware:
    // MiniMax-M3 up to 524288; M2.x up to 204800. Sampling ranges are temperature [0,2]
    // and top_p [0,1]. Normalize centrally so dependent plugins keep their legacy bodies.
    if ($provider_code === 'minimax' && agfo_ai_capability_is_chat($capability)) {
        $decoded_mm = json_decode($body, true);
        if (is_array($decoded_mm)) {
            $model_mm = strtolower(trim((string) (!empty($options['model']) ? $options['model'] : ($decoded_mm['model'] ?? ''))));
            $max_mm_tokens = strpos($model_mm, 'minimax-m3') !== false ? 524288 : 204800;

            if (isset($decoded_mm['max_tokens']) && !isset($decoded_mm['max_completion_tokens'])) {
                $decoded_mm['max_completion_tokens'] = $decoded_mm['max_tokens'];
                unset($decoded_mm['max_tokens']);
            }
            if (isset($decoded_mm['max_completion_tokens'])) {
                $decoded_mm['max_completion_tokens'] = max(1, min($max_mm_tokens, (int) $decoded_mm['max_completion_tokens']));
            }
            if (isset($decoded_mm['temperature'])) {
                $decoded_mm['temperature'] = max(0.0, min(2.0, (float) $decoded_mm['temperature']));
            }
            if (isset($decoded_mm['top_p'])) {
                $decoded_mm['top_p'] = max(0.0, min(1.0, (float) $decoded_mm['top_p']));
            }
            // MiniMax does not document OpenAI's multi-choice n field; remove it rather than
            // allowing legacy callers to cause an avoidable provider validation error.
            unset($decoded_mm['n']);
            $body = class_exists('AGFO_AIM_Request_Guard') // CHANGED 17.0.0: keep empty objects intact.
                ? AGFO_AIM_Request_Guard::reencode($body, $decoded_mm)
                : wp_json_encode($decoded_mm);
        }
    }

    // CHANGED: Normalize token-limit fields centrally for OpenAI and OpenRouter.
    // OpenAI chat-latest / GPT-4+ / GPT-5+ and OpenRouter-routed frontier models may reject max_tokens.
    if (in_array($provider_code, ['openai', 'openrouter'], true)) {
        $decoded = json_decode($body, true);
        if (is_array($decoded)) {
            $decoded_before  = $decoded; // CHANGED 17.0.0: re-encode only on change.
            $model_for_rules = !empty($options['model']) ? (string) $options['model'] : (string)($decoded['model'] ?? '');

            if (isset($decoded['max_tokens'])) {
                if ($provider_code === 'openrouter' || agfo_uses_max_completion_tokens($model_for_rules)) {
                    $decoded['max_completion_tokens'] = $decoded['max_tokens'];
                    unset($decoded['max_tokens']);
                    agfo_ai_manager_log_transport('AGFO_API_POST_TOKEN_FIELD_NORMALIZED', [
                        'provider' => $provider_code,
                        'model'    => $model_for_rules,
                        'from'     => 'max_tokens',
                        'to'       => 'max_completion_tokens',
                    ]);
                }
            }

            // CHANGED 16.17.2: Sampling guard is fail-safe for modern OpenAI families.
            // Dependent plugins may keep sending temperature. AGFO AI Manager removes sampling
            // controls centrally for models that use provider-default sampling (all GPT-5 family
            // identifiers and o-series), even when an older live probe says "supported". Probe
            // results are historical evidence, not permission to override a stricter current model
            // contract. OpenRouter receives the same protection after its vendor prefix is removed.
            $temp_status = function_exists('agfo_model_temperature_status')
                ? agfo_model_temperature_status($provider_code, $model_for_rules)
                : 'unknown';

            $uses_default_sampling = function_exists('agfo_model_uses_default_sampling')
                ? agfo_model_uses_default_sampling($provider_code, $model_for_rules)
                : false;

            if ($temp_status === 'unsupported' || $uses_default_sampling) {
                $params_to_strip = function_exists('agfo_openai_reasoning_unsupported_params')
                    ? agfo_openai_reasoning_unsupported_params()
                    : ['temperature'];
                $stripped = [];
                foreach ($params_to_strip as $param) {
                    if (array_key_exists($param, $decoded)) {
                        unset($decoded[$param]);
                        $stripped[] = $param;
                    }
                }
                if (!empty($stripped)) {
                    agfo_ai_manager_log_transport('AGFO_API_POST_UNSUPPORTED_PARAMS_REMOVED', [
                        'provider' => $provider_code,
                        'model'    => $model_for_rules,
                        'params'   => implode(',', $stripped),
                        'reason'   => $uses_default_sampling ? 'spec_default_sampling_model' : 'live_probe_temperature_unsupported',
                    ]);
                }
            }

            // CHANGED 17.0.0: an unconditional decode/encode turned empty JSON objects ({})
            // into arrays ([]) and broke tool schemas ("properties": {}). Only rewrite on change.
            if ($decoded !== $decoded_before) {
                $body = class_exists('AGFO_AIM_Request_Guard')
                    ? AGFO_AIM_Request_Guard::reencode($body, $decoded)
                    : wp_json_encode($decoded);
            }
        }
    }

    // CHANGED: OpenRouter Fusion is injected centrally so dependent AGFO plugins keep using the old agfo_api_post() flow.
    // CHANGED 16.6.0: Fusion artik yalnizca chat cagrilarinda uygulanir. Onceden kosulsuzdu;
    // muzik/ses gibi chat disi bir govdeye 'tools' enjekte edilirse saglayici HTTP 400 doner.
    // capability gecirmeyen TUM eski cagiricilar 'chat' sayilir, davranis birebir aynidir.
    if ($provider_code === 'openrouter' && agfo_ai_capability_is_chat($capability)) {
        $decoded = json_decode($body, true);
        if (is_array($decoded) && function_exists('agfo_openrouter_maybe_apply_fusion_tools')) {
            $fusion_before = $decoded;
            $decoded = agfo_openrouter_maybe_apply_fusion_tools($decoded, $options);
            if ($decoded !== $fusion_before) { // CHANGED 17.0.0: rewrite only when Fusion added tools.
                $body = class_exists('AGFO_AIM_Request_Guard')
                    ? AGFO_AIM_Request_Guard::reencode($body, $decoded)
                    : wp_json_encode($decoded);
            }
        }
    }

    $args = [
        'timeout'   => $timeout,
        'sslverify' => true,
        'headers'   => $headers,
        'body'      => $body,
    ];

    $managed_url = agfo_ai_manager_is_managed_ai_url($url);
    $guards      = agfo_ai_manager_connector_guard_callbacks();
    $use_shield  = $managed_url && !empty($guards);

    agfo_ai_manager_log_transport('AGFO_API_POST_START', [
        'provider'       => $provider_code ?: '-',
        'model'          => isset($options['model']) ? (string) $options['model'] : '-',
        'host'           => (string) wp_parse_url($url, PHP_URL_HOST),
        'managed_url'    => $managed_url ? 'yes' : 'no',
        'guard_detected' => !empty($guards) ? 'yes' : 'no',
    ]);

    // CHANGED 16.3.0: Harici izleyici pluginler icin genel kanca (progress callback'ten BAGIMSIZ).
    // Cagiran plugin bir 'agfo_ai_call_id' gecebilir; gecmezse merkezi olarak uretilir.
    $agfo_call_id = isset($options['agfo_call_id']) && $options['agfo_call_id'] !== ''
        ? (string) $options['agfo_call_id']
        : (function_exists('wp_generate_password') ? strtolower(wp_generate_password(12, false, false)) : substr(md5(uniqid('', true)), 0, 12));
    do_action('agfo_ai_call_started', [
        'call_id'  => $agfo_call_id,
        'provider' => $provider_code ?: '-',
        'model'    => isset($options['model']) ? (string) $options['model'] : '-',
        'source'   => isset($options['source']) ? (string) $options['source'] : '-',
        'timeout'  => $timeout,
        'host'     => (string) wp_parse_url($url, PHP_URL_HOST),
    ]);
    // Alt asamalari da izleyiciye ilet (progress callback'i sarmalayarak; cagiranin kendi callback'i KORUNUR).
    $__caller_progress = $progress;
    $progress = function ($stage, $detail = []) use ($__caller_progress, $agfo_call_id, $provider_code) {
        do_action('agfo_ai_call_stage', [
            'call_id'  => $agfo_call_id,
            'provider' => $provider_code ?: '-',
            'stage'    => (string) $stage,
            'detail'   => is_array($detail) ? $detail : [],
        ]);
        if ($__caller_progress) { try { $__caller_progress($stage, $detail); } catch (Exception $e) {} }
    };

    if ($progress) { try { $progress('sending', ['provider' => $provider_code, 'timeout' => $timeout]); } catch (Exception $e) {} } // CHANGED 16.2.0

    $runner = function () use ($url, $args) {
        return wp_remote_post($url, $args);
    };

    $response = $use_shield
        ? agfo_ai_manager_without_connector_guard(function () use ($runner) { return $runner(); })
        : $runner();

    if (is_wp_error($response)) {
        // CHANGED 16.6.0: cURL hata mesajlari sik sik tam URL icerir; Gemini'nin
        // chat_url'i anahtari sorgu dizesinde tasidigi icin mesaj redakte edilir.
        // Redaksiyon yalnizca log'a degil, cagiriciya donen metne de uygulanir.
        $err = agfo_redact_secrets($response->get_error_message());
        agfo_ai_manager_log_transport('AGFO_API_POST_ERROR', [
            'error' => $err,
        ]);
        do_action('agfo_ai_call_finished', ['call_id' => $agfo_call_id, 'provider' => $provider_code ?: '-', 'ok' => false, 'http_code' => 0, 'error' => $err]); // CHANGED 16.3.0
        return [
            'error' => $err,
            'stage' => 'http',
        ];
    }

    $http_code = (int) wp_remote_retrieve_response_code($response);
    $raw_body  = (string) wp_remote_retrieve_body($response);

    // NEW 16.17.2: Future-proof fallback. If a chat provider explicitly rejects
    // temperature, retry once without that field. This protects dependent plugins
    // that send temperature for a newly released model before capability metadata is
    // refreshed. Only an explicit provider-side temperature rejection triggers retry.
    if (agfo_ai_capability_is_chat($capability) && $http_code >= 400 && stripos($raw_body, 'temperature') !== false) {
        $temperature_rejected = (bool) preg_match(
            '/(?:unsupported|not\s+supported|does\s+not\s+support|invalid)[^\r\n]{0,120}temperature|temperature[^\r\n]{0,120}(?:unsupported|not\s+supported|does\s+not\s+support|invalid)/i',
            $raw_body
        );
        $retry_body = json_decode((string) ($args['body'] ?? ''), true);
        $retry_changed = false;

        if ($temperature_rejected && is_array($retry_body)) {
            if (array_key_exists('temperature', $retry_body)) {
                unset($retry_body['temperature']);
                $retry_changed = true;
            }
            if (isset($retry_body['generationConfig']) && is_array($retry_body['generationConfig']) && array_key_exists('temperature', $retry_body['generationConfig'])) {
                unset($retry_body['generationConfig']['temperature']);
                $retry_changed = true;
            }
        }

        if ($retry_changed) {
            $temperature_retry_used = true;
            $retry_args = $args;
            $retry_args['body'] = wp_json_encode($retry_body);
            agfo_ai_manager_log_transport('AGFO_API_POST_TEMPERATURE_RETRY', [
                'provider' => $provider_code ?: '-',
                'model'    => isset($options['model']) ? (string) $options['model'] : '-',
                'from_http_code' => $http_code,
            ]);

            $retry_runner = function () use ($url, $retry_args) {
                return wp_remote_post($url, $retry_args);
            };
            $retry_response = $use_shield
                ? agfo_ai_manager_without_connector_guard(function () use ($retry_runner) { return $retry_runner(); })
                : $retry_runner();

            if (!is_wp_error($retry_response)) {
                $response  = $retry_response;
                $http_code = (int) wp_remote_retrieve_response_code($retry_response);
                $raw_body  = (string) wp_remote_retrieve_body($retry_response);
            }
        }
    }

    // CHANGED 16.1.0: NVIDIA 202 Accepted -> requestId ile sonucu bekle (polling).
    if ($provider_code === 'nvidia' && $http_code === 202 && function_exists('agfo_nvidia_poll_result')) {
        $req_id = (string) wp_remote_retrieve_header($response, 'nvcf-reqid');
        if ($req_id === '') {
            $decoded_202 = json_decode($raw_body, true);
            if (is_array($decoded_202)) {
                $req_id = (string) ($decoded_202['requestId'] ?? $decoded_202['request_id'] ?? $decoded_202['id'] ?? '');
            }
        }
        agfo_ai_manager_log_transport('AGFO_API_POST_NVIDIA_202_POLL', [
            'request_id' => $req_id !== '' ? $req_id : '-',
            'budget'     => $timeout,
        ]);
        if ($req_id !== '') {
            if ($progress) { try { $progress('nvidia_queue', ['request_id' => $req_id]); } catch (Exception $e) {} } // CHANGED 16.2.0
            $polled = agfo_nvidia_poll_result($req_id, $headers, $timeout, $progress);
            if (isset($polled['http_code'])) {
                $http_code = (int) $polled['http_code'];
                $raw_body  = (string) $polled['body'];
                agfo_ai_manager_log_transport('AGFO_API_POST_NVIDIA_202_RESOLVED', [
                    'http_code' => $http_code,
                    'attempts'  => $polled['attempts'] ?? 0,
                ]);
            } else {
                agfo_ai_manager_log_transport('AGFO_API_POST_NVIDIA_202_TIMEOUT', [
                    'error' => $polled['error'] ?? 'bilinmiyor',
                ]);
                do_action('agfo_ai_call_finished', ['call_id' => $agfo_call_id, 'provider' => $provider_code, 'ok' => false, 'http_code' => 0, 'error' => $polled['error'] ?? 'NVIDIA async sonucu alinamadi']); // CHANGED 16.3.0
                return [
                    'error' => $polled['error'] ?? 'NVIDIA async sonucu alinamadi',
                    'stage' => $polled['stage'] ?? 'nvidia_poll',
                ];
            }
        }
    }

    // CHANGED 16.6.0: fal.ai kuyrugu — submit yaniti status_url dondurur, sonuc
    // hazir olana kadar beklenir. Genel agfo_async_poll_result() kullanilir.
    if ($provider_code === 'fal' && $http_code >= 200 && $http_code < 300) {
        $queued = json_decode($raw_body, true);
        if (is_array($queued) && !empty($queued['status_url']) && is_string($queued['status_url'])) {
            $poll_budget = isset($options['poll_budget']) ? (int) $options['poll_budget'] : 600;
            agfo_ai_manager_log_transport('AGFO_API_POST_FAL_QUEUED', [
                'request_id' => isset($queued['request_id']) ? (string) $queued['request_id'] : '-',
                'budget'     => $poll_budget,
            ]);
            if ($progress) { try { $progress('fal_queue', ['budget' => $poll_budget]); } catch (Exception $e) {} }

            $polled = agfo_async_poll_result(
                (string) $queued['status_url'],
                $headers,
                [
                    'budget'         => $poll_budget,
                    'max_budget'     => 900,
                    'interval'       => 3,
                    'stage'          => 'fal_poll',
                    'pending_codes'  => [202],
                    'status_field'   => 'status',
                    'pending_values' => ['IN_QUEUE', 'IN_PROGRESS'],
                    'result_field'   => 'response_url',
                ],
                $progress
            );

            if (isset($polled['http_code'])) {
                $http_code = (int) $polled['http_code'];
                $raw_body  = (string) $polled['body'];
                agfo_ai_manager_log_transport('AGFO_API_POST_FAL_RESOLVED', [
                    'http_code' => $http_code,
                    'attempts'  => $polled['attempts'] ?? 0,
                ]);
            } else {
                agfo_ai_manager_log_transport('AGFO_API_POST_FAL_TIMEOUT', [
                    'error' => $polled['error'] ?? 'bilinmiyor',
                ]);
                do_action('agfo_ai_call_finished', ['call_id' => $agfo_call_id, 'provider' => $provider_code, 'ok' => false, 'http_code' => 0, 'error' => $polled['error'] ?? 'fal.ai sonucu alinamadi']);
                return [
                    'error' => $polled['error'] ?? 'fal.ai sonucu alinamadi',
                    'stage' => $polled['stage'] ?? 'fal_poll',
                ];
            }
        }
    }

    if ($progress) { try { $progress('http_done', ['http_code' => $http_code]); } catch (Exception $e) {} } // CHANGED 16.2.0

    agfo_ai_manager_log_transport('AGFO_API_POST_DONE', [
        'http_code' => $http_code,
        'shield'    => $use_shield ? 'used' : 'not_used',
        'bytes'     => strlen($raw_body),
    ]);

    do_action('agfo_ai_call_finished', ['call_id' => $agfo_call_id, 'provider' => $provider_code ?: '-', 'ok' => ($http_code >= 200 && $http_code < 300), 'http_code' => $http_code, 'error' => '']); // CHANGED 16.3.0

    return [
        'http_code' => $http_code,
        'body'      => $raw_body,
        'stage'     => 'http',
        'transport' => $use_shield ? 'agfo_api_post_guard_shield' : 'agfo_api_post',
        'temperature_retry' => $temperature_retry_used,
    ];
}


/* ── OPENAI: max_completion_tokens KONTROLÜ ─────────────── */
function agfo_uses_max_completion_tokens(string $model): bool {
    $lower = strtolower(trim($model));
    if ($lower === '') return false;

    // CHANGED 16.4.0: OpenAI spesifikasyonu — Chat Completions'ta max_tokens DEPRECATED,
    // resmi parametre max_completion_tokens. Reasoning modeller (o-serisi, gpt-5 ailesi)
    // max_tokens'i HTTP 400 ile reddeder. Bu nedenle mantik tersine cevrildi:
    // pattern eslesen "modern" modeller degil, yalnizca legacy /v1/completions donemine
    // ait model adlari max_tokens'ta kalir; DIGER TUM MODELLER (bilinmeyen/yeni cikan
    // aileler dahil) max_completion_tokens kullanir. Boylece yeni model geldiginde
    // pattern listesi guncellenmeden dogru calisir.
    $legacy_patterns = [
        'text-davinci',
        'davinci',
        'babbage',
        'curie',
        'ada',
        'instruct',
        'gpt-3.5', // gpt-3.5-turbo max_tokens ile calisir; agfo_clean_model_list zaten filtreler.
    ];
    foreach ($legacy_patterns as $p) {
        // CHANGED 16.16.2: 'ada' gibi kisa legacy adlar alt-dize olarak arandiginda,
        // icinde tesadufen bu harf dizisi gecen yeni model adlarini yanlislikla legacy
        // sayip max_tokens'ta birakiyordu (sonuc: sessiz HTTP 400). Kisa adlarda
        // kelime siniri kontrolu uygulanir; uzun adlarda davranis birebir aynidir.
        if (strlen($p) <= 4) {
            if (preg_match('/(^|[^a-z0-9])' . preg_quote($p, '/') . '([^a-z0-9]|$)/', $lower)) return false;
            continue;
        }
        if (strpos($lower, $p) !== false) return false;
    }

    return true;
}

/* ── OPENAI: REASONING MODEL TESPITI (spec tabanli) ─────── */
// CHANGED 16.4.0: OpenAI reasoning modelleri (o1/o3/o4/o5..., gpt-5 ailesi) Chat
// Completions'ta reasoning davranisi ayrica siniflandirilir. gpt-5*-chat-latest gibi
// "chat" varyantlari reasoning DEGILDIR; temperature karari 16.17.2 tasima
// katmanindaki default-sampling korumasi tarafindan ayrica verilir.
function agfo_openai_model_is_reasoning(string $model): bool {
    $lower = strtolower(trim($model));
    if ($lower === '') return false;

    // chat varyantlari (gpt-5-chat-latest, gpt-5.2-chat-latest...) reasoning degildir.
    // Bu, temperature gonderilecegi anlamina gelmez; sampling korumasi tasima katmaninda ayridir.
    if (strpos($lower, 'chat') !== false && strpos($lower, 'chatgpt-') !== 0) return false;

    // o-serisi: o1, o1-mini, o3, o3-pro, o4-mini, o5... (kelime siniri ile; "gpt-4o" eslesmez)
    if (preg_match('/^o[0-9]+(-|$)/', $lower)) return true;

    // gpt-5 ailesi (gpt-5, gpt-5.2, gpt-5.4-mini, gpt-5-pro...) — chat varyantlari yukarida elendi.
    if (strpos($lower, 'gpt-5') === 0) return true;

    return false;
}

// CHANGED 16.4.0: Reasoning modellerin Chat Completions'ta reddettigi parametreler
// (kaynak: OpenAI/Azure resmi dokumani). max_tokens ayri normalizasyonla cozulur.
function agfo_openai_reasoning_unsupported_params(): array {
    return ['temperature', 'top_p', 'presence_penalty', 'frequency_penalty', 'logprobs', 'top_logprobs', 'logit_bias', 'n'];
}

/* ── MODEL UYUMLULUK METADATA KATMANI ───────────────────── */
function agfo_get_saved_model_capabilities(string $provider_code, string $model): array {
    $provider = sanitize_key($provider_code);
    $id       = trim($model);
    if ($provider === '' || $id === '') return [];

    $all = agfo_read_data_json();
    $caps = isset($all['model_capabilities']) && is_array($all['model_capabilities']) ? $all['model_capabilities'] : [];
    if (isset($caps[$provider][$id]) && is_array($caps[$provider][$id])) {
        return $caps[$provider][$id];
    }

    $id_lower = strtolower($id);
    if (isset($caps[$provider]) && is_array($caps[$provider])) {
        foreach ($caps[$provider] as $key => $row) {
            if (strtolower((string) $key) === $id_lower && is_array($row)) {
                return $row;
            }
        }
    }

    return [];
}

function agfo_save_model_capabilities(string $provider_code, string $model, array $capabilities): bool {
    $provider = sanitize_key($provider_code);
    $id       = trim($model);
    if ($provider === '' || $id === '') return false;

    $all = agfo_read_data_json();
    if (!isset($all['model_capabilities']) || !is_array($all['model_capabilities'])) {
        $all['model_capabilities'] = [];
    }
    if (!isset($all['model_capabilities'][$provider]) || !is_array($all['model_capabilities'][$provider])) {
        $all['model_capabilities'][$provider] = [];
    }

    $existing = isset($all['model_capabilities'][$provider][$id]) && is_array($all['model_capabilities'][$provider][$id])
        ? $all['model_capabilities'][$provider][$id]
        : [];

    $all['model_capabilities'][$provider][$id] = array_merge($existing, $capabilities, [
        'provider' => $provider,
        'id'       => $id,
        'updated_at' => current_time('mysql'),
    ]);

    return agfo_write_data_json($all);
}

function agfo_get_model_capability_defaults(string $provider_code, string $model): array {
    $provider = sanitize_key($provider_code);
    $id       = trim($model);
    $lower    = strtolower($id);

    $endpoint = 'chat';
    if ($provider === 'gemini') {
        $endpoint = 'generateContent';
    } elseif ($provider === 'claude') {
        $endpoint = 'messages';
    }

    return [
        'endpoint_type'        => $endpoint,
        'supports_chat'        => true,
        'supports_temperature' => true,
        'temperature_status'   => 'unknown',
        'docx_allowed'         => true,
        'compatibility_level'  => 'unknown',
        'compatibility_notes'  => ['Capability henuz canli diagnose ile dogrulanmadi.'],
        'capability_source'    => 'default_unknown',
        'probe_status'         => 'not_tested',
        'probed_at'            => '',
    ];
}

function agfo_get_model_capability_heuristics(string $provider_code, string $model): array {
    $provider = sanitize_key($provider_code);
    $id       = trim($model);
    $lower    = strtolower($id);
    $meta     = [];
    $notes    = [];

    if (preg_match('/image|vision|audio|realtime|embedding|embed|whisper|tts|transcribe|sora|video|veo/i', $lower)) {
        $meta['supports_chat']       = false;
        $meta['docx_allowed']        = false;
        $meta['compatibility_level'] = 'warn';
        $notes[] = 'Model adi metin chat disi modalite isareti tasiyor.';
    }

    if ($provider === 'openai' && (strpos($lower, 'codex') !== false || strpos($lower, 'computer-use') !== false)) {
        $meta['supports_chat']       = false;
        $meta['docx_allowed']        = false;
        $meta['compatibility_level'] = 'warn';
        $notes[] = 'Model adi genel metin chat yerine ozel kullanim sinifi gibi gorunuyor.';
    }

    if (!empty($notes)) {
        $meta['compatibility_notes'] = $notes;
        $meta['capability_source']   = 'heuristic_name_filter';
        $meta['probe_status']        = 'not_tested';
    }

    return $meta;
}

// CHANGED 16.17.7: One effective rule for models that only accept provider-default sampling.
// Historical probe metadata is preserved, but it can no longer make dependent plugins send
// unsupported sampling controls to current GPT-5 / o-series endpoints.
/**
 * Raw live-probe temperature evidence, without any policy applied.
 *
 * Added in 17.0.0 so the request guard can read probe evidence without recursing into
 * agfo_model_temperature_status(), which now reports the effective policy.
 */
function agfo_aim_probe_temperature_status(string $provider_code, string $model): string {
    $saved  = agfo_get_saved_model_capabilities($provider_code, $model);
    $status = (string) ($saved['temperature_status'] ?? 'unknown');
    $source = (string) ($saved['capability_source'] ?? '');
    // Only probe evidence counts; defaults, name heuristics and skipped probes do not.
    if (in_array($source, ['default_unknown', 'heuristic_name_filter', 'live_probe_not_supported_for_provider'], true)) return 'unknown';
    return in_array($status, ['supported', 'unsupported'], true) ? $status : 'unknown';
}

function agfo_model_uses_default_sampling(string $provider_code, string $model): bool {
    $provider_code = sanitize_key($provider_code);
    // CHANGED 17.0.0: one policy for every caller — the request guard decides. Unknown and
    // future OpenAI families are treated as provider-default until a live probe proves
    // otherwise; any provider that once refused temperature stays protected.
    if (class_exists('AGFO_AIM_Request_Guard')) {
        return AGFO_AIM_Request_Guard::sampling_policy($provider_code, $model) === 'provider_default';
    }
    if (!in_array($provider_code, ['openai', 'openrouter'], true)) return false;

    $model_id = strtolower(trim($model));
    if ($provider_code === 'openrouter' && strpos($model_id, '/') !== false) {
        $model_id = substr($model_id, strpos($model_id, '/') + 1);
    }

    return $model_id !== '' && (
        strpos($model_id, 'gpt-5') === 0
        || (bool) preg_match('/^o[0-9]+(?:-|$)/', $model_id)
    );
}

// CHANGED 16.17.7: Last-resort transport shield for legacy/dependent AGFO plugins that still
// call wp_remote_post() directly instead of agfo_api_post(). Scope is intentionally narrow:
// only OpenAI/OpenRouter chat-completions requests carrying a GPT-5/o-series model are touched.
// Capability probes opt out with X-AGFO-Temperature-Probe so intelligence data remains genuine.
function agfo_ai_manager_filter_http_request_sampling(array $args, string $url): array {
    $host = strtolower((string) wp_parse_url($url, PHP_URL_HOST));
    $path = strtolower((string) wp_parse_url($url, PHP_URL_PATH));

    $provider_code = '';
    if ($host === 'api.openai.com' && strpos($path, '/v1/chat/completions') !== false) {
        $provider_code = 'openai';
    } elseif ($host === 'openrouter.ai' && strpos($path, '/api/v1/chat/completions') !== false) {
        $provider_code = 'openrouter';
    } else {
        return $args;
    }

    $headers = isset($args['headers']) && is_array($args['headers']) ? $args['headers'] : [];
    foreach ($headers as $header_name => $header_value) {
        // CHANGED 17.0.0: the generic raw-probe header opts out as well.
        if (in_array(strtolower((string) $header_name), ['x-agfo-temperature-probe', 'x-agfo-raw-probe'], true) && (string) $header_value === '1') {
            return $args;
        }
    }

    $body = $args['body'] ?? '';
    if (is_array($body)) {
        $decoded = $body;
    } elseif (is_string($body) && $body !== '') {
        $decoded = json_decode($body, true);
    } else {
        return $args;
    }
    if (!is_array($decoded)) return $args;

    $model = (string) ($decoded['model'] ?? '');
    if (!agfo_model_uses_default_sampling($provider_code, $model)) return $args;

    $params_to_strip = function_exists('agfo_openai_reasoning_unsupported_params')
        ? agfo_openai_reasoning_unsupported_params()
        : ['temperature'];
    $stripped = [];
    foreach ($params_to_strip as $param) {
        if (array_key_exists($param, $decoded)) {
            unset($decoded[$param]);
            $stripped[] = $param;
        }
    }
    if (empty($stripped)) return $args;

    $args['body'] = is_array($body) ? $decoded : wp_json_encode($decoded);
    if (function_exists('agfo_ai_manager_log_transport')) {
        agfo_ai_manager_log_transport('AGFO_HTTP_ARGS_UNSUPPORTED_PARAMS_REMOVED', [
            'provider' => $provider_code,
            'model'    => $model,
            'params'   => implode(',', $stripped),
            'reason'   => 'direct_wp_http_default_sampling_guard',
        ]);
    }
    return $args;
}

if (function_exists('add_filter')) {
    add_filter('http_request_args', 'agfo_ai_manager_filter_http_request_sampling', 9, 2);
}

function agfo_get_model_capabilities(string $provider_code, string $model): array {
    $base   = agfo_get_model_capability_defaults($provider_code, $model);
    $heur   = agfo_get_model_capability_heuristics($provider_code, $model);
    $saved  = agfo_get_saved_model_capabilities($provider_code, $model);

    $meta = array_merge($base, $heur, $saved);

    $meta['supports_chat']        = !empty($meta['supports_chat']);
    $meta['supports_temperature'] = !empty($meta['supports_temperature']);
    // CHANGED 16.17.7: Effective contract wins over stale successful temperature probes.
    if (agfo_model_uses_default_sampling($provider_code, $model)) {
        $meta['supports_temperature'] = false;
    }
    $meta['docx_allowed']         = !empty($meta['docx_allowed']);
    $meta['endpoint_type']        = (string) ($meta['endpoint_type'] ?? 'chat');
    $meta['temperature_status']   = (string) ($meta['temperature_status'] ?? 'unknown');
    $meta['compatibility_level']  = (string) ($meta['compatibility_level'] ?? 'unknown');
    $meta['probe_status']         = (string) ($meta['probe_status'] ?? 'not_tested');
    if (!isset($meta['compatibility_notes']) || !is_array($meta['compatibility_notes'])) {
        $meta['compatibility_notes'] = [];
    }

    // NEW 17.0.0: effective transport contract from the central request guard.
    // sampling_policy  — 'provider_default' means temperature/top_p are removed before sending.
    // transport_route  — 'chat' | 'responses_bridge' | 'not_chat' | 'unavailable'.
    // NEW 17.0.0: probes before 17.0.0 gave reasoning models only 8 output tokens; the model
    // spent them thinking and the provider answered "max_tokens or model output limit was
    // reached". That proves the chat endpoint works, so the stale "chat ✗" is corrected here.
    if (empty($meta['supports_chat'])) {
        $evidence = strtolower(
            (is_array($meta['compatibility_notes']) ? implode(' ', array_map('strval', $meta['compatibility_notes'])) : '')
            . ' ' . (is_string($saved['compatibility_notes'] ?? null) ? $saved['compatibility_notes'] : '')
            . ' ' . (is_string($meta['probe_chat_error'] ?? null) ? $meta['probe_chat_error'] : '')
        );
        if (strpos($evidence, 'max_tokens or model output limit') !== false || strpos($evidence, 'output limit was reached') !== false) {
            $meta['supports_chat']       = true;
            $meta['docx_allowed']        = true;
            $meta['endpoint_type']       = 'chat';
            $meta['compatibility_level'] = 'ok';
            $meta['compatibility_notes'] = ['Eski test token sınırına takılmıştı; chat ucu çalışıyor.'];
        }
    }

    if (class_exists('AGFO_AIM_Request_Guard')) {
        $policy = AGFO_AIM_Request_Guard::sampling_policy($provider_code, $model);
        $route  = AGFO_AIM_Request_Guard::model_route($provider_code, $model);
        $meta['sampling_policy'] = $policy;
        if ($policy === 'provider_default') {
            $meta['supports_temperature'] = false;
        }
        if ($route === 'responses' && apply_filters('agfo_ai_responses_bridge_enabled', true, $model)) {
            // Served transparently through /v1/responses; callers keep the chat body.
            $meta['transport_route']     = 'responses_bridge';
            $meta['supports_chat']       = true;
            $meta['docx_allowed']        = true;
            $meta['endpoint_type']       = 'responses';
            $meta['compatibility_level'] = 'ok';
            $meta['compatibility_notes'][] = 'Responses API köprüsü ile chat çağrıları otomatik çalışır.';
        } elseif ($route === 'unavailable') {
            $meta['transport_route']     = 'unavailable';
            $meta['supports_chat']       = false;
            $meta['docx_allowed']        = false;
            $meta['compatibility_level'] = 'blocked';
            $meta['compatibility_notes'][] = 'Sağlayıcı bu modele erişimi reddetti; istekler yedek modele yönlendirilir.';
        } elseif ($route === 'not_chat') {
            $meta['transport_route'] = 'not_chat';
            $meta['supports_chat']   = false;
            $meta['docx_allowed']    = false;
        } else {
            $meta['transport_route'] = 'chat';
        }
    }

    return $meta;
}

function agfo_model_supports_chat(string $provider_code, string $model): bool {
    $meta = agfo_get_model_capabilities($provider_code, $model);
    return !empty($meta['supports_chat']);
}

function agfo_model_supports_temperature(string $provider_code, string $model): bool {
    $meta = agfo_get_model_capabilities($provider_code, $model);
    return !empty($meta['supports_temperature']);
}

// CHANGED 16.7.0: Uc degerli temperature durumu. 'supported' / 'unsupported' YALNIZCA canli
// probe yazmissa doner; probe edilmemis model her zaman 'unknown' doner ve cagiran taraf
// (agfo_api_post) spec kuralina duser. Boolean agfo_model_supports_temperature() bu ayrimi
// yapamiyordu (varsayilan true, kanit ile ayirt edilemiyordu).
// FIX 16.15.2: Geriye uyumluluk shim'i. 16.7.0 oncesi tek argumanli (yalnizca model
// kimligi) cagiran eklentiler (ornek: agfo-flow-rollout-tracker) iki zorunlu parametreli
// imza yuzunden fatal ArgumentCountError uretiyordu. Ikinci parametre opsiyonel yapildi;
// tek argumanli cagrida ilk parametre model kimligi kabul edilir ve tum saglayicilarin
// probe kanitlari taranir. Kanit yoksa guvenli varsayilan 'unknown' doner (spec kurali).
function agfo_model_temperature_status(string $provider_code, ?string $model = null): string {
    if ($model === null) {
        return agfo_model_temperature_status_by_model($provider_code);
    }
    // CHANGED 17.0.0: a provider-default model always reports 'unsupported', so callers that
    // decide before building the body never add temperature for it.
    if (class_exists('AGFO_AIM_Request_Guard')
        && AGFO_AIM_Request_Guard::sampling_policy($provider_code, $model) === 'provider_default') {
        return 'unsupported';
    }
    $meta   = agfo_get_model_capabilities($provider_code, $model);
    $status = (string) ($meta['temperature_status'] ?? 'unknown');
    return in_array($status, ['supported', 'unsupported'], true) ? $status : 'unknown';
}

// NEW 16.15.2: Saglayici bilinmeden yalnizca model kimligi ile durum sorgusu.
// data.json model_capabilities altindaki tum saglayicilarda buyuk/kucuk harf duyarsiz
// eslesme aranir; ilk 'supported'/'unsupported' probe kaniti doner, yoksa 'unknown'.
function agfo_model_temperature_status_by_model(string $model): string {
    $id = trim($model);
    if ($id === '') return 'unknown';
    $id_lower = strtolower($id);

    $all  = agfo_read_data_json();
    $caps = (isset($all['model_capabilities']) && is_array($all['model_capabilities']))
        ? $all['model_capabilities'] : [];

    foreach ($caps as $rows) {
        if (!is_array($rows)) continue;
        foreach ($rows as $key => $row) {
            if (!is_array($row)) continue;
            if (strtolower((string) $key) !== $id_lower) continue;
            $status = (string) ($row['temperature_status'] ?? 'unknown');
            if (in_array($status, ['supported', 'unsupported'], true)) {
                return $status;
            }
        }
    }
    return 'unknown';
}

function agfo_model_is_docx_allowed(string $provider_code, string $model): bool {
    $meta = agfo_get_model_capabilities($provider_code, $model);
    return !empty($meta['docx_allowed']);
}

function agfo_get_models_for_provider_public(string $provider_code, array $args = []): array {
    $provider = sanitize_key($provider_code);
    if ($provider === '') return [];

    $all_data   = agfo_read_data_json();
    $all_models = (isset($all_data['models']) && is_array($all_data['models'])) ? $all_data['models'] : [];
    $models     = get_option('agfo_models_' . $provider, []);
    if (empty($models)) $models = $all_models[$provider] ?? [];
    if (!is_array($models)) return [];

    $chat_only = !empty($args['chat_only']);
    $docx_only = !empty($args['docx_only']);
    $out = [];

    foreach ($models as $model) {
        $id = '';
        if (is_string($model)) {
            $id = trim($model);
        } elseif (is_array($model)) {
            $id = trim((string)($model['id'] ?? $model['name'] ?? ''));
        }
        if ($id === '') continue;

        $meta = agfo_get_model_capabilities($provider, $id);
        if ($chat_only && empty($meta['supports_chat'])) continue;
        if ($docx_only && empty($meta['docx_allowed'])) continue;

        $row = is_array($model) ? $model : ['id' => $id, 'name' => $id];
        $row = array_merge($row, $meta);
        $out[] = $row;
    }

    return $out;
}

/* ── MODEL FİLTRELEME ───────────────────────────────────── */
// CHANGED 16.5.0: Sabit regex 8 kategoriye bolundu; ayarlardan acilip kapatilabilir.
// Kategorilerin birlesimi eski tek-parca regex ile BIREBIR aynidir (golden test ile dogrulandi).
function agfo_model_filter_categories(): array {
    return [
        'vision' => [
            'label'   => 'Görüntü anlama (vision/multimodal)',
            'pattern' => 'vision|multimodal|pixtral|internvl|llava|qwen.*vl',
        ],
        'audio' => [
            'label'   => 'Ses modelleri (TTS/STT/realtime)',
            'pattern' => '\btts\b|tts-|voice|sonic|playai|voxtral|whisper|transcribe|\bstt\b|diarize|realtime|\baudio\b',
        ],
        'image_gen' => [
            'label'   => 'Görsel üretim',
            'pattern' => 'dall-e|dalle|imagen|\bflux|stable-diffusion|sdxl|seedream|bria|ideogram|dreamshaper|juggernaut|gpt-image-|chatgpt-image|^models\/imagen|^models\/nano-banana',
        ],
        'video_gen' => [
            'label'   => 'Video/müzik üretim',
            // CHANGED 16.6.0: Desen saglayici onekinden bagimsiz hale getirildi.
            // Onceden ^models/lyria yalnizca Gemini bicimini yakaliyor, OpenRouter'in
            // google/lyria-3-pro-preview bicimini kaciriyordu; ayni model saglayiciya
            // gore listede gorunup gorunmuyordu.
            'pattern' => '\bsora|\bveo|kling|seedance|\bvidu|pixverse|\bwan2|\blyria|^models\/veo',
        ],
        'embedding' => [
            'label'   => 'Embedding/rerank',
            'pattern' => 'embedding|\bembed\b|bge-|\be5-|gte-|text2vec|sentence-transformer|mxbai-rerank|clip-vit|^models\/embedding',
        ],
        'moderation' => [
            'label'   => 'Güvenlik/moderasyon',
            'pattern' => 'guard|moderation|safeguard|virtue|prompt-guard',
        ],
        'niche' => [
            'label'   => 'Niş/özel amaçlı (OCR, research, router...)',
            'pattern' => '\bocr\b|paddleocr|prover|llemma|\/auto$|\/bodybuilder$|\/router$|\bmoa-|search-api|search-preview|\baqa\b|deep-research|computer-use|robotics|^models\/aqa$|^models\/deep-research|^models\/gemini-robotics',
        ],
        'legacy_openai' => [
            'label'   => 'Eski OpenAI modelleri ve tarihli kopyalar',
            'pattern' => '^babbage-|^davinci-|^gpt-3\.5-|^gpt-4$|^gpt-4-0613|^gpt-4-turbo|gpt-4o-20[0-9]{2}-|gpt-4o-mini-20[0-9]{2}-',
        ],
    ];
}

// CHANGED 16.5.0: Filtre semalari — ekrani kalabaliklastirmamak icin tek select.
function agfo_model_filter_presets(): array {
    $all = array_keys(agfo_model_filter_categories());
    return [
        'strict'    => [ 'label' => 'Sıkı (Varsayılan) — tüm filtreler açık',                    'categories' => $all ],
        'chat_only' => [ 'label' => 'Yalnızca Chat-Dışını Gizle — niş ve eski modeller görünür', 'categories' => ['vision', 'audio', 'image_gen', 'video_gen', 'embedding', 'moderation'] ],
        'all'       => [ 'label' => 'Her Şeyi Göster — filtre yok',                              'categories' => [] ],
        'custom'    => [ 'label' => 'Özel — kategorileri tek tek seç',                           'categories' => null ],
    ];
}

// CHANGED 16.5.0: Kayitli filtre ayarlarini cozer. Donen deger:
// ['preset'=>..., 'categories'=>aktif kategori id listesi, 'whitelist'=>istisna satirlari]
function agfo_get_model_filter_settings(): array {
    $all_ids = array_keys(agfo_model_filter_categories());
    $saved   = get_option('agfo_model_filter_settings', []);
    if (!is_array($saved)) $saved = [];

    $presets = agfo_model_filter_presets();
    $preset  = isset($saved['preset']) && isset($presets[$saved['preset']]) ? (string) $saved['preset'] : 'strict';

    if ($preset === 'custom') {
        $custom = isset($saved['custom_categories']) && is_array($saved['custom_categories']) ? $saved['custom_categories'] : $all_ids;
        $active = array_values(array_intersect($all_ids, array_map('strval', $custom)));
    } else {
        $active = $presets[$preset]['categories'];
    }

    $whitelist = [];
    if (!empty($saved['whitelist']) && is_string($saved['whitelist'])) {
        foreach (preg_split('/[\r\n,]+/', $saved['whitelist']) as $line) {
            $line = strtolower(trim($line));
            if ($line !== '') $whitelist[] = $line;
        }
    }

    return ['preset' => $preset, 'categories' => $active, 'whitelist' => $whitelist];
}

function agfo_clean_model_list(array $models): array {
    // CHANGED 16.5.0: Sabit regex yerine ayar tabanli. Varsayilan (strict) davranis
    // eski surumle BIREBIR aynidir. Istisna listesindeki adlar her durumda gecer
    // (buyuk/kucuk harf duyarsiz PARCA eslesmesi).
    $settings = agfo_get_model_filter_settings();
    $cats     = agfo_model_filter_categories();

    $parts = [];
    foreach ($settings['categories'] as $cat_id) {
        if (isset($cats[$cat_id])) $parts[] = $cats[$cat_id]['pattern'];
    }
    $pattern   = empty($parts) ? '' : '/' . implode('|', $parts) . '/i';
    $whitelist = $settings['whitelist'];

    $cleaned = [];
    foreach ($models as $m) {
        if (!is_string($m) || $m === '') continue;

        $pass = ($pattern === '' || !preg_match($pattern, $m));

        if (!$pass && !empty($whitelist)) {
            $m_lower = strtolower($m);
            foreach ($whitelist as $w) {
                if (strpos($m_lower, $w) !== false) { $pass = true; break; }
            }
        }

        if ($pass) $cleaned[] = $m;
    }
    return array_values($cleaned);
}

/* ── BENCHMARK ──────────────────────────────────────────── */
function agfo_get_benchmark_sources(): array {
    return [
        'lmsys'              => ['name' => 'LMSYS Chatbot Arena',  'weight' => 0.40, 'icon' => '🏆'],
        'openllm'            => ['name' => 'Open LLM Leaderboard', 'weight' => 0.30, 'icon' => '📊'],
        'artificialanalysis' => ['name' => 'Artificial Analysis',  'weight' => 0.30, 'icon' => '🔬'],
    ];
}

function agfo_get_known_benchmarks(): array {
    return [
        'gpt-4o'                     => ['lmsys' => 1314, 'openllm' => 88, 'artificialanalysis' => 90],
        'gpt-4o-mini'                => ['lmsys' => 1281, 'openllm' => 82, 'artificialanalysis' => 85],
        'gpt-4.1'                    => ['lmsys' => 1320, 'openllm' => 89, 'artificialanalysis' => 91],
        'gpt-4.1-mini'               => ['lmsys' => 1290, 'openllm' => 84, 'artificialanalysis' => 86],
        'gpt-4.1-nano'               => ['lmsys' => 1260, 'openllm' => 79, 'artificialanalysis' => 81],
        'o1'                         => ['lmsys' => 1348, 'openllm' => 92, 'artificialanalysis' => 94],
        'o1-pro'                     => ['lmsys' => 1360, 'openllm' => 94, 'artificialanalysis' => 95],
        'o3'                         => ['lmsys' => 1370, 'openllm' => 95, 'artificialanalysis' => 96],
        'o3-mini'                    => ['lmsys' => 1320, 'openllm' => 87, 'artificialanalysis' => 89],
        'o4-mini'                    => ['lmsys' => 1330, 'openllm' => 88, 'artificialanalysis' => 90],
        'gpt-5'                      => ['lmsys' => 1420, 'openllm' => 97, 'artificialanalysis' => 98],
        'gpt-5-mini'                 => ['lmsys' => 1360, 'openllm' => 92, 'artificialanalysis' => 93],
        'gpt-5-nano'                 => ['lmsys' => 1300, 'openllm' => 84, 'artificialanalysis' => 85],
        'gpt-5.1'                    => ['lmsys' => 1390, 'openllm' => 95, 'artificialanalysis' => 96],
        'gpt-5.2'                    => ['lmsys' => 1395, 'openllm' => 95, 'artificialanalysis' => 96],
        'gpt-5.4'                    => ['lmsys' => 1420, 'openllm' => 97, 'artificialanalysis' => 98],
        'gpt-5.4-mini'               => ['lmsys' => 1360, 'openllm' => 92, 'artificialanalysis' => 93],
        'gpt-5.4-nano'               => ['lmsys' => 1300, 'openllm' => 84, 'artificialanalysis' => 85],
        'gpt-5.5'                    => ['lmsys' => 1430, 'openllm' => 98, 'artificialanalysis' => 98],

        'claude-opus'                => ['lmsys' => 1380, 'openllm' => 95, 'artificialanalysis' => 96],
        'claude-sonnet'              => ['lmsys' => 1345, 'openllm' => 91, 'artificialanalysis' => 93],
        'claude-haiku'               => ['lmsys' => 1210, 'openllm' => 78, 'artificialanalysis' => 80],
        'claude-3-5-sonnet-20241022' => ['lmsys' => 1341, 'openllm' => 90, 'artificialanalysis' => 92],
        'claude-3.5-sonnet'          => ['lmsys' => 1332, 'openllm' => 89, 'artificialanalysis' => 91],
        'claude-3.7-sonnet'          => ['lmsys' => 1345, 'openllm' => 91, 'artificialanalysis' => 93],
        'claude-3-haiku-20240307'    => ['lmsys' => 1181, 'openllm' => 78, 'artificialanalysis' => 80],

        'gemini-3.1-flash-lite'      => ['lmsys' => 1300, 'openllm' => 85, 'artificialanalysis' => 86],
        'gemini-3.1-pro'             => ['lmsys' => 1345, 'openllm' => 92, 'artificialanalysis' => 93],
        'gemini-3-flash'             => ['lmsys' => 1310, 'openllm' => 88, 'artificialanalysis' => 89],
        'gemini-3-pro'               => ['lmsys' => 1340, 'openllm' => 91, 'artificialanalysis' => 92],
        'gemini-2.5-flash'           => ['lmsys' => 1310, 'openllm' => 88, 'artificialanalysis' => 89],
        'gemini-2.5-flash-lite'      => ['lmsys' => 1280, 'openllm' => 82, 'artificialanalysis' => 84],
        'gemini-2.5-pro'             => ['lmsys' => 1335, 'openllm' => 90, 'artificialanalysis' => 92],
        'gemini-2.0-flash'           => ['lmsys' => 1295, 'openllm' => 86, 'artificialanalysis' => 87],
        'gemini-2.0-flash-lite'      => ['lmsys' => 1265, 'openllm' => 80, 'artificialanalysis' => 82],

        'deepseek-r1'                => ['lmsys' => 1338, 'openllm' => 89, 'artificialanalysis' => 90],
        'deepseek-reasoner'          => ['lmsys' => 1338, 'openllm' => 89, 'artificialanalysis' => 90],
        'deepseek-v4-pro'            => ['lmsys' => 1320, 'openllm' => 87, 'artificialanalysis' => 88],
        'deepseek-v4-flash'          => ['lmsys' => 1280, 'openllm' => 82, 'artificialanalysis' => 84],
        'deepseek-v4'                => ['lmsys' => 1315, 'openllm' => 86, 'artificialanalysis' => 87],
        'deepseek-v3'                => ['lmsys' => 1310, 'openllm' => 85, 'artificialanalysis' => 86],
        'deepseek-chat'              => ['lmsys' => 1279, 'openllm' => 83, 'artificialanalysis' => 84],

        'qwen3-235b-a22b-thinking'   => ['lmsys' => 1350, 'openllm' => 91, 'artificialanalysis' => 92],
        'qwen3-235b-a22b-2507'       => ['lmsys' => 1325, 'openllm' => 87, 'artificialanalysis' => 88],
        'qwen3-235b-a22b'            => ['lmsys' => 1320, 'openllm' => 86, 'artificialanalysis' => 88],
        'qwen3-235b'                 => ['lmsys' => 1320, 'openllm' => 86, 'artificialanalysis' => 88],
        'qwen3-max-thinking'         => ['lmsys' => 1360, 'openllm' => 91, 'artificialanalysis' => 92],
        'qwen3-max'                  => ['lmsys' => 1330, 'openllm' => 88, 'artificialanalysis' => 89],

        'qwen3.6-max'                => ['lmsys' => 1335, 'openllm' => 89, 'artificialanalysis' => 90],
        'qwen3.6-plus'               => ['lmsys' => 1320, 'openllm' => 87, 'artificialanalysis' => 88],
        'qwen3.6-flash'              => ['lmsys' => 1295, 'openllm' => 83, 'artificialanalysis' => 85],
        'qwen3.6-35b'                => ['lmsys' => 1275, 'openllm' => 81, 'artificialanalysis' => 83],
        'qwen3.6-27b'                => ['lmsys' => 1265, 'openllm' => 80, 'artificialanalysis' => 82],

        'qwen3.5-397b'               => ['lmsys' => 1330, 'openllm' => 89, 'artificialanalysis' => 90],
        'qwen3.5-122b'               => ['lmsys' => 1310, 'openllm' => 86, 'artificialanalysis' => 87],
        'qwen3.5-plus'               => ['lmsys' => 1305, 'openllm' => 85, 'artificialanalysis' => 86],
        'qwen3.5-flash'              => ['lmsys' => 1265, 'openllm' => 80, 'artificialanalysis' => 82],
        'qwen3.5-35b'                => ['lmsys' => 1260, 'openllm' => 79, 'artificialanalysis' => 81],
        'qwen3.5-27b'                => ['lmsys' => 1250, 'openllm' => 78, 'artificialanalysis' => 80],

        'qwen3-coder-flash'          => ['lmsys' => 1285, 'openllm' => 82, 'artificialanalysis' => 84],
        'qwen3-coder'                => ['lmsys' => 1320, 'openllm' => 87, 'artificialanalysis' => 88],
        'qwen3-next-80b'             => ['lmsys' => 1300, 'openllm' => 85, 'artificialanalysis' => 86],
        'qwen3-32b'                  => ['lmsys' => 1260, 'openllm' => 80, 'artificialanalysis' => 82],
        'qwen3-30b'                  => ['lmsys' => 1260, 'openllm' => 80, 'artificialanalysis' => 82],
        'qwen3-14b'                  => ['lmsys' => 1210, 'openllm' => 74, 'artificialanalysis' => 76],
        'qwen3-8b'                   => ['lmsys' => 1180, 'openllm' => 70, 'artificialanalysis' => 72],
        'qwen-plus'                  => ['lmsys' => 1290, 'openllm' => 83, 'artificialanalysis' => 84],
        'qwen-turbo'                 => ['lmsys' => 1230, 'openllm' => 75, 'artificialanalysis' => 76],

        'llama-4-maverick'           => ['lmsys' => 1300, 'openllm' => 84, 'artificialanalysis' => 86],
        'llama-4-scout'              => ['lmsys' => 1270, 'openllm' => 80, 'artificialanalysis' => 82],
        'llama-3.3-70b-instruct'     => ['lmsys' => 1253, 'openllm' => 82, 'artificialanalysis' => 83],
        'llama-3.1-405b-instruct'    => ['lmsys' => 1276, 'openllm' => 84, 'artificialanalysis' => 85],
        'llama-3.1-70b'              => ['lmsys' => 1245, 'openllm' => 80, 'artificialanalysis' => 82],

        'kimi-k2-thinking'           => ['lmsys' => 1340, 'openllm' => 90, 'artificialanalysis' => 91],
        'kimi-k2'                    => ['lmsys' => 1295, 'openllm' => 84, 'artificialanalysis' => 85],

        'glm-5'                      => ['lmsys' => 1280, 'openllm' => 82, 'artificialanalysis' => 84],
        'glm-4.7-flash'              => ['lmsys' => 1250, 'openllm' => 77, 'artificialanalysis' => 79],
        'glm-4.7'                    => ['lmsys' => 1250, 'openllm' => 76, 'artificialanalysis' => 78],
        'glm-4.6'                    => ['lmsys' => 1240, 'openllm' => 74, 'artificialanalysis' => 76],
        'glm-4.5'                    => ['lmsys' => 1230, 'openllm' => 72, 'artificialanalysis' => 74],

        'mistral-medium'             => ['lmsys' => 1310, 'openllm' => 87, 'artificialanalysis' => 88],
        'mistral-large'              => ['lmsys' => 1300, 'openllm' => 86, 'artificialanalysis' => 87],
        'mistral-small'              => ['lmsys' => 1245, 'openllm' => 76, 'artificialanalysis' => 78],
        'codestral'                  => ['lmsys' => 1260, 'openllm' => 80, 'artificialanalysis' => 82],
        'devstral'                   => ['lmsys' => 1255, 'openllm' => 79, 'artificialanalysis' => 81],

        'grok-4.3'                   => ['lmsys' => 1330, 'openllm' => 88, 'artificialanalysis' => 89],
        'grok'                       => ['lmsys' => 1300, 'openllm' => 85, 'artificialanalysis' => 86],

        'minimax-m2.7'               => ['lmsys' => 1260, 'openllm' => 78, 'artificialanalysis' => 80],
        'minimax-m2'                 => ['lmsys' => 1240, 'openllm' => 74, 'artificialanalysis' => 76],
        'step-3.5-flash'             => ['lmsys' => 1260, 'openllm' => 78, 'artificialanalysis' => 80],
        'seed-2.0'                   => ['lmsys' => 1275, 'openllm' => 80, 'artificialanalysis' => 82],
        'seed-1.6-flash'             => ['lmsys' => 1245, 'openllm' => 76, 'artificialanalysis' => 78],
        'mimo-v2-flash'              => ['lmsys' => 1240, 'openllm' => 75, 'artificialanalysis' => 77],
        'reka-flash'                 => ['lmsys' => 1235, 'openllm' => 74, 'artificialanalysis' => 76],
        'nova-lite'                  => ['lmsys' => 1230, 'openllm' => 74, 'artificialanalysis' => 75],
        'nova-micro'                 => ['lmsys' => 1190, 'openllm' => 70, 'artificialanalysis' => 72],

        'gpt-oss-120b'               => ['lmsys' => 1280, 'openllm' => 84, 'artificialanalysis' => 85],
        'gpt-oss-20b'                => ['lmsys' => 1220, 'openllm' => 76, 'artificialanalysis' => 78],
    ];
}

function agfo_calculate_combined_score(string $provider, string $model): ?array {
    $known   = agfo_get_known_benchmarks();
    $sources = agfo_get_benchmark_sources();
    $m_lower = strtolower($model);

    $bench = null;

    if (isset($known[$model])) {
        $bench = $known[$model];
    } elseif (isset($known[$m_lower])) {
        $bench = $known[$m_lower];
    } else {
        foreach ($known as $key => $data) {
            $key_lower = strtolower($key);
            if (
                strpos($m_lower, $key_lower) !== false ||
                strpos($key_lower, $m_lower) !== false
            ) {
                $bench = $data;
                break;
            }
        }
    }

    if (!$bench) return null;

    $scores = [];
    $ws     = 0.0;
    $tw     = 0.0;

    foreach (['lmsys', 'openllm', 'artificialanalysis'] as $src) {
        if (!isset($bench[$src])) continue;

        $score = ($src === 'lmsys')
            ? min(100, max(0, (($bench[$src] - 1000) / 400) * 100))
            : (float) $bench[$src];

        $scores[$src] = $score;
        $ws          += $score * $sources[$src]['weight'];
        $tw          += $sources[$src]['weight'];
    }

    if (empty($scores)) return null;

    $final = ($tw > 0) ? (int) round($ws / $tw) : 0;

    return [
        'final_score' => $final,
        'tier'        => agfo_score_to_tier($final),
        'sources'     => $scores,
    ];
}

function agfo_score_to_tier(int $score): string {
    if ($score >= 88) return 'S';
    if ($score >= 80) return 'A';
    if ($score >= 70) return 'B';
    if ($score >= 60) return 'C';
    return 'D';
}


/* -- OPENROUTER FUSION -------------------------------------------------- */
if (!function_exists('agfo_openrouter_get_fusion_profiles')) {
    function agfo_openrouter_get_fusion_profiles(): array {
        return [
            'economic' => [
                'label' => 'Ekonomik Fusion',
                'description' => 'Günlük araştırma, hızlı eleştiri ve düşük maliyetli çoklu perspektif.',
                'analysis_models' => [
                    '~google/gemini-flash-latest',
                    'deepseek/deepseek-v3.2',
                    '~moonshotai/kimi-latest',
                ],
                'max_tool_calls' => 6,
            ],
            'balanced' => [
                'label' => 'Dengeli Fusion',
                'description' => 'AGFO rapor analizi, standart mukayesesi ve kök neden eleştirisi için dengeli panel.',
                'analysis_models' => [
                    '~google/gemini-pro-latest',
                    'deepseek/deepseek-v3.2',
                    '~moonshotai/kimi-latest',
                ],
                'max_tool_calls' => 8,
            ],
            'critical_audit' => [
                'label' => 'Kritik Denetim Fusion',
                'description' => 'Major/minor kararları, standart yorumu ve yüksek riskli denetim değerlendirmeleri.',
                'analysis_models' => [
                    '~anthropic/claude-opus-latest',
                    '~openai/gpt-latest',
                    '~google/gemini-pro-latest',
                    'deepseek/deepseek-v3.2',
                ],
                'max_tool_calls' => 10,
            ],
            'research_max' => [
                'label' => 'Güçlü Araştırma Fusion',
                'description' => 'Derin araştırma, çok kaynaklı karşılaştırma ve yanılmanın pahalı olduğu kararlar.',
                'analysis_models' => [
                    '~anthropic/claude-opus-latest',
                    '~openai/gpt-latest',
                    '~google/gemini-pro-latest',
                ],
                'max_tool_calls' => 12,
            ],
            'custom' => [
                'label' => 'Özel JSON / Satır Listesi',
                'description' => 'Admin panelinde tanımlanan özel panel modelleri kullanılır.',
                'analysis_models' => [],
                'max_tool_calls' => 8,
            ],
        ];
    }
}

if (!function_exists('agfo_openrouter_parse_model_list')) {
    function agfo_openrouter_parse_model_list($raw): array {
        if (is_array($raw)) {
            $items = $raw;
        } else {
            $text = trim((string) $raw);
            if ($text === '') return [];
            $json = json_decode($text, true);
            if (is_array($json)) {
                $items = $json;
            } else {
                $items = preg_split('/[\r\n,]+/', $text);
            }
        }
        $out = [];
        foreach ($items as $item) {
            $id = trim((string) $item);
            if ($id === '') continue;
            if (strlen($id) > 160) continue;
            $out[] = sanitize_text_field($id);
        }
        return array_values(array_unique(array_slice($out, 0, 8)));
    }
}

if (!function_exists('agfo_openrouter_get_fusion_config')) {
    function agfo_openrouter_get_fusion_config(): array {
        $profiles = agfo_openrouter_get_fusion_profiles();
        $mode = sanitize_key((string) get_option('agfo_openrouter_fusion_mode', 'off'));
        if (!in_array($mode, ['off', 'auto', 'force'], true)) $mode = 'off';

        $profile = sanitize_key((string) get_option('agfo_openrouter_fusion_profile', 'balanced'));
        if (!isset($profiles[$profile])) $profile = 'balanced';

        $analysis_models = $profiles[$profile]['analysis_models'] ?? [];
        if ($profile === 'custom') {
            $analysis_models = agfo_openrouter_parse_model_list(get_option('agfo_openrouter_fusion_analysis_models', ''));
        }
        if (empty($analysis_models)) {
            $analysis_models = $profiles['balanced']['analysis_models'];
        }

        $max_tool_calls = (int) get_option('agfo_openrouter_fusion_max_tool_calls', (int)($profiles[$profile]['max_tool_calls'] ?? 8));
        $max_tool_calls = max(1, min(16, $max_tool_calls));

        $judge_model = trim((string) get_option('agfo_openrouter_fusion_judge_model', ''));
        $max_completion_tokens = (int) get_option('agfo_openrouter_fusion_max_completion_tokens', 0);
        $temperature_raw = trim((string) get_option('agfo_openrouter_fusion_temperature', ''));
        $temperature = ($temperature_raw === '') ? null : max(0, min(2, (float) $temperature_raw));

        return [
            'mode' => $mode,
            'profile' => $profile,
            'profile_label' => (string)($profiles[$profile]['label'] ?? $profile),
            'analysis_models' => $analysis_models,
            'judge_model' => sanitize_text_field($judge_model),
            'max_tool_calls' => $max_tool_calls,
            'max_completion_tokens' => $max_completion_tokens > 0 ? min(128000, $max_completion_tokens) : 0,
            'temperature' => $temperature,
            'profiles' => $profiles,
        ];
    }
}

if (!function_exists('agfo_openrouter_maybe_apply_fusion_tools')) {
    function agfo_openrouter_maybe_apply_fusion_tools(array $body, array $options = []): array {
        $provider_code = isset($options['provider_code']) ? sanitize_key((string) $options['provider_code']) : '';
        if ($provider_code !== 'openrouter') return $body;

        $config = agfo_openrouter_get_fusion_config();
        if (($config['mode'] ?? 'off') === 'off') return $body;
        if (empty($body['messages']) || !is_array($body['messages'])) return $body;

        // CHANGED: Avoid duplicate or conflicting Fusion injection when a caller already manages tools explicitly.
        if (!empty($body['tools']) && is_array($body['tools'])) return $body;

        $parameters = [
            'analysis_models' => array_values($config['analysis_models']),
            'max_tool_calls'  => (int) $config['max_tool_calls'],
        ];
        if (!empty($config['judge_model'])) {
            $parameters['model'] = (string) $config['judge_model'];
        }
        if (!empty($config['max_completion_tokens'])) {
            $parameters['max_completion_tokens'] = (int) $config['max_completion_tokens'];
        }
        if ($config['temperature'] !== null) {
            $parameters['temperature'] = (float) $config['temperature'];
        }

        $body['tools'] = [
            [
                'type' => 'openrouter:fusion',
                'parameters' => $parameters,
            ],
        ];

        if (($config['mode'] ?? '') === 'force') {
            $body['tool_choice'] = 'required';
        }

        if (function_exists('agfo_ai_manager_log_transport')) {
            agfo_ai_manager_log_transport('OPENROUTER_FUSION_INJECTED', [
                'mode' => (string) $config['mode'],
                'profile' => (string) $config['profile'],
                'panel_count' => count($parameters['analysis_models']),
            ]);
        }

        return $body;
    }
}

/* ── GERİYE DÖNÜK UYUMLULUK ─────────────────────────────── */
if (!function_exists('agfo_get_priority_api_key')) {
    function agfo_get_priority_api_key($force_check = false, $preferred_model = '', $provider_override = '') {
        try {
            // CHANGED 17.1.0: optional provider override (used by the text_translate route).
            $code    = ($provider_override !== '' && $provider_override !== null) ? sanitize_key((string) $provider_override) : agfo_get_selected_provider();
            $api_key = agfo_get_api_key($code);
            if (empty($api_key)) return false;

            $registry = agfo_api_registry();
            if (!isset($registry[$code])) return false;

            // CHANGED 16.6.0: Guvenlik agi. 16.6.0 ile registry'ye chat yapamayan
            // medya saglayicilari (fal.ai) eklendi; boyle bir kod bir sekilde
            // agfo_selected_provider'a yazilirsa chat akisi bozulmasin diye reddedilir.
            if (($registry[$code]['type'] ?? 'llm') !== 'llm') return false;

            $info  = $registry[$code];
            // CHANGED 17.1.0: with a provider override the global model belongs to another provider.
            $is_override = ($provider_override !== '' && $provider_override !== null && $code !== agfo_get_selected_provider());
            $model = $preferred_model ?: ($is_override ? '' : get_option('agfo_global_preferred_model', ''));

            if (empty($model)) {
                $models = get_option('agfo_models_' . $code, []);
                if (!empty($models)) {
                    $first = $models[0];
                    $model = is_array($first) ? (isset($first['id']) ? $first['id'] : '') : (string)$first;
                }
            }

            // NEW 17.0.0: never hand dependent plugins a model the provider cannot serve as chat.
            // Responses-only OpenAI models stay selected (the request guard bridges them);
            // unavailable or non-chat models are replaced by a working model of the same provider.
            $model_fallback_from = '';
            $transport_route     = 'chat';
            if (class_exists('AGFO_AIM_Request_Guard') && $model !== '') {
                $route = AGFO_AIM_Request_Guard::model_route($code, $model);
                if (in_array($route, ['unavailable', 'not_chat'], true) && AGFO_AIM_Request_Guard::fallback_enabled()) {
                    $fallback = AGFO_AIM_Request_Guard::fallback_model($code, $model);
                    if ($fallback !== '') {
                        $model_fallback_from = $model;
                        $model               = $fallback;
                        $route               = AGFO_AIM_Request_Guard::model_route($code, $model);
                    }
                }
                $transport_route = ($route === 'responses') ? 'responses_bridge' : $route;
            }

            $auth = [];
            $info_auth = isset($info['auth']) ? $info['auth'] : [];
            foreach ($info_auth as $k => $v) {
                $auth[$k] = str_replace('{key}', $api_key, $v);
            }

            $chat_url = isset($info['chat_url']) ? $info['chat_url'] : '';
            if ($code === 'gemini') {
                $chat_url = str_replace(['{model}', '{key}'], [$model, $api_key], $chat_url);
            }

            $model_capabilities = function_exists('agfo_get_model_capabilities')
                ? agfo_get_model_capabilities($code, $model)
                : [];

            // NEW 16.17.2: Expose the effective transport rule, not stale probe metadata.
            // This lets dependent plugins omit temperature before the request is built, while
            // agfo_api_post() remains the final safety net if they still send it.
            $effective_supports_temperature = $model_capabilities['supports_temperature'] ?? true;
            if (function_exists('agfo_model_uses_default_sampling') && agfo_model_uses_default_sampling($code, $model)) {
                $effective_supports_temperature = false;
            }

            return [
                'code'                       => $code,
                'provider_name'              => isset($info['label']) ? $info['label'] : $code,
                'model'                      => $model,
                'key'                        => $api_key,
                'chat_url'                   => $chat_url,
                'auth'                       => $auth,
                'base_url'                   => isset($info['chat_url']) ? $info['chat_url'] : '',
                'provider_info'              => $info,
                // CHANGED 16.16.2: OpenRouter ve MiniMax chat de max_completion_tokens kullanir.
                // Donusum agfo_api_post() icinde merkezi olarak yapiliyordu, ancak bu alan yalnizca
                // 'openai' icin hesaplandigi icin alani okuyup govdeyi elle kuran bagimli pluginler
                // OpenRouter'da yanlis alan adi gonderiyordu. Alan artik tasima katmaniyla ayni
                // sonucu bildirir; agfo_api_post() zaten idempotenttir, cift donusum olmaz.
                'uses_max_completion_tokens' => (
                    $code === 'openrouter'
                    || $code === 'minimax'
                    || ($code === 'openai' && agfo_uses_max_completion_tokens($model))
                ),
                // CHANGED 15.4.0: Backward-compatible model metadata for dependent plugins such as DOCX Studio.
                'model_capabilities'         => $model_capabilities,
                'endpoint_type'              => $model_capabilities['endpoint_type'] ?? 'chat',
                'supports_chat'              => $model_capabilities['supports_chat'] ?? true,
                'supports_temperature'       => (bool) $effective_supports_temperature,
                'docx_allowed'               => $model_capabilities['docx_allowed'] ?? true,
                'compatibility_level'        => $model_capabilities['compatibility_level'] ?? 'ok',
                'compatibility_notes'        => $model_capabilities['compatibility_notes'] ?? [],
                // CHANGED: Expose OpenRouter Fusion status to dependent AGFO plugins without forcing them to implement tool logic.
                'openrouter_fusion'         => ($code === 'openrouter' && function_exists('agfo_openrouter_get_fusion_config')) ? agfo_openrouter_get_fusion_config() : [],
                // NEW 17.0.0: effective transport facts for dependent plugins.
                'sampling_policy'            => $model_capabilities['sampling_policy'] ?? 'allowed',
                'transport_route'            => $transport_route,
                'model_fallback_from'        => $model_fallback_from,
                'is_reasoning'               => ($code === 'openai' || $code === 'openrouter') && function_exists('agfo_openai_model_is_reasoning')
                    ? agfo_openai_model_is_reasoning(preg_replace('#^[^/]+/#', '', $model))
                    : false,
            ];
        } catch (Exception $e) {
            if (defined('WP_DEBUG') && WP_DEBUG) error_log('AGFO: ' . $e->getMessage());
            return false;
        }
    }
}