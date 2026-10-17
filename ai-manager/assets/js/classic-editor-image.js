(function ($) {
    'use strict';

    var cfg = window.agfoClassicImage || {};
    var lastResult = null;
    var storageKey = 'agfoClassicImagePreferences';

    function post(action, data) {
        return $.ajax({
            url: cfg.ajaxUrl,
            method: 'POST',
            dataType: 'json',
            timeout: 300000,
            data: $.extend({ action: action, nonce: cfg.nonce }, data || {})
        });
    }

    function message(key, fallback) {
        return (cfg.messages && cfg.messages[key]) || fallback;
    }

    function currentPostId() {
        var fromField = parseInt($('#post_ID').val(), 10);
        if (fromField > 0) return fromField;
        return parseInt(cfg.postId, 10) || 0;
    }

    function setStatus(text, state) {
        $('#agfo-classic-image-status')
            .removeClass('is-idle is-working is-complete is-failed')
            .addClass('is-' + (state || 'idle'))
            .text(text);
    }

    function setBusy(busy) {
        $('#agfo-classic-image-generate, #agfo-classic-image-preview-prompt').prop('disabled', !!busy);
        $('#agfo-classic-image-modal').toggleClass('is-busy', !!busy);
    }

    function classicEditorExists() {
        return $('#wp-content-wrap, #postdivrich, textarea#content').length > 0;
    }

    function buildButton(extraClass) {
        return $('<button>', {
            type: 'button',
            'class': 'button agfo-classic-image-open ' + extraClass,
            'data-editor': 'content',
            'aria-haspopup': 'dialog',
            'aria-controls': 'agfo-classic-image-modal'
        }).append($('<span>', {
            'class': 'dashicons dashicons-format-image',
            'aria-hidden': 'true'
        })).append(document.createTextNode(' AI Görsel'));
    }

    function ensureToolbarButton() {
        if ($('.agfo-classic-image-toolbar-button').length) return true;
        if (!classicEditorExists()) return false;

        var $mediaButtons = $('#wp-content-media-buttons, .wp-media-buttons').first();
        if ($mediaButtons.length) {
            $mediaButtons.append(buildButton('agfo-classic-image-toolbar-button agfo-classic-image-open-fallback'));
            return true;
        }
        return false;
    }

    function ensureFeaturedBoxButton() {
        var $box = $('#postimagediv .inside');
        if (!$box.length || $box.find('.agfo-classic-image-featured-button').length) return;
        $box.append(
            $('<p>', { 'class': 'agfo-classic-image-featured-wrap' })
                .append(buildButton('agfo-classic-image-featured-button'))
        );
    }

    function activePreset() {
        var key = $('#agfo-classic-image-preset').val();
        return (cfg.presets && cfg.presets[key]) || null;
    }

    function updatePresetHelp() {
        var preset = activePreset();
        $('#agfo-classic-image-preset-help').text(preset ? preset.description : '');
        $('#agfo-classic-image-title-row').prop('hidden', !(preset && preset.allow_text));
    }

    function applyPresetAspect() {
        var preset = activePreset();
        if (preset && preset.aspect) {
            $('#agfo-classic-image-aspect').val(preset.aspect);
        }
    }

    // CHANGED 17.0.1: the model field is a real select. A <datalist> only offered options that
    // matched the current text, so with "gpt-image-2" filled in no other model was visible.
    var CUSTOM_MODEL = '__custom__';

    function refreshModelList(event) {
        // A provider change resets the model; opening the modal keeps a saved custom id.
        var providerChanged = !!(event && event.type === 'change');
        var provider = $('#agfo-classic-image-provider').val() || '';
        var rows = (cfg.models && cfg.models[provider]) || [];
        var $select = $('#agfo-classic-image-model-select').empty();
        var $input = $('#agfo-classic-image-model');
        var current = $.trim($input.val() || '');

        rows.forEach(function (row) {
            var label = row.label && row.label !== row.id ? row.label + ' — ' + row.id : row.id;
            $select.append($('<option>', { value: row.id, text: label }));
        });
        $select.append($('<option>', { value: CUSTOM_MODEL, text: 'Diğer model (kimliği yazın)…' }));

        var known = rows.some(function (row) { return row.id === current; });
        if (known) {
            $select.val(current);
            $input.prop('hidden', true);
        } else if (current !== '' && (!providerChanged || rows.length === 0)) {
            $select.val(CUSTOM_MODEL);
            $input.prop('hidden', false);
        } else if (rows.length) {
            $select.val(rows[0].id);
            $input.val(rows[0].id).prop('hidden', true);
        } else {
            $select.val(CUSTOM_MODEL);
            $input.val('').prop('hidden', false);
        }
        updateActiveModelLabel();
    }

    function onModelSelect() {
        var value = $('#agfo-classic-image-model-select').val() || '';
        var $input = $('#agfo-classic-image-model');
        if (value === CUSTOM_MODEL) {
            $input.prop('hidden', false).val('').trigger('focus');
        } else {
            $input.prop('hidden', true).val(value);
        }
        updateActiveModelLabel();
    }

    function updateActiveModelLabel() {
        var provider = $('#agfo-classic-image-provider').val() || '';
        var model = $.trim($('#agfo-classic-image-model').val() || '');
        $('#agfo-classic-image-active-model').text(provider && model ? provider + ' · ' + model : 'Yapılandırılmadı');
    }

    function loadPreferences() {
        try {
            return JSON.parse(window.localStorage.getItem(storageKey) || '{}');
        } catch (error) {
            return {};
        }
    }

    function savePreferences() {
        var preferences = {
            preset: $('#agfo-classic-image-preset').val(),
            aspect: $('#agfo-classic-image-aspect').val(),
            provider: $('#agfo-classic-image-provider').val(),
            model: $('#agfo-classic-image-model').val(),
            scope: $('#agfo-classic-image-scope').val(),
            quality: $('#agfo-classic-image-quality').val(),
            language: $('#agfo-classic-image-language').val()
        };
        try { window.localStorage.setItem(storageKey, JSON.stringify(preferences)); } catch (error) { /* optional */ }
    }

    function restorePreferences() {
        var preferences = loadPreferences();
        var map = {
            preset: '#agfo-classic-image-preset',
            aspect: '#agfo-classic-image-aspect',
            provider: '#agfo-classic-image-provider',
            scope: '#agfo-classic-image-scope',
            quality: '#agfo-classic-image-quality',
            language: '#agfo-classic-image-language'
        };
        Object.keys(map).forEach(function (key) {
            var value = preferences[key];
            if (typeof value === 'undefined' || value === null) return;
            var selector = map[key] + ' option[value="' + String(value).replace(/"/g, '\\"') + '"]';
            if ($(selector).length) $(map[key]).val(value);
        });
        if (preferences.model) $('#agfo-classic-image-model').val(preferences.model);
    }

    // CHANGED 16.16.1: Gorunurluk artik hem 'hidden' ozniteligi hem de .is-open
    // sinifi ile surulur. Yalnizca oznitelige guvenmek, bir stil kuralinin display
    // tanimlamasi halinde modali kapatilamaz hale getiriyordu.
    function openModal() {
        restorePreferences();
        refreshModelList();
        updatePresetHelp();
        $('#agfo-classic-image-extra-count').text(String($('#agfo-classic-image-extra').val() || '').length);
        $('#agfo-classic-image-overlay').prop('hidden', false).addClass('is-open');
        $('#agfo-classic-image-modal').prop('hidden', false).addClass('is-open');
        $('body').addClass('agfo-classic-image-modal-open');
        window.setTimeout(function () { $('#agfo-classic-image-extra').trigger('focus'); }, 50);
    }

    // CHANGED 16.16.1: Kapatma her durumda calisir; devam eden bir istek varsa
    // modal kapansa da yanit dondugunde durum satiri guncellenmeye devam eder.
    function closeModal() {
        $('#agfo-classic-image-overlay').prop('hidden', true).removeClass('is-open');
        $('#agfo-classic-image-modal').prop('hidden', true).removeClass('is-open');
        $('body').removeClass('agfo-classic-image-modal-open');
    }

    // CHANGED 16.16.1: Sayfa yuklendiginde modalin kapali oldugu garanti edilir.
    function forceClosedOnLoad() {
        $('#agfo-classic-image-overlay').prop('hidden', true).removeClass('is-open');
        $('#agfo-classic-image-modal').prop('hidden', true).removeClass('is-open');
        $('body').removeClass('agfo-classic-image-modal-open');
    }

    function renderPreview(result) {
        var $preview = $('#agfo-classic-image-preview').empty();
        if (!result || !result.url) {
            $preview.append($('<div>', { 'class': 'agfo-classic-image-placeholder', text: 'Önizleme burada görünecek.' }));
            return;
        }
        $preview.append($('<img>', { src: result.url, alt: 'Üretilen görsel' }));

        var meta = [];
        if (result.provider) meta.push(result.provider);
        if (result.model) meta.push(result.model);
        if (result.width && result.height) meta.push(result.width + '×' + result.height);
        if (result.bytes) meta.push(Math.round(result.bytes / 1024) + ' KB');
        if (result.notes) meta.push(result.notes);
        $('#agfo-classic-image-result-meta').text(meta.join(' · '));

        $('#agfo-classic-image-prompt-view').text(result.prompt || '');
        $('#agfo-classic-image-open-media')
            .attr('href', result.attachment_id ? ('post.php?post=' + result.attachment_id + '&action=edit') : '#')
            .prop('hidden', !result.attachment_id);
    }

    function collectPayload() {
        return {
            post_id: currentPostId(),
            preset: $('#agfo-classic-image-preset').val() || '',
            aspect: $('#agfo-classic-image-aspect').val() || '',
            provider: $('#agfo-classic-image-provider').val() || '',
            model: $.trim($('#agfo-classic-image-model').val() || ''),
            extra: $('#agfo-classic-image-extra').val() || '',
            subject_scope: $('#agfo-classic-image-scope').val() || 'content',
            quality: $('#agfo-classic-image-quality').val() || 'high',
            title_text: $('#agfo-classic-image-title-text').val() || '',
            language: $('#agfo-classic-image-language').val() || ''
        };
    }

    function responseMessage(xhr, fallback) {
        if (xhr && xhr.responseJSON && xhr.responseJSON.data && xhr.responseJSON.data.message) {
            return xhr.responseJSON.data.message;
        }
        if (xhr && xhr.statusText === 'timeout') {
            return 'Sağlayıcı zamanında yanıt vermedi. Daha düşük kalite veya farklı bir model deneyin.';
        }
        return fallback;
    }

    function updateFeaturedMetabox(html, thumbUrl) {
        var $inside = $('#postimagediv .inside');
        if (!$inside.length) return;

        if (html) {
            var $wrap = $inside.find('.agfo-classic-image-featured-wrap').detach();
            $inside.html(html);
            if ($wrap.length) $inside.append($wrap);
            ensureFeaturedBoxButton();
            return;
        }

        var $thumb = $inside.find('#set-post-thumbnail img');
        if ($thumb.length && thumbUrl) $thumb.attr('src', thumbUrl);
    }

    function runGenerate(event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        if ($('#agfo-classic-image-generate').prop('disabled')) return;

        var payload = collectPayload();
        if (!payload.model) {
            setStatus('Bir model seçin ya da model kimliği yazın.', 'failed');
            return;
        }

        savePreferences();
        setBusy(true);
        setStatus(payload.subject_scope === 'prompt' ? message('working', 'Görsel üretiliyor…') : message('briefing', 'Yazının içeriğinden görsel özeti çıkarılıyor…'), 'working');
        $('#agfo-classic-image-set-featured').prop('disabled', true);

        window.setTimeout(function () {
            if ($('#agfo-classic-image-modal').hasClass('is-busy')) {
                setStatus(message('working', 'Görsel üretiliyor…'), 'working');
            }
        }, 4000);

        post('agfo_ai_image_generate', payload).done(function (response) {
            if (!response || !response.success) {
                setStatus(response && response.data && response.data.message ? response.data.message : message('failed', 'Görsel üretilemedi.'), 'failed');
                return;
            }
            lastResult = response.data;
            renderPreview(lastResult);
            $('#agfo-classic-image-set-featured').prop('disabled', !(lastResult.attachment_id && currentPostId() > 0));
            setStatus(message('complete', 'Görsel hazır ve medya kütüphanesine kaydedildi.'), 'complete');
        }).fail(function (xhr) {
            setStatus(responseMessage(xhr, message('failed', 'Görsel üretilemedi.')), 'failed');
        }).always(function () {
            setBusy(false);
        });
    }

    function runPreviewPrompt(event) {
        if (event) event.preventDefault();
        setBusy(true);
        setStatus('Prompt hazırlanıyor…', 'working');

        post('agfo_ai_image_preview_prompt', collectPayload()).done(function (response) {
            if (!response || !response.success) {
                setStatus(response && response.data && response.data.message ? response.data.message : 'Prompt hazırlanamadı.', 'failed');
                return;
            }
            $('#agfo-classic-image-prompt-view').text(response.data.prompt || '').prop('hidden', false);
            setStatus(response.data.notes || 'Prompt hazır.', 'complete');
        }).fail(function (xhr) {
            setStatus(responseMessage(xhr, 'Prompt hazırlanamadı.'), 'failed');
        }).always(function () {
            setBusy(false);
        });
    }

    function runSetFeatured(event) {
        if (event) event.preventDefault();
        if (!lastResult || !lastResult.attachment_id) return;

        var postId = currentPostId();
        if (postId < 1) {
            setStatus('Öne çıkan görsel atamak için yazıyı önce taslak olarak kaydedin.', 'failed');
            return;
        }

        setBusy(true);
        post('agfo_ai_image_set_featured', {
            post_id: postId,
            attachment_id: lastResult.attachment_id
        }).done(function (response) {
            if (!response || !response.success) {
                setStatus(response && response.data && response.data.message ? response.data.message : 'Öne çıkan görsel atanamadı.', 'failed');
                return;
            }
            updateFeaturedMetabox(response.data.html, response.data.thumb_url);
            setStatus(message('featured', 'Öne çıkan görsel olarak atandı.'), 'complete');
        }).fail(function (xhr) {
            setStatus(responseMessage(xhr, 'Öne çıkan görsel atanamadı.'), 'failed');
        }).always(function () {
            setBusy(false);
        });
    }

    $(function () {
        forceClosedOnLoad(); // CHANGED 16.16.1
        ensureToolbarButton();
        ensureFeaturedBoxButton();

        var observer = new MutationObserver(function () {
            ensureToolbarButton();
            ensureFeaturedBoxButton();
        });
        if (document.body) observer.observe(document.body, { childList: true, subtree: true });
        window.setTimeout(function () { observer.disconnect(); }, 10000);

        updatePresetHelp();
        refreshModelList();
    });

    $(document).on('click', '.agfo-classic-image-open', function (event) {
        event.preventDefault();
        openModal();
    });
    $(document).on('click', '.agfo-classic-image-close, #agfo-classic-image-overlay', function (event) {
        event.preventDefault();
        closeModal();
    });
    $(document).on('keydown', function (event) {
        if (event.key === 'Escape' && !$('#agfo-classic-image-modal').prop('hidden')) closeModal();
    });

    $(document).on('change', '#agfo-classic-image-preset', function () {
        updatePresetHelp();
        applyPresetAspect();
    });
    $(document).on('change', '#agfo-classic-image-provider', refreshModelList);
    $(document).on('input change', '#agfo-classic-image-model', updateActiveModelLabel);
    $(document).on('change', '#agfo-classic-image-model-select', onModelSelect);
    $(document).on('input', '#agfo-classic-image-extra', function () {
        $('#agfo-classic-image-extra-count').text(String($(this).val() || '').length);
    });
    $(document).on('click', '#agfo-classic-image-toggle-prompt', function (event) {
        event.preventDefault();
        var $view = $('#agfo-classic-image-prompt-view');
        $view.prop('hidden', !$view.prop('hidden'));
    });

    $(document).on('submit', '#agfo-classic-image-form', runGenerate);
    $(document).on('click', '#agfo-classic-image-generate', runGenerate);
    $(document).on('click', '#agfo-classic-image-preview-prompt', runPreviewPrompt);
    $(document).on('click', '#agfo-classic-image-set-featured', runSetFeatured);
}(jQuery));
