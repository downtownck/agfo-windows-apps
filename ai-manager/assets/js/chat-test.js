/**
 * AGFO Chat Test – chat-test.js v16.2.0
 * Admin sayfasında ayrı yüklenir: agfo-chat-test hook'unda enqueue edilir.
 */
(function ($) {
  'use strict';

  var ChatTest = {
    messages: [],   // { role, content }
    loading:  false,

    init: function () {
      this.bindEvents();
      this.loadModels($('#ct-provider').val());
    },

    bindEvents: function () {
      var self = this;

      // Sağlayıcı değişince modelleri yenile
      $('#ct-provider').on('change', function () {
        self.loadModels(this.value);
      });

      // Sıcaklık slider
      $('#ct-temperature').on('input', function () {
        $('#ct-temp-val').text(parseFloat(this.value).toFixed(1));
      });

      // Gönder butonu
      $('#ct-send-btn').on('click', function () {
        self.send();
      });

      // Ctrl+Enter ile gönder
      $('#ct-input').on('keydown', function (e) {
        if (e.ctrlKey && e.key === 'Enter') {
          e.preventDefault();
          self.send();
        }
      });

      // Temizle
      $('#ct-clear-btn').on('click', function () {
        self.clearChat();
      });

      // CHANGED 16.2.0: model secilince hiz beklentisi rozeti (Model Intelligence verisinden).
      $('#ct-model').on('change', function () {
        self.updateSpeedBadge($('#ct-provider').val(), this.value);
      });
    },

    /* CHANGED 16.2.0: hiz rozeti. */
    updateSpeedBadge: function (provider, model) {
      var $sel = $('#ct-model');
      var $b = $('#ct-speed-badge');
      if (!$b.length) $b = $('<div id="ct-speed-badge" style="margin-top:6px;font-size:11px;color:#50575e;"></div>').insertAfter($sel);
      $b.text('');
      if (!provider || !model || /^[⏳❌]/.test(model)) return;
      $.post(agfoConfig.ajaxurl, { action: 'agfo_ai_model_speed', nonce: agfoConfig.nonce, provider: provider, model: model }, function (res) {
        if (!res || !res.success || !res.data || res.data.speed_score == null) { $b.text(''); return; }
        var s = res.data.speed_score, t;
        if (s >= 86)      t = '⚡ Hızlı model — saniyeler içinde yanıt beklenir';
        else if (s >= 54) t = '🚶 Orta hız — 5–15 sn beklenebilir';
        else              t = '🐢 Yavaş / kuyruklu model — uzun bekleme olası';
        if (res.data.label) t += ' · ' + res.data.label;
        $b.text(t);
      });
    },

    /* ── Model listesini yükle ─────────────────────────── */
    loadModels: function (provider) {
      var self = this;
      var $sel = $('#ct-model');
      $sel.html('<option>⏳ Yükleniyor...</option>').prop('disabled', true);

      $.post(agfoConfig.ajaxurl, {
        action:   'agfo_qs_get_models_only',
        provider: provider,
        nonce:    agfoConfig.nonce // CHANGED 16.6.0: sunucu tarafinda nonce zorunlu oldu.
      }, function (res) {
        $sel.prop('disabled', false);
        if (!res.success || !res.data || !res.data.length) {
          $sel.html('<option>❌ Model bulunamadı — önce Model Yönetimi sayfasından yükleyin</option>');
          return;
        }
        var opts = res.data.map(function (m) {
          var id = typeof m === 'string' ? m : m.id;
          return '<option value="' + id + '">' + id + '</option>';
        }).join('');
        $sel.html(opts);
      }).fail(function () {
        $sel.html('<option>❌ Bağlantı hatası</option>').prop('disabled', false);
      });
    },

    /* ── Mesaj gönder ─────────────────────────────────── */
    send: function () {
      if (this.loading) return;

      var text = $('#ct-input').val().trim();
      if (!text) return;

      var provider = $('#ct-provider').val();
      var model    = $('#ct-model').val();

      if (!provider || !model || /^[⏳❌]/.test(model)) {
        this.appendError('⚠️ Lütfen geçerli bir sağlayıcı ve model seçin.');
        return;
      }

      // Kullanıcı mesajını ekle
      this.messages.push({ role: 'user', content: text });
      this.appendBubble('user', text);
      $('#ct-input').val('');

      // Typing göster
      this.showTyping();
      this.setLoading(true);

      var self = this;
      var payload = {
        nonce:       agfoConfig.nonce,
        provider:    provider,
        model:       model,
        system:      $('#ct-system').val(),
        temperature: $('#ct-temperature').val(),
        max_tokens:  $('#ct-max-tokens').val(),
        messages:    JSON.stringify(self.messages),
        reasoning:   $('#ct-reasoning').is(':checked') ? 1 : 0
      };
      // CHANGED 16.2.0: ASYNC JOB akisi — is arka planda calisir, tarayici GERCEK asamalari poll'lar.
      // Job baslatilamazsa eski senkron yol (sendSync) AYNEN devreye girer; hicbir davranis kaybolmadi.
      this.sendAsync(payload);
    },

    /* CHANGED 16.2.0: eski senkron gonderim — fallback olarak birebir korundu. */
    sendSync: function (payload) {
      var self = this;
      payload.action = 'agfo_chat_test';
      $.post(agfoConfig.ajaxurl, payload, function (res) {
        self.hideTyping();
        self.setLoading(false);

        if (!res.success) {
          // Hatalı mesajı geçmişten çıkar
          self.messages.pop();
          self.appendError('❌ ' + (res.data || 'Bilinmeyen hata'));
          return;
        }

        var d = res.data;
        self.messages.push({ role: 'assistant', content: d.content });
        self.appendBubble('assistant', d.content, d.model, d.elapsed_ms);
        self.updateStats(d);
      }).fail(function (xhr) {
        self.hideTyping();
        self.setLoading(false);
        self.messages.pop();
        var msg = 'HTTP ' + xhr.status;
        try { var j = JSON.parse(xhr.responseText); if (j.data) msg = j.data; } catch(e) {}
        self.appendError('❌ İstek başarısız: ' + msg);
      });
    },

    /* CHANGED 16.2.0: async job akisi + gercek asamali progress bar. */
    progress: function () {
      if (window.AGFOProgress) return window.AGFOProgress;
      return { begin: function(){return this;}, stage: function(){return this;}, done: function(){return this;}, fail: function(){return this;} };
    },

    stageText: function (st) {
      var s = st.stage || st.status || '';
      if (s === 'queued')       return 'Kuyruğa alındı…';
      if (s === 'starting')     return 'İş başlatıldı…';
      if (s === 'sending')      return 'Modele gönderildi, yanıt bekleniyor…';
      if (s === 'nvidia_queue') return 'NVIDIA kuyruğunda (202 alındı)…';
      if (s === 'nvidia_poll')  return 'NVIDIA sonucu bekleniyor — deneme ' + (st.attempt || 1);
      if (s === 'http_done')    return 'Yanıt alındı, işleniyor…';
      return 'Çalışıyor… (' + s + ')';
    },

    sendAsync: function (payload) {
      var self = this, P = this.progress();
      var startBody = $.extend({ action: 'agfo_ai_job_start' }, payload);
      P.begin('AI: ' + payload.model);
      P.stage('İş gönderiliyor…', null);

      $.post(agfoConfig.ajaxurl, startBody, function (res) {
        if (!res || !res.success || !res.data || !res.data.job_id) {
          P.stage('Async kullanılamadı — klasik yol…', null);
          self.sendSync(payload);
          return;
        }
        var jobId = res.data.job_id, kicked = false, deadline = Date.now() + 200000;

        var poll = function () {
          if (Date.now() > deadline) {
            self.hideTyping(); self.setLoading(false); self.messages.pop();
            P.fail('Zaman aşımı (200sn)');
            self.appendError('❌ İş zaman aşımına uğradı (200sn). Daha hızlı bir model deneyin.');
            return;
          }
          $.post(agfoConfig.ajaxurl, { action: 'agfo_ai_job_status', nonce: agfoConfig.nonce, job_id: jobId }, function (st) {
            if (!st || !st.success) {
              self.hideTyping(); self.setLoading(false); self.messages.pop();
              P.fail('Durum okunamadı');
              self.appendError('❌ ' + ((st && st.data) || 'İş durumu okunamadı'));
              return;
            }
            var d = st.data;
            if (d.status === 'done') {
              self.hideTyping(); self.setLoading(false);
              var r = d.result || {};
              if (!r.elapsed_ms && d.elapsed_ms) r.elapsed_ms = d.elapsed_ms;
              self.messages.push({ role: 'assistant', content: r.content });
              self.appendBubble('assistant', r.content, r.model || payload.model, r.elapsed_ms);
              self.updateStats(r);
              P.done('Tamamlandı — ' + ((r.elapsed_ms || 0) / 1000).toFixed(1) + ' sn');
              return;
            }
            if (d.status === 'error') {
              self.hideTyping(); self.setLoading(false); self.messages.pop();
              P.fail('Hata');
              self.appendError('❌ ' + (d.error || 'Bilinmeyen hata'));
              return;
            }
            // Calisiyor: gercek asamayi yaz
            P.stage(self.stageText(d), null);
            // Loopback engelliyse (5sn+ 'queued'): isi tarayicidan tekmele — bir kez.
            if (d.status === 'queued' && d.age >= 5 && !kicked) {
              kicked = true;
              $.post(agfoConfig.ajaxurl, { action: 'agfo_ai_job_run', nonce: agfoConfig.nonce, job_id: jobId });
            }
            setTimeout(poll, 1500);
          }).fail(function () { setTimeout(poll, 2500); });
        };
        setTimeout(poll, 900);
      }).fail(function () {
        P.stage('Async kullanılamadı — klasik yol…', null);
        self.sendSync(payload);
      });
    },

    /* ── DOM yardımcıları ─────────────────────────────── */
    appendBubble: function (role, content, model, elapsed) {
      var avatar = role === 'user' ? '👤' : '🤖';
      var time   = new Date().toLocaleTimeString('tr-TR', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
      var meta   = time;
      if (model)   meta += ' · ' + model;
      if (elapsed) meta += ' · ' + elapsed + 'ms';

      var $msg = $(
        '<div class="agfo-chat-msg ' + role + '">' +
          '<div class="agfo-chat-avatar">' + avatar + '</div>' +
          '<div>' +
            '<div class="agfo-chat-bubble">' + this.escHtml(content) + '</div>' +
            '<div class="agfo-chat-meta">' + meta + '</div>' +
          '</div>' +
        '</div>'
      );

      this.removeWelcome();
      $('#ct-messages').append($msg);
      this.scrollBottom();
    },

    appendError: function (msg) {
      var $err = $(
        '<div class="agfo-chat-msg error">' +
          '<div class="agfo-chat-bubble">' + this.escHtml(msg) + '</div>' +
        '</div>'
      );
      this.removeWelcome();
      $('#ct-messages').append($err);
      this.scrollBottom();
    },

    showTyping: function () {
      var $t = $(
        '<div class="agfo-chat-msg assistant agfo-chat-typing" id="ct-typing">' +
          '<div class="agfo-chat-avatar">🤖</div>' +
          '<div class="agfo-chat-bubble">' +
            '<div class="agfo-typing-dots">' +
              '<span></span><span></span><span></span>' +
            '</div>' +
          '</div>' +
        '</div>'
      );
      this.removeWelcome();
      $('#ct-messages').append($t);
      this.scrollBottom();
    },

    hideTyping: function () {
      $('#ct-typing').remove();
    },

    updateStats: function (d) {
      var html =
        '<div class="agfo-chat-stat-row"><span>⏱️ Süre</span><span>' + (d.elapsed_ms || 0) + ' ms</span></div>' +
        '<div class="agfo-chat-stat-row"><span>📥 Prompt</span><span>' + (d.prompt_tokens || 0) + ' token</span></div>' +
        '<div class="agfo-chat-stat-row"><span>📤 Yanıt</span><span>' + (d.completion_tokens || 0) + ' token</span></div>' +
        '<div class="agfo-chat-stat-row"><span>🔢 Toplam</span><span>' + (d.total_tokens || 0) + ' token</span></div>' +
        '<div class="agfo-chat-stat-row"><span>🤖 Model</span><span style="font-size:10px;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + this.escHtml(d.model || '-') + '</span></div>';
      $('#ct-stats').html(html);
      $('#ct-stats-card').show();
    },

    clearChat: function () {
      this.messages = [];
      $('#ct-messages').html(
        '<div class="agfo-chat-welcome">' +
          '<div style="font-size:32px;margin-bottom:8px;">💬</div>' +
          '<div style="font-size:14px;color:#6b7280;">Sağlayıcı ve model seçin, mesaj gönderin.</div>' +
        '</div>'
      );
      $('#ct-stats-card').hide();
      $('#ct-stats').html('');
    },

    setLoading: function (state) {
      this.loading = state;
      $('#ct-send-btn').prop('disabled', state).text(state ? '⏳ Bekleniyor...' : '➤ Gönder');
      $('#ct-input').prop('disabled', state);
    },

    removeWelcome: function () {
      $('#ct-messages .agfo-chat-welcome').remove();
    },

    scrollBottom: function () {
      var $m = $('#ct-messages');
      $m.scrollTop($m[0].scrollHeight);
    },

    escHtml: function (str) {
      return String(str)
        .replace(/&/g,  '&amp;')
        .replace(/</g,  '&lt;')
        .replace(/>/g,  '&gt;')
        .replace(/"/g,  '&quot;')
        .replace(/'/g,  '&#039;');
    }
  };

  /* ── Başlat ─────────────────────────────────────────── */
  $(document).ready(function () {
    if ($('.agfo-chat-wrap').length) {
      ChatTest.init();
    }
  });

}(jQuery));// chat-test.js
