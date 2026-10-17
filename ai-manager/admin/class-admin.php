<?php
if (!defined('ABSPATH')) exit;

class AGFO_AIM_Admin {

public static function register_hooks(): void {
    add_action('admin_menu',            [__CLASS__, 'add_menus']);
    add_action('admin_init',            [__CLASS__, 'handle_form']);
    add_action('admin_bar_menu',        [__CLASS__, 'admin_bar'], 999);

    // ↓ HER İKİ HOOK DA — admin + frontend
    add_action('admin_enqueue_scripts', [__CLASS__, 'enqueue_assets']);
    add_action('wp_enqueue_scripts',    [__CLASS__, 'enqueue_assets']);

    // ↓ HER İKİ FOOTER DA — admin + frontend
    add_action('admin_footer',          [__CLASS__, 'render_modal']);
    add_action('wp_footer',             [__CLASS__, 'render_modal']);

    add_action('admin_notices',         [__CLASS__, 'legacy_notice']);
}

    /* ── Menü ─────────────────────────────────────────────── */

    public static function add_menus(): void {
        add_menu_page(
            'AGFO AI Manager', 'AGFO AI', 'manage_options',
            'agfo-ai-manager', [__CLASS__, 'render_settings_page'],
            'dashicons-shield-alt', 3
        );
        add_submenu_page(
            'agfo-ai-manager', 'Model Yönetimi', '🔄 Model Yönetimi',
            'manage_options', 'agfo-model-manager', [__CLASS__, 'render_model_manager_page']
        );
        add_submenu_page(
            'agfo-ai-manager', 'Chat Test', '💬 Chat Test',
            'manage_options', 'agfo-chat-test', [__CLASS__, 'render_chat_page']
        );
    }

    /* ── Asset'ler ────────────────────────────────────────── */

    /**
     * CHANGED 16.6.0: Asset surumu.
     * Onceden her sayfa yuklemesinde time() kullaniliyordu; bu, tarayici
     * onbellegini tamamen devre disi birakip her admin sayfasinda JS/CSS'in
     * yeniden indirilmesine yol aciyordu. filemtime dosya degistiginde degisir,
     * degismediginde sabit kalir; onbellek kirma davranisi korunur.
     */
    private static function asset_version( string $relative_path ): string {
        $version = defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '16.17.2';
        $file    = defined( 'AGFO_AIM_PLUGIN_DIR' ) ? AGFO_AIM_PLUGIN_DIR . $relative_path : '';
        if ( $file !== '' && file_exists( $file ) ) {
            return $version . '.' . (string) filemtime( $file );
        }
        return $version;
    }

 public static function enqueue_assets( $hook = '' ): void {
    // Giriş yapmış kullanıcı kontrolü — is_user_logged_in() yeterli
    if ( ! is_user_logged_in() ) return;
    if ( ! current_user_can( 'manage_options' ) ) return;
    // CHANGED 17.3.1: on the front end the modal is only reachable from the admin bar.
    // The small shared progress bar stays available for other AGFO front-end tools.
    if ( ! self::frontend_switcher_needed() ) {
        $p_url = defined( 'AGFO_AIM_PLUGIN_URL' ) ? AGFO_AIM_PLUGIN_URL : plugin_dir_url( __FILE__ ) . '../';
        wp_enqueue_script( 'agfo-progress', $p_url . 'assets/js/agfo-progress.js', [], self::asset_version( 'assets/js/agfo-progress.js' ), true );
        wp_enqueue_style(  'agfo-progress', $p_url . 'assets/css/agfo-progress.css', [], self::asset_version( 'assets/css/agfo-progress.css' ) );
        return;
    }

    $hook    = (string) ( $hook ?? '' );
    $version = defined( 'AGFO_AIM_VERSION' )    ? AGFO_AIM_VERSION    : '16.17.2';
    $url     = defined( 'AGFO_AIM_PLUGIN_URL' ) ? AGFO_AIM_PLUGIN_URL : plugin_dir_url( __FILE__ ) . '../';

    wp_enqueue_script(
        'agfo-switcher',
        $url . 'assets/js/script.js',
        [ 'jquery' ],
        self::asset_version( 'assets/js/script.js' ), // CHANGED 16.6.0: time() yerine filemtime.
        true
    );
    wp_localize_script( 'agfo-switcher', 'agfoConfig', [
        'ajaxurl' => admin_url( 'admin-ajax.php' ),
        'nonce'   => wp_create_nonce( 'agfo_ajax_nonce' ),
        'version' => $version,
    ] );
    wp_enqueue_style(
        'agfo-admin-style',
        $url . 'assets/css/style.css',
        [],
        self::asset_version( 'assets/css/style.css' ) // CHANGED 16.6.0: time() yerine filemtime.
    );

    // NEW 17.1.0: Translation and Image boards of AI Kontrol Merkezi.
    wp_enqueue_script(
        'agfo-control-center-boards',
        $url . 'assets/js/control-center-boards.js',
        [ 'jquery', 'agfo-switcher' ],
        self::asset_version( 'assets/js/control-center-boards.js' ),
        true
    );

    // NEW 17.0.0: redesigned AI Kontrol Merkezi modal styles.
    wp_enqueue_style(
        'agfo-control-center',
        $url . 'assets/css/control-center.css',
        [ 'agfo-admin-style' ],
        self::asset_version( 'assets/css/control-center.css' )
    );

    // CHANGED 16.2.0: AGFO Progress mini bar (tum admin AGFO sayfalarinda hazir bekler; islem yokken gorunmez).
    wp_enqueue_script( 'agfo-progress', $url . 'assets/js/agfo-progress.js', [], self::asset_version( 'assets/js/agfo-progress.js' ), true );
    wp_enqueue_style(  'agfo-progress', $url . 'assets/css/agfo-progress.css', [], self::asset_version( 'assets/css/agfo-progress.css' ) );

    if ( ! empty( $hook ) && strpos( $hook, 'agfo-chat-test' ) !== false ) {
        wp_enqueue_style(
            'agfo-chat-style',
            $url . 'assets/css/chat-test.css',
            [ 'agfo-admin-style' ],
            $version
        );
        wp_enqueue_script(
            'agfo-chat-test',
            $url . 'assets/js/chat-test.js',
            [ 'jquery', 'agfo-switcher' ],
            $version,
            true
        );
    }
}


    /* ── Admin Bar ────────────────────────────────────────── */

    public static function admin_bar( $wp_admin_bar ): void {
        if ( ! current_user_can( 'manage_options' ) ) return;
        $provider     = get_option( 'agfo_selected_provider', 'openai' );
        $is_reasoning = get_option( 'agfo_reasoning_mode', 0 );
        $wp_admin_bar->add_node( [
            'id'    => 'agfo-quick-switch',
            'title' => ( $is_reasoning ? '🧠' : '⚡' ) . ' AI: ' . ucfirst( $provider ),
            'href'  => '#',
            'meta'  => [ 'onclick' => 'agfoOpenSwitcher(); return false;' ],
        ] );
    }

    /* ── Form İşleme ──────────────────────────────────────── */

    public static function handle_form(): void {
        if ( ! current_user_can( 'manage_options' ) )                          return;
        if ( ! isset( $_POST['agfo_api_nonce'] ) )                             return;
        if ( ! wp_verify_nonce( $_POST['agfo_api_nonce'], 'agfo_save_keys' ) ) return;

        global $AGFO_ENC;
        $providers = agfo_api_registry();

        if ( isset( $_POST['submit'] ) && $AGFO_ENC ) {
            foreach ( $providers as $code => $p ) {
                $field = 'key_' . $code;
                if ( ! empty( $_POST[ $field ] ) ) {
                    $val = sanitize_text_field( $_POST[ $field ] );
                    update_option( 'agfo_' . $code . '_api_key', $AGFO_ENC->encrypt( $val ) );
                }
            }
        }

        if ( isset( $_POST['agfo_delete_key'] ) ) {
            $code = sanitize_text_field( $_POST['agfo_delete_key'] );
            delete_option( 'agfo_' . $code . '_api_key' );
            if ( agfo_get_selected_provider() === $code ) {
                update_option( 'agfo_selected_provider', 'openai' );
            }
        }

        // CHANGED: Save OpenRouter Fusion Manager settings from the main AGFO AI Manager page.
        if ( isset( $_POST['agfo_fusion_mode'] ) ) {
            $mode = sanitize_key( wp_unslash( $_POST['agfo_fusion_mode'] ) );
            if ( in_array( $mode, [ 'off', 'auto', 'force' ], true ) ) {
                update_option( 'agfo_openrouter_fusion_mode', $mode );
            }
        }
        if ( isset( $_POST['agfo_fusion_profile'] ) ) {
            $profile  = sanitize_key( wp_unslash( $_POST['agfo_fusion_profile'] ) );
            $profiles = function_exists( 'agfo_openrouter_get_fusion_profiles' ) ? agfo_openrouter_get_fusion_profiles() : [];
            if ( isset( $profiles[ $profile ] ) ) {
                update_option( 'agfo_openrouter_fusion_profile', $profile );
            }
        }
        if ( isset( $_POST['agfo_fusion_analysis_models'] ) ) {
            $models = sanitize_textarea_field( wp_unslash( $_POST['agfo_fusion_analysis_models'] ) );
            update_option( 'agfo_openrouter_fusion_analysis_models', $models );
        }
        if ( isset( $_POST['agfo_fusion_judge_model'] ) ) {
            update_option( 'agfo_openrouter_fusion_judge_model', sanitize_text_field( wp_unslash( $_POST['agfo_fusion_judge_model'] ) ) );
        }
        if ( isset( $_POST['agfo_fusion_max_tool_calls'] ) ) {
            update_option( 'agfo_openrouter_fusion_max_tool_calls', max( 1, min( 16, absint( $_POST['agfo_fusion_max_tool_calls'] ) ) ) );
        }
        if ( isset( $_POST['agfo_fusion_max_completion_tokens'] ) ) {
            update_option( 'agfo_openrouter_fusion_max_completion_tokens', absint( $_POST['agfo_fusion_max_completion_tokens'] ) );
        }
        if ( isset( $_POST['agfo_fusion_temperature'] ) ) {
            $temp = trim( sanitize_text_field( wp_unslash( $_POST['agfo_fusion_temperature'] ) ) );
            update_option( 'agfo_openrouter_fusion_temperature', $temp );
        }

        // CHANGED 16.5.0: Model filtreleme ayarları (şema + özel kategoriler + istisna listesi).
        if ( isset( $_POST['agfo_model_filter_preset'] ) && function_exists( 'agfo_model_filter_presets' ) ) {
            $preset  = sanitize_key( wp_unslash( $_POST['agfo_model_filter_preset'] ) );
            $presets = agfo_model_filter_presets();
            if ( isset( $presets[ $preset ] ) ) {
                $saved = get_option( 'agfo_model_filter_settings', [] );
                if ( ! is_array( $saved ) ) $saved = [];
                $saved['preset'] = $preset;

                if ( 'custom' === $preset ) {
                    $all_ids = array_keys( agfo_model_filter_categories() );
                    $posted  = isset( $_POST['agfo_model_filter_categories'] ) && is_array( $_POST['agfo_model_filter_categories'] )
                        ? array_map( 'sanitize_key', wp_unslash( $_POST['agfo_model_filter_categories'] ) )
                        : [];
                    $saved['custom_categories'] = array_values( array_intersect( $all_ids, $posted ) );
                }

                $saved['whitelist'] = isset( $_POST['agfo_model_filter_whitelist'] )
                    ? sanitize_textarea_field( wp_unslash( $_POST['agfo_model_filter_whitelist'] ) )
                    : '';

                update_option( 'agfo_model_filter_settings', $saved );
            }
        }

        // CHANGED 16.6.0: Yetenek Yonlendirme ayarlari. 'chat' bilincli olarak
        // kaydedilmez; chat saglayicisi eskisi gibi Quick Switch uzerinden secilir.
        if ( isset( $_POST['agfo_capability_routing'] ) && is_array( $_POST['agfo_capability_routing'] )
             && function_exists( 'agfo_save_capability_routing' ) ) {
            $posted  = wp_unslash( $_POST['agfo_capability_routing'] );
            $routing = [];
            foreach ( $posted as $cap => $row ) {
                if ( ! is_array( $row ) ) continue;
                $cap = sanitize_key( (string) $cap );
                if ( 'chat' === $cap ) continue;
                $routing[ $cap ] = [
                    'provider' => sanitize_key( (string) ( $row['provider'] ?? '' ) ),
                    'model'    => sanitize_text_field( (string) ( $row['model'] ?? '' ) ),
                ];
            }
            if ( ! empty( $routing ) ) {
                agfo_save_capability_routing( $routing );
            }
        }

        wp_safe_redirect( add_query_arg(
            [ 'page' => 'agfo-ai-manager', 'updated' => '1' ],
            admin_url( 'admin.php' )
        ) );
        exit;
    }

    /* ── Ayar Sayfası ─────────────────────────────────────── */

    public static function render_settings_page(): void {
        if ( ! current_user_can( 'manage_options' ) ) return;
        $providers = agfo_api_registry();
        $version   = defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '16.17.2';
        ?>
        <div class="wrap" style="max-width:1200px;">
            <h1>🔑 AGFO AI Manager v<?php echo esc_html( $version ); ?></h1>
            <p>AI Model Yönetimi + Multi-Source Benchmark Sistemi</p>
            <?php if ( isset( $_GET['updated'] ) ) : ?>
                <div class="notice notice-success is-dismissible"><p>✔ Ayarlar kaydedildi!</p></div>
            <?php endif; ?>
            <form method="post" action="">
                <?php wp_nonce_field( 'agfo_save_keys', 'agfo_api_nonce' ); ?>
                <table class="form-table">
                    <?php foreach ( $providers as $code => $p ) :
                        $has_key = ! empty( get_option( 'agfo_' . $code . '_api_key', '' ) ); ?>
                        <tr>
                            <th scope="row">
                                <?php echo esc_html( $p['label'] ); ?>
                                <?php if ( $has_key ) : ?>
                                    <span style="color:green;margin-left:6px;">✔ Kayıtlı</span>
                                <?php endif; ?>
                            </th>
                            <td>
                                <input type="password"
                                       name="key_<?php echo esc_attr( $code ); ?>"
                                       class="regular-text"
                                       placeholder="<?php echo $has_key ? 'Yeni anahtar girin' : 'API Key'; ?>">
                                <?php if ( $has_key ) : ?>
                                    <button type="submit"
                                            name="agfo_delete_key"
                                            value="<?php echo esc_attr( $code ); ?>"
                                            class="button button-secondary"
                                            onclick="return confirm('Silmek istediğinize emin misiniz?')">Sil</button>
                                <?php endif; ?>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                </table>

                <?php
                // CHANGED: OpenRouter Fusion Manager is stored centrally in AI Manager, not in dependent AGFO plugins.
                $fusion_config   = function_exists( 'agfo_openrouter_get_fusion_config' ) ? agfo_openrouter_get_fusion_config() : [];
                $fusion_profiles = function_exists( 'agfo_openrouter_get_fusion_profiles' ) ? agfo_openrouter_get_fusion_profiles() : [];
                $fusion_models   = (string) get_option( 'agfo_openrouter_fusion_analysis_models', '' );
                ?>
                <div style="margin-top:24px;padding:18px;border:1px solid #dcdcde;border-radius:10px;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.04);">
                    <h2 style="margin-top:0;">🧠 OpenRouter Fusion Manager</h2>
                    <p class="description">
                        Fusion, sadece OpenRouter seçili çağrılarda merkezi olarak body içine <code>openrouter:fusion</code> tool bilgisini ekler. Diğer AGFO eklentileri aynı <code>agfo_api_post()</code> akışını kullanmaya devam eder.
                    </p>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-top:14px;">
                        <label>
                            <strong>Fusion Modu</strong><br>
                            <select name="agfo_fusion_mode" style="width:100%;margin-top:6px;">
                                <option value="off" <?php selected( $fusion_config['mode'] ?? 'off', 'off' ); ?>>Kapalı</option>
                                <option value="auto" <?php selected( $fusion_config['mode'] ?? 'off', 'auto' ); ?>>Auto - model gerekirse çağırır</option>
                                <option value="force" <?php selected( $fusion_config['mode'] ?? 'off', 'force' ); ?>>Force - her OpenRouter isteğinde zorunlu</option>
                            </select>
                        </label>
                        <label>
                            <strong>Fusion Profili</strong><br>
                            <select name="agfo_fusion_profile" style="width:100%;margin-top:6px;">
                                <?php foreach ( $fusion_profiles as $fp_code => $fp ) : ?>
                                    <option value="<?php echo esc_attr( $fp_code ); ?>" <?php selected( $fusion_config['profile'] ?? 'balanced', $fp_code ); ?>>
                                        <?php echo esc_html( $fp['label'] ?? $fp_code ); ?>
                                    </option>
                                <?php endforeach; ?>
                            </select>
                        </label>
                        <label>
                            <strong>Judge Model</strong><br>
                            <input type="text" name="agfo_fusion_judge_model" value="<?php echo esc_attr( $fusion_config['judge_model'] ?? '' ); ?>" placeholder="Boşsa dış model kullanılır" style="width:100%;margin-top:6px;">
                        </label>
                        <label>
                            <strong>Max Tool Calls</strong><br>
                            <input type="number" name="agfo_fusion_max_tool_calls" min="1" max="16" value="<?php echo esc_attr( (string) ( $fusion_config['max_tool_calls'] ?? 8 ) ); ?>" style="width:100%;margin-top:6px;">
                        </label>
                        <label>
                            <strong>Max Completion Tokens</strong><br>
                            <input type="number" name="agfo_fusion_max_completion_tokens" min="0" step="256" value="<?php echo esc_attr( (string) ( $fusion_config['max_completion_tokens'] ?? 0 ) ); ?>" placeholder="0 = sağlayıcı varsayılanı" style="width:100%;margin-top:6px;">
                        </label>
                        <label>
                            <strong>Temperature</strong><br>
                            <input type="text" name="agfo_fusion_temperature" value="<?php echo esc_attr( (string) get_option( 'agfo_openrouter_fusion_temperature', '' ) ); ?>" placeholder="Boş = varsayılan" style="width:100%;margin-top:6px;">
                        </label>
                    </div>
                    <label style="display:block;margin-top:16px;">
                        <strong>Özel Panel Modelleri</strong><br>
                        <textarea name="agfo_fusion_analysis_models" rows="5" style="width:100%;margin-top:6px;font-family:Consolas,monospace;" placeholder="Her satıra bir model veya JSON array yazılabilir."><?php echo esc_textarea( $fusion_models ); ?></textarea>
                    </label>
                    <p class="description" style="margin-bottom:0;">
                        Özel profil seçili değilse yukarıdaki panel listesi kullanılmaz. Fusion web_search/web_fetch kullandığı için gizli müşteri verilerinde bilinçli kullanılmalıdır.
                    </p>
                </div>

                <?php
                // CHANGED 16.5.0: Model Filtreleme — şema tabanlı kompakt kart.
                if ( function_exists( 'agfo_get_model_filter_settings' ) ) :
                    $mf_settings   = agfo_get_model_filter_settings();
                    $mf_presets    = agfo_model_filter_presets();
                    $mf_categories = agfo_model_filter_categories();
                    $mf_saved_raw  = get_option( 'agfo_model_filter_settings', [] );
                    $mf_custom     = ( isset( $mf_saved_raw['custom_categories'] ) && is_array( $mf_saved_raw['custom_categories'] ) )
                        ? $mf_saved_raw['custom_categories']
                        : array_keys( $mf_categories );
                    $mf_whitelist  = isset( $mf_saved_raw['whitelist'] ) && is_string( $mf_saved_raw['whitelist'] ) ? $mf_saved_raw['whitelist'] : '';
                    ?>
                    <div style="margin-top:24px;padding:18px;border:1px solid #dcdcde;border-radius:10px;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.04);">
                        <h2 style="margin-top:0;">🧹 Model Filtreleme</h2>
                        <p class="description">
                            Sağlayıcılardan çekilen model listelerinden chat için anlamsız olanları (görsel/ses/video üretim, embedding vb.) gizler.
                            Değişiklik, Model Yönetimi'nde <strong>Yenile / Tüm Modelleri Yenile</strong> sonrası listeye yansır.
                        </p>
                        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;margin-top:14px;">
                            <label>
                                <strong>Filtre Şeması</strong><br>
                                <select name="agfo_model_filter_preset" id="agfo-model-filter-preset" style="width:100%;margin-top:6px;">
                                    <?php foreach ( $mf_presets as $mf_code => $mf_p ) : ?>
                                        <option value="<?php echo esc_attr( $mf_code ); ?>" <?php selected( $mf_settings['preset'], $mf_code ); ?>><?php echo esc_html( $mf_p['label'] ); ?></option>
                                    <?php endforeach; ?>
                                </select>
                            </label>
                            <label>
                                <strong>İstisna Listesi</strong> <span class="description">(her satıra bir ad; filtreye takılsa da geçer)</span><br>
                                <textarea name="agfo_model_filter_whitelist" rows="2" style="width:100%;margin-top:6px;font-family:Consolas,monospace;" placeholder="örn. deep-research&#10;qwen-vl-max"><?php echo esc_textarea( $mf_whitelist ); ?></textarea>
                            </label>
                        </div>
                        <div id="agfo-model-filter-custom" style="margin-top:12px;<?php echo ( 'custom' === $mf_settings['preset'] ) ? '' : 'display:none;'; ?>">
                            <strong>Özel kategoriler</strong> <span class="description">(işaretli olanlar gizlenir)</span>
                            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:6px 16px;margin-top:8px;">
                                <?php foreach ( $mf_categories as $mf_cat_id => $mf_cat ) : ?>
                                    <label style="font-size:13px;">
                                        <input type="checkbox" name="agfo_model_filter_categories[]" value="<?php echo esc_attr( $mf_cat_id ); ?>" <?php checked( in_array( $mf_cat_id, $mf_custom, true ) ); ?>>
                                        <?php echo esc_html( $mf_cat['label'] ); ?>
                                    </label>
                                <?php endforeach; ?>
                            </div>
                        </div>
                        <script>
                        (function(){
                            var sel = document.getElementById('agfo-model-filter-preset');
                            var box = document.getElementById('agfo-model-filter-custom');
                            if (sel && box) {
                                sel.addEventListener('change', function(){
                                    box.style.display = (sel.value === 'custom') ? '' : 'none';
                                });
                            }
                        })();
                        </script>
                    </div>
                <?php endif; ?>

                <?php self::render_capability_routing_card(); ?>

                <?php self::render_version_info_card(); ?>

                <?php submit_button( 'Kaydet', 'primary', 'submit' ); ?>
            </form>
        </div>
        <?php
    }


    /**
     * CHANGED 16.6.0: Yetenek Yonlendirme karti.
     * Chat disi modalitelerin hangi saglayici/modele gidecegini belirler.
     * Varsayilan "Otomatik"tir; gunluk kullanimda dokunulmasi gerekmez.
     */
    private static function render_capability_routing_card(): void {
        if ( ! function_exists( 'agfo_ai_capabilities' ) || ! function_exists( 'agfo_get_capability_routing' ) ) {
            return;
        }

        $caps    = agfo_ai_capabilities();
        $routing = agfo_get_capability_routing();

        // 'chat' bu kartta gosterilmez; chat saglayicisi Quick Switch'ten secilir.
        unset( $caps['chat'] );
        if ( empty( $caps ) ) return;
        ?>
        <div style="margin-top:24px;padding:18px;border:1px solid #dcdcde;border-radius:10px;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.04);">
            <h2 style="margin-top:0;">🎛️ Yetenek Yönlendirme</h2>
            <p class="description">
                Chat dışı modaliteler (müzik üretimi, ses dönüşümü) için hangi sağlayıcının kullanılacağını belirler.
                <strong>Otomatik</strong> bırakılırsa anahtarı tanımlı ilk uygun sağlayıcı seçilir.
                Bu ayar chat davranışını etkilemez; metin üretimi eskisi gibi Quick Switch'ten yönetilir.
            </p>
            <table class="form-table" style="margin-top:6px;">
                <?php foreach ( $caps as $cap_id => $cap ) :
                    $available = function_exists( 'agfo_providers_for_capability' )
                        ? agfo_providers_for_capability( $cap_id, false )
                        : [];
                    $current   = isset( $routing[ $cap_id ] ) ? $routing[ $cap_id ] : [ 'provider' => '', 'model' => '' ];
                    ?>
                    <tr>
                        <th scope="row" style="width:220px;">
                            <?php echo esc_html( $cap['label'] ?? $cap_id ); ?><br>
                            <span class="description" style="font-weight:400;"><?php echo esc_html( $cap['description'] ?? '' ); ?></span>
                        </th>
                        <td>
                            <select name="agfo_capability_routing[<?php echo esc_attr( $cap_id ); ?>][provider]" style="min-width:200px;">
                                <option value=""><?php esc_html_e( 'Otomatik', 'agfo-ai-manager' ); ?></option>
                                <?php foreach ( $available as $prov_code => $prov_label ) :
                                    $has_key = ! empty( agfo_get_api_key( $prov_code ) ); ?>
                                    <option value="<?php echo esc_attr( $prov_code ); ?>" <?php selected( $current['provider'], $prov_code ); ?>>
                                        <?php echo esc_html( $prov_label . ( $has_key ? '' : ' (anahtar yok)' ) ); ?>
                                    </option>
                                <?php endforeach; ?>
                            </select>
                            <input type="text"
                                   name="agfo_capability_routing[<?php echo esc_attr( $cap_id ); ?>][model]"
                                   value="<?php echo esc_attr( $current['model'] ); ?>"
                                   class="regular-text"
                                   placeholder="Model (boş = sağlayıcı varsayılanı)">
                        </td>
                    </tr>
                <?php endforeach; ?>
            </table>
            <p class="description" style="margin-bottom:0;">
                Örnek model kimlikleri — OpenRouter: <code>google/lyria-3-pro-preview</code> ·
                fal.ai: <code>fal-ai/stable-audio-25/text-to-audio</code>
            </p>
        </div>
        <?php
    }

    private static function render_version_info_card(): void {
        $version  = defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '16.17.2';
        $history  = [];
        $revision = defined( 'AGFO_AIM_PLUGIN_DIR' ) ? AGFO_AIM_PLUGIN_DIR . 'revision.json' : '';
        if ( $revision && is_readable( $revision ) ) {
            $decoded = json_decode( (string) file_get_contents( $revision ), true );
            if ( is_array( $decoded ) && ! empty( $decoded['releases'] ) && is_array( $decoded['releases'] ) ) {
                $history = array_slice( $decoded['releases'], 0, 5 );
            }
        }
        if ( ! $history ) {
            $history[] = [
                'version' => $version,
                'date'    => '',
                'type'    => 'MINOR',
                'summary' => 'TTS, kalıcı iş kuyruğu, özel varlık deposu ve maliyet koruması.',
            ];
        }
        ?>
        <div style="margin-top:18px;padding:14px;border:1px solid #e5e7eb;border-radius:10px;background:#fafafa;">
            <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">
                <strong>AGFO AI Manager Version Info</strong>
                <span style="font-size:9px;color:#6b7280;">v<?php echo esc_html( $version ); ?></span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:10px;">
                <?php foreach ( $history as $item ) : ?>
                    <div style="padding:10px;border:1px solid #e5e7eb;border-radius:8px;background:#fff;">
                        <div style="font-size:9px;color:#6b7280;"><?php echo esc_html( (string) ( $item['type'] ?? '' ) ); ?> / v<?php echo esc_html( (string) ( $item['version'] ?? '' ) ); ?><?php if ( ! empty( $item['date'] ) ) : ?> / <?php echo esc_html( (string) $item['date'] ); ?><?php endif; ?></div>
                        <div style="font-size:12px;color:#4b5563;margin-top:4px;"><?php echo esc_html( (string) ( $item['summary'] ?? '' ) ); ?></div>
                    </div>
                <?php endforeach; ?>
            </div>
            <script type="application/json" id="agfo-ai-manager-version-history-json"><?php echo wp_json_encode( $history, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ); ?></script>
        </div>
        <?php
    }

    /* ── Model Yönetimi ───────────────────────────────────── */

    public static function render_model_manager_page(): void {
        if ( ! current_user_can( 'manage_options' ) ) wp_die( 'Yetki yok.' );
        $providers = agfo_api_registry();
        ?>
        <div class="wrap">
            <h1>🔄 Model Yönetimi</h1>
            <p class="description">Sağlayıcılardan güncel model listelerini çekin.</p>
            <div style="margin:20px 0;display:flex;gap:10px;">
                <button type="button" id="agfo-refresh-all-btn" class="button button-primary button-large">
                    🔄 Tüm Modelleri Yenile
                </button>
                <button type="button" id="agfo-clear-cache-btn" class="button button-secondary">
                    🗑️ Önbelleği Temizle
                </button>
            </div>
            <table class="wp-list-table widefat fixed striped">
                <thead>
                    <tr>
                        <th style="width:160px;">Sağlayıcı</th>
                        <th style="width:120px;">Durum</th>
                        <th style="width:70px;text-align:center;">Ham</th>
                        <th style="width:80px;text-align:center;">Filtrelenen</th>
                        <th style="width:70px;text-align:center;">Kalan</th>
                        <th style="width:150px;">Son Güncelleme</th>
                        <th style="width:110px;text-align:center;">İşlem</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ( $providers as $code => $info ) :
                        if ( ( $info['type'] ?? '' ) !== 'llm' ) continue;
                        $models    = get_option( "agfo_models_{$code}", [] );
                        $updated   = get_option( "agfo_models_{$code}_updated", '-' );
                        $has_key   = ! empty( agfo_get_api_key( $code ) );
                        $raw_count = get_option( "agfo_models_{$code}_raw_count", 0 );
                        $fil_count = get_option( "agfo_models_{$code}_filtered_count", 0 );
                    ?>
                    <tr id="agfo-row-<?php echo esc_attr( $code ); ?>">
                        <td><strong><?php echo esc_html( $info['label'] ?? $code ); ?></strong></td>
                        <td>
                            <?php if ( $has_key ) : ?>
                                <span style="color:#46b450;font-weight:600;">✅ API Key OK</span>
                            <?php else : ?>
                                <span style="color:#dc3232;font-weight:600;">❌ API Key Yok</span>
                            <?php endif; ?>
                        </td>
                        <td style="text-align:center;">
                            <span class="raw-count"><?php echo (int) $raw_count; ?></span>
                        </td>
                        <td style="text-align:center;">
                            <span class="filtered-count" style="color:#dc3232;font-weight:600;">
                                <?php echo (int) $fil_count; ?>
                            </span>
                        </td>
                        <td style="text-align:center;">
                            <span class="model-count" style="display:inline-block;padding:3px 10px;background:#46b450;color:#fff;border-radius:3px;font-weight:600;">
                                <?php echo is_array( $models ) ? count( $models ) : 0; ?>
                            </span>
                        </td>
                        <td>
                            <small style="color:#646970;">
                                <?php
                                if ( $updated && $updated !== '-' ) {
                                    $date = date_create( $updated );
                                    echo $date ? date_format( $date, 'd.m.Y H:i' ) : esc_html( $updated );
                                } else {
                                    echo '-';
                                }
                                ?>
                            </small>
                        </td>
                        <td style="text-align:center;">
                            <button type="button"
                                    class="button agfo-refresh-single"
                                    data-provider="<?php echo esc_attr( $code ); ?>"
                                    <?php echo ! $has_key ? 'disabled' : ''; ?>>
                                🔄 Yenile
                            </button>
                        </td>
                    </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
            <div id="agfo-refresh-status"
                 style="margin-top:20px;padding:15px;display:none;border-radius:4px;font-family:monospace;font-size:13px;white-space:pre-wrap;">
            </div>
        </div>
        <?php
    }

    /* ── Chat Test Sayfası ────────────────────────────────── */

    public static function render_chat_page(): void {
        if ( ! current_user_can( 'manage_options' ) ) wp_die( 'Yetki yok.' );
        $providers        = agfo_api_registry();
        $active_providers = [];
        foreach ( $providers as $code => $p ) {
            if ( ! empty( agfo_get_api_key( $code ) ) ) {
                $active_providers[ $code ] = $p;
            }
        }
        ?>
        <div class="wrap agfo-chat-wrap">
            <div class="agfo-chat-page-header">
                <h1>💬 Chat Test</h1>
                <p>Sağlayıcı ve model seçerek API bağlantınızı gerçek zamanlı test edin.</p>
            </div>
            <?php if ( empty( $active_providers ) ) : ?>
                <div class="notice notice-warning">
                    <p>⚠️ Henüz API anahtarı tanımlanmamış.
                       <a href="<?php echo admin_url( 'admin.php?page=agfo-ai-manager' ); ?>">
                           Ayarlar sayfasına gidin →
                       </a>
                    </p>
                </div>
            <?php else : ?>
            <div class="agfo-chat-layout">

                <!-- Sol Sidebar -->
                <div class="agfo-chat-sidebar">
                    <div class="agfo-chat-card">
                        <div class="agfo-chat-card-title">⚙️ Bağlantı</div>
                        <label class="agfo-chat-label">Sağlayıcı</label>
                        <select id="ct-provider" class="agfo-chat-select">
                            <?php foreach ( $active_providers as $code => $p ) : ?>
                                <option value="<?php echo esc_attr( $code ); ?>"
                                    <?php selected( get_option( 'agfo_selected_provider', 'openai' ), $code ); ?>>
                                    <?php echo esc_html( $p['label'] ); ?>
                                </option>
                            <?php endforeach; ?>
                        </select>
                        <label class="agfo-chat-label" style="margin-top:10px;">Model</label>
                        <select id="ct-model" class="agfo-chat-select">
                            <option>Yükleniyor...</option>
                        </select>
                    </div>

                    <div class="agfo-chat-card">
                        <div class="agfo-chat-card-title">🎛️ Parametreler</div>
                        <label class="agfo-chat-label">
                            Sıcaklık: <strong id="ct-temp-val">0.7</strong>
                        </label>
                        <input type="range" id="ct-temperature"
                               min="0" max="2" step="0.1" value="0.7"
                               class="agfo-chat-range">
                        <label class="agfo-chat-label" style="margin-top:10px;">Max Token</label>
                        <input type="number" id="ct-max-tokens"
                               value="1024" min="64" max="32000" step="64"
                               class="agfo-chat-input-sm">
                        <div class="agfo-chat-check-row" style="margin-top:10px;">
                            <input type="checkbox" id="ct-reasoning">
                            <label for="ct-reasoning">🧠 Reasoning Modu</label>
                        </div>
                    </div>

                    <div class="agfo-chat-card">
                        <div class="agfo-chat-card-title">📋 System Prompt</div>
                        <textarea id="ct-system" class="agfo-chat-textarea"
                                  placeholder="Sen yardımcı bir AI asistanısın..."></textarea>
                    </div>

                    <div class="agfo-chat-card" id="ct-stats-card" style="display:none;">
                        <div class="agfo-chat-card-title">📊 Son İstek</div>
                        <div id="ct-stats" class="agfo-chat-stats"></div>
                    </div>
                </div>

                <!-- Sağ: Chat Ana Alan -->
                <div class="agfo-chat-main">
                    <div class="agfo-chat-header">
                        <div class="agfo-chat-header-info">
                            <div class="agfo-chat-header-dot" id="ct-status-dot"></div>
                            <span class="agfo-chat-header-label" id="ct-header-provider">—</span>
                            <span class="agfo-chat-header-model" id="ct-header-model"></span>
                        </div>
                        <button id="ct-clear-btn" class="agfo-btn-secondary">🗑️ Temizle</button>
                    </div>
                    <div class="agfo-chat-messages" id="ct-messages">
                        <div class="agfo-chat-welcome">
                            <div class="agfo-chat-welcome-icon">💬</div>
                            <div class="agfo-chat-welcome-text">
                                Sağlayıcı ve model seçin, mesaj gönderin.
                            </div>
                        </div>
                    </div>
                    <div class="agfo-chat-input-area">
                        <textarea id="ct-input" class="agfo-chat-input"
                                  placeholder="Mesajınızı yazın..." rows="3"></textarea>
                        <div class="agfo-chat-input-actions">
                            <span class="agfo-chat-hint">
                                <kbd>Ctrl</kbd> + <kbd>Enter</kbd> ile gönder
                            </span>
                            <button id="ct-send-btn" class="agfo-btn-primary">➤ Gönder</button>
                        </div>
                    </div>
                </div>

            </div>
            <?php endif; ?>
        </div>
        <?php
    }

    /* ── Modal ────────────────────────────────────────────── */

    public static function render_modal(): void {
        if ( ! current_user_can( 'manage_options' ) ) return;
        // CHANGED 17.3.1: skip the modal markup on front-end pages without the admin bar.
        if ( ! self::frontend_switcher_needed() ) return;

        $modal_path = defined( 'AGFO_AIM_PLUGIN_DIR' )
            ? AGFO_AIM_PLUGIN_DIR . 'includes/partials/modal.php'
            : plugin_dir_path( __FILE__ ) . '../includes/partials/modal.php';

        if ( file_exists( $modal_path ) ) {
            include $modal_path;
        }
        // Tüm style ve script modal.php içinden geliyor — buraya hiçbir şey ekleme
    }

    /**
     * NEW 17.3.1: whether the AI Kontrol Merkezi assets/markup are needed on this request.
     * Always true in wp-admin. On the front end only when the admin bar (the modal's only
     * entry point there) is showing; the filter lets a front-end tool opt in.
     */
    public static function frontend_switcher_needed(): bool {
        if ( is_admin() ) {
            return true;
        }
        $needed = function_exists( 'is_admin_bar_showing' ) ? is_admin_bar_showing() : true;
        return (bool) apply_filters( 'agfo_aim_frontend_control_center', $needed );
    }

    /* ── Legacy Notice ────────────────────────────────────── */

    public static function legacy_notice(): void {
        $screen = get_current_screen();
        if ( ! $screen || $screen->id !== 'toplevel_page_agfo-ai-manager' ) return;
        if ( get_option( 'agfo_legacy_notice_shown' ) ) return;
        $version = defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '16.17.2';
        ?>
        <div class="notice notice-success is-dismissible">
            <p>
                <strong>✅ AGFO AI Manager v<?php echo esc_html( $version ); ?> – Geriye Dönük Uyumluluk Aktif</strong><br>
                Eski pluginleriniz (<code>agfo_get_priority_api_key</code>) otomatik olarak yeni API'ye yönlendirilecek.
            </p>
        </div>
        <?php
        update_option( 'agfo_legacy_notice_shown', true );
    }
}
