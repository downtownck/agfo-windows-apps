<?php
/**
 * NEW 17.15.0: OpenRouter seslendirme adaptörü (POST https://openrouter.ai/api/v1/audio/speech).
 *
 * Tek OpenRouter anahtarıyla Gemini TTS, Grok Voice, Kokoro, OpenAI gpt-4o-mini-tts ve diğer ses modelleri.
 * Yanıt ham ses baytıdır (JSON değil). Bazı modeller yalnız PCM verir (ör. Gemini TTS: 24 kHz, 16 bit, mono);
 * MP3 istenip model reddederse PCM alınır, WAV'a sarılır ve sunucuda FFmpeg varsa MP3'e çevrilir.
 * Hız (speed) her modelde yok: 1.0 dışında gönderilir, model reddederse hızsız yeniden denenir.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Adapter_OpenRouter' ) ) {
    final class AGFO_AIM_Adapter_OpenRouter implements AGFO_AIM_Adapter_Interface {
        const ENDPOINT      = 'https://openrouter.ai/api/v1/audio/speech';
        const DEFAULT_MODEL = 'google/gemini-3.8-flash-tts';
        const DEFAULT_VOICE = 'Kore';
        const MAX_CHARS     = 4000;
        const PCM_RATE      = 24000;

        public function provider_code(): string {
            return 'openrouter';
        }

        public function supports( string $capability ): bool {
            return 'speech_synthesize' === $capability;
        }

        public function validate_payload( string $capability, array $payload ) {
            if ( ! $this->supports( $capability ) ) {
                return new WP_Error( 'agfo_capability_unsupported', 'OpenRouter bu yetenek için yapılandırılmadı.' );
            }
            $text = isset( $payload['text'] ) ? trim( (string) $payload['text'] ) : '';
            if ( '' === $text ) {
                return new WP_Error( 'agfo_tts_text_required', 'Seslendirilecek metin gerekli.' );
            }
            if ( mb_strlen( $text, 'UTF-8' ) > self::MAX_CHARS ) {
                return new WP_Error( 'agfo_tts_text_too_long', 'OpenRouter seslendirmesi tek istekte en fazla ' . self::MAX_CHARS . ' karakter alır; metni bölün.' );
            }
            $format = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            if ( ! in_array( $format, [ 'mp3', 'wav', 'pcm' ], true ) ) {
                return new WP_Error( 'agfo_tts_format', 'OpenRouter yalnız MP3 ya da WAV verir.' );
            }
            $speed = (float) ( $payload['speed'] ?? 1.0 );
            if ( $speed < 0.25 || $speed > 4.0 ) {
                return new WP_Error( 'agfo_tts_speed', 'Hız 0.25 ile 4.0 arasında olmalıdır.' );
            }
            return true;
        }

        public function estimate_cost( string $capability, array $payload, array $context = [] ): array {
            $chars = mb_strlen( (string) ( $payload['text'] ?? '' ), 'UTF-8' );
            $model = (string) ( $context['model'] ?? self::DEFAULT_MODEL );
            $rates = function_exists( 'get_option' ) ? get_option( 'agfo_ai_pricing_rates', [] ) : [];
            $rate  = isset( $rates['openrouter'][ $model ]['per_1000_characters'] ) ? (float) $rates['openrouter'][ $model ]['per_1000_characters'] : 0.0;
            return [
                'units'     => (float) $chars,
                'unit_name' => 'character',
                'cost'      => round( ( $chars / 1000 ) * $rate, 8 ),
                'currency'  => 'USD',
                'snapshot'  => [ 'basis' => 'admin_configured_per_1000_characters', 'rate_per_1000' => $rate, 'model' => $model, 'pricing_configured' => $rate > 0 ],
            ];
        }

        /** OpenRouter'a gidecek gövde (testler de kullanır). */
        public static function request_body( array $payload, string $model, string $format, bool $with_speed ): array {
            $voice = sanitize_text_field( (string) ( $payload['voice'] ?? '' ) );
            $body  = [
                'model'           => $model,
                'input'           => (string) $payload['text'],
                'voice'           => '' !== $voice ? $voice : self::DEFAULT_VOICE,
                'response_format' => $format,
            ];
            $speed = round( (float) ( $payload['speed'] ?? 1.0 ), 2 );
            if ( $with_speed && $speed > 0 && abs( $speed - 1.0 ) >= 0.01 ) {
                $body['speed'] = max( 0.25, min( 4.0, $speed ) );
            }
            if ( ! empty( $payload['instructions'] ) ) {
                $body['instructions'] = mb_substr( sanitize_textarea_field( (string) $payload['instructions'] ), 0, 1000, 'UTF-8' );
            }
            return $body;
        }

        public function dispatch( string $capability, array $payload, array $context = [] ) {
            $valid = $this->validate_payload( $capability, $payload );
            if ( is_wp_error( $valid ) ) {
                return $valid;
            }
            $key = function_exists( 'agfo_get_api_key' ) ? agfo_get_api_key( 'openrouter' ) : '';
            if ( ! is_string( $key ) || '' === trim( $key ) ) {
                return new WP_Error( 'agfo_no_api_key', 'OpenRouter API anahtarı tanımlı değil.' );
            }
            $model  = sanitize_text_field( (string) ( $context['model'] ?? $payload['model'] ?? '' ) ) ?: self::DEFAULT_MODEL;
            $want   = sanitize_key( (string) ( $payload['format'] ?? 'mp3' ) );
            $format = 'pcm' === $want ? 'pcm' : 'mp3';
            $speed  = true;

            // En fazla üç deneme: (1) istenen biçim + hız, (2) model hızı reddederse hızsız, (3) MP3 reddedilirse PCM.
            $res = null;
            for ( $attempt = 0; $attempt < 3; $attempt++ ) {
                $res = $this->post( $key, self::request_body( $payload, $model, $format, $speed ) );
                if ( ! is_wp_error( $res ) ) {
                    break;
                }
                $msg = strtolower( $res->get_error_message() );
                if ( $speed && false !== strpos( $msg, 'speed' ) ) {
                    $speed = false;
                    continue;
                }
                if ( 'mp3' === $format && ( false !== strpos( $msg, 'pcm' ) || false !== strpos( $msg, 'response_format' ) || false !== strpos( $msg, 'format' ) ) ) {
                    $format = 'pcm';
                    continue;
                }
                return $res;
            }
            if ( is_wp_error( $res ) ) {
                return $res;
            }
            list( $tmp, $mime, $ref ) = $res;

            if ( 'pcm' === $format || false !== strpos( $mime, 'pcm' ) || false !== strpos( $mime, 'l16' ) ) {
                $tmp = self::pcm_to_audio( $tmp, 'pcm' === $want ? 'pcm' : ( 'wav' === $want ? 'wav' : 'mp3' ) );
                if ( is_wp_error( $tmp ) ) {
                    return $tmp;
                }
                $mime = self::mime_of( $tmp );
            }
            $bytes = file_exists( $tmp ) ? (int) filesize( $tmp ) : 0;
            if ( $bytes < 1 ) {
                @unlink( $tmp ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
                return new WP_Error( 'agfo_openrouter_tts_empty', 'OpenRouter boş ses döndürdü.' );
            }
            return [
                'temp_file'    => $tmp,
                'mime'         => $mime,
                'bytes'        => $bytes,
                'provider_ref' => $ref,
                'usage'        => [ 'input_units' => mb_strlen( (string) $payload['text'], 'UTF-8' ), 'output_units' => 1, 'unit_name' => 'character' ],
                'cost_actual'  => null,
            ];
        }

        /** @return array{0:string,1:string,2:string}|WP_Error [geçici dosya, mime, generation id] */
        private function post( string $key, array $body ) {
            $tmp = self::temp_file( 'agfo-openrouter-tts' );
            if ( ! $tmp ) {
                return new WP_Error( 'agfo_temp_file', 'Geçici ses dosyası oluşturulamadı.' );
            }
            $response = wp_remote_post(
                self::ENDPOINT,
                [
                    'timeout'   => 180,
                    'sslverify' => true,
                    'stream'    => true,
                    'filename'  => $tmp,
                    'headers'   => [
                        'Authorization' => 'Bearer ' . $key,
                        'Content-Type'  => 'application/json',
                        'HTTP-Referer'  => function_exists( 'home_url' ) ? home_url( '/' ) : '',
                        'X-Title'       => 'AGFO AI Manager',
                    ],
                    'body'      => wp_json_encode( $body ),
                ]
            );
            if ( is_wp_error( $response ) ) {
                @unlink( $tmp ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
                return new WP_Error( 'agfo_openrouter_tts_http', agfo_redact_secrets( $response->get_error_message() ) );
            }
            $code = (int) wp_remote_retrieve_response_code( $response );
            if ( $code < 200 || $code >= 300 ) {
                $message = self::read_error_file( $tmp );
                @unlink( $tmp ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
                return new WP_Error( 'agfo_openrouter_tts_' . $code, 'OpenRouter ses hatası (HTTP ' . $code . '): ' . $message );
            }
            $mime = strtolower( (string) wp_remote_retrieve_header( $response, 'content-type' ) );
            return [ $tmp, '' !== $mime ? $mime : 'audio/mpeg', (string) wp_remote_retrieve_header( $response, 'x-generation-id' ) ];
        }

        /**
         * Ham PCM'i (24 kHz, 16 bit, mono) WAV'a sarar; MP3 istendiyse ve FFmpeg varsa MP3'e çevirir.
         *
         * @return string|WP_Error yeni geçici dosya
         */
        public static function pcm_to_audio( string $pcm_file, string $want ) {
            $pcm = (string) file_get_contents( $pcm_file );
            @unlink( $pcm_file ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
            if ( '' === $pcm ) {
                return new WP_Error( 'agfo_openrouter_tts_empty', 'OpenRouter boş ses döndürdü.' );
            }
            if ( 'pcm' === $want ) {
                $out = self::temp_file( 'agfo-openrouter-tts' );
                file_put_contents( $out, $pcm );
                return $out;
            }
            $wav = self::temp_file( 'agfo-openrouter-tts' ) . '.wav';
            file_put_contents( $wav, self::wav_header( strlen( $pcm ), self::PCM_RATE ) . $pcm );
            if ( 'wav' === $want || ! class_exists( 'AGFO_AIM_Audio_Effects' ) || ! method_exists( 'AGFO_AIM_Audio_Effects', 'run_ffmpeg' ) ) {
                return $wav;
            }
            $mp3 = substr( $wav, 0, -4 ) . '.mp3';
            $run = AGFO_AIM_Audio_Effects::run_ffmpeg( [ '-y', '-loglevel', 'error', '-i', $wav, '-codec:a', 'libmp3lame', '-b:a', '128k', $mp3 ], 120 );
            if ( is_wp_error( $run ) || ! is_file( $mp3 ) || filesize( $mp3 ) < 1 ) {
                @unlink( $mp3 ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
                return $wav;                                    // FFmpeg yoksa WAV olarak teslim
            }
            @unlink( $wav ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
            return $mp3;
        }

        public static function wav_header( int $data_len, int $rate, int $channels = 1, int $bits = 16 ): string {
            $block = $channels * $bits / 8;
            return 'RIFF' . pack( 'V', 36 + $data_len ) . 'WAVE' . 'fmt ' . pack( 'VvvVVvv', 16, 1, $channels, $rate, $rate * $block, $block, $bits )
                . 'data' . pack( 'V', $data_len );
        }

        private static function mime_of( string $file ): string {
            $head = (string) file_get_contents( $file, false, null, 0, 4 );
            if ( 'RIFF' === $head ) {
                return 'audio/wav';
            }
            if ( 'ID3' === substr( $head, 0, 3 ) || ( strlen( $head ) > 1 && 0xFF === ord( $head[0] ) ) ) {
                return 'audio/mpeg';
            }
            return 'audio/L16';
        }

        /** @return string|false */
        private static function temp_file( string $name ) {
            if ( ! function_exists( 'wp_tempnam' ) && defined( 'ABSPATH' ) && is_readable( ABSPATH . 'wp-admin/includes/file.php' ) ) {
                require_once ABSPATH . 'wp-admin/includes/file.php';
            }
            return function_exists( 'wp_tempnam' ) ? wp_tempnam( $name ) : false;
        }

        private static function read_error_file( string $path ): string {
            $raw = is_file( $path ) ? (string) file_get_contents( $path, false, null, 0, 8192 ) : '';
            if ( '' === $raw ) {
                return 'Yanıt gövdesi boş.';
            }
            $json = json_decode( $raw, true );
            if ( is_array( $json ) && isset( $json['error']['message'] ) ) {
                $msg = (string) $json['error']['message'];
                $raw_meta = $json['error']['metadata']['raw'] ?? '';
                if ( is_string( $raw_meta ) && '' !== $raw_meta ) {
                    $msg .= ' — ' . mb_substr( $raw_meta, 0, 300, 'UTF-8' );
                }
                return sanitize_text_field( $msg );
            }
            return sanitize_text_field( wp_strip_all_tags( $raw ) );
        }
    }
}
