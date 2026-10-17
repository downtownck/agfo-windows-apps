<?php
/**
 * Daily usage rollups.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Usage' ) ) {
    final class AGFO_AIM_Usage {
        public static function record( array $event ): bool {
            global $wpdb;

            if ( ! class_exists( 'AGFO_AIM_Schema' ) ) {
                return false;
            }

            $table         = AGFO_AIM_Schema::usage_table();
            $usage_date    = isset( $event['usage_date'] ) ? sanitize_text_field( (string) $event['usage_date'] ) : current_time( 'Y-m-d' );
            $provider      = sanitize_key( (string) ( $event['provider'] ?? '' ) );
            $model         = sanitize_text_field( (string) ( $event['model'] ?? '' ) );
            $capability    = sanitize_key( (string) ( $event['capability'] ?? '' ) );
            $source_plugin = sanitize_key( (string) ( $event['source_plugin'] ?? '' ) );
            $unit_name     = sanitize_key( (string) ( $event['unit_name'] ?? 'call' ) );
            $now           = current_time( 'mysql' );

            if ( '' === $provider || '' === $capability ) {
                return false;
            }

            $sql = $wpdb->prepare(
                "INSERT INTO {$table}
                (usage_date, provider, model, capability, source_plugin, calls, input_units, output_units, unit_name, cost_estimate, cost_actual, currency, updated_at)
                VALUES (%s, %s, %s, %s, %s, 1, %f, %f, %s, %f, %f, %s, %s)
                ON DUPLICATE KEY UPDATE
                    calls = calls + 1,
                    input_units = input_units + VALUES(input_units),
                    output_units = output_units + VALUES(output_units),
                    cost_estimate = cost_estimate + VALUES(cost_estimate),
                    cost_actual = cost_actual + VALUES(cost_actual),
                    updated_at = VALUES(updated_at)",
                $usage_date,
                $provider,
                $model,
                $capability,
                $source_plugin,
                (float) ( $event['input_units'] ?? 0 ),
                (float) ( $event['output_units'] ?? 0 ),
                $unit_name,
                (float) ( $event['cost_estimate'] ?? 0 ),
                (float) ( $event['cost_actual'] ?? 0 ),
                strtoupper( sanitize_text_field( (string) ( $event['currency'] ?? 'USD' ) ) ),
                $now
            );

            return false !== $wpdb->query( $sql );
        }

        public static function month_spend( array $filters = [] ): float {
            global $wpdb;

            if ( ! class_exists( 'AGFO_AIM_Schema' ) ) {
                return 0.0;
            }

            $table = AGFO_AIM_Schema::usage_table();
            $start = wp_date( 'Y-m-01 00:00:00', time() );
            $end   = wp_date( 'Y-m-t 23:59:59', time() );
            $where = [ 'usage_date >= %s', 'usage_date <= %s' ];
            $args  = [ substr( $start, 0, 10 ), substr( $end, 0, 10 ) ];

            foreach ( [ 'provider', 'capability', 'source_plugin' ] as $field ) {
                if ( ! empty( $filters[ $field ] ) ) {
                    $where[] = "{$field} = %s";
                    $args[]  = sanitize_key( (string) $filters[ $field ] );
                }
            }

            $sql = "SELECT SUM(CASE WHEN cost_actual > 0 THEN cost_actual ELSE cost_estimate END) FROM {$table} WHERE " . implode( ' AND ', $where );
            $sum = $wpdb->get_var( $wpdb->prepare( $sql, $args ) );
            return $sum ? (float) $sum : 0.0;
        }

        public static function sum_input_units( array $filters, string $start_date, string $end_date ): float {
            global $wpdb;

            if ( ! class_exists( 'AGFO_AIM_Schema' ) ) {
                return 0.0;
            }

            $table = AGFO_AIM_Schema::usage_table();
            $where = [ 'usage_date >= %s', 'usage_date <= %s' ];
            $args  = [ sanitize_text_field( $start_date ), sanitize_text_field( $end_date ) ];

            foreach ( [ 'provider', 'capability', 'source_plugin', 'unit_name' ] as $field ) {
                if ( ! empty( $filters[ $field ] ) ) {
                    $where[] = "{$field} = %s";
                    $args[]  = 'unit_name' === $field
                        ? sanitize_key( (string) $filters[ $field ] )
                        : sanitize_key( (string) $filters[ $field ] );
                }
            }

            $sql = 'SELECT SUM(input_units) FROM ' . $table . ' WHERE ' . implode( ' AND ', $where );
            $sum = $wpdb->get_var( $wpdb->prepare( $sql, $args ) );
            return $sum ? (float) $sum : 0.0;
        }

        public static function recent_summary( int $days = 30 ): array {
            global $wpdb;

            if ( ! class_exists( 'AGFO_AIM_Schema' ) ) {
                return [];
            }
            $days  = max( 1, min( 365, $days ) );
            $table = AGFO_AIM_Schema::usage_table();
            $from  = wp_date( 'Y-m-d', time() - ( $days - 1 ) * DAY_IN_SECONDS );

            $sql = $wpdb->prepare(
                "SELECT provider, capability, source_plugin, SUM(calls) AS calls,
                    SUM(input_units) AS input_units,
                    SUM(CASE WHEN cost_actual > 0 THEN cost_actual ELSE cost_estimate END) AS cost
                 FROM {$table}
                 WHERE usage_date >= %s
                 GROUP BY provider, capability, source_plugin
                 ORDER BY cost DESC, calls DESC",
                $from
            );
            $rows = $wpdb->get_results( $sql, ARRAY_A );
            return is_array( $rows ) ? $rows : [];
        }
    }
}
