<?php
/**
 * ElevenLabs speech synthesis adapter.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Adapter_ElevenLabs' ) ) {
    final class AGFO_AIM_Adapter_ElevenLabs implements AGFO_AIM_Adapter_Interface {
        public function provider_code(): string {
            return 'elevenlabs';
        }

        public function supports( string $capability ): bool {
            return in_array( $capability, [ 'speech_synthesize', 'music_generate' ], true );
        }

        public function validate_payload( string $capability, array $payload ) {
            if ( 'music_generate' === $capability ) {
                return $this->validate_music_payload( $payload );
            }
            if ( ! $this->supports( $capability ) ) {
                return new WP_Error( 'agfo_capability_unsupported', 'ElevenLabs bu yetenek için yapılandırılmadı.' );
            }
            if ( '' === trim( (string) ( $payload['text'] ?? '' ) ) ) {
                return new WP_Error( 'agfo_tts_text_required', 'Seslendirilecek metin gerekli.' );
            }
            $text = (string) ( $payload['text'] ?? '' );
            if ( ( function_exists( 'mb_strlen' ) ? mb_strlen( $text, 'UTF-8' ) : strlen( $text ) ) > 40000 ) {
                return new WP_Error( 'agfo_tts_text_too_long', 'ElevenLabs TTS tek işte en fazla 40000 karakter kabul edecek şekilde sınırlandırılmıştır.' );
            }
            if ( '' === trim( (string) ( $payload['voice'] ?? '' ) ) ) {
                return new WP_Error( 'agfo_tts_voice_required', 'ElevenLabs için voice ID gerekli.' );
            }
            $format = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            if ( ! in_array( $format, [ 'mp3', 'wav', 'pcm', 'ulaw', 'alaw', 'opus' ], true ) ) {
                return new WP_Error( 'agfo_tts_format', 'Desteklenmeyen ElevenLabs ses biçimi.' );
            }
            foreach ( [ 'stability', 'similarity_boost', 'style' ] as $field ) {
                if ( isset( $payload[ $field ] ) && '' !== (string) $payload[ $field ] ) {
                    $value = (float) $payload[ $field ];
                    if ( $value < 0 || $value > 1 ) {
                        return new WP_Error( 'agfo_tts_voice_setting', $field . ' değeri 0 ile 1 arasında olmalıdır.' );
                    }
                }
            }
            return true;
        }

        public function estimate_cost( string $capability, array $payload, array $context = [] ): array {
            if ( 'music_generate' === $capability ) {
                $model    = sanitize_text_field( (string) ( $context['model'] ?? $payload['model'] ?? 'music_v1' ) );
                $duration = max( 3, min( 600, absint( $payload['duration'] ?? 30 ) ) );
                $rates    = get_option( 'agfo_ai_pricing_rates', [] );
                $rate     = isset( $rates['elevenlabs'][ $model ]['per_minute'] ) ? max( 0, (float) $rates['elevenlabs'][ $model ]['per_minute'] ) : 0.0;
                return [
                    'units' => (float) $duration,
                    'unit_name' => 'second',
                    'cost' => round( ( $duration / 60 ) * $rate, 8 ),
                    'currency' => 'USD',
                    'snapshot' => [ 'basis' => 'per_minute', 'rate_per_minute' => $rate, 'model' => $model, 'source' => $rate > 0 ? 'admin_override' : 'unpriced_provider_credits' ],
                ];
            }
            $chars = function_exists( 'mb_strlen' ) ? mb_strlen( (string) ( $payload['text'] ?? '' ), 'UTF-8' ) : strlen( (string) ( $payload['text'] ?? '' ) );
            $model = (string) ( $context['model'] ?? $payload['model'] ?? 'eleven_multilingual_v2' );
            $rates = get_option( 'agfo_ai_pricing_rates', [] );

            if ( isset( $rates['elevenlabs'][ $model ]['per_1000_characters'] ) ) {
                $rate   = (float) $rates['elevenlabs'][ $model ]['per_1000_characters'];
                $source = 'admin_override';
            } elseif ( false !== stripos( $model, 'flash' ) || false !== stripos( $model, 'turbo' ) ) {
                $rate   = 0.05;
                $source = 'official_snapshot_2026-07-31';
            } else {
                $rate   = 0.10;
                $source = 'official_snapshot_2026-07-31';
            }

            return [
                'units'     => (float) $chars,
                'unit_name' => 'character',
                'cost'      => round( ( $chars / 1000 ) * $rate, 8 ),
                'currency'  => 'USD',
                'snapshot'  => [
                    'basis'         => 'per_1000_characters',
                    'rate_per_1000' => $rate,
                    'model'         => $model,
                    'source'        => $source,
                ],
            ];
        }

        public function dispatch( string $capability, array $payload, array $context = [] ) {
            if ( 'music_generate' === $capability ) {
                return $this->dispatch_music( $payload, $context );
            }
            $valid = $this->validate_payload( $capability, $payload );
            if ( is_wp_error( $valid ) ) {
                return $valid;
            }

            $key = function_exists( 'agfo_get_api_key' ) ? agfo_get_api_key( 'elevenlabs' ) : '';
            if ( ! is_string( $key ) || '' === $key ) {
                return new WP_Error( 'agfo_no_api_key', 'ElevenLabs API anahtarı tanımlı değil.' );
            }

            $voice        = rawurlencode( sanitize_text_field( (string) $payload['voice'] ) );
            $model        = sanitize_text_field( (string) ( $context['model'] ?? $payload['model'] ?? 'eleven_multilingual_v2' ) );
            $format       = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            $output_format = $this->output_format( $format, (string) ( $payload['quality'] ?? '' ) );
            $url          = 'https://api.elevenlabs.io/v1/text-to-speech/' . $voice . '?output_format=' . rawurlencode( $output_format );
            $body         = [
                'text'     => (string) $payload['text'],
                'model_id' => $model,
            ];

            if ( ! empty( $payload['language'] ) ) {
                $body['language_code'] = sanitize_key( (string) $payload['language'] );
            }
            $voice_settings = [];
            foreach ( [ 'stability', 'similarity_boost', 'style', 'speed' ] as $field ) {
                if ( isset( $payload[ $field ] ) && '' !== (string) $payload[ $field ] ) {
                    $voice_settings[ $field ] = (float) $payload[ $field ];
                }
            }
            if ( isset( $payload['use_speaker_boost'] ) ) {
                $voice_settings['use_speaker_boost'] = (bool) $payload['use_speaker_boost'];
            }
            if ( $voice_settings ) {
                $body['voice_settings'] = $voice_settings;
            }

            $tmp = $this->create_temp_file( 'agfo-elevenlabs-tts.' . $format );
            if ( ! $tmp ) {
                return new WP_Error( 'agfo_temp_file', 'Geçici ses dosyası oluşturulamadı.' );
            }

            $response = wp_remote_post(
                $url,
                [
                    'timeout'   => 120,
                    'sslverify' => true,
                    'stream'    => true,
                    'filename'  => $tmp,
                    'headers'   => [
                        'xi-api-key'   => $key,
                        'Content-Type' => 'application/json',
                        'Accept'       => $this->mime_for_format( $format ),
                    ],
                    'body'      => wp_json_encode( $body ),
                ]
            );

            if ( is_wp_error( $response ) ) {
                @unlink( $tmp );
                return new WP_Error( 'agfo_elevenlabs_tts_http', agfo_redact_secrets( $response->get_error_message() ) );
            }

            $code = (int) wp_remote_retrieve_response_code( $response );
            if ( $code < 200 || $code >= 300 ) {
                $message = $this->read_error_file( $tmp );
                @unlink( $tmp );
                return new WP_Error( 'agfo_elevenlabs_tts_' . $code, 'ElevenLabs TTS hatası (HTTP ' . $code . '): ' . $message );
            }

            $bytes = file_exists( $tmp ) ? (int) filesize( $tmp ) : 0;
            if ( $bytes < 1 ) {
                @unlink( $tmp );
                return new WP_Error( 'agfo_elevenlabs_tts_empty', 'ElevenLabs boş ses çıktısı döndürdü.' );
            }

            $character_cost = (float) wp_remote_retrieve_header( $response, 'character-cost' );
            $request_id     = (string) wp_remote_retrieve_header( $response, 'request-id' );
            $estimate       = $this->estimate_cost( $capability, $payload, [ 'model' => $model ] );

            return [
                'temp_file'    => $tmp,
                'mime'         => $this->mime_for_format( $format ),
                'bytes'        => $bytes,
                'provider_ref' => $request_id,
                'usage'        => [
                    'input_units'  => $character_cost > 0 ? $character_cost : $estimate['units'],
                    'output_units' => 1,
                    'unit_name'    => 'character',
                ],
                'cost_actual'  => $character_cost > 0 ? round( ( $character_cost / 1000 ) * (float) $estimate['snapshot']['rate_per_1000'], 8 ) : null,
            ];
        }

        private function validate_music_payload( array $payload ) {
            $prompt = $this->music_prompt( $payload );
            if ( '' === trim( $prompt ) ) {
                return new WP_Error( 'agfo_music_prompt_required', 'ElevenLabs için müzik açıklaması veya şarkı sözü gerekli.' );
            }
            $length = function_exists( 'mb_strlen' ) ? mb_strlen( $prompt, 'UTF-8' ) : strlen( $prompt );
            if ( $length > 4100 ) {
                return new WP_Error( 'agfo_music_prompt_too_long', 'ElevenLabs Music istemi en fazla 4100 karakter olabilir.' );
            }
            $duration = absint( $payload['duration'] ?? 30 );
            if ( $duration < 3 || $duration > 600 ) {
                return new WP_Error( 'agfo_music_duration', 'ElevenLabs Music süresi 3 ile 600 saniye arasında olmalıdır.' );
            }
            $model = sanitize_text_field( (string) ( $payload['model'] ?? '' ) );
            if ( '' !== $model && ! in_array( $model, [ 'music_v1', 'music_v2' ], true ) ) {
                return new WP_Error( 'agfo_music_model', 'Desteklenmeyen ElevenLabs Music modeli.' );
            }
            $format = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            if ( ! in_array( $format, [ 'mp3', 'wav', 'pcm', 'opus' ], true ) ) {
                return new WP_Error( 'agfo_music_format', 'Desteklenmeyen ElevenLabs Music çıktı biçimi.' );
            }
            return true;
        }

        private function dispatch_music( array $payload, array $context ) {
            $payload['model'] = sanitize_text_field( (string) ( $context['model'] ?? $payload['model'] ?? 'music_v1' ) );
            $valid = $this->validate_music_payload( $payload );
            if ( is_wp_error( $valid ) ) {
                return $valid;
            }
            $key = function_exists( 'agfo_get_api_key' ) ? agfo_get_api_key( 'elevenlabs' ) : '';
            if ( ! is_string( $key ) || '' === trim( $key ) ) {
                return new WP_Error( 'agfo_no_api_key', 'ElevenLabs API anahtarı tanımlı değil.' );
            }

            $model     = $payload['model'];
            $format    = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            $quality   = sanitize_key( (string) ( $payload['quality'] ?? '' ) );
            $output    = $this->music_output_format( $format, $quality, $model );
            $tmp       = $this->create_temp_file( 'agfo-elevenlabs-music.' . ( 'wav' === $format ? 'wav' : ( 'opus' === $format ? 'opus' : 'mp3' ) ) );
            if ( ! $tmp ) {
                return new WP_Error( 'agfo_temp_file', 'Geçici müzik dosyası oluşturulamadı.' );
            }
            $body = [
                'prompt'            => $this->music_prompt( $payload ),
                'music_length_ms'   => max( 3000, min( 600000, absint( $payload['duration'] ?? 30 ) * 1000 ) ),
                'model_id'          => $model,
                'force_instrumental'=> ! empty( $payload['instrumental'] ),
            ];
            $response = wp_remote_post(
                'https://api.elevenlabs.io/v1/music?output_format=' . rawurlencode( $output ),
                [
                    'timeout' => 300,
                    'sslverify' => true,
                    'stream' => true,
                    'filename' => $tmp,
                    'headers' => [ 'xi-api-key' => trim( $key ), 'Content-Type' => 'application/json', 'Accept' => $this->mime_for_format( $format ) ],
                    'body' => wp_json_encode( $body ),
                ]
            );
            if ( is_wp_error( $response ) ) {
                @unlink( $tmp );
                return new WP_Error( 'agfo_elevenlabs_music_http', agfo_redact_secrets( $response->get_error_message() ) );
            }
            $code = (int) wp_remote_retrieve_response_code( $response );
            if ( $code < 200 || $code >= 300 ) {
                $message = $this->read_error_file( $tmp );
                @unlink( $tmp );
                return new WP_Error( 'agfo_elevenlabs_music_' . $code, 'ElevenLabs Music hatası (HTTP ' . $code . '): ' . $message );
            }
            $bytes = file_exists( $tmp ) ? (int) filesize( $tmp ) : 0;
            if ( $bytes < 1 ) {
                @unlink( $tmp );
                return new WP_Error( 'agfo_elevenlabs_music_empty', 'ElevenLabs boş müzik çıktısı döndürdü.' );
            }
            $estimate = $this->estimate_cost( 'music_generate', $payload, [ 'model' => $model ] );
            return [
                'temp_file' => $tmp,
                'mime' => $this->mime_for_format( $format ),
                'bytes' => $bytes,
                'provider_ref' => sanitize_text_field( (string) wp_remote_retrieve_header( $response, 'song-id' ) ),
                'usage' => [ 'input_units' => (float) absint( $payload['duration'] ?? 30 ), 'output_units' => 1, 'unit_name' => 'second' ],
                'cost_actual' => (float) $estimate['cost'],
                'metadata' => [ 'duration_ms' => absint( $payload['duration'] ?? 30 ) * 1000 ],
            ];
        }

        private function music_prompt( array $payload ): string {
            $prompt = trim( (string) ( $payload['prompt'] ?? '' ) );
            $lyrics = trim( (string) ( $payload['lyrics'] ?? '' ) );
            if ( '' !== $lyrics && empty( $payload['instrumental'] ) ) {
                $prompt .= ( '' !== $prompt ? "\n\n" : '' ) . "Use these exact lyrics and preserve the section tags:\n" . $lyrics;
            }
            return trim( $prompt );
        }

        private function music_output_format( string $format, string $quality, string $model ): string {
            if ( '' !== $quality ) {
                return $quality;
            }
            if ( 'music_v2' === $model && 'mp3' === $format ) {
                return 'mp3_48000_192';
            }
            $map = [ 'mp3' => 'mp3_44100_128', 'wav' => 'wav_44100', 'pcm' => 'pcm_44100', 'opus' => 'opus_48000_128' ];
            return $map[ $format ] ?? 'mp3_44100_128';
        }

        private function output_format( string $format, string $quality ): string {
            $quality = sanitize_key( $quality );
            $map     = [
                'mp3'  => $quality ?: 'mp3_44100_128',
                'wav'  => $quality ?: 'wav_44100',
                'pcm'  => $quality ?: 'pcm_24000',
                'ulaw' => $quality ?: 'ulaw_8000',
                'alaw' => $quality ?: 'alaw_8000',
                'opus' => $quality ?: 'opus_48000_64',
            ];
            return $map[ $format ] ?? 'mp3_44100_128';
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
                'wav'  => 'audio/wav',
                'pcm'  => 'audio/L16',
                'ulaw' => 'audio/basic',
                'alaw' => 'audio/basic',
                'opus' => 'audio/ogg',
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
            if ( is_array( $json ) ) {
                if ( isset( $json['detail']['message'] ) ) {
                    return sanitize_text_field( (string) $json['detail']['message'] );
                }
                if ( isset( $json['message'] ) ) {
                    return sanitize_text_field( (string) $json['message'] );
                }
            }
            return sanitize_text_field( wp_strip_all_tags( $raw ) );
        }
    }
}
