<?php
/**
 * NEW 17.14.0: AI Editor seslendirmesinde EMA dışındaki sağlayıcılar (OpenAI, ElevenLabs, MiniMax).
 *
 * Sağlayıcı adaptörleri (includes/adapters) ve ses kataloğu (includes/tts) zaten AI Manager'da var;
 * bu sınıf editörün kısa seslendirme (/editor/speech-quick) ve iş (/editor/speech) uçlarına bunları açar:
 *   - providers(): hangi sağlayıcılar hazır (anahtarı girilmiş), tek seferde kaç karakter alıyor
 *   - payload(): editörün isteğini sağlayıcının yük biçimine çevirir (ses, model, hız sınırları)
 *   - synthesize(): adaptörle anında ses üretir, kullanımı Kullanım tablosuna yazar
 *   - mp3_seconds(): üretilen MP3'ün süresi (editör altyazı / zamanlama için)
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Editor_Voice' ) ) {
    final class AGFO_AIM_Editor_Voice {
        /** Sağlayıcı => [etiket, tek istekte en fazla karakter, hız aralığı, varsayılan model, varsayılan ses]. */
        const PROVIDERS = [
            'ema'        => [ 'label' => 'EMA Lightning (Türkçe, AGFO sunucusu)', 'max' => 4000, 'speed' => [ 0.7, 1.4 ], 'model' => 'ema-lightning', 'voice' => 'ema' ],
            'openai'     => [ 'label' => 'OpenAI', 'max' => 4000, 'speed' => [ 0.25, 4.0 ], 'model' => 'gpt-4o-mini-tts', 'voice' => 'marin' ],
            'elevenlabs' => [ 'label' => 'ElevenLabs', 'max' => 4000, 'speed' => [ 0.7, 1.2 ], 'model' => 'eleven_multilingual_v2', 'voice' => '' ],
            'minimax'    => [ 'label' => 'MiniMax', 'max' => 4000, 'speed' => [ 0.5, 2.0 ], 'model' => 'speech-2.8-hd', 'voice' => '' ],
            // NEW 17.15.0: tek anahtarla Gemini TTS, Grok, Kokoro, OpenAI... (ses modele göre değişir)
            'openrouter' => [ 'label' => 'OpenRouter (Gemini, Grok, Kokoro…)', 'max' => 4000, 'speed' => [ 0.5, 2.0 ], 'model' => 'google/gemini-3.8-flash-tts', 'voice' => 'Kore' ],
        ];
        /** İş kuyruğunda (uzun ses dosyası) parça başına üst sınır; sağlayıcının kendi sınırının altında. */
        const JOB_MAX = [ 'ema' => 60000, 'openai' => 4000, 'elevenlabs' => 9000, 'minimax' => 9000, 'openrouter' => 4000 ];

        public static function known( string $provider ): bool {
            return isset( self::PROVIDERS[ sanitize_key( $provider ) ] );
        }

        public static function key_ready( string $provider ): bool {
            $provider = sanitize_key( $provider );
            if ( 'ema' === $provider ) {
                return class_exists( 'AGFO_AIM_Adapter_EMA' ) && '' !== AGFO_AIM_Adapter_EMA::token();
            }
            if ( ! function_exists( 'agfo_get_api_key' ) ) {
                return false;
            }
            $key = agfo_get_api_key( $provider );
            return is_string( $key ) && '' !== trim( $key )
                && ( ! class_exists( 'AGFO_AIM_Adapter_Registry' ) || AGFO_AIM_Adapter_Registry::supports( $provider, 'speech_synthesize' ) );
        }

        /** /editor/info için: [{id, label, ready, max_chars, job_max_chars, speed_min, speed_max, default_model, default_voice, pauses, lexicon}]. */
        public static function providers(): array {
            $out = [];
            foreach ( self::PROVIDERS as $id => $p ) {
                $out[] = [
                    'id'            => $id,
                    'label'         => $p['label'],
                    'ready'         => self::key_ready( $id ),
                    'max_chars'     => $p['max'],
                    'job_max_chars' => self::JOB_MAX[ $id ],
                    'speed_min'     => $p['speed'][0],
                    'speed_max'     => $p['speed'][1],
                    'default_model' => $p['model'],
                    'default_voice' => $p['voice'],
                    'pauses'        => 'ema' === $id,       // cümle / paragraf arası duraklama yalnız EMA'da
                    'lexicon'       => 'ema' === $id,       // ortak telaffuz sözlüğü EMA sunucusunda
                    'instructions'  => in_array( $id, [ 'openai', 'openrouter' ], true ), // okuma talimatı: OpenAI, Gemini (OpenRouter)
                    'voices_by_model' => 'openrouter' === $id, // NEW 17.15.0: ses listesi seçili modele göre
                ];
            }
            return $out;
        }

        public static function clamp_speed( string $provider, float $speed ): float {
            $p = self::PROVIDERS[ sanitize_key( $provider ) ] ?? self::PROVIDERS['ema'];
            if ( $speed <= 0 ) {
                $speed = 1.0;
            }
            return round( max( $p['speed'][0], min( $p['speed'][1], $speed ) ), 2 );
        }

        /**
         * Editör isteği -> adaptör yükü ve bağlamı.
         *
         * @return array{0:array,1:array}|WP_Error [payload, context]
         */
        public static function payload( string $provider, string $text, array $opts ) {
            $provider = sanitize_key( $provider );
            if ( ! self::known( $provider ) || 'ema' === $provider ) {
                return new WP_Error( 'agfo_editor_voice_provider', 'Desteklenmeyen ses sağlayıcısı: ' . $provider );
            }
            $p     = self::PROVIDERS[ $provider ];
            $voice = sanitize_text_field( (string) ( $opts['voice'] ?? '' ) );
            if ( '' === $voice ) {
                $voice = $p['voice'];
            }
            if ( '' === $voice ) {
                return new WP_Error( 'agfo_editor_voice_required', $p['label'] . ' için bir ses seçin (AI Editor › Ses › Ses).' );
            }
            $model   = sanitize_text_field( (string) ( $opts['model'] ?? '' ) ) ?: $p['model'];
            if ( 'openrouter' === $provider && class_exists( 'AGFO_AIM_OpenRouter_TTS_Catalog' ) ) {
                // Seçili ses bu modelin ailesinde yoksa (ör. Gemini sesi Grok modeliyle) modelin ilk sesi kullanılır.
                $fam = AGFO_AIM_OpenRouter_TTS_Catalog::family_voices( $model );
                if ( $fam && ! isset( $fam[ $voice ] ) ) {
                    $voice = (string) array_key_first( $fam );
                }
            }
            $payload = [
                'text'   => $text,
                'voice'  => $voice,
                'format' => 'mp3',
                'speed'  => self::clamp_speed( $provider, (float) ( $opts['speed'] ?? 1.0 ) ),
            ];
            if ( in_array( $provider, [ 'openai', 'openrouter' ], true ) && ! empty( $opts['instructions'] ) ) {
                $payload['instructions'] = mb_substr( sanitize_textarea_field( (string) $opts['instructions'] ), 0, 1000, 'UTF-8' );
            }
            if ( 'elevenlabs' === $provider ) {
                $payload['language'] = sanitize_key( (string) ( $opts['language'] ?? 'tr' ) ) ?: 'tr';
            }
            if ( 'minimax' === $provider ) {
                $payload['language_boost'] = 'Turkish';
            }
            return [ $payload, [ 'model' => $model, 'source_plugin' => 'agfo-ai-editor' ] ];
        }

        /**
         * Anında seslendirme (kuyruksuz). Dönüş: ['audio' => bayt, 'seconds' => float, 'provider', 'model'] | WP_Error.
         */
        public static function synthesize( string $provider, string $text, array $opts ) {
            $provider = sanitize_key( $provider );
            if ( class_exists( 'AGFO_AIM_Kill_Switch' ) && ! AGFO_AIM_Kill_Switch::is_enabled( 'speech_synthesize' ) ) {
                return new WP_Error( 'agfo_kill_switch', 'Seslendirme yönetici tarafından durduruldu.' );
            }
            if ( ! self::key_ready( $provider ) ) {
                return new WP_Error( 'agfo_no_api_key', self::PROVIDERS[ $provider ]['label'] . ' API anahtarı sitede tanımlı değil (AI Manager › Sağlayıcılar).' );
            }
            $built = self::payload( $provider, $text, $opts );
            if ( is_wp_error( $built ) ) {
                return $built;
            }
            list( $payload, $context ) = $built;
            $adapter = AGFO_AIM_Adapter_Registry::get( $provider );
            if ( is_wp_error( $adapter ) ) {
                return $adapter;
            }
            $valid = $adapter->validate_payload( 'speech_synthesize', $payload );
            if ( is_wp_error( $valid ) ) {
                return $valid;
            }
            $res = $adapter->dispatch( 'speech_synthesize', $payload, $context );
            if ( is_wp_error( $res ) ) {
                return $res;
            }
            $file  = (string) ( $res['temp_file'] ?? '' );
            $audio = '' !== $file && is_file( $file ) ? (string) file_get_contents( $file ) : '';
            if ( '' !== $file && is_file( $file ) ) {
                @unlink( $file ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
            }
            if ( '' === $audio ) {
                return new WP_Error( 'agfo_editor_voice_empty', 'Sağlayıcı boş ses döndürdü.' );
            }
            if ( class_exists( 'AGFO_AIM_Usage' ) ) {
                $usage    = is_array( $res['usage'] ?? null ) ? $res['usage'] : [];
                $estimate = method_exists( $adapter, 'estimate_cost' ) ? $adapter->estimate_cost( 'speech_synthesize', $payload, $context ) : [];
                AGFO_AIM_Usage::record(
                    [
                        'provider'      => $provider,
                        'model'         => $context['model'],
                        'capability'    => 'speech_synthesize',
                        'source_plugin' => 'agfo-ai-editor',
                        'input_units'   => (float) ( $usage['input_units'] ?? mb_strlen( $text, 'UTF-8' ) ),
                        'output_units'  => (float) ( $usage['output_units'] ?? 1 ),
                        'unit_name'     => (string) ( $usage['unit_name'] ?? 'character' ),
                        'cost_estimate' => (float) ( $estimate['cost'] ?? 0 ),
                        'cost_actual'   => isset( $res['cost_actual'] ) && null !== $res['cost_actual'] ? (float) $res['cost_actual'] : (float) ( $estimate['cost'] ?? 0 ),
                    ]
                );
            }
            return [ 'audio' => $audio, 'seconds' => self::mp3_seconds( $audio ), 'provider' => $provider, 'model' => $context['model'] ];
        }

        /**
         * MP3 süresi (saniye): Xing/Info başlığındaki kare sayısı, yoksa ilk karenin bit hızıyla bayttan tahmin.
         */
        public static function mp3_seconds( string $data ): float {
            $len = strlen( $data );
            if ( $len > 44 && 'RIFF' === substr( $data, 0, 4 ) && 'WAVE' === substr( $data, 8, 4 ) ) {
                // NEW 17.15.0: FFmpeg'siz sunucuda OpenRouter PCM'i WAV olarak döner
                $rate = unpack( 'V', substr( $data, 28, 4 ) )[1];        // bayt/saniye
                return $rate > 0 ? round( ( $len - 44 ) / $rate, 3 ) : 0.0;
            }
            $pos = 0;
            if ( $len > 10 && 'ID3' === substr( $data, 0, 3 ) ) {
                $size = ( ( ord( $data[6] ) & 0x7f ) << 21 ) | ( ( ord( $data[7] ) & 0x7f ) << 14 ) | ( ( ord( $data[8] ) & 0x7f ) << 7 ) | ( ord( $data[9] ) & 0x7f );
                $pos  = 10 + $size;
            }
            $rates = [
                1 => [ 0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320 ],   // MPEG-1 Layer III
                2 => [ 0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160 ],       // MPEG-2/2.5 Layer III
            ];
            $srs   = [ 3 => [ 44100, 48000, 32000 ], 2 => [ 22050, 24000, 16000 ], 0 => [ 11025, 12000, 8000 ] ];
            for ( $i = $pos; $i < min( $len - 4, $pos + 65536 ); $i++ ) {
                if ( 0xFF !== ord( $data[ $i ] ) || ( ord( $data[ $i + 1 ] ) & 0xE0 ) !== 0xE0 ) {
                    continue;
                }
                $b1  = ord( $data[ $i + 1 ] );
                $b2  = ord( $data[ $i + 2 ] );
                $ver = ( $b1 >> 3 ) & 3;              // 3 = MPEG1, 2 = MPEG2, 0 = MPEG2.5
                $lay = ( $b1 >> 1 ) & 3;              // 1 = Layer III
                $bri = ( $b2 >> 4 ) & 15;
                $sri = ( $b2 >> 2 ) & 3;
                if ( 1 === $ver || 1 !== $lay || 0 === $bri || 15 === $bri || 3 === $sri ) {
                    continue;
                }
                $kbps  = $rates[ 3 === $ver ? 1 : 2 ][ $bri ];
                $sr    = $srs[ $ver ][ $sri ];
                $spf   = 3 === $ver ? 1152 : 576;
                $mono  = ( ( ord( $data[ $i + 3 ] ) >> 6 ) & 3 ) === 3;
                $side  = 3 === $ver ? ( $mono ? 17 : 32 ) : ( $mono ? 9 : 17 );
                $xing  = $i + 4 + $side;
                $tag   = substr( $data, $xing, 4 );
                if ( ( 'Xing' === $tag || 'Info' === $tag ) && $xing + 12 <= $len ) {
                    $flags = unpack( 'N', substr( $data, $xing + 4, 4 ) )[1];
                    if ( $flags & 1 ) {
                        $frames = unpack( 'N', substr( $data, $xing + 8, 4 ) )[1];
                        return round( $frames * $spf / $sr, 3 );
                    }
                }
                return round( ( $len - $i ) * 8 / ( $kbps * 1000 ), 3 );
            }
            return 0.0;
        }

        /** /editor/voices için katalog: sadeleştirilmiş sesler ve modeller. */
        public static function catalog( string $provider, bool $force = false ) {
            $provider = sanitize_key( $provider );
            if ( ! self::known( $provider ) ) {
                return new WP_Error( 'agfo_editor_voice_provider', 'Desteklenmeyen ses sağlayıcısı.' );
            }
            if ( 'ema' === $provider ) {
                return [ 'provider' => 'ema', 'voices' => [ [ 'id' => 'ema', 'name' => 'EMA (Türkçe)', 'description' => '' ] ],
                         'models' => [ [ 'id' => 'ema-lightning', 'name' => 'EMA Lightning', 'recommended' => true, 'voice_ids' => [ 'ema' ] ] ] ];
            }
            if ( ! class_exists( 'AGFO_AIM_TTS_Catalog' ) ) {
                return new WP_Error( 'agfo_editor_voice_catalog', 'Ses kataloğu bileşeni yüklü değil.' );
            }
            $cat = AGFO_AIM_TTS_Catalog::get_catalog( $provider, $force );
            if ( is_wp_error( $cat ) ) {
                return $cat;
            }
            $voices = [];
            foreach ( (array) ( $cat['voices'] ?? [] ) as $v ) {
                if ( is_array( $v ) && ! empty( $v['id'] ) ) {
                    $voices[] = [
                        'id'          => (string) $v['id'],
                        'name'        => (string) ( $v['name'] ?? $v['id'] ),
                        'description' => (string) ( $v['description'] ?? '' ),
                    ];
                }
            }
            $models = [];
            foreach ( (array) ( $cat['models'] ?? [] ) as $m ) {
                if ( is_array( $m ) && ! empty( $m['id'] ) ) {
                    $models[] = [
                        'id'          => (string) $m['id'],
                        'name'        => (string) ( $m['name'] ?? $m['id'] ),
                        'recommended' => ! empty( $m['recommended'] ),
                        'voice_ids'   => array_values( array_map( 'strval', (array) ( $m['voice_ids'] ?? [] ) ) ),
                    ];
                }
            }
            return [ 'provider' => $provider, 'voices' => $voices, 'models' => $models, 'notice' => (string) ( $cat['notice'] ?? '' ) ];
        }
    }
}
