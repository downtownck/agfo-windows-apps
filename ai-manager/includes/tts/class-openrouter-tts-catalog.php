<?php
/**
 * NEW 17.15.0: OpenRouter ses modelleri ve sesleri.
 *
 * Model listesi OpenRouter'dan alınır (GET /api/v1/models?output_modalities=speech); sesler modele göre değişir:
 *   - modelin supported_voices alanı doluysa o liste (ör. Microsoft MAI-Voice),
 *   - yoksa bilinen model aileleri için yerleşik sesler (Gemini, OpenAI, Grok, Kokoro).
 * Sesini bilmediğimiz modeller listelenmez (yanlış ses kimliği gönderip hata almamak için).
 * Ağ ya da anahtar yoksa aynı ailelerden yedek bir liste döner. Her modelin voice_ids alanı o modelin sesleridir.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_OpenRouter_TTS_Catalog' ) ) {
    final class AGFO_AIM_OpenRouter_TTS_Catalog {
        const CACHE_KEY = 'agfo_ai_openrouter_tts_catalog_v1';
        const CACHE_TTL = 43200;
        const MODELS_URL = 'https://openrouter.ai/api/v1/models?output_modalities=speech';

        /** Gemini TTS'in 30 yerleşik sesi ve karakteri. */
        const GEMINI_VOICES = [
            'Kore' => 'Kararlı', 'Puck' => 'Neşeli', 'Charon' => 'Bilgilendirici', 'Zephyr' => 'Parlak', 'Fenrir' => 'Heyecanlı',
            'Leda' => 'Genç', 'Orus' => 'Kararlı', 'Aoede' => 'Ferah', 'Callirrhoe' => 'Rahat', 'Autonoe' => 'Parlak',
            'Enceladus' => 'Nefesli', 'Iapetus' => 'Net', 'Umbriel' => 'Rahat', 'Algieba' => 'Yumuşak', 'Despina' => 'Yumuşak',
            'Erinome' => 'Net', 'Algenib' => 'Kısık', 'Rasalgethi' => 'Bilgilendirici', 'Laomedeia' => 'Neşeli', 'Achernar' => 'Yumuşak',
            'Alnilam' => 'Kararlı', 'Schedar' => 'Dengeli', 'Gacrux' => 'Olgun', 'Pulcherrima' => 'Atılgan', 'Achird' => 'Samimi',
            'Zubenelgenubi' => 'Gündelik', 'Vindemiatrix' => 'Nazik', 'Sadachbia' => 'Canlı', 'Sadaltager' => 'Bilgili', 'Sulafat' => 'Sıcak',
        ];
        const OPENAI_VOICES = [ 'marin' => 'Önerilen kalite', 'cedar' => 'Önerilen kalite', 'alloy' => '', 'ash' => '', 'ballad' => '',
                                'coral' => '', 'echo' => '', 'fable' => '', 'nova' => '', 'onyx' => '', 'sage' => '', 'shimmer' => '', 'verse' => '' ];
        const GROK_VOICES   = [ 'Eve' => '', 'Ara' => '', 'Rex' => '', 'Sal' => '', 'Leo' => '' ];
        const KOKORO_VOICES = [ 'af_heart' => 'İngilizce (ABD), kadın', 'af_bella' => 'İngilizce (ABD), kadın', 'am_michael' => 'İngilizce (ABD), erkek',
                                'am_fenrir' => 'İngilizce (ABD), erkek', 'bf_emma' => 'İngilizce (İngiltere), kadın', 'bm_george' => 'İngilizce (İngiltere), erkek',
                                'ef_dora' => 'İspanyolca, kadın', 'em_alex' => 'İspanyolca, erkek' ];

        /** Ağsız yedek liste: [id, ad, açıklama, önerilen]. */
        const FALLBACK_MODELS = [
            [ 'google/gemini-3.8-flash-tts', 'Gemini 3.8 Flash TTS', 'Google; 70+ dil (Türkçe, Arapça dahil), okuma talimatı alır.', true ],
            [ 'google/gemini-3.8-flash-lite-tts', 'Gemini 3.8 Flash Lite TTS', 'Daha ucuz Gemini sesi.', false ],
            [ 'google/gemini-3.1-flash-tts-preview', 'Gemini 3.1 Flash TTS (önizleme)', 'Önceki Gemini ses modeli.', false ],
            [ 'openai/gpt-4o-mini-tts-2025-12-15', 'OpenAI GPT-4o mini TTS', 'OpenAI sesleri OpenRouter üzerinden.', false ],
            [ 'x-ai/grok-voice-tts-1.0', 'Grok Voice TTS 1.0', '20+ dil, dili kendisi algılar.', false ],
            [ 'hexgrad/kokoro-82m', 'Kokoro 82M', 'Çok ucuz; İngilizce ve İspanyolca (Türkçe ve Arapça yok).', false ],
        ];

        /** Model kimliğinden bilinen ses ailesi: [ses => açıklama] ya da null. */
        public static function family_voices( string $model_id ): ?array {
            $id = strtolower( $model_id );
            if ( 0 === strpos( $id, 'google/gemini' ) && false !== strpos( $id, 'tts' ) ) {
                return self::GEMINI_VOICES;
            }
            if ( 0 === strpos( $id, 'openai/' ) && false !== strpos( $id, 'tts' ) ) {
                return self::OPENAI_VOICES;
            }
            if ( 0 === strpos( $id, 'x-ai/grok-voice' ) ) {
                return self::GROK_VOICES;
            }
            if ( 0 === strpos( $id, 'hexgrad/kokoro' ) ) {
                return self::KOKORO_VOICES;
            }
            return null;
        }

        public static function default_voice( string $model_id ): string {
            $v = self::family_voices( $model_id );
            return $v ? (string) array_key_first( $v ) : '';
        }

        /** @return array<string,mixed> */
        public static function fallback_catalog(): array {
            $models = [];
            foreach ( self::FALLBACK_MODELS as $m ) {
                $models[] = [ 'id' => $m[0], 'name' => $m[1], 'description' => $m[2], 'recommended' => $m[3], 'voices' => self::family_voices( $m[0] ) ];
            }
            return self::build( $models, 'fallback', 'OpenRouter model listesi alınamadı; bilinen ses modelleri gösteriliyor.' );
        }

        /**
         * @return array<string,mixed>
         */
        public static function catalog( bool $force = false ): array {
            if ( ! $force && function_exists( 'get_transient' ) ) {
                $cached = get_transient( self::CACHE_KEY );
                if ( is_array( $cached ) && ! empty( $cached['models'] ) ) {
                    $cached['cached'] = true;
                    return $cached;
                }
            }
            $key = function_exists( 'agfo_get_api_key' ) ? agfo_get_api_key( 'openrouter' ) : '';
            if ( ! is_string( $key ) || '' === trim( $key ) ) {
                return self::fallback_catalog();
            }
            $response = wp_remote_get( self::MODELS_URL, [
                'timeout' => 25,
                'headers' => [ 'Authorization' => 'Bearer ' . $key, 'Accept' => 'application/json' ],
            ] );
            if ( is_wp_error( $response ) || 200 !== (int) wp_remote_retrieve_response_code( $response ) ) {
                return self::fallback_catalog();
            }
            $json = json_decode( (string) wp_remote_retrieve_body( $response ), true );
            $cat  = is_array( $json ) ? self::from_models_api( $json ) : null;
            if ( ! $cat || empty( $cat['models'] ) ) {
                return self::fallback_catalog();
            }
            if ( function_exists( 'set_transient' ) ) {
                set_transient( self::CACHE_KEY, $cat, self::CACHE_TTL );
            }
            return $cat;
        }

        /** OpenRouter /models yanıtından katalog (yalnız sesini bildiğimiz konuşma modelleri). */
        public static function from_models_api( array $json ): ?array {
            $rows = isset( $json['data'] ) && is_array( $json['data'] ) ? $json['data'] : [];
            $models = [];
            foreach ( $rows as $row ) {
                if ( ! is_array( $row ) || empty( $row['id'] ) ) {
                    continue;
                }
                $id  = (string) $row['id'];
                $out = (array) ( $row['architecture']['output_modalities'] ?? [] );
                if ( $out && ! array_intersect( [ 'speech', 'audio' ], array_map( 'strtolower', array_map( 'strval', $out ) ) ) ) {
                    continue;                                   // filtre uygulanmadıysa sohbet modellerini ele
                }
                if ( ! $out && false === stripos( $id, 'tts' ) && false === stripos( $id, 'voice' ) && false === stripos( $id, 'kokoro' ) ) {
                    continue;
                }
                $voices = null;
                if ( ! empty( $row['supported_voices'] ) && is_array( $row['supported_voices'] ) ) {
                    $voices = [];
                    foreach ( $row['supported_voices'] as $v ) {
                        $vid = is_array( $v ) ? (string) ( $v['id'] ?? $v['name'] ?? '' ) : (string) $v;
                        if ( '' !== $vid ) {
                            $voices[ $vid ] = is_array( $v ) ? (string) ( $v['description'] ?? '' ) : '';
                        }
                    }
                }
                if ( ! $voices ) {
                    $voices = self::family_voices( $id );
                }
                if ( ! $voices ) {
                    continue;
                }
                $desc  = trim( (string) ( $row['description'] ?? '' ) );
                $desc  = mb_substr( preg_replace( '/\s+/u', ' ', $desc ), 0, 160, 'UTF-8' );
                $price = self::price_note( (array) ( $row['pricing'] ?? [] ) );
                $models[] = [
                    'id'          => $id,
                    'name'        => (string) ( $row['name'] ?? $id ),
                    'description' => trim( $price . ( $price && $desc ? ' · ' : '' ) . $desc ),
                    'recommended' => self::FALLBACK_MODELS[0][0] === $id,
                    'voices'      => $voices,
                ];
            }
            if ( ! $models ) {
                return null;
            }
            usort( $models, static function ( $a, $b ) {
                return [ $a['recommended'] ? 0 : 1, $a['id'] ] <=> [ $b['recommended'] ? 0 : 1, $b['id'] ];
            } );
            return self::build( $models, 'openrouter_models_api', 'OpenRouter ses modelleri (' . count( $models ) . ').' );
        }

        private static function price_note( array $p ): string {
            foreach ( [ 'prompt' => 'girdi', 'completion' => 'çıktı' ] as $k => $label ) {
                if ( isset( $p[ $k ] ) && (float) $p[ $k ] > 0 ) {
                    return '$' . rtrim( rtrim( number_format( (float) $p[ $k ] * 1000000, 2, '.', '' ), '0' ), '.' ) . '/M ' . $label;
                }
            }
            return '';
        }

        /** Modeller + tekil ses listesi; her modelin voice_ids alanı kendi sesleri. */
        private static function build( array $models, string $source, string $notice ): array {
            $voices = [];
            $out    = [];
            foreach ( $models as $m ) {
                $ids = [];
                foreach ( (array) $m['voices'] as $vid => $desc ) {
                    $vid   = (string) $vid;
                    $ids[] = $vid;
                    if ( ! isset( $voices[ $vid ] ) ) {
                        $voices[ $vid ] = [ 'id' => $vid, 'name' => ucfirst( $vid ), 'category' => 'built-in', 'description' => (string) $desc,
                                            'labels' => [], 'preview_url' => '', 'model_ids' => [], 'is_owner' => false ];
                    }
                    $voices[ $vid ]['model_ids'][] = $m['id'];
                }
                $out[] = [
                    'id'                    => $m['id'],
                    'name'                  => $m['name'],
                    'description'           => $m['description'],
                    'recommended'           => ! empty( $m['recommended'] ),
                    'supports_instructions' => (bool) preg_match( '#^(google/gemini|openai/)#', (string) $m['id'] ),
                    'max_characters'        => AGFO_AIM_Adapter_OpenRouter::MAX_CHARS,
                    'voice_ids'             => $ids,
                    'default_voice'         => $ids[0] ?? '',
                ];
            }
            return [
                'provider'   => 'openrouter',
                'source'     => $source,
                'cached'     => false,
                'fetched_at' => function_exists( 'current_time' ) ? current_time( 'mysql' ) : gmdate( 'Y-m-d H:i:s' ),
                'models'     => $out,
                'voices'     => array_values( $voices ),
                'formats'    => [ 'mp3', 'wav' ],
                'truncated'  => false,
                'notice'     => $notice,
            ];
        }
    }
}
