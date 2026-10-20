<?php
/**
 * Provider-aware TTS model and voice catalog.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_TTS_Catalog' ) ) {
    final class AGFO_AIM_TTS_Catalog {
        private const CACHE_TTL       = 900;
        private const MAX_VOICE_PAGES = 25;

        public static function register_hooks(): void {
            add_action( 'wp_ajax_agfo_ai_tts_catalog', [ __CLASS__, 'ajax_catalog' ] );
        }

        public static function ajax_catalog(): void {
            if ( ! is_user_logged_in() || ! current_user_can( 'manage_options' ) ) {
                wp_send_json_error( [ 'message' => 'Yetki yok.' ], 403 );
            }
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );

            $provider = sanitize_key( (string) ( $_POST['provider'] ?? '' ) );
            $force    = ! empty( $_POST['force'] );
            $catalog  = self::get_catalog( $provider, $force );

            if ( is_wp_error( $catalog ) ) {
                wp_send_json_error(
                    [
                        'message' => $catalog->get_error_message(),
                        'code'    => $catalog->get_error_code(),
                    ],
                    400
                );
            }

            wp_send_json_success( $catalog );
        }

        /**
         * @return array<string,mixed>|WP_Error
         */
        public static function get_catalog( string $provider, bool $force = false ) {
            $provider = sanitize_key( $provider );
            if ( 'openai' === $provider ) {
                return self::openai_catalog();
            }
            if ( 'elevenlabs' === $provider ) {
                return self::elevenlabs_catalog( $force );
            }
            if ( 'minimax' === $provider ) {
                return self::minimax_catalog( $force );
            }
            if ( 'ema' === $provider && class_exists( 'AGFO_AIM_Adapter_EMA' ) ) {
                // $force (the Studio "test" button) also probes the local service.
                return AGFO_AIM_Adapter_EMA::catalog( $force );
            }
            return new WP_Error( 'agfo_tts_catalog_provider', 'Desteklenmeyen TTS katalog sağlayıcısı.' );
        }

        /**
         * Official Speech API model and built-in voice choices.
         *
         * @return array<string,mixed>
         */
        public static function openai_catalog(): array {
            $all_voices = [
                self::voice( 'alloy', 'Alloy' ),
                self::voice( 'ash', 'Ash' ),
                self::voice( 'ballad', 'Ballad' ),
                self::voice( 'coral', 'Coral' ),
                self::voice( 'echo', 'Echo' ),
                self::voice( 'fable', 'Fable' ),
                self::voice( 'nova', 'Nova' ),
                self::voice( 'onyx', 'Onyx' ),
                self::voice( 'sage', 'Sage' ),
                self::voice( 'shimmer', 'Shimmer' ),
                self::voice( 'verse', 'Verse' ),
                self::voice( 'marin', 'Marin', 'Önerilen kalite' ),
                self::voice( 'cedar', 'Cedar', 'Önerilen kalite' ),
            ];
            $legacy_voices = [ 'alloy', 'ash', 'coral', 'echo', 'fable', 'onyx', 'nova', 'sage', 'shimmer' ];

            return [
                'provider'  => 'openai',
                'source'    => 'official_static_catalog',
                'cached'    => false,
                'fetched_at'=> current_time( 'mysql' ),
                'models'    => [
                    [
                        'id'                    => 'gpt-4o-mini-tts',
                        'name'                  => 'GPT-4o mini TTS',
                        'description'           => 'Yeni nesil, talimatla ton ve okuma biçimi kontrolü.',
                        'recommended'           => true,
                        'supports_instructions' => true,
                        'max_characters'        => 4096,
                        'voice_ids'             => array_column( $all_voices, 'id' ),
                    ],
                    [
                        'id'                    => 'gpt-4o-mini-tts-2025-12-15',
                        'name'                  => 'GPT-4o mini TTS — 2025-12-15 snapshot',
                        'description'           => 'Sabitlenmiş model snapshotı; tekrarlanabilir üretim için.',
                        'recommended'           => false,
                        'supports_instructions' => true,
                        'max_characters'        => 4096,
                        'voice_ids'             => array_column( $all_voices, 'id' ),
                    ],
                    [
                        'id'                    => 'tts-1',
                        'name'                  => 'TTS-1',
                        'description'           => 'Daha düşük gecikme; daha düşük ses kalitesi.',
                        'recommended'           => false,
                        'supports_instructions' => false,
                        'max_characters'        => 4096,
                        'voice_ids'             => $legacy_voices,
                    ],
                    [
                        'id'                    => 'tts-1-hd',
                        'name'                  => 'TTS-1 HD',
                        'description'           => 'Eski nesil, kalite odaklı TTS modeli.',
                        'recommended'           => false,
                        'supports_instructions' => false,
                        'max_characters'        => 4096,
                        'voice_ids'             => $legacy_voices,
                    ],
                ],
                'voices'    => $all_voices,
                'formats'   => [ 'mp3', 'opus', 'aac', 'flac', 'wav', 'pcm' ],
                'truncated' => false,
                'notice'    => 'OpenAI Speech API yerleşik model ve ses seçenekleri.',
            ];
        }

        /**
         * @return array<string,mixed>|WP_Error
         */
        private static function elevenlabs_catalog( bool $force ) {
            $key = function_exists( 'agfo_get_api_key' ) ? agfo_get_api_key( 'elevenlabs' ) : '';
            if ( ! is_string( $key ) || '' === trim( $key ) ) {
                $fallback            = self::elevenlabs_fallback_catalog();
                $fallback['notice']  = 'ElevenLabs API anahtarı eklendikten sonra hesabınızdaki modeller ve sesler otomatik yüklenir.';
                $fallback['has_key'] = false;
                return $fallback;
            }

            $cache_key = 'agfo_ai_tts_catalog_el_' . substr( hash( 'sha256', $key ), 0, 20 );
            if ( $force ) {
                delete_transient( $cache_key );
            } else {
                $cached = get_transient( $cache_key );
                if ( is_array( $cached ) ) {
                    $cached['cached'] = true;
                    return $cached;
                }
            }

            $models_response = self::request_json(
                'https://api.elevenlabs.io/v1/models',
                $key
            );
            if ( is_wp_error( $models_response ) ) {
                return $models_response;
            }

            $models = [];
            foreach ( $models_response as $item ) {
                if ( ! is_array( $item ) || empty( $item['model_id'] ) || empty( $item['can_do_text_to_speech'] ) ) {
                    continue;
                }
                $languages = [];
                foreach ( (array) ( $item['languages'] ?? [] ) as $language ) {
                    if ( ! is_array( $language ) || empty( $language['language_id'] ) ) {
                        continue;
                    }
                    $languages[] = [
                        'id'   => sanitize_key( (string) $language['language_id'] ),
                        'name' => sanitize_text_field( (string) ( $language['name'] ?? $language['language_id'] ) ),
                    ];
                }
                $models[] = [
                    'id'                    => sanitize_text_field( (string) $item['model_id'] ),
                    'name'                  => sanitize_text_field( (string) ( $item['name'] ?? $item['model_id'] ) ),
                    'description'           => sanitize_text_field( (string) ( $item['description'] ?? '' ) ),
                    'recommended'           => 'eleven_multilingual_v2' === (string) $item['model_id'],
                    'supports_instructions' => false,
                    'can_use_style'         => ! empty( $item['can_use_style'] ),
                    'can_use_speaker_boost' => ! empty( $item['can_use_speaker_boost'] ),
                    'requires_alpha_access' => ! empty( $item['requires_alpha_access'] ),
                    'max_characters'        => absint( $item['maximum_text_length_per_request'] ?? $item['max_characters_request_subscribed_user'] ?? 40000 ),
                    'token_cost_factor'     => isset( $item['token_cost_factor'] ) ? (float) $item['token_cost_factor'] : null,
                    'languages'             => $languages,
                ];
            }

            usort(
                $models,
                static function ( array $a, array $b ): int {
                    if ( ! empty( $a['recommended'] ) !== ! empty( $b['recommended'] ) ) {
                        return ! empty( $a['recommended'] ) ? -1 : 1;
                    }
                    return strcasecmp( (string) $a['name'], (string) $b['name'] );
                }
            );

            $voices       = [];
            $seen_voices  = [];
            $next_token   = '';
            $seen_tokens  = [];
            $truncated    = false;
            $page_counter = 0;

            do {
                $query = [
                    'page_size'           => 100,
                    'sort'                => 'name',
                    'sort_direction'      => 'asc',
                    'include_total_count' => 'false',
                ];
                if ( '' !== $next_token ) {
                    $query['next_page_token'] = $next_token;
                }

                $voices_response = self::request_json(
                    add_query_arg( $query, 'https://api.elevenlabs.io/v2/voices' ),
                    $key
                );
                if ( is_wp_error( $voices_response ) ) {
                    return $voices_response;
                }

                foreach ( (array) ( $voices_response['voices'] ?? [] ) as $voice ) {
                    if ( ! is_array( $voice ) || empty( $voice['voice_id'] ) ) {
                        continue;
                    }
                    $voice_id = sanitize_text_field( (string) $voice['voice_id'] );
                    if ( isset( $seen_voices[ $voice_id ] ) ) {
                        continue;
                    }
                    $seen_voices[ $voice_id ] = true;
                    $labels = [];
                    foreach ( (array) ( $voice['labels'] ?? [] ) as $label_key => $label_value ) {
                        if ( ! is_scalar( $label_value ) ) {
                            continue;
                        }
                        $labels[ sanitize_key( (string) $label_key ) ] = sanitize_text_field( (string) $label_value );
                    }
                    $voices[] = [
                        'id'          => $voice_id,
                        'name'        => sanitize_text_field( (string) ( $voice['name'] ?? $voice_id ) ),
                        'category'    => sanitize_key( (string) ( $voice['category'] ?? 'other' ) ),
                        'description' => sanitize_text_field( (string) ( $voice['description'] ?? '' ) ),
                        'labels'      => $labels,
                        'preview_url' => esc_url_raw( (string) ( $voice['preview_url'] ?? '' ) ),
                        'model_ids'   => array_values(
                            array_filter(
                                array_map( 'sanitize_text_field', (array) ( $voice['high_quality_base_model_ids'] ?? [] ) )
                            )
                        ),
                        'is_owner'    => ! empty( $voice['is_owner'] ),
                    ];
                }

                $page_counter++;
                $has_more   = ! empty( $voices_response['has_more'] );
                $next_token = sanitize_text_field( (string) ( $voices_response['next_page_token'] ?? '' ) );
                if ( $has_more && ( '' === $next_token || isset( $seen_tokens[ $next_token ] ) ) ) {
                    $truncated = true;
                    break;
                }
                if ( '' !== $next_token ) {
                    $seen_tokens[ $next_token ] = true;
                }
                if ( $has_more && $page_counter >= self::MAX_VOICE_PAGES ) {
                    $truncated = true;
                    break;
                }
            } while ( $has_more );

            usort(
                $voices,
                static function ( array $a, array $b ): int {
                    $category_compare = strcasecmp( (string) $a['category'], (string) $b['category'] );
                    return 0 !== $category_compare ? $category_compare : strcasecmp( (string) $a['name'], (string) $b['name'] );
                }
            );

            $catalog = [
                'provider'   => 'elevenlabs',
                'source'     => 'live_provider_api',
                'cached'     => false,
                'has_key'    => true,
                'fetched_at' => current_time( 'mysql' ),
                'models'     => $models ?: self::elevenlabs_fallback_catalog()['models'],
                'voices'     => $voices,
                'formats'    => [ 'mp3', 'wav', 'pcm', 'ulaw', 'alaw', 'opus' ],
                'truncated'  => $truncated,
                'notice'     => $truncated
                    ? 'Ses listesi güvenli üst sınıra ulaştığı için kısaltıldı. Aradığınız Voice ID görünmüyorsa manuel ID seçeneğini kullanın.'
                    : 'ElevenLabs hesabınızdaki erişilebilir TTS modelleri ve sesleri yüklendi.',
            ];

            set_transient( $cache_key, $catalog, self::CACHE_TTL );
            return $catalog;
        }

        /**
         * @return array<string,mixed>
         */
        public static function elevenlabs_fallback_catalog(): array {
            return [
                'provider'   => 'elevenlabs',
                'source'     => 'built_in_fallback',
                'cached'     => false,
                'has_key'    => false,
                'fetched_at' => current_time( 'mysql' ),
                'models'     => [
                    [
                        'id'                    => 'eleven_multilingual_v2',
                        'name'                  => 'Eleven Multilingual v2',
                        'description'           => 'Uzun biçimli üretimde tutarlı, çok dilli model.',
                        'recommended'           => true,
                        'supports_instructions' => false,
                        'can_use_style'         => true,
                        'can_use_speaker_boost' => true,
                        'max_characters'        => 10000,
                        'languages'             => [],
                    ],
                    [
                        'id'                    => 'eleven_v3',
                        'name'                  => 'Eleven v3',
                        'description'           => 'Duygusal ve ifade gücü yüksek üretim.',
                        'recommended'           => false,
                        'supports_instructions' => false,
                        'can_use_style'         => true,
                        'can_use_speaker_boost' => true,
                        'max_characters'        => 5000,
                        'languages'             => [],
                    ],
                    [
                        'id'                    => 'eleven_flash_v2_5',
                        'name'                  => 'Eleven Flash v2.5',
                        'description'           => 'Düşük gecikme ve daha düşük maliyet odaklı model.',
                        'recommended'           => false,
                        'supports_instructions' => false,
                        'can_use_style'         => false,
                        'can_use_speaker_boost' => true,
                        'max_characters'        => 40000,
                        'languages'             => [],
                    ],
                ],
                'voices'     => [],
                'formats'    => [ 'mp3', 'wav', 'pcm', 'ulaw', 'alaw', 'opus' ],
                'truncated'  => false,
                'notice'     => '',
            ];
        }

        /**
         * @return array<string,mixed>|WP_Error
         */
        private static function minimax_catalog( bool $force ) {
            $key = function_exists( 'agfo_get_api_key' ) ? agfo_get_api_key( 'minimax' ) : '';
            if ( ! is_string( $key ) || '' === trim( $key ) ) {
                $fallback            = self::minimax_fallback_catalog();
                $fallback['notice']  = 'MiniMax API anahtarı eklendikten sonra sistem, klonlanmış ve tasarlanmış sesler hesabınızdan yüklenir.';
                $fallback['has_key'] = false;
                return $fallback;
            }

            $cache_key = 'agfo_ai_tts_catalog_mm_' . substr( hash( 'sha256', $key ), 0, 20 );
            if ( $force ) {
                delete_transient( $cache_key );
            } else {
                $cached = get_transient( $cache_key );
                if ( is_array( $cached ) ) {
                    $cached['cached'] = true;
                    return $cached;
                }
            }

            $response = wp_remote_post(
                'https://api.minimax.io/v1/get_voice',
                [
                    'timeout'   => 30,
                    'sslverify' => true,
                    'headers'   => [
                        'Authorization' => 'Bearer ' . trim( $key ),
                        'Content-Type'  => 'application/json',
                        'Accept'        => 'application/json',
                    ],
                    'body'      => wp_json_encode( [ 'voice_type' => 'all' ] ),
                ]
            );
            if ( is_wp_error( $response ) ) {
                return new WP_Error( 'agfo_minimax_catalog_http', agfo_redact_secrets( $response->get_error_message() ) );
            }

            $code = (int) wp_remote_retrieve_response_code( $response );
            $body = (string) wp_remote_retrieve_body( $response );
            $json = json_decode( $body, true );
            if ( $code < 200 || $code >= 300 ) {
                $message = is_array( $json ) ? (string) ( $json['base_resp']['status_msg'] ?? $json['message'] ?? '' ) : '';
                return new WP_Error( 'agfo_minimax_catalog_' . $code, 'MiniMax ses kataloğu isteği başarısız oldu (HTTP ' . $code . '). ' . sanitize_text_field( $message ) );
            }
            if ( ! is_array( $json ) ) {
                return new WP_Error( 'agfo_minimax_catalog_json', 'MiniMax ses kataloğu yanıtı geçerli JSON değil.' );
            }
            if ( 0 !== (int) ( $json['base_resp']['status_code'] ?? -1 ) ) {
                return new WP_Error( 'agfo_minimax_catalog_provider', 'MiniMax ses kataloğu hatası: ' . sanitize_text_field( (string) ( $json['base_resp']['status_msg'] ?? 'Bilinmeyen hata' ) ) );
            }

            $voices = [];
            $groups = [
                'system_voice'    => 'system',
                'voice_cloning'   => 'cloned',
                'voice_generation'=> 'generated',
                'music_generation'=> 'music',
            ];
            foreach ( $groups as $response_key => $category ) {
                foreach ( (array) ( $json[ $response_key ] ?? [] ) as $voice ) {
                    if ( ! is_array( $voice ) || empty( $voice['voice_id'] ) ) {
                        continue;
                    }
                    $description = $voice['description'] ?? '';
                    if ( is_array( $description ) ) {
                        $description = implode( ' ', array_map( 'sanitize_text_field', $description ) );
                    }
                    $voice_id = sanitize_text_field( (string) $voice['voice_id'] );
                    $voices[] = [
                        'id'          => $voice_id,
                        'name'        => sanitize_text_field( (string) ( $voice['voice_name'] ?? $voice_id ) ),
                        'category'    => $category,
                        'description' => sanitize_text_field( (string) $description ),
                        'labels'      => [
                            'created_time' => sanitize_text_field( (string) ( $voice['created_time'] ?? '' ) ),
                        ],
                        'preview_url' => '',
                        'model_ids'   => [],
                        'is_owner'    => 'system' !== $category,
                    ];
                }
            }

            usort(
                $voices,
                static function ( array $a, array $b ): int {
                    $category_compare = strcasecmp( (string) $a['category'], (string) $b['category'] );
                    return 0 !== $category_compare ? $category_compare : strcasecmp( (string) $a['name'], (string) $b['name'] );
                }
            );

            $catalog            = self::minimax_fallback_catalog();
            $catalog['source']  = 'live_provider_api';
            $catalog['cached']  = false;
            $catalog['has_key'] = true;
            $catalog['voices']  = $voices;
            $catalog['notice']  = 'MiniMax hesabınızdaki sistem ve özel sesler yüklendi.';
            set_transient( $cache_key, $catalog, self::CACHE_TTL );
            return $catalog;
        }

        /**
         * @return array<string,mixed>
         */
        public static function minimax_fallback_catalog(): array {
            $languages = [
                [ 'id' => 'auto', 'name' => 'Otomatik algıla' ],
                [ 'id' => 'Turkish', 'name' => 'Türkçe' ],
                [ 'id' => 'English', 'name' => 'İngilizce' ],
                [ 'id' => 'German', 'name' => 'Almanca' ],
                [ 'id' => 'French', 'name' => 'Fransızca' ],
                [ 'id' => 'Spanish', 'name' => 'İspanyolca' ],
                [ 'id' => 'Italian', 'name' => 'İtalyanca' ],
                [ 'id' => 'Arabic', 'name' => 'Arapça' ],
                [ 'id' => 'Russian', 'name' => 'Rusça' ],
                [ 'id' => 'Portuguese', 'name' => 'Portekizce' ],
                [ 'id' => 'Chinese', 'name' => 'Çince' ],
                [ 'id' => 'Chinese,Yue', 'name' => 'Kantonca' ],
                [ 'id' => 'Japanese', 'name' => 'Japonca' ],
                [ 'id' => 'Korean', 'name' => 'Korece' ],
            ];
            return [
                'provider'   => 'minimax',
                'source'     => 'built_in_fallback',
                'cached'     => false,
                'has_key'    => false,
                'fetched_at' => current_time( 'mysql' ),
                'models'     => [
                    [
                        'id'                    => 'speech-2.8-hd',
                        'name'                  => 'Speech 2.8 HD',
                        'description'           => 'En yeni HD model; doğal ses etiketleri ve yüksek kalite.',
                        'recommended'           => true,
                        'supports_instructions' => false,
                        'max_characters'        => 9999,
                        'languages'             => $languages,
                    ],
                    [
                        'id'                    => 'speech-2.8-turbo',
                        'name'                  => 'Speech 2.8 Turbo',
                        'description'           => 'Daha düşük gecikme ve daha düşük maliyet.',
                        'recommended'           => false,
                        'supports_instructions' => false,
                        'max_characters'        => 9999,
                        'languages'             => $languages,
                    ],
                    [
                        'id'                    => 'speech-2.6-hd',
                        'name'                  => 'Speech 2.6 HD',
                        'description'           => 'Güçlü prozodi ve klon ses benzerliği.',
                        'recommended'           => false,
                        'supports_instructions' => false,
                        'max_characters'        => 9999,
                        'languages'             => $languages,
                    ],
                    [
                        'id'                    => 'speech-2.6-turbo',
                        'name'                  => 'Speech 2.6 Turbo',
                        'description'           => '40 dil destekli hızlı model.',
                        'recommended'           => false,
                        'supports_instructions' => false,
                        'max_characters'        => 9999,
                        'languages'             => $languages,
                    ],
                    [
                        'id'                    => 'speech-02-hd',
                        'name'                  => 'Speech 02 HD',
                        'description'           => 'Ritim, kararlılık ve ses benzerliği odaklı eski nesil HD model.',
                        'recommended'           => false,
                        'supports_instructions' => false,
                        'max_characters'        => 9999,
                        'languages'             => $languages,
                    ],
                    [
                        'id'                    => 'speech-02-turbo',
                        'name'                  => 'Speech 02 Turbo',
                        'description'           => 'Çok dilli, hızlı eski nesil model.',
                        'recommended'           => false,
                        'supports_instructions' => false,
                        'max_characters'        => 9999,
                        'languages'             => $languages,
                    ],
                    [
                        'id'                    => 'speech-01-hd',
                        'name'                  => 'Speech 01 HD (Legacy)',
                        'description'           => 'MiniMax T2A tarafından hâlen kabul edilen eski nesil HD model.',
                        'recommended'           => false,
                        'supports_instructions' => false,
                        'max_characters'        => 9999,
                        'languages'             => $languages,
                    ],
                    [
                        'id'                    => 'speech-01-turbo',
                        'name'                  => 'Speech 01 Turbo (Legacy)',
                        'description'           => 'MiniMax T2A tarafından hâlen kabul edilen eski nesil hızlı model.',
                        'recommended'           => false,
                        'supports_instructions' => false,
                        'max_characters'        => 9999,
                        'languages'             => $languages,
                    ],
                ],
                'voices'     => [],
                'formats'    => [ 'mp3', 'wav', 'flac' ],
                'truncated'  => false,
                'notice'     => '',
            ];
        }

        /**
         * @return array<string,mixed>|WP_Error
         */
        private static function request_json( string $url, string $key ) {
            $response = wp_remote_get(
                $url,
                [
                    'timeout'   => 25,
                    'sslverify' => true,
                    'headers'   => [
                        'xi-api-key' => $key,
                        'Accept'     => 'application/json',
                    ],
                ]
            );
            if ( is_wp_error( $response ) ) {
                return new WP_Error( 'agfo_tts_catalog_http', agfo_redact_secrets( $response->get_error_message() ) );
            }

            $code = (int) wp_remote_retrieve_response_code( $response );
            $body = (string) wp_remote_retrieve_body( $response );
            if ( $code < 200 || $code >= 300 ) {
                $message = 'ElevenLabs katalog isteği başarısız oldu (HTTP ' . $code . ').';
                $json    = json_decode( $body, true );
                if ( is_array( $json ) ) {
                    $detail = $json['detail']['message'] ?? $json['detail'] ?? $json['message'] ?? '';
                    if ( is_scalar( $detail ) && '' !== trim( (string) $detail ) ) {
                        $message .= ' ' . sanitize_text_field( (string) $detail );
                    }
                }
                return new WP_Error( 'agfo_tts_catalog_' . $code, agfo_redact_secrets( $message ) );
            }

            $json = json_decode( $body, true );
            if ( ! is_array( $json ) ) {
                return new WP_Error( 'agfo_tts_catalog_json', 'ElevenLabs katalog yanıtı geçerli JSON değil.' );
            }
            return $json;
        }

        /**
         * @return array<string,mixed>
         */
        private static function voice( string $id, string $name, string $description = '' ): array {
            return [
                'id'          => $id,
                'name'        => $name,
                'category'    => 'built-in',
                'description' => $description,
                'labels'      => [],
                'preview_url' => '',
                'model_ids'   => [],
                'is_owner'    => false,
            ];
        }
    }
}
