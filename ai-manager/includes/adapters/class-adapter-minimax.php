<?php
/**
 * MiniMax synchronous TTS adapter.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Adapter_MiniMax' ) ) {
    final class AGFO_AIM_Adapter_MiniMax implements AGFO_AIM_Adapter_Interface {
        public function provider_code(): string {
            return 'minimax';
        }

        public function supports( string $capability ): bool {
            return in_array( $capability, [ 'speech_synthesize', 'music_generate' ], true );
        }

        public function validate_payload( string $capability, array $payload ) {
            if ( 'music_generate' === $capability ) {
                return $this->validate_music_payload( $payload );
            }
            if ( ! $this->supports( $capability ) ) {
                return new WP_Error( 'agfo_minimax_capability', 'MiniMax adaptörü bu yeteneği desteklemiyor.' );
            }

            $text = trim( (string) ( $payload['text'] ?? '' ) );
            if ( '' === $text ) {
                return new WP_Error( 'agfo_tts_text_required', 'Seslendirilecek metin gerekli.' );
            }
            $length = function_exists( 'mb_strlen' ) ? mb_strlen( $text, 'UTF-8' ) : strlen( $text );
            if ( $length >= 10000 ) {
                return new WP_Error( 'agfo_tts_text_too_long', 'MiniMax T2A HTTP tek işte 10000 karakterden kısa metin kabul eder.' );
            }
            if ( '' === trim( (string) ( $payload['voice'] ?? '' ) ) ) {
                return new WP_Error( 'agfo_tts_voice_required', 'MiniMax için voice ID gerekli.' );
            }

            $format = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            if ( ! in_array( $format, [ 'mp3', 'wav', 'flac' ], true ) ) {
                return new WP_Error( 'agfo_tts_format', 'MiniMax için desteklenmeyen ses biçimi.' );
            }

            $speed = (float) ( $payload['speed'] ?? 1.0 );
            if ( $speed < 0.5 || $speed > 2.0 ) {
                return new WP_Error( 'agfo_minimax_speed', 'MiniMax hız değeri 0.5 ile 2.0 arasında olmalıdır.' );
            }

            $volume = (float) ( $payload['volume'] ?? 1.0 );
            if ( $volume <= 0 || $volume > 10 ) {
                return new WP_Error( 'agfo_minimax_volume', 'MiniMax ses düzeyi 0 değerinden büyük ve en fazla 10 olmalıdır.' );
            }

            $pitch = (int) ( $payload['pitch'] ?? 0 );
            if ( $pitch < -12 || $pitch > 12 ) {
                return new WP_Error( 'agfo_minimax_pitch', 'MiniMax perde değeri -12 ile 12 arasında olmalıdır.' );
            }

            $sample_rate = absint( $payload['sample_rate'] ?? 32000 );
            if ( ! in_array( $sample_rate, [ 8000, 16000, 22050, 24000, 32000, 44100 ], true ) ) {
                return new WP_Error( 'agfo_minimax_sample_rate', 'MiniMax için desteklenmeyen örnekleme hızı.' );
            }

            $bitrate = absint( $payload['bitrate'] ?? 128000 );
            if ( ! in_array( $bitrate, [ 32000, 64000, 128000, 256000 ], true ) ) {
                return new WP_Error( 'agfo_minimax_bitrate', 'MiniMax için desteklenmeyen bitrate.' );
            }

            $channel = absint( $payload['channel'] ?? 1 );
            if ( ! in_array( $channel, [ 1, 2 ], true ) ) {
                return new WP_Error( 'agfo_minimax_channel', 'MiniMax kanal değeri 1 veya 2 olmalıdır.' );
            }

            $emotion = sanitize_key( (string) ( $payload['emotion'] ?? '' ) );
            if ( 'whipser' === $emotion ) {
                $emotion = 'whisper';
            }
            if ( '' !== $emotion && ! in_array( $emotion, [ 'happy', 'sad', 'angry', 'fearful', 'surprised', 'calm', 'fluent', 'whisper' ], true ) ) {
                return new WP_Error( 'agfo_minimax_emotion', 'MiniMax için desteklenmeyen duygu değeri.' );
            }

            return true;
        }

        public function estimate_cost( string $capability, array $payload, array $context = [] ): array {
            if ( 'music_generate' === $capability ) {
                $model = sanitize_text_field( (string) ( $context['model'] ?? $payload['model'] ?? 'music-2.6-free' ) );
                $rates = get_option( 'agfo_ai_pricing_rates', [] );
                $rate = isset( $rates['minimax'][ $model ]['per_song'] ) ? max( 0, (float) $rates['minimax'][ $model ]['per_song'] ) : ( false !== strpos( $model, '-free' ) ? 0.0 : 0.15 );
                return [ 'units' => 1.0, 'unit_name' => 'song', 'cost' => $rate, 'currency' => 'USD', 'snapshot' => [ 'basis' => 'per_song', 'rate' => $rate, 'model' => $model, 'source' => isset( $rates['minimax'][ $model ]['per_song'] ) ? 'admin_override' : 'official_snapshot_2026-08-01' ] ];
            }
            $chars = function_exists( 'mb_strlen' )
                ? mb_strlen( (string) ( $payload['text'] ?? '' ), 'UTF-8' )
                : strlen( (string) ( $payload['text'] ?? '' ) );
            $model = sanitize_text_field( (string) ( $context['model'] ?? $payload['model'] ?? 'speech-2.8-hd' ) );
            $rates = get_option( 'agfo_ai_pricing_rates', [] );

            if ( isset( $rates['minimax'][ $model ]['per_1000_characters'] ) ) {
                $rate   = max( 0, (float) $rates['minimax'][ $model ]['per_1000_characters'] );
                $source = 'admin_override';
            } elseif ( false !== stripos( $model, 'turbo' ) ) {
                $rate   = 0.06;
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

            $key = function_exists( 'agfo_get_api_key' ) ? agfo_get_api_key( 'minimax' ) : '';
            if ( ! is_string( $key ) || '' === trim( $key ) ) {
                return new WP_Error( 'agfo_no_api_key', 'MiniMax API anahtarı tanımlı değil.' );
            }

            $model       = sanitize_text_field( (string) ( $context['model'] ?? $payload['model'] ?? 'speech-2.8-hd' ) );
            $format      = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            $sample_rate = absint( $payload['sample_rate'] ?? 32000 );
            $bitrate     = absint( $payload['bitrate'] ?? 128000 );
            $channel     = absint( $payload['channel'] ?? 1 );
            $body        = [
                'model'          => $model,
                'text'           => (string) $payload['text'],
                'stream'         => false,
                'output_format'  => 'hex',
                'language_boost' => sanitize_text_field( (string) ( $payload['language_boost'] ?? 'auto' ) ) ?: 'auto',
                'voice_setting'  => [
                    'voice_id' => sanitize_text_field( (string) $payload['voice'] ),
                    'speed'    => (float) ( $payload['speed'] ?? 1.0 ),
                    'vol'      => (float) ( $payload['volume'] ?? 1.0 ),
                    'pitch'    => (int) ( $payload['pitch'] ?? 0 ),
                ],
                'audio_setting'  => [
                    'sample_rate' => $sample_rate,
                    'bitrate'     => $bitrate,
                    'format'      => $format,
                    'channel'     => $channel,
                ],
            ];

            $emotion = sanitize_key( (string) ( $payload['emotion'] ?? '' ) );
            if ( 'whipser' === $emotion ) {
                $emotion = 'whisper';
            }
            if ( '' !== $emotion ) {
                $body['voice_setting']['emotion'] = $emotion;
            }

            $response = wp_remote_post(
                'https://api.minimax.io/v1/t2a_v2',
                [
                    'timeout'   => 180,
                    'sslverify' => true,
                    'headers'   => [
                        'Authorization' => 'Bearer ' . trim( $key ),
                        'Content-Type'  => 'application/json',
                        'Accept'        => 'application/json',
                    ],
                    'body'      => wp_json_encode( $body ),
                ]
            );

            if ( is_wp_error( $response ) ) {
                return new WP_Error( 'agfo_minimax_tts_http', agfo_redact_secrets( $response->get_error_message() ) );
            }

            $http_code = (int) wp_remote_retrieve_response_code( $response );
            $raw       = (string) wp_remote_retrieve_body( $response );
            $json      = json_decode( $raw, true );
            if ( $http_code < 200 || $http_code >= 300 ) {
                return new WP_Error( 'agfo_minimax_tts_' . $http_code, 'MiniMax TTS hatası (HTTP ' . $http_code . '): ' . $this->response_message( $json, $raw ) );
            }
            if ( ! is_array( $json ) ) {
                return new WP_Error( 'agfo_minimax_tts_json', 'MiniMax TTS yanıtı geçerli JSON değil.' );
            }

            $status_code = (int) ( $json['base_resp']['status_code'] ?? -1 );
            if ( 0 !== $status_code ) {
                return new WP_Error( 'agfo_minimax_tts_provider', 'MiniMax TTS hatası: ' . $this->response_message( $json, $raw ) );
            }

            $hex = (string) ( $json['data']['audio'] ?? '' );
            if ( '' === $hex || 0 !== strlen( $hex ) % 2 || ! ctype_xdigit( $hex ) ) {
                return new WP_Error( 'agfo_minimax_tts_audio', 'MiniMax geçerli hex ses verisi döndürmedi.' );
            }

            $binary = hex2bin( $hex );
            if ( false === $binary || '' === $binary ) {
                return new WP_Error( 'agfo_minimax_tts_decode', 'MiniMax ses verisi çözülemedi.' );
            }

            $tmp = $this->create_temp_file( 'agfo-minimax-tts.' . $format );
            if ( ! $tmp ) {
                return new WP_Error( 'agfo_temp_file', 'Geçici ses dosyası oluşturulamadı.' );
            }
            $written = file_put_contents( $tmp, $binary, LOCK_EX );
            unset( $binary, $hex );
            if ( false === $written || $written < 1 ) {
                @unlink( $tmp );
                return new WP_Error( 'agfo_minimax_tts_write', 'MiniMax ses çıktısı geçici dosyaya yazılamadı.' );
            }

            $extra          = is_array( $json['extra_info'] ?? null ) ? $json['extra_info'] : [];
            $usage_chars    = max( 0, absint( $extra['usage_characters'] ?? 0 ) );
            $estimate       = $this->estimate_cost( $capability, $payload, [ 'model' => $model ] );
            $actual_units   = $usage_chars > 0 ? $usage_chars : (float) $estimate['units'];
            $rate_per_1000  = (float) ( $estimate['snapshot']['rate_per_1000'] ?? 0 );

            return [
                'temp_file'    => $tmp,
                'mime'         => $this->mime_for_format( $format ),
                'bytes'        => (int) $written,
                'provider_ref' => sanitize_text_field( (string) ( $json['trace_id'] ?? '' ) ),
                'usage'        => [
                    'input_units'  => $actual_units,
                    'output_units' => 1,
                    'unit_name'    => 'character',
                ],
                'cost_actual'  => $rate_per_1000 > 0 ? round( ( $actual_units / 1000 ) * $rate_per_1000, 8 ) : null,
            ];
        }

        private function validate_music_payload( array $payload ) {
            $prompt = trim( (string) ( $payload['prompt'] ?? '' ) );
            $lyrics = trim( (string) ( $payload['lyrics'] ?? '' ) );
            $instrumental = ! empty( $payload['instrumental'] );
            $optimizer = ! empty( $payload['lyrics_optimizer'] );
            if ( '' === $prompt && ( $instrumental || '' === $lyrics ) ) {
                return new WP_Error( 'agfo_music_prompt_required', 'MiniMax için müzik açıklaması gerekli.' );
            }
            $prompt_length = function_exists( 'mb_strlen' ) ? mb_strlen( $prompt, 'UTF-8' ) : strlen( $prompt );
            $lyrics_length = function_exists( 'mb_strlen' ) ? mb_strlen( $lyrics, 'UTF-8' ) : strlen( $lyrics );
            if ( $prompt_length > 2000 ) {
                return new WP_Error( 'agfo_music_prompt_too_long', 'MiniMax müzik açıklaması en fazla 2000 karakter olabilir.' );
            }
            if ( $lyrics_length > 3500 ) {
                return new WP_Error( 'agfo_music_lyrics_too_long', 'MiniMax şarkı sözü en fazla 3500 karakter olabilir.' );
            }
            if ( ! $instrumental && '' === $lyrics && ! $optimizer ) {
                return new WP_Error( 'agfo_music_lyrics_required', 'Vokalli MiniMax üretiminde söz girin veya otomatik söz üretimini açın.' );
            }
            $model = sanitize_text_field( (string) ( $payload['model'] ?? '' ) );
            if ( '' !== $model && ! in_array( $model, [ 'music-2.6', 'music-2.6-free' ], true ) ) {
                return new WP_Error( 'agfo_music_model', 'İlk sürümde MiniMax music-2.6 ve music-2.6-free desteklenir.' );
            }
            $format = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            if ( ! in_array( $format, [ 'mp3', 'wav', 'flac' ], true ) ) {
                return new WP_Error( 'agfo_music_format', 'MiniMax Music için desteklenmeyen çıktı biçimi.' );
            }
            return true;
        }

        private function dispatch_music( array $payload, array $context ) {
            $payload['model'] = sanitize_text_field( (string) ( $context['model'] ?? $payload['model'] ?? 'music-2.6-free' ) );
            $valid = $this->validate_music_payload( $payload );
            if ( is_wp_error( $valid ) ) {
                return $valid;
            }
            $key = function_exists( 'agfo_get_api_key' ) ? agfo_get_api_key( 'minimax' ) : '';
            if ( ! is_string( $key ) || '' === trim( $key ) ) {
                return new WP_Error( 'agfo_no_api_key', 'MiniMax API anahtarı tanımlı değil.' );
            }
            $format = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            $body = [
                'model' => $payload['model'],
                'prompt' => (string) ( $payload['prompt'] ?? '' ),
                'lyrics' => (string) ( $payload['lyrics'] ?? '' ),
                'stream' => false,
                'output_format' => 'url',
                'lyrics_optimizer' => ! empty( $payload['lyrics_optimizer'] ),
                'is_instrumental' => ! empty( $payload['instrumental'] ),
                'audio_setting' => [
                    'sample_rate' => 44100,
                    'bitrate' => 256000,
                    'format' => $format,
                ],
            ];
            $response = wp_remote_post( 'https://api.minimax.io/v1/music_generation', [
                'timeout' => 300,
                'sslverify' => true,
                'headers' => [ 'Authorization' => 'Bearer ' . trim( $key ), 'Content-Type' => 'application/json', 'Accept' => 'application/json' ],
                'body' => wp_json_encode( $body ),
            ] );
            if ( is_wp_error( $response ) ) {
                return new WP_Error( 'agfo_minimax_music_http', agfo_redact_secrets( $response->get_error_message() ) );
            }
            $code = (int) wp_remote_retrieve_response_code( $response );
            $raw = (string) wp_remote_retrieve_body( $response );
            $json = json_decode( $raw, true );
            if ( $code < 200 || $code >= 300 ) {
                return new WP_Error( 'agfo_minimax_music_' . $code, 'MiniMax Music hatası (HTTP ' . $code . '): ' . $this->response_message( $json, $raw ) );
            }
            if ( ! is_array( $json ) || 0 !== (int) ( $json['base_resp']['status_code'] ?? -1 ) ) {
                return new WP_Error( 'agfo_minimax_music_provider', 'MiniMax Music hatası: ' . $this->response_message( $json, $raw ) );
            }
            $audio = (string) ( $json['data']['audio'] ?? '' );
            if ( '' === $audio ) {
                return new WP_Error( 'agfo_minimax_music_audio', 'MiniMax Music yanıtında ses verisi bulunamadı.' );
            }
            $tmp = $this->create_temp_file( 'agfo-minimax-music.' . $format );
            if ( ! $tmp ) {
                return new WP_Error( 'agfo_temp_file', 'Geçici müzik dosyası oluşturulamadı.' );
            }
            $written = 0;
            if ( filter_var( $audio, FILTER_VALIDATE_URL ) ) {
                $download = wp_safe_remote_get( $audio, [ 'timeout' => 300, 'sslverify' => true, 'stream' => true, 'filename' => $tmp ] );
                if ( is_wp_error( $download ) ) {
                    @unlink( $tmp );
                    return new WP_Error( 'agfo_minimax_music_download', agfo_redact_secrets( $download->get_error_message() ) );
                }
                $download_code = (int) wp_remote_retrieve_response_code( $download );
                if ( $download_code < 200 || $download_code >= 300 ) {
                    @unlink( $tmp );
                    return new WP_Error( 'agfo_minimax_music_download_' . $download_code, 'MiniMax müzik dosyası indirilemedi.' );
                }
                $written = file_exists( $tmp ) ? (int) filesize( $tmp ) : 0;
            } elseif ( 0 === strlen( $audio ) % 2 && ctype_xdigit( $audio ) ) {
                $binary = hex2bin( $audio );
                $written = false !== $binary ? (int) file_put_contents( $tmp, $binary, LOCK_EX ) : 0;
                unset( $binary );
            }
            if ( $written < 1 ) {
                @unlink( $tmp );
                return new WP_Error( 'agfo_minimax_music_write', 'MiniMax müzik çıktısı geçici dosyaya yazılamadı.' );
            }
            $extra = is_array( $json['extra_info'] ?? null ) ? $json['extra_info'] : [];
            $estimate = $this->estimate_cost( 'music_generate', $payload, [ 'model' => $payload['model'] ] );
            return [
                'temp_file' => $tmp,
                'mime' => $this->mime_for_format( $format ),
                'bytes' => $written,
                'provider_ref' => sanitize_text_field( (string) ( $json['trace_id'] ?? '' ) ),
                'usage' => [ 'input_units' => (float) ( (int) ( $extra['music_duration'] ?? 0 ) / 1000 ), 'output_units' => 1, 'unit_name' => 'second' ],
                'cost_actual' => (float) $estimate['cost'],
                'metadata' => [ 'duration_ms' => absint( $extra['music_duration'] ?? 0 ), 'sample_rate' => absint( $extra['music_sample_rate'] ?? 0 ) ],
            ];
        }

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
            $map = [
                'mp3'  => 'audio/mpeg',
                'wav'  => 'audio/wav',
                'flac' => 'audio/flac',
            ];
            return $map[ $format ] ?? 'application/octet-stream';
        }

        private function response_message( $json, string $raw ): string {
            if ( is_array( $json ) ) {
                $message = $json['base_resp']['status_msg'] ?? $json['message'] ?? $json['error']['message'] ?? '';
                if ( is_scalar( $message ) && '' !== trim( (string) $message ) ) {
                    return sanitize_text_field( (string) $message );
                }
            }
            $fallback = wp_strip_all_tags( substr( $raw, 0, 1000 ) );
            return '' !== trim( $fallback ) ? sanitize_text_field( $fallback ) : 'Yanıt ayrıntısı yok.';
        }
    }
}
