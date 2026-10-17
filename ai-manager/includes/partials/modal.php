<?php
/**
 * AI Kontrol Merkezi — quick switch modal markup.
 *
 * CHANGED 17.0.0: full redesign. Styles moved to assets/css/control-center.css
 * (enqueued by AGFO_AIM_Admin::enqueue_assets). Every element id and class that
 * assets/js/script.js or other AGFO plugins rely on is kept; #qs-model stays as the
 * hidden source of truth behind the new #qs-model-list table.
 *
 * @package AGFO_AI_Manager
 */
if (!defined('ABSPATH')) exit;

$providers         = agfo_api_registry();
$selected_provider = agfo_get_selected_provider();
$agfo_version      = defined('AGFO_AIM_VERSION') ? AGFO_AIM_VERSION : '';

$brands = [
    'openai'    => 'OpenAI',
    'claude'    => 'Claude',
    'gemini'    => 'Gemini',
    'grok'      => 'Grok',
    'llama'     => 'Llama',
    'qwen'      => 'Qwen',
    'deepseek'  => 'DeepSeek',
    'mistral'   => 'Mistral',
    'minimax'   => 'MiniMax',
    'kimi'      => 'Kimi',
    'nvidia'    => 'Nvidia',
    'glm'       => 'GLM',
    'bytedance' => 'ByteDance',
    'phi'       => 'Phi',
    'step'      => 'Step',
];

// Context sizes: one sequential cobalt ramp, small → large.
$contexts = [
    '8k'   => ['8K',    '#c9d1f6'],
    '16k'  => ['16K',   '#a9b6f1'],
    '32k'  => ['32K',   '#8496ea'],
    '64k'  => ['64K',   '#5d75e1'],
    '100k' => ['100K+', '#3c58d9'],
    '200k' => ['200K+', '#2a42b5'],
    '1m'   => ['1M+',   '#1b2c80'],
];
?>
<div id="agfo-switcher-overlay" onclick="agfoCloseSwitcher()"></div>

<div id="agfo-switcher-modal" role="dialog" aria-modal="true" aria-labelledby="ax-title">

    <header class="ax-head">
        <div class="ax-title" id="ax-title">
            <span class="ax-mark" aria-hidden="true">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h10M3 8h6M3 12h8"/><circle cx="12" cy="8" r="1.4" fill="currentColor" stroke="none"/></svg>
            </span>
            AI Kontrol Merkezi
        </div>
        <span class="ax-head-sub">Varsayılan sağlayıcı ve model tüm AGFO eklentilerine uygulanır</span>
        <div class="ax-head-right">
            <span id="qs-status-indicator" data-state="busy">Yükleniyor</span>
            <button type="button" class="ax-icon-btn agfo-mclose" onclick="agfoCloseSwitcher()" aria-label="Kapat">
                <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M4.5 4.5l9 9M13.5 4.5l-9 9"/></svg>
            </button>
        </div>
    </header>

    <div class="ax-bar">
        <label class="ax-field">
            <span class="ax-field-label">Sağlayıcı</span>
            <select id="qs-provider">
                <?php foreach ($providers as $code => $p):
                    // Media-only providers (fal.ai, ElevenLabs) cannot serve chat and are not listed.
                    if (($p['type'] ?? 'llm') !== 'llm') continue;
                    if (agfo_get_api_key($code)): ?>
                        <option value="<?php echo esc_attr($code); ?>" <?php selected($selected_provider, $code); ?>><?php echo esc_html($p['label']); ?></option>
                <?php endif; endforeach; ?>
            </select>
        </label>

        <label class="ax-switch" title="Yalnızca akıl yürütme (reasoning) modellerini listeler">
            <input type="checkbox" id="qs-reasoning">
            <span class="ax-switch-track" aria-hidden="true"></span>
            <span class="ax-switch-text">Yalnız reasoning</span>
        </label>

        <span class="ax-sep" aria-hidden="true"></span>

        <div class="ax-field ax-fusion" id="ax-fusion-group">
            <span class="ax-field-label">Fusion</span>
            <select id="qs-fusion-mode" aria-label="OpenRouter Fusion modu">
                <option value="off">Kapalı</option>
                <option value="auto">Otomatik</option>
                <option value="force">Her zaman</option>
            </select>
            <select id="qs-fusion-profile" aria-label="Fusion profili">
                <?php if (function_exists('agfo_openrouter_get_fusion_profiles')): foreach (agfo_openrouter_get_fusion_profiles() as $fp_code => $fp): ?>
                    <option value="<?php echo esc_attr($fp_code); ?>"><?php echo esc_html($fp['label'] ?? $fp_code); ?></option>
                <?php endforeach; endif; ?>
            </select>
        </div>

    </div>

    <div class="ax-body">

        <aside class="ax-side" aria-label="Filtreler">
            <section class="ax-group">
                <div class="ax-group-head">
                    <span class="ax-group-title">Marka</span>
                    <button type="button" id="toggle-all-brands" class="ax-link">Tümünü seç</button>
                </div>
                <div class="ax-checks">
                    <?php foreach ($brands as $value => $label): ?>
                        <label class="ax-check">
                            <input type="checkbox" class="qs-brand" value="<?php echo esc_attr($value); ?>">
                            <span><?php echo esc_html($label); ?></span>
                        </label>
                    <?php endforeach; ?>
                </div>
            </section>

            <section class="ax-group">
                <div class="ax-group-head">
                    <span class="ax-group-title">Bağlam penceresi</span>
                    <button type="button" id="toggle-all-contexts" class="ax-link">Hepsini kaldır</button>
                </div>
                <div class="ax-checks">
                    <?php foreach ($contexts as $value => $ctx): ?>
                        <label class="ax-check">
                            <input type="checkbox" class="qs-context-filter" value="<?php echo esc_attr($value); ?>" checked>
                            <span class="ax-ctx-dot" style="background:<?php echo esc_attr($ctx[1]); ?>" aria-hidden="true"></span>
                            <span><?php echo esc_html($ctx[0]); ?></span>
                        </label>
                    <?php endforeach; ?>
                </div>
            </section>
        </aside>

        <div class="ax-work agfo-pworkspace">
            <div class="ax-tabs" role="tablist" aria-label="AI Kontrol Merkezi bölümleri">
                <button type="button" class="agfo-modal-tab is-active" id="agfo-tab-btn-models" role="tab" aria-selected="true" aria-controls="agfo-tab-models" data-agfo-tab="models">Modeller</button>
                <button type="button" class="agfo-modal-tab" id="agfo-tab-btn-translate" role="tab" aria-selected="false" aria-controls="agfo-tab-translate" data-agfo-tab="translate">Çeviri</button>
                <button type="button" class="agfo-modal-tab" id="agfo-tab-btn-image" role="tab" aria-selected="false" aria-controls="agfo-tab-image" data-agfo-tab="image">Görsel üretimi</button>
                <button type="button" class="agfo-modal-tab" id="agfo-tab-btn-speed" role="tab" aria-selected="false" aria-controls="agfo-tab-speed" data-agfo-tab="speed">Hız ve uyum</button>
                <button type="button" class="agfo-modal-tab" id="agfo-tab-btn-benchmark" role="tab" aria-selected="false" aria-controls="agfo-tab-benchmark" data-agfo-tab="benchmark">Benchmark</button>
                <button type="button" class="agfo-modal-tab" id="agfo-tab-btn-saved" role="tab" aria-selected="false" aria-controls="agfo-tab-saved" data-agfo-tab="saved">Kayıtlı modeller</button>
                <button type="button" class="agfo-modal-tab" id="agfo-tab-btn-settings" role="tab" aria-selected="false" aria-controls="agfo-tab-settings" data-agfo-tab="settings">Ayarlar ve koruma</button>
            </div>

            <div class="ax-panels">
                <section class="agfo-tab-panel" id="agfo-tab-models" role="tabpanel" aria-labelledby="agfo-tab-btn-models" data-agfo-panel="models">
                    <div class="ax-list-tools">
                        <div class="ax-search">
                            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/></svg>
                            <input type="text" id="qs-model-search" placeholder="Model ara" autocomplete="off" aria-label="Model ara">
                        </div>
                        <label class="ax-field ax-sort">
                            <span class="ax-field-label">Sırala</span>
                            <select id="qs-model-sort" aria-label="Model sıralaması">
                                <option value="newest">En yeni</option>
                                <option value="score">Puan</option>
                                <option value="price">Fiyat (ucuzdan)</option>
                                <option value="name">Ad</option>
                            </select>
                        </label>
                        <span class="ax-count"><strong id="model-count">0</strong> model</span>
                        <label class="ax-check" title="Erişimi olmayan veya chat yapamayan modelleri gizler">
                            <input type="checkbox" id="qs-hide-unusable" checked>
                            <span>Kullanılamayanları gizle</span>
                        </label>
                        <div class="ax-bar-actions">
                            <a href="#" class="ax-btn agfo-download-models" title="Model listesini, yayın tarihlerini ve fiyatları sağlayıcıdan indir" data-provider="<?php echo esc_attr($selected_provider); ?>">
                                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9M13.5 2.5v3h-3"/></svg>
                                <span class="ax-btn-text">Güncelle</span>
                            </a>
                            <button type="button" id="agfo-probe-model-btn" class="ax-btn" title="Seçili modelin chat ve temperature uyumunu canlı test et">
                                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2h4M7 2v4.2L3.3 12.6A1 1 0 0 0 4.2 14h7.6a1 1 0 0 0 .9-1.4L9 6.2V2"/></svg>
                                <span class="ax-btn-text">Test et</span>
                            </button>
                        </div>
                    </div>

                    <div class="ax-cols" aria-hidden="true">
                        <span></span>
                        <span>Model</span>
                        <span class="ax-col-ctx">Bağlam</span>
                        <span class="ax-col-price is-num">$/1M girdi · çıktı</span>
                        <span class="ax-col-speed">Hız</span>
                        <span class="ax-col-score is-num">Puan</span>
                        <span>Durum</span>
                    </div>

                    <ul id="qs-model-list" role="listbox" tabindex="0" aria-label="Modeller">
                        <li class="ax-empty">Yükleniyor</li>
                    </ul>

                    <select id="qs-model" size="2" aria-hidden="true" tabindex="-1">
                        <option>Yükleniyor...</option>
                    </select>
                </section>

                <section class="agfo-tab-panel" id="agfo-tab-translate" role="tabpanel" aria-labelledby="agfo-tab-btn-translate" data-agfo-panel="translate" hidden>
                    <div class="agfo-tab-intro">
                        <div>
                            <h4>Çeviri için en iyi modeller</h4>
                            <p>Anahtarı tanımlı tüm sağlayıcılarda, kalite eşiğini geçen chat modelleri 1.000 kelimelik çevirinin tahmini maliyetine göre sıralanır.</p>
                        </div>
                        <div class="ax-current" id="ax-tr-current">Çeviri modeli: varsayılan chat modeli</div>
                    </div>
                    <div class="ax-board-tools">
                        <div class="ax-seg" role="radiogroup" aria-label="Kalite eşiği">
                            <span class="ax-field-label">En düşük kalite</span>
                            <label><input type="radio" name="ax-tr-min" value="80"><span>80</span></label>
                            <label><input type="radio" name="ax-tr-min" value="85" checked><span>85</span></label>
                            <label><input type="radio" name="ax-tr-min" value="90"><span>90</span></label>
                        </div>
                        <label class="ax-field">
                            <span class="ax-field-label">Kapsam</span>
                            <select id="ax-tr-scope">
                                <option value="all">Tüm sağlayıcılar</option>
                                <option value="selected">Yalnız seçili sağlayıcı</option>
                            </select>
                        </label>
                    </div>
                    <div class="ax-picks" id="ax-tr-picks"></div>
                    <div id="ax-tr-table" class="ax-board-wrap"><div class="ax-guard-empty">Yükleniyor</div></div>
                    <p class="agfo-tab-note" id="ax-tr-note"></p>
                </section>

                <section class="agfo-tab-panel" id="agfo-tab-image" role="tabpanel" aria-labelledby="agfo-tab-btn-image" data-agfo-panel="image" hidden>
                    <div class="agfo-tab-intro">
                        <div>
                            <h4>Görsel üretimi modelleri</h4>
                            <p>Görsel Stüdyosu'nun kullanabileceği modeller: önce anahtarı olanlar, sonra kalite, sonra görsel başına fiyat.</p>
                        </div>
                        <div class="ax-current" id="ax-img-current">Varsayılan: -</div>
                    </div>
                    <div class="ax-picks" id="ax-img-picks"></div>
                    <div id="ax-img-table" class="ax-board-wrap"><div class="ax-guard-empty">Yükleniyor</div></div>
                    <p class="agfo-tab-note">Kalite notu AGFO'nun editoryal değerlendirmesidir (A: güncel amiral model, B: sağlam, C: eski nesil) ve <code>agfo_ai_image_model_note</code> filtresiyle değiştirilebilir. Görsel başına fiyatı sağlayıcı bildirmiyorsa satırdaki kutuya kendi tarifenizi yazın; Maliyet sayfasındaki tarifelerle aynı yere kaydedilir ve sıralamaya hemen girer.</p>
                </section>

                <section class="agfo-tab-panel" id="agfo-tab-speed" role="tabpanel" aria-labelledby="agfo-tab-btn-speed" data-agfo-panel="speed" hidden>
                    <div class="agfo-tab-intro">
                        <div>
                            <h4>Hız ve uyum dağılımı</h4>
                            <p>Seçili sağlayıcının model havuzu, ölçülen hız ve chat uyumuna göre.</p>
                        </div>
                    </div>
                    <div class="agfo-tab-stat-grid">
                        <div class="agfo-tab-stat"><div id="speed-ultra" class="agfo-sn">0</div><div class="agfo-sl">Çok hızlı</div><div class="ax-stat-bar"><i data-bar="speed-ultra" style="background:#17845a"></i></div></div>
                        <div class="agfo-tab-stat"><div id="speed-fast" class="agfo-sn">0</div><div class="agfo-sl">Dengeli</div><div class="ax-stat-bar"><i data-bar="speed-fast" style="background:#2e4bd8"></i></div></div>
                        <div class="agfo-tab-stat"><div id="speed-blacklist" class="agfo-sn">0</div><div class="agfo-sl">Kullanılamaz</div><div class="ax-stat-bar"><i data-bar="speed-blacklist" style="background:#b42318"></i></div></div>
                        <div class="agfo-tab-stat"><div id="speed-total" class="agfo-sn">0</div><div class="agfo-sl">Toplam</div><div class="ax-stat-bar"><i data-bar="speed-total" style="background:#7c8494;width:100%"></i></div></div>
                    </div>
                    <p class="agfo-tab-note">Hız, Model Intelligence ölçümü (<code>speed_score</code>) varsa ondan; yoksa model adındaki mini, flash, turbo gibi işaretlerden çıkarılır. “Kullanılamaz”, sağlayıcının erişim vermediği veya chat yapamayan modellerdir. Responses köprüsüyle çalışan modeller bu sayıya girmez.</p>
                </section>

                <section class="agfo-tab-panel" id="agfo-tab-benchmark" role="tabpanel" aria-labelledby="agfo-tab-btn-benchmark" data-agfo-panel="benchmark" hidden>
                    <div class="agfo-tab-intro">
                        <div>
                            <h4>Benchmark</h4>
                            <p>Seçili modelin birleşik puanı ve varsa kaynak kırılımı.</p>
                        </div>
                    </div>
                    <div class="agfo-benchmark-shell">
                        <div id="benchmark-model-name" class="agfo-benchmark-model">Model seçilmedi</div>
                        <div id="model-score-display" style="display:none;"><div id="score-content"></div></div>
                        <div id="model-score-placeholder">Benchmark için Modeller sekmesinden bir model seçin.</div>
                    </div>
                </section>

                <section class="agfo-tab-panel" id="agfo-tab-saved" role="tabpanel" aria-labelledby="agfo-tab-btn-saved" data-agfo-panel="saved" hidden>
                    <div class="agfo-tab-intro">
                        <div>
                            <h4>Kayıtlı modeller</h4>
                            <p>Bu sağlayıcı için hızlı geçiş havuzuna alınmış modeller.</p>
                        </div>
                    </div>
                    <div class="agfo-saved-shell">
                        <div class="agfo-saved-tools">
                            <input type="search" id="qs-saved-model-search" placeholder="Kayıtlı modellerde ara" aria-label="Kayıtlı modellerde ara">
                            <button type="button" id="agfo-copy-model-list" class="agfo-mini-action">Listeyi kopyala</button>
                        </div>
                        <div id="json-model-count" class="agfo-saved-summary">Toplam: <strong>0</strong></div>
                        <div id="json-model-preview" class="agfo-code-preview"></div>
                    </div>
                </section>

                <section class="agfo-tab-panel" id="agfo-tab-settings" role="tabpanel" aria-labelledby="agfo-tab-btn-settings" data-agfo-panel="settings" hidden>
                    <div class="agfo-tab-intro">
                        <div>
                            <h4>Ayarlar ve koruma</h4>
                            <p>Kaydedilmiş durum ile bu pencerede hazırladığınız seçim.</p>
                        </div>
                        <span id="agfo-unsaved-badge">Kaydedilmemiş değişiklik</span>
                    </div>
                    <div class="agfo-settings-shell">
                        <div class="agfo-settings-grid">
                            <div class="agfo-settings-card">
                                <h5>Kaydedilmiş</h5>
                                <div class="agfo-cfg-row"><span>Sağlayıcı</span><span id="cfg-provider">-</span></div>
                                <div class="agfo-cfg-row"><span>Model</span><span id="cfg-model">-</span></div>
                                <div class="agfo-cfg-row"><span>Reasoning</span><span id="cfg-reasoning">Kapalı</span></div>
                                <div class="agfo-cfg-row"><span>Fusion</span><span id="cfg-fusion">Kapalı</span></div>
                            </div>
                            <div class="agfo-settings-card">
                                <h5>Bu pencerede seçili</h5>
                                <div class="agfo-cfg-row"><span>Sağlayıcı</span><span id="draft-provider">-</span></div>
                                <div class="agfo-cfg-row"><span>Model</span><span id="draft-model">-</span></div>
                                <div class="agfo-cfg-row"><span>Reasoning</span><span id="draft-reasoning">Kapalı</span></div>
                                <div class="agfo-cfg-row"><span>Fusion</span><span id="draft-fusion">Kapalı</span></div>
                            </div>
                        </div>
                    </div>

                    <div class="ax-guard">
                        <div class="ax-guard-head">
                            <div>
                                <h5>İstek koruması</h5>
                                <p>Sağlayıcının reddettiği parametreler ve modeller burada öğrenilir; sonraki istekler gönderilmeden önce düzeltilir. Desteklenmeyen temperature her zaman otomatik kaldırılır.</p>
                            </div>
                            <button type="button" id="ax-guard-reset" class="ax-btn ax-btn-quiet ax-btn-danger">Öğrenilenleri sıfırla</button>
                        </div>
                        <label class="ax-check" style="margin:0 0 10px">
                            <input type="checkbox" id="ax-guard-fallback" checked>
                            <span>Erişilemeyen model istenirse aynı sağlayıcının çalışan bir modeline yönlendir</span>
                        </label>
                        <div id="ax-guard-rules"><div class="ax-guard-empty">Henüz öğrenilmiş bir kural yok.</div></div>
                    </div>
                </section>
            </div>
        </div>
    </div>

    <footer class="ax-foot">
        <div class="ax-foot-sel">
            <span class="ax-foot-label">Seçili model</span>
            <div id="selected-model-bar" style="display:none;">
                <span id="selected-model-name">-</span>
                <span id="ax-selected-badges" class="ax-badges"></span>
            </div>
        </div>
        <div class="ax-foot-actions">
            <span id="ax-dirty" class="ax-dirty">Kaydedilmemiş değişiklik</span>
            <span class="ax-version">AGFO AI Manager v<?php echo esc_html($agfo_version); ?></span>
            <button type="button" class="ax-btn ax-btn-quiet" onclick="agfoCloseSwitcher()">Kapat</button>
            <button type="button" id="qs-save-btn" class="ax-btn ax-btn-primary">Kaydet ve uygula</button>
        </div>
    </footer>

    <div id="ax-toast" class="ax-toast" role="status" aria-live="polite" hidden></div>
</div>

<script>
if (typeof window.agfoOpenSwitcher === 'undefined') {
    window.agfoOpenSwitcher = function () {
        document.getElementById('agfo-switcher-overlay').style.display = 'block';
        document.getElementById('agfo-switcher-modal').classList.add('agfo-open');
        if (window.AGFO) window.AGFO.loadData();
        return false;
    };
}
if (typeof window.agfoCloseSwitcher === 'undefined') {
    window.agfoCloseSwitcher = function () {
        document.getElementById('agfo-switcher-overlay').style.display = 'none';
        document.getElementById('agfo-switcher-modal').classList.remove('agfo-open');
        return false;
    };
}
</script>
