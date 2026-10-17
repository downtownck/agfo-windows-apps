<?php
/**
 * Single-step background job worker.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Job_Worker' ) ) {
    final class AGFO_AIM_Job_Worker {
        public static function register_hooks(): void {
            add_action( 'agfo_ai_run_jobs', [ __CLASS__, 'run' ], 10, 1 );
            add_action( 'agfo_ai_cleanup_assets', [ __CLASS__, 'cleanup_assets' ] );
        }

        public static function kick(): void {
            $args = [ 'kick' ];
            if ( ! wp_next_scheduled( 'agfo_ai_run_jobs', $args ) ) {
                wp_schedule_single_event( time() + 1, 'agfo_ai_run_jobs', $args );
            }
            if ( function_exists( 'spawn_cron' ) ) {
                spawn_cron( time() );
            }
        }

        public static function run( $trigger = null ): void {
            if ( ! class_exists( 'AGFO_AIM_Job_Store' ) ) {
                return;
            }

            $max = (int) apply_filters( 'agfo_ai_worker_batch_size', 1 );
            for ( $i = 0; $i < max( 1, min( 10, $max ) ); $i++ ) {
                $job = AGFO_AIM_Job_Store::claim_next();
                if ( ! is_array( $job ) ) {
                    break;
                }
                self::process( $job );
            }
        }

        private static function process( array $job ): void {
            $job_id     = (int) $job['id'];
            $capability = sanitize_key( (string) $job['capability'] );

            if ( class_exists( 'AGFO_AIM_Kill_Switch' ) && ! AGFO_AIM_Kill_Switch::is_enabled( $capability ) ) {
                AGFO_AIM_Job_Store::fail( $job_id, new WP_Error( 'agfo_kill_switch', 'Bu AI yeteneği yönetici tarafından durduruldu.' ), false );
                AGFO_AIM_Budget::settle( $job_id, 0.0 );
                return;
            }

            $routes = is_array( $job['routes'] ?? null ) ? $job['routes'] : [];
            if ( ! $routes ) {
                $routes = [ [ 'provider' => $job['provider'], 'model' => $job['model'] ] ];
            }

            $last_error = null;
            foreach ( $routes as $route_index => $route ) {
                $provider = sanitize_key( (string) ( $route['provider'] ?? '' ) );
                $model    = sanitize_text_field( (string) ( $route['model'] ?? '' ) );
                if ( '' === $provider ) {
                    continue;
                }

                $adapter = AGFO_AIM_Adapter_Registry::get( $provider );
                if ( is_wp_error( $adapter ) || ! $adapter->supports( $capability ) ) {
                    $last_error = is_wp_error( $adapter ) ? $adapter : new WP_Error( 'agfo_adapter_capability', 'Adaptör yeteneği desteklemiyor.' );
                    continue;
                }

                AGFO_AIM_Job_Store::update_route( $job_id, $provider, $model );
                $request_payload = is_array( $job['request'] ) ? $job['request'] : [];
                if ( class_exists( 'AGFO_AIM_Job_API' ) ) {
                    $request_payload = AGFO_AIM_Job_API::payload_for_provider( $request_payload, $provider );
                }
                $validation = $adapter->validate_payload( $capability, $request_payload );
                if ( is_wp_error( $validation ) ) {
                    $last_error = $validation;
                    continue;
                }
                $result = $adapter->dispatch(
                    $capability,
                    $request_payload,
                    [
                        'model'         => $model,
                        'source_plugin' => $job['source_plugin'],
                        'job_uuid'      => $job['job_uuid'],
                    ]
                );

                if ( is_wp_error( $result ) ) {
                    $last_error = $result;
                    if ( self::failover_allowed( $result ) && isset( $routes[ $route_index + 1 ] ) ) {
                        continue;
                    }
                    break;
                }

                $route_estimate = self::route_estimate( $job, $provider, $model );
                $actual_cost   = isset( $result['cost_actual'] ) && null !== $result['cost_actual']
                    ? (float) $result['cost_actual']
                    : $route_estimate;
                $usage         = is_array( $result['usage'] ?? null ) ? $result['usage'] : [];

                AGFO_AIM_Job_Store::mark_storing( $job_id, (string) ( $result['provider_ref'] ?? '' ) );
                $payload      = is_array( $job['request'] ) ? $job['request'] : [];
                $audio_effect = class_exists( 'AGFO_AIM_Audio_Effects' ) ? AGFO_AIM_Audio_Effects::sanitize_effect( $payload['audio_effect'] ?? 'none' ) : 'none';
                $effect_amount = class_exists( 'AGFO_AIM_Audio_Effects' ) ? AGFO_AIM_Audio_Effects::sanitize_amount( $payload['effect_amount'] ?? 35 ) : 0;

                if ( 'speech_synthesize' === $capability && 'none' !== $audio_effect && $effect_amount > 0 ) {
                    $processed = AGFO_AIM_Audio_Effects::apply(
                        (string) ( $result['temp_file'] ?? '' ),
                        (string) ( $result['mime'] ?? 'application/octet-stream' ),
                        $audio_effect,
                        $effect_amount
                    );
                    if ( is_wp_error( $processed ) ) {
                        if ( ! empty( $result['temp_file'] ) && is_file( (string) $result['temp_file'] ) ) {
                            @unlink( (string) $result['temp_file'] ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
                        }
                        AGFO_AIM_Job_Store::fail( $job_id, $processed, false );
                        AGFO_AIM_Budget::settle( $job_id, $actual_cost );
                        AGFO_AIM_Usage::record(
                            [
                                'provider'      => $provider,
                                'model'         => $model,
                                'capability'    => $capability,
                                'source_plugin' => $job['source_plugin'],
                                'input_units'   => (float) ( $usage['input_units'] ?? 0 ),
                                'output_units'  => (float) ( $usage['output_units'] ?? 0 ),
                                'unit_name'     => (string) ( $usage['unit_name'] ?? 'call' ),
                                'cost_estimate' => $route_estimate,
                                'cost_actual'   => $actual_cost,
                                'currency'      => (string) $job['currency'],
                            ]
                        );
                        do_action( 'agfo_ai_job_failed', $job['job_uuid'], $processed, $job, false );
                        return;
                    }
                    $result['temp_file'] = (string) $processed['temp_file'];
                    $result['mime']      = (string) $processed['mime'];
                    $result['metadata']  = array_merge(
                        is_array( $result['metadata'] ?? null ) ? $result['metadata'] : [],
                        [
                            'audio_effect'  => (string) $processed['effect'],
                            'effect_amount' => (int) $processed['amount'],
                            'processed_by'  => 'ffmpeg',
                        ]
                    );
                }

                $asset = AGFO_AIM_Asset_Store::store_temp_file(
                    $job_id,
                    (string) $result['temp_file'],
                    [
                        'mime'                     => (string) ( $result['mime'] ?? 'application/octet-stream' ),
                        'kind'                     => 'music_generate' === $capability ? 'music' : 'audio',
                        'visibility'               => (string) ( $payload['visibility'] ?? 'private' ),
                        'retention_days'           => absint( $payload['retention_days'] ?? 30 ),
                        'publish_to_media_library' => ! empty( $payload['publish_to_media_library'] ),
                        'title'                    => sanitize_text_field( (string) ( $payload['title'] ?? ( 'music_generate' === $capability ? 'AGFO AI Music' : 'AGFO AI Speech' ) ) ),
                        'created_by'               => (int) $job['created_by'],
                        'provenance'               => [
                            'generated_by' => 'agfo-ai-manager',
                            'version'      => defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '',
                            'capability'   => $capability,
                            'provider'     => $provider,
                            'model'        => $model,
                            'job_uuid'     => $job['job_uuid'],
                            'source_plugin'=> $job['source_plugin'],
                            'audio_effect' => $audio_effect,
                            'effect_amount'=> $effect_amount,
                            'processed_by' => ( 'speech_synthesize' === $capability && 'none' !== $audio_effect && $effect_amount > 0 ) ? 'ffmpeg' : 'provider',
                            'created_at'   => current_time( 'mysql' ),
                        ],
                    ]
                );

                if ( is_wp_error( $asset ) ) {
                    $last_error = $asset;
                    break;
                }

                AGFO_AIM_Job_Store::complete(
                    $job_id,
                    [
                        'asset_uuid'    => (string) $asset['asset_uuid'],
                        'mime'          => (string) $asset['mime'],
                        'bytes'         => (int) $asset['bytes'],
                        'attachment_id' => ! empty( $asset['attachment_id'] ) ? (int) $asset['attachment_id'] : null,
                        'metadata'      => is_array( $result['metadata'] ?? null ) ? $result['metadata'] : [],
                    ],
                    $actual_cost
                );
                AGFO_AIM_Budget::settle( $job_id, $actual_cost );

                AGFO_AIM_Usage::record(
                    [
                        'provider'      => $provider,
                        'model'         => $model,
                        'capability'    => $capability,
                        'source_plugin' => $job['source_plugin'],
                        'input_units'   => (float) ( $usage['input_units'] ?? 0 ),
                        'output_units'  => (float) ( $usage['output_units'] ?? 0 ),
                        'unit_name'     => (string) ( $usage['unit_name'] ?? 'call' ),
                        'cost_estimate' => $route_estimate,
                        'cost_actual'   => $actual_cost,
                        'currency'      => (string) $job['currency'],
                    ]
                );
                do_action( 'agfo_ai_job_completed', $job['job_uuid'], $asset, $job );
                return;
            }

            if ( ! $last_error instanceof WP_Error ) {
                $last_error = new WP_Error( 'agfo_job_no_route', 'Çalıştırılabilir sağlayıcı rotası bulunamadı.' );
            }

            $attempts     = (int) $job['attempts'];
            $max_attempts = (int) $job['max_attempts'];
            $retry        = $attempts < $max_attempts && self::retry_allowed( $last_error );
            $delay        = min( 900, 30 * ( 2 ** max( 0, $attempts - 1 ) ) );
            AGFO_AIM_Job_Store::fail( $job_id, $last_error, $retry, $delay );
            if ( ! $retry ) {
                AGFO_AIM_Budget::settle( $job_id, 0.0 );
            }
            do_action( 'agfo_ai_job_failed', $job['job_uuid'], $last_error, $job, $retry );
        }

        private static function route_estimate( array $job, string $provider, string $model ): float {
            $routes = isset( $job['pricing']['routes'] ) && is_array( $job['pricing']['routes'] ) ? $job['pricing']['routes'] : [];
            foreach ( $routes as $route ) {
                if ( (string) ( $route['provider'] ?? '' ) === $provider && (string) ( $route['model'] ?? '' ) === $model ) {
                    return max( 0.0, (float) ( $route['cost'] ?? 0 ) );
                }
            }
            return max( 0.0, (float) ( $job['cost_estimate'] ?? 0 ) );
        }

        private static function failover_allowed( WP_Error $error ): bool {
            $code = strtolower( (string) $error->get_error_code() );
            return (bool) preg_match( '/_(429|500|502|503|504)$/', $code );
        }

        private static function retry_allowed( WP_Error $error ): bool {
            $code = strtolower( (string) $error->get_error_code() );
            return false !== strpos( $code, 'http' ) || (bool) preg_match( '/_(408|409|425|429|500|502|503|504)$/', $code );
        }

        public static function cleanup_assets(): void {
            if ( class_exists( 'AGFO_AIM_Asset_Store' ) ) {
                AGFO_AIM_Asset_Store::cleanup_expired();
            }
        }
    }
}
