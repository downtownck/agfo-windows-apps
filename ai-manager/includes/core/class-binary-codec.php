<?php
/**
 * AGFO AI Manager — single audited Base64 codec.
 *
 * Added in 17.1.2. Every Base64 conversion in the plugin goes through here:
 *  - OpenAI, Gemini, MiniMax and OpenRouter return generated images and audio as Base64
 *    text inside JSON; those bytes are decoded once and written to the media library.
 *  - Stored provider API keys are AES-256-CBC ciphertext kept as Base64 text.
 *
 * Decoding never executes or evaluates anything. libsodium's constant-time decoder
 * (bundled with PHP 7.2+ and polyfilled by WordPress core) is preferred because API-key
 * ciphertext passes through it; the standard decoder is only a fallback for hosts that
 * lack both. Output is binary data that callers validate (MIME sniffing, decryption).
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Binary_Codec' ) ) {
    final class AGFO_AIM_Binary_Codec {

        /**
         * Strictly decode standard or URL-safe Base64, with or without padding.
         *
         * @return string|null Binary data, or null when the input is not valid Base64.
         */
        public static function decode( string $text ): ?string {
            $clean = (string) preg_replace( '/\s+/', '', $text );
            if ( '' === $clean ) {
                return null;
            }
            // URL-safe alphabet → standard alphabet.
            $clean = strtr( $clean, '-_', '+/' );
            if ( ! preg_match( '#^[A-Za-z0-9+/]+={0,2}$#', $clean ) ) {
                return null;
            }

            if ( function_exists( 'sodium_base642bin' ) && defined( 'SODIUM_BASE64_VARIANT_ORIGINAL_NO_PADDING' ) ) {
                try {
                    $binary = sodium_base642bin( rtrim( $clean, '=' ), SODIUM_BASE64_VARIANT_ORIGINAL_NO_PADDING );
                    return '' === $binary ? null : $binary;
                } catch ( \Throwable $e ) {
                    return null;
                }
            }

            // Fallback for hosts without libsodium and without the WordPress polyfill.
            $binary = base64_decode( $clean, true ); // Decodes provider media / key ciphertext only; nothing is executed.
            return ( false === $binary || '' === $binary ) ? null : $binary;
        }

        /**
         * Standard padded Base64, byte-identical to base64_encode().
         */
        public static function encode( string $binary ): string {
            if ( function_exists( 'sodium_bin2base64' ) && defined( 'SODIUM_BASE64_VARIANT_ORIGINAL' ) ) {
                return sodium_bin2base64( $binary, SODIUM_BASE64_VARIANT_ORIGINAL );
            }
            return base64_encode( $binary ); // Fallback; same output.
        }

        /**
         * Split a data: URI into [ mime, payload ]; plain Base64 returns [ '', input ].
         *
         * @return array{0:string,1:string}
         */
        public static function split_data_uri( string $raw ): array {
            if ( 0 === strpos( $raw, 'data:' ) && false !== strpos( $raw, ',' ) ) {
                [ $meta, $payload ] = explode( ',', $raw, 2 );
                $mime = preg_match( '#data:([^;,]+)#i', $meta, $m ) ? (string) $m[1] : '';
                return [ $mime, $payload ];
            }
            return [ '', $raw ];
        }
    }
}
