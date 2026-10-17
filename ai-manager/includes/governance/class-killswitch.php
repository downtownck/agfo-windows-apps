<?php
/**
 * Capability kill switches.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Kill_Switch' ) ) {
    final class AGFO_AIM_Kill_Switch {
        const OPTION = 'agfo_ai_kill_switches';

        public static function is_enabled( string $capability ): bool {
            $switches = get_option( self::OPTION, [] );
            if ( ! is_array( $switches ) ) {
                return true;
            }
            return empty( $switches[ sanitize_key( $capability ) ] );
        }

        public static function set_disabled( string $capability, bool $disabled, int $user_id = 0 ): void {
            $capability = sanitize_key( $capability );
            $switches   = get_option( self::OPTION, [] );
            if ( ! is_array( $switches ) ) {
                $switches = [];
            }

            if ( $disabled ) {
                $switches[ $capability ] = [
                    'disabled' => true,
                    'user_id'  => $user_id,
                    'time'     => current_time( 'mysql' ),
                ];
            } else {
                unset( $switches[ $capability ] );
            }
            update_option( self::OPTION, $switches, false );
        }

        public static function all(): array {
            $switches = get_option( self::OPTION, [] );
            return is_array( $switches ) ? $switches : [];
        }
    }
}
