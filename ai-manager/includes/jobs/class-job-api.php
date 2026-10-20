<?php
/**
 * Public and AJAX job API.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Job_API' ) ) {
    final class AGFO_AIM_Job_API {
        public static function register_hooks(): void {
            add_action( 'wp_ajax_agfo_job_submit', [ __CLASS__, 'ajax_submit' ] );
            add_action( 'wp_ajax_agfo_job_status', [ __CLASS__, 'ajax_status' ] );
            add_action( 'wp_ajax_agfo_job_cancel', [ __CLASS__, 'ajax_cancel' ] );
        }

        public static function submit( string $capability, array $payload, array $args = [] ) {
            $capability = sanitize_key( $capability );
            if ( ! function_exists( 'agfo_ai_capability_exists' ) || ! agfo_ai_capability_exists( $capability ) ) {
                return new WP_Error( 'agfo_capability_unknown', 'Bilinmeyen AI yeteneği: ' . $capability );
            }
            if ( class_exists( 'AGFO_AIM_Kill_Switch' ) && ! AGFO_AIM_Kill_Switch::is_enabled( $capability ) ) {
                return new WP_Error( 'agfo_kill_switch', 'Bu AI yeteneği yönetici tarafından durduruldu.' );
            }

            $payload = self::sanitize_payload( $capability, $payload );
            if ( 'speech_synthesize' === $capability && ! empty( $payload['audio_effect'] ) && 'none' !== $payload['audio_effect'] && (int) ( $payload['effect_amount'] ?? 0 ) > 0 ) {
                if ( ! class_exists( 'AGFO_AIM_Audio_Effects' ) ) {
                    return new WP_Error( 'agfo_audio_effect_missing', 'Ses efekti motoru yüklenmedi.' );
                }
                $effect_status = AGFO_AIM_Audio_Effects::status();
                if ( empty( $effect_status['available'] ) ) {
                    return new WP_Error( 'agfo_audio_effect_unavailable', (string) ( $effect_status['reason'] ?? 'Ses efekti kullanılamıyor.' ) );
                }
            }
            $routes  = self::resolve_routes( $capability, $args );
            if ( is_wp_error( $routes ) ) {
                return $routes;
            }

            $first           = $routes[0];
            $primary_payload = self::payload_for_provider( $payload, $first['provider'] );
            $adapter         = AGFO_AIM_Adapter_Registry::get( $first['provider'] );
            if ( is_wp_error( $adapter ) ) {
                return $adapter;
            }
            $valid = $adapter->validate_payload( $capability, $primary_payload );
            if ( is_wp_error( $valid ) ) {
                return $valid;
            }

            // Reserve the highest viable route estimate so an explicit 429/5xx failover
            // cannot bypass the monthly budget ceiling.
            $estimate = [ 'cost' => 0.0, 'currency' => 'USD', 'snapshot' => [ 'routes' => [] ] ];
            foreach ( $routes as $route ) {
                $route_adapter = AGFO_AIM_Adapter_Registry::get( (string) $route['provider'] );
                if ( is_wp_error( $route_adapter ) ) {
                    continue;
                }
                $route_payload = self::payload_for_provider( $payload, (string) $route['provider'] );
                $route_valid   = $route_adapter->validate_payload( $capability, $route_payload );
                if ( is_wp_error( $route_valid ) ) {
                    continue;
                }
                $route_estimate = $route_adapter->estimate_cost( $capability, $route_payload, [ 'model' => (string) $route['model'] ] );
                $estimate['snapshot']['routes'][] = [
                    'provider' => (string) $route['provider'],
                    'model'    => (string) $route['model'],
                    'cost'     => (float) ( $route_estimate['cost'] ?? 0 ),
                    'details'  => (array) ( $route_estimate['snapshot'] ?? [] ),
                ];
                if ( (float) ( $route_estimate['cost'] ?? 0 ) >= (float) $estimate['cost'] ) {
                    $estimate['cost']     = (float) ( $route_estimate['cost'] ?? 0 );
                    $estimate['currency'] = (string) ( $route_estimate['currency'] ?? 'USD' );
                }
            }
            $draft = AGFO_AIM_Job_Store::create_draft(
                $capability,
                $payload,
                [
                    'provider'         => $first['provider'],
                    'model'            => $first['model'],
                    'routes'           => $routes,
                    'source_plugin'    => sanitize_key( (string) ( $args['source_plugin'] ?? 'agfo-ai-manager' ) ),
                    'idempotency_key'  => (string) ( $args['idempotency_key'] ?? '' ),
                    'created_by'       => absint( $args['created_by'] ?? get_current_user_id() ),
                    'max_attempts'     => absint( $args['max_attempts'] ?? 3 ),
                    'cost_estimate'    => (float) ( $estimate['cost'] ?? 0 ),
                    'currency'         => (string) ( $estimate['currency'] ?? 'USD' ),
                    'pricing_snapshot' => (array) ( $estimate['snapshot'] ?? [] ),
                ]
            );
            if ( is_wp_error( $draft ) ) {
                return $draft;
            }

            if ( 'draft' !== $draft['status'] ) {
                return self::public_job( $draft );
            }

            $reserved = AGFO_AIM_Budget::reserve(
                (int) $draft['id'],
                [
                    'cost_estimate' => (float) ( $estimate['cost'] ?? 0 ),
                    'provider'      => $first['provider'],
                    'capability'    => $capability,
                    'source_plugin' => (string) $draft['source_plugin'],
                ]
            );
            if ( is_wp_error( $reserved ) ) {
                AGFO_AIM_Job_Store::delete_draft( (int) $draft['id'] );
                return $reserved;
            }

            if ( ! AGFO_AIM_Job_Store::queue( (int) $draft['id'] ) ) {
                AGFO_AIM_Job_Store::delete_draft( (int) $draft['id'] );
                return new WP_Error( 'agfo_job_queue', 'AI işi kuyruğa alınamadı.' );
            }

            AGFO_AIM_Job_Worker::kick();
            return self::public_job( AGFO_AIM_Job_Store::get_by_id( (int) $draft['id'] ) );
        }

        public static function status( string $job_uuid, int $user_id = 0 ) {
            $job = AGFO_AIM_Job_Store::get( $job_uuid );
            if ( ! is_array( $job ) ) {
                return new WP_Error( 'agfo_job_not_found', 'AI işi bulunamadı.' );
            }
            $user_id = $user_id ?: get_current_user_id();
            if ( ! AGFO_AIM_Job_Store::can_view( $job, $user_id ) ) {
                return new WP_Error( 'agfo_job_forbidden', 'Bu AI işini görüntüleme yetkiniz yok.' );
            }
            return self::public_job( $job );
        }

        public static function cancel( string $job_uuid, int $user_id = 0 ) {
            $user_id = $user_id ?: get_current_user_id();
            if ( AGFO_AIM_Job_Store::cancel( $job_uuid, $user_id ) ) {
                return true;
            }
            return new WP_Error( 'agfo_job_cancel', 'İş iptal edilemedi; iş başlamış veya yetkiniz yetersiz olabilir.' );
        }

        public static function ajax_submit(): void {
            if ( ! is_user_logged_in() || ! current_user_can( 'manage_options' ) ) {
                wp_send_json_error( [ 'message' => 'Yetki yok.' ], 403 );
            }
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );

            $capability = sanitize_key( (string) ( $_POST['capability'] ?? '' ) );
            $payload_raw = isset( $_POST['payload'] ) ? wp_unslash( (string) $_POST['payload'] ) : '{}';
            $payload     = json_decode( $payload_raw, true );
            if ( ! is_array( $payload ) ) {
                wp_send_json_error( [ 'message' => 'Geçersiz iş verisi.' ], 400 );
            }

            $provider_models_raw = isset( $_POST['provider_models'] ) ? wp_unslash( (string) $_POST['provider_models'] ) : '{}';
            $provider_models     = json_decode( $provider_models_raw, true );
            if ( ! is_array( $provider_models ) ) {
                $provider_models = [];
            }

            $result = self::submit(
                $capability,
                $payload,
                [
                    'provider'        => sanitize_key( (string) ( $_POST['provider'] ?? '' ) ),
                    'model'           => sanitize_text_field( (string) ( $_POST['model'] ?? '' ) ),
                    'provider_models' => $provider_models,
                    'source_plugin'   => sanitize_key( (string) ( $_POST['source_plugin'] ?? 'agfo-ai-manager' ) ),
                    'created_by'      => get_current_user_id(),
                    'idempotency_key' => sanitize_text_field( (string) ( $_POST['idempotency_key'] ?? '' ) ),
                ]
            );
            if ( is_wp_error( $result ) ) {
                wp_send_json_error( [ 'message' => $result->get_error_message(), 'code' => $result->get_error_code() ], 400 );
            }
            wp_send_json_success( $result );
        }

        public static function ajax_status(): void {
            if ( ! is_user_logged_in() ) {
                wp_send_json_error( [ 'message' => 'Oturum gerekli.' ], 403 );
            }
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );
            $result = self::status( sanitize_text_field( (string) ( $_POST['job_uuid'] ?? '' ) ), get_current_user_id() );
            if ( is_wp_error( $result ) ) {
                wp_send_json_error( [ 'message' => $result->get_error_message(), 'code' => $result->get_error_code() ], 404 );
            }
            wp_send_json_success( $result );
        }

        public static function ajax_cancel(): void {
            if ( ! is_user_logged_in() ) {
                wp_send_json_error( [ 'message' => 'Oturum gerekli.' ], 403 );
            }
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );
            $result = self::cancel( sanitize_text_field( (string) ( $_POST['job_uuid'] ?? '' ) ), get_current_user_id() );
            if ( is_wp_error( $result ) ) {
                wp_send_json_error( [ 'message' => $result->get_error_message(), 'code' => $result->get_error_code() ], 400 );
            }
            wp_send_json_success( [ 'cancelled' => true ] );
        }

        /**
         * Public view of route resolution. Long-form speech needs to know every
         * route the job may fail over to, because the chunk size must fit the
         * SMALLEST per-request limit among them.
         *
         * @return array<int,array<string,string>>|WP_Error
         */
        public static function routes_for( string $capability, array $args = [] ) {
            return self::resolve_routes( sanitize_key( $capability ), $args );
        }

        private static function resolve_routes( string $capability, array $args ) {
            $available = function_exists( 'agfo_providers_for_capability' ) ? agfo_providers_for_capability( $capability, true ) : [];
            if ( ! $available ) {
                return new WP_Error( 'agfo_capability_no_provider', 'Bu yetenek için API anahtarı tanımlı sağlayıcı yok.' );
            }

            $routing  = function_exists( 'agfo_get_capability_routing' ) ? agfo_get_capability_routing() : [];
            $saved    = is_array( $routing[ $capability ] ?? null ) ? $routing[ $capability ] : [];
            $explicit = sanitize_key( (string) ( $args['provider'] ?? '' ) );
            if ( '' !== $explicit && ! isset( $available[ $explicit ] ) ) {
                return new WP_Error( 'agfo_capability_provider_unavailable', 'Seçilen sağlayıcı için geçerli API anahtarı veya yetenek desteği bulunamadı: ' . $explicit );
            }
            if ( '' !== $explicit && class_exists( 'AGFO_AIM_Adapter_Registry' ) && ! AGFO_AIM_Adapter_Registry::supports( $explicit, $capability ) ) {
                return new WP_Error( 'agfo_capability_adapter_unavailable', 'Seçilen sağlayıcı için çalıştırılabilir adaptör bulunamadı: ' . $explicit );
            }
            $primary = $explicit ?: sanitize_key( (string) ( $saved['provider'] ?? '' ) );
            if ( '' === $primary || ! isset( $available[ $primary ] ) ) {
                $primary = (string) array_key_first( $available );
            }

            $model = sanitize_text_field( (string) ( $args['model'] ?? '' ) );
            if ( '' === $model ) {
                $model = sanitize_text_field( (string) ( $saved['model'] ?? '' ) );
            }
            $provider_models = self::sanitize_provider_models( $args['provider_models'] ?? [] );

            $registry = agfo_api_registry();
            $routes   = [];
            $ordered  = array_unique( array_merge( [ $primary ], array_keys( $available ) ) );
            foreach ( $ordered as $provider ) {
                if ( ! isset( $available[ $provider ] ) || ! AGFO_AIM_Adapter_Registry::supports( $provider, $capability ) ) {
                    continue;
                }
                if ( ! empty( $provider_models[ $provider ] ) ) {
                    $route_model = $provider_models[ $provider ];
                } elseif ( $provider === $primary && '' !== $model ) {
                    $route_model = $model;
                } else {
                    $route_model = sanitize_text_field( (string) ( $registry[ $provider ]['default_models'][ $capability ] ?? $registry[ $provider ]['default_model'] ?? '' ) );
                }
                $routes[] = [ 'provider' => $provider, 'model' => $route_model ];
            }

            if ( ! $routes ) {
                return new WP_Error( 'agfo_capability_no_adapter', 'Bu yetenek için çalıştırılabilir adaptör bulunamadı.' );
            }
            return array_slice( $routes, 0, 3 );
        }

        private static function sanitize_payload( string $capability, array $payload ): array {
            if ( 'music_generate' === $capability ) {
                $clean = [
                    'prompt'                   => sanitize_textarea_field( (string) ( $payload['prompt'] ?? '' ) ),
                    'lyrics'                   => sanitize_textarea_field( (string) ( $payload['lyrics'] ?? '' ) ),
                    'duration'                 => max( 3, min( 600, absint( $payload['duration'] ?? 30 ) ) ),
                    'instrumental'             => ! empty( $payload['instrumental'] ),
                    'lyrics_optimizer'         => ! empty( $payload['lyrics_optimizer'] ),
                    'format'                   => sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) ),
                    'quality'                  => sanitize_key( (string) ( $payload['quality'] ?? '' ) ),
                    'seed'                     => isset( $payload['seed'] ) && '' !== (string) $payload['seed'] ? absint( $payload['seed'] ) : null,
                    'visibility'               => 'public' === (string) ( $payload['visibility'] ?? 'private' ) ? 'public' : 'private',
                    'publish_to_media_library' => ! empty( $payload['publish_to_media_library'] ),
                    'retention_days'           => max( 1, min( 3650, absint( $payload['retention_days'] ?? 30 ) ) ),
                    'title'                    => sanitize_text_field( (string) ( $payload['title'] ?? 'AGFO AI Music' ) ),
                ];
                return array_filter( $clean, static function ( $value ) { return null !== $value; } );
            }
            if ( 'speech_synthesize' !== $capability ) {
                return $payload;
            }
            $clean = [
                'text'                     => self::sanitize_speech_text( (string) ( $payload['text'] ?? '' ) ), // CHANGED 17.10.0: keeps %45 etc.
                'voice'                    => sanitize_text_field( (string) ( $payload['voice'] ?? '' ) ),
                'provider_voices'          => self::sanitize_provider_voices( $payload['provider_voices'] ?? [] ),
                'language'                 => sanitize_key( (string) ( $payload['language'] ?? '' ) ),
                'format'                   => sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) ),
                'quality'                  => sanitize_key( (string) ( $payload['quality'] ?? '' ) ),
                'speed'                    => (float) ( $payload['speed'] ?? 1.0 ),
                'instructions'             => sanitize_textarea_field( (string) ( $payload['instructions'] ?? '' ) ),
                'audio_effect'              => class_exists( 'AGFO_AIM_Audio_Effects' ) ? AGFO_AIM_Audio_Effects::sanitize_effect( $payload['audio_effect'] ?? 'none' ) : 'none',
                'effect_amount'             => class_exists( 'AGFO_AIM_Audio_Effects' ) ? AGFO_AIM_Audio_Effects::sanitize_amount( $payload['effect_amount'] ?? 35 ) : 0,
                'stability'                => isset( $payload['stability'] ) && '' !== (string) $payload['stability'] ? (float) $payload['stability'] : null,
                'similarity_boost'         => isset( $payload['similarity_boost'] ) && '' !== (string) $payload['similarity_boost'] ? (float) $payload['similarity_boost'] : null,
                'style'                    => isset( $payload['style'] ) && '' !== (string) $payload['style'] ? (float) $payload['style'] : null,
                'volume'                   => isset( $payload['volume'] ) && '' !== (string) $payload['volume'] ? (float) $payload['volume'] : null,
                'pitch'                    => isset( $payload['pitch'] ) && '' !== (string) $payload['pitch'] ? (int) $payload['pitch'] : null,
                'emotion'                  => sanitize_key( (string) ( $payload['emotion'] ?? '' ) ),
                'language_boost'           => sanitize_text_field( (string) ( $payload['language_boost'] ?? '' ) ),
                'sample_rate'              => isset( $payload['sample_rate'] ) && '' !== (string) $payload['sample_rate'] ? absint( $payload['sample_rate'] ) : null,
                'bitrate'                  => isset( $payload['bitrate'] ) && '' !== (string) $payload['bitrate'] ? absint( $payload['bitrate'] ) : null,
                'channel'                  => isset( $payload['channel'] ) && '' !== (string) $payload['channel'] ? absint( $payload['channel'] ) : null,
                'pause_ms'                 => isset( $payload['pause_ms'] ) && '' !== (string) $payload['pause_ms'] ? min( 2000, absint( $payload['pause_ms'] ) ) : null,
                'reading_script'           => isset( $payload['reading_script'] ) && '' !== $payload['reading_script'] ? filter_var( $payload['reading_script'], FILTER_VALIDATE_BOOLEAN ) : null, // CHANGED 17.12.0: PHP false kept
                'script_ready'             => ! empty( $payload['script_ready'] ) && filter_var( $payload['script_ready'], FILTER_VALIDATE_BOOLEAN ) ? true : null,
                'paragraph_pause_ms'       => isset( $payload['paragraph_pause_ms'] ) && '' !== (string) $payload['paragraph_pause_ms'] ? min( 3000, absint( $payload['paragraph_pause_ms'] ) ) : null,
                'visibility'               => 'public' === (string) ( $payload['visibility'] ?? 'private' ) ? 'public' : 'private',
                'publish_to_media_library' => ! empty( $payload['publish_to_media_library'] ),
                'retention_days'           => max( 1, min( 3650, absint( $payload['retention_days'] ?? 30 ) ) ),
                'title'                    => sanitize_text_field( (string) ( $payload['title'] ?? 'AGFO AI Speech' ) ),
            ];
            if ( ! empty( $clean['audio_effect'] ) && 'none' !== $clean['audio_effect'] ) {
                $clean['format'] = 'mp3';
            }
            if ( array_key_exists( 'use_speaker_boost', $payload ) && '' !== (string) $payload['use_speaker_boost'] ) {
                $clean['use_speaker_boost'] = filter_var( $payload['use_speaker_boost'], FILTER_VALIDATE_BOOLEAN, FILTER_NULL_ON_FAILURE );
            }
            return array_filter( $clean, static function ( $value ) { return null !== $value; } );
        }

        /**
         * NEW 17.10.0: plain-text sanitiser for speech. sanitize_textarea_field() deletes
         * "%" followed by two hex digits as if it were URL encoding, so "%45" and "%92"
         * vanished from narrated text. Same protections otherwise: valid UTF-8, no tags,
         * no control characters; line breaks are kept.
         */
        public static function sanitize_speech_text( string $text ): string {
            $text = wp_check_invalid_utf8( $text );
            $text = str_replace( [ "\r\n", "\r" ], "\n", $text );
            $text = wp_strip_all_tags( $text, false );
            $text = (string) preg_replace( '/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', $text );
            $text = (string) preg_replace( '/[ \t]+\n/u', "\n", $text );
            return trim( $text );
        }

        public static function payload_for_provider( array $payload, string $provider ): array {
            $provider = sanitize_key( $provider );
            $voices   = isset( $payload['provider_voices'] ) && is_array( $payload['provider_voices'] ) ? $payload['provider_voices'] : [];
            if ( ! empty( $voices[ $provider ] ) ) {
                $payload['voice'] = sanitize_text_field( (string) $voices[ $provider ] );
            }
            return $payload;
        }

        private static function sanitize_provider_models( $models ): array {
            if ( ! is_array( $models ) ) {
                return [];
            }
            $clean = [];
            foreach ( $models as $provider => $model ) {
                $provider = sanitize_key( (string) $provider );
                $model    = sanitize_text_field( (string) $model );
                if ( '' !== $provider && '' !== $model ) {
                    $clean[ $provider ] = $model;
                }
            }
            return $clean;
        }

        private static function sanitize_provider_voices( $voices ): array {
            if ( ! is_array( $voices ) ) {
                return [];
            }
            $clean = [];
            foreach ( $voices as $provider => $voice ) {
                $provider = sanitize_key( (string) $provider );
                $voice    = sanitize_text_field( (string) $voice );
                if ( '' !== $provider && '' !== $voice ) {
                    $clean[ $provider ] = $voice;
                }
            }
            return $clean;
        }

        private static function public_job( ?array $job ): array {
            if ( ! is_array( $job ) ) {
                return [];
            }
            $out = [
                'job_uuid'      => (string) $job['job_uuid'],
                'capability'    => (string) $job['capability'],
                'provider'      => (string) $job['provider'],
                'model'         => (string) $job['model'],
                'status'        => (string) $job['status'],
                'attempts'      => (int) $job['attempts'],
                'max_attempts'  => (int) $job['max_attempts'],
                'cost_estimate' => (float) $job['cost_estimate'],
                'cost_actual'   => (float) $job['cost_actual'],
                'currency'      => (string) $job['currency'],
                'created_at'    => (string) $job['created_at'],
                'updated_at'    => (string) $job['updated_at'],
                'error_code'    => (string) $job['error_code'],
                'error_message' => (string) $job['error_message'],
            ];
            if ( 'complete' === $job['status'] && ! empty( $job['result']['asset_uuid'] ) ) {
                $out['asset_uuid'] = (string) $job['result']['asset_uuid'];
                $out['asset_url']  = agfo_asset_url( $out['asset_uuid'], false );
                $out['download_url'] = agfo_asset_url( $out['asset_uuid'], true );
                $out['mime']       = (string) ( $job['result']['mime'] ?? '' );
                $out['bytes']      = (int) ( $job['result']['bytes'] ?? 0 );
                $out['attachment_id'] = ! empty( $job['result']['attachment_id'] ) ? (int) $job['result']['attachment_id'] : null;
                if ( ! empty( $job['result']['metadata'] ) && is_array( $job['result']['metadata'] ) ) {
                    $out['metadata'] = $job['result']['metadata'];
                }
                if ( $out['attachment_id'] ) {
                    $attachment_url = wp_get_attachment_url( $out['attachment_id'] );
                    if ( is_string( $attachment_url ) && '' !== $attachment_url ) {
                        $out['attachment_url'] = $attachment_url;
                    }
                }
            }
            return $out;
        }
    }
}

if ( ! function_exists( 'agfo_job_submit' ) ) {
    function agfo_job_submit( string $capability, array $payload, array $args = [] ) {
        return class_exists( 'AGFO_AIM_Job_API' ) ? AGFO_AIM_Job_API::submit( $capability, $payload, $args ) : new WP_Error( 'agfo_job_api_missing', 'AGFO AI iş API yüklenmedi.' );
    }
}

if ( ! function_exists( 'agfo_job_status' ) ) {
    function agfo_job_status( string $job_uuid, int $user_id = 0 ) {
        return class_exists( 'AGFO_AIM_Job_API' ) ? AGFO_AIM_Job_API::status( $job_uuid, $user_id ) : new WP_Error( 'agfo_job_api_missing', 'AGFO AI iş API yüklenmedi.' );
    }
}

if ( ! function_exists( 'agfo_job_cancel' ) ) {
    function agfo_job_cancel( string $job_uuid, int $user_id = 0 ) {
        return class_exists( 'AGFO_AIM_Job_API' ) ? AGFO_AIM_Job_API::cancel( $job_uuid, $user_id ) : new WP_Error( 'agfo_job_api_missing', 'AGFO AI iş API yüklenmedi.' );
    }
}

if ( ! function_exists( 'agfo_speech_synthesize' ) ) {
    function agfo_speech_synthesize( string $text, array $options = [] ) {
        $payload         = $options;
        $payload['text'] = $text;
        $args            = [
            'provider'        => sanitize_key( (string) ( $options['provider'] ?? '' ) ),
            'model'           => sanitize_text_field( (string) ( $options['model'] ?? '' ) ),
            'provider_models' => is_array( $options['provider_models'] ?? null ) ? $options['provider_models'] : [],
            'source_plugin'   => sanitize_key( (string) ( $options['source_plugin'] ?? 'agfo-ai-manager' ) ),
            'idempotency_key' => sanitize_text_field( (string) ( $options['idempotency_key'] ?? '' ) ),
            'created_by'      => absint( $options['created_by'] ?? get_current_user_id() ),
        ];
        unset( $payload['provider'], $payload['model'], $payload['provider_models'], $payload['source_plugin'], $payload['idempotency_key'], $payload['created_by'] );
        return agfo_job_submit( 'speech_synthesize', $payload, $args );
    }
}

if ( ! function_exists( 'agfo_music_generate' ) ) {
    function agfo_music_generate( string $prompt, array $options = [] ) {
        $payload           = $options;
        $payload['prompt'] = $prompt;
        $args              = [
            'provider'        => sanitize_key( (string) ( $options['provider'] ?? '' ) ),
            'model'           => sanitize_text_field( (string) ( $options['model'] ?? '' ) ),
            'provider_models' => is_array( $options['provider_models'] ?? null ) ? $options['provider_models'] : [],
            'source_plugin'   => sanitize_key( (string) ( $options['source_plugin'] ?? 'agfo-ai-manager' ) ),
            'idempotency_key' => sanitize_text_field( (string) ( $options['idempotency_key'] ?? '' ) ),
            'created_by'      => absint( $options['created_by'] ?? get_current_user_id() ),
        ];
        unset( $payload['provider'], $payload['model'], $payload['provider_models'], $payload['source_plugin'], $payload['idempotency_key'], $payload['created_by'] );
        return agfo_job_submit( 'music_generate', $payload, $args );
    }
}

