<?php
/**
 * AGFO AI Manager database schema.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Schema' ) ) {
    final class AGFO_AIM_Schema {
        const VERSION = '1.0.0';
        const OPTION  = 'agfo_ai_schema_version';

        public static function jobs_table(): string {
            global $wpdb;
            return $wpdb->prefix . 'agfo_ai_jobs';
        }

        public static function assets_table(): string {
            global $wpdb;
            return $wpdb->prefix . 'agfo_ai_assets';
        }

        public static function usage_table(): string {
            global $wpdb;
            return $wpdb->prefix . 'agfo_ai_usage';
        }

        public static function install() {
            global $wpdb;

            if ( ! function_exists( 'dbDelta' ) ) {
                require_once ABSPATH . 'wp-admin/includes/upgrade.php';
            }

            $charset_collate = $wpdb->get_charset_collate();
            $jobs            = self::jobs_table();
            $assets          = self::assets_table();
            $usage           = self::usage_table();

            $sql_jobs = "CREATE TABLE {$jobs} (
                id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
                job_uuid char(36) NOT NULL,
                capability varchar(64) NOT NULL,
                provider varchar(64) NOT NULL DEFAULT '',
                model varchar(191) NOT NULL DEFAULT '',
                route_json longtext NULL,
                status varchar(32) NOT NULL DEFAULT 'draft',
                request_json longtext NOT NULL,
                provider_ref varchar(191) NOT NULL DEFAULT '',
                attempts smallint(5) unsigned NOT NULL DEFAULT 0,
                max_attempts smallint(5) unsigned NOT NULL DEFAULT 3,
                next_run_at datetime NULL,
                lease_token varchar(64) NOT NULL DEFAULT '',
                lease_until datetime NULL,
                cost_estimate decimal(18,8) NOT NULL DEFAULT 0,
                cost_reserved decimal(18,8) NOT NULL DEFAULT 0,
                cost_actual decimal(18,8) NOT NULL DEFAULT 0,
                currency char(3) NOT NULL DEFAULT 'USD',
                pricing_snapshot longtext NULL,
                source_plugin varchar(191) NOT NULL DEFAULT '',
                idempotency_key varchar(191) NULL,
                created_by bigint(20) unsigned NOT NULL DEFAULT 0,
                created_at datetime NOT NULL,
                updated_at datetime NOT NULL,
                started_at datetime NULL,
                completed_at datetime NULL,
                cancelled_at datetime NULL,
                error_code varchar(100) NOT NULL DEFAULT '',
                error_message text NULL,
                result_json longtext NULL,
                PRIMARY KEY  (id),
                UNIQUE KEY job_uuid (job_uuid),
                UNIQUE KEY idempotency_key (idempotency_key),
                KEY status_next_run (status,next_run_at),
                KEY provider_status (provider,status),
                KEY created_by (created_by),
                KEY capability (capability)
            ) {$charset_collate};";

            $sql_assets = "CREATE TABLE {$assets} (
                id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
                asset_uuid char(36) NOT NULL,
                job_id bigint(20) unsigned NOT NULL,
                kind varchar(32) NOT NULL DEFAULT 'audio',
                storage_path text NOT NULL,
                original_name varchar(191) NOT NULL DEFAULT '',
                mime varchar(100) NOT NULL DEFAULT 'application/octet-stream',
                bytes bigint(20) unsigned NOT NULL DEFAULT 0,
                width int(10) unsigned NULL,
                height int(10) unsigned NULL,
                duration_seconds decimal(14,4) NULL,
                sha256 char(64) NOT NULL,
                attachment_id bigint(20) unsigned NULL,
                visibility varchar(20) NOT NULL DEFAULT 'private',
                provenance_json longtext NOT NULL,
                retention_until datetime NULL,
                created_by bigint(20) unsigned NOT NULL DEFAULT 0,
                created_at datetime NOT NULL,
                PRIMARY KEY  (id),
                UNIQUE KEY asset_uuid (asset_uuid),
                KEY job_id (job_id),
                KEY retention_until (retention_until),
                KEY attachment_id (attachment_id),
                KEY created_by (created_by)
            ) {$charset_collate};";

            $sql_usage = "CREATE TABLE {$usage} (
                id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
                usage_date date NOT NULL,
                provider varchar(64) NOT NULL,
                model varchar(191) NOT NULL DEFAULT '',
                capability varchar(64) NOT NULL,
                source_plugin varchar(191) NOT NULL DEFAULT '',
                calls bigint(20) unsigned NOT NULL DEFAULT 0,
                input_units decimal(20,6) NOT NULL DEFAULT 0,
                output_units decimal(20,6) NOT NULL DEFAULT 0,
                unit_name varchar(32) NOT NULL DEFAULT 'call',
                cost_estimate decimal(18,8) NOT NULL DEFAULT 0,
                cost_actual decimal(18,8) NOT NULL DEFAULT 0,
                currency char(3) NOT NULL DEFAULT 'USD',
                updated_at datetime NOT NULL,
                PRIMARY KEY  (id),
                UNIQUE KEY usage_rollup (usage_date,provider,model(100),capability,source_plugin(100),unit_name),
                KEY provider_date (provider,usage_date),
                KEY capability_date (capability,usage_date)
            ) {$charset_collate};";

            dbDelta( $sql_jobs );
            dbDelta( $sql_assets );
            dbDelta( $sql_usage );

            $missing = [];
            foreach ( [ $jobs, $assets, $usage ] as $table ) {
                $found = $wpdb->get_var( $wpdb->prepare( 'SHOW TABLES LIKE %s', $wpdb->esc_like( $table ) ) );
                if ( $found !== $table ) {
                    $missing[] = $table;
                }
            }
            if ( $missing ) {
                return new WP_Error( 'agfo_schema_install', 'AGFO AI tabloları oluşturulamadı: ' . implode( ', ', $missing ) );
            }

            update_option( self::OPTION, self::VERSION, false );
            return true;
        }

        public static function is_current(): bool {
            return self::VERSION === (string) get_option( self::OPTION, '' );
        }
    }
}
