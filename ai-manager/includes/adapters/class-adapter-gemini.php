<?php
/**
 * Gemini Lyria music generation adapter.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Adapter_Gemini' ) ) {
    final class AGFO_AIM_Adapter_Gemini implements AGFO_AIM_Adapter_Interface {
        public function provider_code(): string {
            return 'gemini';
        }

        public function supports( string $capability ): bool {
            return 'music_generate' === $capability;
        }

        public function validate_payload( string $capability, array $payload ) {
            if ( ! $this->supports( $capability ) ) {
                return new WP_Error( 'agfo_capability_unsupported', 'Gemini bu yetenek için yapılandırılmadı.' );
            }

            $prompt = trim( (string) ( $payload['prompt'] ?? '' ) );
            $lyrics = trim( (string) ( $payload['lyrics'] ?? '' ) );
            if ( '' === $prompt && '' === $lyrics ) {
                return new WP_Error( 'agfo_music_prompt_required', 'Müzik açıklaması veya şarkı sözü gerekli.' );
            }
            if ( $this->text_length( $prompt ) > 6000 || $this->text_length( $lyrics ) > 6000 ) {
                return new WP_Error( 'agfo_music_text_too_long', 'Gemini Lyria için açıklama ve söz alanlarının her biri en fazla 6000 karakter olabilir.' );
            }

            $model = sanitize_text_field( (string) ( $payload['model'] ?? '' ) );
            if ( '' !== $model && ! in_array( $model, [ 'lyria-3-clip-preview', 'lyria-3-pro-preview' ], true ) ) {
                return new WP_Error( 'agfo_music_model', 'Desteklenmeyen Gemini Lyria modeli.' );
            }

            $format = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            if ( 'mp3' !== $format ) {
                return new WP_Error( 'agfo_music_format', 'İlk Lyria entegrasyonunda güvenli ve doğrulanabilir çıktı olarak yalnız MP3 desteklenir.' );
            }
            return true;
        }

        public function estimate_cost( string $capability, array $payload, array $context = [] ): array {
            $model = sanitize_text_field( (string) ( $context['model'] ?? $payload['model'] ?? 'lyria-3-clip-preview' ) );
            $rates = get_option( 'agfo_ai_pricing_rates', [] );
            if ( isset( $rates['gemini'][ $model ]['per_request'] ) ) {
                $rate   = max( 0, (float) $rates['gemini'][ $model ]['per_request'] );
                $source = 'admin_override';
            } else {
                $rate   = 'lyria-3-pro-preview' === $model ? 0.08 : 0.04;
                $source = 'official_snapshot_2026-08-01';
            }

            return [
                'units'     => 1.0,
                'unit_name' => 'request',
                'cost'      => $rate,
                'currency'  => 'USD',
                'snapshot'  => [
                    'basis'      => 'per_request',
                    'rate'       => $rate,
                    'model'      => $model,
                    'source'     => $source,
                ],
            ];
        }

        public function dispatch( string $capability, array $payload, array $context = [] ) {
            $payload['model'] = sanitize_text_field( (string) ( $context['model'] ?? $payload['model'] ?? 'lyria-3-clip-preview' ) );
            $valid = $this->validate_payload( $capability, $payload );
            if ( is_wp_error( $valid ) ) {
                return $valid;
            }

            $key = function_exists( 'agfo_get_api_key' ) ? agfo_get_api_key( 'gemini' ) : '';
            if ( ! is_string( $key ) || '' === trim( $key ) ) {
                return new WP_Error( 'agfo_no_api_key', 'Gemini API anahtarı tanımlı değil.' );
            }

            $model  = $payload['model'];
            $format = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            $input  = $this->build_prompt( $payload, $model );
            $body   = [
                'model' => $model,
                'input' => $input,
            ];
            $response = wp_remote_post(
                'https://generativelanguage.googleapis.com/v1beta/interactions',
                [
                    'timeout'   => 300,
                    'sslverify' => true,
                    'headers'   => [
                        'x-goog-api-key' => trim( $key ),
                        'Content-Type'   => 'application/json',
                        'Accept'         => 'application/json',
                    ],
                    'body'      => wp_json_encode( $body ),
                ]
            );
            if ( is_wp_error( $response ) ) {
                return new WP_Error( 'agfo_gemini_music_http', agfo_redact_secrets( $response->get_error_message() ) );
            }

            $code = (int) wp_remote_retrieve_response_code( $response );
            $raw  = (string) wp_remote_retrieve_body( $response );
            $json = json_decode( $raw, true );
            if ( $code < 200 || $code >= 300 ) {
                return new WP_Error( 'agfo_gemini_music_' . $code, 'Gemini Lyria hatası (HTTP ' . $code . '): ' . $this->response_message( $json, $raw ) );
            }
            if ( ! is_array( $json ) ) {
                return new WP_Error( 'agfo_gemini_music_json', 'Gemini Lyria yanıtı geçerli JSON değil.' );
            }

            $audio_data = '';
            $mime       = 'audio/mpeg';
            $texts      = [];
            foreach ( (array) ( $json['steps'] ?? [] ) as $step ) {
                if ( ! is_array( $step ) || 'model_output' !== (string) ( $step['type'] ?? '' ) ) {
                    continue;
                }
                foreach ( (array) ( $step['content'] ?? [] ) as $block ) {
                    if ( ! is_array( $block ) ) {
                        continue;
                    }
                    if ( 'audio' === (string) ( $block['type'] ?? '' ) && ! empty( $block['data'] ) ) {
                        $audio_data = (string) $block['data'];
                        if ( ! empty( $block['mime_type'] ) ) {
                            $mime = sanitize_text_field( (string) $block['mime_type'] );
                        }
                    } elseif ( 'text' === (string) ( $block['type'] ?? '' ) && isset( $block['text'] ) ) {
                        $texts[] = sanitize_textarea_field( (string) $block['text'] );
                    }
                }
            }
            if ( '' === $audio_data ) {
                return new WP_Error( 'agfo_gemini_music_audio', 'Gemini Lyria yanıtında ses bloğu bulunamadı.' );
            }

            // CHANGED 17.1.2: decode through the single audited codec.
            $binary = class_exists( 'AGFO_AIM_Binary_Codec' ) ? AGFO_AIM_Binary_Codec::decode( $audio_data ) : null;
            unset( $audio_data );
            if ( null === $binary ) {
                return new WP_Error( 'agfo_gemini_music_decode', 'Gemini Lyria ses verisi çözülemedi.' );
            }

            $extension = false !== stripos( $mime, 'wav' ) ? 'wav' : 'mp3';
            $tmp       = $this->create_temp_file( 'agfo-gemini-music.' . $extension );
            if ( ! $tmp ) {
                return new WP_Error( 'agfo_temp_file', 'Geçici müzik dosyası oluşturulamadı.' );
            }
            $written = file_put_contents( $tmp, $binary, LOCK_EX );
            unset( $binary );
            if ( false === $written || $written < 1 ) {
                @unlink( $tmp );
                return new WP_Error( 'agfo_gemini_music_write', 'Gemini Lyria çıktısı geçici dosyaya yazılamadı.' );
            }

            $estimate = $this->estimate_cost( $capability, $payload, [ 'model' => $model ] );
            return [
                'temp_file'    => $tmp,
                'mime'         => $mime,
                'bytes'        => (int) $written,
                'provider_ref' => sanitize_text_field( (string) ( $json['id'] ?? $json['interaction_id'] ?? '' ) ),
                'usage'        => [ 'input_units' => 1, 'output_units' => 1, 'unit_name' => 'request' ],
                'cost_actual'  => (float) $estimate['cost'],
                'metadata'     => [
                    'generated_text' => trim( implode( "\n\n", array_filter( $texts ) ) ),
                    'duration_ms'    => 'lyria-3-clip-preview' === $model ? 30000 : null,
                ],
            ];
        }

        private function build_prompt( array $payload, string $model ): string {
            $prompt = trim( (string) ( $payload['prompt'] ?? '' ) );
            $lyrics = trim( (string) ( $payload['lyrics'] ?? '' ) );
            $duration = max( 3, min( 600, absint( $payload['duration'] ?? 30 ) ) );
            $parts = [];
            if ( '' !== $prompt ) {
                $parts[] = $prompt;
            }
            if ( ! empty( $payload['instrumental'] ) ) {
                $parts[] = 'Instrumental only, no vocals.';
            } elseif ( '' !== $lyrics ) {
                $parts[] = "Use exactly these custom lyrics and preserve their section tags:\n\n" . $lyrics;
            }
            if ( 'lyria-3-pro-preview' === $model ) {
                $parts[] = 'Target duration: approximately ' . $duration . ' seconds.';
            }
            return trim( implode( "\n\n", $parts ) );
        }

        private function create_temp_file( string $filename ) {
            if ( ! function_exists( 'wp_tempnam' ) ) {
                $file_api = ABSPATH . 'wp-admin/includes/file.php';
                if ( is_readable( $file_api ) ) {
                    require_once $file_api;
                }
            }
            return function_exists( 'wp_tempnam' ) ? wp_tempnam( $filename ) : false;
        }

        private function text_length( string $text ): int {
            return function_exists( 'mb_strlen' ) ? mb_strlen( $text, 'UTF-8' ) : strlen( $text );
        }

        private function response_message( $json, string $raw ): string {
            if ( is_array( $json ) ) {
                $message = $json['error']['message'] ?? $json['message'] ?? '';
                if ( is_scalar( $message ) && '' !== trim( (string) $message ) ) {
                    return sanitize_text_field( (string) $message );
                }
            }
            $fallback = wp_strip_all_tags( substr( $raw, 0, 1000 ) );
            return '' !== trim( $fallback ) ? sanitize_text_field( $fallback ) : 'Yanıt ayrıntısı yok.';
        }
    }
}
