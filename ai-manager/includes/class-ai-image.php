<?php
/**
 * AGFO AI Manager — Generated image handling.
 *
 * Added in 16.16.0. Mirrors includes/class-ai-media.php, which is audio-only:
 * the audio MIME whitelist there deliberately rejects image types, so images
 * need their own whitelist, their own response shapes and their own
 * featured-image wiring. Nothing in this file changes an existing signature.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) exit;

if ( ! function_exists( 'agfo_ai_image_allowed_types' ) ) {
    /**
     * Accepted image types. Nothing outside this whitelist is ever written.
     *
     * @return array<string,string> mime => extension
     */
    function agfo_ai_image_allowed_types(): array {
        return apply_filters( 'agfo_ai_image_allowed_types', [
            'image/png'  => 'png',
            'image/jpeg' => 'jpg',
            'image/jpg'  => 'jpg',
            'image/webp' => 'webp',
        ] );
    }
}

if ( ! function_exists( 'agfo_ai_image_extension_for_mime' ) ) {
    function agfo_ai_image_extension_for_mime( string $mime ): string {
        $allowed = agfo_ai_image_allowed_types();
        $mime    = strtolower( trim( explode( ';', $mime )[0] ) );
        return isset( $allowed[ $mime ] ) ? $allowed[ $mime ] : '';
    }
}

if ( ! function_exists( 'agfo_ai_image_sniff_mime' ) ) {
    /**
     * Detect the MIME type from the binary signature.
     *
     * Providers are inconsistent about content-type headers, and a wrong
     * extension breaks WordPress thumbnail generation. The bytes are the
     * only trustworthy source.
     */
    function agfo_ai_image_sniff_mime( string $bin ): string {
        if ( strlen( $bin ) < 12 ) return '';
        if ( substr( $bin, 0, 8 ) === "\x89PNG\x0d\x0a\x1a\x0a" ) return 'image/png';
        if ( substr( $bin, 0, 3 ) === "\xff\xd8\xff" ) return 'image/jpeg';
        if ( substr( $bin, 0, 4 ) === 'RIFF' && substr( $bin, 8, 4 ) === 'WEBP' ) return 'image/webp';
        return '';
    }
}

if ( ! function_exists( 'agfo_ai_store_generated_image' ) ) {
    /**
     * Write a generated image into the media library.
     *
     * Accepts either raw/base64 data or a remote URL.
     *
     * @param array $payload 'data' (raw or base64) or 'url'; 'mime'; 'filename'.
     * @param array $args    'title', 'post_id', 'source', 'alt', 'caption',
     *                       'description', 'set_featured'.
     * @return array|WP_Error [ 'attachment_id', 'url', 'thumb_url', 'mime', 'bytes', 'width', 'height', 'featured' ]
     */
    function agfo_ai_store_generated_image( array $payload, array $args = [] ) {
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
                return new WP_Error( 'agfo_image_bad_url', 'Geçersiz görsel adresi.' );
            }

            $response = wp_remote_get( $url, [ 'timeout' => 120, 'sslverify' => true ] );
            if ( is_wp_error( $response ) ) {
                return new WP_Error( 'agfo_image_fetch', 'Görsel indirilemedi: ' . $response->get_error_message() );
            }
            $code = (int) wp_remote_retrieve_response_code( $response );
            if ( $code < 200 || $code >= 300 ) {
                return new WP_Error( 'agfo_image_fetch', 'Görsel indirilemedi. HTTP ' . $code );
            }

            $bin = (string) wp_remote_retrieve_body( $response );
            if ( $mime === '' ) {
                $mime = (string) wp_remote_retrieve_header( $response, 'content-type' );
            }
        } elseif ( ! empty( $payload['data'] ) ) {
            $raw = (string) $payload['data'];

            // data:image/png;base64,.... is also accepted.
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
            return new WP_Error( 'agfo_image_empty', 'Kaydedilecek görsel verisi yok.' );
        }

        if ( $bin === '' ) {
            return new WP_Error( 'agfo_image_empty', 'Görsel verisi boş.' );
        }

        // The binary signature always wins over the declared MIME type.
        $sniffed = agfo_ai_image_sniff_mime( $bin );
        if ( $sniffed !== '' ) {
            $mime = $sniffed;
        }

        $ext = agfo_ai_image_extension_for_mime( $mime );
        if ( $ext === '' ) {
            $name_hint = isset( $payload['filename'] ) ? (string) $payload['filename'] : '';
            $hint_ext  = strtolower( (string) pathinfo( $name_hint, PATHINFO_EXTENSION ) );
            $ext       = in_array( $hint_ext, array_values( agfo_ai_image_allowed_types() ), true ) ? $hint_ext : '';
        }
        if ( $ext === '' ) {
            return new WP_Error( 'agfo_image_mime', 'Desteklenmeyen görsel tipi: ' . ( $mime !== '' ? $mime : 'bilinmiyor' ) );
        }

        $title = isset( $args['title'] ) ? trim( (string) $args['title'] ) : '';
        $base  = $title !== '' ? sanitize_file_name( $title ) : 'agfo-ai-image';
        if ( $base === '' ) $base = 'agfo-ai-image';
        $filename = $base . '-' . gmdate( 'Ymd-His' ) . '-' . wp_generate_password( 6, false, false ) . '.' . $ext;

        $tmp = wp_tempnam( $filename );
        if ( ! $tmp ) {
            return new WP_Error( 'agfo_image_tmp', 'Geçici dosya oluşturulamadı.' );
        }
        if ( file_put_contents( $tmp, $bin ) === false ) {
            @unlink( $tmp );
            return new WP_Error( 'agfo_image_write', 'Geçici dosyaya yazılamadı.' );
        }

        $file_array = [ 'name' => $filename, 'tmp_name' => $tmp ];
        $post_id    = isset( $args['post_id'] ) ? (int) $args['post_id'] : 0;

        $attachment_id = media_handle_sideload(
            $file_array,
            $post_id,
            $title !== '' ? $title : null,
            [
                'post_content' => isset( $args['description'] ) ? sanitize_textarea_field( (string) $args['description'] ) : '',
                'post_excerpt' => isset( $args['caption'] ) ? sanitize_text_field( (string) $args['caption'] ) : '',
            ]
        );

        if ( is_wp_error( $attachment_id ) ) {
            @unlink( $tmp );
            return $attachment_id;
        }

        if ( ! empty( $args['alt'] ) ) {
            update_post_meta( $attachment_id, '_wp_attachment_image_alt', sanitize_text_field( (string) $args['alt'] ) );
        }
        if ( ! empty( $args['source'] ) ) {
            update_post_meta( $attachment_id, '_agfo_ai_source', sanitize_text_field( (string) $args['source'] ) );
        }
        if ( ! empty( $args['prompt'] ) ) {
            update_post_meta( $attachment_id, '_agfo_ai_image_prompt', sanitize_textarea_field( (string) $args['prompt'] ) );
        }
        update_post_meta( $attachment_id, '_agfo_ai_generated', 1 );

        $featured = false;
        if ( ! empty( $args['set_featured'] ) && $post_id > 0 ) {
            $featured = (bool) set_post_thumbnail( $post_id, (int) $attachment_id );
        }

        $meta  = wp_get_attachment_metadata( $attachment_id );
        $thumb = wp_get_attachment_image_src( $attachment_id, 'medium' );

        return [
            'attachment_id' => (int) $attachment_id,
            'url'           => (string) wp_get_attachment_url( $attachment_id ),
            'thumb_url'     => is_array( $thumb ) && ! empty( $thumb[0] ) ? (string) $thumb[0] : (string) wp_get_attachment_url( $attachment_id ),
            'mime'          => (string) get_post_mime_type( $attachment_id ),
            'bytes'         => strlen( $bin ),
            'width'         => is_array( $meta ) && isset( $meta['width'] ) ? (int) $meta['width'] : 0,
            'height'        => is_array( $meta ) && isset( $meta['height'] ) ? (int) $meta['height'] : 0,
            'featured'      => $featured,
        ];
    }
}

if ( ! function_exists( 'agfo_ai_extract_image_from_response' ) ) {
    /**
     * Pull image data or a URL out of a provider response.
     *
     * Known shapes are tried in order; if none match, a recursive scan looks
     * for any base64 image field or image URL. An unrecognised shape returns
     * WP_Error instead of silently producing a broken attachment.
     *
     * @param array|string $response Decoded array or raw JSON.
     * @return array|WP_Error [ 'url' ] or [ 'data', 'mime' ]
     */
    function agfo_ai_extract_image_from_response( $response ) {
        $data = is_string( $response ) ? json_decode( $response, true ) : $response;
        if ( ! is_array( $data ) ) {
            return new WP_Error( 'agfo_image_parse', 'Yanıt çözümlenemedi.' );
        }

        $pluck = static function ( array $root, array $path ) {
            $node = $root;
            foreach ( $path as $seg ) {
                if ( is_array( $node ) && isset( $node[ $seg ] ) ) {
                    $node = $node[ $seg ];
                } else {
                    return null;
                }
            }
            return $node;
        };

        // 1) Base64 shapes.
        $data_paths = [
            // OpenAI Images API.
            [ [ 'data', 0, 'b64_json' ], '' ],
            // Google Imagen predict.
            [ [ 'predictions', 0, 'bytesBase64Encoded' ], [ 'predictions', 0, 'mimeType' ] ],
            // Gemini generateContent inline image part.
            [ [ 'candidates', 0, 'content', 'parts', 0, 'inlineData', 'data' ], [ 'candidates', 0, 'content', 'parts', 0, 'inlineData', 'mimeType' ] ],
            [ [ 'candidates', 0, 'content', 'parts', 1, 'inlineData', 'data' ], [ 'candidates', 0, 'content', 'parts', 1, 'inlineData', 'mimeType' ] ],
            // MiniMax / generic.
            [ [ 'data', 'image_base64', 0 ], '' ],
            [ [ 'image_base64' ], '' ],
            [ [ 'images', 0, 'b64_json' ], [ 'images', 0, 'content_type' ] ],
        ];
        foreach ( $data_paths as $pair ) {
            $node = $pluck( $data, $pair[0] );
            if ( is_string( $node ) && $node !== '' ) {
                $mime = '';
                if ( is_array( $pair[1] ) ) {
                    $found = $pluck( $data, $pair[1] );
                    if ( is_string( $found ) ) $mime = $found;
                }
                return [ 'data' => $node, 'mime' => $mime !== '' ? $mime : 'image/png' ];
            }
        }

        // 2) URL shapes.
        $url_paths = [
            [ [ 'data', 0, 'url' ], '' ],
            [ [ 'images', 0, 'url' ], [ 'images', 0, 'content_type' ] ],
            [ [ 'image', 'url' ], '' ],
            [ [ 'output', 0, 'url' ], '' ],
            [ [ 'data', 'image_urls', 0 ], '' ],
            [ [ 'image_urls', 0 ], '' ],
            // OpenRouter image-capable chat models.
            [ [ 'choices', 0, 'message', 'images', 0, 'image_url', 'url' ], '' ],
        ];
        foreach ( $url_paths as $pair ) {
            $node = $pluck( $data, $pair[0] );
            if ( is_string( $node ) && $node !== '' ) {
                if ( strpos( $node, 'data:' ) === 0 ) {
                    return [ 'data' => $node, 'mime' => '' ];
                }
                $mime = '';
                if ( is_array( $pair[1] ) ) {
                    $found = $pluck( $data, $pair[1] );
                    if ( is_string( $found ) ) $mime = $found;
                }
                return [ 'url' => $node, 'mime' => $mime ];
            }
        }

        // 3) Recursive fallback for provider shapes not yet catalogued.
        $found = agfo_ai_image_scan_for_payload( $data );
        if ( is_array( $found ) ) {
            return $found;
        }

        return new WP_Error( 'agfo_image_shape', 'Yanıtta tanınan bir görsel alanı bulunamadı.' );
    }
}

if ( ! function_exists( 'agfo_ai_image_scan_for_payload' ) ) {
    /**
     * Recursive last-resort scan for an image payload.
     *
     * @param mixed $node
     * @param int   $depth
     * @return array|null
     */
    function agfo_ai_image_scan_for_payload( $node, int $depth = 0 ) {
        if ( $depth > 8 || ! is_array( $node ) ) return null;

        $b64_keys = [ 'b64_json', 'bytesBase64Encoded', 'image_base64', 'imageBytes', 'b64', 'base64' ];
        foreach ( $b64_keys as $key ) {
            if ( isset( $node[ $key ] ) && is_string( $node[ $key ] ) && strlen( $node[ $key ] ) > 256 ) {
                return [ 'data' => $node[ $key ], 'mime' => 'image/png' ];
            }
        }

        foreach ( $node as $value ) {
            if ( is_string( $value ) ) {
                if ( strpos( $value, 'data:image/' ) === 0 ) {
                    return [ 'data' => $value, 'mime' => '' ];
                }
                if ( preg_match( '#^https?://[^\s"\']+\.(png|jpe?g|webp)(\?[^\s"\']*)?$#i', $value ) ) {
                    return [ 'url' => $value, 'mime' => '' ];
                }
            } elseif ( is_array( $value ) ) {
                $found = agfo_ai_image_scan_for_payload( $value, $depth + 1 );
                if ( is_array( $found ) ) return $found;
            }
        }

        return null;
    }
}
