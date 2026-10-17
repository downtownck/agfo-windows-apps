<?php
/**
 * AGFO AI Manager installer and upgrade runner.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Installer' ) ) {
    final class AGFO_AIM_Installer {
        const UPGRADE_OPTION = 'agfo_ai_manager_installed_version';
        const CRON_HOOK      = 'agfo_ai_run_jobs';
        const CLEANUP_HOOK   = 'agfo_ai_cleanup_assets';

        public static function activate(): void {
            if ( class_exists( 'AGFO_AIM_Schema' ) ) {
                $schema = AGFO_AIM_Schema::install();
                if ( is_wp_error( $schema ) ) {
                    update_option( 'agfo_ai_schema_error', sanitize_text_field( $schema->get_error_message() ), false );
                } else {
                    delete_option( 'agfo_ai_schema_error' );
                }
            }

            if ( class_exists( 'AGFO_AIM_Asset_Store' ) ) {
                $storage = AGFO_AIM_Asset_Store::ensure_storage_root();
                if ( is_wp_error( $storage ) ) {
                    update_option( 'agfo_ai_storage_error', sanitize_text_field( $storage->get_error_message() ), false );
                } else {
                    delete_option( 'agfo_ai_storage_error' );
                }
            }

            self::schedule_events();
            update_option( self::UPGRADE_OPTION, defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '', false );
        }

        public static function deactivate(): void {
            wp_clear_scheduled_hook( self::CRON_HOOK );
            wp_clear_scheduled_hook( self::CLEANUP_HOOK );
        }

        public static function maybe_upgrade(): void {
            $installed = (string) get_option( self::UPGRADE_OPTION, '' );
            $current   = defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '';

            if ( ! class_exists( 'AGFO_AIM_Schema' ) || ! AGFO_AIM_Schema::is_current() || $installed !== $current ) {
                self::activate();
            }
        }

        public static function schedule_events(): void {
            if ( ! wp_next_scheduled( self::CRON_HOOK ) ) {
                wp_schedule_event( time() + 60, 'agfo_ai_minute', self::CRON_HOOK );
            }
            if ( ! wp_next_scheduled( self::CLEANUP_HOOK ) ) {
                wp_schedule_event( time() + HOUR_IN_SECONDS, 'daily', self::CLEANUP_HOOK );
            }
        }

        public static function add_cron_schedules( array $schedules ): array {
            if ( ! isset( $schedules['agfo_ai_minute'] ) ) {
                $schedules['agfo_ai_minute'] = [
                    'interval' => MINUTE_IN_SECONDS,
                    'display'  => 'AGFO AI every minute',
                ];
            }
            return $schedules;
        }
    }
}
