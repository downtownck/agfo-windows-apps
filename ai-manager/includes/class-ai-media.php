<?php
/**
 * AGFO AI Manager — Uretilen Medyanin Kutuphaneye Aktarimi.
 *
 * 16.6.0 ile eklendi. Async is sonuclari transient'te saklandigi icin,
 * cok megabaytlik base64 ses verisinin wp_options'a dusmesi istenmez.
 * Bu katman uretilen sesi medya kutuphanesine yazar; cagirici tarafi
 * sadece attachment ID tasir.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) exit;

if ( ! function_exists( 'agfo_ai_media_allowed_types' ) ) {
    /**
     * Kabul edilen ses tipleri. Beyaz liste disi hicbir sey yazilmaz.
     *
     * @return array<string,string> mime => uzanti
     */
    function agfo_ai_media_allowed_types(): array {
        return apply_filters( 'agfo_ai_media_allowed_types', [
            'audio/mpeg'  => 'mp3',
            'audio/mp3'   => 'mp3',
            'audio/wav'   => 'wav',
            'audio/x-wav' => 'wav',
            'audio/wave'  => 'wav',
            'audio/ogg'   => 'ogg',
            'audio/webm'  => 'webm',
            'audio/flac'  => 'flac',
            'audio/mp4'   => 'm4a',
            'audio/aac'   => 'm4a',
        ] );
    }
}

if ( ! function_exists( 'agfo_ai_media_extension_for_mime' ) ) {
    function agfo_ai_media_extension_for_mime( string $mime ): string {
        $allowed = agfo_ai_media_allowed_types();
        $mime    = strtolower( trim( explode( ';', $mime )[0] ) );
        return isset( $allowed[ $mime ] ) ? $allowed[ $mime ] : '';
    }
}

if ( ! function_exists( 'agfo_ai_store_generated_media' ) ) {
    /**
     * Uretilen sesi medya kutuphanesine yazar.
     *
     * Girdi olarak ya ham/base64 veri ya da uzak bir URL kabul eder.
     *
     * @param array $payload 'data' (ham veya base64) veya 'url'; 'mime'; 'filename'.
     * @param array $args    'title', 'post_id', 'source'.
     * @return array|WP_Error [ 'attachment_id', 'url', 'mime', 'bytes' ]
     */
    function agfo_ai_store_generated_media( array $payload, array $args = [] ) {
        if ( ! function_exists( 'wp_handle_sideload' ) ) {
            require_once ABSPATH . 'wp-admin/includes/file.php';
        }
        if ( ! function_exists( 'wp_generate_attachment_metadata' ) ) {
            require_once ABSPATH . 'wp-admin/includes/image.php';
        }
        if ( ! function_exists( 'media_handle_sideload' ) ) {
            require_once ABSPATH . 'wp-admin/includes/media.php';
        }

        $mime = isset( $payload['mime'] ) ? (string) $payload['mime'] : '';
        $bin  = '';

        if ( ! empty( $payload['url'] ) ) {
            $url = esc_url_raw( (string) $payload['url'] );
            if ( ! wp_http_validate_url( $url ) ) {
                return new WP_Error( 'agfo_media_bad_url', 'Gecersiz medya URL.' );
            }

            $response = wp_remote_get( $url, [ 'timeout' => 120, 'sslverify' => true ] );
            if ( is_wp_error( $response ) ) {
                return new WP_Error( 'agfo_media_fetch', 'Medya indirilemedi: ' . $response->get_error_message() );
            }
            $code = (int) wp_remote_retrieve_response_code( $response );
            if ( $code < 200 || $code >= 300 ) {
                return new WP_Error( 'agfo_media_fetch', 'Medya indirilemedi. HTTP ' . $code );
            }

            $bin = (string) wp_remote_retrieve_body( $response );
            if ( $mime === '' ) {
                $mime = (string) wp_remote_retrieve_header( $response, 'content-type' );
            }
        } elseif ( ! empty( $payload['data'] ) ) {
            $raw = (string) $payload['data'];

            // data:audio/mpeg;base64,.... bicimini de kabul et.
            if ( strpos( $raw, 'data:' ) === 0 && strpos( $raw, ',' ) !== false ) {
                [ $meta, $raw ] = explode( ',', $raw, 2 );
                if ( $mime === '' && preg_match( '#data:([^;]+)#i', $meta, $m ) ) {
                    $mime = $m[1];
                }
            }

            // CHANGED 17.1.2: decode through the single audited codec.
            $decoded = class_exists( 'AGFO_AIM_Binary_Codec' ) ? AGFO_AIM_Binary_Codec::decode( $raw ) : null;
            $bin     = ( null !== $decoded ) ? $decoded : $raw;
        } else {
            return new WP_Error( 'agfo_media_empty', 'Kaydedilecek medya verisi yok.' );
        }

        if ( $bin === '' ) {
            return new WP_Error( 'agfo_media_empty', 'Medya verisi bos.' );
        }

        $ext = agfo_ai_media_extension_for_mime( $mime );
        if ( $ext === '' ) {
            // MIME guvenilir degilse dosya adindan tureten son bir deneme.
            $name_hint = isset( $payload['filename'] ) ? (string) $payload['filename'] : '';
            $hint_ext  = strtolower( (string) pathinfo( $name_hint, PATHINFO_EXTENSION ) );
            $ext       = in_array( $hint_ext, array_values( agfo_ai_media_allowed_types() ), true ) ? $hint_ext : '';
        }
        if ( $ext === '' ) {
            return new WP_Error( 'agfo_media_mime', 'Desteklenmeyen medya tipi: ' . ( $mime !== '' ? $mime : 'bilinmiyor' ) );
        }

        $base = isset( $args['title'] ) && $args['title'] !== ''
            ? sanitize_file_name( (string) $args['title'] )
            : 'agfo-ai-audio';
        $filename = $base . '-' . gmdate( 'Ymd-His' ) . '-' . wp_generate_password( 6, false, false ) . '.' . $ext;

        $tmp = wp_tempnam( $filename );
        if ( ! $tmp ) {
            return new WP_Error( 'agfo_media_tmp', 'Gecici dosya olusturulamadi.' );
        }
        if ( file_put_contents( $tmp, $bin ) === false ) {
            @unlink( $tmp );
            return new WP_Error( 'agfo_media_write', 'Gecici dosyaya yazilamadi.' );
        }

        $file_array = [ 'name' => $filename, 'tmp_name' => $tmp ];
        $post_id    = isset( $args['post_id'] ) ? (int) $args['post_id'] : 0;

        $attachment_id = media_handle_sideload( $file_array, $post_id, isset( $args['title'] ) ? (string) $args['title'] : null );

        if ( is_wp_error( $attachment_id ) ) {
            @unlink( $tmp );
            return $attachment_id;
        }

        if ( ! empty( $args['source'] ) ) {
            update_post_meta( $attachment_id, '_agfo_ai_source', sanitize_text_field( (string) $args['source'] ) );
        }
        update_post_meta( $attachment_id, '_agfo_ai_generated', 1 );

        return [
            'attachment_id' => (int) $attachment_id,
            'url'           => (string) wp_get_attachment_url( $attachment_id ),
            'mime'          => (string) get_post_mime_type( $attachment_id ),
            'bytes'         => strlen( $bin ),
        ];
    }
}

if ( ! function_exists( 'agfo_ai_extract_media_from_response' ) ) {
    /**
     * Saglayici yanitindan ses verisini/URL'ini cikarir.
     *
     * Farkli saglayicilar farkli sekiller kullanir; bilinen yollari sirayla
     * dener ve ilk eslesmeyi dondurur. Tanimadigi bir sekil gelirse
     * WP_Error doner, sessizce yanlis veri uretmez.
     *
     * @param array|string $response Coozulmus dizi veya ham JSON.
     * @return array|WP_Error [ 'url' ] veya [ 'data', 'mime' ]
     */
    function agfo_ai_extract_media_from_response( $response ) {
        $data = is_string( $response ) ? json_decode( $response, true ) : $response;
        if ( ! is_array( $data ) ) {
            return new WP_Error( 'agfo_media_parse', 'Yanit cozumlenemedi.' );
        }

        $url_paths = [
            [ 'audio', 'url' ],
            [ 'audio_url' ],
            [ 'output', 'url' ],
            [ 'audio_file', 'url' ],
            [ 'data', 0, 'url' ],
        ];
        foreach ( $url_paths as $path ) {
            $node = $data;
            foreach ( $path as $seg ) {
                if ( is_array( $node ) && isset( $node[ $seg ] ) ) {
                    $node = $node[ $seg ];
                } else {
                    $node = null;
                    break;
                }
            }
            if ( is_string( $node ) && $node !== '' ) {
                return [ 'url' => $node ];
            }
        }

        $data_paths = [
            [ 'audio', 'data' ],
            [ 'audio_base64' ],
            [ 'data', 0, 'b64_audio' ],
        ];
        foreach ( $data_paths as $path ) {
            $node = $data;
            foreach ( $path as $seg ) {
                if ( is_array( $node ) && isset( $node[ $seg ] ) ) {
                    $node = $node[ $seg ];
                } else {
                    $node = null;
                    break;
                }
            }
            if ( is_string( $node ) && $node !== '' ) {
                $mime = '';
                if ( isset( $data['audio']['content_type'] ) ) $mime = (string) $data['audio']['content_type'];
                if ( $mime === '' && isset( $data['content_type'] ) ) $mime = (string) $data['content_type'];
                return [ 'data' => $node, 'mime' => $mime !== '' ? $mime : 'audio/mpeg' ];
            }
        }

        return new WP_Error( 'agfo_media_shape', 'Yanitta taninan bir ses alani bulunamadi.' );
    }
}
