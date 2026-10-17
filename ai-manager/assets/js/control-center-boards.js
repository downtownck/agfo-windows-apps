/**
 * AGFO AI Manager – control-center-boards.js v17.1.0
 * Translation and image-generation boards of AI Kontrol Merkezi.
 * Depends on script.js (window.AGFO for escaping, toasts and price formatting).
 */
(function ($) {
    'use strict';

    var A = function () { return window.AGFO; };
    var esc = function (v) { return A().escHtml(v === null || v === undefined ? '' : v); };

    function money(v, digits) {
        if (v === null || v === undefined || v === '' || isNaN(Number(v))) return '—';
        var n = Number(v);
        if (n === 0) return '$0';
        if (digits !== undefined) return '$' + n.toFixed(digits);
        if (n < 0.01) return '$' + n.toFixed(4);
        if (n < 1) return '$' + n.toFixed(3);
        return '$' + n.toFixed(2);
    }

    function post(action, data) {
        return $.post(agfoConfig.ajaxurl, $.extend({ action: action, nonce: agfoConfig.nonce }, data || {}));
    }

    window.AGFO_Boards = {
        trMin: 85,
        trScope: 'all',
        trLoading: false,
        imgLoading: false,

        /* ── Translation ───────────────────────────────────── */

        loadTranslation: function () {
            var self = this;
            if (typeof agfoConfig === 'undefined' || self.trLoading) return;
            self.trLoading = true;
            $('#ax-tr-table').html('<div class="ax-guard-empty">Modeller karşılaştırılıyor</div>');
            post('agfo_aim_board_translation', { min_quality: self.trMin, scope: self.trScope })
                .done(function (res) {
                    if (!res || !res.success) {
                        $('#ax-tr-table').html('<div class="ax-guard-empty">Liste alınamadı.</div>');
                        return;
                    }
                    self.renderTranslation(res.data || {});
                })
                .fail(function () { $('#ax-tr-table').html('<div class="ax-guard-empty">Sunucuya ulaşılamadı.</div>'); })
                .always(function () { self.trLoading = false; });
        },

        renderTranslation: function (d) {
            var self = this;
            var cur = d.current || {};
            $('#ax-tr-current').html(cur.model
                ? 'Çeviri modeli: <strong>' + esc(cur.model) + '</strong> <span class="ax-muted-txt">' + esc(cur.provider) + '</span>'
                : 'Çeviri modeli: varsayılan chat modeli');

            var picks = d.picks || {};
            var tiles = [
                ['value', 'En iyi değer', 'Kalite eşiğini geçenler içinde dolar başına en çok kalite'],
                ['quality', 'En kaliteli', 'En yüksek puan; eşitlikte daha ucuz olan'],
                ['cheapest', 'En ucuz', 'Kalite eşiğini geçen en düşük maliyet']
            ];
            $('#ax-tr-picks').html(tiles.map(function (t) {
                var r = picks[t[0]];
                if (!r) return '<div class="ax-pick is-empty"><span class="ax-pick-label">' + esc(t[1]) + '</span><span class="ax-pick-none">Eşiği geçen fiyatlı model yok</span></div>';
                var isCur = cur.provider === r.provider && cur.model === r.id;
                return '<div class="ax-pick" title="' + esc(t[2]) + '">' +
                    '<span class="ax-pick-label">' + esc(t[1]) + '</span>' +
                    '<strong class="ax-pick-model">' + esc(r.id) + '</strong>' +
                    '<span class="ax-pick-meta">' + esc(r.provider_label) + ' · kalite ' + esc(r.quality) + ' · ' + money(r.cost_1k_words) + ' / 1.000 kelime</span>' +
                    (isCur ? '<span class="ax-badge is-ok">Kullanılıyor</span>'
                        : '<button type="button" class="ax-btn ax-tr-use" data-provider="' + esc(r.provider) + '" data-model="' + esc(r.id) + '">Çeviri için kullan</button>') +
                    '</div>';
            }).join(''));

            var rows = d.rows || [];
            if (!rows.length) {
                $('#ax-tr-table').html('<div class="ax-guard-empty">Çeviriye uygun chat modeli bulunamadı. Sağlayıcı anahtarlarını ve model listelerini kontrol edin.</div>');
            } else {
                var maxValue = 0;
                rows.forEach(function (r) { if (r.eligible && r.value > maxValue) maxValue = r.value; });
                var body = rows.map(function (r) {
                    var isCur = cur.provider === r.provider && cur.model === r.id;
                    var bar = (r.value && maxValue) ? Math.max(4, Math.round(r.value / maxValue * 100)) : 0;
                    var flags = '';
                    if (r.is_new) flags += '<span class="ax-badge is-new">Yeni</span>';
                    if (r.route === 'responses_bridge') flags += '<span class="ax-badge is-bridge" title="Responses köprüsüyle çalışır">Responses</span>';
                    if (r.reasoning) flags += '<span class="ax-badge is-auto" title="Gizli düşünme tokenları maliyete eklendi">Reasoning</span>';
                    return '<tr class="' + (r.eligible ? '' : 'is-muted') + (isCur ? ' is-current' : '') + '">' +
                        '<td><div class="ax-cell-model">' + esc(r.id) + flags + '</div><div class="ax-cell-sub">' + esc(r.provider_label) + '</div></td>' +
                        '<td class="is-num" title="' + esc(r.quality_source === 'benchmark' ? 'Benchmark: ' + r.quality_key : 'Benchmark yok; AGFO puanından tahmin') + '"><span class="ax-tier">' + esc(r.tier) + ' <b>' + esc(r.quality) + '</b>' + (r.quality_source === 'benchmark' ? '' : '<sup class="ax-est">≈</sup>') + '</span></td>' +
                        '<td class="is-num" title="' + esc(r.price_source || 'Fiyat bilinmiyor') + '">' + (r.in !== null ? money(r.in, 2) + ' · ' + money(r.out, 2) : '<span class="ax-muted">—</span>') + '</td>' +
                        '<td class="is-num"><strong>' + money(r.cost_1k_words) + '</strong></td>' +
                        '<td><div class="ax-meter" title="' + esc(r.value !== null ? 'Değer: ' + r.value : 'Fiyat yok') + '"><i style="width:' + bar + '%"></i></div></td>' +
                        '<td class="is-act">' + (isCur ? '<span class="ax-badge is-ok">Kullanılıyor</span>'
                            : '<button type="button" class="ax-link ax-tr-use" data-provider="' + esc(r.provider) + '" data-model="' + esc(r.id) + '">Kullan</button>') + '</td>' +
                        '</tr>';
                }).join('');
                $('#ax-tr-table').html('<table class="ax-board"><thead><tr><th>Model</th><th class="is-num">Kalite</th><th class="is-num">$/1M girdi · çıktı</th><th class="is-num">≈ 1.000 kelime</th><th>Değer</th><th></th></tr></thead><tbody>' + body + '</tbody></table>');
            }

            var a = d.assumptions || {};
            $('#ax-tr-note').text(
                (d.eligible || 0) + ' model eşiği geçti, ' + (d.total || 0) + ' model incelendi. ' +
                'Maliyet, 1.000 kelimelik bir metin için yaklaşık ' + (a.input_tokens || 1700) + ' girdi ve ' + (a.output_tokens || 1900) + ' çıktı tokenı varsayar; reasoning modellerinde çıktı ×' + (a.reasoning_overhead || 1.4) + ' alınır. ' +
                'Kalite, eklentinin benchmark tablosundan (LMSYS, OpenLLM, Artificial Analysis) gelir; çeviriye özel bir ölçüm değildir. ≈ işaretli modellerin benchmark kaydı yok, puanı tahminidir. Değer = 60 üzerindeki kalite puanı ÷ maliyet. ' +
                'Fiyatı görünmeyen modeller için Modeller sekmesinde “Güncelle”ye basın; OpenRouter fiyatları oradan gelir. ' +
                'Seçilen model eklentilere agfo_get_translation_config() ile verilir.'
            );
        },

        useTranslation: function ($btn) {
            var self = this;
            var provider = String($btn.data('provider') || ''), model = String($btn.data('model') || '');
            $btn.prop('disabled', true);
            post('agfo_aim_set_translation_model', { provider: provider, model: model })
                .done(function (res) {
                    if (res && res.success) {
                        A().toast('Çeviri modeli: ' + model, 'ok');
                        self.loadTranslation();
                    } else {
                        A().toast((res && res.data && res.data.message) || 'Çeviri modeli kaydedilemedi.', 'error');
                        $btn.prop('disabled', false);
                    }
                })
                .fail(function () { A().toast('Sunucuya ulaşılamadı.', 'error'); $btn.prop('disabled', false); });
        },

        /* ── Image ─────────────────────────────────────────── */

        loadImage: function () {
            var self = this;
            if (typeof agfoConfig === 'undefined' || self.imgLoading) return;
            self.imgLoading = true;
            $('#ax-img-table').html('<div class="ax-guard-empty">Görsel modelleri yükleniyor</div>');
            post('agfo_aim_board_image', {})
                .done(function (res) {
                    if (!res || !res.success) {
                        $('#ax-img-table').html('<div class="ax-guard-empty">Liste alınamadı.</div>');
                        return;
                    }
                    self.renderImage(res.data || {});
                })
                .fail(function () { $('#ax-img-table').html('<div class="ax-guard-empty">Sunucuya ulaşılamadı.</div>'); })
                .always(function () { self.imgLoading = false; });
        },

        renderImage: function (d) {
            var def = d.default || {};
            $('#ax-img-current').html(def.model
                ? 'Varsayılan: <strong>' + esc(def.model) + '</strong> <span class="ax-muted-txt">' + esc(def.provider) + '</span>'
                : 'Varsayılan: seçilmedi');

            var tierName = { A: 'Amiral', B: 'Sağlam', C: 'Eski nesil' };
            var picks = d.picks || {};
            var tiles = [
                ['recommended', 'Önerilen', 'Anahtarı olan en yüksek kaliteli, eşitlikte en ucuz model'],
                ['value', 'En iyi değer', 'A kalitesinde fiyatı bilinen en ucuz model'],
                ['cheapest', 'En ucuz', 'Fiyatı bilinen en düşük görsel başı maliyet']
            ];
            $('#ax-img-picks').html(tiles.map(function (t) {
                var r = picks[t[0]];
                if (!r) return '<div class="ax-pick is-empty"><span class="ax-pick-label">' + esc(t[1]) + '</span><span class="ax-pick-none">' + (t[0] === 'recommended' ? 'Anahtarı olan görsel sağlayıcısı yok' : 'Görsel başı fiyat girilmemiş') + '</span></div>';
                return '<div class="ax-pick" title="' + esc(t[2]) + '">' +
                    '<span class="ax-pick-label">' + esc(t[1]) + '</span>' +
                    '<strong class="ax-pick-model">' + esc(r.id) + '</strong>' +
                    '<span class="ax-pick-meta">' + esc(r.provider_label) + ' · ' + esc(tierName[r.tier] || r.tier) + ' · ' + (r.price !== null ? money(r.price) + ' / görsel' : 'fiyat yok') + '</span>' +
                    (r.is_default ? '<span class="ax-badge is-ok">Varsayılan</span>'
                        : '<button type="button" class="ax-btn ax-img-use" data-provider="' + esc(r.provider) + '" data-model="' + esc(r.id) + '">Varsayılan yap</button>') +
                    '</div>';
            }).join(''));

            var rows = d.rows || [];
            var body = rows.map(function (r) {
                var chips = (r.strengths || []).map(function (s) { return '<span class="ax-chip">' + esc(s) + '</span>'; }).join('');
                var action = !r.has_key ? '<span class="ax-badge is-auto">Anahtar yok</span>'
                    : (r.is_default ? '<span class="ax-badge is-ok">Varsayılan</span>'
                        : '<button type="button" class="ax-link ax-img-use" data-provider="' + esc(r.provider) + '" data-model="' + esc(r.id) + '">Varsayılan yap</button>');
                return '<tr class="' + (r.has_key ? '' : 'is-muted') + (r.is_default ? ' is-current' : '') + '">' +
                    '<td><div class="ax-cell-model">' + esc(r.id) + '</div><div class="ax-cell-sub">' + esc(r.provider_label) + (r.label && r.label !== r.id ? ' · ' + esc(r.label) : '') + '</div></td>' +
                    '<td><span class="ax-grade ax-grade-' + esc(r.tier) + '">' + esc(r.tier) + '</span> ' + esc(tierName[r.tier] || '') + '</td>' +
                    '<td><div class="ax-chips">' + (chips || '<span class="ax-muted">—</span>') + '</div></td>' +
                    '<td class="is-num"><label class="ax-price"><span>$</span><input type="text" inputmode="decimal" class="ax-img-price" value="' + (r.price !== null ? esc(r.price) : '') + '" placeholder="—" data-provider="' + esc(r.provider) + '" data-model="' + esc(r.id) + '" aria-label="' + esc(r.id) + ' görsel başı fiyat" title="' + esc(r.price_source ? 'Kaynak: ' + r.price_source : 'Görsel başı fiyatı yazın') + '"></label></td>' +
                    '<td class="is-num">' + esc(Number(r.prompt_budget || 0).toLocaleString('tr-TR')) + '</td>' +
                    '<td class="is-act">' + action + '</td>' +
                    '</tr>';
            }).join('');
            $('#ax-img-table').html(rows.length
                ? '<table class="ax-board"><thead><tr><th>Model</th><th>Kalite</th><th>Güçlü yanlar</th><th class="is-num">$ / görsel</th><th class="is-num">Prompt sınırı</th><th></th></tr></thead><tbody>' + body + '</tbody></table>'
                : '<div class="ax-guard-empty">Görsel modeli bulunamadı.</div>');
        },

        useImage: function ($btn) {
            var self = this;
            var provider = String($btn.data('provider') || ''), model = String($btn.data('model') || '');
            $btn.prop('disabled', true);
            post('agfo_aim_set_image_model', { provider: provider, model: model })
                .done(function (res) {
                    if (res && res.success) {
                        A().toast('Görsel Stüdyosu varsayılanı: ' + model, 'ok');
                        self.loadImage();
                    } else {
                        A().toast((res && res.data && res.data.message) || 'Varsayılan kaydedilemedi.', 'error');
                        $btn.prop('disabled', false);
                    }
                })
                .fail(function () { A().toast('Sunucuya ulaşılamadı.', 'error'); $btn.prop('disabled', false); });
        },

        saveImagePrice: function ($input) {
            var self = this;
            var raw = String($input.val() || '').replace(',', '.').trim();
            if (raw !== '' && (isNaN(Number(raw)) || Number(raw) < 0)) {
                A().toast('Fiyatı sayı olarak yazın, örn. 0.04', 'error');
                return;
            }
            post('agfo_aim_set_image_price', { provider: $input.data('provider'), model: $input.data('model'), price: raw === '' ? 0 : raw })
                .done(function (res) {
                    if (res && res.success) {
                        A().toast(raw === '' ? 'Fiyat kaldırıldı.' : 'Fiyat kaydedildi: $' + raw + ' / görsel', 'ok');
                        self.loadImage();
                    } else {
                        A().toast((res && res.data && res.data.message) || 'Fiyat kaydedilemedi.', 'error');
                    }
                });
        }
    };

    $(document).on('change', 'input[name="ax-tr-min"]', function () {
        window.AGFO_Boards.trMin = parseInt($(this).val(), 10) || 85;
        window.AGFO_Boards.loadTranslation();
    });
    $(document).on('change', '#ax-tr-scope', function () {
        window.AGFO_Boards.trScope = $(this).val() || 'all';
        window.AGFO_Boards.loadTranslation();
    });
    $(document).on('click', '.ax-tr-use', function () { window.AGFO_Boards.useTranslation($(this)); });
    $(document).on('click', '.ax-img-use', function () { window.AGFO_Boards.useImage($(this)); });
    $(document).on('change', '.ax-img-price', function () { window.AGFO_Boards.saveImagePrice($(this)); });
    $(document).on('keydown', '.ax-img-price', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); $(this).trigger('change'); }
    });
}(jQuery));
