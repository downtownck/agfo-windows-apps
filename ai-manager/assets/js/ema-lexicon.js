(function ($) {
    'use strict';

    var cfg = window.agfoEmaLexicon || {};
    var rows = [];
    var page = 1;
    var SOURCE_LABELS = { base: 'Hazır', added: 'Eklendi', edited: 'Değiştirildi', removed: 'Kaldırıldı' };

    function setStatus(text, state) {
        $('#agfo-lex-status').attr('class', 'agfo-status is-' + (state || 'idle')).text(text);
    }

    function call(op, data) {
        return $.ajax({
            url: cfg.ajaxUrl,
            method: 'POST',
            dataType: 'json',
            timeout: 90000,
            data: $.extend({ action: 'agfo_ai_ema_lexicon', nonce: cfg.nonce, op: op }, data || {})
        });
    }

    function errorText(xhr, response, fallback) {
        if (response && response.data && response.data.message) return response.data.message;
        if (xhr && xhr.responseJSON && xhr.responseJSON.data && xhr.responseJSON.data.message) return xhr.responseJSON.data.message;
        return fallback;
    }

    function filtered() {
        var term = $.trim($('#agfo-lex-search').val() || '').toLocaleLowerCase('tr-TR');
        var filter = $('#agfo-lex-filter').val() || '';
        return rows.filter(function (r) {
            if (filter === 'mine' && r.source !== 'added' && r.source !== 'edited') return false;
            if (filter === 'removed' && r.source !== 'removed') return false;
            if (filter === 'base' && r.source !== 'base') return false;
            if (!term) return true;
            return String(r.word).toLocaleLowerCase('tr-TR').indexOf(term) !== -1 ||
                String(r.reading).toLocaleLowerCase('tr-TR').indexOf(term) !== -1;
        });
    }

    function render() {
        var list = filtered();
        var per = cfg.perPage || 50;
        var pages = Math.max(1, Math.ceil(list.length / per));
        if (page > pages) page = pages;
        var $body = $('#agfo-lex-rows').empty();
        if (!list.length) {
            $body.append($('<tr>').append($('<td colspan="4">').text(rows.length ? 'Eşleşen kayıt yok.' : 'Sözlük boş.')));
        }
        list.slice((page - 1) * per, page * per).forEach(function (r) {
            var $tr = $('<tr>').attr('data-word', r.word).toggleClass('agfo-lex-row-removed', r.source === 'removed');
            $('<td>').text(r.word).appendTo($tr);
            var $input = $('<input type="text" maxlength="160" class="agfo-lex-row-reading">').val(r.reading).prop('disabled', r.source === 'removed');
            $('<td>').append($input).appendTo($tr);
            var $badge = $('<span class="agfo-lex-badge">').addClass('is-' + r.source).text(SOURCE_LABELS[r.source] || r.source);
            if (r.source === 'edited' && r.base_reading) $badge.attr('title', 'Hazır okunuş: ' + r.base_reading);
            $('<td>').append($badge).appendTo($tr);
            var $act = $('<td>');
            $('<button type="button" class="button button-small agfo-lex-row-listen">').text('Dinle').appendTo($act);
            if (r.source === 'removed') {
                $('<button type="button" class="button button-small agfo-lex-row-restore">').text('Geri al').appendTo($act);
            } else {
                $('<button type="button" class="button button-small agfo-lex-row-save">').text('Kaydet').appendTo($act);
                $('<button type="button" class="button button-small button-link-delete agfo-lex-row-delete">').text('Sil').appendTo($act);
                if (r.source === 'edited') {
                    $('<button type="button" class="button-link agfo-lex-row-restore">').text('Hazıra dön').appendTo($act);
                }
            }
            $act.appendTo($tr);
            $body.append($tr);
        });
        $('#agfo-lex-page').text(page + ' / ' + pages + ' · ' + list.length + ' kayıt');
        $('#agfo-lex-prev').prop('disabled', page <= 1);
        $('#agfo-lex-next').prop('disabled', page >= pages);
    }

    function load() {
        $('#agfo-lex-reload').prop('disabled', true);
        return call('list').done(function (response) {
            if (!response || !response.success) {
                setStatus(errorText(null, response, 'Sözlük alınamadı.'), 'failed');
                $('#agfo-lex-rows').html('<tr><td colspan="4"></td></tr>').find('td').text(errorText(null, response, 'Sözlük alınamadı.'));
                return;
            }
            rows = response.data.entries || [];
            var mine = rows.filter(function (r) { return r.source === 'added' || r.source === 'edited'; }).length;
            var removed = rows.filter(function (r) { return r.source === 'removed'; }).length;
            $('#agfo-lex-counts').text('— ' + response.data.active + ' etkin kayıt · ' + mine + ' eklenen/değiştirilen · ' + removed + ' kaldırılan');
            render();
        }).fail(function (xhr) {
            var msg = errorText(xhr, null, 'Sözlük alınamadı.');
            setStatus(msg, 'failed');
            $('#agfo-lex-rows').html('<tr><td colspan="4"></td></tr>').find('td').text(msg);
        }).always(function () { $('#agfo-lex-reload').prop('disabled', false); });
    }

    function save(word, reading, $button) {
        word = $.trim(word || '');
        reading = $.trim(reading || '');
        if (!word || !reading) { setStatus('Kelime ve okunuş gerekli.', 'failed'); return $.Deferred().reject().promise(); }
        if ($button) $button.prop('disabled', true);
        setStatus('Kaydediliyor…', 'processing');
        return call('save', { word: word, reading: reading }).done(function (response) {
            if (!response || !response.success) { setStatus(errorText(null, response, 'Kaydedilemedi.'), 'failed'); return; }
            setStatus('“' + response.data.word + '” → “' + response.data.reading + '” kaydedildi; bütün sitelerde geçerli.', 'complete');
            load();
        }).fail(function (xhr) {
            setStatus(errorText(xhr, null, 'Kaydedilemedi.'), 'failed');
        }).always(function () { if ($button) $button.prop('disabled', false); });
    }

    function listen(word, reading, $button) {
        var text = $.trim(reading || word || '');
        if (!text) { setStatus('Dinlemek için okunuş yazın.', 'failed'); return; }
        if ($button) $button.prop('disabled', true);
        setStatus('Örnek ses hazırlanıyor…', 'processing');
        call('listen', { word: word || '', reading: text }).done(function (response) {
            if (!response || !response.success) { setStatus(errorText(null, response, 'Örnek ses alınamadı.'), 'failed'); return; }
            var player = document.getElementById('agfo-lex-player');
            player.hidden = false;
            player.src = response.data.audio;
            setStatus('“' + text + '” çalınıyor.', 'complete');
            var p = player.play();
            if (p && p.catch) p.catch(function () { /* autoplay may be blocked; controls stay visible */ });
        }).fail(function (xhr) {
            setStatus(errorText(xhr, null, 'Örnek ses alınamadı.'), 'failed');
        }).always(function () { if ($button) $button.prop('disabled', false); });
    }

    function removeOrRestore(op, word, $button) {
        $button.prop('disabled', true);
        call(op, { word: word }).done(function (response) {
            if (!response || !response.success) { setStatus(errorText(null, response, 'İşlem yapılamadı.'), 'failed'); return; }
            setStatus(op === 'delete' ? '“' + word + '” sözlükten kaldırıldı.' : '“' + word + '” hazır okunuşuna döndü.', 'complete');
            load();
        }).fail(function (xhr) {
            setStatus(errorText(xhr, null, 'İşlem yapılamadı.'), 'failed');
        }).always(function () { $button.prop('disabled', false); });
    }

    $('#agfo-lex-form').on('submit', function (event) {
        event.preventDefault();
        save($('#agfo-lex-word').val(), $('#agfo-lex-reading').val(), $('#agfo-lex-save')).done(function (response) {
            if (response && response.success) {
                $('#agfo-lex-search').val(response.data.word);
                $('#agfo-lex-filter').val('');
                page = 1;
                $('#agfo-lex-word, #agfo-lex-reading').val('');
            }
        });
    });
    $('#agfo-lex-word').on('change', function () {
        var word = $.trim($(this).val() || '');
        var hit = rows.filter(function (r) { return r.word === word; })[0];
        if (hit && !$.trim($('#agfo-lex-reading').val() || '')) {
            $('#agfo-lex-reading').val(hit.reading);
            setStatus('“' + word + '” sözlükte var; okunuşu değiştirip kaydedebilirsiniz.', 'idle');
        }
    });
    $('#agfo-lex-listen').on('click', function () { listen($('#agfo-lex-word').val(), $('#agfo-lex-reading').val(), $(this)); });
    $('#agfo-lex-search').on('input', function () { page = 1; render(); });
    $('#agfo-lex-filter').on('change', function () { page = 1; render(); });
    $('#agfo-lex-reload').on('click', load);
    $('#agfo-lex-prev').on('click', function () { page -= 1; render(); });
    $('#agfo-lex-next').on('click', function () { page += 1; render(); });

    $('#agfo-lex-rows').on('click', '.agfo-lex-row-save', function () {
        var $tr = $(this).closest('tr');
        save($tr.attr('data-word'), $tr.find('.agfo-lex-row-reading').val(), $(this));
    }).on('click', '.agfo-lex-row-listen', function () {
        var $tr = $(this).closest('tr');
        listen($tr.attr('data-word'), $tr.find('.agfo-lex-row-reading').val(), $(this));
    }).on('click', '.agfo-lex-row-delete', function () {
        removeOrRestore('delete', $(this).closest('tr').attr('data-word'), $(this));
    }).on('click', '.agfo-lex-row-restore', function () {
        removeOrRestore('restore', $(this).closest('tr').attr('data-word'), $(this));
    }).on('keydown', '.agfo-lex-row-reading', function (event) {
        if (event.key === 'Enter') { event.preventDefault(); $(this).closest('tr').find('.agfo-lex-row-save').trigger('click'); }
    });

    if ($('#agfo-lex-rows').length) load();
})(jQuery);
