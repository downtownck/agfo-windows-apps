/**
 * AGFO Progress — v16.2.0
 * Sag altta ince, sabit, kapatilabilir mini ilerleme cubugu.
 * GERCEK asamalardan beslenir (async job durumlari / sirali toplu isler).
 * API: AGFOProgress.begin(title) -> handle { stage(text, pct|null), done(text), fail(text) }
 * pct null ise belirsiz (kayan) mod; islem bitince 3sn sonra kendini gizler.
 */
(function () {
    'use strict';

    var el = null, barEl = null, txtEl = null, ttlEl = null, hideTimer = null, minimized = false;

    function build() {
        if (el) return;
        el = document.createElement('div');
        el.id = 'agfo-progress';
        el.innerHTML =
            '<div class="agfo-progress-head">' +
              '<span class="agfo-progress-title"></span>' +
              '<button type="button" class="agfo-progress-min" title="Küçült">–</button>' +
            '</div>' +
            '<div class="agfo-progress-text"></div>' +
            '<div class="agfo-progress-track"><i class="agfo-progress-bar"></i></div>';
        document.body.appendChild(el);
        barEl = el.querySelector('.agfo-progress-bar');
        txtEl = el.querySelector('.agfo-progress-text');
        ttlEl = el.querySelector('.agfo-progress-title');
        el.querySelector('.agfo-progress-min').addEventListener('click', function () {
            minimized = !minimized;
            el.classList.toggle('is-min', minimized);
            this.textContent = minimized ? '+' : '–';
        });
    }

    function show() {
        build();
        if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
        el.classList.add('is-visible');
        el.classList.remove('is-done', 'is-fail');
    }

    function scheduleHide() {
        if (hideTimer) clearTimeout(hideTimer);
        hideTimer = setTimeout(function () { if (el) el.classList.remove('is-visible'); }, 3000);
    }

    window.AGFOProgress = {
        begin: function (title) {
            show();
            ttlEl.textContent = title || 'AGFO işlem';
            txtEl.textContent = 'Başlatılıyor…';
            barEl.style.width = '0%';
            el.classList.add('is-indeterminate');
            return this;
        },
        stage: function (text, pct) {
            show();
            txtEl.textContent = text || '';
            if (typeof pct === 'number' && isFinite(pct)) {
                el.classList.remove('is-indeterminate');
                barEl.style.width = Math.max(0, Math.min(100, pct)) + '%';
            } else {
                el.classList.add('is-indeterminate');
            }
            return this;
        },
        done: function (text) {
            show();
            el.classList.remove('is-indeterminate');
            el.classList.add('is-done');
            barEl.style.width = '100%';
            txtEl.textContent = text || 'Tamamlandı ✓';
            scheduleHide();
            return this;
        },
        fail: function (text) {
            show();
            el.classList.remove('is-indeterminate');
            el.classList.add('is-fail');
            barEl.style.width = '100%';
            txtEl.textContent = text || 'Hata';
            scheduleHide();
            return this;
        }
    };
})();
