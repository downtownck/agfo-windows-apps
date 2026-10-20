(function ($) {
    'use strict';

    var activeJob = '';
    var timer = null;
    var catalogs = agfoTtsStudio.catalogs || {};
    var voiceSearchTimers = {};

    function setStatus(text, state) {
        $('#agfo-tts-status').attr('class', 'agfo-status is-' + (state || 'idle')).text(text);
    }

    function post(action, data) {
        return $.ajax({
            url: agfoTtsStudio.ajaxUrl,
            method: 'POST',
            dataType: 'json',
            data: $.extend({ action: action, nonce: agfoTtsStudio.nonce }, data || {})
        });
    }

    function formatQuotaNumber(value) {
        var number = Number(value || 0);
        return new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 }).format(number);
    }

    function quotaError(provider, message) {
        var $card = $('[data-quota-provider="' + provider + '"]');
        $card.addClass('is-error').removeClass('is-ready');
        $card.find('.agfo-quota-source').attr('class', 'agfo-quota-source is-error').text('Alınamadı');
        $card.find('.agfo-quota-remaining').text('—');
        $card.find('.agfo-quota-note').text(message || 'Kota bilgisi alınamadı.');
    }

    function renderQuota(provider, data) {
        var $card = $('[data-quota-provider="' + provider + '"]');
        var percent = Math.max(0, Math.min(100, Number(data.percent_used || 0)));
        $card.removeClass('is-error').addClass('is-ready');
        $card.find('.agfo-quota-source')
            .attr('class', 'agfo-quota-source ' + (data.exact ? 'is-live' : 'is-local'))
            .text(data.exact ? 'Canlı / kesin' : 'Yerel tahmin');
        $card.find('.agfo-quota-remaining').text(formatQuotaNumber(data.remaining));
        $card.find('[data-field="used"]').text(formatQuotaNumber(data.used));
        $card.find('[data-field="limit"]').text(formatQuotaNumber(data.limit));
        $card.find('[data-field="tier"]').text(data.tier || '—');
        $card.find('[data-field="reset_at"]').text(data.reset_at || '—');
        $card.find('.agfo-quota-progress span').css('width', percent.toFixed(2) + '%');
        $card.find('.agfo-quota-note').text(data.note || '');
    }

    function loadQuota(provider, force) {
        var hasKey = agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys[provider];
        var $card = $('[data-quota-provider="' + provider + '"]');
        if (!$card.length) return $.Deferred().resolve().promise();
        if (!hasKey) {
            quotaError(provider, (provider === 'minimax' ? 'MiniMax' : 'ElevenLabs') + ' API anahtarı tanımlı değil.');
            return $.Deferred().resolve().promise();
        }
        $card.removeClass('is-error is-ready');
        $card.find('.agfo-quota-source').attr('class', 'agfo-quota-source is-loading').text('Yükleniyor');
        return post('agfo_ai_provider_quota', { provider: provider, force: force ? 1 : 0 })
            .done(function (response) {
                if (!response || !response.success) {
                    quotaError(provider, response && response.data && response.data.message ? response.data.message : 'Kota bilgisi alınamadı.');
                    return;
                }
                renderQuota(provider, response.data);
            })
            .fail(function (xhr) {
                var message = xhr.responseJSON && xhr.responseJSON.data && xhr.responseJSON.data.message
                    ? xhr.responseJSON.data.message : 'Kota bilgisi alınamadı.';
                quotaError(provider, message);
            });
    }

    function optionWithValue($select, value) {
        return $select.find('option').filter(function () { return this.value === value; });
    }

    function selectedOrManual(selectId, manualId) {
        var value = $(selectId).val() || '';
        return value === '__manual__' ? $.trim($(manualId).val() || '') : value;
    }

    function toggleManualField(selectId, manualId) {
        var manual = $(selectId).val() === '__manual__';
        $(manualId).prop('hidden', !manual).prop('required', manual);
        if (manual) $(manualId).trigger('focus');
    }

    function findModel(provider, modelId) {
        var models = (catalogs[provider] && catalogs[provider].models) || [];
        for (var i = 0; i < models.length; i += 1) {
            if (models[i].id === modelId) return models[i];
        }
        return null;
    }

    function providerModel(provider) {
        return selectedOrManual('#agfo-tts-model-' + provider, '#agfo-tts-model-' + provider + '-manual');
    }

    function providerVoice(provider) {
        return selectedOrManual('#agfo-tts-voice-' + provider, '#agfo-tts-voice-' + provider + '-manual');
    }

    function defaultModel(provider) {
        if (provider === 'openai') return 'gpt-4o-mini-tts';
        if (provider === 'elevenlabs') return 'eleven_multilingual_v2';
        if (provider === 'minimax') return 'speech-2.8-hd';
        if (provider === 'ema') return 'ema-lightning';
        return '';
    }

    var PROVIDER_LABELS = { openai: 'OpenAI', elevenlabs: 'ElevenLabs', minimax: 'MiniMax', ema: 'EMA Lightning' };
    var SPEECH_PROVIDERS = ['openai', 'elevenlabs', 'minimax', 'ema'];

    function providerLabel(provider) {
        return PROVIDER_LABELS[provider] || provider;
    }

    function populateModels(provider, catalog) {
        var $select = $('#agfo-tts-model-' + provider);
        if (!$select.length) return;
        if (provider === 'ema') return; // Single fixed model rendered server-side.
        var previous = providerModel(provider);
        var defaultId = defaultModel(provider);
        $select.empty();

        (catalog.models || []).forEach(function (model) {
            var label = String(model.name || model.id || '');
            if (model.recommended) label += ' — önerilen';
            if (model.requires_alpha_access) label += ' — özel erişim';
            $('<option>')
                .val(model.id)
                .text(label)
                .attr('data-description', model.description || '')
                .attr('data-max-characters', model.max_characters || '')
                .attr('data-supports-instructions', model.supports_instructions ? '1' : '0')
                .appendTo($select);
        });
        $('<option>').val('__manual__').text('Özel / yeni model kimliği…').appendTo($select);

        if (previous && optionWithValue($select, previous).length) {
            $select.val(previous);
        } else if (optionWithValue($select, defaultId).length) {
            $select.val(defaultId);
        } else {
            $select.prop('selectedIndex', 0);
        }
        toggleManualField('#agfo-tts-model-' + provider, '#agfo-tts-model-' + provider + '-manual');
    }

    function populateOpenAiVoices(catalog) {
        var $select = $('#agfo-tts-voice-openai');
        var previous = $select.val() || 'coral';
        $select.empty();
        (catalog.voices || []).forEach(function (voice) {
            var label = String(voice.name || voice.id || '');
            if (voice.description) label += ' — ' + String(voice.description);
            $('<option>').val(voice.id).text(label).appendTo($select);
        });
        if (optionWithValue($select, previous).length) $select.val(previous);
        else if (optionWithValue($select, 'coral').length) $select.val('coral');
        else $select.prop('selectedIndex', 0);
        updateOpenAiCompatibility();
    }

    function categoryLabel(category) {
        var labels = {
            premade: 'Hazır sesler', professional: 'Profesyonel sesler', cloned: 'Klonlanmış sesler',
            generated: 'Tasarlanmış sesler', system: 'Sistem sesleri', music: 'Müzik sesleri',
            personal: 'Kişisel sesler', workspace: 'Çalışma alanı sesleri', community: 'Topluluk sesleri',
            default: 'Varsayılan sesler', 'built-in': 'Yerleşik sesler', other: 'Diğer sesler'
        };
        return labels[category] || category || labels.other;
    }

    function voiceSearchText(voice) {
        var labels = voice.labels || {};
        return [
            voice.name, voice.id, voice.category, voice.description, labels.language, labels.locale,
            labels.accent, labels.gender, labels.age, labels.use_case, labels.description, labels.created_time
        ].filter(Boolean).join(' ').toLocaleLowerCase('tr-TR');
    }

    function voiceLabel(voice) {
        var labels = voice.labels || {};
        var parts = [String(voice.name || voice.id || '')];
        [labels.language, labels.accent, labels.gender, labels.age].forEach(function (item) {
            if (item && parts.indexOf(String(item)) === -1) parts.push(String(item));
        });
        return parts.join(' — ');
    }

    function populateProviderVoices(provider, catalog, searchTerm) {
        var $select = $('#agfo-tts-voice-' + provider);
        if (!$select.length) return;
        var previous = providerVoice(provider);
        var term = $.trim(searchTerm || '').toLocaleLowerCase('tr-TR');
        var groups = {};
        var count = 0;

        (catalog.voices || []).forEach(function (voice) {
            if (term && voiceSearchText(voice).indexOf(term) === -1) return;
            var category = voice.category || 'other';
            if (!groups[category]) groups[category] = [];
            groups[category].push(voice);
            count += 1;
        });

        $select.empty();
        if (!count) {
            $('<option>').val('').text(term ? 'Aramayla eşleşen ses bulunamadı' : 'Bu hesap için ses bulunamadı').appendTo($select);
        }
        Object.keys(groups).sort().forEach(function (category) {
            var $group = $('<optgroup>').attr('label', categoryLabel(category));
            groups[category].forEach(function (voice) {
                $('<option>')
                    .val(voice.id)
                    .text(voiceLabel(voice))
                    .attr('data-description', voice.description || '')
                    .attr('data-preview-url', voice.preview_url || '')
                    .appendTo($group);
            });
            $group.appendTo($select);
        });
        $('<option>').val('__manual__').text('Voice ID\'yi manuel gir…').appendTo($select);

        if (previous && optionWithValue($select, previous).length) {
            $select.val(previous);
        } else if (count) {
            $select.find('option:not([value="__manual__"])').first().prop('selected', true);
        }
        toggleManualField('#agfo-tts-voice-' + provider, '#agfo-tts-voice-' + provider + '-manual');
        updateProviderVoiceHelp(provider);
    }

    function populateLanguages(model) {
        var $select = $('#agfo-tts-language');
        var previous = $select.val() || '';
        $select.empty().append($('<option>').val('').text('Otomatik algıla'));
        ((model && model.languages) || []).forEach(function (language) {
            $('<option>').val(language.id).text(language.name || language.id).appendTo($select);
        });
        if (previous && optionWithValue($select, previous).length) $select.val(previous);
    }

    function updateOpenAiCompatibility() {
        var model = findModel('openai', providerModel('openai'));
        var voiceIds = model && model.voice_ids ? model.voice_ids : [];
        var $voice = $('#agfo-tts-voice-openai');
        $voice.find('option').each(function () {
            var supported = !voiceIds.length || voiceIds.indexOf(this.value) !== -1;
            $(this).prop('disabled', !supported).prop('hidden', !supported);
        });
        if ($voice.find('option:selected').prop('disabled')) $voice.find('option:not(:disabled)').first().prop('selected', true);
        $('#agfo-openai-model-help').text(model ? (model.description || '') : 'Özel model kimliği kullanılacak.');
        updateInstructionsState();
        updateTextLimit();
    }

    function updateElevenModelHelp() {
        var model = findModel('elevenlabs', providerModel('elevenlabs'));
        var text = model ? (model.description || '') : 'Özel model kimliği kullanılacak.';
        if (model && model.max_characters) text += (text ? ' ' : '') + 'Tek istek sınırı: ' + model.max_characters + ' karakter.';
        $('#agfo-elevenlabs-model-help').text(text);
        populateLanguages(model);
        $('#agfo-tts-style').prop('disabled', !!model && model.can_use_style === false);
        $('#agfo-tts-speaker-boost').prop('disabled', !!model && model.can_use_speaker_boost === false);
        updateTextLimit();
    }

    function updateMiniMaxModelHelp() {
        var model = findModel('minimax', providerModel('minimax'));
        var text = model ? (model.description || '') : 'Özel model kimliği kullanılacak.';
        if (model && model.max_characters) text += (text ? ' ' : '') + 'Tek istek sınırı: ' + model.max_characters + ' karakter.';
        $('#agfo-minimax-model-help').text(text);
        updateTextLimit();
    }

    function updateProviderVoiceHelp(provider) {
        var $selected = $('#agfo-tts-voice-' + provider + ' option:selected');
        var text = $selected.attr('data-description') || 'Ses adı gösterilir; API çağrısında gerçek Voice ID kullanılır.';
        if ($selected.val() && $selected.val() !== '__manual__') text += ' Voice ID: ' + $selected.val();
        $('#agfo-' + provider + '-voice-help').text(text);
    }

    function updateInstructionsState() {
        var provider = $('#agfo-tts-provider').val();
        var model = findModel('openai', providerModel('openai'));
        var supports = !!(model && model.supports_instructions);
        var hasOpenAi = agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys.openai;
        var enabled = provider === 'openai' && hasOpenAi && supports;
        $('#agfo-tts-instructions').prop('disabled', !enabled);
        var help;
        if (enabled) help = 'Seçilen OpenAI modeli aksan, ton, duygu, hız ve fısıltı gibi talimatları yorumlayabilir.';
        else if (provider === 'elevenlabs') help = 'ElevenLabs için okuma biçimini ses seçimi ve gelişmiş ses ayarlarıyla belirleyin.';
        else if (provider === 'minimax') help = 'MiniMax için okuma biçimini ses, duygu, perde, ses düzeyi ve hız ayarlarıyla belirleyin.';
        else if (provider === 'ema') help = 'EMA Lightning talimat almaz; okumayı hız, duraklama ve telaffuz sözlüğüyle ayarlayın.';
        else help = 'Okuma talimatı yalnız talimat destekleyen OpenAI modeli açıkça seçildiğinde gönderilir.';
        $('#agfo-instructions-help').text(help);
    }

    function providerFormats(provider) {
        var defaults = {
            openai: ['mp3', 'opus', 'aac', 'flac', 'wav', 'pcm'],
            elevenlabs: ['mp3', 'wav', 'pcm', 'ulaw', 'alaw', 'opus'],
            minimax: ['mp3', 'wav', 'flac'],
            ema: ['mp3', 'wav']
        };
        return (catalogs[provider] && catalogs[provider].formats) || defaults[provider] || ['mp3'];
    }

    function intersection(arrays) {
        if (!arrays.length) return ['mp3'];
        return arrays.slice(1).reduce(function (current, next) {
            return current.filter(function (item) { return next.indexOf(item) !== -1; });
        }, arrays[0].slice());
    }

    function availableFormats() {
        var provider = $('#agfo-tts-provider').val();
        if (provider) return providerFormats(provider);
        // EMA is left out of the auto intersection: it is a Turkish-only fallback
        // and must not narrow the formats the paid providers can deliver.
        var active = ['openai', 'elevenlabs', 'minimax'].filter(function (code) {
            return agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys[code];
        }).map(providerFormats);
        if (!active.length && agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys.ema) active = [providerFormats('ema')];
        return intersection(active.length ? active : [providerFormats('openai'), providerFormats('elevenlabs'), providerFormats('minimax')]);
    }

    function updateFormats() {
        var formats = availableFormats();
        var $select = $('#agfo-tts-format');
        var current = $select.val();
        $select.find('option').each(function () {
            var supported = formats.indexOf(this.value) !== -1;
            $(this).prop('disabled', !supported).prop('hidden', !supported);
        });
        if (formats.indexOf(current) === -1) $select.val(formats.indexOf('mp3') !== -1 ? 'mp3' : formats[0]);
        $('#agfo-format-help').text($('#agfo-tts-provider').val() === ''
            ? 'Otomatik yönlendirmede anahtarı bulunan sağlayıcıların ortak biçimleri gösterilir.'
            : 'Seçilen sağlayıcının desteklediği biçimler gösterilir.');
    }

    function modelLimit(provider) {
        var model = findModel(provider, providerModel(provider));
        var fallback = provider === 'openai' ? 4096 : (provider === 'minimax' ? 9999 : (provider === 'ema' ? 60000 : 40000));
        return model && Number(model.max_characters) > 0 ? Number(model.max_characters) : fallback;
    }

    function updateTextLimit() {
        var provider = $('#agfo-tts-provider').val();
        var limit;
        if (provider) {
            limit = modelLimit(provider);
        } else {
            var active = ['openai', 'elevenlabs', 'minimax'].filter(function (code) {
                return agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys[code];
            });
            if (!active.length && agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys.ema) active = ['ema'];
            if (!active.length) active = ['openai', 'elevenlabs', 'minimax'];
            limit = Math.min.apply(Math, active.map(modelLimit));
        }
        var cap = provider === 'ema' ? 60000 : 40000;
        limit = Math.max(1, Math.min(cap, limit || cap));
        $('#agfo-tts-text').attr('maxlength', limit);
        $('#agfo-tts-char-limit').text(limit);
        $('#agfo-tts-char-count').text($('#agfo-tts-text').val().length);
    }

    function updateSpeedRange() {
        var provider = $('#agfo-tts-provider').val();
        var usesMiniMax = provider === 'minimax' || (!provider && agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys.minimax);
        var $speed = $('#agfo-tts-speed');
        var min = usesMiniMax ? 0.5 : 0.25;
        var max = usesMiniMax ? 2 : 4;
        if (provider === 'ema') { min = 0.7; max = 1.4; }
        var value = parseFloat($speed.val() || '1');
        if (value < min) value = min;
        if (value > max) value = max;
        $speed.attr({ min: min, max: max }).val(value);
    }

    function updateProviderPanels() {
        var provider = $('#agfo-tts-provider').val();
        $('[data-provider-panel]').each(function () {
            var panelProvider = $(this).data('provider-panel');
            $(this).prop('hidden', provider && provider !== panelProvider);
        });
        $('#agfo-elevenlabs-refresh').prop('disabled', !(agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys.elevenlabs));
        $('#agfo-minimax-refresh').prop('disabled', !(agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys.minimax));
        $('#agfo-ema-refresh').prop('disabled', !(agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys.ema));
        updateSpeedRange();
        updateFormats();
        updateInstructionsState();
        updateElevenModelHelp();
        updateMiniMaxModelHelp();
        updateTextLimit();
    }

    function catalogStatus(provider) {
        var id = '#agfo-' + provider + '-catalog-status';
        var catalog = catalogs[provider] || {};
        var count = (catalog.voices || []).length;
        var hasKey = agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys[provider];
        var notice = catalog.notice || (count ? agfoTtsStudio.messages.catalogReady : agfoTtsStudio.messages.catalogEmpty);
        if (!hasKey) {
            if (provider === 'elevenlabs') notice = 'ElevenLabs API anahtarı eklendiğinde hesabınızdaki sesler otomatik yüklenecek.';
            else if (provider === 'ema') notice = 'EMA servis token’ı Sağlayıcılar ekranında “EMA Lightning (yerel TTS)” alanına girildiğinde kullanılabilir.';
            else notice = 'MiniMax API anahtarı eklendiğinde hesabınızdaki sistem ve özel sesler otomatik yüklenecek.';
        }
        if (provider === 'ema') {
            var state = catalog.healthy === true ? 'is-ready' : (catalog.healthy === false ? 'is-error' : '');
            $(id).attr('class', 'agfo-catalog-status ' + state).text(notice);
            return;
        }
        $(id).attr('class', 'agfo-catalog-status ' + (hasKey && count ? 'is-ready' : '')).text(notice + (count ? ' (' + count + ' ses)' : ''));
    }

    function applyCatalog(provider, catalog) {
        catalogs[provider] = catalog || {};
        populateModels(provider, catalogs[provider]);
        if (provider === 'openai') {
            populateOpenAiVoices(catalogs[provider]);
        } else if (provider === 'ema') {
            catalogStatus('ema');
        } else {
            var searchId = provider === 'elevenlabs' ? '#agfo-tts-voice-elevenlabs-search' : '#agfo-tts-voice-minimax-search';
            populateProviderVoices(provider, catalogs[provider], $(searchId).val());
            if (provider === 'elevenlabs') updateElevenModelHelp();
            else updateMiniMaxModelHelp();
            catalogStatus(provider);
        }
        updateFormats();
        updateTextLimit();
    }

    function loadProviderCatalog(provider, force) {
        if (!agfoTtsStudio.hasKeys || !agfoTtsStudio.hasKeys[provider]) {
            applyCatalog(provider, catalogs[provider] || {});
            return;
        }
        var buttonId = '#agfo-' + provider + '-refresh';
        var statusId = '#agfo-' + provider + '-catalog-status';
        var label = providerLabel(provider);
        var $button = $(buttonId);
        $button.prop('disabled', true);
        $(statusId).attr('class', 'agfo-catalog-status is-loading').text(provider === 'ema' ? 'EMA servisine bağlanılıyor…' : agfoTtsStudio.messages.catalogLoading);
        post('agfo_ai_tts_catalog', { provider: provider, force: force ? 1 : 0 })
            .done(function (response) {
                if (!response || !response.success) {
                    var message = response && response.data && response.data.message ? response.data.message : label + ' seçenekleri alınamadı.';
                    $(statusId).attr('class', 'agfo-catalog-status is-error').text(message);
                    return;
                }
                applyCatalog(provider, response.data);
            })
            .fail(function (xhr) {
                var message = xhr.responseJSON && xhr.responseJSON.data && xhr.responseJSON.data.message
                    ? xhr.responseJSON.data.message : label + ' seçenekleri alınamadı.';
                $(statusId).attr('class', 'agfo-catalog-status is-error').text(message);
            })
            .always(function () { $button.prop('disabled', false); });
    }

    function renderJob(job) {
        $('#agfo-tts-meta').prop('hidden', false);
        $('#agfo-tts-job-id').text(job.job_uuid || '—');
        $('#agfo-tts-job-provider').text(job.provider || '—');
        $('#agfo-tts-job-model').text(job.model || '—');
        $('#agfo-tts-job-cost').text((job.currency || 'USD') + ' ' + Number(job.cost_estimate || 0).toFixed(6));
        var label = agfoTtsStudio.messages[job.status] || job.status;
        setStatus(label, job.status);
        $('#agfo-tts-cancel').prop('hidden', ['queued', 'retry'].indexOf(job.status) === -1);

        if (job.status === 'complete') {
            clearTimeout(timer);
            $('#agfo-tts-output').prop('hidden', false);
            $('#agfo-tts-player').attr('src', job.asset_url || '');
            $('#agfo-tts-download').attr('href', job.download_url || '#');
            $('#agfo-tts-cancel').prop('hidden', true);
            $('#agfo-tts-form :input').prop('disabled', false);
            updateProviderPanels();
            if (job.provider === 'elevenlabs' || job.provider === 'minimax') {
                loadQuota(job.provider, true);
            }
            return;
        }
        if (['failed', 'cancelled'].indexOf(job.status) !== -1) {
            clearTimeout(timer);
            setStatus(job.error_message || label, job.status);
            $('#agfo-tts-cancel').prop('hidden', true);
            $('#agfo-tts-form :input').prop('disabled', false);
            updateProviderPanels();
            return;
        }
        timer = setTimeout(poll, agfoTtsStudio.pollMs);
    }

    function poll() {
        if (!activeJob) return;
        post('agfo_job_status', { job_uuid: activeJob })
            .done(function (response) {
                if (!response || !response.success) {
                    setStatus(response && response.data && response.data.message ? response.data.message : 'İş durumu alınamadı.', 'failed');
                    return;
                }
                renderJob(response.data);
            })
            .fail(function (xhr) {
                var message = xhr.responseJSON && xhr.responseJSON.data && xhr.responseJSON.data.message ? xhr.responseJSON.data.message : 'İş durumu alınamadı.';
                setStatus(message, 'failed');
                timer = setTimeout(poll, agfoTtsStudio.pollMs * 2);
            });
    }

    $('#agfo-tts-text').on('input', function () { $('#agfo-tts-char-count').text($(this).val().length); });
    $('#agfo-tts-provider').on('change', function () {
        updateProviderPanels();
        var provider = $(this).val();
        if (provider === 'elevenlabs' || provider === 'minimax') loadProviderCatalog(provider, false);
    });

    ['openai', 'elevenlabs', 'minimax'].forEach(function (provider) {
        $('#agfo-tts-model-' + provider).on('change', function () {
            toggleManualField('#agfo-tts-model-' + provider, '#agfo-tts-model-' + provider + '-manual');
            if (provider === 'openai') updateOpenAiCompatibility();
            else if (provider === 'elevenlabs') updateElevenModelHelp();
            else updateMiniMaxModelHelp();
        });
    });

    ['elevenlabs', 'minimax'].forEach(function (provider) {
        $('#agfo-tts-voice-' + provider).on('change', function () {
            toggleManualField('#agfo-tts-voice-' + provider, '#agfo-tts-voice-' + provider + '-manual');
            updateProviderVoiceHelp(provider);
        });
        $('#agfo-tts-voice-' + provider + '-search').on('input', function () {
            var term = $(this).val();
            clearTimeout(voiceSearchTimers[provider]);
            voiceSearchTimers[provider] = setTimeout(function () {
                populateProviderVoices(provider, catalogs[provider] || {}, term);
            }, 120);
        });
    });

    $('#agfo-elevenlabs-refresh').on('click', function () { loadProviderCatalog('elevenlabs', true); });
    $('#agfo-minimax-refresh').on('click', function () { loadProviderCatalog('minimax', true); });
    $('#agfo-ema-refresh').on('click', function () { loadProviderCatalog('ema', true); });
    $('#agfo-ema-save').on('click', function () {
        var $button = $(this).prop('disabled', true);
        var $status = $('#agfo-ema-save-status').attr('data-state', 'saving').text('Kaydediliyor…');
        post('agfo_ai_ema_settings', {
            endpoint: $.trim($('#agfo-ema-endpoint').val() || ''),
            lexicon: $('#agfo-ema-lexicon').val() || '',
            pause_ms: $('#agfo-ema-pause').val(),
            paragraph_pause_ms: $('#agfo-ema-paragraph-pause').val(),
            script_enabled: $('#agfo-ema-script').length ? ($('#agfo-ema-script').prop('checked') ? 1 : 0) : '',
            script_model: $('#agfo-ema-script-model').length ? ($('#agfo-ema-script-model').val() || '') : ''
        }).done(function (response) {
            if (!response || !response.success) {
                $status.attr('data-state', 'error').text(response && response.data && response.data.message ? response.data.message : 'EMA ayarları kaydedilemedi.');
                return;
            }
            $status.attr('data-state', 'saved').text(response.data.message + ' Servis: ' + response.data.endpoint + ', sözlük: ' + response.data.lexicon_entries + ' girdi.');
            if (agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys.ema) loadProviderCatalog('ema', true);
        }).fail(function (xhr) {
            $status.attr('data-state', 'error').text(xhr.responseJSON && xhr.responseJSON.data && xhr.responseJSON.data.message ? xhr.responseJSON.data.message : 'EMA ayarları kaydedilemedi.');
        }).always(function () { $button.prop('disabled', false); });
    });
    $('.agfo-quota-refresh').on('click', function () { loadQuota($(this).data('provider'), true); });
    $('#agfo-quota-refresh-all').on('click', function () {
        var $button = $(this).prop('disabled', true);
        $.when(loadQuota('elevenlabs', true), loadQuota('minimax', true)).always(function () {
            $button.prop('disabled', false);
        });
    });

    // NEW 17.10.0: EMA reading script preview. The prepared script replaces the text;
    // it is then spoken as-is (script_ready) and can be edited or undone first.
    var emaScript = { ready: false, original: '' };

    function resetEmaScript() {
        emaScript.ready = false;
        emaScript.original = '';
        $('#agfo-ema-script-undo').prop('hidden', true);
        $('#agfo-ema-script-status').attr('data-state', '').text('');
    }

    $('#agfo-ema-script-preview').on('click', function () {
        var text = $('#agfo-tts-text').val() || '';
        var $button = $(this);
        var $status = $('#agfo-ema-script-status');
        if (!$.trim(text)) { $status.attr('data-state', 'error').text('Önce metni yazın.'); return; }
        if (!(agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys.ema)) { $status.attr('data-state', 'error').text('EMA servis token’ı tanımlı değil.'); return; }
        var original = emaScript.ready ? emaScript.original : text;
        $button.prop('disabled', true);
        $status.attr('data-state', 'working').text('Okuma metni hazırlanıyor… Uzun metinlerde birkaç dakika sürebilir.');
        $.ajax({
            url: agfoTtsStudio.ajaxUrl, method: 'POST', dataType: 'json', timeout: 600000,
            data: { action: 'agfo_ai_ema_script_preview', nonce: agfoTtsStudio.nonce, text: original }
        }).done(function (response) {
            if (!response || !response.success) {
                $status.attr('data-state', 'error').text(response && response.data && response.data.message ? response.data.message : 'Okuma metni hazırlanamadı.');
                return;
            }
            var d = response.data;
            emaScript.ready = true;
            emaScript.original = original;
            $('#agfo-tts-text').val(d.text).trigger('input');
            updateTextLimit();
            $('#agfo-ema-script-undo').prop('hidden', false);
            var note = d.rewritten + '/' + d.chunks + ' bölüm hazırlandı (' + d.model + ')';
            if (d.kept_original) note += '; ' + d.kept_original + ' bölüm denetimden geçmediği için özgün bırakıldı';
            $status.attr('data-state', 'done').text(note + '. Metni kontrol edip düzeltebilir, sonra “Sesi Üret”e basabilirsiniz.');
        }).fail(function (xhr) {
            $status.attr('data-state', 'error').text(xhr.responseJSON && xhr.responseJSON.data && xhr.responseJSON.data.message ? xhr.responseJSON.data.message : 'Okuma metni hazırlanamadı.');
        }).always(function () { $button.prop('disabled', false); });
    });

    $('#agfo-ema-script-undo').on('click', function () {
        if (emaScript.original) $('#agfo-tts-text').val(emaScript.original).trigger('input');
        resetEmaScript();
    });

    $('#agfo-tts-form').on('submit', function (event) {
        event.preventDefault();
        clearTimeout(timer);
        $('#agfo-tts-output').prop('hidden', true);
        var form = this;
        var provider = form.provider.value;
        var models = {};
        var voices = {};
        SPEECH_PROVIDERS.forEach(function (code) {
            if (!$('#agfo-tts-model-' + code).length) return;
            models[code] = providerModel(code);
            voices[code] = providerVoice(code);
        });
        if (provider && !voices[provider]) {
            setStatus(providerLabel(provider) + ' için bir ses seçin veya Voice ID girin.', 'failed');
            return;
        }

        var fallbackVoice = voices.openai || voices.elevenlabs || voices.minimax || '';
        var payload = {
            text: form.text.value,
            voice: provider ? voices[provider] : fallbackVoice,
            provider_voices: voices,
            format: form.format.value,
            speed: form.speed.value,
            instructions: $('#agfo-tts-instructions').prop('disabled') ? '' : form.instructions.value,
            retention_days: form.retention_days.value,
            publish_to_media_library: form.publish_to_media_library.checked,
            visibility: form.publish_to_media_library.checked ? 'public' : 'private',
            title: 'AGFO AI Speech'
        };

        ['language', 'stability', 'similarity_boost', 'style', 'use_speaker_boost'].forEach(function (field) {
            var input = form[field] || null;
            var value = input && !input.disabled ? input.value : '';
            if (value !== '') payload[field] = value;
        });
        var minimaxFields = {
            language_boost: '#agfo-minimax-language-boost', volume: '#agfo-minimax-volume',
            pitch: '#agfo-minimax-pitch', emotion: '#agfo-minimax-emotion',
            sample_rate: '#agfo-minimax-sample-rate', bitrate: '#agfo-minimax-bitrate', channel: '#agfo-minimax-channel'
        };
        Object.keys(minimaxFields).forEach(function (field) {
            var value = $(minimaxFields[field]).val();
            if (value !== '') payload[field] = value;
        });
        if (provider === 'ema') {
            // Explicit EMA choice: the other panels' language hints do not apply.
            payload.language = 'tr';
            delete payload.language_boost;
        }
        if ($('#agfo-ema-pause').length && (provider === 'ema' || (!provider && agfoTtsStudio.hasKeys && agfoTtsStudio.hasKeys.ema))) {
            payload.pause_ms = $('#agfo-ema-pause').val();
            payload.paragraph_pause_ms = $('#agfo-ema-paragraph-pause').val();
            if (emaScript.ready && provider === 'ema') {
                payload.script_ready = 1;
                payload.reading_script = 0;
            } else if ($('#agfo-ema-script').length) {
                payload.reading_script = $('#agfo-ema-script').prop('checked') ? 1 : 0;
            }
        }

        setStatus('İş hazırlanıyor…', 'queued');
        $(form).find(':input').prop('disabled', true);
        post('agfo_job_submit', {
            capability: 'speech_synthesize',
            provider: provider,
            model: provider ? models[provider] : '',
            provider_models: JSON.stringify(models),
            source_plugin: 'agfo-ai-manager',
            idempotency_key: 'studio-' + Date.now() + '-' + Math.random().toString(36).slice(2),
            payload: JSON.stringify(payload)
        }).done(function (response) {
            if (!response || !response.success) {
                $(form).find(':input').prop('disabled', false);
                updateProviderPanels();
                setStatus(response && response.data && response.data.message ? response.data.message : 'İş başlatılamadı.', 'failed');
                return;
            }
            activeJob = response.data.job_uuid;
            renderJob(response.data);
        }).fail(function (xhr) {
            $(form).find(':input').prop('disabled', false);
            updateProviderPanels();
            var message = xhr.responseJSON && xhr.responseJSON.data && xhr.responseJSON.data.message ? xhr.responseJSON.data.message : 'İş başlatılamadı.';
            setStatus(message, 'failed');
        });
    });

    $('#agfo-tts-cancel').on('click', function () {
        if (!activeJob) return;
        post('agfo_job_cancel', { job_uuid: activeJob }).done(function (response) {
            if (response && response.success) {
                clearTimeout(timer);
                setStatus('İş iptal edildi.', 'cancelled');
                $('#agfo-tts-form :input').prop('disabled', false);
                updateProviderPanels();
                $('#agfo-tts-cancel').prop('hidden', true);
            }
        });
    });

    applyCatalog('openai', catalogs.openai || {});
    applyCatalog('elevenlabs', catalogs.elevenlabs || {});
    applyCatalog('minimax', catalogs.minimax || {});
    if ($('#agfo-tts-model-ema').length) applyCatalog('ema', catalogs.ema || {});
    updateProviderPanels();
    loadProviderCatalog('elevenlabs', false);
    loadProviderCatalog('minimax', false);
    loadQuota('elevenlabs', false);
    loadQuota('minimax', false);
})(jQuery);
