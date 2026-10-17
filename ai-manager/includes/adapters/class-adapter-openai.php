<?php
/**
 * OpenAI speech synthesis adapter.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Adapter_OpenAI' ) ) {
    final class AGFO_AIM_Adapter_OpenAI implements AGFO_AIM_Adapter_Interface {
        public function provider_code(): string {
            return 'openai';
        }

        public function supports( string $capability ): bool {
            return 'speech_synthesize' === $capability;
        }

        public function validate_payload( string $capability, array $payload ) {
            if ( ! $this->supports( $capability ) ) {
                return new WP_Error( 'agfo_capability_unsupported', 'OpenAI bu yetenek için yapılandırılmadı.' );
            }

            $text = isset( $payload['text'] ) ? trim( (string) $payload['text'] ) : '';
            if ( '' === $text ) {
                return new WP_Error( 'agfo_tts_text_required', 'Seslendirilecek metin gerekli.' );
            }
            if ( function_exists( 'mb_strlen' ) ? mb_strlen( $text, 'UTF-8' ) > 4096 : strlen( $text ) > 4096 ) {
                return new WP_Error( 'agfo_tts_text_too_long', 'OpenAI TTS tek istekte en fazla 4096 karakter kabul eder.' );
            }

            $format = isset( $payload['format'] ) ? sanitize_key( (string) $payload['format'] ) : 'mp3';
            if ( ! in_array( $format, [ 'mp3', 'opus', 'aac', 'flac', 'wav', 'pcm' ], true ) ) {
                return new WP_Error( 'agfo_tts_format', 'Desteklenmeyen ses biçimi.' );
            }

            $speed = isset( $payload['speed'] ) ? (float) $payload['speed'] : 1.0;
            if ( $speed < 0.25 || $speed > 4.0 ) {
                return new WP_Error( 'agfo_tts_speed', 'Hız 0.25 ile 4.0 arasında olmalıdır.' );
            }

            return true;
        }

        public function estimate_cost( string $capability, array $payload, array $context = [] ): array {
            $chars = function_exists( 'mb_strlen' ) ? mb_strlen( (string) ( $payload['text'] ?? '' ), 'UTF-8' ) : strlen( (string) ( $payload['text'] ?? '' ) );
            $model = (string) ( $context['model'] ?? 'gpt-4o-mini-tts' );
            $rates = get_option( 'agfo_ai_pricing_rates', [] );
            $rate  = isset( $rates['openai'][ $model ]['per_1000_characters'] ) ? (float) $rates['openai'][ $model ]['per_1000_characters'] : 0.0;

            return [
                'units'     => (float) $chars,
                'unit_name' => 'character',
                'cost'      => round( ( $chars / 1000 ) * $rate, 8 ),
                'currency'  => 'USD',
                'snapshot'  => [
                    'basis'              => 'admin_configured_per_1000_characters',
                    'rate_per_1000'      => $rate,
                    'model'              => $model,
                    'pricing_configured' => $rate > 0,
                ],
            ];
        }

        public function dispatch( string $capability, array $payload, array $context = [] ) {
            $valid = $this->validate_payload( $capability, $payload );
            if ( is_wp_error( $valid ) ) {
                return $valid;
            }

            $key = function_exists( 'agfo_get_api_key' ) ? agfo_get_api_key( 'openai' ) : '';
            if ( ! is_string( $key ) || '' === $key ) {
                return new WP_Error( 'agfo_no_api_key', 'OpenAI API anahtarı tanımlı değil.' );
            }

            $format = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            $model  = sanitize_text_field( (string) ( $context['model'] ?? $payload['model'] ?? 'gpt-4o-mini-tts' ) );
            $voice  = sanitize_text_field( (string) ( $payload['voice'] ?? 'coral' ) );
            $legacy_models = [ 'tts-1', 'tts-1-hd' ];
            $legacy_voices = [ 'alloy', 'ash', 'coral', 'echo', 'fable', 'onyx', 'nova', 'sage', 'shimmer' ];
            if ( in_array( $model, $legacy_models, true ) && ! in_array( $voice, $legacy_voices, true ) ) {
                return new WP_Error( 'agfo_openai_voice_model', 'Seçilen OpenAI sesi TTS-1 model ailesiyle uyumlu değil.' );
            }

            $body   = [
                'model'           => $model,
                'input'           => (string) $payload['text'],
                'voice'           => $voice,
                'response_format' => $format,
                'speed'           => max( 0.25, min( 4.0, (float) ( $payload['speed'] ?? 1.0 ) ) ),
            ];
            if ( ! empty( $payload['instructions'] ) && ! in_array( $model, $legacy_models, true ) ) {
                $body['instructions'] = sanitize_textarea_field( (string) $payload['instructions'] );
            }

            $tmp = $this->create_temp_file( 'agfo-openai-tts.' . $format );
            if ( ! $tmp ) {
                return new WP_Error( 'agfo_temp_file', 'Geçici ses dosyası oluşturulamadı.' );
            }

            $response = wp_remote_post(
                'https://api.openai.com/v1/audio/speech',
                [
                    'timeout'   => 120,
                    'sslverify' => true,
                    'stream'    => true,
                    'filename'  => $tmp,
                    'headers'   => [
                        'Authorization' => 'Bearer ' . $key,
                        'Content-Type'  => 'application/json',
                    ],
                    'body'      => wp_json_encode( $body ),
                ]
            );

            if ( is_wp_error( $response ) ) {
                @unlink( $tmp );
                return new WP_Error( 'agfo_openai_tts_http', agfo_redact_secrets( $response->get_error_message() ) );
            }

            $code = (int) wp_remote_retrieve_response_code( $response );
            if ( $code < 200 || $code >= 300 ) {
                $message = $this->read_error_file( $tmp );
                @unlink( $tmp );
                return new WP_Error( 'agfo_openai_tts_' . $code, 'OpenAI TTS hatası (HTTP ' . $code . '): ' . $message );
            }

            $bytes = file_exists( $tmp ) ? (int) filesize( $tmp ) : 0;
            if ( $bytes < 1 ) {
                @unlink( $tmp );
                return new WP_Error( 'agfo_openai_tts_empty', 'OpenAI boş ses çıktısı döndürdü.' );
            }

            return [
                'temp_file'    => $tmp,
                'mime'         => $this->mime_for_format( $format ),
                'bytes'        => $bytes,
                'provider_ref' => (string) wp_remote_retrieve_header( $response, 'x-request-id' ),
                'usage'        => [
                    'input_units'  => function_exists( 'mb_strlen' ) ? mb_strlen( (string) $payload['text'], 'UTF-8' ) : strlen( (string) $payload['text'] ),
                    'output_units' => 1,
                    'unit_name'    => 'character',
                ],
                'cost_actual'  => null,
            ];
        }

        /**
         * WordPress admin file helpers are not loaded automatically during WP-Cron.
         * Load wp_tempnam() lazily so background TTS jobs cannot fatal.
         *
         * @return string|false
         */
        private function create_temp_file( string $filename ) {
            if ( ! function_exists( 'wp_tempnam' ) ) {
                $file_api = ABSPATH . 'wp-admin/includes/file.php';
                if ( is_readable( $file_api ) ) {
                    require_once $file_api;
                }
            }

            if ( ! function_exists( 'wp_tempnam' ) ) {
                return false;
            }

            return wp_tempnam( $filename );
        }

        private function mime_for_format( string $format ): string {
            $map = [
                'mp3'  => 'audio/mpeg',
                'opus' => 'audio/ogg',
                'aac'  => 'audio/aac',
                'flac' => 'audio/flac',
                'wav'  => 'audio/wav',
                'pcm'  => 'audio/L16',
            ];
            return $map[ $format ] ?? 'application/octet-stream';
        }

        private function read_error_file( string $path ): string {
            if ( ! file_exists( $path ) ) {
                return 'Yanıt gövdesi yok.';
            }
            $raw = file_get_contents( $path, false, null, 0, 8192 );
            if ( ! is_string( $raw ) || '' === $raw ) {
                return 'Yanıt gövdesi boş.';
            }
            $json = json_decode( $raw, true );
            if ( is_array( $json ) && isset( $json['error']['message'] ) ) {
                return sanitize_text_field( (string) $json['error']['message'] );
            }
            return sanitize_text_field( wp_strip_all_tags( $raw ) );
        }
    }
}
