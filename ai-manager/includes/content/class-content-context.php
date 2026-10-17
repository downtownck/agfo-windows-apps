<?php
/**
 * Builds a safe, structured page context for Content Studio.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Content_Context' ) ) {
    final class AGFO_AIM_Content_Context {
        /**
         * Metadata that should never be sent to a language model.
         */
        private const SENSITIVE_KEY_PATTERN = '/(?:password|passwd|passphrase|secret|token|nonce|api[_-]?key|access[_-]?key|private[_-]?key|oauth|authorization|auth[_-]?|cookie|session|license[_-]?key|webhook|signature|salt|credit|card|iban|swift|email|e[_-]?mail|phone|mobile|meeting[_-]?(?:url|link)|zoom|teams|portal[_-]?(?:url|link)|login[_-]?(?:url|link))/i';

        /**
         * Large/internal WordPress or builder metadata that adds noise rather than page meaning.
         */
        private const NOISE_KEYS = [
            '_edit_lock',
            '_edit_last',
            '_wp_old_slug',
            '_wp_attached_file',
            '_wp_attachment_metadata',
            '_thumbnail_id',
            '_elementor_data',
            '_elementor_css',
            '_elementor_page_settings',
            '_vc_post_settings',
            '_wpb_vc_js_status',
        ];

        /**
         * Build the current post/page context.
         *
         * @return array{prompt:string,meta_count:int,taxonomy_count:int,post_type:string,title:string}
         */
        public static function build( int $post_id, string $current_title = '' ): array {
            $empty = [
                'prompt'         => '',
                'meta_count'     => 0,
                'taxonomy_count' => 0,
                'post_type'      => '',
                'title'          => '',
            ];

            if ( $post_id <= 0 || ! current_user_can( 'edit_post', $post_id ) ) {
                return $empty;
            }

            $post = get_post( $post_id );
            if ( ! $post instanceof WP_Post ) {
                return $empty;
            }

            $title = trim( sanitize_text_field( $current_title ) );
            if ( '' === $title ) {
                $title = get_the_title( $post );
            }

            $lines   = [];
            $lines[] = 'PAGE/POST CONTEXT (authoritative facts about this specific WordPress item):';
            $lines[] = '- Post ID: ' . $post_id;
            $lines[] = '- Post type: ' . sanitize_key( $post->post_type );
            $lines[] = '- Status: ' . sanitize_key( $post->post_status );
            if ( '' !== $title ) {
                $lines[] = '- Title: ' . self::clean_scalar( $title, 500 );
            }
            if ( '' !== trim( (string) $post->post_excerpt ) ) {
                $lines[] = '- Excerpt: ' . self::clean_scalar( $post->post_excerpt, 1200 );
            }

            $taxonomy_count = 0;
            $taxonomies     = get_object_taxonomies( $post->post_type, 'objects' );
            foreach ( $taxonomies as $taxonomy => $object ) {
                $terms = get_the_terms( $post_id, $taxonomy );
                if ( is_wp_error( $terms ) || empty( $terms ) ) {
                    continue;
                }
                $names = [];
                foreach ( $terms as $term ) {
                    if ( $term instanceof WP_Term && '' !== trim( $term->name ) ) {
                        $names[] = self::clean_scalar( $term->name, 240 );
                    }
                }
                if ( empty( $names ) ) {
                    continue;
                }
                $taxonomy_count++;
                $label   = isset( $object->labels->singular_name ) ? (string) $object->labels->singular_name : (string) $taxonomy;
                $lines[] = '- Taxonomy ' . self::clean_scalar( $label, 120 ) . ': ' . implode( ', ', array_unique( $names ) );
            }

            $raw_meta   = get_post_meta( $post_id );
            $meta_lines = [];
            foreach ( $raw_meta as $key => $values ) {
                if ( ! self::allow_meta_key( (string) $key ) ) {
                    continue;
                }

                $clean_values = [];
                foreach ( (array) $values as $value ) {
                    $decoded = maybe_unserialize( $value );
                    $flat    = self::flatten_value( $decoded );
                    if ( '' !== $flat ) {
                        $clean_values[] = $flat;
                    }
                }

                $clean_values = array_values( array_unique( array_filter( $clean_values ) ) );
                if ( empty( $clean_values ) ) {
                    continue;
                }

                $meta_lines[] = '- Meta [' . sanitize_text_field( (string) $key ) . ']: ' . implode( ' | ', array_slice( $clean_values, 0, 8 ) );
                if ( count( $meta_lines ) >= 80 ) {
                    break;
                }
            }

            /**
             * Filter context metadata after built-in secret/noise removal.
             * Plugins may add their own public course fields here.
             */
            $meta_lines = apply_filters( 'agfo_ai_content_context_meta_lines', $meta_lines, $post_id, $post );
            if ( ! is_array( $meta_lines ) ) {
                $meta_lines = [];
            }

            if ( ! empty( $meta_lines ) ) {
                $lines[] = 'SAVED CUSTOM FIELDS / META:';
                foreach ( array_slice( $meta_lines, 0, 80 ) as $line ) {
                    $lines[] = self::clean_scalar( (string) $line, 2200 );
                }
            }

            $prompt = implode( "\n", $lines );
            if ( strlen( $prompt ) > 24000 ) {
                $prompt = substr( $prompt, 0, 24000 ) . "\n[Context truncated for model safety.]";
            }

            return [
                'prompt'         => $prompt,
                'meta_count'     => count( $meta_lines ),
                'taxonomy_count' => $taxonomy_count,
                'post_type'      => sanitize_key( $post->post_type ),
                'title'          => $title,
            ];
        }

        private static function allow_meta_key( string $key ): bool {
            if ( '' === trim( $key ) || in_array( $key, self::NOISE_KEYS, true ) ) {
                return false;
            }
            if ( preg_match( self::SENSITIVE_KEY_PATTERN, $key ) ) {
                return false;
            }
            // Hidden custom fields may contain real course data, so they are allowed here.
            // ACF's companion field references (field_abc123) are filtered by value below.
            return true;
        }

        private static function flatten_value( $value, int $depth = 0 ): string {
            if ( $depth > 3 || null === $value || false === $value || '' === $value ) {
                return '';
            }

            if ( is_scalar( $value ) ) {
                $text = self::clean_scalar( (string) $value, 1800 );
                if ( preg_match( '/^field_[a-z0-9]+$/i', $text ) ) {
                    return '';
                }
                if ( self::looks_sensitive_value( $text ) ) {
                    return '';
                }
                return $text;
            }

            if ( is_object( $value ) ) {
                $value = get_object_vars( $value );
            }

            if ( is_array( $value ) ) {
                $parts = [];
                $seen  = 0;
                foreach ( $value as $key => $item ) {
                    if ( $seen >= 24 ) {
                        break;
                    }
                    if ( is_string( $key ) && preg_match( self::SENSITIVE_KEY_PATTERN, $key ) ) {
                        continue;
                    }
                    $flat = self::flatten_value( $item, $depth + 1 );
                    if ( '' === $flat ) {
                        continue;
                    }
                    $prefix  = is_string( $key ) ? self::clean_scalar( $key, 120 ) . '=' : '';
                    $parts[] = $prefix . $flat;
                    $seen++;
                }
                return self::clean_scalar( implode( '; ', $parts ), 1800 );
            }

            return '';
        }

        private static function clean_scalar( string $value, int $limit ): string {
            $value = wp_strip_all_tags( $value, true );
            $value = html_entity_decode( $value, ENT_QUOTES, get_bloginfo( 'charset' ) ?: 'UTF-8' );
            $value = preg_replace( '/\s+/u', ' ', $value );
            $value = trim( (string) $value );
            if ( strlen( $value ) > $limit ) {
                $value = substr( $value, 0, $limit ) . '…';
            }
            return $value;
        }

        private static function looks_sensitive_value( string $value ): bool {
            if ( preg_match( '/^[A-Za-z0-9+\/_=-]{40,}$/', $value ) ) {
                return true;
            }
            if ( preg_match( '/\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+\/-]+=*/i', $value ) ) {
                return true;
            }
            return false;
        }
    }
}
