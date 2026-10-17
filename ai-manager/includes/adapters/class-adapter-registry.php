<?php
/**
 * Adapter registry.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Adapter_Registry' ) ) {
    final class AGFO_AIM_Adapter_Registry {
        /** @var array<string,AGFO_AIM_Adapter_Interface> */
        private static $instances = [];

        public static function register( AGFO_AIM_Adapter_Interface $adapter ): void {
            self::$instances[ sanitize_key( $adapter->provider_code() ) ] = $adapter;
        }

        public static function boot_defaults(): void {
            if ( class_exists( 'AGFO_AIM_Adapter_OpenAI' ) ) {
                self::register( new AGFO_AIM_Adapter_OpenAI() );
            }
            if ( class_exists( 'AGFO_AIM_Adapter_ElevenLabs' ) ) {
                self::register( new AGFO_AIM_Adapter_ElevenLabs() );
            }
            if ( class_exists( 'AGFO_AIM_Adapter_MiniMax' ) ) {
                self::register( new AGFO_AIM_Adapter_MiniMax() );
            }
            if ( class_exists( 'AGFO_AIM_Adapter_Gemini' ) ) {
                self::register( new AGFO_AIM_Adapter_Gemini() );
            }
            do_action( 'agfo_ai_register_adapters', __CLASS__ );
        }

        /**
         * @return AGFO_AIM_Adapter_Interface|WP_Error
         */
        public static function get( string $provider ) {
            $provider = sanitize_key( $provider );
            if ( isset( self::$instances[ $provider ] ) ) {
                return self::$instances[ $provider ];
            }
            return new WP_Error( 'agfo_adapter_missing', 'Sağlayıcı adaptörü bulunamadı: ' . $provider );
        }

        public static function supports( string $provider, string $capability ): bool {
            $adapter = self::get( $provider );
            return ! is_wp_error( $adapter ) && $adapter->supports( $capability );
        }

        /**
         * @return array<string,AGFO_AIM_Adapter_Interface>
         */
        public static function all(): array {
            return self::$instances;
        }
    }
}
