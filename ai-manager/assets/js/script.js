/**
 * AGFO AI Manager – script.js v17.0.0
 * 17.0.0: AI Kontrol Merkezi redesign — #qs-model-list table, keyboard navigation,
 * status pill, inline toasts instead of alert(), request-guard panel.
 * Context-aware model rendering + ranking + blacklist support
 * Fixed context normalization: 16K / 200K+ ayrımı
 */
(function ($) {
    'use strict';

    window.AGFO = {

        searchTimer: null,
        currentModels: [],
        savedState: null,
        benchmarkRequestSeq: 0,
        lastBenchmarkKey: '',

        init: function () {
            this.bindEvents();
            console.log('[AGFO] script.js hazır');
        },

        bindEvents: function () {
            var self = window.AGFO;

            $(document).on('change', '#qs-provider', function () {
                self.loadModels($(this).val());
                self.updateFusionState();
                self.syncDraftSummary();
            });

            // NEW 17.0.0: model table interactions.
            $(document).on('click', '#qs-model-list .ax-row', function () {
                self.selectModel(String($(this).data('model') || ''), $(this));
            });
            $(document).on('keydown', '#qs-model-list', function (e) {
                self.listKeydown(e);
            });
            $(document).on('change', '#qs-hide-unusable', function () {
                self.applyAllFilters();
            });
            // NEW 17.1.0: newest-first and other sort modes.
            $(document).on('change', '#qs-model-sort', function () {
                self.sortMode = $(this).val() || 'newest';
                try { window.sessionStorage.setItem('agfoQuickSwitchSort', self.sortMode); } catch (e) {}
                self.renderModels(self.currentModels, $('#qs-model').val() || '');
            });
            $(document).on('click', '#ax-guard-reset', function () {
                self.resetGuardRules($(this));
            });
            $(document).on('change', '#ax-guard-fallback', function () {
                self.saveGuardFallback($(this).is(':checked'));
            });

            $(document).on('change', '.qs-context-filter', function () {
                self.applyAllFilters();
            });

            $(document).on('change', '.qs-brand', function () {
                self.applyAllFilters();
            });

            $(document).on('input', '#qs-model-search', function () {
                clearTimeout(self.searchTimer);

                self.searchTimer = setTimeout(function () {
                    self.applyAllFilters();
                }, 180);
            });

            $(document).on('change', '#qs-reasoning', function () {
                self.applyAllFilters();
                self.syncDraftSummary();
            });

            $(document).on('change', '#qs-fusion-mode, #qs-fusion-profile', function () {
                self.syncDraftSummary();
            });

            $(document).on('change', '#qs-model', function () {
                var val = $(this).val() || '';

                if (val) {
                    $('#selected-model-name').text(val);
                    $('#selected-model-bar').show();
                } else {
                    $('#selected-model-bar').hide();
                }

                self.syncSelection();
                self.syncDraftSummary();
                self.loadModelScore($('#qs-provider').val() || '', val);
            });

            $(document).on('click', '#qs-save-btn', function (e) {
                e.preventDefault();
                self.save();
            });

            $(document).on('click', '.agfo-download-models', function (e) {
                e.preventDefault();
                self.downloadModels($(this));
            });

            $(document).on('click', '#agfo-probe-model-btn', function (e) {
                e.preventDefault();
                self.probeSelectedModel($(this));
            });

            $(document).on('click', '#toggle-all-brands', function () {
                var $checks = $('.qs-brand');
                var allChecked = $checks.filter(':checked').length === $checks.length;

                $checks.prop('checked', !allChecked);
                $(this).text(allChecked ? 'Tümünü seç' : 'Tümünü kaldır');

                self.applyAllFilters();
            });

            $(document).on('click', '#toggle-all-contexts', function () {
                var $checks = $('.qs-context-filter');
                var allChecked = $checks.filter(':checked').length === $checks.length;

                $checks.prop('checked', !allChecked);
                $(this).text(allChecked ? 'Tümünü seç' : 'Hepsini kaldır');

                self.applyAllFilters();
            });

            $(document).on('keydown', function (e) {
                if (e.key === 'Escape') {
                    window.agfoCloseSwitcher();
                }
            });

            $(document).on('click', '#agfo-switcher-overlay', function () {
                window.agfoCloseSwitcher();
            });

            // CHANGED 16.17.0: Former right-column cards are first-class workspace tabs.
            $(document).on('click', '.agfo-modal-tab', function () {
                self.activateTab($(this).data('agfo-tab'));
            });

            $(document).on('keydown', '.agfo-modal-tab', function (e) {
                if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
                e.preventDefault();
                var $tabs = $('.agfo-modal-tab');
                var index = $tabs.index(this);
                var next = e.key === 'ArrowRight' ? index + 1 : index - 1;
                if (next < 0) next = $tabs.length - 1;
                if (next >= $tabs.length) next = 0;
                var $next = $tabs.eq(next);
                self.activateTab($next.data('agfo-tab'));
                $next.trigger('focus');
            });

            $(document).on('input', '#qs-saved-model-search', function () {
                self.filterSavedModels($(this).val());
            });

            $(document).on('click', '#agfo-copy-model-list', function () {
                self.copySavedModels($(this));
            });

            $(document).on('click', '.agfo-use-saved-model', function () {
                var model = String($(this).data('model') || '');
                if (!model) return;
                var exists = $('#qs-model option').filter(function () { return $(this).val() === model; }).length > 0;
                if (exists) {
                    $('#qs-model').val(model).trigger('change');
                    self.activateTab('models');
                }
            });
        },

        loadData: function () {
            var self = window.AGFO;

            if (typeof agfoConfig === 'undefined') {
                console.error('[AGFO] agfoConfig tanımlı değil.');
                self.setStatus('Yapılandırma yok', 'error');
                self.listMessage('Yapılandırma yüklenemedi', 'Sayfayı yenileyip tekrar deneyin.');
                return;
            }

            self.setStatus('Yükleniyor', 'busy');
            self.listMessage('Modeller yükleniyor', '');
            $('#model-count').text('…');

            $.post(agfoConfig.ajaxurl, {
                action: 'agfo_qs_get_data',
                nonce: agfoConfig.nonce // CHANGED 16.6.0: sunucu tarafinda nonce zorunlu oldu.
            })
            .done(function (res) {
                if (!res || !res.success) {
                    console.error('[AGFO] agfo_qs_get_data başarısız:', res);
                    self.setStatus('Veri alınamadı', 'error');
                    self.listMessage('Veri alınamadı', 'Oturumunuzun açık olduğundan emin olup pencereyi yeniden açın.');
                    return;
                }

                var d = res.data || {};
                var models = d.all_models || [];

                $('#qs-provider').val(d.provider || 'openai');
                $('#qs-reasoning').prop('checked', parseInt(d.reasoning || 0, 10) === 1);
                // CHANGED: Restore compact OpenRouter Fusion mode/profile controls.
                if (d.fusion) {
                    $('#qs-fusion-mode').val(d.fusion.mode || 'off');
                    $('#qs-fusion-profile').val(d.fusion.profile || 'balanced');
                }

                self.savedState = {
                    provider: d.provider || 'openai',
                    model: d.current_model || '',
                    reasoning: parseInt(d.reasoning || 0, 10) === 1 ? 1 : 0,
                    fusionMode: d.fusion && d.fusion.mode ? d.fusion.mode : 'off',
                    fusionProfile: d.fusion && d.fusion.profile ? d.fusion.profile : 'balanced',
                    fusionProfileLabel: d.fusion && d.fusion.profile_label ? d.fusion.profile_label : ''
                };

                self.renderModels(models, d.current_model || '');
                self.updateFusionState();
                self.renderSavedState();
                self.syncDraftSummary();

                if (d.current_model) {
                    self.loadModelScore(d.provider || 'openai', d.current_model);
                } else {
                    self.resetBenchmark('Benchmark için Modeller sekmesinden bir model seçin.');
                }

                self.setStatus('Hazır', 'ok');
            })
            .fail(function (xhr) {
                console.error('[AGFO] AJAX fail:', xhr.status, xhr.responseText);
                self.setStatus('Bağlantı hatası', 'error');
                self.listMessage('Sunucuya ulaşılamadı', 'Bağlantıyı kontrol edip pencereyi yeniden açın.');
            });
        },

        loadModels: function (provider) {
            var self = window.AGFO;

            if (typeof agfoConfig === 'undefined') return;

            self.listMessage('Modeller yükleniyor', '');
            self.setStatus('Yükleniyor', 'busy');
            $('#model-count').text('…');

            $.post(agfoConfig.ajaxurl, {
                action: 'agfo_qs_get_models_only',
                provider: provider,
                nonce: agfoConfig.nonce // CHANGED 16.6.0: sunucu tarafinda nonce zorunlu oldu.
            })
            .done(function (res) {
                if (!res || !res.success) {
                    self.listMessage('Model listesi alınamadı', 'Sağlayıcı anahtarını kontrol edin.');
                    self.setStatus('Liste alınamadı', 'error');
                    $('#model-count').text('0');
                    return;
                }

                self.setStatus('Hazır', 'ok');
                self.renderModels(res.data || [], '');
                self.resetBenchmark('Yeni sağlayıcı için benchmark görmek üzere bir model seçin.');
                self.syncDraftSummary();
            })
            .fail(function () {
                self.listMessage('Sunucuya ulaşılamadı', '');
                self.setStatus('Bağlantı hatası', 'error');
                $('#model-count').text('0');
            });
        },

        normalizeContext: function (ctx) {
            ctx = String(ctx || '32k').toLowerCase().trim();

            ctx = ctx.replace(/\+/g, '');
            ctx = ctx.replace(/\s/g, '');

            if (ctx === '1000000' || ctx === '1024k' || ctx === '1million' || ctx === '1m') return '1m';
            if (ctx === '200000' || ctx === '200k') return '200k';
            if (ctx === '100000' || ctx === '100k') return '100k';
            if (ctx === '64000' || ctx === '64k') return '64k';
            if (ctx === '32000' || ctx === '32k') return '32k';
            if (ctx === '16000' || ctx === '16k') return '16k';
            if (ctx === '8000' || ctx === '8k') return '8k';

            return '32k';
        },

        contextDot: function (ctx) {
            ctx = window.AGFO.normalizeContext(ctx);

            var map = {
                '8k':   '🟢',
                '16k':  '🔵',
                '32k':  '🟡',
                '64k':  '🟠',
                '100k': '🔴',
                '200k': '🟣',
                '1m':   '⚫'
            };

            return map[ctx] || '⚪';
        },

        // CHANGED 16.7.0: Dropdown etiketi icin islevsel bilgi yardimcilari.
        fmtUsd: function (v) {
            if (v === null || v === undefined || v === '' || isNaN(Number(v))) return '';
            var n = Math.round(Number(v) * 100) / 100;
            return '$' + n;
        },

        speedWord: function (s) {
            if (s === null || s === undefined || s === '' || isNaN(Number(s))) return '';
            s = Number(s);
            if (s >= 86) return 'hızlı';   // chat-test hiz rozeti esikleriyle ayni
            if (s >= 54) return 'orta';
            return 'yavaş';
        },

        renderModels: function (models, selected) {
            this.currentModels = Array.isArray(models) ? models.slice() : [];

            if (!models || !models.length) {
                $('#qs-model').html('');
                this.listMessage('Bu sağlayıcı için model yok', '“Güncelle” ile listeyi sağlayıcıdan indirin.');
                $('#model-count').text('0');
                this.updateSpeedSummary([]);
                this.renderSavedModels([]);
                $('#selected-model-bar').hide();
                return;
            }

            var html = '';
            models = this.sortModels(models);

            models.forEach(function (m) {
                var id = typeof m === 'string' ? m : (m.id || m.name || '');
                if (!id) return;

                var ctx   = window.AGFO.normalizeContext(typeof m === 'string' ? '32k' : (m.context || '32k'));
                var score = typeof m === 'string' ? '' : (m.rank_score || m.score || '');
                var tier  = typeof m === 'string' ? '' : (m.tier  || '');
                var price = typeof m === 'string' ? '' : (m.price_label || '');
                var fp    = typeof m === 'string' ? null : (m.fp !== undefined && m.fp !== null ? m.fp : null);
                var supportsChat = typeof m === 'string' ? true : (m.supports_chat !== false);
                var supportsTemp = typeof m === 'string' ? true : (m.supports_temperature !== false);
                var tempStatus   = typeof m === 'string' ? 'unknown' : (m.temperature_status || 'unknown');
                var probeStatus  = typeof m === 'string' ? 'not_tested' : (m.probe_status || 'not_tested');
                var docxAllowed  = typeof m === 'string' ? true : (m.docx_allowed !== false);
                var endpointType = typeof m === 'string' ? 'chat' : (m.endpoint_type || 'chat');
                var compatLevel  = typeof m === 'string' ? 'ok' : (m.compatibility_level || 'ok');
                var speedScore   = typeof m === 'string' ? '' : (m.speed_score !== undefined && m.speed_score !== null ? m.speed_score : '');

                var dot = window.AGFO.contextDot(ctx);
                var inP  = typeof m === 'string' ? null : (m.in_price  !== undefined ? m.in_price  : null);
                var outP = typeof m === 'string' ? null : (m.out_price !== undefined ? m.out_price : null);
                var spd  = speedScore === '' ? null : speedScore;
                // NEW 17.0.0: effective transport contract from the request guard.
                var route    = typeof m === 'string' ? 'chat' : (m.transport_route || (supportsChat ? 'chat' : 'not_chat'));
                var sampling = typeof m === 'string' ? 'allowed' : (m.sampling_policy || 'allowed');

                var info = [];
                info.push(ctx);

                var priceTxt = '';
                if (inP !== null && outP !== null)      priceTxt = window.AGFO.fmtUsd(inP) + '/' + window.AGFO.fmtUsd(outP);
                else if (inP !== null)                  priceTxt = window.AGFO.fmtUsd(inP);
                else if (price)                         priceTxt = price;
                if (priceTxt) info.push(priceTxt);

                var speedTxt = window.AGFO.speedWord(spd);
                if (speedTxt) info.push(speedTxt);

                if (tier || score !== '') info.push(tier + score + (probeStatus === 'completed' ? '✓' : ''));
                if (fp !== null && fp !== '') info.push('FP' + fp);

                if (!supportsChat) info.push('chat✗');
                if (tempStatus === 'unsupported' || supportsTemp === false) info.push('temp✗');
                if (supportsChat && !docxAllowed) info.push('docx✗');

                var sel = id === selected ? ' selected' : '';

                html += '<option value="' + window.AGFO.escAttr(id) + '"' + sel +
                    ' data-context="'       + window.AGFO.escAttr(ctx)   + '"' +
                    ' data-tier="'          + window.AGFO.escAttr(tier)   + '"' +
                    ' data-score="'         + window.AGFO.escAttr(score)  + '"' +
                    ' data-price="'         + window.AGFO.escAttr(price)  + '"' +
                    ' data-fp="'            + window.AGFO.escAttr(fp !== null ? fp : '') + '"' +
                    ' data-speed-score="'   + window.AGFO.escAttr(speedScore) + '"' +
                    ' data-endpoint-type="' + window.AGFO.escAttr(endpointType) + '"' +
                    ' data-supports-chat="' + window.AGFO.escAttr(supportsChat ? '1' : '0') + '"' +
                    ' data-supports-temp="' + window.AGFO.escAttr(supportsTemp ? '1' : '0') + '"' +
                    ' data-temp-status="'   + window.AGFO.escAttr(tempStatus) + '"' +
                    ' data-probe-status="'  + window.AGFO.escAttr(probeStatus) + '"' +
                    ' data-docx-allowed="'  + window.AGFO.escAttr(docxAllowed ? '1' : '0') + '"' +
                    ' data-compat-level="'  + window.AGFO.escAttr(compatLevel) + '"' +
                    ' data-route="'         + window.AGFO.escAttr(route) + '"' +
                    ' data-is-new="'        + (typeof m !== 'string' && m.is_new ? '1' : '0') + '"' +
                    ' data-released="'      + window.AGFO.escAttr(typeof m === 'string' ? 0 : (m.released || 0)) + '"' +
                    ' data-sampling="'      + window.AGFO.escAttr(sampling) + '"' +
                    ' data-in-price="'      + window.AGFO.escAttr(inP !== null ? inP : '') + '"' +
                    ' data-out-price="'     + window.AGFO.escAttr(outP !== null ? outP : '') + '"' +
                    ' data-model-id="'      + window.AGFO.escAttr(id)    + '">' +
                    dot + ' ' + window.AGFO.escHtml(id.replace('models/', '')) + ' (' + window.AGFO.escHtml(info.join(' · ')) + ')' +
                    '</option>';
            });

            $('#qs-model').html(html);
            this.renderModelRows();
            $('#model-count').text(models.length);
            this.updateSpeedSummary(models);
            this.renderSavedModels(models);

            if (selected) {
                $('#selected-model-name').text(selected);
                $('#selected-model-bar').show();
            } else {
                $('#selected-model-bar').hide();
            }

            this.applyAllFilters();
        },

        updateSpeedSummary: function (models) {
            var ultra = 0;
            var fast = 0;
            var incompatible = 0;

            (models || []).forEach(function (m) {
                var id = typeof m === 'string' ? m : (m.id || m.name || '');
                var lower = String(id).toLowerCase();
                var supportsChat = typeof m === 'string' ? true : (m.supports_chat !== false);
                var compatLevel = typeof m === 'string' ? 'ok' : String(m.compatibility_level || 'ok').toLowerCase();
                var speed = typeof m === 'string' ? null : (m.speed_score !== undefined && m.speed_score !== null ? Number(m.speed_score) : null);

                var route = typeof m === 'string' ? 'chat' : String(m.transport_route || '');
                if ((!supportsChat && route !== 'responses_bridge') || compatLevel === 'blocked') incompatible++;

                if (speed !== null && !isNaN(speed)) {
                    if (speed >= 86) ultra++;
                    else if (speed >= 54) fast++;
                } else if (/mini|instant|flash|turbo/.test(lower)) {
                    ultra++;
                } else if (/fast/.test(lower)) {
                    fast++;
                }
            });

            $('#speed-total').text((models || []).length);
            $('#speed-ultra').text(ultra);
            $('#speed-fast').text(fast);
            $('#speed-blacklist').text(incompatible);
            var total = Math.max(1, (models || []).length);
            $('[data-bar="speed-ultra"]').css('width', (ultra / total * 100) + '%');
            $('[data-bar="speed-fast"]').css('width', (fast / total * 100) + '%');
            $('[data-bar="speed-blacklist"]').css('width', (incompatible / total * 100) + '%');
        },

        renderSavedModels: function (models) {
            var items = [];
            (models || []).forEach(function (m) {
                var id = typeof m === 'string' ? m : (m.id || m.name || '');
                if (!id) return;
                items.push(
                    '<div class="agfo-saved-model-item" data-search="' + window.AGFO.escAttr(String(id).toLowerCase()) + '">' +
                        '<span>' + window.AGFO.escHtml(id) + '</span>' +
                        '<button type="button" class="agfo-use-saved-model" data-model="' + window.AGFO.escAttr(id) + '">Seç</button>' +
                    '</div>'
                );
            });

            $('#json-model-count').html('Toplam: <strong>' + items.length + '</strong>');
            $('#json-model-preview').html(items.length ? items.join('') : '<div class="ax-guard-empty">Kayıtlı model yok.</div>');
            this.filterSavedModels($('#qs-saved-model-search').val() || '');
        },

        filterSavedModels: function (query) {
            var q = String(query || '').toLowerCase().trim();
            var visible = 0;
            $('#json-model-preview .agfo-saved-model-item').each(function () {
                var hit = !q || String($(this).data('search') || '').indexOf(q) !== -1;
                $(this).toggleClass('is-hidden', !hit);
                if (hit) visible++;
            });
            if (q) $('#json-model-count').html('Eşleşen: <strong>' + visible + '</strong> / ' + this.currentModels.length);
            else $('#json-model-count').html('Toplam: <strong>' + this.currentModels.length + '</strong>');
        },

        copySavedModels: function ($btn) {
            var text = this.currentModels.map(function (m) {
                return typeof m === 'string' ? m : (m.id || m.name || '');
            }).filter(Boolean).join('\n');
            if (!text) return;

            var done = function () {
                var old = $btn.text();
                $btn.text('Kopyalandı');
                setTimeout(function () { $btn.text(old); }, 1200);
            };

            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(done).catch(function () {
                    window.AGFO.copyTextFallback(text); done();
                });
            } else {
                this.copyTextFallback(text); done();
            }
        },

        copyTextFallback: function (text) {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.setAttribute('readonly', 'readonly');
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand('copy'); } catch (e) {}
            document.body.removeChild(ta);
        },

        applyAllFilters: function () {
            var checkedContexts = [];
            var checkedBrands = [];
            var q = String($('#qs-model-search').val() || '').toLowerCase();
            var reasoningOnly = $('#qs-reasoning').is(':checked');
            var hideUnusable = $('#qs-hide-unusable').is(':checked');
            var $rows = $('#qs-model-list .ax-row');
            var rowByIndex = {};
            $rows.each(function () { rowByIndex[this.getAttribute('data-index')] = this; });

            $('.qs-context-filter:checked').each(function () {
                checkedContexts.push(window.AGFO.normalizeContext($(this).val()));
            });

            $('.qs-brand:checked').each(function () {
                checkedBrands.push(String($(this).val()).toLowerCase());
            });

            var visible = 0;

            $('#qs-model option').each(function (optIndex) {
                var $opt = $(this);
                var id = String($opt.data('model-id') || $opt.val() || '').toLowerCase();
                var ctx = window.AGFO.normalizeContext($opt.data('context') || '32k');

                var show = true;

                if (checkedContexts.length && checkedContexts.indexOf(ctx) === -1) {
                    show = false;
                }

                if (show && checkedBrands.length && !window.AGFO.matchesBrand(id, checkedBrands)) {
                    show = false;
                }

                if (show && q && this.text.toLowerCase().indexOf(q) === -1) {
                    show = false;
                }

                if (show && reasoningOnly && !window.AGFO.isReasoning(id)) {
                    show = false;
                }

                // NEW 17.0.0: hide models the provider cannot serve, unless already selected.
                if (show && hideUnusable && window.AGFO.isUnusable($opt) && !$opt.is(':selected')) {
                    show = false;
                }

                this.style.display = show ? '' : 'none';
                if (rowByIndex[optIndex]) rowByIndex[optIndex].hidden = !show;

                if (show) visible++;
            });

            $('#model-count').text(visible);
            $('#qs-model-list .ax-empty-filter').remove();
            if ($rows.length && !visible) {
                $('#qs-model-list').append('<li class="ax-empty ax-empty-filter"><strong>Filtreyle eşleşen model yok</strong>Marka, bağlam veya arama filtresini gevşetin.</li>');
            }
        },

        activateTab: function (tab) {
            tab = String(tab || 'models');
            if (!$('.agfo-modal-tab[data-agfo-tab="' + tab + '"]').length) tab = 'models';

            $('.agfo-modal-tab').removeClass('is-active').attr('aria-selected', 'false');
            $('.agfo-modal-tab[data-agfo-tab="' + tab + '"]').addClass('is-active').attr('aria-selected', 'true');
            $('.agfo-tab-panel').attr('hidden', true);
            $('.agfo-tab-panel[data-agfo-panel="' + tab + '"]').removeAttr('hidden');

            try { window.sessionStorage.setItem('agfoQuickSwitchTab', tab); } catch (e) {}

            if (tab === 'benchmark') {
                this.loadModelScore($('#qs-provider').val() || '', $('#qs-model').val() || '');
            } else if (tab === 'settings') {
                this.syncDraftSummary();
                this.loadGuardRules();
            } else if (tab === 'translate' && window.AGFO_Boards) {
                window.AGFO_Boards.loadTranslation();
            } else if (tab === 'image' && window.AGFO_Boards) {
                window.AGFO_Boards.loadImage();
            } else if (tab === 'saved') {
                this.filterSavedModels($('#qs-saved-model-search').val() || '');
            }
        },

        restoreTab: function () {
            var tab = 'models';
            try { tab = window.sessionStorage.getItem('agfoQuickSwitchTab') || 'models'; } catch (e) {}
            this.activateTab(tab);
        },

        renderSavedState: function () {
            var s = this.savedState || { provider: '-', model: '-', reasoning: 0, fusionMode: 'off', fusionProfile: 'balanced' };
            $('#cfg-provider').text(s.provider || '-');
            $('#cfg-model').text(s.model || '-');
            $('#cfg-reasoning').text(s.reasoning ? 'Açık' : 'Kapalı');
            $('#cfg-fusion').text(s.fusionMode !== 'off' ? (String(s.fusionMode).toUpperCase() + ' / ' + (s.fusionProfileLabel || s.fusionProfile || '-')) : 'Kapalı');
        },

        getDraftState: function () {
            var mode = $('#qs-fusion-mode').val() || 'off';
            var profile = $('#qs-fusion-profile').val() || 'balanced';
            var profileLabel = $('#qs-fusion-profile option:selected').text() || profile;
            return {
                provider: $('#qs-provider').val() || '',
                model: $('#qs-model').val() || '',
                reasoning: $('#qs-reasoning').is(':checked') ? 1 : 0,
                fusionMode: mode,
                fusionProfile: profile,
                fusionProfileLabel: profileLabel
            };
        },

        syncDraftSummary: function () {
            var d = this.getDraftState();
            var s = this.savedState || {};

            $('#draft-provider').text(d.provider || '-');
            $('#draft-model').text(d.model || '-');
            $('#draft-reasoning').text(d.reasoning ? 'Açık' : 'Kapalı');
            $('#draft-fusion').text(d.fusionMode !== 'off' ? (String(d.fusionMode).toUpperCase() + ' / ' + (d.fusionProfileLabel || d.fusionProfile)) : 'Kapalı');

            var changed = !!this.savedState && (
                String(d.provider || '') !== String(s.provider || '') ||
                String(d.model || '') !== String(s.model || '') ||
                Number(d.reasoning || 0) !== Number(s.reasoning || 0) ||
                String(d.fusionMode || 'off') !== String(s.fusionMode || 'off') ||
                String(d.fusionProfile || 'balanced') !== String(s.fusionProfile || 'balanced')
            );
            $('#agfo-unsaved-badge').toggleClass('is-visible', changed);
            $('#ax-dirty').toggleClass('is-visible', changed);
        },

        resetBenchmark: function (message) {
            this.lastBenchmarkKey = '';
            $('#benchmark-model-name').text('Model seçilmedi');
            $('#model-score-display').hide();
            $('#score-content').empty();
            $('#model-score-placeholder').show().html(
                this.escHtml(message || 'Model seçin.')
            );
        },

        loadModelScore: function (provider, model) {
            provider = String(provider || '');
            model = String(model || '');

            if (!provider || !model || !$('#qs-model option').filter(function () { return $(this).val() === model && $(this).data('model-id'); }).length) {
                this.resetBenchmark('Benchmark için Modeller sekmesinden bir model seçin.');
                return;
            }

            var key = provider + '::' + model;
            if (this.lastBenchmarkKey === key && $('#model-score-display').is(':visible')) return;
            this.lastBenchmarkKey = key;
            var seq = ++this.benchmarkRequestSeq;

            $('#benchmark-model-name').text(model);
            $('#model-score-display').hide();
            $('#model-score-placeholder').show().html('Benchmark yükleniyor');

            if (typeof agfoConfig === 'undefined') {
                this.renderBenchmarkFallback(model, 'Bağlantı yapılandırması bulunamadı.');
                return;
            }

            $.post(agfoConfig.ajaxurl, {
                action: 'agfo_get_model_score',
                nonce: agfoConfig.nonce,
                provider: provider,
                model: model
            }).done(function (res) {
                if (seq !== window.AGFO.benchmarkRequestSeq) return;
                if (res && res.success && res.data) {
                    window.AGFO.renderBenchmark(res.data, model);
                } else {
                    window.AGFO.renderBenchmarkFallback(model, (res && res.data && res.data.message) ? res.data.message : 'Bu model için kaynak benchmark kırılımı yok.');
                }
            }).fail(function () {
                if (seq !== window.AGFO.benchmarkRequestSeq) return;
                window.AGFO.renderBenchmarkFallback(model, 'Benchmark servisine ulaşılamadı.');
            });
        },

        renderBenchmark: function (data, model) {
            var score = Number(data.final_score || 0);
            var tier = data.tier || '-';
            var sources = data.sources || {};
            var labels = { lmsys: 'LMSYS', openllm: 'OpenLLM', artificialanalysis: 'Artificial Analysis' };
            var sourceHtml = '';

            Object.keys(labels).forEach(function (key) {
                if (sources[key] === undefined || sources[key] === null) return;
                sourceHtml += '<div class="agfo-score-source"><strong>' + window.AGFO.escHtml(Math.round(Number(sources[key]))) + '</strong><span>' + window.AGFO.escHtml(labels[key]) + '</span></div>';
            });

            var html = '<div class="agfo-score-hero">' +
                '<div class="agfo-score-number">' + this.escHtml(Math.round(score)) + '<small>Tier ' + this.escHtml(tier) + '</small></div>' +
                '<div><div style="font-size:12px;font-weight:700;color:#0f172a;margin-bottom:8px;">Birleşik benchmark puanı</div>' +
                '<div class="agfo-score-source-grid">' + (sourceHtml || '<div style="color:#94a3b8;font-size:10px;">Kaynak kırılımı yok.</div>') + '</div></div>' +
                '</div>';

            $('#benchmark-model-name').text(model);
            $('#score-content').html(html);
            $('#model-score-placeholder').hide();
            $('#model-score-display').show();
        },

        renderBenchmarkFallback: function (model, message) {
            var $opt = $('#qs-model option').filter(function () { return $(this).val() === model; }).first();
            var score = $opt.data('score');
            var tier = $opt.data('tier');

            $('#benchmark-model-name').text(model);
            if (score !== undefined && score !== null && score !== '') {
                var html = '<div class="agfo-score-hero">' +
                    '<div class="agfo-score-number">' + this.escHtml(score) + '<small>Tier ' + this.escHtml(tier || '-') + '</small></div>' +
                    '<div><div style="font-size:12px;font-weight:700;color:#0f172a;margin-bottom:6px;">AGFO model sıralama puanı</div>' +
                    '<div style="font-size:10px;color:#64748b;line-height:1.5;">' + this.escHtml(message || 'Kaynak benchmark kırılımı bulunamadı.') + ' Liste sıralama puanı gösteriliyor.</div></div>' +
                    '</div>';
                $('#score-content').html(html);
                $('#model-score-placeholder').hide();
                $('#model-score-display').show();
            } else {
                $('#model-score-display').hide();
                $('#model-score-placeholder').show().html(this.escHtml(message || 'Bu model için benchmark bulunamadı.'));
            }
        },

        matchesBrand: function (id, brands) {
            id = String(id || '').toLowerCase();

            if (!brands.length) return true;

            return brands.some(function (brand) {
                brand = String(brand || '').toLowerCase();

                if (brand === 'openai') {
                    return id.indexOf('gpt') >= 0 || id.indexOf('openai/') >= 0 || /^o[134]/.test(id);
                }

                if (brand === 'claude' || brand === 'anthropic') {
                    return id.indexOf('claude') >= 0 || id.indexOf('anthropic/') >= 0;
                }

                if (brand === 'gemini' || brand === 'google') {
                    return id.indexOf('gemini') >= 0 || id.indexOf('gemma') >= 0 || id.indexOf('google/') >= 0;
                }

                if (brand === 'deepseek') {
                    return id.indexOf('deepseek') >= 0;
                }

                if (brand === 'qwen') {
                    return id.indexOf('qwen') >= 0;
                }

                if (brand === 'llama' || brand === 'meta') {
                    return id.indexOf('llama') >= 0 || id.indexOf('meta-llama') >= 0;
                }

                if (brand === 'mistral' || brand === 'mistralai') {
                    return id.indexOf('mistral') >= 0;
                }

                if (brand === 'grok' || brand === 'xai' || brand === 'x-ai') {
                    return id.indexOf('grok') >= 0 || id.indexOf('x-ai') >= 0;
                }

                if (brand === 'kimi' || brand === 'moonshot') {
                    return id.indexOf('kimi') >= 0 || id.indexOf('moonshot') >= 0;
                }

                if (brand === 'glm' || brand === 'zai' || brand === 'z-ai') {
                    return id.indexOf('glm') >= 0 || id.indexOf('zai') >= 0 || id.indexOf('z-ai') >= 0;
                }

                return id.indexOf(brand) >= 0;
            });
        },

        isReasoning: function (id) {
            id = String(id || '').toLowerCase();

            return (
                id.indexOf('thinking') >= 0 ||
                id.indexOf('reasoning') >= 0 ||
                id.indexOf('reasoner') >= 0 ||
                id.indexOf('r1') >= 0 ||
                /^o[134]/.test(id) ||
                id.indexOf('/o1') >= 0 ||
                id.indexOf('/o3') >= 0 ||
                id.indexOf('/o4') >= 0
            );
        },

        probeSelectedModel: function ($btn) {
            var self = window.AGFO;
            var provider = $('#qs-provider').val() || 'openai';
            var model = $('#qs-model').val() || '';

            if (!model) {
                self.toast('Önce listeden bir model seçin.', 'error');
                return;
            }

            var $label = $btn.find('.ax-btn-text');
            var oldText = $label.text();
            $btn.prop('disabled', true);
            $label.text('Test ediliyor');
            self.setStatus('Uyumluluk testi', 'busy');

            $.post(agfoConfig.ajaxurl, {
                action: 'agfo_probe_model_capabilities',
                nonce: agfoConfig.nonce,
                provider: provider,
                model: model
            })
            .done(function (res) {
                if (!res || !res.success) {
                    var msg = (res && res.data && res.data.message) ? res.data.message : (res && res.data && res.data.error ? res.data.error : 'Uyumluluk testi başarısız.');
                    self.toast(msg, 'error');
                    self.setStatus('Test başarısız', 'error');
                    return;
                }

                var caps = (res.data && res.data.capabilities) ? res.data.capabilities : {};
                var routeTxt = {
                    chat: 'Chat Completions',
                    responses_bridge: 'Responses köprüsü (otomatik)',
                    unavailable: 'Erişim yok — yedek modele yönlenir',
                    not_chat: 'Chat modeli değil'
                }[caps.transport_route || 'chat'] || (caps.endpoint_type || '-');
                var lines = [
                    model,
                    'Uç: ' + routeTxt,
                    'Chat: ' + (caps.supports_chat ? 'çalışıyor' : 'çalışmıyor') + ' · DOCX: ' + (caps.docx_allowed ? 'uygun' : 'uygun değil'),
                    'Temperature: ' + (caps.sampling_policy === 'provider_default' ? 'sağlayıcı varsayılanı (otomatik kaldırılır)' : 'gönderilebilir')
                ];
                self.toast(lines.join('\n'), 'ok');
                self.setStatus('Test kaydedildi', 'ok');
                self.loadModels(provider);
            })
            .fail(function (xhr) {
                console.error('[AGFO] capability probe fail:', xhr.status, xhr.responseText);
                self.toast('Sunucuya ulaşılamadı (HTTP ' + xhr.status + ').', 'error');
                self.setStatus('Bağlantı hatası', 'error');
            })
            .always(function () {
                $btn.prop('disabled', false);
                $label.text(oldText);
            });
        },

        save: function () {
            var self = window.AGFO;
            if (typeof agfoConfig === 'undefined') return;

            var provider = $('#qs-provider').val();
            var model = $('#qs-model').val();
            var reasoning = $('#qs-reasoning').is(':checked') ? 1 : 0;
            // CHANGED: Compact Fusion values are saved with the normal Quick Switch state.
            var fusionMode = $('#qs-fusion-mode').val() || 'off';
            var fusionProfile = $('#qs-fusion-profile').val() || 'balanced';

            if (!model || !$('#qs-model option').filter(function () { return $(this).val() === model && $(this).data('model-id'); }).length) {
                self.toast('Kaydetmeden önce listeden bir model seçin.', 'error');
                return;
            }

            var $btn = $('#qs-save-btn');
            $btn.prop('disabled', true).text('Kaydediliyor');

            $.post(agfoConfig.ajaxurl, {
                action: 'agfo_qs_save',
                nonce: agfoConfig.nonce,
                provider: provider,
                model: model,
                reasoning: reasoning,
                fusion_mode: fusionMode,
                fusion_profile: fusionProfile
            })
            .done(function (res) {
                if (res && res.success) {
                    $btn.text('Kaydedildi');
                    self.savedState = self.getDraftState();
                    self.renderSavedState();
                    self.syncDraftSummary();
                    self.syncSelection();
                    self.setStatus('Kaydedildi', 'ok');

                    setTimeout(function () {
                        $btn.prop('disabled', false).text('Kaydet ve uygula');
                    }, 1400);
                } else {
                    self.toast('Ayar kaydedilemedi. Sayfayı yenileyip tekrar deneyin.', 'error');
                    $btn.prop('disabled', false).text('Kaydet ve uygula');
                }
            })
            .fail(function () {
                self.toast('Sunucuya ulaşılamadı; ayar kaydedilmedi.', 'error');
                $btn.prop('disabled', false).text('Kaydet ve uygula');
            });
        },

        downloadModels: function ($btn) {
            if (typeof agfoConfig === 'undefined') return;

            var self = window.AGFO;
            var provider = $('#qs-provider').val();
            var $label = $btn.find('.ax-btn-text');
            if (!$label.length) $label = $btn;

            $btn.attr('disabled', 'disabled').css('pointer-events', 'none');
            $label.text('Güncelleniyor');
            self.setStatus('Modeller indiriliyor', 'busy');

            $.getJSON(agfoConfig.ajaxurl, {
                action: 'agfo_download_models',
                code: provider,
                nonce: agfoConfig.nonce // CHANGED 16.6.0: sunucu tarafinda nonce zorunlu oldu.
            })
            .done(function (res) {
                if (res && res.ok) {
                    self.toast(res.message || 'Model listesi güncellendi.', 'ok');
                    self.loadModels(provider);
                } else {
                    self.toast((res && res.error) ? res.error : 'Model listesi güncellenemedi.', 'error');
                    self.setStatus('Güncellenemedi', 'error');
                }
            })
            .fail(function () {
                self.toast('Sunucuya ulaşılamadı.', 'error');
                self.setStatus('Bağlantı hatası', 'error');
            })
            .always(function () {
                $btn.removeAttr('disabled').css('pointer-events', '');
                $label.text('Güncelle');
            });
        },

        /* ── NEW 17.1.0: sorting ─────────────────────────────── */

        sortMode: (function () { try { return window.sessionStorage.getItem('agfoQuickSwitchSort') || 'newest'; } catch (e) { return 'newest'; } }()),

        sortModels: function (models) {
            var mode = this.sortMode || 'newest';
            $('#qs-model-sort').val(mode);
            var list = (models || []).slice();
            var num = function (v) { v = Number(v); return isNaN(v) ? 0 : v; };
            var idOf = function (m) { return String(typeof m === 'string' ? m : (m.id || m.name || '')); };
            var field = function (m, k) { return typeof m === 'string' ? null : m[k]; };

            if (mode === 'name') {
                list.sort(function (a, b) { return idOf(a).localeCompare(idOf(b)); });
            } else if (mode === 'score') {
                list.sort(function (a, b) { return num(field(b, 'rank_score')) - num(field(a, 'rank_score')) || idOf(a).localeCompare(idOf(b)); });
            } else if (mode === 'price') {
                var price = function (m) {
                    var i = field(m, 'in_price'), o = field(m, 'out_price');
                    if (i === null || i === undefined) return Infinity;
                    return num(i) + num(o === null || o === undefined ? i : o);
                };
                list.sort(function (a, b) { return price(a) - price(b) || idOf(a).localeCompare(idOf(b)); });
            } else {
                // Newest first: release time when every model has one; otherwise family
                // version (gpt-5.7 above gpt-5.6), then release/date, then name.
                var allDated = list.length > 0 && list.every(function (m) { return num(field(m, 'released')) > 0; });
                list.sort(function (a, b) {
                    if (allDated) return num(field(b, 'released')) - num(field(a, 'released')) || idOf(a).localeCompare(idOf(b));
                    return num(field(b, 'version')) - num(field(a, 'version'))
                        || num(field(b, 'released')) - num(field(a, 'released'))
                        || idOf(a).localeCompare(idOf(b));
                });
            }
            return list;
        },

        /* ── NEW 17.0.0: model table ─────────────────────────── */

        isUnusable: function ($opt) {
            var route = String($opt.data('route') || '');
            if (route === 'unavailable' || route === 'not_chat') return true;
            return String($opt.data('supports-chat')) === '0' && route !== 'responses_bridge';
        },

        listMessage: function (title, detail) {
            $('#qs-model').html('');
            $('#qs-model-list').html('<li class="ax-empty"><strong>' + this.escHtml(title) + '</strong>' + this.escHtml(detail || '') + '</li>');
        },

        badgesFor: function ($opt) {
            var b = [];
            var route = String($opt.data('route') || 'chat');
            if (route === 'responses_bridge') b.push(['is-bridge', 'Responses köprüsü', 'Chat isteği otomatik olarak /v1/responses ucuna çevrilir']);
            else if (route === 'unavailable') b.push(['is-bad', 'Erişim yok', 'Sağlayıcı bu modele erişimi reddetti; istekler yedek modele gider']);
            else if (this.isUnusable($opt)) b.push(['is-bad', 'Chat dışı', 'Metin chat modeli değil']);
            else b.push(['is-ok', 'Hazır', 'Chat Completions ile çalışır']);

            if (String($opt.data('is-new')) === '1' && !this.isUnusable($opt)) {
                var rel = Number($opt.data('released') || 0);
                b.unshift(['is-new', 'Yeni', rel ? 'Yayın: ' + new Date(rel * 1000).toLocaleDateString('tr-TR') : 'Ailesinin en yeni sürümü']);
            }

            if (String($opt.data('sampling')) === 'provider_default' && !this.isUnusable($opt)) {
                b.push(['is-auto', 'Temp otomatik', 'Bu model yalnız sağlayıcı varsayılanını kabul eder; temperature ve top_p gönderilmeden önce kaldırılır']);
            }
            if (String($opt.data('docx-allowed')) === '0' && !this.isUnusable($opt)) {
                b.push(['is-warn', 'DOCX yok', 'DOCX üretimine uygun işaretlenmedi']);
            }
            return b;
        },

        renderModelRows: function () {
            var self = this;
            var selected = $('#qs-model').val() || '';
            var html = '';
            var ctxColor = { '8k': '#c9d1f6', '16k': '#a9b6f1', '32k': '#8496ea', '64k': '#5d75e1', '100k': '#3c58d9', '200k': '#2a42b5', '1m': '#1b2c80' };
            var ctxLabel = { '8k': '8K', '16k': '16K', '32k': '32K', '64k': '64K', '100k': '100K+', '200k': '200K+', '1m': '1M+' };

            $('#qs-model option').each(function () {
                var $opt = $(this);
                var id = String($opt.data('model-id') || '');
                if (!id) return;
                var idx = $opt.index();
                var ctx = String($opt.data('context') || '32k');
                var inP = $opt.data('in-price');
                var outP = $opt.data('out-price');
                var price = (inP !== '' && inP !== undefined) ? self.fmtUsd(inP) + (outP !== '' && outP !== undefined ? ' · ' + self.fmtUsd(outP) : '') : String($opt.data('price') || '');
                var speed = self.speedWord($opt.data('speed-score'));
                var tier = String($opt.data('tier') || '');
                var score = String($opt.data('score') || '');
                var probed = String($opt.data('probe-status')) === 'completed';
                var unusable = self.isUnusable($opt);
                var isSel = id === selected;
                var badges = self.badgesFor($opt).map(function (x) {
                    return '<span class="ax-badge ' + x[0] + '" title="' + self.escAttr(x[2]) + '">' + self.escHtml(x[1]) + '</span>';
                }).join('');

                html += '<li class="ax-row' + (isSel ? ' is-selected' : '') + (unusable ? ' is-unusable' : '') + '" role="option"' +
                    ' aria-selected="' + (isSel ? 'true' : 'false') + '"' +
                    (unusable ? ' aria-disabled="true"' : '') +
                    ' data-index="' + idx + '" data-model="' + self.escAttr(id) + '">' +
                    '<span class="ax-radio" aria-hidden="true"></span>' +
                    '<span class="ax-name" title="' + self.escAttr(id) + '">' + self.escHtml(id.replace('models/', '')) + (probed ? '<small>test edildi</small>' : '') + '</span>' +
                    '<span class="ax-cell ax-col-ctx"><span class="ax-ctx"><span class="ax-ctx-dot" style="background:' + (ctxColor[ctx] || '#c9d1f6') + '"></span>' + self.escHtml(ctxLabel[ctx] || ctx) + '</span></span>' +
                    '<span class="ax-cell ax-col-price is-num">' + (price ? self.escHtml(price) : '<span class="ax-muted">—</span>') + '</span>' +
                    '<span class="ax-cell ax-col-speed">' + (speed ? self.escHtml(speed) : '<span class="ax-muted">—</span>') + '</span>' +
                    '<span class="ax-cell ax-col-score is-num">' + (score !== '' ? '<span class="ax-tier">' + self.escHtml(tier) + ' <b>' + self.escHtml(score) + '</b></span>' : '<span class="ax-muted">—</span>') + '</span>' +
                    '<span class="ax-badges">' + badges + '</span>' +
                    '</li>';
            });

            $('#qs-model-list').html(html || '<li class="ax-empty"><strong>Bu sağlayıcı için model yok</strong>“Güncelle” ile listeyi indirin.</li>');
            this.syncSelection();
            var sel = $('#qs-model-list .ax-row.is-selected')[0];
            if (sel && sel.scrollIntoView) {
                setTimeout(function () { sel.scrollIntoView({ block: 'center' }); }, 0);
            }
        },

        selectModel: function (model, $row) {
            if (!model) return;
            if ($row && $row.hasClass('is-unusable')) {
                this.toast('Bu model sağlayıcı tarafından chat için sunulmuyor. Başka bir model seçin.', 'error');
                return;
            }
            $('#qs-model').val(model).trigger('change');
            $('#qs-model-list .ax-row').removeClass('is-active');
            if ($row) $row.addClass('is-active');
        },

        syncSelection: function () {
            var val = $('#qs-model').val() || '';
            var $rows = $('#qs-model-list .ax-row');
            $rows.removeClass('is-selected').attr('aria-selected', 'false');
            var $sel = $rows.filter(function () { return String($(this).data('model')) === val; });
            $sel.addClass('is-selected').attr('aria-selected', 'true');

            var self = this;
            var $opt = $('#qs-model option').filter(function () { return $(this).val() === val; }).first();
            $('#ax-selected-badges').html($opt.length && val ? this.badgesFor($opt).map(function (x) {
                return '<span class="ax-badge ' + x[0] + '" title="' + self.escAttr(x[2]) + '">' + self.escHtml(x[1]) + '</span>';
            }).join('') : '');
        },

        listKeydown: function (e) {
            var $rows = $('#qs-model-list .ax-row').not('[hidden]');
            if (!$rows.length) return;
            var $active = $rows.filter('.is-active');
            if (!$active.length) $active = $rows.filter('.is-selected');
            var i = $rows.index($active);

            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                i = e.key === 'ArrowDown' ? Math.min($rows.length - 1, i + 1) : Math.max(0, i - 1);
                $rows.removeClass('is-active');
                var $next = $rows.eq(i).addClass('is-active');
                if ($next[0] && $next[0].scrollIntoView) $next[0].scrollIntoView({ block: 'nearest' });
            } else if ((e.key === 'Enter' || e.key === ' ') && $active.length) {
                e.preventDefault();
                this.selectModel(String($active.data('model') || ''), $active);
            }
        },

        /* ── NEW 17.0.0: chrome helpers ──────────────────────── */

        setStatus: function (text, state) {
            $('#qs-status-indicator').text(text).attr('data-state', state || 'idle');
        },

        toast: function (message, type) {
            var $t = $('#ax-toast');
            if (!$t.length) { window.alert(message); return; }
            clearTimeout(this.toastTimer);
            $t.text(message).toggleClass('is-error', type === 'error').prop('hidden', false);
            this.toastTimer = setTimeout(function () { $t.prop('hidden', true); }, type === 'error' ? 6500 : 4500);
        },

        updateFusionState: function () {
            var isOpenRouter = ($('#qs-provider').val() || '') === 'openrouter';
            $('#ax-fusion-group').toggleClass('is-inactive', !isOpenRouter);
            $('#qs-fusion-mode, #qs-fusion-profile').prop('disabled', !isOpenRouter);
            $('.agfo-download-models').attr('data-provider', $('#qs-provider').val() || '');
        },

        /* ── NEW 17.0.0: request guard panel ─────────────────── */

        loadGuardRules: function () {
            var self = this;
            if (typeof agfoConfig === 'undefined') return;
            $.post(agfoConfig.ajaxurl, { action: 'agfo_aim_guard_rules', nonce: agfoConfig.nonce })
                .done(function (res) {
                    if (!res || !res.success) return;
                    $('#ax-guard-fallback').prop('checked', !!res.data.fallback);
                    self.renderGuardRules(res.data.rules || []);
                });
        },

        renderGuardRules: function (rules) {
            if (!rules.length) {
                $('#ax-guard-rules').html('<div class="ax-guard-empty">Henüz öğrenilmiş bir kural yok. Sağlayıcı bir parametreyi veya modeli reddettiğinde burada görünür.</div>');
                return;
            }
            var self = this;
            var label = {
                param: 'Parametre kaldırılır',
                responses: 'Responses köprüsü',
                unavailable: 'Erişim yok, yedek modele yönlenir',
                not_chat: 'Chat modeli değil'
            };
            var rows = rules.slice(0, 60).map(function (r) {
                var what = r.rule === 'param' ? label.param + ': ' + r.value : (label[r.value] || r.value);
                var when = r.at ? new Date(r.at * 1000).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' }) : '';
                return '<tr><td>' + self.escHtml(r.provider) + '</td><td>' + self.escHtml(r.model) + '</td><td>' + self.escHtml(what) + '</td><td>' + self.escHtml(when) + '</td></tr>';
            }).join('');
            $('#ax-guard-rules').html('<table class="ax-guard-table"><thead><tr><th>Sağlayıcı</th><th>Model</th><th>Kural</th><th>Öğrenildi</th></tr></thead><tbody>' + rows + '</tbody></table>');
        },

        resetGuardRules: function ($btn) {
            var self = this;
            if (!window.confirm('Öğrenilmiş tüm koruma kuralları silinsin mi? Temperature için yerleşik koruma devam eder.')) return;
            $btn.prop('disabled', true);
            $.post(agfoConfig.ajaxurl, { action: 'agfo_aim_guard_reset', nonce: agfoConfig.nonce })
                .done(function (res) {
                    if (res && res.success) {
                        self.renderGuardRules([]);
                        self.toast('Öğrenilmiş kurallar sıfırlandı.', 'ok');
                    }
                })
                .always(function () { $btn.prop('disabled', false); });
        },

        saveGuardFallback: function (enabled) {
            var self = this;
            $.post(agfoConfig.ajaxurl, { action: 'agfo_aim_guard_reset', nonce: agfoConfig.nonce, fallback: enabled ? 1 : 0 })
                .done(function (res) {
                    if (res && res.success) self.toast(enabled ? 'Yedek model yönlendirmesi açık.' : 'Yedek model yönlendirmesi kapalı.', 'ok');
                });
        },

        escHtml: function (str) {
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        },

        escAttr: function (str) {
            return window.AGFO.escHtml(str);
        }
    };

    window.agfoOpenSwitcher = function () {
        var overlay = document.getElementById('agfo-switcher-overlay');
        var modal = document.getElementById('agfo-switcher-modal');

        if (!overlay || !modal) {
            console.error('[AGFO] Modal elementi bulunamadı.');
            return false;
        }

        overlay.style.display = 'block';
        modal.classList.add('agfo-open');

        window.AGFO.restoreTab();
        window.AGFO.loadData();

        return false;
    };

    window.agfoCloseSwitcher = function () {
        var overlay = document.getElementById('agfo-switcher-overlay');
        var modal = document.getElementById('agfo-switcher-modal');

        if (overlay) overlay.style.display = 'none';
        if (modal) modal.classList.remove('agfo-open');

        return false;
    };

    /* ── CHANGED 16.0.1: Model Yönetimi sayfası butonları — eksik handler'lar eklendi.
       Sayfa markup'ı (class-admin.php) ve AJAX uçları (class-data.php: agfo_refresh_provider_models,
       agfo_refresh_all_models, agfo_clear_model_cache) mevcuttu; script.js tarafında hiçbir bağlama yoktu. ── */
    function agfoMmStatus(msg, ok) {
        var $box = $('#agfo-refresh-status');
        if (!$box.length) return;
        $box.stop(true, true).show()
            .css({ background: ok ? '#edfaef' : '#fcf0f1', border: '1px solid ' + (ok ? '#46b450' : '#dc3232'), color: '#1d2327' })
            .text(msg);
    }

    function agfoMmUpdateRow(code, d) {
        var $row = $('#agfo-row-' + code);
        if (!$row.length || !d) return;
        $row.find('.raw-count').text(d.raw_count != null ? d.raw_count : 0);
        $row.find('.filtered-count').text(d.filtered_count != null ? d.filtered_count : 0);
        $row.find('.model-count').text(d.final_count != null ? d.final_count : (d.models ? d.models.length : 0));
        var now = new Date();
        var pad = function (n) { return (n < 10 ? '0' : '') + n; };
        $row.find('td:eq(5) small').text(pad(now.getDate()) + '.' + pad(now.getMonth() + 1) + '.' + now.getFullYear() + ' ' + pad(now.getHours()) + ':' + pad(now.getMinutes()));
    }

    $(document).on('click', '.agfo-refresh-single', function (e) {
        e.preventDefault();
        if (typeof agfoConfig === 'undefined') { alert('agfoConfig bulunamadı — sayfayı yenileyin.'); return; }
        var $btn = $(this), code = $btn.data('provider');
        if (!code) return;
        $btn.prop('disabled', true).text('⏳ Yenileniyor…');
        agfoMmStatus(code + ' modelleri çekiliyor…', true);
        $.post(agfoConfig.ajaxurl, {
            action: 'agfo_refresh_provider_models',
            nonce: agfoConfig.nonce,
            provider: code
        }).done(function (res) {
            if (res && res.success) {
                agfoMmUpdateRow(code, res.data);
                agfoMmStatus('✅ ' + code + ': ' + res.data.final_count + ' model kaydedildi (' + res.data.filtered_count + ' filtrelendi, ham ' + res.data.raw_count + ')', true);
            } else {
                agfoMmStatus('❌ ' + code + ': ' + ((res && res.data) ? res.data : 'Bilinmeyen hata'), false);
            }
        }).fail(function (xhr) {
            agfoMmStatus('❌ ' + code + ': istek başarısız (HTTP ' + xhr.status + ')', false);
        }).always(function () {
            $btn.prop('disabled', false).text('🔄 Yenile');
        });
    });

    /* CHANGED 16.2.0: 'Tumu yenile' artik SIRALI calisir -> gercek yuzde (i/N) + satirlar aninda guncellenir.
       Sunucudaki toplu uc (agfo_refresh_all_models) korunuyor; yalnizca istemci akisi sirali oldu.
       AGFOProgress varsa mini bar gercek yuzdeyle ilerler. */
    $(document).on('click', '#agfo-refresh-all-btn', function (e) {
        e.preventDefault();
        if (typeof agfoConfig === 'undefined') { alert('agfoConfig bulunamadı — sayfayı yenileyin.'); return; }
        var $btn = $(this);
        var rows = [];
        $('.agfo-refresh-single').each(function () {
            rows.push({ code: $(this).data('provider'), hasKey: !$(this).prop('disabled') });
        });
        if (!rows.length) { agfoMmStatus('Sağlayıcı satırı bulunamadı.', false); return; }

        var P = window.AGFOProgress || { begin:function(){return this;}, stage:function(){return this;}, done:function(){return this;}, fail:function(){return this;} };
        var lines = [], i = 0, total = rows.length, failed = 0;
        $btn.prop('disabled', true).text('⏳ Tümü yenileniyor…');
        P.begin('Model listeleri yenileniyor');

        var next = function () {
            if (i >= total) {
                agfoMmStatus(lines.join('\n'), failed === 0);
                (failed === 0 ? P.done(total + ' sağlayıcı tamamlandı') : P.done((total - failed) + '/' + total + ' başarılı'));
                $btn.prop('disabled', false).text('🔄 Tüm Modelleri Yenile');
                return;
            }
            var row = rows[i], pct = Math.round((i / total) * 100);
            i++;
            if (!row.hasKey) {
                lines.push('⏭️ ' + row.code + ': API key yok');
                agfoMmStatus(lines.join('\n'), true);
                next();
                return;
            }
            P.stage(row.code + ' çekiliyor… (' + i + '/' + total + ')', pct);
            agfoMmStatus(lines.concat(['⏳ ' + row.code + '…']).join('\n'), true);
            $.post(agfoConfig.ajaxurl, {
                action: 'agfo_refresh_provider_models',
                nonce: agfoConfig.nonce,
                provider: row.code
            }).done(function (res) {
                if (res && res.success) {
                    agfoMmUpdateRow(row.code, res.data);
                    lines.push('✅ ' + row.code + ': ' + res.data.final_count + ' model');
                } else {
                    failed++;
                    lines.push('❌ ' + row.code + ': ' + ((res && res.data) ? res.data : 'hata'));
                }
            }).fail(function (xhr) {
                failed++;
                lines.push('❌ ' + row.code + ': istek başarısız (HTTP ' + xhr.status + ')');
            }).always(function () {
                agfoMmStatus(lines.join('\n'), failed === 0);
                next();
            });
        };
        next();
    });

    $(document).on('click', '#agfo-clear-cache-btn', function (e) {
        e.preventDefault();
        if (typeof agfoConfig === 'undefined') { alert('agfoConfig bulunamadı — sayfayı yenileyin.'); return; }
        if (!window.confirm('Tüm sağlayıcıların model önbelleği silinecek. Emin misiniz?')) return;
        var $btn = $(this);
        $btn.prop('disabled', true).text('⏳ Temizleniyor…');
        $.post(agfoConfig.ajaxurl, {
            action: 'agfo_clear_model_cache',
            nonce: agfoConfig.nonce
        }).done(function (res) {
            if (res && res.success) {
                $('tr[id^="agfo-row-"]').each(function () {
                    $(this).find('.raw-count,.filtered-count,.model-count').text('0');
                    $(this).find('td:eq(5) small').text('-');
                });
                agfoMmStatus('🗑️ ' + res.data, true);
            } else {
                agfoMmStatus('❌ ' + ((res && res.data) ? res.data : 'Bilinmeyen hata'), false);
            }
        }).fail(function (xhr) {
            agfoMmStatus('❌ İstek başarısız (HTTP ' + xhr.status + ')', false);
        }).always(function () {
            $btn.prop('disabled', false).text('🗑️ Önbelleği Temizle');
        });
    });

    $(document).ready(function () {
        window.AGFO.init();
        console.log('[AGFO] DOM hazır.');
    });

})(jQuery);