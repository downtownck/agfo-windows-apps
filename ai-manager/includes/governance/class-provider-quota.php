<?php
/**
 * Provider quota and subscription usage readers.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Provider_Quota' ) ) {
    final class AGFO_AIM_Provider_Quota {
        const MINIMAX_QUOTA_OPTION     = 'agfo_ai_minimax_audio_monthly_quota';
        const MINIMAX_RESET_DAY_OPTION = 'agfo_ai_minimax_audio_reset_day';
        const CACHE_TTL                = 300;

        public static function register_hooks(): void {
            add_action( 'wp_ajax_agfo_ai_provider_quota', [ __CLASS__, 'ajax_get' ] );
        }

        public static function ajax_get(): void {
            if ( ! current_user_can( 'manage_options' ) ) {
                wp_send_json_error( [ 'message' => 'Bu işlem için yetkiniz yok.' ], 403 );
            }
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );

            $provider = isset( $_POST['provider'] ) ? sanitize_key( wp_unslash( (string) $_POST['provider'] ) ) : '';
            $force    = ! empty( $_POST['force'] );
            if ( ! in_array( $provider, [ 'elevenlabs', 'minimax' ], true ) ) {
                wp_send_json_error( [ 'message' => 'Desteklenmeyen sağlayıcı.' ], 400 );
            }

            $result = self::get( $provider, $force );
            if ( is_wp_error( $result ) ) {
                wp_send_json_error( [ 'message' => $result->get_error_message() ], 400 );
            }
            wp_send_json_success( $result );
        }

        /**
         * @return array|WP_Error
         */
        public static function get( string $provider, bool $force = false ) {
            if ( 'elevenlabs' === $provider ) {
                return self::elevenlabs( $force );
            }
            if ( 'minimax' === $provider ) {
                return self::minimax_local();
            }
            return new WP_Error( 'agfo_quota_provider', 'Desteklenmeyen sağlayıcı.' );
        }

        /**
         * Read the exact ElevenLabs subscription counters from the documented API.
         *
         * @return array|WP_Error
         */
        private static function elevenlabs( bool $force = false ) {
            $key = function_exists( 'agfo_get_api_key' ) ? (string) agfo_get_api_key( 'elevenlabs' ) : '';
            if ( '' === $key ) {
                return new WP_Error( 'agfo_quota_no_key', 'ElevenLabs API anahtarı tanımlı değil.' );
            }

            $cache_key = 'agfo_ai_quota_el_' . substr( hash( 'sha256', $key ), 0, 16 );
            if ( $force ) {
                delete_transient( $cache_key );
            } else {
                $cached = get_transient( $cache_key );
                if ( is_array( $cached ) ) {
                    return $cached;
                }
            }

            $response = wp_remote_get(
                'https://api.elevenlabs.io/v1/user/subscription',
                [
                    'timeout' => 20,
                    'headers' => [
                        'Accept'     => 'application/json',
                        'xi-api-key' => $key,
                    ],
                ]
            );
            if ( is_wp_error( $response ) ) {
                return new WP_Error( 'agfo_quota_elevenlabs_http', 'ElevenLabs kota bilgisi alınamadı: ' . agfo_redact_secrets( $response->get_error_message() ) );
            }

            $code = (int) wp_remote_retrieve_response_code( $response );
            $raw  = (string) wp_remote_retrieve_body( $response );
            $json = json_decode( $raw, true );
            if ( $code < 200 || $code >= 300 ) {
                $message = 'HTTP ' . $code;
                if ( is_array( $json ) && isset( $json['detail'] ) ) {
                    if ( is_array( $json['detail'] ) && ! empty( $json['detail']['message'] ) ) {
                        $message = sanitize_text_field( (string) $json['detail']['message'] );
                    } elseif ( is_string( $json['detail'] ) && '' !== $json['detail'] ) {
                        $message = sanitize_text_field( $json['detail'] );
                    }
                }
                return new WP_Error( 'agfo_quota_elevenlabs_' . $code, 'ElevenLabs kota bilgisi alınamadı: ' . $message );
            }
            if ( ! is_array( $json ) ) {
                return new WP_Error( 'agfo_quota_elevenlabs_json', 'ElevenLabs kota yanıtı geçerli JSON değil.' );
            }

            $used      = max( 0.0, (float) ( $json['character_count'] ?? 0 ) );
            $limit     = max( 0.0, (float) ( $json['character_limit'] ?? 0 ) );
            $remaining = max( 0.0, $limit - $used );
            $percent   = $limit > 0 ? min( 100.0, ( $used / $limit ) * 100 ) : 0.0;
            $reset_unix = ! empty( $json['next_character_count_reset_unix'] ) ? absint( $json['next_character_count_reset_unix'] ) : 0;

            $data = [
                'provider'       => 'elevenlabs',
                'label'          => 'ElevenLabs',
                'source'         => 'provider_live',
                'exact'          => true,
                'unit'           => 'credit',
                'used'           => $used,
                'limit'          => $limit,
                'remaining'      => $remaining,
                'percent_used'   => $percent,
                'tier'           => sanitize_text_field( (string) ( $json['tier'] ?? '' ) ),
                'status'         => sanitize_key( (string) ( $json['status'] ?? '' ) ),
                'reset_at'       => $reset_unix > 0 ? wp_date( 'Y-m-d H:i', $reset_unix ) : '',
                'checked_at'     => current_time( 'mysql' ),
                'note'           => 'ElevenLabs abonelik API’sinden canlı olarak alındı. Bu sayaç plan kotasını gösterir; ayrı PAYG/top-up bakiyesi bu endpointte verilmez.',
            ];
            set_transient( $cache_key, $data, self::CACHE_TTL );
            return $data;
        }

        /**
         * MiniMax does not document a public Audio Subscription balance endpoint.
         * Show a clearly labelled local estimate based on successful jobs recorded by AGFO AI Manager.
         */
        private static function minimax_local(): array {
            $quota     = max( 0, (int) get_option( self::MINIMAX_QUOTA_OPTION, 100000 ) );
            $reset_day = max( 1, min( 28, (int) get_option( self::MINIMAX_RESET_DAY_OPTION, 1 ) ) );
            $cycle     = self::billing_cycle( $reset_day );
            $used      = class_exists( 'AGFO_AIM_Usage' )
                ? AGFO_AIM_Usage::sum_input_units(
                    [
                        'provider'   => 'minimax',
                        'capability' => 'speech_synthesize',
                        'unit_name'  => 'character',
                    ],
                    $cycle['start_date'],
                    $cycle['end_date']
                )
                : 0.0;
            $remaining = max( 0.0, $quota - $used );
            $percent   = $quota > 0 ? min( 100.0, ( $used / $quota ) * 100 ) : 0.0;

            return [
                'provider'       => 'minimax',
                'label'          => 'MiniMax',
                'source'         => 'local_estimate',
                'exact'          => false,
                'unit'           => 'audio_point_estimate',
                'used'           => $used,
                'limit'          => (float) $quota,
                'remaining'      => $remaining,
                'percent_used'   => $percent,
                'tier'           => 100000 === $quota ? 'Audio Starter' : 'Yapılandırılmış plan',
                'status'         => $quota > 0 ? 'configured' : 'unconfigured',
                'reset_at'       => $cycle['next_reset'],
                'checked_at'     => current_time( 'mysql' ),
                'note'           => 'Yerel tahmin: yalnız AGFO AI Manager üzerinden başarıyla tamamlanan MiniMax TTS işlerini içerir. MiniMax’ın belgelenmiş Audio Subscription bakiye endpointi bulunmadığı için portal dışı kullanım hesaba katılamaz.',
            ];
        }

        private static function billing_cycle( int $reset_day ): array {
            $timezone = wp_timezone();
            $now      = new DateTimeImmutable( 'now', $timezone );
            $year     = (int) $now->format( 'Y' );
            $month    = (int) $now->format( 'n' );
            $day      = (int) $now->format( 'j' );

            if ( $day >= $reset_day ) {
                $start = $now->setDate( $year, $month, $reset_day )->setTime( 0, 0, 0 );
            } else {
                $previous = $now->modify( 'first day of previous month' );
                $start    = $previous->setDate( (int) $previous->format( 'Y' ), (int) $previous->format( 'n' ), $reset_day )->setTime( 0, 0, 0 );
            }
            $next = $start->modify( '+1 month' );
            $end  = $next->modify( '-1 second' );

            return [
                'start_date' => $start->format( 'Y-m-d' ),
                'end_date'   => $end->format( 'Y-m-d' ),
                'next_reset' => $next->format( 'Y-m-d H:i' ),
            ];
        }
    }
}
