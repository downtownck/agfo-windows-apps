<?php
/**
 * AGFO AI Manager — Yetenek (Capability) Yönlendirme Katmani.
 *
 * 16.6.0 ile eklendi. Amac: agfo_get_priority_api_key() tek bir "chat" saglayicisi
 * dondurdugu icin, chat disi modaliteler (muzik uretimi, ses duzenleme) icin ayri
 * bir cozumleyici gerekiyordu. Bu dosyadaki hicbir fonksiyon mevcut imzalari
 * degistirmez; tamamen ek katmandir. Hicbir bagimli plugin bu dosyadan etkilenmez.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) exit;

/* ── YETENEK TANIMLARI ──────────────────────────────────── */

if ( ! function_exists( 'agfo_ai_capabilities' ) ) {
    /**
     * Sistemde tanimli yetenekler. 'chat' her zaman ilk siradadir ve
     * mevcut davranisla birebir aynidir.
     *
     * @return array<string,array>
     */
    function agfo_ai_capabilities(): array {
        $caps = [
            'chat' => [
                'label'             => 'Metin / Chat',
                'description'       => 'Varsayilan metin uretimi. Mevcut tum AGFO eklentileri bunu kullanir.',
                'input_modality'    => 'text',
                'output_modality'   => 'text',
                'transport'         => 'sync',
                'cost_unit'         => 'token',
                'parameter_schema'  => [ 'messages', 'temperature', 'max_tokens' ],
            ],
            // NEW 17.1.0: translation is a chat-shaped capability with its own model route.
            'text_translate' => [
                'label'             => 'Çeviri',
                'description'       => 'Metin çevirisi. Ayrı bir model seçilmezse varsayılan chat modeli kullanılır.',
                'input_modality'    => 'text',
                'output_modality'   => 'text',
                'transport'         => 'sync',
                'cost_unit'         => 'token',
                'parameter_schema'  => [ 'messages', 'temperature', 'max_tokens' ],
            ],
            // NEW 17.2.0: AI code review (Plugin Installer). Chat-shaped, own model routes.
            'code_review' => [
                'label'             => 'Kod inceleme (hızlı)',
                'description'       => 'Plugin Installer her yüklemeden sonra bulguları ucuz bir modelle sınıflandırır. Boş bırakılırsa gpt-4.1-mini, yoksa varsayılan chat modeli.',
                'input_modality'    => 'text',
                'output_modality'   => 'text',
                'transport'         => 'sync',
                'cost_unit'         => 'token',
                'parameter_schema'  => [ 'messages', 'temperature', 'max_tokens' ],
            ],
            'code_review_deep' => [
                'label'             => 'Kod inceleme (derin)',
                'description'       => 'İstek üzerine yapılan derin analiz. Boş bırakılırsa varsayılan chat modeli.',
                'input_modality'    => 'text',
                'output_modality'   => 'text',
                'transport'         => 'sync',
                'cost_unit'         => 'token',
                'parameter_schema'  => [ 'messages', 'temperature', 'max_tokens' ],
            ],
            'speech_synthesize' => [
                'label'             => 'Metinden Sese (TTS)',
                'description'       => 'Metni secilen saglayici, model ve ses ile ses dosyasina donusturur.',
                'input_modality'    => 'text',
                'output_modality'   => 'audio',
                'transport'         => 'queued',
                'cost_unit'         => 'character',
                'parameter_schema'  => [ 'text', 'voice', 'model', 'format', 'speed', 'instructions', 'language', 'language_boost', 'volume', 'pitch', 'emotion', 'sample_rate', 'bitrate', 'channel', 'retention_days' ],
            ],
            'music_generate' => [
                'label'             => 'Muzik uretimi (metinden)',
                'description'       => 'Metin promptundan sarki veya enstrumantal ses uretir.',
                'input_modality'    => 'text',
                'output_modality'   => 'audio',
                'transport'         => 'queued',
                'cost_unit'         => 'song_or_second',
                'parameter_schema'  => [ 'prompt', 'lyrics', 'duration', 'instrumental', 'lyrics_optimizer', 'model', 'format', 'retention_days' ],
            ],
            'image_generate' => [
                'label'             => 'Gorsel uretimi (metinden)',
                'description'       => 'Metin promptundan one cikan gorsel veya kapak gorseli uretir.',
                'input_modality'    => 'text',
                'output_modality'   => 'image',
                'transport'         => 'sync',
                'cost_unit'         => 'image',
                'parameter_schema'  => [ 'prompt', 'model', 'size', 'aspect', 'quality', 'format' ],
            ],
            'audio_transform' => [
                'label'             => 'Ses donusumu (sesten sese)',
                'description'       => 'Yuklenen bir kaydi referans alarak yeni duzenleme uretir.',
                'input_modality'    => 'audio',
                'output_modality'   => 'audio',
                'transport'         => 'async',
                'cost_unit'         => 'second',
                'parameter_schema'  => [ 'source_asset', 'prompt' ],
            ],
        ];

        return apply_filters( 'agfo_ai_capabilities', $caps );
    }
}

if ( ! function_exists( 'agfo_ai_capability_exists' ) ) {
    function agfo_ai_capability_exists( string $capability ): bool {
        return isset( agfo_ai_capabilities()[ $capability ] );
    }
}

if ( ! function_exists( 'agfo_ai_capability_is_chat' ) ) {
    /**
     * Bos veya tanimsiz deger her zaman 'chat' sayilir. Geriye uyumlulugun
     * bel kemigi budur: capability gecirmeyen eski cagirici = chat.
     */
    function agfo_ai_capability_is_chat( $capability ): bool {
        $capability = is_string( $capability ) ? sanitize_key( $capability ) : '';
        return ( $capability === '' || $capability === 'chat' );
    }
}

/* ── SAGLAYICI YETENEKLERI ──────────────────────────────── */

if ( ! function_exists( 'agfo_provider_capabilities' ) ) {
    /**
     * Bir saglayicinin destekledigi yetenekler. Registry'deki 'capabilities'
     * alanindan okunur; tanimli degilse tip'e gore varsayilan uretilir
     * (llm => chat). Boylece eski registry girdileri de calisir.
     *
     * @return string[]
     */
    function agfo_provider_capabilities( string $provider_code ): array {
        $provider_code = sanitize_key( $provider_code );
        $registry      = agfo_api_registry();
        if ( ! isset( $registry[ $provider_code ] ) ) return [];

        $info = $registry[ $provider_code ];
        if ( ! empty( $info['capabilities'] ) && is_array( $info['capabilities'] ) ) {
            $caps = array_values( array_unique( array_map( 'sanitize_key', $info['capabilities'] ) ) );
        } else {
            $caps = ( ( $info['type'] ?? '' ) === 'llm' ) ? [ 'chat' ] : [];
        }
        // NEW 17.1.0: every chat provider can translate.
        if ( in_array( 'chat', $caps, true ) ) {
            // CHANGED 17.2.0: chat-shaped capabilities follow chat support.
            foreach ( [ 'text_translate', 'code_review', 'code_review_deep' ] as $chat_like ) {
                if ( ! in_array( $chat_like, $caps, true ) ) {
                    $caps[] = $chat_like;
                }
            }
        }

        return apply_filters( 'agfo_provider_capabilities', $caps, $provider_code, $info );
    }
}

if ( ! function_exists( 'agfo_provider_supports_capability' ) ) {
    function agfo_provider_supports_capability( string $provider_code, string $capability ): bool {
        return in_array( sanitize_key( $capability ), agfo_provider_capabilities( $provider_code ), true );
    }
}

if ( ! function_exists( 'agfo_providers_for_capability' ) ) {
    /**
     * Belirtilen yetenegi destekleyen ve anahtari tanimli saglayicilar.
     *
     * @return array<string,string> code => label
     */
    function agfo_providers_for_capability( string $capability, bool $require_key = true ): array {
        $capability = sanitize_key( $capability );
        $out        = [];

        foreach ( agfo_api_registry() as $code => $info ) {
            if ( ! agfo_provider_supports_capability( $code, $capability ) ) continue;
            if ( $require_key && empty( agfo_get_api_key( $code ) ) ) continue;
            $out[ $code ] = isset( $info['label'] ) ? (string) $info['label'] : $code;
        }

        return $out;
    }
}

/* ── YONLENDIRME AYARLARI ───────────────────────────────── */

if ( ! function_exists( 'agfo_get_capability_routing' ) ) {
    /**
     * Kayitli yonlendirme tercihleri.
     * Yapisi: [ capability => [ 'provider' => code|'', 'model' => string ] ]
     * Bos provider = otomatik (ilk uygun saglayici).
     */
    function agfo_get_capability_routing(): array {
        $saved = get_option( 'agfo_ai_capability_routing', [] );
        if ( ! is_array( $saved ) ) $saved = [];

        $out = [];
        foreach ( array_keys( agfo_ai_capabilities() ) as $cap ) {
            $row               = isset( $saved[ $cap ] ) && is_array( $saved[ $cap ] ) ? $saved[ $cap ] : [];
            $out[ $cap ] = [
                'provider' => isset( $row['provider'] ) ? sanitize_key( (string) $row['provider'] ) : '',
                'model'    => isset( $row['model'] ) ? sanitize_text_field( (string) $row['model'] ) : '',
            ];
        }

        return $out;
    }
}

if ( ! function_exists( 'agfo_save_capability_routing' ) ) {
    function agfo_save_capability_routing( array $routing ): bool {
        $clean = [];
        foreach ( agfo_ai_capabilities() as $cap => $_meta ) {
            if ( ! isset( $routing[ $cap ] ) || ! is_array( $routing[ $cap ] ) ) continue;
            $provider = isset( $routing[ $cap ]['provider'] ) ? sanitize_key( (string) $routing[ $cap ]['provider'] ) : '';
            $model    = isset( $routing[ $cap ]['model'] ) ? sanitize_text_field( (string) $routing[ $cap ]['model'] ) : '';

            // Saglayici gercekten bu yetenegi desteklemiyorsa otomatige dus.
            if ( $provider !== '' && ! agfo_provider_supports_capability( $provider, $cap ) ) {
                $provider = '';
            }

            $clean[ $cap ] = [ 'provider' => $provider, 'model' => $model ];
        }

        return update_option( 'agfo_ai_capability_routing', $clean, false );
    }
}

/* ── COZUMLEYICI ────────────────────────────────────────── */

if ( ! function_exists( 'agfo_get_provider_for_capability' ) ) {
    /**
     * Bir yetenek icin calisir yapilandirma dondurur.
     *
     * 'chat' istendiginde davranis kasitli olarak agfo_get_priority_api_key()
     * ile ayni tutulur; boylece bu fonksiyon her yerde guvenle kullanilabilir.
     *
     * @param string $capability Yetenek anahtari.
     * @param array  $args       'model' => tercih edilen model.
     * @return array|WP_Error
     */
    function agfo_get_provider_for_capability( string $capability, array $args = [] ) {
        $capability = sanitize_key( $capability );
        if ( $capability === '' ) $capability = 'chat';

        if ( ! agfo_ai_capability_exists( $capability ) ) {
            return new WP_Error( 'agfo_capability_unknown', sprintf( 'Bilinmeyen yetenek: %s', $capability ) );
        }

        // Chat icin mevcut merkezi cozumleyiciyi aynen kullan.
        if ( $capability === 'chat' ) {
            $config = agfo_get_priority_api_key( false, isset( $args['model'] ) ? (string) $args['model'] : '' );
            if ( ! is_array( $config ) || empty( $config['key'] ) ) {
                return new WP_Error( 'agfo_config', 'AI yapilandirmasi eksik.' );
            }
            $config['capability'] = 'chat';
            $config['transport']  = 'sync';
            return $config;
        }

        $routing  = agfo_get_capability_routing();
        $pref     = isset( $routing[ $capability ] ) ? $routing[ $capability ] : [ 'provider' => '', 'model' => '' ];
        $provider = (string) $pref['provider'];

        // NEW 17.1.0: translation returns the same chat config shape as agfo_get_priority_api_key(),
        // for the routed provider/model, or the default chat model when no route is set.
        // CHANGED 17.2.0: same chat config path for every chat-shaped capability.
        if ( in_array( $capability, [ 'text_translate', 'code_review', 'code_review_deep' ], true ) ) {
            $t_provider = ! empty( $args['provider'] ) ? sanitize_key( (string) $args['provider'] ) : $provider;
            $t_model    = isset( $args['model'] ) && $args['model'] !== '' ? (string) $args['model'] : (string) $pref['model'];
            $config     = agfo_get_priority_api_key( false, $t_model, $t_provider );
            if ( ! is_array( $config ) || empty( $config['key'] ) ) {
                $config = agfo_get_priority_api_key( false );
            }
            if ( ! is_array( $config ) || empty( $config['key'] ) ) {
                return new WP_Error( 'agfo_config', 'AI yapilandirmasi eksik.' );
            }
            $config['capability'] = $capability;
            $config['transport']  = 'sync';
            return apply_filters( 'agfo_capability_config', $config, $capability, $args );
        }

        // CHANGED 16.16.0: Cagirici acikca bir saglayici belirtebilir. Yalnizca
        // istenen yetenegi gercekten destekleyen bir kod kabul edilir; belirtilmezse
        // davranis birebir eskisi gibi kalir (yonlendirme ayari, sonra otomatik).
        if ( ! empty( $args['provider'] ) ) {
            $requested = sanitize_key( (string) $args['provider'] );
            if ( agfo_provider_supports_capability( $requested, $capability ) ) {
                $provider = $requested;
            }
        }

        if ( $provider === '' ) {
            $candidates = agfo_providers_for_capability( $capability, true );
            $provider   = (string) ( array_key_first( $candidates ) ?? '' );
        }

        if ( $provider === '' ) {
            return new WP_Error(
                'agfo_capability_no_provider',
                sprintf( '"%s" yetenegi icin anahtari tanimli saglayici bulunamadi.', $capability )
            );
        }

        $registry = agfo_api_registry();
        if ( ! isset( $registry[ $provider ] ) ) {
            return new WP_Error( 'agfo_capability_provider_missing', 'Saglayici kayitli degil: ' . $provider );
        }

        $api_key = agfo_get_api_key( $provider );
        if ( empty( $api_key ) ) {
            return new WP_Error( 'agfo_capability_no_key', 'API anahtari tanimlanmamis: ' . $provider );
        }

        $info  = $registry[ $provider ];
        $model = isset( $args['model'] ) && $args['model'] !== '' ? (string) $args['model'] : (string) $pref['model'];
        // CHANGED 16.16.0: Yetenege ozel varsayilan model, genel varsayilandan onceliklidir.
        if ( $model === '' && ! empty( $info['default_models'][ $capability ] ) ) {
            $model = (string) $info['default_models'][ $capability ];
        }
        if ( $model === '' && ! empty( $info['default_model'] ) ) {
            $model = (string) $info['default_model'];
        }

        $auth = [];
        foreach ( ( $info['auth'] ?? [] ) as $k => $v ) {
            $auth[ $k ] = str_replace( '{key}', $api_key, (string) $v );
        }

        $endpoint = isset( $info['submit_url'] ) ? (string) $info['submit_url'] : (string) ( $info['chat_url'] ?? '' );
        $voice    = isset( $args['voice'] ) ? sanitize_text_field( (string) $args['voice'] ) : '';
        $endpoint = str_replace( [ '{model}', '{key}', '{voice}' ], [ $model, $api_key, rawurlencode( $voice ) ], $endpoint );

        $caps_meta = agfo_ai_capabilities();

        $config = [
            'code'          => $provider,
            'provider_name' => isset( $info['label'] ) ? (string) $info['label'] : $provider,
            'capability'    => $capability,
            'model'         => $model,
            'key'           => $api_key,
            'endpoint'      => $endpoint,
            'chat_url'      => $endpoint, // Eski sozlesmeye alisik cagiricilar icin ayni deger.
            'auth'          => $auth,
            'provider_info' => $info,
            'transport'     => isset( $caps_meta[ $capability ]['transport'] ) ? (string) $caps_meta[ $capability ]['transport'] : 'sync',
            'poll_style'    => isset( $info['poll_style'] ) ? (string) $info['poll_style'] : '',
        ];

        return apply_filters( 'agfo_capability_config', $config, $capability, $args );
    }
}

if ( ! function_exists( 'agfo_capability_request' ) ) {
    /**
     * Yetenek tabanli tek adimli istek: cozumle + gonder + gerekirse poll et.
     *
     * Donen dizi agfo_api_post() ile ayni sekle sahiptir
     * ( http_code / body / stage ), boylece cagirici tarafi tanidik kalir.
     *
     * @param string $capability Yetenek anahtari.
     * @param array  $body       JSON govdesi (dizi olarak).
     * @param array  $options    'timeout', 'model', 'source', 'progress', 'poll_budget'.
     * @return array|WP_Error
     */
    function agfo_capability_request( string $capability, array $body, array $options = [] ) {
        $capability = sanitize_key( $capability );
        if ( in_array( $capability, [ 'speech_synthesize', 'music_generate' ], true ) && function_exists( 'agfo_job_submit' ) ) {
            return agfo_job_submit(
                $capability,
                $body,
                [
                    'provider'        => sanitize_key( (string) ( $options['provider'] ?? '' ) ),
                    'model'           => sanitize_text_field( (string) ( $options['model'] ?? '' ) ),
                    'source_plugin'   => sanitize_key( (string) ( $options['source'] ?? 'capability' ) ),
                    'created_by'      => absint( $options['created_by'] ?? get_current_user_id() ),
                    'idempotency_key' => sanitize_text_field( (string) ( $options['idempotency_key'] ?? '' ) ),
                ]
            );
        }

        $config = agfo_get_provider_for_capability( $capability, [
            'model' => isset( $options['model'] ) ? (string) $options['model'] : '',
        ] );
        if ( is_wp_error( $config ) ) return $config;

        $headers = array_merge( [ 'Content-Type' => 'application/json' ], $config['auth'] );

        $post_options = [
            'provider_code' => $config['code'],
            'model'         => $config['model'],
            'capability'    => $capability, // Fusion ve chat-ozel normalizasyonlar bunu gorup atlar.
            'source'        => isset( $options['source'] ) ? (string) $options['source'] : 'capability',
        ];
        if ( isset( $options['timeout'] ) )  $post_options['timeout']  = (int) $options['timeout'];
        if ( isset( $options['progress'] ) ) $post_options['progress'] = $options['progress'];
        if ( isset( $options['poll_budget'] ) ) $post_options['poll_budget'] = (int) $options['poll_budget'];

        return agfo_api_post( $config['endpoint'], $headers, $body, $post_options );
    }
}

if ( ! function_exists( 'agfo_get_translation_config' ) ) {
    /**
     * Chat config for translation work (17.1.0). Same keys as agfo_get_priority_api_key():
     * code, model, key, chat_url, auth, supports_temperature, transport_route …
     * Uses the model chosen in AI Kontrol Merkezi › Çeviri, or the default chat model.
     *
     * @return array|false
     */
    function agfo_get_translation_config() {
        $config = agfo_get_provider_for_capability( 'text_translate' );
        return is_wp_error( $config ) ? false : $config;
    }
}
