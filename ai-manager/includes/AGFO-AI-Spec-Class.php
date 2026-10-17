<?php
/**
 * AGFO AI Specification Context Class
 * Creates copyable AI context packages for developing AGFO-compatible WordPress plugins.
 *
 * @version 16.12.0
 */

if (!defined('ABSPATH')) {
    exit;
}

class AGFO_AI_Spec_Class {

    public static function register_hooks(): void {
        add_action('admin_menu', [__CLASS__, 'add_menu']);
    }

    public static function add_menu(): void {
        add_submenu_page(
            'agfo-ai-manager',
            'AI Specification',
            '📐 AI Specification',
            'manage_options',
            'agfo-ai-spec',
            [__CLASS__, 'render_page']
        );
    }

    public static function render_page(): void {
        if (!current_user_can('manage_options')) {
            wp_die('Unauthorized');
        }

        $provider  = function_exists('agfo_get_selected_provider') ? agfo_get_selected_provider() : '';
        $model     = (string) get_option('agfo_global_preferred_model', '');
        $reasoning = (int) get_option('agfo_reasoning_mode', 0);
        $plugins   = self::get_plugin_choices();

        $selected_plugin      = isset($_POST['target_plugin'])       ? sanitize_text_field(wp_unslash($_POST['target_plugin']))     : '';
        $plugin_name          = isset($_POST['plugin_name'])         ? sanitize_text_field(wp_unslash($_POST['plugin_name']))       : '';
        $plugin_goal          = isset($_POST['plugin_goal'])         ? sanitize_textarea_field(wp_unslash($_POST['plugin_goal']))   : '';
        $extra_rules          = isset($_POST['extra_rules'])         ? sanitize_textarea_field(wp_unslash($_POST['extra_rules']))   : '';
        $include_plugin_files = !empty($_POST['include_plugin_files']);
        $generated            = '';

        if (isset($_POST['agfo_generate_spec'])) {
            check_admin_referer('agfo_ai_spec_generate');
            $generated = self::build_spec_package([
                'provider'             => $provider,
                'model'                => $model,
                'reasoning'            => $reasoning,
                'target_plugin'        => $selected_plugin,
                'plugin_name'          => $plugin_name,
                'plugin_goal'          => $plugin_goal,
                'extra_rules'          => $extra_rules,
                'include_plugin_files' => $include_plugin_files,
            ]);
        }
        ?>
        <div class="wrap">
            <h1>📐 AGFO AI Specification Context</h1>
            <p>
                Bu sayfa, yeni geliştireceğiniz plugin için AI'ye verilecek standart bağlam paketini üretir.
                Amaç: yeni pluginlerin AGFO AI Manager mimarisine uyması, API bağlantısını merkezi fonksiyonlardan yapması
                ve provider uyumsuzluklarını tekrar yaşamamasıdır.
            </p>

            <div style="display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap;margin-top:20px;">
                <div class="postbox" style="padding:16px;max-width:420px;width:100%;">
                    <h2>⚙️ Specification Ayarları</h2>
                    <form method="post">
                        <?php wp_nonce_field('agfo_ai_spec_generate'); ?>
                        <table class="form-table">
                            <tr>
                                <th scope="row">Aktif AI Bağlantısı</th>
                                <td>
                                    <code><?php echo esc_html($provider ?: '-'); ?></code><br>
                                    <small>Model: <code><?php echo esc_html($model ?: '-'); ?></code></small><br>
                                    <small>Reasoning: <code><?php echo $reasoning ? 'on' : 'off'; ?></code></small>
                                </td>
                            </tr>
                            <tr>
                                <th scope="row">Yeni / Hedef Plugin</th>
                                <td>
                                    <select name="target_plugin" style="width:100%;">
                                        <option value="">— Yeni plugin / seçim yok —</option>
                                        <?php foreach ($plugins as $slug => $label): ?>
                                            <option value="<?php echo esc_attr($slug); ?>" <?php selected($selected_plugin, $slug); ?>>
                                                <?php echo esc_html($label); ?>
                                            </option>
                                        <?php endforeach; ?>
                                    </select>
                                    <p class="description">Bu seçici mevcut plugin slug listesini okur.</p>
                                    <label style="display:block;margin-top:10px;">
                                        <input type="checkbox" name="include_plugin_files" value="1" <?php checked($include_plugin_files); ?>>
                                        Seçili plugin dosyalarını bağlam paketine ekle
                                    </label>
                                    <p class="description">
                                        Vendor, node_modules, DOMPDF, TCPDF, minified dosyalar, büyük dosyalar ve
                                        <code>data/data.json</code> otomatik dışlanır.
                                    </p>
                                </td>
                            </tr>
                            <tr>
                                <th scope="row">Plugin Adı</th>
                                <td>
                                    <input type="text" name="plugin_name" value="<?php echo esc_attr($plugin_name); ?>"
                                           style="width:100%;" placeholder="Örn: AGFO Certificate Intelligence">
                                </td>
                            </tr>
                            <tr>
                                <th scope="row">Amaç</th>
                                <td>
                                    <textarea name="plugin_goal" rows="5" style="width:100%;"
                                              placeholder="Bu plugin ne yapacak?"><?php echo esc_textarea($plugin_goal); ?></textarea>
                                </td>
                            </tr>
                            <tr>
                                <th scope="row">Ek Kurallar</th>
                                <td>
                                    <textarea name="extra_rules" rows="5" style="width:100%;"
                                              placeholder="Örn: shortcode olacak, CPT kullanacak, AJAX olmasın..."><?php echo esc_textarea($extra_rules); ?></textarea>
                                </td>
                            </tr>
                        </table>
                        <p>
                            <button type="submit" name="agfo_generate_spec" class="button button-primary">
                                📦 Bağlam Paketini Üret
                            </button>
                        </p>
                    </form>
                </div>

                <div class="postbox" style="padding:16px;flex:1;min-width:520px;">
                    <h2>🧠 AI Context Package</h2>
                    <textarea id="agfo-spec-output" readonly
                              style="width:100%;height:620px;background:#1e1e1e;color:#d4d4d4;font-family:Consolas,Monaco,monospace;font-size:12px;padding:12px;"><?php echo esc_textarea($generated); ?></textarea>
                    <p style="display:flex;gap:8px;flex-wrap:wrap;">
                        <button type="button" class="button" onclick="agfoSpecCopy()">📋 Kopyala</button>
                        <button type="button" class="button" onclick="agfoSpecDownload()">💾 İndir</button>
                    </p>
                </div>
            </div>
        </div>

        <script>
        function agfoSpecCopy() {
            const el = document.getElementById('agfo-spec-output');
            el.focus(); el.select();
            document.execCommand('copy');
        }
        function agfoSpecDownload() {
            const el  = document.getElementById('agfo-spec-output');
            const content = el.value || '';
            if (!content) return;
            const blob = new Blob([content], {type: 'text/plain'});
            const a    = document.createElement('a');
            a.href     = URL.createObjectURL(blob);
            a.download = 'agfo-ai-spec-' + Date.now() + '.txt';
            a.click();
        }
        </script>
        <?php
    }

    private static function build_spec_package(array $args): string {
        $provider      = (string) ($args['provider']      ?? '');
        $model         = (string) ($args['model']         ?? '');
        $reasoning     = !empty($args['reasoning']) ? 'enabled' : 'disabled';
        $target_plugin = (string) ($args['target_plugin'] ?? '');
        $plugin_name   = (string) ($args['plugin_name']   ?? '');
        $plugin_goal   = (string) ($args['plugin_goal']   ?? '');
        $extra_rules   = (string) ($args['extra_rules']   ?? '');

        $registry      = function_exists('agfo_api_registry') ? agfo_api_registry() : [];
        $provider_info = $registry[$provider] ?? [];

        $lines = [];

        $lines[] = "### AGFO AI MANAGER SPECIFICATION CONTEXT ###";
        $lines[] = "DATE: " . current_time('mysql');
        $lines[] = "SOURCE: AGFO AI Manager / AGFO_AI_Spec_Class";
        $lines[] = "PURPOSE: Development rules for new AGFO-compatible WordPress plugins";
        $lines[] = "------------------------------------------------------------";
        $lines[] = "";

        $lines[] = "## ACTIVE AI CONFIGURATION";
        $lines[] = "- Provider: " . ($provider ?: '-');
        $lines[] = "- Provider Label: " . (($provider_info['label'] ?? '') ?: '-');
        $lines[] = "- Model: " . ($model ?: '-');
        $lines[] = "- Reasoning Mode: " . $reasoning;
        $lines[] = "";

        $lines[] = "## CURRENT WORDPRESS ENVIRONMENT";
        $lines[] = "- WordPress Version: " . get_bloginfo('version');
        $lines[] = "- PHP Version: " . PHP_VERSION;
        $lines[] = "- Active Plugins: " . count((array) get_option('active_plugins', []));
        $lines[] = "- Memory Limit: " . ini_get('memory_limit');
        $lines[] = "- Memory Usage: " . size_format(memory_get_usage(true));
        $lines[] = "- debug.log: " . self::get_debug_log_status();
        $lines[] = "- AGFO Snippet Engine Active Count: " . self::count_active_agfo_snippets();
        $lines[] = "- Code Snippets Active Count: " . self::count_active_code_snippets();
        $lines[] = "";

        $lines[] = "## TARGET PLUGIN";
        $lines[] = "- Existing Plugin Slug: " . ($target_plugin ?: 'new-plugin');
        $lines[] = "- Plugin Name: " . ($plugin_name ?: '-');
        $lines[] = "- Goal:";
        $lines[] = ($plugin_goal ?: '-');
        $lines[] = "";

        $lines[] = "## HARD ARCHITECTURE RULES";
        $lines[] = "1. Do not bypass AGFO AI Manager configuration.";
        $lines[] = "   All provider calls must resolve API keys, provider, model, URL and headers from AGFO AI Manager functions.";
        $lines[] = "2. Never hardcode API keys or provider URLs.";
        $lines[] = "3. Never store raw API keys in the new plugin.";
        $lines[] = "4. Never duplicate provider registry logic.";
        $lines[] = "5. Never use cURL directly for AI calls.";
        $lines[] = "6. Chat/completion calls from AGFO plugins must use agfo_api_post() as the central transport gate.";
        $lines[] = "7. Provider, model, API key, auth headers and chat URL must come from AGFO AI Manager.";
        $lines[] = "8. agfo_api_post() is the backward-compatible central AGFO transport gate.";
        $lines[] = "   It keeps OpenAI max_completion_tokens compatibility and protects managed AGFO AI calls from connector approval traps.";
        $lines[] = "9. For Gemini, Claude and OpenAI-compatible providers, build the correct body format explicitly, then send it through agfo_api_post().";
        $lines[] = "10. The new plugin must fail gracefully if AGFO AI Manager is inactive.";
        $lines[] = "";

        $lines[] = "## AVAILABLE AGFO AI MANAGER FUNCTIONS";
        $lines[] = "- agfo_get_priority_api_key()";
        $lines[] = "  → Returns array with keys:";
        $lines[] = "    code                       : string  (provider slug, e.g. 'openai', 'claude', 'gemini')";
        $lines[] = "    provider_name              : string  (human readable label)";
        $lines[] = "    model                      : string  (selected model ID)";
        $lines[] = "    key                        : string  (decrypted API key)";
        $lines[] = "    chat_url                   : string  (ready-to-use chat endpoint)";
        $lines[] = "    auth                       : array   (headers with {key} ALREADY replaced, e.g. ['Authorization'=>'Bearer sk-...'])";
        $lines[] = "    base_url                   : string  (raw chat_url from registry with placeholders)";
        $lines[] = "    provider_info              : array   (full registry entry: label, url, chat_url, auth, type)";
        $lines[] = "    uses_max_completion_tokens : bool    (true if OpenAI model needs max_completion_tokens)";
        $lines[] = "- agfo_get_selected_provider()             → returns active provider code string";
        $lines[] = "- agfo_get_api_key(\$provider)              → returns decrypted API key string or null";
        $lines[] = "- agfo_api_registry()                      → returns all provider definitions";
        $lines[] = "- agfo_uses_max_completion_tokens(\$model)  → bool; true for OpenAI chat-latest/o1/o3/o4/gpt-4/gpt-5 models";
        $lines[] = "- agfo_api_post(\$url, \$headers, \$body, \$options)";
        $lines[] = "  → Backward-compatible central transport. \$options may contain 'provider_code', 'model', 'timeout' and 'source'.";
        $lines[] = "  → Auto-rewrites max_tokens to max_completion_tokens for OpenAI new models and OpenRouter-routed frontier models, then logs guarded transport stages.";
        $lines[] = "  → Returns ['http_code'=>int, 'body'=>string, 'transport'=>string] or ['error'=>string, 'stage'=>string].";
        $lines[] = "  → For provider 'nvidia' (NVIDIA NIM), max_tokens above 4096 is automatically clamped to 4096 (NIM API limit).";
        $lines[] = "";
        $lines[] = "## CAPABILITY, JOB AND ASSET API (16.12.0)";
        $lines[] = "- agfo_job_submit(\$capability, \$payload, \$args) → persistent queued job; use for new non-chat work. TTS args may include provider_models[provider] for provider-specific fallback models.";
        $lines[] = "- agfo_job_status(\$job_uuid, \$user_id) / agfo_job_cancel(\$job_uuid, \$user_id).";
        $lines[] = "- agfo_speech_synthesize(\$text, \$options) → speech_synthesize facade.";
        $lines[] = "- agfo_asset_url(\$asset_uuid, \$download) → nonce and ACL protected delivery URL.";
        $lines[] = "RULES:";
        $lines[] = "1. TTS and generated media must use agfo_job_submit()/agfo_speech_synthesize(); do not call provider endpoints directly.";
        $lines[] = "2. New generated assets are private by default and stored outside the web root; public Media Library publication must be explicit opt-in.";
        $lines[] = "3. Every generated asset requires source_plugin and provenance. Never mix generated media with audit evidence without clear source labelling.";
        $lines[] = "4. Do not bypass budget reservation, capability kill switches, job ownership or asset ACL checks.";
        $lines[] = "5. Video generation is not part of 16.12.0 and must not be assumed available.";
        $lines[] = "";

        // CHANGED 16.0.0: Model Intelligence sozlesmesi (payload 16.0.0'dan tasindi; 15.6.2 transport dokumani KORUNDU).
        if ( function_exists( 'agfo_ai_get_model_intelligence' ) ) {
            $lines[] = "## AVAILABLE MODEL INTELLIGENCE FUNCTIONS (16.0.0)";
            $lines[] = "- agfo_ai_get_model_intelligence(\$provider, \$model)      → array (supports_chat, supports_temperature, endpoint_type, docx_allowed, price metadata, benchmark/speed/cost/fp scores, final_agfo_score, recommendation_label)";
            $lines[] = "- agfo_ai_get_compatible_models(\$args)                   → array of chat-compatible models (filters: provider, chat_only, docx_only, min_score)";
            $lines[] = "- agfo_ai_get_docx_allowed_models(\$provider)             → array of models safe for long DOCX generation";
            $lines[] = "- agfo_ai_get_best_model(\$args) / agfo_ai_get_best_fp_model(\$provider) / agfo_ai_get_cheapest_compatible_model(\$provider)";
            $lines[] = "- agfo_ai_estimate_model_cost(\$provider, \$model, \$in_tokens, \$out_tokens) → estimated USD cost";
            $lines[] = "- agfo_ai_get_model_recommendation_label(\$provider, \$model) → string label (Best AGFO Choice / Budget Friendly / Fast / ...)";
            $lines[] = "RULES:";
            $lines[] = "1. Model DECISIONS come from Model Intelligence; transport config still comes from agfo_get_priority_api_key().";
            $lines[] = "2. Feature plugins must fail gracefully when Model Intelligence is unavailable (function_exists guard).";
            $lines[] = "3. Batch scan is MANUAL and belongs to AI Manager admin only; feature plugins must never trigger it.";
            $lines[] = "";
        }

        $lines[] = "## PROVIDER-SPECIFIC REQUEST FORMATS";
        $lines[] = "Each provider requires a different request body. Build it explicitly in your plugin.";
        $lines[] = "";
        $lines[] = "GEMINI:";
        $lines[] = "  Gemini is optional. Do not force Gemini direct API usage unless Gemini is the selected/configured provider.";
        $lines[] = "  chat_url from agfo_get_priority_api_key() is already resolved with model and key.";
        $lines[] = "  Body: { contents: [{role, parts:[{text}]}], generationConfig: {temperature, maxOutputTokens} }";
        $lines[] = "  System prompt: top-level systemInstruction field — NOT inside contents array.";
        $lines[] = "  Role mapping: assistant → 'model', user → 'user'. System messages are stripped from contents.";
        $lines[] = "  Response path: candidates[0].content.parts[0].text";
        $lines[] = "";
        $lines[] = "CLAUDE:";
        $lines[] = "  Body: { model, max_tokens, temperature, messages, system }";
        $lines[] = "  System prompt: top-level 'system' string field — NOT inside messages array.";
        $lines[] = "  Headers: x-api-key + anthropic-version (already resolved in \$ai['auth'])";
        $lines[] = "  Response path: content[0].text";
        $lines[] = "";
        $lines[] = "OPENAI-COMPATIBLE (openai, openrouter, groq, deepseek, deepinfra, llama_together):";
        $lines[] = "  Body: { model, messages, temperature }";
        $lines[] = "  Token limit field:";
        $lines[] = "    - If \$ai['uses_max_completion_tokens'] is true → use max_completion_tokens";
        $lines[] = "    - Otherwise → use max_tokens";
        $lines[] = "  Response path: choices[0].message.content";
        $lines[] = "";
        $lines[] = "OPENROUTER FUSION:";
        $lines[] = "  If OpenRouter is selected and AGFO AI Manager Fusion mode is enabled, feature plugins must NOT add tools manually.";
        $lines[] = "  Fusion tools are injected centrally inside agfo_api_post() according to the AI Manager Fusion profile.";
        $lines[] = "  Modes: off = no Fusion, auto = model may invoke Fusion, force = tool_choice required.";
        $lines[] = "  Dependent plugins should keep sending normal OpenAI-compatible bodies through agfo_api_post().";
        $lines[] = "  Do not send confidential customer documents with Fusion unless the user knowingly accepts web_search/web_fetch behavior.";
        $lines[] = "";

        $lines[] = "## REQUIRED AI CALL PATTERN";
        $lines[] = "```php";
        $lines[] = "// 1. Resolve configuration centrally";
        $lines[] = "\$ai = function_exists('agfo_get_priority_api_key') ? agfo_get_priority_api_key() : false;";
        $lines[] = "if (!\$ai || empty(\$ai['key']) || empty(\$ai['model']) || empty(\$ai['chat_url'])) {";
        $lines[] = "    return new WP_Error('agfo_ai_missing', 'AGFO AI Manager is not configured.');";
        $lines[] = "}";
        $lines[] = "";
        $lines[] = "\$provider_code = \$ai['code'];";
        $lines[] = "\$model         = \$ai['model'];";
        $lines[] = "\$chat_url      = \$ai['chat_url'];";
        $lines[] = "\$headers       = array_merge(['Content-Type' => 'application/json'], \$ai['auth'] ?? []);";
        $lines[] = "";
        $lines[] = "// 2. Prepare messages";
        $lines[] = "\$messages = [";
        $lines[] = "    ['role' => 'system', 'content' => 'You are an AGFO-compatible assistant.'],";
        $lines[] = "    ['role' => 'user',   'content' => \$prompt],";
        $lines[] = "];";
        $lines[] = "";
        $lines[] = "// 3. Build provider-specific body explicitly";
        $lines[] = "if (\$provider_code === 'gemini') {";
        $lines[] = "    \$contents = [];";
        $lines[] = "    \$sys_text = '';";
        $lines[] = "    foreach (\$messages as \$m) {";
        $lines[] = "        if (\$m['role'] === 'system') { \$sys_text = \$m['content']; continue; }";
        $lines[] = "        \$contents[] = ['role' => \$m['role'] === 'assistant' ? 'model' : 'user', 'parts' => [['text' => \$m['content']]]];";
        $lines[] = "    }";
        $lines[] = "    \$body = ['contents' => \$contents, 'generationConfig' => ['temperature' => 0.3, 'maxOutputTokens' => 1200]];";
        $lines[] = "    if (\$sys_text) \$body['systemInstruction'] = ['parts' => [['text' => \$sys_text]]];";
        $lines[] = "} elseif (\$provider_code === 'claude') {";
        $lines[] = "    \$msg_list = []; \$sys_text = '';";
        $lines[] = "    foreach (\$messages as \$m) {";
        $lines[] = "        if (\$m['role'] === 'system') { \$sys_text = \$m['content']; continue; }";
        $lines[] = "        \$msg_list[] = \$m;";
        $lines[] = "    }";
        $lines[] = "    \$body = ['model' => \$model, 'max_tokens' => 1200, 'temperature' => 0.3, 'messages' => \$msg_list];";
        $lines[] = "    if (\$sys_text) \$body['system'] = \$sys_text;";
        $lines[] = "} else {";
        $lines[] = "    \$body = ['model' => \$model, 'messages' => \$messages, 'temperature' => 0.3];";
        $lines[] = "    if (!empty(\$ai['uses_max_completion_tokens'])) \$body['max_completion_tokens'] = 1200; else \$body['max_tokens'] = 1200;";
        $lines[] = "}";
        $lines[] = "";
        $lines[] = "// 4. Send through the AGFO central transport gate. Do not call wp_remote_post() directly from feature plugins.";
        $lines[] = "\$result = agfo_api_post(\$chat_url, \$headers, wp_json_encode(\$body), [";
        $lines[] = "    'provider_code' => \$provider_code,";
        $lines[] = "    'model'         => \$model,";
        $lines[] = "    'timeout'       => 60,";
        $lines[] = "    'source'        => 'your_plugin_slug',";
        $lines[] = "]);";
        $lines[] = "if (isset(\$result['error'])) return new WP_Error('agfo_ai_error', \$result['error']);";
        $lines[] = "";
        $lines[] = "\$decoded = json_decode((string) (\$result['body'] ?? ''), true);";
        $lines[] = "\$text = '';";
        $lines[] = "if (\$provider_code === 'gemini') \$text = \$decoded['candidates'][0]['content']['parts'][0]['text'] ?? '';";
        $lines[] = "elseif (\$provider_code === 'claude') \$text = \$decoded['content'][0]['text'] ?? '';";
        $lines[] = "else \$text = \$decoded['choices'][0]['message']['content'] ?? '';";
        $lines[] = "if (trim((string) \$text) === '') return new WP_Error('agfo_ai_empty', 'AI response could not be parsed.');";
        $lines[] = "return trim((string) \$text);";
        $lines[] = "```";
        $lines[] = "";

        $lines[] = "## WORDPRESS DEVELOPMENT RULES";
        $lines[] = "- Prefix all NEW functions/classes/options/meta keys with your_plugin_slug_ (e.g. agfo_cert_).";
        $lines[] = "  Do NOT use agfo_ prefix for NEW symbols unless you are extending AGFO AI Manager itself.";
        $lines[] = "- EXCEPTION: If the existing analyzed plugin already historically uses agfo_ prefix,";
        $lines[] = "  do NOT mass-rename existing functions/classes to avoid breaking backwards compatibility.";
        $lines[] = "  Apply this prefix rule only to NEW symbols you add.";
        $lines[] = "- Use nonces for every write action and every AJAX action.";
        $lines[] = "- Use current_user_can('manage_options') for admin-only AI operations.";
        $lines[] = "- Escape output with esc_html(), esc_attr(), esc_url(), wp_kses_post().";
        $lines[] = "- Sanitize input with sanitize_text_field(), sanitize_textarea_field(), absint().";
        $lines[] = "- Avoid loading heavy assets globally.";
        $lines[] = "- Do not run expensive scans on every admin page load.";
        $lines[] = "- Keep AI prompts visible, copyable, and debuggable.";
        $lines[] = "";

        $lines[] = "## FAILURE-SAFE RULES";
        $lines[] = "- The new plugin must fail gracefully if AGFO AI Manager is inactive.";
        $lines[] = "- The new plugin must not fatal if no provider/model/API key is configured.";
        $lines[] = "- Missing AI configuration should show an admin notice or WP_Error, not a crash.";
        $lines[] = "- Long AI calls should use timeout handling and return readable errors.";
        $lines[] = "";

        $lines[] = "## AI SAFETY RULES";
        $lines[] = "- AI must never overwrite existing code, files, snippets or database records without explicit user confirmation.";
        $lines[] = "- AI-generated modifications must be previewed before saving.";
        $lines[] = "- AI must not auto-activate modified code or generated logic.";
        $lines[] = "- AI must not execute generated PHP directly.";
        $lines[] = "- AI must not write to arbitrary filesystem paths.";
        $lines[] = "- AI must preserve rollback capability before destructive changes.";
        $lines[] = "- AI must follow: analyze → propose → preview → confirm → save.";
        $lines[] = "";

        $lines[] = "## AI CODE REVIEW TASKS";
        $lines[] = "1. Detect security risks: missing nonces, missing capability checks, unsafe input/output.";
        $lines[] = "2. Detect architectural problems: large files, mixed responsibilities, duplicated logic.";
        $lines[] = "3. Suggest minimal safe refactors.";
        $lines[] = "4. Identify AI integration points.";
        $lines[] = "5. Identify unused or redundant code/files.";
        $lines[] = "6. Prefer minimal patches over full rewrites.";
        $lines[] = "7. Preserve existing working behavior.";
        $lines[] = "8. Explain risky changes before applying them.";
        $lines[] = "";

        $lines[] = "## EXTRA USER RULES";
        $lines[] = ($extra_rules ?: '-');
        $lines[] = "";

        if (!empty($args['include_plugin_files']) && $target_plugin !== '' && self::is_valid_plugin_slug($target_plugin)) {
            $lines[] = "## SOURCE ANALYSIS INSTRUCTIONS";
            $lines[] = "Before modifying the code below, AI must:";
            $lines[] = "- Build a structure map.";
            $lines[] = "- Identify security risks.";
            $lines[] = "- Detect unused or redundant code.";
            $lines[] = "- Identify safe AI integration points.";
            $lines[] = "- Propose a minimal patch plan.";
            $lines[] = "";
            $lines[] = "## SELECTED PLUGIN SOURCE CONTEXT";
            $lines[] = self::scan_plugin_source_for_context($target_plugin);
            $lines[] = "";
        }

        $lines[] = "## TASK FOR AI";
        $lines[] = "Develop or refactor the plugin according to all rules above.";
        $lines[] = "Resolve all configuration (provider, model, API key, headers, URL) from AGFO AI Manager functions.";
        $lines[] = "Build provider-specific request bodies explicitly, then send the JSON string through agfo_api_post().";
        $lines[] = "Always parse the returned response safely and handle empty/error responses explicitly.";
        $lines[] = "Do not use direct wp_remote_post() for chat/completion calls in AGFO feature plugins; use agfo_api_post() so AGFO AI Manager remains the single protected transport gate.";

        return implode("\n", $lines);
    }

    private static function scan_plugin_source_for_context(string $slug): string {
        if (!self::is_valid_plugin_slug($slug)) {
            return "[PLUGIN SOURCE ERROR: invalid plugin slug]\n";
        }

        $root             = WP_PLUGIN_DIR . '/' . $slug;
        $allowed_ext      = ['php', 'js', 'css', 'json', 'md', 'txt', 'html', 'htm'];
        $exclude_patterns = [
            'vendor', 'node_modules', '.git', '.github', 'dompdf', 'tcpdf', 'mpdf',
            'composer.lock', 'package-lock.json', 'yarn.lock',
            '.map', '.min.js', '.min.css', 'data/data.json',
            'cache', 'logs', 'backup', 'backups', 'tmp',
        ];
        $max_file_size  = 180000;
        $max_total_size = 900000;
        $output         = '';
        $included       = 0;
        $excluded       = 0;
        $skipped_large  = 0;
        $skipped_ext    = 0;
        $unreadable     = 0;

        try {
            $iterator = new RecursiveIteratorIterator(
                new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS),
                RecursiveIteratorIterator::LEAVES_ONLY
            );
        } catch (Exception $e) {
            return "[PLUGIN SOURCE ERROR: " . $e->getMessage() . "]\n";
        }

        foreach ($iterator as $file) {
            if (!$file->isFile()) {
                continue;
            }

            $path      = $file->getPathname();
            $rel       = str_replace('\\', '/', ltrim(str_replace($root, '', $path), DIRECTORY_SEPARATOR));
            $rel_lower = strtolower($rel);

            $is_excluded = false;
            foreach ($exclude_patterns as $pattern) {
                if (strpos($rel_lower, strtolower($pattern)) !== false) {
                    $is_excluded = true;
                    break;
                }
            }
            if ($is_excluded) {
                $excluded++;
                continue;
            }

            $ext = strtolower(pathinfo($path, PATHINFO_EXTENSION));
            if (!in_array($ext, $allowed_ext, true)) {
                $skipped_ext++;
                continue;
            }

            $size = @filesize($path);
            if ($size !== false && $size > $max_file_size) {
                $output .= "--- SKIPPED LARGE FILE: {$slug}/{$rel} (" . size_format($size) . ") ---\n\n";
                $skipped_large++;
                continue;
            }

            $content = @file_get_contents($path);
            if ($content === false) {
                $unreadable++;
                continue;
            }

            $output .= "--- FILE: {$slug}/{$rel} ---\n";
            $output .= "TYPE: " . strtoupper($ext) . "\n";
            $output .= "SIZE: " . ($size !== false ? size_format($size) : 'unknown') . "\n";
            $output .= "--- BEGIN CONTENT ---\n";
            $output .= $content . "\n";
            $output .= "--- END CONTENT ---\n\n";
            $included++;

            if (strlen($output) >= $max_total_size) {
                $output .= "[SOURCE CONTEXT STOPPED: output limit reached.]\n";
                break;
            }
        }

        $summary  = "### SELECTED PLUGIN SOURCE SUMMARY ###\n";
        $summary .= "Plugin: {$slug}\n";
        $summary .= "Included files: {$included}\n";
        $summary .= "Excluded paths: {$excluded}\n";
        $summary .= "Skipped by extension: {$skipped_ext}\n";
        $summary .= "Skipped large files: {$skipped_large}\n";
        $summary .= "Unreadable files: {$unreadable}\n";
        $summary .= "--------------------------------------\n\n";

        return $summary . $output;
    }

    private static function get_debug_log_status(): string {
        $file = WP_CONTENT_DIR . '/debug.log';
        if (!file_exists($file)) {
            return 'Not found';
        }
        if (!is_readable($file)) {
            return 'Exists but not readable';
        }
        return 'Readable, ' . size_format(filesize($file));
    }

    private static function count_active_agfo_snippets(): int {
        global $wpdb;
        return (int) $wpdb->get_var($wpdb->prepare("
            SELECT COUNT(p.ID)
            FROM {$wpdb->posts} p
            INNER JOIN {$wpdb->postmeta} m ON m.post_id = p.ID
            WHERE p.post_type = %s
              AND m.meta_key = %s
              AND m.meta_value = '1'
              AND p.post_status NOT IN ('trash', 'auto-draft')
        ", 'agfo_snippet', '_agfo_active'));
    }

    private static function count_active_code_snippets(): int {
        global $wpdb;
        $table  = $wpdb->prefix . 'snippets';
        $exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
        if ($exists !== $table) {
            return 0;
        }
        return (int) $wpdb->get_var("SELECT COUNT(*) FROM {$table} WHERE active = 1");
    }

    private static function get_plugin_choices(): array {
        $out = [];
        if (!defined('WP_PLUGIN_DIR') || !is_dir(WP_PLUGIN_DIR)) {
            return $out;
        }
        $dirs = glob(WP_PLUGIN_DIR . '/*', GLOB_ONLYDIR);
        if (!is_array($dirs)) {
            return $out;
        }
        foreach ($dirs as $dir) {
            $slug = basename($dir);
            if ($slug !== '') {
                $out[$slug] = $slug;
            }
        }
        ksort($out);
        return $out;
    }

    private static function is_valid_plugin_slug(string $slug): bool {
        if ($slug === '') {
            return false;
        }
        if (strpos($slug, '..') !== false || strpos($slug, '/') !== false || strpos($slug, '\\') !== false) {
            return false;
        }
        return defined('WP_PLUGIN_DIR') && is_dir(WP_PLUGIN_DIR . '/' . $slug);
    }
}