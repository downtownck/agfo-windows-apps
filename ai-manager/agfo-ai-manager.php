<?php
/**
 * Plugin Name: AGFO AI Manager
 * Plugin URI: https://agfocert.com/
 * Description: AI Model Yönetimi + Multi-Source Benchmark
 * Version: 17.6.0
 * Requires at least: 6.0
 * Requires PHP: 7.4
 * Author: AGFOCERT
 * Author URI: https://agfocert.com/
 * License: GPL-2.0-or-later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: agfo-ai-manager
 * Domain Path: /languages
 * Revision: 17.6.0 - /editor/chat accepts max_output_tokens (256-8000) for long content generation from sources; 180 s timeout for long outputs.
 */
if (!defined('ABSPATH')) exit;

define('AGFO_AIM_VERSION',    '17.6.0');
define('AGFO_AIM_PLUGIN_DIR', plugin_dir_path(__FILE__));
define('AGFO_AIM_PLUGIN_URL', plugin_dir_url(__FILE__));
define('AGFO_AIM_DATA_DIR',   AGFO_AIM_PLUGIN_DIR . 'data/');
define('AGFO_AIM_DATA_FILE',  AGFO_AIM_DATA_DIR . 'data.json');

// NEW 17.1.2: single audited Base64 codec (loaded first; the key encryptor uses it).
require_once AGFO_AIM_PLUGIN_DIR . 'includes/core/class-binary-codec.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/functions.php';
// NEW 17.0.0: central request guard (sampling policy, learned refusals, Responses bridge,
// model fallback). Hooked at load time so every HTTP request in the site is covered.
require_once AGFO_AIM_PLUGIN_DIR . 'includes/core/class-request-guard.php';
AGFO_AIM_Request_Guard::register_hooks();
require_once AGFO_AIM_PLUGIN_DIR . 'includes/ajax/class-data.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/class-model-intelligence.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/class-model-public-api.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/class-model-batch-scanner.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/class-ai-jobs.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/class-ai-capability.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/class-ai-media.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/class-ai-image.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/class-model-catalog.php'; // NEW 17.1.0
require_once AGFO_AIM_PLUGIN_DIR . 'includes/class-code-review.php'; // NEW 17.2.0
require_once AGFO_AIM_PLUGIN_DIR . 'includes/api/class-editor-api.php'; // NEW 17.4.0
require_once AGFO_AIM_PLUGIN_DIR . 'includes/api/class-editor-tokens.php'; // NEW 17.5.0
require_once AGFO_AIM_PLUGIN_DIR . 'includes/core/class-github-updater.php'; // NEW 17.4.0

// 16.8.0 persistent runtime core. Existing public functions remain untouched.
require_once AGFO_AIM_PLUGIN_DIR . 'includes/core/class-schema.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/assets/class-asset-store.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/audio/class-audio-effects.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/core/class-installer.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/adapters/interface-adapter.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/adapters/class-adapter-openai.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/adapters/class-adapter-elevenlabs.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/adapters/class-adapter-minimax.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/adapters/class-adapter-gemini.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/adapters/class-adapter-image.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/adapters/class-adapter-registry.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/tts/class-tts-catalog.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/tts/class-speech-long.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/content/class-content-prompt-library.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/content/class-content-context.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/content/class-content-transformer.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/editor/class-classic-editor-tts.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/image/class-image-prompt-library.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/image/class-image-generator.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/editor/class-classic-editor-content.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/editor/class-classic-editor-image.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/governance/class-killswitch.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/governance/class-usage.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/governance/class-provider-quota.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/governance/class-budget.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/jobs/class-job-store.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/jobs/class-job-worker.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/assets/class-asset-delivery.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/jobs/class-job-api.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/tracker/class-native-tracker.php';

require_once AGFO_AIM_PLUGIN_DIR . 'admin/class-admin.php';
require_once AGFO_AIM_PLUGIN_DIR . 'admin/class-operations.php';
require_once AGFO_AIM_PLUGIN_DIR . 'includes/AGFO-AI-Spec-Class.php';

// CHANGED 16.17.1: AGFO_Admin, AGFO_Ajax_Data and AGFO_Encryptor were renamed to the
// plugin-specific AGFO_AIM_* prefix. If another AGFO plugin declared one of the generic
// names, the result was a "Cannot redeclare" compile-time fatal, which no try/catch can
// intercept. The legacy names are kept as aliases when they are still free, so existing
// callers keep working; when a name is already taken the alias is skipped instead of
// raising an error.
foreach ([
    'AGFO_AIM_Admin'     => 'AGFO_Admin',
    'AGFO_AIM_Ajax_Data' => 'AGFO_Ajax_Data',
    'AGFO_AIM_Encryptor' => 'AGFO_Encryptor',
] as $agfo_aim_new => $agfo_aim_legacy) {
    if (class_exists($agfo_aim_new, false) && !class_exists($agfo_aim_legacy, false)) {
        class_alias($agfo_aim_new, $agfo_aim_legacy);
    }
}
unset($agfo_aim_new, $agfo_aim_legacy);

// NEW 17.4.0: updates from GitHub Releases (SHA-256 verified, data.json preserved). Registered at
// load time because the update transient can be built before plugins_loaded callbacks finish.
AGFO_AIM_GitHub_Updater::register_hooks( __FILE__ );

add_filter( 'cron_schedules', [ 'AGFO_AIM_Installer', 'add_cron_schedules' ] );
register_activation_hook( __FILE__, [ 'AGFO_AIM_Installer', 'activate' ] );
register_deactivation_hook( __FILE__, [ 'AGFO_AIM_Installer', 'deactivate' ] );

add_action('plugins_loaded', function () {
    AGFO_AIM_Adapter_Registry::boot_defaults();
    AGFO_AIM_Installer::maybe_upgrade();

    if (class_exists('AGFO_AIM_Ajax_Data')) {
        AGFO_AIM_Ajax_Data::register_hooks();
    }
    if (class_exists('AGFO_AIM_Admin')) {
        AGFO_AIM_Admin::register_hooks();
    }
    if (class_exists('AGFO_AIM_Operations_Admin')) {
        AGFO_AIM_Operations_Admin::register_hooks();
    }
    if (class_exists('AGFO_AIM_TTS_Catalog')) {
        AGFO_AIM_TTS_Catalog::register_hooks();
    }
    if (class_exists('AGFO_AIM_Content_Transformer')) {
        AGFO_AIM_Content_Transformer::register_hooks();
    }
    if (class_exists('AGFO_AIM_Classic_Editor_TTS')) {
        AGFO_AIM_Classic_Editor_TTS::register_hooks();
    }
    if (class_exists('AGFO_AIM_Classic_Editor_Content')) {
        AGFO_AIM_Classic_Editor_Content::register_hooks();
    }
    if (class_exists('AGFO_AIM_Image_Generator')) {
        AGFO_AIM_Image_Generator::register_hooks();
    }
    if (class_exists('AGFO_AIM_Classic_Editor_Image')) {
        AGFO_AIM_Classic_Editor_Image::register_hooks();
    }
    if (class_exists('AGFO_AIM_Provider_Quota')) {
        AGFO_AIM_Provider_Quota::register_hooks();
    }
    if (class_exists('AGFO_AIM_Native_Tracker')) {
        AGFO_AIM_Native_Tracker::register_hooks();
    }
    if (class_exists('AGFO_AI_Spec_Class')) {
        AGFO_AI_Spec_Class::register_hooks();
    }
    if (class_exists('AGFO_AIM_Model_Public_API')) {
        AGFO_AIM_Model_Public_API::register_hooks();
    }
    if (class_exists('AGFO_AIM_Model_Batch_Scanner')) {
        AGFO_AIM_Model_Batch_Scanner::register_hooks();
    }
    if (class_exists('AGFO_AIM_AI_Jobs')) {
        AGFO_AIM_AI_Jobs::register_hooks();
    }
    if (class_exists('AGFO_AIM_Model_Catalog')) {
        AGFO_AIM_Model_Catalog::register_hooks(); // NEW 17.1.0
    }
    if (class_exists('AGFO_AIM_Editor_API')) {
        AGFO_AIM_Editor_API::register_hooks(); // NEW 17.4.0
    }
    if (class_exists('AGFO_AIM_Editor_Tokens')) {
        AGFO_AIM_Editor_Tokens::register_hooks(); // NEW 17.5.0
    }
    AGFO_AIM_Job_Worker::register_hooks();
    AGFO_AIM_Asset_Delivery::register_hooks();
    AGFO_AIM_Job_API::register_hooks();
});
