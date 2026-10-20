<?php
/**
 * AI Editor speech endpoints (NEW 17.12.0): EMA narration jobs, reading-script preview and the
 * shared pronunciation lexicon, for the AGFO AI Editor desktop app.
 *
 * Same authentication as the other /editor routes (connection key or application password,
 * AGFO_AIM_Editor_API::can_use). Changing the shared lexicon additionally needs manage_options,
 * because it affects every site that uses the TTS server.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Editor_Speech_API' ) ) {
    final class AGFO_AIM_Editor_Speech_API {
        const JOB_RE = '(?P<job>[A-Za-z0-9\-]{8,64})';

        public static function register_hooks(): void {
            add_action( 'rest_api_init', [ __CLASS__, 'register_routes' ] );
        }

        public static function register_routes(): void {
            if ( ! class_exists( 'AGFO_AIM_Editor_API' ) || ! AGFO_AIM_Editor_API::enabled() ) {
                return;
            }
            $ns   = AGFO_AIM_Editor_API::NAMESPACE_V1;
            $auth = [ 'AGFO_AIM_Editor_API', 'can_use' ];
            register_rest_route( $ns, '/editor/speech', [
                'methods'             => 'POST',
                'callback'            => [ __CLASS__, 'rest_submit' ],
                'permission_callback' => $auth,
            ] );
            register_rest_route( $ns, '/editor/speech/' . self::JOB_RE, [
                'methods'             => 'GET',
                'callback'            => [ __CLASS__, 'rest_status' ],
                'permission_callback' => $auth,
            ] );
            register_rest_route( $ns, '/editor/speech/' . self::JOB_RE . '/audio', [
                'methods'             => 'GET',
                'callback'            => [ __CLASS__, 'rest_audio' ],
                'permission_callback' => $auth,
            ] );
            register_rest_route( $ns, '/editor/speech-script', [
                'methods'             => 'POST',
                'callback'            => [ __CLASS__, 'rest_script' ],
                'permission_callback' => $auth,
            ] );
            register_rest_route( $ns, '/editor/lexicon', [
                [
                    'methods'             => 'GET',
                    'callback'            => [ __CLASS__, 'rest_lexicon_list' ],
                    'permission_callback' => $auth,
                ],
                [
                    'methods'             => 'POST',
                    'callback'            => [ __CLASS__, 'rest_lexicon_change' ],
                    'permission_callback' => [ __CLASS__, 'can_edit_lexicon' ],
                ],
            ] );
            register_rest_route( $ns, '/editor/lexicon/listen', [
                'methods'             => 'POST',
                'callback'            => [ __CLASS__, 'rest_lexicon_listen' ],
                'permission_callback' => $auth,
            ] );
        }

        /** @return bool|WP_Error */
        public static function can_edit_lexicon() {
            $ok = AGFO_AIM_Editor_API::can_use();
            if ( true !== $ok ) {
                return $ok;
            }
            if ( ! current_user_can( 'manage_options' ) ) {
                return new WP_Error( 'agfo_editor_lexicon_forbidden', 'Ortak telaffuz sözlüğünü yalnız site yöneticisi değiştirebilir.', [ 'status' => 403 ] );
            }
            return true;
        }

        /** Capability summary for /editor/info. */
        public static function info(): array {
            $ema = class_exists( 'AGFO_AIM_Adapter_EMA' );
            return [
                'speech_ready'          => $ema && '' !== AGFO_AIM_Adapter_EMA::token(),
                'speech_provider'       => 'ema',
                'speech_max_chars'      => $ema ? AGFO_AIM_Adapter_EMA::MAX_CHARS : 0,
                'reading_script'        => class_exists( 'AGFO_AIM_Speech_Script' ),
                'reading_script_default'=> class_exists( 'AGFO_AIM_Speech_Script' ) && AGFO_AIM_Speech_Script::enabled_by_default(),
                'lexicon_edit'          => current_user_can( 'manage_options' ),
            ];
        }

        private static function ready() {
            if ( ! class_exists( 'AGFO_AIM_Adapter_EMA' ) || ! class_exists( 'AGFO_AIM_Job_API' ) ) {
                return self::error( 'agfo_editor_speech_missing', 'Bu sitede EMA seslendirme bileşenleri yüklü değil.', 500 );
            }
            if ( '' === AGFO_AIM_Adapter_EMA::token() ) {
                return self::error( 'agfo_editor_speech_token', 'Sitede EMA servis token’ı tanımlı değil (AI Manager › Sağlayıcılar › EMA Lightning).', 400 );
            }
            return true;
        }

        public static function rest_submit( $request ) {
            $ready = self::ready();
            if ( true !== $ready ) {
                return $ready;
            }
            $text = AGFO_AIM_Job_API::sanitize_speech_text( (string) $request->get_param( 'text' ) );
            if ( '' === $text ) {
                return self::error( 'agfo_editor_speech_empty', 'Seslendirilecek metin boş.', 400 );
            }
            if ( mb_strlen( $text, 'UTF-8' ) > AGFO_AIM_Adapter_EMA::MAX_CHARS ) {
                return self::error( 'agfo_editor_speech_long', 'Metin ' . number_format_i18n( AGFO_AIM_Adapter_EMA::MAX_CHARS ) . ' karakteri aşıyor; bölerek seslendirin.', 400 );
            }
            $format = 'wav' === sanitize_key( (string) $request->get_param( 'format' ) ) ? 'wav' : 'mp3';
            $speed  = (float) ( $request->get_param( 'speed' ) ?: 1.0 );
            $script_ready = filter_var( $request->get_param( 'script_ready' ), FILTER_VALIDATE_BOOLEAN );
            $payload = [
                'text'                     => $text,
                'voice'                    => 'ema',
                'provider_voices'          => [ 'ema' => 'ema' ],
                'language'                 => 'tr',
                'format'                   => $format,
                'speed'                    => max( 0.7, min( 1.4, $speed ) ),
                'reading_script'           => $script_ready ? false : filter_var( $request->get_param( 'reading_script' ) ?? true, FILTER_VALIDATE_BOOLEAN ),
                'script_ready'             => $script_ready,
                'retention_days'           => 30,
                'publish_to_media_library' => false,
                'visibility'               => 'private',
                'title'                    => sanitize_text_field( (string) ( $request->get_param( 'title' ) ?: 'AGFO AI Editor' ) ),
            ];
            foreach ( [ 'pause_ms', 'paragraph_pause_ms' ] as $key ) {
                $value = $request->get_param( $key );
                if ( null !== $value && '' !== (string) $value ) {
                    $payload[ $key ] = absint( $value );
                }
            }
            $job = AGFO_AIM_Job_API::submit(
                'speech_synthesize',
                $payload,
                [
                    'provider'        => 'ema',
                    'model'           => 'ema-lightning',
                    'source_plugin'   => 'agfo-ai-editor',
                    'created_by'      => get_current_user_id(),
                    'idempotency_key' => substr( sanitize_text_field( (string) $request->get_param( 'request_id' ) ), 0, 80 ),
                ]
            );
            if ( is_wp_error( $job ) ) {
                return self::error( $job->get_error_code(), $job->get_error_message(), 400 );
            }
            return new WP_REST_Response( self::public_job( $job ), 202 );
        }

        public static function rest_status( $request ) {
            $job = AGFO_AIM_Job_API::status( (string) $request['job'], get_current_user_id() );
            if ( is_wp_error( $job ) ) {
                return self::error( $job->get_error_code(), $job->get_error_message(), 404 );
            }
            // Low-traffic sites: WP-Cron only runs on visits, so a status poll nudges the queue.
            if ( in_array( $job['status'] ?? '', [ 'queued', 'retry' ], true ) && class_exists( 'AGFO_AIM_Job_Worker' ) ) {
                AGFO_AIM_Job_Worker::kick();
            }
            return new WP_REST_Response( self::public_job( $job ), 200 );
        }

        /** Streams the finished audio file (the editor cannot use the cookie-bound admin-post link). */
        public static function rest_audio( $request ) {
            $job = AGFO_AIM_Job_API::status( (string) $request['job'], get_current_user_id() );
            if ( is_wp_error( $job ) ) {
                return self::error( $job->get_error_code(), $job->get_error_message(), 404 );
            }
            if ( 'complete' !== ( $job['status'] ?? '' ) || empty( $job['asset_uuid'] ) ) {
                return self::error( 'agfo_editor_speech_not_ready', 'Ses henüz hazır değil.', 409 );
            }
            $asset = AGFO_AIM_Asset_Store::get( (string) $job['asset_uuid'] );
            if ( ! is_array( $asset ) || ! AGFO_AIM_Asset_Delivery::can_access( $asset, get_current_user_id() ) ) {
                return self::error( 'agfo_editor_speech_forbidden', 'Bu sese erişim yetkiniz yok.', 403 );
            }
            $path = wp_normalize_path( (string) $asset['storage_path'] );
            if ( ! AGFO_AIM_Asset_Store::path_is_inside_store( $path ) || ! is_file( $path ) || ! is_readable( $path ) ) {
                return self::error( 'agfo_editor_speech_missing_file', 'Ses dosyası bulunamadı (saklama süresi dolmuş olabilir).', 404 );
            }
            $ext = strtolower( pathinfo( $path, PATHINFO_EXTENSION ) );
            nocache_headers();
            header( 'Content-Type: ' . (string) $asset['mime'] );
            header( 'Content-Length: ' . (string) filesize( $path ) );
            header( 'X-Content-Type-Options: nosniff' );
            header( 'Content-Disposition: attachment; filename="agfo-ses-' . preg_replace( '/[^a-zA-Z0-9_-]/', '', (string) $request['job'] ) . '.' . $ext . '"' );
            $handle = fopen( $path, 'rb' );
            if ( false === $handle ) {
                return self::error( 'agfo_editor_speech_stream', 'Ses dosyası açılamadı.', 500 );
            }
            while ( ! feof( $handle ) ) {
                echo fread( $handle, 1024 * 1024 ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
                flush();
            }
            fclose( $handle );
            exit;
        }

        public static function rest_script( $request ) {
            if ( ! class_exists( 'AGFO_AIM_Speech_Script' ) ) {
                return self::error( 'agfo_editor_script_missing', 'Okuma metni bileşeni yüklü değil.', 500 );
            }
            $text = AGFO_AIM_Job_API::sanitize_speech_text( (string) $request->get_param( 'text' ) );
            if ( '' === $text ) {
                return self::error( 'agfo_editor_script_empty', 'Metin boş.', 400 );
            }
            if ( mb_strlen( $text, 'UTF-8' ) > 60000 ) {
                return self::error( 'agfo_editor_script_long', 'Metin 60.000 karakteri aşıyor.', 400 );
            }
            if ( function_exists( 'set_time_limit' ) ) {
                @set_time_limit( 900 ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
            }
            $base = class_exists( 'AGFO_AIM_Adapter_EMA' ) && '' !== AGFO_AIM_Adapter_EMA::token() ? AGFO_AIM_Adapter_EMA::apply_server_lexicon( $text ) : $text;
            $res  = AGFO_AIM_Speech_Script::prepare( is_wp_error( $base ) ? $text : $base, [ 'fail_if_none' => true ] );
            if ( is_wp_error( $res ) ) {
                return self::error( $res->get_error_code(), $res->get_error_message(), 400 );
            }
            return new WP_REST_Response( $res, 200 );
        }

        public static function rest_lexicon_list( $request ) {
            $ready = self::ready();
            if ( true !== $ready ) {
                return $ready;
            }
            $res = AGFO_AIM_Adapter_EMA::service_call( 'GET', '/lexicon' );
            if ( is_wp_error( $res ) ) {
                return self::error( $res->get_error_code(), $res->get_error_message(), 502 );
            }
            $res['can_edit'] = current_user_can( 'manage_options' );
            return new WP_REST_Response( $res, 200 );
        }

        public static function rest_lexicon_change( $request ) {
            $ready = self::ready();
            if ( true !== $ready ) {
                return $ready;
            }
            $op      = sanitize_key( (string) $request->get_param( 'op' ) );
            $word    = self::line( (string) $request->get_param( 'word' ), 80 );
            $reading = self::line( (string) $request->get_param( 'reading' ), 160 );
            if ( '' === $word ) {
                return self::error( 'agfo_editor_lexicon_word', 'Kelime gerekli.', 400 );
            }
            if ( 'save' === $op ) {
                if ( '' === $reading ) {
                    return self::error( 'agfo_editor_lexicon_reading', 'Okunuş gerekli.', 400 );
                }
                $res = AGFO_AIM_Adapter_EMA::service_call( 'POST', '/lexicon/entry', [ 'word' => $word, 'reading' => $reading ] );
            } elseif ( in_array( $op, [ 'delete', 'restore' ], true ) ) {
                $res = AGFO_AIM_Adapter_EMA::service_call( 'POST', '/lexicon/delete', [ 'word' => $word, 'reading' => 'restore' === $op ? '__restore__' : '' ] );
            } else {
                return self::error( 'agfo_editor_lexicon_op', 'Geçersiz işlem (save, delete, restore).', 400 );
            }
            if ( is_wp_error( $res ) ) {
                return self::error( $res->get_error_code(), $res->get_error_message(), 502 );
            }
            return new WP_REST_Response( $res, 200 );
        }

        public static function rest_lexicon_listen( $request ) {
            $ready = self::ready();
            if ( true !== $ready ) {
                return $ready;
            }
            $audio = AGFO_AIM_Adapter_EMA::listen( self::line( (string) $request->get_param( 'reading' ), 300 ) );
            if ( is_wp_error( $audio ) ) {
                return self::error( $audio->get_error_code(), $audio->get_error_message(), 502 );
            }
            return new WP_REST_Response( [ 'mime' => 'audio/mpeg', 'audio_base64' => base64_encode( $audio ) ], 200 ); // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions.obfuscation_base64_encode
        }

        /* ── helpers ─────────────────────────────────────── */

        private static function public_job( array $job ): array {
            $out = [
                'job'        => (string) ( $job['job_uuid'] ?? '' ),
                'status'     => (string) ( $job['status'] ?? '' ),
                'provider'   => (string) ( $job['provider'] ?? '' ),
                'error'      => (string) ( $job['error_message'] ?? '' ),
                'created_at' => (string) ( $job['created_at'] ?? '' ),
            ];
            if ( 'complete' === $out['status'] ) {
                $meta              = is_array( $job['metadata'] ?? null ) ? $job['metadata'] : [];
                $out['mime']        = (string) ( $job['mime'] ?? '' );
                $out['bytes']       = (int) ( $job['bytes'] ?? 0 );
                $out['duration_ms'] = isset( $meta['duration_ms'] ) ? (int) $meta['duration_ms'] : null;
                $out['script']      = is_array( $meta['script'] ?? null ) ? $meta['script'] : null;
            }
            return $out;
        }

        private static function line( string $value, int $max ): string {
            $value = wp_check_invalid_utf8( $value );
            $value = wp_strip_all_tags( $value, true );
            $value = trim( (string) preg_replace( '/[\x00-\x1F\x7F]+|\s+/u', ' ', $value ) );
            return mb_substr( $value, 0, $max, 'UTF-8' );
        }

        private static function error( string $code, string $message, int $status ): WP_Error {
            return new WP_Error( $code, $message, [ 'status' => $status ] );
        }
    }
}
