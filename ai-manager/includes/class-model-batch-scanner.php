<?php
if ( ! defined( 'ABSPATH' ) ) exit;

if ( ! class_exists( 'AGFO_AIM_Model_Batch_Scanner' ) ) {
class AGFO_AIM_Model_Batch_Scanner {

    public static function register_hooks(): void {
        add_action( 'admin_menu', array( __CLASS__, 'add_menu' ), 20 );
        add_action( 'wp_ajax_agfo_aim_mi_list', array( __CLASS__, 'ajax_list' ) );
        add_action( 'wp_ajax_agfo_aim_mi_probe', array( __CLASS__, 'ajax_probe' ) );
    }

    public static function add_menu(): void {
        add_submenu_page(
            'agfo-ai-manager',
            'Model Intelligence',
            '🧠 Model Intelligence',
            'manage_options',
            'agfo-model-intelligence',
            array( __CLASS__, 'render_page' )
        );
    }

    private static function guard(): void {
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( array( 'message' => 'Yetki yok.' ), 403 );
        }
        check_ajax_referer( 'agfo_aim_mi_nonce', 'nonce' );
        if ( ! class_exists( 'AGFO_AIM_Model_Intelligence' ) ) {
            wp_send_json_error( array( 'message' => 'Model Intelligence sınıfı yüklenmedi.' ), 500 );
        }
    }

    public static function ajax_list(): void {
        self::guard();
        $provider = isset( $_POST['provider'] ) ? sanitize_key( wp_unslash( $_POST['provider'] ) ) : '';
        if ( $provider === '' ) $provider = AGFO_AIM_Model_Intelligence::get_active_provider();
        wp_send_json_success( array(
            'provider' => $provider,
            'models'   => AGFO_AIM_Model_Intelligence::get_models_for_provider( $provider ),
        ) );
    }

    public static function ajax_probe(): void {
        self::guard();
        $provider = isset( $_POST['provider'] ) ? sanitize_key( wp_unslash( $_POST['provider'] ) ) : '';
        $model    = isset( $_POST['model'] ) ? sanitize_text_field( wp_unslash( $_POST['model'] ) ) : '';
        if ( $provider === '' ) $provider = AGFO_AIM_Model_Intelligence::get_active_provider();
        if ( $model === '' ) wp_send_json_error( array( 'message' => 'Model boş.' ), 400 );
        $intel = AGFO_AIM_Model_Intelligence::probe_and_save( $provider, $model );
        wp_send_json_success( array( 'intelligence' => $intel ) );
    }

    public static function render_page(): void {
        if ( ! current_user_can( 'manage_options' ) ) wp_die( esc_html__( 'Yetki yok.', 'agfo-ai-manager' ) );
        $nonce = wp_create_nonce( 'agfo_aim_mi_nonce' );
        $provider = class_exists( 'AGFO_AIM_Model_Intelligence' ) ? AGFO_AIM_Model_Intelligence::get_active_provider() : 'openai';
        ?>
        <div class="wrap agfo-mi-wrap">
            <h1>AGFO AI Manager — Model Intelligence <span>v<?php echo esc_html( defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '16.17.2' ); ?></span></h1>
            <p>Aktif sağlayıcıdaki modelleri canlı test eder; chat uyumu, temperature desteği, DOCX uygunluğu, fiyat metadata ve AGFO skorlarını merkezi <code>data.json</code> içine işler.</p>

            <div class="agfo-mi-panel">
                <p class="agfo-mi-actions">
                    <button class="button button-primary" id="agfo-mi-start">Capability Scan</button>
                    <button class="button" id="agfo-mi-stop">Durdur</button>
                    <button class="button" id="agfo-mi-refresh">Listeyi Yenile</button>
                    <button class="button" id="agfo-mi-preview-docx">DOCX Preview</button>
                    <label><input type="checkbox" id="agfo-mi-skip-completed" checked> Tamamlanmışları atla</label>
                    <label><input type="checkbox" id="agfo-mi-hide-blocked"> Uyumsuzları gizle</label>
                </p>
                <div id="agfo-mi-status">Hazır. Provider: <?php echo esc_html( $provider ); ?></div>
                <div id="agfo-mi-budget">Tahmini bütçe: scan sonrası hesaplanır.</div>
            </div>

            <div class="agfo-mi-panel">
                <h2>Model Listesi</h2>
                <table class="widefat striped" id="agfo-mi-table">
                    <thead>
                        <tr>
                            <th>#</th><th>Model</th><th>Chat</th><th>Temp</th><th>DOCX</th><th>Status</th><th>Süre</th><th>Maliyet</th><th>Skor</th><th>Öneri</th><th>Not</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>

            <textarea id="agfo-mi-log" rows="14" readonly></textarea>
        </div>
        <style>
            .agfo-mi-wrap h1 span{font-size:11px;color:#64748b;font-weight:600}.agfo-mi-panel{background:#fff;border:1px solid #dcdcde;border-radius:10px;padding:14px;margin:14px 0;max-width:1320px}.agfo-mi-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.agfo-mi-actions label{font-size:12px;color:#334155}#agfo-mi-status,#agfo-mi-budget{padding:9px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;margin-top:8px}#agfo-mi-log{width:100%;font-family:Consolas,Monaco,monospace;font-size:12px}#agfo-mi-table td,#agfo-mi-table th{font-size:12px;vertical-align:top}.agfo-mi-ok{color:#047857;font-weight:700}.agfo-mi-bad{color:#b91c1c;font-weight:700}.agfo-mi-warn{color:#a16207;font-weight:700}.agfo-mi-muted{color:#64748b}
        </style>
        <script>
        (function(){
            const ajaxUrl = window.ajaxurl || <?php echo wp_json_encode( admin_url( 'admin-ajax.php' ) ); ?>;
            const nonce = <?php echo wp_json_encode( $nonce ); ?>;
            let provider = <?php echo wp_json_encode( $provider ); ?>;
            let models = [], stopped = false, totalCost = 0;
            const tbody = document.querySelector('#agfo-mi-table tbody');
            const statusEl = document.getElementById('agfo-mi-status');
            const budgetEl = document.getElementById('agfo-mi-budget');
            const logEl = document.getElementById('agfo-mi-log');
            function esc(s){return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');}
            function post(action,data){const body=new URLSearchParams(Object.assign({action:action,nonce:nonce,provider:provider},data||{}));return fetch(ajaxUrl,{method:'POST',credentials:'same-origin',body:body}).then(r=>r.json());}
            function log(s){logEl.value += s + "\n"; logEl.scrollTop = logEl.scrollHeight;}
            function status(s){statusEl.textContent = s;}
            function mark(v){if(v===true||v==='supported')return '<span class="agfo-mi-ok">YES</span>'; if(v===false||v==='unsupported'||v==='blocked')return '<span class="agfo-mi-bad">NO</span>'; return '<span class="agfo-mi-warn">?</span>';}
            function allowed(m){return m && m.supports_chat === true && m.docx_allowed === true;}
            function render(){tbody.innerHTML=''; const hide=document.getElementById('agfo-mi-hide-blocked').checked; let visible=0; models.forEach(function(m){if(hide&&!allowed(m))return; visible++; const notes=Array.isArray(m.compatibility_notes)?m.compatibility_notes.join(' | '):(m.compatibility_notes||''); const tr=document.createElement('tr'); tr.innerHTML='<td>'+visible+'</td><td><code>'+esc(m.id||m.model)+'</code><br><span class="agfo-mi-muted">'+esc(provider)+'</span></td><td>'+mark(m.supports_chat)+'</td><td>'+mark(m.temperature_status||m.supports_temperature)+'</td><td>'+mark(m.docx_allowed)+'</td><td>'+esc(m.probe_status||'not_tested')+'</td><td>'+esc(m.duration_ms||'-')+' ms</td><td>'+esc(m.estimated_cost_label||m.price_label||'price_unknown')+'</td><td>'+esc(m.final_agfo_score||m.benchmark_score||'-')+'</td><td>'+esc(m.recommendation_label||'-')+'</td><td>'+esc(notes)+'</td>'; tbody.appendChild(tr);});}
            function loadList(){status('Model listesi alınıyor...'); return post('agfo_aim_mi_list',{}).then(function(r){if(!r.success){status('Liste alınamadı: '+((r.data&&r.data.message)||'error'));return;} models=r.data.models||[]; provider=r.data.provider||provider; totalCost=0; render(); status('Liste hazır. Provider: '+provider+' | Model sayısı: '+models.length); budgetEl.textContent='Tahmini bütçe: scan sonrası hesaplanır.'; log('Loaded '+models.length+' models from '+provider);});}
            async function runAll(){stopped=false; totalCost=0; const skip=document.getElementById('agfo-mi-skip-completed').checked; for(let i=0;i<models.length;i++){if(stopped){status('Durduruldu.');break;} const m=models[i]; if(skip && (m.probe_status==='completed'||m.capability_source==='batch_probe')){log('SKIP: '+m.id);continue;} status((i+1)+'/'+models.length+' test ediliyor: '+m.id); log('TEST: '+m.id); try{const r=await post('agfo_aim_mi_probe',{model:m.id}); if(r.success){models[i]=r.data.intelligence||m; totalCost += Number(models[i].estimated_cost_value||0); log('OK: '+m.id+' | chat='+models[i].supports_chat+' | temp='+models[i].temperature_status+' | score='+models[i].final_agfo_score);}else{log('FAIL: '+m.id+' | '+((r.data&&r.data.message)||'error'));}}catch(e){log('FAIL: '+m.id+' | '+e.message);} budgetEl.textContent='Tahmini bütçe: $'+totalCost.toFixed(8)+' | Fiyat metadata yoksa price_unknown görünür.'; render(); await new Promise(resolve=>setTimeout(resolve,350));} if(!stopped)status('Tamamlandı. Sonuçlar data.json içine işlendi.');}
            function previewDocx(){const ok=models.filter(allowed); log('DOCX PREVIEW: '+ok.length+' model'); ok.forEach(m=>log('DOCX OK: '+m.id)); document.getElementById('agfo-mi-hide-blocked').checked=true; status('DOCX uygun model sayısı: '+ok.length); render();}
            document.getElementById('agfo-mi-start').addEventListener('click',runAll); document.getElementById('agfo-mi-stop').addEventListener('click',function(){stopped=true;}); document.getElementById('agfo-mi-refresh').addEventListener('click',loadList); document.getElementById('agfo-mi-preview-docx').addEventListener('click',previewDocx); document.getElementById('agfo-mi-hide-blocked').addEventListener('change',render); loadList();
        })();
        </script>
        <?php
    }
}
}
