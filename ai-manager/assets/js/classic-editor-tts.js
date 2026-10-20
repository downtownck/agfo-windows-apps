(function ($) {
    'use strict';

    var cfg = window.agfoClassicTts || {};
    var catalogs = cfg.catalogs || {};
    var activeJob = '';
    var activeEditor = 'content';
    var timer = null;
    var voiceTimers = {};
    var output = { url: '', downloadUrl: '', attachmentId: 0 };
    var storageKey = 'agfoClassicTtsPreferences';
    var preferences = loadPreferences();

    function post(action, data) {
        return $.ajax({
            url: cfg.ajaxUrl,
            method: 'POST',
            dataType: 'json',
            data: $.extend({ action: action, nonce: cfg.nonce }, data || {})
        });
    }

    function classicEditorExists() {
        return $('#wp-content-wrap, #postdivrich, textarea#content').length > 0;
    }

    function ensureToolbarButton() {
        var $toolbarButton = $('.agfo-classic-tts-toolbar-button').first();
        if ($toolbarButton.length) {
            $('.agfo-classic-tts-guaranteed-launcher').prop('hidden', true);
            return true;
        }
        if (!classicEditorExists()) return false;

        var $button = $('<button>', {
            type: 'button',
            'class': 'button agfo-classic-tts-open agfo-classic-tts-toolbar-button agfo-classic-tts-open-fallback',
            'data-editor': 'content',
            'aria-haspopup': 'dialog',
            'aria-controls': 'agfo-classic-tts-modal'
        }).append($('<span>', {
            'class': 'dashicons dashicons-controls-volumeon',
            'aria-hidden': 'true'
        })).append(document.createTextNode(' Seslendir'));

        var $mediaButtons = $('#wp-content-media-buttons, .wp-media-buttons').first();
        if ($mediaButtons.length) {
            $mediaButtons.append($button);
            $('.agfo-classic-tts-guaranteed-launcher').prop('hidden', true);
            return true;
        }
        $('.agfo-classic-tts-guaranteed-launcher').prop('hidden', false);
        return false;
    }

    function loadPreferences() {
        try {
            var value = window.localStorage.getItem(storageKey);
            return value ? JSON.parse(value) : {};
        } catch (error) {
            return {};
        }
    }

    function savePreferences() {
        preferences = {
            provider: $('#agfo-classic-tts-provider').val() || '',
            modelOpenai: providerModel('openai'),
            modelElevenlabs: providerModel('elevenlabs'),
            modelMinimax: providerModel('minimax'),
            voiceOpenai: providerVoice('openai'),
            voiceElevenlabs: providerVoice('elevenlabs'),
            voiceMinimax: providerVoice('minimax'),
            emaPause: $('#agfo-classic-tts-ema-pause').val() || '',
            emaParagraphPause: $('#agfo-classic-tts-ema-paragraph-pause').val() || '',
            format: $('#agfo-classic-tts-format').val() || 'mp3',
            speed: $('#agfo-classic-tts-speed').val() || '1',
            instructions: $('#agfo-classic-tts-instructions').val() || '',
            language: $('#agfo-classic-tts-language').val() || '',
            stability: $('#agfo-classic-tts-stability').val() || '',
            similarity: $('#agfo-classic-tts-similarity').val() || '',
            style: $('#agfo-classic-tts-style').val() || '',
            speakerBoost: $('#agfo-classic-tts-speaker-boost').val() || '',
            minimaxLanguage: $('#agfo-classic-tts-minimax-language').val() || 'auto',
            minimaxVolume: $('#agfo-classic-tts-minimax-volume').val() || '1',
            minimaxPitch: $('#agfo-classic-tts-minimax-pitch').val() || '0',
            minimaxEmotion: $('#agfo-classic-tts-minimax-emotion').val() || '',
            minimaxSampleRate: $('#agfo-classic-tts-minimax-sample-rate').val() || '32000',
            minimaxBitrate: $('#agfo-classic-tts-minimax-bitrate').val() || '128000',
            minimaxChannel: $('#agfo-classic-tts-minimax-channel').val() || '1',
            audioEffect: $('#agfo-classic-tts-audio-effect').val() || 'none',
            effectAmount: $('#agfo-classic-tts-effect-amount').val() || '35',
            publish: $('#agfo-classic-tts-publish').prop('checked')
        };
        try { window.localStorage.setItem(storageKey, JSON.stringify(preferences)); } catch (error) { /* optional */ }
    }

    function restoreSimplePreferences() {
        var provider = preferences.provider || cfg.defaultProvider || '';
        if (provider && $('#agfo-classic-tts-provider option[value="' + provider + '"]').length) $('#agfo-classic-tts-provider').val(provider);
        if (preferences.format) $('#agfo-classic-tts-format').val(preferences.format);
        if (preferences.speed) $('#agfo-classic-tts-speed').val(preferences.speed);
        if (typeof preferences.instructions === 'string') $('#agfo-classic-tts-instructions').val(preferences.instructions);
        if (typeof preferences.publish === 'boolean') $('#agfo-classic-tts-publish').prop('checked', preferences.publish);
        if (preferences.stability !== undefined) $('#agfo-classic-tts-stability').val(preferences.stability);
        if (preferences.similarity !== undefined) $('#agfo-classic-tts-similarity').val(preferences.similarity);
        if (preferences.style !== undefined) $('#agfo-classic-tts-style').val(preferences.style);
        if (preferences.speakerBoost !== undefined) $('#agfo-classic-tts-speaker-boost').val(preferences.speakerBoost);
        if (preferences.minimaxLanguage !== undefined) $('#agfo-classic-tts-minimax-language').val(preferences.minimaxLanguage);
        if (preferences.minimaxVolume !== undefined) $('#agfo-classic-tts-minimax-volume').val(preferences.minimaxVolume);
        if (preferences.minimaxPitch !== undefined) $('#agfo-classic-tts-minimax-pitch').val(preferences.minimaxPitch);
        if (preferences.minimaxEmotion !== undefined) $('#agfo-classic-tts-minimax-emotion').val(preferences.minimaxEmotion);
        if (preferences.minimaxSampleRate !== undefined) $('#agfo-classic-tts-minimax-sample-rate').val(preferences.minimaxSampleRate);
        if (preferences.minimaxBitrate !== undefined) $('#agfo-classic-tts-minimax-bitrate').val(preferences.minimaxBitrate);
        if (preferences.minimaxChannel !== undefined) $('#agfo-classic-tts-minimax-channel').val(preferences.minimaxChannel);
        if (preferences.audioEffect !== undefined) $('#agfo-classic-tts-audio-effect').val(preferences.audioEffect);
        if (preferences.effectAmount !== undefined) $('#agfo-classic-tts-effect-amount').val(preferences.effectAmount);
        if (preferences.emaPause) $('#agfo-classic-tts-ema-pause').val(preferences.emaPause);
        if (preferences.emaParagraphPause) $('#agfo-classic-tts-ema-paragraph-pause').val(preferences.emaParagraphPause);
    }

    var emaScript = { ready: false, original: '' };

    function resetEmaScript() {
        emaScript.ready = false;
        emaScript.original = '';
        $('#agfo-classic-tts-ema-script-undo').prop('hidden', true);
        $('#agfo-classic-tts-ema-script-status').attr('data-state', '').text('');
    }

    var PROVIDER_LABELS = { openai: 'OpenAI', elevenlabs: 'ElevenLabs', minimax: 'MiniMax', ema: 'EMA Lightning' };
    var SPEECH_PROVIDERS = ['openai', 'elevenlabs', 'minimax', 'ema'];

    function providerLabel(provider) {
        return PROVIDER_LABELS[provider] || provider;
    }

    function setStatus(text, state) {
        $('#agfo-classic-tts-status').attr('class', 'agfo-classic-tts-status is-' + (state || 'idle')).text(text);
    }

    function responseMessage(xhr, fallback) {
        return xhr && xhr.responseJSON && xhr.responseJSON.data && xhr.responseJSON.data.message
            ? xhr.responseJSON.data.message : fallback;
    }

    function formatQuotaNumber(value) {
        return new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 }).format(Number(value || 0));
    }

    function renderCompactQuota(provider, data) {
        var $item = $('.agfo-classic-tts-quota-item[data-quota-provider="' + provider + '"]');
        var suffix = data.exact ? 'kalan kredi · canlı' : 'tahmini kalan · yalnız AGFO kullanımı';
        $item.removeClass('is-error').addClass(data.exact ? 'is-live' : 'is-local');
        $item.find('.agfo-classic-tts-quota-value').text(formatQuotaNumber(data.remaining));
        $item.find('small').text(suffix + (data.reset_at ? ' · yenilenme ' + data.reset_at : ''));
        $item.attr('title', data.note || '');
    }

    function compactQuotaError(provider, message) {
        var $item = $('.agfo-classic-tts-quota-item[data-quota-provider="' + provider + '"]');
        $item.removeClass('is-live is-local').addClass('is-error');
        $item.find('.agfo-classic-tts-quota-value').text('—');
        $item.find('small').text(message || 'Kota bilgisi alınamadı.');
    }

    function loadCompactQuota(provider, force) {
        if (!cfg.hasKeys || !cfg.hasKeys[provider]) {
            compactQuotaError(provider, providerLabel(provider) + ' anahtarı yok.');
            return $.Deferred().resolve().promise();
        }
        return post('agfo_ai_provider_quota', { provider: provider, force: force ? 1 : 0 })
            .done(function (response) {
                if (!response || !response.success) {
                    compactQuotaError(provider, response && response.data && response.data.message ? response.data.message : 'Kota bilgisi alınamadı.');
                    return;
                }
                renderCompactQuota(provider, response.data);
            })
            .fail(function (xhr) { compactQuotaError(provider, responseMessage(xhr, 'Kota bilgisi alınamadı.')); });
    }

    function optionExists($select, value) {
        return $select.find('option').filter(function () { return this.value === value; }).length > 0;
    }

    function selectedOrManual(selectSelector, manualSelector) {
        var value = $(selectSelector).val() || '';
        return value === '__manual__' ? $.trim($(manualSelector).val() || '') : value;
    }

    function toggleManual(selectSelector, manualSelector) {
        var manual = $(selectSelector).val() === '__manual__';
        $(manualSelector).prop('hidden', !manual).prop('required', manual);
        if (manual) $(manualSelector).trigger('focus');
    }

    function providerModel(provider) {
        return selectedOrManual('#agfo-classic-tts-model-' + provider, '#agfo-classic-tts-model-' + provider + '-manual');
    }

    function providerVoice(provider) {
        return selectedOrManual('#agfo-classic-tts-voice-' + provider, '#agfo-classic-tts-voice-' + provider + '-manual');
    }

    function findModel(provider, modelId) {
        var models = (catalogs[provider] && catalogs[provider].models) || [];
        for (var i = 0; i < models.length; i += 1) if (models[i].id === modelId) return models[i];
        return null;
    }

    function preferenceModel(provider) {
        if (provider === 'openai') return preferences.modelOpenai || 'gpt-4o-mini-tts';
        if (provider === 'elevenlabs') return preferences.modelElevenlabs || 'eleven_multilingual_v2';
        if (provider === 'ema') return 'ema-lightning';
        return preferences.modelMinimax || 'speech-2.8-hd';
    }

    function defaultModel(provider) {
        if (provider === 'openai') return 'gpt-4o-mini-tts';
        if (provider === 'elevenlabs') return 'eleven_multilingual_v2';
        if (provider === 'ema') return 'ema-lightning';
        return 'speech-2.8-hd';
    }

    function populateModels(provider, catalog) {
        var $select = $('#agfo-classic-tts-model-' + provider);
        if (!$select.length) return;
        if (provider === 'ema') return; // Single fixed model rendered server-side.
        var preferred = preferenceModel(provider);
        $select.empty();
        (catalog.models || []).forEach(function (model) {
            var label = String(model.name || model.id || '');
            if (model.recommended) label += ' — önerilen';
            if (model.requires_alpha_access) label += ' — özel erişim';
            $('<option>').val(model.id).text(label).attr('data-description', model.description || '').appendTo($select);
        });
        $('<option>').val('__manual__').text('Özel / yeni model kimliği…').appendTo($select);
        if (preferred && optionExists($select, preferred)) {
            $select.val(preferred);
        } else if (preferred && optionExists($select, '__manual__')) {
            $select.val('__manual__');
            $('#agfo-classic-tts-model-' + provider + '-manual').val(preferred);
        } else if (optionExists($select, defaultModel(provider))) {
            $select.val(defaultModel(provider));
        } else {
            $select.prop('selectedIndex', 0);
        }
        toggleManual('#agfo-classic-tts-model-' + provider, '#agfo-classic-tts-model-' + provider + '-manual');
    }

    function populateOpenAiVoices(catalog) {
        var $select = $('#agfo-classic-tts-voice-openai');
        var preferred = preferences.voiceOpenai || 'coral';
        $select.empty();
        (catalog.voices || []).forEach(function (voice) {
            var label = String(voice.name || voice.id || '');
            if (voice.description) label += ' — ' + voice.description;
            $('<option>').val(voice.id).text(label).appendTo($select);
        });
        if (optionExists($select, preferred)) $select.val(preferred);
        else if (optionExists($select, 'coral')) $select.val('coral');
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
        return [voice.name, voice.id, voice.category, voice.description, labels.language, labels.locale,
            labels.accent, labels.gender, labels.age, labels.use_case, labels.description, labels.created_time]
            .filter(Boolean).join(' ').toLocaleLowerCase('tr-TR');
    }

    function voiceLabel(voice) {
        var labels = voice.labels || {};
        var parts = [String(voice.name || voice.id || '')];
        [labels.language, labels.accent, labels.gender, labels.age].forEach(function (item) {
            if (item && parts.indexOf(String(item)) === -1) parts.push(String(item));
        });
        return parts.join(' — ');
    }

    function preferredVoice(provider) {
        return provider === 'elevenlabs' ? preferences.voiceElevenlabs : preferences.voiceMinimax;
    }

    function populateProviderVoices(provider, catalog, searchTerm) {
        var $select = $('#agfo-classic-tts-voice-' + provider);
        if (!$select.length) return;
        var preferred = preferredVoice(provider) || providerVoice(provider);
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
        if (!count) $('<option>').val('').text(term ? 'Aramayla eşleşen ses bulunamadı' : 'Bu hesap için ses bulunamadı').appendTo($select);
        Object.keys(groups).sort().forEach(function (category) {
            var $group = $('<optgroup>').attr('label', categoryLabel(category));
            groups[category].forEach(function (voice) {
                $('<option>').val(voice.id).text(voiceLabel(voice)).attr('data-description', voice.description || '').appendTo($group);
            });
            $group.appendTo($select);
        });
        $('<option>').val('__manual__').text('Voice ID\'yi manuel gir…').appendTo($select);
        if (preferred && optionExists($select, preferred)) {
            $select.val(preferred);
        } else if (preferred && optionExists($select, '__manual__')) {
            $select.val('__manual__');
            $('#agfo-classic-tts-voice-' + provider + '-manual').val(preferred);
        } else if (count) {
            $select.find('option:not([value="__manual__"])').first().prop('selected', true);
        }
        toggleManual('#agfo-classic-tts-voice-' + provider, '#agfo-classic-tts-voice-' + provider + '-manual');
        updateProviderVoiceHelp(provider);
    }

    function populateLanguages(model) {
        var $select = $('#agfo-classic-tts-language');
        var preferred = preferences.language || $select.val() || '';
        $select.empty().append($('<option>').val('').text('Otomatik algıla'));
        ((model && model.languages) || []).forEach(function (language) {
            $('<option>').val(language.id).text(language.name || language.id).appendTo($select);
        });
        if (preferred && optionExists($select, preferred)) $select.val(preferred);
    }

    function updateOpenAiCompatibility() {
        var model = findModel('openai', providerModel('openai'));
        var allowed = model && model.voice_ids ? model.voice_ids : [];
        var $voice = $('#agfo-classic-tts-voice-openai');
        $voice.find('option').each(function () {
            var supported = !allowed.length || allowed.indexOf(this.value) !== -1;
            $(this).prop('disabled', !supported).prop('hidden', !supported);
        });
        if ($voice.find('option:selected').prop('disabled')) $voice.find('option:not(:disabled)').first().prop('selected', true);
        $('#agfo-classic-tts-openai-model-help').text(model ? (model.description || '') : 'Özel model kimliği kullanılacak.');
        updateInstructions();
        updateTextLimit();
    }

    function updateElevenModelHelp() {
        var model = findModel('elevenlabs', providerModel('elevenlabs'));
        var help = model ? (model.description || '') : 'Özel model kimliği kullanılacak.';
        if (model && model.max_characters) help += (help ? ' ' : '') + 'Sınır: ' + model.max_characters + ' karakter.';
        $('#agfo-classic-tts-eleven-model-help').text(help);
        populateLanguages(model);
        $('#agfo-classic-tts-style').prop('disabled', !!model && model.can_use_style === false);
        $('#agfo-classic-tts-speaker-boost').prop('disabled', !!model && model.can_use_speaker_boost === false);
        updateTextLimit();
    }

    function updateMiniMaxModelHelp() {
        var model = findModel('minimax', providerModel('minimax'));
        var help = model ? (model.description || '') : 'Özel model kimliği kullanılacak.';
        if (model && model.max_characters) help += (help ? ' ' : '') + 'Sınır: ' + model.max_characters + ' karakter.';
        $('#agfo-classic-tts-minimax-model-help').text(help);
        updateTextLimit();
    }

    function updateProviderVoiceHelp(provider) {
        var $selected = $('#agfo-classic-tts-voice-' + provider + ' option:selected');
        var text = $selected.attr('data-description') || 'Ses adı gösterilir; API çağrısında Voice ID kullanılır.';
        if ($selected.val() && $selected.val() !== '__manual__') text += ' Voice ID: ' + $selected.val();
        $('#' + (provider === 'elevenlabs' ? 'agfo-classic-tts-eleven-voice-help' : 'agfo-classic-tts-minimax-voice-help')).text(text);
    }

    function updateInstructions() {
        var provider = $('#agfo-classic-tts-provider').val();
        var model = findModel('openai', providerModel('openai'));
        var enabled = provider === 'openai' && !!(model && model.supports_instructions);
        $('#agfo-classic-tts-instructions').prop('disabled', !enabled);
        var help;
        if (enabled) help = 'Ton, duygu, aksan ve okuma biçimini doğal dille tarif edebilirsiniz.';
        else if (provider === 'elevenlabs') help = 'ElevenLabs okuma biçimi ses seçimi ve gelişmiş ses ayarlarıyla belirlenir.';
        else if (provider === 'minimax') help = 'MiniMax okuma biçimi ses, duygu, perde, ses düzeyi ve hız ayarlarıyla belirlenir.';
        else if (provider === 'ema') help = 'EMA Lightning talimat almaz; okumayı hız, duraklama ve telaffuz sözlüğüyle ayarlayın.';
        else help = 'Seçilen OpenAI modeli okuma talimatını desteklemiyor.';
        $('#agfo-classic-tts-instructions-help').text(help);
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

    function updateFormats() {
        var provider = $('#agfo-classic-tts-provider').val();
        var formats = providerFormats(provider || 'elevenlabs');
        var $select = $('#agfo-classic-tts-format');
        var current = $select.val();
        $select.find('option').each(function () {
            var supported = formats.indexOf(this.value) !== -1;
            $(this).prop('disabled', !supported).prop('hidden', !supported);
        });
        if (formats.indexOf(current) === -1) $select.val(formats.indexOf('mp3') !== -1 ? 'mp3' : formats[0]);
    }

    function modelLimit(provider) {
        var model = findModel(provider, providerModel(provider));
        var fallback = provider === 'openai' ? 4096 : (provider === 'minimax' ? 9999 : (provider === 'ema' ? 60000 : 40000));
        return model && Number(model.max_characters) > 0 ? Number(model.max_characters) : fallback;
    }

    function updateTextLimit() {
        var provider = $('#agfo-classic-tts-provider').val() || cfg.defaultProvider || 'elevenlabs';
        var cap = provider === 'ema' ? 60000 : 40000;
        var limit = Math.max(1, Math.min(cap, modelLimit(provider)));
        $('#agfo-classic-tts-text').attr('maxlength', limit);
        $('#agfo-classic-tts-char-limit').text(limit);
        $('#agfo-classic-tts-char-count').text($('#agfo-classic-tts-text').val().length);
    }

    function updateSpeedRange() {
        var provider = $('#agfo-classic-tts-provider').val();
        var $speed = $('#agfo-classic-tts-speed');
        var min = provider === 'minimax' ? 0.5 : (provider === 'ema' ? 0.7 : 0.25);
        var max = provider === 'minimax' ? 2 : (provider === 'ema' ? 1.4 : 4);
        var value = parseFloat($speed.val() || '1');
        if (value < min) value = min;
        if (value > max) value = max;
        $speed.attr({ min: min, max: max }).val(value);
    }

    function updateAudioEffect() {
        var effectConfig = cfg.audioEffects || {};
        var available = !!effectConfig.available;
        var $effect = $('#agfo-classic-tts-audio-effect');
        var $amount = $('#agfo-classic-tts-effect-amount');
        var effect = $effect.val() || 'none';

        if (!available && effect !== 'none') {
            effect = 'none';
            $effect.val('none');
        }

        var active = available && effect !== 'none';
        var amount = Math.max(0, Math.min(100, parseInt($amount.val() || '35', 10)));
        $amount.val(amount).prop('disabled', !active);
        $('#agfo-classic-tts-effect-amount-output').text(amount + '%');

        if (!available) {
            $('#agfo-classic-tts-effect-help').text(effectConfig.reason || 'FFmpeg kullanılamıyor; yalnız kuru ses üretilebilir.');
            return;
        }
        if (!active) {
            $('#agfo-classic-tts-effect-help').text('Efekt uygulanmaz; sağlayıcının ürettiği kuru ses korunur.');
            return;
        }

        $('#agfo-classic-tts-format').val('mp3');
        $('#agfo-classic-tts-effect-help').text('Efekt işlenmiş kalıcı çıktı MP3 olarak oluşturulur. Bu ayar gerçek zamanlı değildir; üretilen dosyaya uygulanır.');
    }

    function updateProviderPanels() {
        var provider = $('#agfo-classic-tts-provider').val();
        $('#agfo-classic-tts-modal [data-provider-panel]').each(function () {
            $(this).prop('hidden', $(this).data('provider-panel') !== provider);
        });
        $('#agfo-classic-tts-refresh-eleven').prop('disabled', !(cfg.hasKeys && cfg.hasKeys.elevenlabs));
        $('#agfo-classic-tts-refresh-minimax').prop('disabled', !(cfg.hasKeys && cfg.hasKeys.minimax));
        $('#agfo-classic-tts-refresh-ema').prop('disabled', !(cfg.hasKeys && cfg.hasKeys.ema));
        if ($('#agfo-classic-tts-model-ema').length) $('#agfo-classic-tts-submit').prop('disabled', provider === 'ema' && !(cfg.hasKeys && cfg.hasKeys.ema));
        updateSpeedRange();
        updateFormats();
        updateAudioEffect();
        updateInstructions();
        updateElevenModelHelp();
        updateMiniMaxModelHelp();
        updateTextLimit();
    }

    function statusSelector(provider) {
        if (provider === 'elevenlabs') return '#agfo-classic-tts-eleven-status';
        return '#agfo-classic-tts-' + provider + '-status';
    }

    function refreshSelector(provider) {
        if (provider === 'elevenlabs') return '#agfo-classic-tts-refresh-eleven';
        return '#agfo-classic-tts-refresh-' + provider;
    }

    function catalogStatus(provider) {
        var id = statusSelector(provider);
        var catalog = catalogs[provider] || {};
        var count = (catalog.voices || []).length;
        var hasKey = cfg.hasKeys && cfg.hasKeys[provider];
        var text = catalog.notice || (count ? cfg.messages.catalogReady : cfg.messages.catalogEmpty);
        if (!hasKey) text = providerLabel(provider) + (provider === 'ema' ? ' servis token’ı bulunamadı.' : ' API anahtarı bulunamadı.');
        if (provider === 'ema') {
            var state = catalog.healthy === true ? 'is-ready' : (catalog.healthy === false ? 'is-error' : '');
            $(id).attr('class', 'agfo-classic-tts-catalog-status ' + state).text(text);
            return;
        }
        $(id).attr('class', 'agfo-classic-tts-catalog-status ' + (hasKey && count ? 'is-ready' : '')).text(text + (count ? ' (' + count + ' ses)' : ''));
    }

    function applyCatalog(provider, catalog) {
        catalogs[provider] = catalog || {};
        populateModels(provider, catalogs[provider]);
        if (provider === 'openai') {
            populateOpenAiVoices(catalogs[provider]);
        } else if (provider === 'ema') {
            catalogStatus('ema');
        } else {
            var searchId = provider === 'elevenlabs' ? '#agfo-classic-tts-voice-search' : '#agfo-classic-tts-voice-minimax-search';
            populateProviderVoices(provider, catalogs[provider], $(searchId).val());
            if (provider === 'elevenlabs') updateElevenModelHelp(); else updateMiniMaxModelHelp();
            catalogStatus(provider);
        }
        updateProviderPanels();
    }

    function loadProviderCatalog(provider, force) {
        if (!cfg.hasKeys || !cfg.hasKeys[provider]) {
            catalogStatus(provider);
            return;
        }
        var statusId = statusSelector(provider);
        var buttonId = refreshSelector(provider);
        var label = providerLabel(provider);
        var $button = $(buttonId);
        $button.prop('disabled', true);
        $(statusId).attr('class', 'agfo-classic-tts-catalog-status is-loading').text(provider === 'ema' ? 'EMA servisine bağlanılıyor…' : (cfg.messages.catalogLoading || 'Seçenekler yükleniyor…'));
        post('agfo_ai_tts_catalog', { provider: provider, force: force ? 1 : 0 })
            .done(function (response) {
                if (!response || !response.success) {
                    var message = response && response.data && response.data.message ? response.data.message : label + ' seçenekleri alınamadı.';
                    $(statusId).attr('class', 'agfo-classic-tts-catalog-status is-error').text(message);
                    return;
                }
                applyCatalog(provider, response.data);
            })
            .fail(function (xhr) {
                $(statusId).attr('class', 'agfo-classic-tts-catalog-status is-error').text(responseMessage(xhr, label + ' seçenekleri alınamadı.'));
            })
            .always(function () { $button.prop('disabled', false); });
    }

    function htmlToPlainText(html) {
        var prepared = String(html || '')
            .replace(/<br\s*\/?>/gi, '\n').replace(/<\/p\s*>/gi, '\n\n').replace(/<\/div\s*>/gi, '\n')
            .replace(/<\/h[1-6]\s*>/gi, '\n\n').replace(/<li[^>]*>/gi, '• ').replace(/<\/li\s*>/gi, '\n');
        var node = document.createElement('div');
        node.innerHTML = prepared;
        return (node.textContent || node.innerText || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
    }

    function editorText(selectionOnly) {
        var editor = window.tinymce && window.tinymce.get ? window.tinymce.get(activeEditor) : null;
        if (editor && !editor.isHidden()) {
            return htmlToPlainText(selectionOnly ? editor.selection.getContent({ format: 'html' }) : editor.getContent({ format: 'html' }));
        }
        var textarea = document.getElementById(activeEditor);
        if (!textarea) return '';
        var value = textarea.value || '';
        if (selectionOnly && typeof textarea.selectionStart === 'number' && textarea.selectionEnd > textarea.selectionStart) {
            value = value.substring(textarea.selectionStart, textarea.selectionEnd);
        } else if (selectionOnly) return '';
        return htmlToPlainText(value);
    }

    function fillFromEditor(selectionOnly) {
        var text = editorText(selectionOnly);
        if (!text && selectionOnly) {
            text = editorText(false);
            $('#agfo-classic-tts-source-note').text('Seçili metin bulunamadı; tüm sayfa içeriği alındı.');
        } else {
            $('#agfo-classic-tts-source-note').text(selectionOnly ? 'Seçili metin alındı.' : 'Tüm sayfa içeriği alındı.');
        }
        $('#agfo-classic-tts-text').val(text).trigger('input');
    }

    function openModal(editorId) {
        activeEditor = editorId || 'content';
        $('#agfo-classic-tts-editor-id').val(activeEditor);
        resetEmaScript();
        output = { url: '', downloadUrl: '', attachmentId: 0 };
        $('#agfo-classic-tts-player').prop('hidden', true).attr('src', '');
        $('#agfo-classic-tts-download, #agfo-classic-tts-insert, #agfo-classic-tts-cancel').prop('hidden', true);
        setStatus('Henüz iş başlatılmadı.', 'idle');
        fillFromEditor(true);
        $('#agfo-classic-tts-overlay, #agfo-classic-tts-modal').prop('hidden', false);
        $('body').addClass('agfo-classic-tts-opened');
        updateProviderPanels();
        var provider = $('#agfo-classic-tts-provider').val();
        if (provider === 'elevenlabs' || provider === 'minimax') loadProviderCatalog(provider, false);
        loadCompactQuota('elevenlabs', false);
        loadCompactQuota('minimax', false);
        window.setTimeout(function () { $('#agfo-classic-tts-text').trigger('focus'); }, 50);
    }

    function closeModal() {
        $('#agfo-classic-tts-overlay, #agfo-classic-tts-modal').prop('hidden', true);
        $('body').removeClass('agfo-classic-tts-opened');
    }

    function setFormBusy(busy) {
        $('#agfo-classic-tts-form :input, #agfo-classic-tts-submit').prop('disabled', busy);
        if (!busy) updateProviderPanels();
    }

    function renderJob(job) {
        var label = (cfg.messages && cfg.messages[job.status]) || job.status;
        setStatus(label, job.status);
        $('#agfo-classic-tts-cancel').prop('hidden', ['queued', 'retry'].indexOf(job.status) === -1);
        if (job.status === 'complete') {
            window.clearTimeout(timer);
            setFormBusy(false);
            output.url = job.attachment_url || '';
            output.downloadUrl = job.download_url || '';
            output.attachmentId = Number(job.attachment_id || 0);
            $('#agfo-classic-tts-player').attr('src', job.asset_url || '').prop('hidden', false);
            $('#agfo-classic-tts-download').attr('href', job.download_url || '#').prop('hidden', !job.download_url);
            $('#agfo-classic-tts-insert').prop('hidden', !output.url);
            $('#agfo-classic-tts-cancel').prop('hidden', true);
            if ($('#agfo-classic-tts-publish').prop('checked') && !output.url) {
                setStatus('Ses üretildi; ancak Medya Kütüphanesi kopyası oluşturulamadığı için editöre eklenemiyor.', 'failed');
            }
            if (job.provider === 'elevenlabs' || job.provider === 'minimax') {
                loadCompactQuota(job.provider, true);
            }
            return;
        }
        if (['failed', 'cancelled'].indexOf(job.status) !== -1) {
            window.clearTimeout(timer);
            setFormBusy(false);
            setStatus(job.error_message || label, job.status);
            $('#agfo-classic-tts-cancel').prop('hidden', true);
            return;
        }
        timer = window.setTimeout(poll, cfg.pollMs || 2500);
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
                setStatus(responseMessage(xhr, 'İş durumu alınamadı; yeniden denenecek.'), 'failed');
                timer = window.setTimeout(poll, (cfg.pollMs || 2500) * 2);
            });
    }

    function insertAtCursor(text) {
        var editor = window.tinymce && window.tinymce.get ? window.tinymce.get(activeEditor) : null;
        if (editor && !editor.isHidden()) {
            editor.focus();
            editor.execCommand('mceInsertContent', false, text);
            editor.save();
            return true;
        }
        var textarea = document.getElementById(activeEditor);
        if (!textarea) return false;
        var start = typeof textarea.selectionStart === 'number' ? textarea.selectionStart : textarea.value.length;
        var end = typeof textarea.selectionEnd === 'number' ? textarea.selectionEnd : start;
        var before = textarea.value.substring(0, start);
        var after = textarea.value.substring(end);
        var prefix = before && !/\n\s*$/.test(before) ? '\n\n' : '';
        var suffix = after && !/^\s*\n/.test(after) ? '\n\n' : '';
        textarea.value = before + prefix + text + suffix + after;
        textarea.selectionStart = textarea.selectionEnd = (before + prefix + text).length;
        $(textarea).trigger('input').trigger('change');
        return true;
    }

    function insertAudio() {
        if (!output.url) {
            setStatus('Kalıcı medya URL’si bulunamadı. Üretimde Medya Kütüphanesi seçeneğini açık bırakın.', 'failed');
            return;
        }
        var safeUrl = String(output.url).replace(/"/g, '&quot;');
        var shortcode = '[audio src="' + safeUrl + '"][/audio]';
        window.wpActiveEditor = activeEditor;
        if (insertAtCursor(shortcode)) {
            setStatus('Ses oynatıcı sayfa editörüne eklendi. Sayfayı güncelleyerek kaydedin.', 'complete');
            $('#agfo-classic-tts-insert').text('Tekrar Ekle');
        } else setStatus('Editör bulunamadı; ses eklenemedi.', 'failed');
    }

    $(function () {
        ensureToolbarButton();
        window.setTimeout(ensureToolbarButton, 400);
        window.setTimeout(ensureToolbarButton, 1200);
        if (window.MutationObserver && !$('.agfo-classic-tts-toolbar-button').length) {
            var observer = new MutationObserver(function () { if (ensureToolbarButton()) observer.disconnect(); });
            observer.observe(document.body, { childList: true, subtree: true });
            window.setTimeout(function () { observer.disconnect(); }, 5000);
        }

        $(document).on('click', '.agfo-classic-tts-open', function () { openModal($(this).data('editor') || 'content'); });
        $(document).on('agfo:tts:open-with-text', function (event, payload) {
            payload = payload || {};
            openModal(payload.editorId || 'content');
            if (typeof payload.text === 'string') {
                $('#agfo-classic-tts-text').val(payload.text).trigger('input');
            }
            if (payload.note) $('#agfo-classic-tts-source-note').text(payload.note);
        });
        $(document).on('click', '.agfo-classic-tts-close, #agfo-classic-tts-overlay', closeModal);
        $(document).on('keydown', function (event) { if (event.key === 'Escape' && !$('#agfo-classic-tts-modal').prop('hidden')) closeModal(); });
        $('#agfo-classic-tts-use-selection').on('click', function () { fillFromEditor(true); });
        $('#agfo-classic-tts-use-all').on('click', function () { fillFromEditor(false); });
        $('#agfo-classic-tts-text').on('input', updateTextLimit);
        $('#agfo-classic-tts-audio-effect').on('change', updateAudioEffect);
        $('#agfo-classic-tts-effect-amount').on('input change', updateAudioEffect);
        $('#agfo-classic-tts-format').on('change', function () {
            if (($('#agfo-classic-tts-audio-effect').val() || 'none') !== 'none') updateAudioEffect();
        });
        $('#agfo-classic-tts-provider').on('change', function () {
            updateProviderPanels();
            var provider = $(this).val();
            if (provider === 'elevenlabs' || provider === 'minimax') loadProviderCatalog(provider, false);
        });

        ['openai', 'elevenlabs', 'minimax'].forEach(function (provider) {
            $('#agfo-classic-tts-model-' + provider).on('change', function () {
                toggleManual('#agfo-classic-tts-model-' + provider, '#agfo-classic-tts-model-' + provider + '-manual');
                if (provider === 'openai') updateOpenAiCompatibility();
                else if (provider === 'elevenlabs') updateElevenModelHelp();
                else updateMiniMaxModelHelp();
            });
        });
        ['elevenlabs', 'minimax'].forEach(function (provider) {
            $('#agfo-classic-tts-voice-' + provider).on('change', function () {
                toggleManual('#agfo-classic-tts-voice-' + provider, '#agfo-classic-tts-voice-' + provider + '-manual');
                updateProviderVoiceHelp(provider);
            });
            var searchId = provider === 'elevenlabs' ? '#agfo-classic-tts-voice-search' : '#agfo-classic-tts-voice-minimax-search';
            $(searchId).on('input', function () {
                var term = $(this).val();
                window.clearTimeout(voiceTimers[provider]);
                voiceTimers[provider] = window.setTimeout(function () { populateProviderVoices(provider, catalogs[provider] || {}, term); }, 120);
            });
        });
        $('#agfo-classic-tts-refresh-eleven').on('click', function () { loadProviderCatalog('elevenlabs', true); });
        $('#agfo-classic-tts-refresh-minimax').on('click', function () { loadProviderCatalog('minimax', true); });
        $('#agfo-classic-tts-refresh-ema').on('click', function () { loadProviderCatalog('ema', true); });
        $('#agfo-classic-tts-ema-script-preview').on('click', function () {
            var $button = $(this);
            var $status = $('#agfo-classic-tts-ema-script-status');
            var text = $('#agfo-classic-tts-text').val() || '';
            if (!$.trim(text)) { $status.attr('data-state', 'error').text('Önce metni alın.'); return; }
            if (!(cfg.hasKeys && cfg.hasKeys.ema)) { $status.attr('data-state', 'error').text('EMA servis token’ı tanımlı değil.'); return; }
            var original = emaScript.ready ? emaScript.original : text;
            $button.prop('disabled', true);
            $status.attr('data-state', 'working').text('Okuma metni hazırlanıyor… Uzun metinlerde birkaç dakika sürebilir.');
            $.ajax({
                url: cfg.ajaxUrl, method: 'POST', dataType: 'json', timeout: 600000,
                data: { action: 'agfo_ai_ema_script_preview', nonce: cfg.nonce, text: original }
            }).done(function (response) {
                if (!response || !response.success) {
                    $status.attr('data-state', 'error').text(response && response.data && response.data.message ? response.data.message : 'Okuma metni hazırlanamadı.');
                    return;
                }
                var d = response.data;
                emaScript.ready = true;
                emaScript.original = original;
                $('#agfo-classic-tts-text').val(d.text).trigger('input');
                $('#agfo-classic-tts-ema-script-undo').prop('hidden', false);
                var note = d.rewritten + '/' + d.chunks + ' bölüm hazırlandı';
                if (d.kept_original) note += '; ' + d.kept_original + ' bölüm özgün bırakıldı';
                $status.attr('data-state', 'done').text(note + '. Metni kontrol edip düzeltebilirsiniz.');
            }).fail(function (xhr) {
                $status.attr('data-state', 'error').text(responseMessage(xhr, 'Okuma metni hazırlanamadı.'));
            }).always(function () { $button.prop('disabled', false); });
        });
        $('#agfo-classic-tts-ema-script-undo').on('click', function () {
            if (emaScript.original) $('#agfo-classic-tts-text').val(emaScript.original).trigger('input');
            resetEmaScript();
        });
        $('#agfo-classic-tts-use-selection, #agfo-classic-tts-use-all').on('click', resetEmaScript);
        $('#agfo-classic-tts-refresh-quota').on('click', function () {
            var $button = $(this).prop('disabled', true);
            $.when(loadCompactQuota('elevenlabs', true), loadCompactQuota('minimax', true)).always(function () { $button.prop('disabled', false); });
        });
        $('#agfo-classic-tts-insert').on('click', insertAudio);

        $('#agfo-classic-tts-form').on('submit', function (event) {
            event.preventDefault();
            window.clearTimeout(timer);
            var provider = $('#agfo-classic-tts-provider').val() || '';
            var models = {};
            var voices = {};
            SPEECH_PROVIDERS.forEach(function (code) {
                if (!$('#agfo-classic-tts-model-' + code).length) return;
                models[code] = providerModel(code);
                voices[code] = code === 'ema' ? ($('#agfo-classic-tts-voice-ema').val() || 'ema') : providerVoice(code);
            });
            var text = $('#agfo-classic-tts-text').val() || '';
            var publish = $('#agfo-classic-tts-publish').prop('checked');
            if (!provider) { setStatus('Kullanılabilir TTS sağlayıcısı bulunamadı.', 'failed'); return; }
            if (!$.trim(text)) { setStatus('Seslendirilecek metin boş olamaz.', 'failed'); return; }
            if (provider === 'ema' && !(cfg.hasKeys && cfg.hasKeys.ema)) { setStatus('EMA servis token’ı tanımlı değil: AGFO AI › Sağlayıcılar › EMA Lightning (yerel TTS) alanına token girin.', 'failed'); return; }
            if (!voices[provider]) { setStatus(providerLabel(provider) + ' için bir ses seçin veya Voice ID girin.', 'failed'); return; }

            savePreferences();
            output = { url: '', downloadUrl: '', attachmentId: 0 };
            $('#agfo-classic-tts-player, #agfo-classic-tts-download, #agfo-classic-tts-insert').prop('hidden', true);
            $('#agfo-classic-tts-insert').text('Editöre Ekle');
            var title = 'AGFO TTS' + (cfg.postTitle ? ' - ' + cfg.postTitle : '');
            var payload = {
                text: text,
                voice: voices[provider],
                provider_voices: voices,
                format: $('#agfo-classic-tts-format').val() || 'mp3',
                speed: $('#agfo-classic-tts-speed').val() || '1',
                instructions: $('#agfo-classic-tts-instructions').prop('disabled') ? '' : ($('#agfo-classic-tts-instructions').val() || ''),
                audio_effect: $('#agfo-classic-tts-audio-effect').val() || 'none',
                effect_amount: $('#agfo-classic-tts-effect-amount').val() || '35',
                retention_days: 365,
                publish_to_media_library: publish,
                visibility: publish ? 'public' : 'private',
                title: title
            };
            // EMA ignores the other providers' tuning; a hidden ElevenLabs language or
            // MiniMax language boost must not make a Turkish job look foreign.
            if (provider === 'ema') {
                payload.language = 'tr';
                payload.pause_ms = $('#agfo-classic-tts-ema-pause').val() || '';
                payload.paragraph_pause_ms = $('#agfo-classic-tts-ema-paragraph-pause').val() || '';
                if (emaScript.ready) {
                    payload.script_ready = 1;
                    payload.reading_script = 0;
                } else if ($('#agfo-classic-tts-ema-script').length) {
                    payload.reading_script = $('#agfo-classic-tts-ema-script').prop('checked') ? 1 : 0;
                }
            } else ['language', 'stability', 'similarity_boost', 'style', 'use_speaker_boost'].forEach(function (field) {
                var id = field === 'similarity_boost' ? 'similarity' : (field === 'use_speaker_boost' ? 'speaker-boost' : field);
                var $input = $('#agfo-classic-tts-' + id);
                if ($input.length && !$input.prop('disabled') && $input.val() !== '') payload[field] = $input.val();
            });
            var minimaxFields = provider === 'ema' ? {} : {
                language_boost: '#agfo-classic-tts-minimax-language', volume: '#agfo-classic-tts-minimax-volume',
                pitch: '#agfo-classic-tts-minimax-pitch', emotion: '#agfo-classic-tts-minimax-emotion',
                sample_rate: '#agfo-classic-tts-minimax-sample-rate', bitrate: '#agfo-classic-tts-minimax-bitrate',
                channel: '#agfo-classic-tts-minimax-channel'
            };
            Object.keys(minimaxFields).forEach(function (field) {
                var value = $(minimaxFields[field]).val();
                if (value !== '') payload[field] = value;
            });

            setStatus('İş hazırlanıyor…', 'queued');
            setFormBusy(true);
            post('agfo_job_submit', {
                capability: 'speech_synthesize',
                provider: provider,
                model: models[provider],
                provider_models: JSON.stringify(models),
                source_plugin: 'agfo-ai-classic-editor',
                idempotency_key: 'classic-editor-' + (cfg.postId || 0) + '-' + Date.now() + '-' + Math.random().toString(36).slice(2),
                payload: JSON.stringify(payload)
            }).done(function (response) {
                if (!response || !response.success) {
                    setFormBusy(false);
                    setStatus(response && response.data && response.data.message ? response.data.message : 'İş başlatılamadı.', 'failed');
                    return;
                }
                activeJob = response.data.job_uuid;
                renderJob(response.data);
            }).fail(function (xhr) {
                setFormBusy(false);
                setStatus(responseMessage(xhr, 'İş başlatılamadı.'), 'failed');
            });
        });

        $('#agfo-classic-tts-cancel').on('click', function () {
            if (!activeJob) return;
            post('agfo_job_cancel', { job_uuid: activeJob }).done(function (response) {
                if (response && response.success) {
                    window.clearTimeout(timer);
                    setFormBusy(false);
                    setStatus('İş iptal edildi.', 'cancelled');
                    $('#agfo-classic-tts-cancel').prop('hidden', true);
                }
            });
        });

        restoreSimplePreferences();
        applyCatalog('openai', catalogs.openai || {});
        applyCatalog('elevenlabs', catalogs.elevenlabs || {});
        applyCatalog('minimax', catalogs.minimax || {});
        if ($('#agfo-classic-tts-model-ema').length) applyCatalog('ema', catalogs.ema || {});
        updateProviderPanels();
    });
})(jQuery);
