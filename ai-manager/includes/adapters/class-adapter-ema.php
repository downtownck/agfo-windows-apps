<?php
/**
 * EMA Lightning (self-hosted Turkish TTS) adapter.
 *
 * Talks to the AGFO TTS Service (FastAPI wrapper around EMA Lightning) that runs
 * on the same server, by default on http://127.0.0.1:8765. No per-character cost.
 *
 * Service contract:
 *   POST {endpoint}/tts   JSON { text, speed, pause_ms, paragraph_pause_ms, format, lexicon }
 *                          header X-AGFO-Token; returns audio (audio/mpeg | audio/wav),
 *                          headers X-AGFO-Seconds (duration), X-AGFO-Cached (0|1).
 *   GET  {endpoint}/health header X-AGFO-Token; returns { ok, model, threads, lexicon_entries }.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Adapter_EMA' ) ) {
    final class AGFO_AIM_Adapter_EMA implements AGFO_AIM_Adapter_Interface {

        const OPT_ENDPOINT = 'agfo_ai_ema_endpoint';
        const OPT_LEXICON  = 'agfo_ai_ema_lexicon';
        const DEFAULT_URL  = 'http://127.0.0.1:8765';
        const MAX_CHARS    = 60000; // Matches the service's MAX_CHARS.

        public function provider_code(): string {
            return 'ema';
        }

        public function supports( string $capability ): bool {
            return 'speech_synthesize' === $capability;
        }

        /* ── Configuration ───────────────────────────────── */

        public static function endpoint(): string {
            $url = trim( (string) get_option( self::OPT_ENDPOINT, '' ) );
            if ( '' === $url && defined( 'AGFO_TTS_ENDPOINT' ) ) {
                $url = (string) AGFO_TTS_ENDPOINT;
            }
            return untrailingslashit( '' !== $url ? esc_url_raw( $url ) : self::DEFAULT_URL );
        }

        /** Paragraph pause default (ms) for jobs that do not send one. */
        public static function default_pause( string $which ): int {
            $saved = get_option( 'agfo_ai_ema_pauses', [] );
            $saved = is_array( $saved ) ? $saved : [];
            if ( 'paragraph' === $which ) {
                return isset( $saved['paragraph'] ) ? max( 0, min( 3000, absint( $saved['paragraph'] ) ) ) : 700;
            }
            return isset( $saved['sentence'] ) ? max( 0, min( 2000, absint( $saved['sentence'] ) ) ) : 350;
        }

        public static function token(): string {
            if ( defined( 'AGFO_TTS_TOKEN' ) && '' !== trim( (string) AGFO_TTS_TOKEN ) ) {
                return trim( (string) AGFO_TTS_TOKEN ); // wp-config.php wins: the secret never has to live in the database.
            }
            if ( function_exists( 'agfo_get_api_key' ) ) {
                $key = agfo_get_api_key( 'ema' );
                if ( is_string( $key ) && '' !== trim( $key ) ) {
                    return trim( $key );
                }
            }
            return '';
        }

        /**
         * Site-level pronunciation overrides, sent with every request on top of the
         * server lexicon. Stored as "Kelime = okunuş" lines.
         *
         * @return array<string,string>
         */
        public static function lexicon(): array {
            $out = [];
            foreach ( preg_split( '/\R/u', (string) get_option( self::OPT_LEXICON, '' ) ) as $line ) {
                $parts = explode( '=', (string) $line, 2 );
                if ( 2 !== count( $parts ) ) {
                    continue;
                }
                $word = trim( $parts[0] );
                $say  = trim( $parts[1] );
                if ( '' !== $word && '' !== $say && mb_strlen( $word ) <= 80 && mb_strlen( $say ) <= 160 ) {
                    $out[ $word ] = $say;
                }
                if ( count( $out ) >= 500 ) {
                    break;
                }
            }
            return $out;
        }

        /**
         * Connection test for the settings screen.
         *
         * @return array|WP_Error
         */
        public static function health() {
            if ( '' === self::token() ) {
                return new WP_Error( 'agfo_ema_no_token', 'EMA servis token’ı tanımlı değil.' );
            }
            $res = wp_remote_get(
                self::endpoint() . '/health',
                [
                    'timeout'   => 10,
                    'sslverify' => true,
                    'headers'   => [ 'X-AGFO-Token' => self::token() ],
                ]
            );
            if ( is_wp_error( $res ) ) {
                return new WP_Error( 'agfo_ema_unreachable', 'EMA servisine ulaşılamadı (' . self::endpoint() . '): ' . agfo_redact_secrets( $res->get_error_message() ) );
            }
            $code = (int) wp_remote_retrieve_response_code( $res );
            $json = json_decode( (string) wp_remote_retrieve_body( $res ), true );
            if ( 401 === $code ) {
                return new WP_Error( 'agfo_ema_bad_token', 'EMA servisi token’ı reddetti.' );
            }
            if ( 200 !== $code || ! is_array( $json ) || empty( $json['ok'] ) ) {
                return new WP_Error( 'agfo_ema_health', 'EMA servisi beklenmeyen yanıt verdi (HTTP ' . $code . ').' );
            }
            return $json;
        }

        /**
         * Studio "EMA servis ayarları" save: endpoint, pronunciation lexicon and
         * default pauses. The token is a provider key and is saved on the
         * Sağlayıcılar screen like every other key.
         */
        public static function ajax_save_settings(): void {
            if ( ! is_user_logged_in() || ! current_user_can( 'manage_options' ) ) {
                wp_send_json_error( [ 'message' => 'Yetki yok.' ], 403 );
            }
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );

            $endpoint = trim( sanitize_text_field( wp_unslash( (string) ( $_POST['endpoint'] ?? '' ) ) ) );
            if ( '' !== $endpoint ) {
                $parts = wp_parse_url( $endpoint );
                if ( ! is_array( $parts ) || empty( $parts['host'] ) || ! in_array( strtolower( (string) ( $parts['scheme'] ?? '' ) ), [ 'http', 'https' ], true ) ) {
                    wp_send_json_error( [ 'message' => 'Servis adresi http:// veya https:// ile başlayan geçerli bir adres olmalı.' ], 400 );
                }
                $endpoint = untrailingslashit( esc_url_raw( $endpoint ) );
            }
            update_option( self::OPT_ENDPOINT, $endpoint, false );

            $lexicon = sanitize_textarea_field( wp_unslash( (string) ( $_POST['lexicon'] ?? '' ) ) );
            update_option( self::OPT_LEXICON, $lexicon, false );

            update_option(
                'agfo_ai_ema_pauses',
                [
                    'sentence'  => max( 0, min( 2000, absint( $_POST['pause_ms'] ?? 350 ) ) ),
                    'paragraph' => max( 0, min( 3000, absint( $_POST['paragraph_pause_ms'] ?? 700 ) ) ),
                ],
                false
            );

            if ( isset( $_POST['script_enabled'] ) ) {
                update_option( 'agfo_ai_ema_script', empty( $_POST['script_enabled'] ) || '0' === (string) $_POST['script_enabled'] ? '0' : '1', false );
            }
            if ( isset( $_POST['script_model'] ) ) {
                $choice = sanitize_text_field( wp_unslash( (string) $_POST['script_model'] ) );
                if ( '' !== $choice && class_exists( 'AGFO_AIM_Content_Transformer' ) && is_wp_error( AGFO_AIM_Content_Transformer::chosen_config( $choice ) ) ) {
                    wp_send_json_error( [ 'message' => 'Seçilen okuma metni modeli bu sitede kullanılamıyor.' ], 400 );
                }
                update_option( 'agfo_ai_ema_script_model', $choice, false );
            }

            wp_send_json_success(
                [
                    'message'         => 'EMA ayarları kaydedildi.',
                    'endpoint'        => self::endpoint(),
                    'lexicon_entries' => count( self::lexicon() ),
                ]
            );
        }

        /** Values the Studio form starts from. */
        public static function settings(): array {
            return [
                'endpoint'           => self::endpoint(),
                'endpoint_saved'     => (string) get_option( self::OPT_ENDPOINT, '' ),
                'endpoint_constant'  => defined( 'AGFO_TTS_ENDPOINT' ),
                'token_constant'     => defined( 'AGFO_TTS_TOKEN' ) && '' !== trim( (string) AGFO_TTS_TOKEN ),
                'lexicon'            => (string) get_option( self::OPT_LEXICON, '' ),
                'pause_ms'           => self::default_pause( 'sentence' ),
                'paragraph_pause_ms' => self::default_pause( 'paragraph' ),
                'script_enabled'     => class_exists( 'AGFO_AIM_Speech_Script' ) ? AGFO_AIM_Speech_Script::enabled_by_default() : false,
                'script_model'       => (string) get_option( 'agfo_ai_ema_script_model', '' ),
            ];
        }

        /**
         * Server lexicon (lexicon.json + this site's overrides) applied in one pass by the
         * service (1.0.8+). Lets the reading script start from the curated readings.
         *
         * @return string|WP_Error
         */
        public static function apply_server_lexicon( string $text ) {
            if ( '' === self::token() ) {
                return new WP_Error( 'agfo_ema_no_token', 'EMA servis token’ı tanımlı değil.' );
            }
            $body = [ 'text' => $text ];
            $lex  = self::lexicon();
            if ( $lex ) {
                $body['lexicon'] = $lex;
            }
            $res = wp_remote_post(
                self::endpoint() . '/lexicon/apply',
                [
                    'timeout'   => 30,
                    'sslverify' => true,
                    'headers'   => [ 'X-AGFO-Token' => self::token(), 'Content-Type' => 'application/json' ],
                    'body'      => wp_json_encode( $body, JSON_UNESCAPED_UNICODE ),
                ]
            );
            if ( is_wp_error( $res ) ) {
                return new WP_Error( 'agfo_ema_lexicon_http', agfo_redact_secrets( $res->get_error_message() ) );
            }
            $code = (int) wp_remote_retrieve_response_code( $res );
            $json = json_decode( (string) wp_remote_retrieve_body( $res ), true );
            if ( 200 !== $code || ! is_array( $json ) || ! isset( $json['text'] ) || ! is_string( $json['text'] ) ) {
                return new WP_Error( 'agfo_ema_lexicon_unsupported', 'EMA servisi sözlük uygulamayı desteklemiyor (HTTP ' . $code . '); servis 1.0.8 veya üstü gerekir.' );
            }
            return $json['text'];
        }

        /**
         * NEW 17.11.0: shared (server) lexicon management — Telaffuz Sözlüğü page.
         * One JSON call to the service; returns decoded body or WP_Error.
         *
         * @return array|WP_Error
         */
        public static function service_call( string $method, string $path, ?array $body = null, int $timeout = 30 ) {
            if ( '' === self::token() ) {
                return new WP_Error( 'agfo_ema_no_token', 'EMA servis token’ı tanımlı değil.' );
            }
            $args = [
                'method'    => $method,
                'timeout'   => $timeout,
                'sslverify' => true,
                'headers'   => [ 'X-AGFO-Token' => self::token(), 'Content-Type' => 'application/json' ],
            ];
            if ( null !== $body ) {
                $args['body'] = wp_json_encode( $body, JSON_UNESCAPED_UNICODE );
            }
            $res = wp_remote_request( self::endpoint() . $path, $args );
            if ( is_wp_error( $res ) ) {
                return new WP_Error( 'agfo_ema_unreachable', 'EMA servisine ulaşılamadı (' . self::endpoint() . '): ' . agfo_redact_secrets( $res->get_error_message() ) );
            }
            $code = (int) wp_remote_retrieve_response_code( $res );
            $json = json_decode( (string) wp_remote_retrieve_body( $res ), true );
            if ( 404 === $code && '/lexicon' === $path ) {
                return new WP_Error( 'agfo_ema_lexicon_unsupported', 'Sunucudaki EMA servisi sözlük düzenlemeyi desteklemiyor; AGFO TTS Service 1.1.0 veya üstüne güncelleyin (update.sh).' );
            }
            if ( $code < 200 || $code >= 300 || ! is_array( $json ) ) {
                $detail = is_array( $json ) && isset( $json['detail'] ) ? ( is_scalar( $json['detail'] ) ? (string) $json['detail'] : wp_json_encode( $json['detail'] ) ) : 'HTTP ' . $code;
                return new WP_Error( 'agfo_ema_service_' . $code, 'EMA servisi: ' . sanitize_text_field( $detail ) );
            }
            return $json;
        }

        /** Short MP3 of a reading, spoken exactly as written (lexicon not applied). */
        public static function listen( string $reading ) {
            $reading = trim( $reading );
            if ( '' === $reading || mb_strlen( $reading, 'UTF-8' ) > 300 ) {
                return new WP_Error( 'agfo_ema_listen_text', 'Dinlenecek okunuş boş veya çok uzun.' );
            }
            if ( '' === self::token() ) {
                return new WP_Error( 'agfo_ema_no_token', 'EMA servis token’ı tanımlı değil.' );
            }
            $res = wp_remote_post(
                self::endpoint() . '/tts',
                [
                    'timeout'   => 60,
                    'sslverify' => true,
                    'headers'   => [ 'X-AGFO-Token' => self::token(), 'Content-Type' => 'application/json', 'Accept' => 'audio/mpeg' ],
                    'body'      => wp_json_encode( [ 'text' => $reading, 'format' => 'mp3', 'apply_lexicon' => false, 'pause_ms' => 0, 'paragraph_pause_ms' => 0 ], JSON_UNESCAPED_UNICODE ),
                ]
            );
            if ( is_wp_error( $res ) ) {
                return new WP_Error( 'agfo_ema_unreachable', agfo_redact_secrets( $res->get_error_message() ) );
            }
            $code = (int) wp_remote_retrieve_response_code( $res );
            $body = (string) wp_remote_retrieve_body( $res );
            if ( 200 !== $code || '' === $body ) {
                return new WP_Error( 'agfo_ema_listen_failed', 'EMA örnek sesi üretemedi (HTTP ' . $code . ').' );
            }
            return $body;
        }

        /* ── Adapter contract ────────────────────────────── */

        public function validate_payload( string $capability, array $payload ) {
            if ( ! $this->supports( $capability ) ) {
                return new WP_Error( 'agfo_capability_unsupported', 'EMA Lightning yalnızca seslendirme (TTS) yapar.' );
            }
            $text = (string) ( $payload['text'] ?? '' );
            if ( '' === trim( $text ) ) {
                return new WP_Error( 'agfo_tts_text_required', 'Seslendirilecek metin gerekli.' );
            }
            if ( mb_strlen( $text, 'UTF-8' ) > self::MAX_CHARS ) {
                return new WP_Error( 'agfo_tts_text_too_long', 'EMA Lightning tek işte en fazla ' . self::MAX_CHARS . ' karakter kabul eder.' );
            }
            $format = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            if ( ! in_array( $format, [ 'mp3', 'wav' ], true ) ) {
                return new WP_Error( 'agfo_tts_format', 'EMA Lightning yalnızca mp3 veya wav üretir.' );
            }
            if ( isset( $payload['speed'] ) && '' !== (string) $payload['speed'] ) {
                $speed = (float) $payload['speed'];
                if ( $speed < 0.7 || $speed > 1.4 ) {
                    return new WP_Error( 'agfo_tts_speed', 'EMA hız değeri 0.7 ile 1.4 arasında olmalıdır.' );
                }
            }
            // EMA only speaks Turkish. A failed validation makes the worker skip this
            // route, so a non-Turkish job that fails over here never becomes wrong audio.
            if ( ! self::is_turkish_request( $payload ) ) {
                return new WP_Error( 'agfo_ema_language', 'EMA Lightning yalnızca Türkçe metni seslendirir; bu metin Türkçe görünmüyor.' );
            }
            return true;
        }

        /**
         * True when the job explicitly asks for Turkish, or when nothing says
         * otherwise and the text itself looks Turkish.
         */
        public static function is_turkish_request( array $payload ): bool {
            $language = strtolower( trim( (string) ( $payload['language'] ?? '' ) ) );
            if ( '' !== $language ) {
                return in_array( $language, [ 'tr', 'tur', 'tr-tr', 'tr_tr', 'turkish' ], true );
            }
            $boost = strtolower( trim( (string) ( $payload['language_boost'] ?? '' ) ) );
            if ( '' !== $boost && 'auto' !== $boost && 'turkish' !== $boost ) {
                return false;
            }
            return self::looks_turkish( (string) ( $payload['text'] ?? '' ) );
        }

        /**
         * Turkish prose carries ı, ş, ğ, ç, ö, ü at a few percent of all letters.
         * Short texts are given the benefit of the doubt.
         */
        public static function looks_turkish( string $text ): bool {
            $letters = preg_match_all( '/\p{L}/u', $text );
            if ( ! $letters || $letters < 200 ) {
                return true;
            }
            $specific = preg_match_all( '/[ıİşŞğĞçÇöÖüÜ]/u', $text );
            return ( $specific / $letters ) >= 0.01;
        }

        public function estimate_cost( string $capability, array $payload, array $context = [] ): array {
            $chars = mb_strlen( (string) ( $payload['text'] ?? '' ), 'UTF-8' );
            return [
                'units'     => (float) $chars,
                'unit_name' => 'character',
                'cost'      => 0.0,
                'currency'  => 'USD',
                'snapshot'  => [
                    'basis'         => 'per_1000_characters',
                    'rate_per_1000' => 0.0,
                    'model'         => 'ema-lightning',
                    'source'        => 'self_hosted',
                ],
            ];
        }

        public function dispatch( string $capability, array $payload, array $context = [] ) {
            $valid = $this->validate_payload( $capability, $payload );
            if ( is_wp_error( $valid ) ) {
                return $valid;
            }
            $token = self::token();
            if ( '' === $token ) {
                return new WP_Error( 'agfo_no_api_key', 'EMA servis token’ı tanımlı değil (AI Manager › Sağlayıcılar › EMA Lightning veya wp-config.php içinde AGFO_TTS_TOKEN).' );
            }

            $format    = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            $spoken    = (string) $payload['text'];
            $use_lex   = true;
            $script    = [ 'status' => 'off' ];
            $started   = microtime( true );
            if ( function_exists( 'set_time_limit' ) ) {
                @set_time_limit( 1200 ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
            }
            if ( ! empty( $payload['script_ready'] ) ) {
                // Text is a reading script prepared (and possibly edited) in the preview.
                $use_lex = false;
                $script  = [ 'status' => 'ready' ];
            } elseif ( self::wants_script( $payload ) ) {
                $base = self::apply_server_lexicon( $spoken );
                if ( ! is_wp_error( $base ) ) {
                    $use_lex = false; // lexicon already applied; never apply it to the script again
                }
                $prepared = AGFO_AIM_Speech_Script::prepare(
                    is_wp_error( $base ) ? $spoken : $base,
                    [ 'deadline' => $started + 600 ]
                );
                if ( is_wp_error( $prepared ) ) {
                    // No usable text model: speak the text as written instead of failing the job.
                    $use_lex = true;
                    $script  = [ 'status' => 'skipped', 'reason' => $prepared->get_error_message() ];
                } else {
                    $spoken = (string) $prepared['text'];
                    $script = [
                        'status'        => 'done',
                        'model'         => $prepared['model'],
                        'chunks'        => $prepared['chunks'],
                        'rewritten'     => $prepared['rewritten'],
                        'kept_original' => $prepared['kept_original'],
                        'cached'        => $prepared['cached'],
                    ];
                }
            }
            if ( mb_strlen( $spoken, 'UTF-8' ) > self::MAX_CHARS ) {
                $spoken = mb_substr( $spoken, 0, self::MAX_CHARS, 'UTF-8' );
            }
            $body   = [
                'text'               => $spoken,
                'speed'              => isset( $payload['speed'] ) && '' !== (string) $payload['speed'] ? round( (float) $payload['speed'], 2 ) : 1.0,
                'pause_ms'           => isset( $payload['pause_ms'] ) ? max( 0, min( 2000, absint( $payload['pause_ms'] ) ) ) : self::default_pause( 'sentence' ),
                'paragraph_pause_ms' => isset( $payload['paragraph_pause_ms'] ) ? max( 0, min( 3000, absint( $payload['paragraph_pause_ms'] ) ) ) : self::default_pause( 'paragraph' ),
                'format'             => $format,
            ];
            if ( $use_lex ) {
                $lexicon = self::lexicon();
                if ( $lexicon ) {
                    $body['lexicon'] = $lexicon;
                }
            } else {
                $body['apply_lexicon'] = false;
            }

            $tmp = $this->create_temp_file( 'agfo-ema-tts.' . $format );
            if ( ! $tmp ) {
                return new WP_Error( 'agfo_temp_file', 'Geçici ses dosyası oluşturulamadı.' );
            }

            // Roughly 2 s of CPU work per 1000 characters on the shared server, plus headroom.
            $timeout  = (int) min( 900, max( 60, ceil( mb_strlen( $body['text'], 'UTF-8' ) / 1000 ) * 6 + 60 ) );
            if ( function_exists( 'set_time_limit' ) ) {
                // Long articles run on CPU; keep the worker alive for the whole request.
                @set_time_limit( $timeout + 60 ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
            }
            $response = wp_remote_post(
                self::endpoint() . '/tts',
                [
                    'timeout'   => $timeout,
                    'sslverify' => true,
                    'stream'    => true,
                    'filename'  => $tmp,
                    'headers'   => [
                        'X-AGFO-Token' => $token,
                        'Content-Type' => 'application/json',
                        'Accept'       => $this->mime_for_format( $format ),
                    ],
                    'body'      => wp_json_encode( $body, JSON_UNESCAPED_UNICODE ),
                ]
            );

            if ( is_wp_error( $response ) ) {
                @unlink( $tmp ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
                return new WP_Error( 'agfo_ema_tts_http', 'EMA servisine ulaşılamadı: ' . agfo_redact_secrets( $response->get_error_message() ) );
            }

            $code = (int) wp_remote_retrieve_response_code( $response );
            if ( $code < 200 || $code >= 300 ) {
                $message = $this->read_error_file( $tmp );
                @unlink( $tmp ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
                return new WP_Error( 'agfo_ema_tts_' . $code, 'EMA TTS hatası (HTTP ' . $code . '): ' . $message );
            }

            $bytes = file_exists( $tmp ) ? (int) filesize( $tmp ) : 0;
            if ( $bytes < 1 ) {
                @unlink( $tmp ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
                return new WP_Error( 'agfo_ema_tts_empty', 'EMA boş ses çıktısı döndürdü.' );
            }

            $seconds = (float) wp_remote_retrieve_header( $response, 'x-agfo-seconds' );
            $cached  = '1' === (string) wp_remote_retrieve_header( $response, 'x-agfo-cached' );
            $chars   = mb_strlen( $body['text'], 'UTF-8' );

            return [
                'temp_file'    => $tmp,
                'mime'         => $this->mime_for_format( $format ),
                'bytes'        => $bytes,
                'provider_ref' => 'ema-' . substr( md5( $body['text'] . '|' . $body['speed'] ), 0, 12 ) . ( $cached ? '-cached' : '' ),
                'usage'        => [
                    'input_units'  => (float) $chars,
                    'output_units' => 1,
                    'unit_name'    => 'character',
                ],
                'cost_actual'  => 0.0,
                'metadata'     => [
                    'duration_ms' => $seconds > 0 ? (int) round( $seconds * 1000 ) : null,
                    'cached'      => $cached,
                    'model'       => 'ema-lightning',
                    'script'      => $script,
                ],
            ];
        }

        /** Job flag wins; jobs from other plugins follow the site default. */
        private static function wants_script( array $payload ): bool {
            if ( ! class_exists( 'AGFO_AIM_Speech_Script' ) ) {
                return false;
            }
            if ( array_key_exists( 'reading_script', $payload ) && null !== $payload['reading_script'] && '' !== $payload['reading_script'] ) {
                return (bool) $payload['reading_script'];
            }
            return AGFO_AIM_Speech_Script::enabled_by_default();
        }

        /* ── Catalog ─────────────────────────────────────── */

        /**
         * Static catalog in the same shape as AGFO_AIM_TTS_Catalog.
         *
         * @return array<string,mixed>
         */
        public static function catalog( bool $probe = false ): array {
            // The health probe is an HTTP call; page renders and chunk sizing skip it.
            $health = $probe ? self::health() : null;
            return [
                'provider'   => 'ema',
                'source'     => 'self_hosted',
                'cached'     => false,
                'has_key'    => '' !== self::token(),
                'fetched_at' => current_time( 'mysql' ),
                'models'     => [
                    [
                        'id'                    => 'ema-lightning',
                        'name'                  => 'EMA Lightning (yerel, Türkçe)',
                        'description'           => 'Sunucuda çalışan 8,6M parametreli Türkçe model. Ücretsiz; tek ses; yabancı kelimeler için telaffuz sözlüğü kullanılır.',
                        'recommended'           => true,
                        'supports_instructions' => false,
                        'max_characters'        => self::MAX_CHARS,
                        'languages'             => [ [ 'id' => 'tr', 'name' => 'Türkçe' ] ],
                        'voice_ids'             => [ 'ema' ],
                    ],
                ],
                'voices'     => [
                    [
                        'id'          => 'ema',
                        'name'        => 'EMA (Türkçe, kadın)',
                        'category'    => 'built-in',
                        'description' => 'Tek ses. Hız 0.7–1.4.',
                        'labels'      => [ 'language' => 'tr', 'gender' => 'female' ],
                        'preview_url' => '',
                        'model_ids'   => [ 'ema-lightning' ],
                        'is_owner'    => false,
                    ],
                ],
                'formats'    => [ 'mp3', 'wav' ],
                'truncated'  => false,
                'notice'     => null === $health
                    ? ( '' !== self::token() ? 'EMA servisi: ' . self::endpoint() . '. Bağlantıyı denemek için “Bağlantıyı test et”e basın.' : 'EMA servis token’ı tanımlı değil.' )
                    : ( is_wp_error( $health )
                        ? $health->get_error_message()
                        : 'EMA servisi çalışıyor (' . self::endpoint() . ', ' . (int) ( $health['lexicon_entries'] ?? 0 ) . ' sözlük girdisi).' ),
                'healthy'    => null === $health ? null : ! is_wp_error( $health ),
            ];
        }

        /* ── Helpers ─────────────────────────────────────── */

        /**
         * @return string|false
         */
        private function create_temp_file( string $filename ) {
            if ( ! function_exists( 'wp_tempnam' ) ) {
                $file_api = ABSPATH . 'wp-admin/includes/file.php';
                if ( is_readable( $file_api ) ) {
                    require_once $file_api;
                }
            }
            return function_exists( 'wp_tempnam' ) ? wp_tempnam( $filename ) : false;
        }

        private function mime_for_format( string $format ): string {
            return 'wav' === $format ? 'audio/wav' : 'audio/mpeg';
        }

        private function read_error_file( string $path ): string {
            if ( ! file_exists( $path ) ) {
                return 'Yanıt gövdesi yok.';
            }
            $raw  = (string) file_get_contents( $path, false, null, 0, 8192 );
            $json = json_decode( $raw, true );
            if ( is_array( $json ) && isset( $json['detail'] ) ) {
                return sanitize_text_field( is_scalar( $json['detail'] ) ? (string) $json['detail'] : wp_json_encode( $json['detail'] ) );
            }
            return '' !== $raw ? sanitize_text_field( wp_strip_all_tags( $raw ) ) : 'Yanıt gövdesi boş.';
        }
    }
}
