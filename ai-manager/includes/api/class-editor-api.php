<?php
/**
 * NEW 17.4.0: REST API for the AGFO AI Editor (Windows desktop text editor).
 *
 * Namespace agfo-ai/v1:
 *   GET  /editor/info       capabilities, prompt templates, configured text/translation model names
 *   POST /editor/transform  content transformation (same service as the Classic Editor Content Studio)
 *   POST /editor/chat       writing-assistant chat about the user's document
 *
 * Authentication is WordPress' own (Application Passwords over HTTPS, or a logged-in cookie session
 * with the REST nonce). Every route requires the Content Studio capability (default manage_options).
 * API keys never leave the server; responses contain provider and model NAMES only.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Editor_API' ) ) {
    final class AGFO_AIM_Editor_API {
        public const NAMESPACE_V1  = 'agfo-ai/v1';
        public const API_VERSION   = 1;
        public const MAX_CHARS     = 60000;
        public const MAX_MESSAGES  = 40;
        public const MAX_MSG_CHARS = 20000;

        public const AUTH_HEADER   = 'HTTP_X_AGFO_EDITOR_AUTH';

        /** @var WP_Error|null Application Password error from the X-AGFO-Editor-Auth fallback (17.4.1). */
        private static $auth_error = null;
        /** @var bool True only while our own fallback calls wp_authenticate_application_password(). */
        private static $in_auth = false;

        public static function register_hooks(): void {
            add_action( 'rest_api_init', [ __CLASS__, 'register_routes' ] );
            // NEW 17.4.1: some LiteSpeed/CGI setups drop the Authorization header before PHP sees it,
            // so WordPress' Application Password check never runs and every request is anonymous (401).
            // The editor also sends the same Basic credentials in X-AGFO-Editor-Auth; it is honoured
            // only for /agfo-ai/v1/editor/* and validated by WordPress' own Application Password code.
            add_filter( 'determine_current_user', [ __CLASS__, 'auth_from_header' ], 30 );
            add_filter( 'application_password_is_api_request', [ __CLASS__, 'is_api_request' ] );
        }

        /** Raw request path, including ?rest_route= form. */
        public static function is_editor_request(): bool {
            $uri   = isset( $_SERVER['REQUEST_URI'] ) ? rawurldecode( (string) wp_unslash( $_SERVER['REQUEST_URI'] ) ) : '';
            $route = isset( $_GET['rest_route'] ) ? rawurldecode( (string) wp_unslash( $_GET['rest_route'] ) ) : '';
            $needle = '/' . self::NAMESPACE_V1 . '/editor/';
            return strpos( $uri, $needle ) !== false || strpos( '/' . ltrim( $route, '/' ), $needle ) === 0;
        }

        public static function fallback_header(): string {
            $raw = isset( $_SERVER[ self::AUTH_HEADER ] ) ? trim( (string) wp_unslash( $_SERVER[ self::AUTH_HEADER ] ) ) : '';
            if ( stripos( $raw, 'Basic ' ) === 0 ) {
                $raw = trim( substr( $raw, 6 ) );
            }
            if ( $raw === '' || strlen( $raw ) > 2048 || ! preg_match( '#^[A-Za-z0-9+/=]+$#', $raw ) ) {
                return '';
            }
            return $raw;
        }

        /** True when any credential reached PHP (for diagnostics only; never echoes values). */
        public static function credentials_received(): bool {
            foreach ( [ 'PHP_AUTH_USER', 'HTTP_AUTHORIZATION', 'REDIRECT_HTTP_AUTHORIZATION', self::AUTH_HEADER ] as $k ) {
                if ( ! empty( $_SERVER[ $k ] ) ) {
                    return true;
                }
            }
            return false;
        }

        public static function is_api_request( $is_api ) {
            return ( self::$in_auth && self::is_editor_request() ) ? true : $is_api;
        }

        /**
         * determine_current_user filter (priority 30, after core's Application Password check at 20).
         *
         * @param int|false $user_id
         * @return int|false
         */
        public static function auth_from_header( $user_id ) {
            if ( ! empty( $user_id ) || ! self::is_editor_request() ) {
                return $user_id;
            }
            $raw = self::fallback_header();
            if ( $raw === '' || ! function_exists( 'wp_authenticate_application_password' ) ) {
                return $user_id;
            }
            $decoded = base64_decode( $raw, true );
            if ( ! is_string( $decoded ) || strpos( $decoded, ':' ) === false ) {
                return $user_id;
            }
            list( $login, $password ) = explode( ':', $decoded, 2 );
            if ( $login === '' || $password === '' ) {
                return $user_id;
            }
            self::$in_auth = true;
            try {
                $user = wp_authenticate_application_password( null, $login, $password );
            } finally {
                self::$in_auth = false;
            }
            if ( is_object( $user ) && ! is_wp_error( $user ) && ! empty( $user->ID ) ) {
                self::$auth_error = null;
                return (int) $user->ID;
            }
            if ( is_wp_error( $user ) ) {
                self::$auth_error = $user;
            }
            return $user_id;
        }

        public static function enabled(): bool {
            return (bool) apply_filters( 'agfo_ai_editor_api_enabled', true );
        }

        public static function register_routes(): void {
            if ( ! self::enabled() ) {
                return;
            }
            // NEW 17.5.0: unauthenticated connection check for the editor's diagnostics (booleans only).
            register_rest_route( self::NAMESPACE_V1, '/editor/ping', [
                'methods'             => 'GET',
                'callback'            => [ __CLASS__, 'rest_ping' ],
                'permission_callback' => '__return_true',
            ] );
            register_rest_route( self::NAMESPACE_V1, '/editor/info', [
                'methods'             => 'GET',
                'callback'            => [ __CLASS__, 'rest_info' ],
                'permission_callback' => [ __CLASS__, 'can_use' ],
            ] );
            register_rest_route( self::NAMESPACE_V1, '/editor/transform', [
                'methods'             => 'POST',
                'callback'            => [ __CLASS__, 'rest_transform' ],
                'permission_callback' => [ __CLASS__, 'can_use' ],
                'args'                => self::transform_args(),
            ] );
            register_rest_route( self::NAMESPACE_V1, '/editor/chat', [
                'methods'             => 'POST',
                'callback'            => [ __CLASS__, 'rest_chat' ],
                'permission_callback' => [ __CLASS__, 'can_use' ],
                'args'                => self::chat_args(),
            ] );
        }

        public static function required_capability(): string {
            if ( class_exists( 'AGFO_AIM_Content_Transformer' ) ) {
                return AGFO_AIM_Content_Transformer::required_capability();
            }
            return 'manage_options';
        }

        public static function rest_ping() {
            $app_pw = function_exists( 'wp_is_application_passwords_available' ) ? (bool) wp_is_application_passwords_available() : null;
            return new WP_REST_Response( [
                'plugin'          => 'agfo-ai-manager',
                'plugin_version'  => defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '',
                'api_version'     => self::API_VERSION,
                'token_auth'      => class_exists( 'AGFO_AIM_Editor_Tokens' ),
                'app_passwords'   => $app_pw,
                'https'           => function_exists( 'is_ssl' ) ? (bool) is_ssl() : null,
                'received'        => [
                    'authorization' => ! empty( $_SERVER['HTTP_AUTHORIZATION'] ) || ! empty( $_SERVER['PHP_AUTH_USER'] ) || ! empty( $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ),
                    'x_auth'        => ! empty( $_SERVER[ self::AUTH_HEADER ] ),
                    'token'         => class_exists( 'AGFO_AIM_Editor_Tokens' ) ? AGFO_AIM_Editor_Tokens::token_sent() : false,
                ],
            ], 200 );
        }

        /** @return bool|WP_Error */
        public static function can_use() {
            // NEW 17.5.0: editor connection key (X-AGFO-Editor-Token) — works even when the server drops
            // the Authorization header or a security plugin disables Application Passwords.
            if ( function_exists( 'is_user_logged_in' ) && ! is_user_logged_in() && class_exists( 'AGFO_AIM_Editor_Tokens' ) ) {
                if ( ! AGFO_AIM_Editor_Tokens::authenticate_request() && AGFO_AIM_Editor_Tokens::token_sent() ) {
                    return new WP_Error( 'agfo_editor_token_invalid', 'Bağlantı anahtarı geçersiz veya silinmiş. AI Manager › AI Editor bağlantısı sayfasından yeni anahtar oluşturun.', [ 'status' => 401, 'credentials_received' => true ] );
                }
            }
            if ( ! function_exists( 'is_user_logged_in' ) || ! is_user_logged_in() ) {
                if ( self::$auth_error instanceof WP_Error ) {
                    // WordPress' own reason: invalid_username, incorrect_password, application_passwords_disabled …
                    return new WP_Error( self::$auth_error->get_error_code(), self::$auth_error->get_error_message(), [ 'status' => 401, 'credentials_received' => true ] );
                }
                return new WP_Error( 'agfo_editor_auth', 'Giriş gerekli. Uygulama parolası (Application Password) ile bağlanın.', [
                    'status'               => 401,
                    'credentials_received' => self::credentials_received(),
                ] );
            }
            if ( ! current_user_can( self::required_capability() ) ) {
                return new WP_Error( 'agfo_editor_forbidden', 'Bu kullanıcının AI içerik yetkisi yok.', [ 'status' => 403 ] );
            }
            return true;
        }

        // ------------------------------------------------------------------ args

        public static function transform_args(): array {
            $text = function ( $max ) {
                return [
                    'type'              => 'string',
                    'required'          => false,
                    'sanitize_callback' => 'sanitize_text_field',
                    'validate_callback' => function ( $v ) use ( $max ) {
                        return is_string( $v ) && self::char_len( $v ) <= $max;
                    },
                ];
            };
            return [
                'source_html'    => [
                    'type'              => 'string',
                    'required'          => false,
                    'validate_callback' => [ __CLASS__, 'validate_source' ],
                ],
                'source_text'    => [
                    'type'              => 'string',
                    'required'          => false,
                    'validate_callback' => [ __CLASS__, 'validate_source' ],
                ],
                'template'       => [ 'type' => 'string', 'required' => false, 'default' => 'rewrite_balanced', 'sanitize_callback' => 'sanitize_key' ],
                'language'       => $text( 80 ),
                'tone'           => $text( 120 ),
                'audience'       => $text( 120 ),
                'length'         => $text( 200 ),
                'extra'          => [
                    'type'              => 'string',
                    'required'          => false,
                    'sanitize_callback' => 'sanitize_textarea_field',
                    'validate_callback' => function ( $v ) {
                        return is_string( $v ) && self::char_len( $v ) <= 4000;
                    },
                ],
                'from_scratch'   => [ 'type' => 'boolean', 'required' => false, 'default' => false ],
                'preserve_facts' => [ 'type' => 'boolean', 'required' => false, 'default' => true ],
            ];
        }

        public static function chat_args(): array {
            return [
                'messages'    => [
                    'type'              => 'array',
                    'required'          => true,
                    'validate_callback' => [ __CLASS__, 'validate_messages' ],
                ],
                'document'    => [
                    'type'              => 'string',
                    'required'          => false,
                    'default'           => '',
                    'validate_callback' => [ __CLASS__, 'validate_source' ],
                ],
                // NEW 17.6.0: longer answers for "create content from sources" (AI Editor 1.2+). Bounded.
                'max_output_tokens' => [
                    'type'              => 'integer',
                    'required'          => false,
                    'default'           => 2400,
                    'validate_callback' => function ( $v ) {
                        return is_numeric( $v ) && (int) $v >= 256 && (int) $v <= 8000;
                    },
                ],
                'instruction' => [
                    'type'              => 'string',
                    'required'          => false,
                    'default'           => '',
                    'sanitize_callback' => 'sanitize_textarea_field',
                    'validate_callback' => function ( $v ) {
                        return is_string( $v ) && self::char_len( $v ) <= 4000;
                    },
                ],
            ];
        }

        /** @return bool|WP_Error */
        public static function validate_source( $value ) {
            if ( ! is_string( $value ) ) {
                return new WP_Error( 'agfo_editor_type', 'Metin alanı dize olmalı.', [ 'status' => 400 ] );
            }
            if ( self::char_len( $value ) > self::MAX_CHARS ) {
                return new WP_Error( 'agfo_editor_too_long', 'Metin çok uzun. En fazla 60.000 karakter gönderin veya yalnız ilgili bölümü seçin.', [ 'status' => 413 ] );
            }
            return true;
        }

        /** @return bool|WP_Error */
        public static function validate_messages( $value ) {
            if ( ! is_array( $value ) || empty( $value ) ) {
                return new WP_Error( 'agfo_editor_messages', 'messages boş olamaz.', [ 'status' => 400 ] );
            }
            if ( count( $value ) > self::MAX_MESSAGES ) {
                return new WP_Error( 'agfo_editor_messages', 'En fazla 40 mesaj gönderilebilir.', [ 'status' => 400 ] );
            }
            foreach ( $value as $m ) {
                if ( ! is_array( $m ) || ! isset( $m['content'] ) || ! is_string( $m['content'] ) ) {
                    return new WP_Error( 'agfo_editor_messages', 'Her mesaj {role, content} olmalı.', [ 'status' => 400 ] );
                }
                $role = (string) ( $m['role'] ?? 'user' );
                if ( ! in_array( $role, [ 'user', 'assistant' ], true ) ) {
                    return new WP_Error( 'agfo_editor_messages', 'Mesaj rolü user veya assistant olmalı.', [ 'status' => 400 ] );
                }
                if ( self::char_len( $m['content'] ) > self::MAX_MSG_CHARS ) {
                    return new WP_Error( 'agfo_editor_too_long', 'Bir mesaj en fazla 20.000 karakter olabilir.', [ 'status' => 413 ] );
                }
            }
            return true;
        }

        // ------------------------------------------------------------------ callbacks

        public static function rest_info( $request ) {
            $user  = function_exists( 'wp_get_current_user' ) ? wp_get_current_user() : null;
            $text  = function_exists( 'agfo_get_priority_api_key' ) ? agfo_get_priority_api_key() : false;
            $trans = class_exists( 'AGFO_AIM_Content_Transformer' ) ? AGFO_AIM_Content_Transformer::translation_config() : false;
            $data  = [
                'plugin'            => 'agfo-ai-manager',
                'plugin_version'    => defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '',
                'api_version'       => self::API_VERSION,
                'user'              => ( $user && isset( $user->display_name ) ) ? (string) $user->display_name : '',
                'templates'         => class_exists( 'AGFO_AIM_Content_Prompt_Library' ) ? AGFO_AIM_Content_Prompt_Library::public_catalog() : [],
                'text_ready'        => self::config_ready( $text ),
                'text_provider'     => self::config_name( $text ),
                'text_model'        => self::config_model( $text ),
                'translation_ready' => self::config_ready( $trans ),
                'translation_provider' => self::config_name( $trans ),
                'translation_model' => self::config_model( $trans ),
                'max_chars'         => self::MAX_CHARS,
                'features'          => [ 'transform', 'chat', 'translate' ],
            ];
            return self::response( $data, 200 );
        }

        public static function rest_transform( $request ) {
            $html = (string) ( $request->get_param( 'source_html' ) ?? '' );
            $text = (string) ( $request->get_param( 'source_text' ) ?? '' );
            if ( trim( $html ) === '' && trim( $text ) !== '' ) {
                $html = self::text_to_html( $text );
            }
            if ( trim( wp_strip_all_tags( $html ) ) === '' ) {
                return new WP_Error( 'agfo_content_empty', 'Dönüştürülecek içerik boş.', [ 'status' => 400 ] );
            }
            $options = self::transform_options( $request );
            $result  = AGFO_AIM_Content_Transformer::transform( $html, $options );
            if ( is_wp_error( $result ) ) {
                return self::rest_error( $result );
            }
            return self::response( $result, 200 );
        }

        public static function rest_chat( $request ) {
            $messages = (array) $request->get_param( 'messages' );
            $document = (string) ( $request->get_param( 'document' ) ?? '' );
            $max      = (int) ( $request->get_param( 'max_output_tokens' ) ?? 2400 );
            $result   = AGFO_AIM_Content_Transformer::chat( $messages, $document, [
                'instruction'       => (string) ( $request->get_param( 'instruction' ) ?? '' ),
                'max_output_tokens' => max( 256, min( 8000, $max ?: 2400 ) ),
            ] );
            if ( is_wp_error( $result ) ) {
                return self::rest_error( $result );
            }
            return self::response( $result, 200 );
        }

        // ------------------------------------------------------------------ helpers

        public static function transform_options( $request ): array {
            $get = function ( $k, $d ) use ( $request ) {
                $v = $request->get_param( $k );
                return ( $v === null || $v === '' ) ? $d : $v;
            };
            return [
                'template'       => sanitize_key( (string) $get( 'template', 'rewrite_balanced' ) ),
                'language'       => sanitize_text_field( (string) $get( 'language', 'Türkçe' ) ),
                'tone'           => sanitize_text_field( (string) $get( 'tone', 'Doğal ve dengeli' ) ),
                'audience'       => sanitize_text_field( (string) $get( 'audience', 'Genel okuyucu' ) ),
                'length'         => sanitize_text_field( (string) $get( 'length', 'Benzer uzunluk' ) ),
                'extra'          => sanitize_textarea_field( (string) $get( 'extra', '' ) ),
                'from_scratch'   => self::truthy( $request->get_param( 'from_scratch' ), false ),
                'preserve_facts' => self::truthy( $request->get_param( 'preserve_facts' ), true ),
                'post_id'        => 0,
                'current_title'  => '',
            ];
        }

        /** Plain text → safe HTML paragraphs (blank line = new paragraph, single newline = <br />). */
        public static function text_to_html( string $text ): string {
            $text  = str_replace( [ "\r\n", "\r" ], "\n", $text );
            $parts = preg_split( '/\n\s*\n/u', $text );
            $html  = '';
            foreach ( (array) $parts as $p ) {
                $p = trim( (string) $p );
                if ( $p === '' ) {
                    continue;
                }
                $html .= '<p>' . str_replace( "\n", '<br />', esc_html( $p ) ) . '</p>';
            }
            return $html;
        }

        private static function truthy( $v, bool $default ): bool {
            if ( $v === null || $v === '' ) {
                return $default;
            }
            if ( is_bool( $v ) ) {
                return $v;
            }
            return in_array( strtolower( (string) $v ), [ '1', 'true', 'yes', 'on' ], true );
        }

        private static function config_ready( $c ): bool {
            return is_array( $c ) && ! empty( $c['key'] ) && ! empty( $c['model'] ) && ! empty( $c['chat_url'] );
        }

        private static function config_name( $c ): string {
            if ( ! self::config_ready( $c ) ) {
                return '';
            }
            return sanitize_text_field( (string) ( $c['provider_name'] ?? $c['code'] ?? '' ) );
        }

        private static function config_model( $c ): string {
            return self::config_ready( $c ) ? sanitize_text_field( (string) $c['model'] ) : '';
        }

        private static function char_len( string $s ): int {
            return function_exists( 'mb_strlen' ) ? (int) mb_strlen( $s, 'UTF-8' ) : strlen( $s );
        }

        private static function rest_error( $error ) {
            $code   = (string) $error->get_error_code();
            $status = in_array( $code, [ 'agfo_content_empty', 'agfo_chat_empty', 'agfo_structured_empty' ], true ) ? 400
                : ( 'agfo_content_config' === $code ? 503 : 502 );
            return new WP_Error( $code, $error->get_error_message(), [ 'status' => $status ] );
        }

        private static function response( array $data, int $status ) {
            if ( class_exists( 'WP_REST_Response' ) ) {
                return new WP_REST_Response( $data, $status );
            }
            return $data;
        }
    }
}
