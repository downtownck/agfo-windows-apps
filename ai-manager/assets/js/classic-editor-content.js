(function ($) {
    'use strict';

    var cfg = window.agfoClassicContent || {};
    var activeEditor = 'content';
    var sourceScope = 'all';
    var selectionBookmark = null;
    var textareaSelection = null;
    var undoStack = [];
    var resultData = null;
    var storageKey = 'agfoClassicContentPreferences';
    // NEW 17.3.0: one-click translation state.
    var translateKey = 'agfoClassicContentTranslateLang';
    var translateTemplate = cfg.translateTemplate || 'translate_polish';
    var quickTranslate = false;
    var defaultModelText = '';

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
        if ($('.agfo-classic-content-toolbar-button').length) return true;
        if (!classicEditorExists()) return false;

        var $button = $('<button>', {
            type: 'button',
            'class': 'button agfo-classic-content-open agfo-classic-content-toolbar-button agfo-classic-content-open-fallback',
            'data-editor': 'content',
            'aria-haspopup': 'dialog',
            'aria-controls': 'agfo-classic-content-modal'
        }).append($('<span>', {
            'class': 'dashicons dashicons-edit-page',
            'aria-hidden': 'true'
        })).append(document.createTextNode(' AI Düzenle'));

        var $mediaButtons = $('#wp-content-media-buttons, .wp-media-buttons').first();
        if ($mediaButtons.length) {
            $mediaButtons.append($button);
            ensureTranslateControls($mediaButtons);
            return true;
        }
        return false;
    }

    // NEW 17.3.0: fallback for screens where the media_buttons hook did not print the translate group.
    function ensureTranslateControls($container) {
        if ($('.agfo-classic-translate-group').length || !$container || !$container.length) return;
        var $select = $('<select>', { 'class': 'agfo-classic-translate-lang', 'aria-label': 'Hedef dil' });
        var languages = cfg.languages || { 'Türkçe': 'Türkçe', 'English': 'English' };
        Object.keys(languages).forEach(function (value) {
            $select.append($('<option>', { value: value, text: languages[value] }));
        });
        var $group = $('<span>', { 'class': 'agfo-classic-translate-group', 'data-editor': 'content' })
            .append($('<button>', {
                type: 'button',
                'class': 'button agfo-classic-translate-open',
                'data-editor': 'content',
                'aria-haspopup': 'dialog',
                'aria-controls': 'agfo-classic-content-modal',
                title: 'Seçili metni (seçim yoksa tüm içeriği) hedef dile çevirir'
            }).append($('<span>', { 'class': 'dashicons dashicons-translation', 'aria-hidden': 'true' })).append(document.createTextNode(' Çevir')))
            .append($select);
        $container.append($group);
        restoreTranslateLanguage();
    }

    function loadTranslateLanguage() {
        try { return window.localStorage.getItem(translateKey) || ''; } catch (error) { return ''; }
    }

    function restoreTranslateLanguage() {
        var saved = loadTranslateLanguage();
        $('.agfo-classic-translate-lang').each(function () {
            var $select = $(this);
            if (saved && $select.find('option').filter(function () { return this.value === saved; }).length) {
                $select.val(saved);
            } else if (!saved && $select.find('option[value="English"]').length) {
                // Most pages are written in Turkish, so English is the useful first target.
                $select.val('English');
            }
        });
    }

    function saveTranslateLanguage(value) {
        try { window.localStorage.setItem(translateKey, value); } catch (error) { /* optional */ }
        $('.agfo-classic-translate-lang').val(value);
    }

    function updateModelLabel() {
        var $name = $('#agfo-classic-content-model-name');
        if (!$name.length) return;
        if (defaultModelText === '') defaultModelText = $name.text();
        var isTranslate = ($('#agfo-classic-content-template').val() || '') === translateTemplate;
        if (isTranslate && cfg.translateModel) {
            $('#agfo-classic-content-model-label').text('Çeviri modeli');
            $name.text([cfg.translateProvider, cfg.translateModel].filter(Boolean).join(' · '));
        } else {
            $('#agfo-classic-content-model-label').text('Aktif model');
            $name.text(defaultModelText);
        }
        if (!$('#agfo-classic-content-submit').data('busy')) {
            $('#agfo-classic-content-submit').text(isTranslate ? 'Çevir' : 'Yeniden Yaz');
        }
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
            template: $('#agfo-classic-content-template').val() || 'rewrite_balanced',
            language: $('#agfo-classic-content-language').val() || 'Türkçe',
            tone: $('#agfo-classic-content-tone').val() || 'Doğal ve dengeli',
            audience: $('#agfo-classic-content-audience').val() || 'Genel okuyucu',
            length: $('#agfo-classic-content-length').val() || 'Benzer uzunluk',
            preserve: $('#agfo-classic-content-preserve').prop('checked'),
            fromScratch: $('#agfo-classic-content-from-scratch').prop('checked')
        };
        try { window.localStorage.setItem(storageKey, JSON.stringify(preferences)); } catch (error) { /* optional */ }
    }

    function restorePreferences() {
        var preferences = loadPreferences();
        Object.keys(preferences).forEach(function (key) {
            var selectors = {
                template: '#agfo-classic-content-template',
                language: '#agfo-classic-content-language',
                tone: '#agfo-classic-content-tone',
                audience: '#agfo-classic-content-audience',
                length: '#agfo-classic-content-length'
            };
            if (selectors[key] && $(selectors[key] + ' option[value="' + String(preferences[key]).replace(/"/g, '\\"') + '"]').length) {
                $(selectors[key]).val(preferences[key]);
            }
        });
        if (typeof preferences.preserve === 'boolean') $('#agfo-classic-content-preserve').prop('checked', preferences.preserve);
        if (typeof preferences.fromScratch === 'boolean') $('#agfo-classic-content-from-scratch').prop('checked', preferences.fromScratch);
        updateTemplateHelp();
    }

    function getEditor() {
        return window.tinymce && window.tinymce.get ? window.tinymce.get(activeEditor) : null;
    }

    function editorSource(selectionOnly) {
        var editor = getEditor();
        if (editor && !editor.isHidden()) {
            if (selectionOnly) {
                selectionBookmark = editor.selection.getBookmark(2, true);
                return editor.selection.getContent({ format: 'html' }) || '';
            }
            selectionBookmark = null;
            return editor.getContent({ format: 'html' }) || '';
        }

        var textarea = document.getElementById(activeEditor);
        if (!textarea) return '';
        var value = textarea.value || '';
        if (selectionOnly && typeof textarea.selectionStart === 'number' && textarea.selectionEnd > textarea.selectionStart) {
            textareaSelection = { start: textarea.selectionStart, end: textarea.selectionEnd };
            return value.substring(textarea.selectionStart, textarea.selectionEnd);
        }
        textareaSelection = null;
        return selectionOnly ? '' : value;
    }

    function fillFromEditor(selectionOnly) {
        var source = editorSource(selectionOnly);
        sourceScope = selectionOnly && source ? 'selection' : 'all';
        if (!source && selectionOnly) source = editorSource(false);
        $('#agfo-classic-content-source').val(source).trigger('input');
        return source;
    }

    function setStatus(text, state) {
        $('#agfo-classic-content-status').attr('class', 'agfo-classic-content-status is-' + (state || 'idle')).text(text);
    }

    function responseMessage(xhr, fallback) {
        if (xhr && xhr.responseJSON && xhr.responseJSON.data) {
            if (xhr.responseJSON.data.message) return xhr.responseJSON.data.message;
            if (typeof xhr.responseJSON.data === 'string') return xhr.responseJSON.data;
        }
        return fallback;
    }

    function updateTemplateHelp() {
        var key = $('#agfo-classic-content-template').val() || '';
        var row = cfg.templates && cfg.templates[key] ? cfg.templates[key] : null;
        $('#agfo-classic-content-template-help').text(row ? row.description : '');
        updateModelLabel();
    }

    function setBusy(busy) {
        $('#agfo-classic-content-form :input, #agfo-classic-content-submit').prop('disabled', busy);
        // CHANGED 17.3.0: the idle label follows the selected template (Çevir / Yeniden Yaz).
        $('#agfo-classic-content-submit').data('busy', busy);
        if (busy) {
            $('#agfo-classic-content-submit').text('İşleniyor…');
        } else {
            updateModelLabel();
        }
        $('.agfo-classic-translate-open').prop('disabled', busy);
    }

    function setResult(html, data) {
        resultData = data || null;
        $('#agfo-classic-content-result').html(html || '');
        var meta = '';
        if (data) {
            meta = (data.input_words || 0) + ' → ' + (data.output_words || 0) + ' kelime';
            if (data.provider || data.model) meta += ' · ' + [data.provider, data.model].filter(Boolean).join(' / ');
            if (data.model_fallback) {
                meta += ' · model fallback';
            } else if (data.temperature_retry) {
                meta += ' · aynı model / parametre retry';
            } else {
                meta += ' · doğrudan';
            }
            if (data.short_brief_mode) meta += ' · kısa brief geliştirildi';
            if (data.translation_route) meta += ' · çeviri modeli';
            if (data.truncated) meta += ' · ⚠ kesildi';
            if (data.page_context_used) {
                meta += ' · sayfa bağlamı';
                if (data.context_meta_count) meta += ': ' + data.context_meta_count + ' meta';
            }
        }
        $('#agfo-classic-content-result-meta').text(meta);
        var hasResult = $.trim($('#agfo-classic-content-result').text()) !== '';
        $('#agfo-classic-content-copy, #agfo-classic-content-speak, #agfo-classic-content-insert, #agfo-classic-content-apply').prop('disabled', !hasResult);
    }

    function openModal(editorId) {
        activeEditor = editorId || 'content';
        quickTranslate = false;
        $('#agfo-classic-content-editor-id').val(activeEditor);
        restorePreferences();
        setResult('', null);
        setStatus((cfg.messages && cfg.messages.idle) || 'Henüz işlem yok.', 'idle');
        fillFromEditor(true);
        $('#agfo-classic-content-overlay, #agfo-classic-content-modal').prop('hidden', false);
        $('body').addClass('agfo-classic-content-opened');
        window.setTimeout(function () { $('#agfo-classic-content-source').trigger('focus'); }, 50);
    }

    function closeModal() {
        $('#agfo-classic-content-overlay, #agfo-classic-content-modal').prop('hidden', true);
        $('body').removeClass('agfo-classic-content-opened');
    }

    function snapshotEditor() {
        var editor = getEditor();
        if (editor && !editor.isHidden()) {
            return { type: 'tinymce', content: editor.getContent({ format: 'html' }) };
        }
        var textarea = document.getElementById(activeEditor);
        return textarea ? { type: 'textarea', content: textarea.value || '' } : null;
    }

    function restoreSnapshot(snapshot) {
        if (!snapshot) return false;
        var editor = getEditor();
        if (snapshot.type === 'tinymce' && editor && !editor.isHidden()) {
            editor.setContent(snapshot.content || '');
            editor.undoManager.add();
            return true;
        }
        var textarea = document.getElementById(activeEditor);
        if (textarea) {
            textarea.value = snapshot.content || '';
            $(textarea).trigger('change');
            return true;
        }
        return false;
    }

    function currentResultHtml() {
        var container = document.createElement('div');
        container.innerHTML = $('#agfo-classic-content-result').html() || '';
        Array.prototype.slice.call(container.querySelectorAll('script,style,iframe,object,embed,form,input,button')).forEach(function (node) {
            node.remove();
        });
        Array.prototype.slice.call(container.querySelectorAll('*')).forEach(function (node) {
            Array.prototype.slice.call(node.attributes || []).forEach(function (attribute) {
                var name = String(attribute.name || '').toLowerCase();
                var value = String(attribute.value || '');
                if (name.indexOf('on') === 0 || name === 'style' || (name === 'href' && /^\s*javascript:/i.test(value))) {
                    node.removeAttribute(attribute.name);
                }
            });
        });
        return $.trim(container.innerHTML || '');
    }

    function applyToEditor(mode) {
        var html = currentResultHtml();
        if (!html) return;
        var snapshot = snapshotEditor();
        if (snapshot) {
            undoStack.push(snapshot);
            if (undoStack.length > 10) undoStack.shift();
        }

        var editor = getEditor();
        if (editor && !editor.isHidden()) {
            editor.focus();
            if (mode === 'replace' && sourceScope === 'selection' && selectionBookmark) {
                try { editor.selection.moveToBookmark(selectionBookmark); } catch (error) { /* use current caret */ }
                editor.selection.setContent(html);
            } else if (mode === 'replace') {
                editor.setContent(html);
            } else {
                editor.setContent(editor.getContent({ format: 'html' }) + '\n' + html);
            }
            editor.undoManager.add();
            // CHANGED 16.17.2: Keep TinyMCE, the hidden textarea and WordPress dirty-state
            // listeners synchronized immediately after replace/insert.
            try { editor.save(); } catch (error) { /* TinyMCE will still retain the edit */ }
            try { editor.fire('change'); } catch (error) { /* optional editor event */ }
            $('#' + activeEditor).trigger('input').trigger('change');
        } else {
            var textarea = document.getElementById(activeEditor);
            if (!textarea) return;
            var value = textarea.value || '';
            if (mode === 'replace' && sourceScope === 'selection' && textareaSelection) {
                textarea.value = value.substring(0, textareaSelection.start) + html + value.substring(textareaSelection.end);
            } else if (mode === 'replace') {
                textarea.value = html;
            } else {
                textarea.value = value + '\n\n' + html;
            }
            $(textarea).trigger('input').trigger('change');
        }
        $('#agfo-classic-content-undo').prop('disabled', undoStack.length === 0);
        setStatus((cfg.messages && cfg.messages.applied) || 'Sonuç editöre uygulandı.', 'complete');
    }

    function htmlToPlainText(html) {
        var node = document.createElement('div');
        node.innerHTML = html || '';
        return (node.textContent || node.innerText || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
    }

    // NEW 17.3.0: open the studio in translation mode and start immediately.
    function openTranslate(editorId, language) {
        activeEditor = editorId || 'content';
        $('#agfo-classic-content-editor-id').val(activeEditor);
        restorePreferences();
        if ($('#agfo-classic-content-template option[value="' + translateTemplate + '"]').length) {
            $('#agfo-classic-content-template').val(translateTemplate);
        }
        if (language && $('#agfo-classic-content-language option').filter(function () { return this.value === language; }).length) {
            $('#agfo-classic-content-language').val(language);
        }
        $('#agfo-classic-content-length').val('Benzer uzunluk');
        $('#agfo-classic-content-from-scratch').prop('checked', false);
        $('#agfo-classic-content-preserve').prop('checked', true);
        $('#agfo-classic-content-extra').val('');
        updateTemplateHelp();
        setResult('', null);
        fillFromEditor(true);
        $('#agfo-classic-content-overlay, #agfo-classic-content-modal').prop('hidden', false);
        $('body').addClass('agfo-classic-content-opened');
        quickTranslate = true;
        runTransform(null);
    }

    $(function () {
        ensureToolbarButton();
        restoreTranslateLanguage();
        var observer = new MutationObserver(function () { ensureToolbarButton(); });
        if (document.body) observer.observe(document.body, { childList: true, subtree: true });
        window.setTimeout(function () { observer.disconnect(); }, 10000);
        updateTemplateHelp();
    });

    $(document).on('click', '.agfo-classic-content-open', function () { openModal($(this).data('editor') || 'content'); });
    $(document).on('click', '.agfo-classic-translate-open', function (event) {
        event.preventDefault();
        var $group = $(this).closest('.agfo-classic-translate-group');
        var language = $group.find('.agfo-classic-translate-lang').val() || 'English';
        saveTranslateLanguage(language);
        openTranslate($(this).data('editor') || 'content', language);
    });
    $(document).on('change', '.agfo-classic-translate-lang', function () { saveTranslateLanguage($(this).val() || 'English'); });
    $(document).on('click', '.agfo-classic-content-close, #agfo-classic-content-overlay', closeModal);
    $(document).on('keydown', function (event) {
        if (event.key === 'Escape' && !$('#agfo-classic-content-modal').prop('hidden')) closeModal();
    });

    function runTransform(event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        // CHANGED 17.3.0: consume the one-click flag first so an early return cannot leak it.
        var skipSave = quickTranslate;
        quickTranslate = false;
        if ($('#agfo-classic-content-submit').prop('disabled')) return;

        var source = $('#agfo-classic-content-source').val() || '';
        if (!$.trim($('<div>').html(source).text())) {
            setStatus((cfg.messages && cfg.messages.noSource) || 'Dönüştürülecek metin bulunamadı.', 'failed');
            return;
        }
        // CHANGED 17.3.0: a one-click translation must not overwrite the studio's saved preferences.
        var isTranslate = ($('#agfo-classic-content-template').val() || '') === translateTemplate;
        if (!skipSave) savePreferences();
        setBusy(true);
        setStatus(isTranslate ? ((cfg.messages && cfg.messages.translating) || 'Çevriliyor…') : ((cfg.messages && cfg.messages.working) || 'İçerik dönüştürülüyor…'), 'working');
        setResult('', null);

        post('agfo_ai_content_transform', {
            source_html: source,
            template: $('#agfo-classic-content-template').val() || 'rewrite_balanced',
            language: $('#agfo-classic-content-language').val() || 'Türkçe',
            tone: $('#agfo-classic-content-tone').val() || 'Doğal ve dengeli',
            audience: $('#agfo-classic-content-audience').val() || 'Genel okuyucu',
            length: $('#agfo-classic-content-length').val() || 'Benzer uzunluk',
            extra: $('#agfo-classic-content-extra').val() || '',
            preserve_facts: $('#agfo-classic-content-preserve').prop('checked') ? 1 : 0,
            from_scratch: $('#agfo-classic-content-from-scratch').prop('checked') ? 1 : 0,
            post_id: parseInt($('#post_ID').val() || cfg.postId || 0, 10) || 0,
            current_title: $('#title').val() || ''
        }).done(function (response) {
            if (!response || !response.success) {
                setStatus(response && response.data && response.data.message ? response.data.message : ((cfg.messages && cfg.messages.failed) || 'İçerik dönüştürülemedi.'), 'failed');
                return;
            }
            setResult(response.data.html || '', response.data);
            if (response.data.truncated) {
                setStatus((cfg.messages && cfg.messages.truncated) || 'Sonuç uzunluk sınırına takıldı.', 'failed');
            } else if (response.data.translation) {
                setStatus((cfg.messages && cfg.messages.translated) || 'Çeviri hazır.', 'complete');
            } else {
                setStatus((cfg.messages && cfg.messages.complete) || 'Yeni metin hazır.', 'complete');
            }
        }).fail(function (xhr) {
            setStatus(responseMessage(xhr, (cfg.messages && cfg.messages.failed) || 'İçerik dönüştürülemedi.'), 'failed');
        }).always(function () { setBusy(false); });
    }

    $(document).on('change', '#agfo-classic-content-template', updateTemplateHelp);
    $(document).on('click', '#agfo-classic-content-use-selection', function (event) {
        event.preventDefault();
        fillFromEditor(true);
    });
    $(document).on('click', '#agfo-classic-content-use-all', function (event) {
        event.preventDefault();
        fillFromEditor(false);
        sourceScope = 'all';
    });
    $(document).on('input', '#agfo-classic-content-source', function () {
        $('#agfo-classic-content-source-count').text(String($(this).val() || '').length);
    });
    $(document).on('submit', '#agfo-classic-content-form', runTransform);
    $(document).on('click', '#agfo-classic-content-submit', runTransform);

    $(document).on('click', '#agfo-classic-content-copy', function (event) {
        event.preventDefault();
        var html = currentResultHtml();
        var plain = htmlToPlainText(html);
        if (!plain) return;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(plain).then(function () { setStatus((cfg.messages && cfg.messages.copied) || 'Sonuç panoya kopyalandı.', 'complete'); });
        } else {
            var $temp = $('<textarea>').val(plain).appendTo('body').select();
            document.execCommand('copy');
            $temp.remove();
            setStatus((cfg.messages && cfg.messages.copied) || 'Sonuç panoya kopyalandı.', 'complete');
        }
    });

    $(document).on('click', '#agfo-classic-content-apply', function (event) { event.preventDefault(); applyToEditor('replace'); });
    $(document).on('click', '#agfo-classic-content-insert', function (event) { event.preventDefault(); applyToEditor('insert'); });
    $(document).on('click', '#agfo-classic-content-undo', function (event) {
        event.preventDefault();
        var snapshot = undoStack.pop();
        if (restoreSnapshot(snapshot)) {
            setStatus((cfg.messages && cfg.messages.undo) || 'Son editör değişikliği geri alındı.', 'complete');
        }
        $(this).prop('disabled', undoStack.length === 0);
    });

    $(document).on('click', '#agfo-classic-content-speak', function (event) {
        event.preventDefault();
        var text = resultData && resultData.plain_text ? resultData.plain_text : htmlToPlainText(currentResultHtml());
        if (!text) return;
        closeModal();
        $(document).trigger('agfo:tts:open-with-text', [{ editorId: activeEditor, text: text, note: 'İçerik Stüdyosu sonucu seslendirmeye aktarıldı.' }]);
    });
}(jQuery));
