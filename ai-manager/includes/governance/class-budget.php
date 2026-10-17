<?php
/**
 * Budget reservation and settlement.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Budget' ) ) {
    final class AGFO_AIM_Budget {
        const OPTION = 'agfo_ai_budget_limits';

        public static function limits(): array {
            $defaults = [
                'global_monthly' => 0.0,
                'providers'      => [],
                'capabilities'   => [],
                'plugins'        => [],
                'warning_ratio'  => 0.8,
            ];
            $saved = get_option( self::OPTION, [] );
            return wp_parse_args( is_array( $saved ) ? $saved : [], $defaults );
        }

        /**
         * Reserve estimated cost on an existing draft job.
         *
         * @return true|WP_Error
         */
        public static function reserve( int $job_id, array $context ) {
            global $wpdb;

            $estimate = max( 0.0, (float) ( $context['cost_estimate'] ?? 0 ) );
            if ( 0.0 === $estimate ) {
                return true;
            }

            $lock_name = 'agfo_ai_budget_' . md5( home_url( '/' ) );
            $locked    = (int) $wpdb->get_var( $wpdb->prepare( 'SELECT GET_LOCK(%s, 5)', $lock_name ) );
            if ( 1 !== $locked ) {
                return new WP_Error( 'agfo_budget_lock', 'Bütçe rezervasyon kilidi alınamadı. Lütfen tekrar deneyin.' );
            }

            try {
                $limits = self::limits();
                $checks = [
                    [ 'limit' => (float) $limits['global_monthly'], 'filters' => [], 'label' => 'Genel aylık bütçe' ],
                ];

                $provider = sanitize_key( (string) ( $context['provider'] ?? '' ) );
                $cap      = sanitize_key( (string) ( $context['capability'] ?? '' ) );
                $plugin   = sanitize_key( (string) ( $context['source_plugin'] ?? '' ) );

                if ( isset( $limits['providers'][ $provider ] ) ) {
                    $checks[] = [ 'limit' => (float) $limits['providers'][ $provider ], 'filters' => [ 'provider' => $provider ], 'label' => 'Sağlayıcı aylık bütçesi' ];
                }
                if ( isset( $limits['capabilities'][ $cap ] ) ) {
                    $checks[] = [ 'limit' => (float) $limits['capabilities'][ $cap ], 'filters' => [ 'capability' => $cap ], 'label' => 'Yetenek aylık bütçesi' ];
                }
                if ( '' !== $plugin && isset( $limits['plugins'][ $plugin ] ) ) {
                    $checks[] = [ 'limit' => (float) $limits['plugins'][ $plugin ], 'filters' => [ 'source_plugin' => $plugin ], 'label' => 'Kaynak plugin aylık bütçesi' ];
                }

                foreach ( $checks as $check ) {
                    if ( $check['limit'] <= 0 ) {
                        continue;
                    }
                    $spent    = class_exists( 'AGFO_AIM_Usage' ) ? AGFO_AIM_Usage::month_spend( $check['filters'] ) : 0.0;
                    $reserved = self::active_reservations( $check['filters'], $job_id );
                    if ( ( $spent + $reserved + $estimate ) > $check['limit'] ) {
                        return new WP_Error(
                            'agfo_budget_exceeded',
                            sprintf( '%s aşılıyor. Limit: $%.4f, kullanılan+rezervasyon: $%.4f, yeni tahmin: $%.4f.', $check['label'], $check['limit'], $spent + $reserved, $estimate )
                        );
                    }
                    $projected     = $spent + $reserved + $estimate;
                    $warning_ratio = max( 0.1, min( 1.0, (float) ( $limits['warning_ratio'] ?? 0.8 ) ) );
                    if ( $projected >= ( $check['limit'] * $warning_ratio ) ) {
                        $warning = [
                            'label'       => $check['label'],
                            'limit'       => $check['limit'],
                            'projected'   => $projected,
                            'ratio'       => $projected / $check['limit'],
                            'provider'    => $provider,
                            'capability'  => $cap,
                            'source_plugin'=> $plugin,
                            'job_id'      => $job_id,
                            'time'        => current_time( 'mysql' ),
                        ];
                        update_option( 'agfo_ai_budget_warning', $warning, false );
                        do_action( 'agfo_ai_budget_warning', $warning );
                    }
                }

                $table = AGFO_AIM_Schema::jobs_table();
                $ok    = $wpdb->update(
                    $table,
                    [ 'cost_reserved' => $estimate, 'updated_at' => current_time( 'mysql' ) ],
                    [ 'id' => $job_id, 'status' => 'draft' ],
                    [ '%f', '%s' ],
                    [ '%d', '%s' ]
                );
                if ( false === $ok ) {
                    return new WP_Error( 'agfo_budget_reserve_write', 'Maliyet rezervasyonu kaydedilemedi.' );
                }
                return true;
            } finally {
                $wpdb->query( $wpdb->prepare( 'SELECT RELEASE_LOCK(%s)', $lock_name ) );
            }
        }

        public static function settle( int $job_id, ?float $actual_cost = null ): void {
            global $wpdb;
            if ( ! class_exists( 'AGFO_AIM_Schema' ) ) {
                return;
            }
            $table = AGFO_AIM_Schema::jobs_table();
            $data  = [
                'cost_reserved' => 0,
                'updated_at'    => current_time( 'mysql' ),
            ];
            $formats = [ '%f', '%s' ];
            if ( null !== $actual_cost ) {
                $data['cost_actual'] = max( 0, $actual_cost );
                $formats[]           = '%f';
            }
            $wpdb->update( $table, $data, [ 'id' => $job_id ], $formats, [ '%d' ] );
        }

        private static function active_reservations( array $filters, int $exclude_job_id ): float {
            global $wpdb;
            $table = AGFO_AIM_Schema::jobs_table();
            $where = [ 'id <> %d', "status IN ('queued','processing','retry','storing')", 'cost_reserved > 0' ];
            $args  = [ $exclude_job_id ];

            foreach ( [ 'provider', 'capability', 'source_plugin' ] as $field ) {
                if ( ! empty( $filters[ $field ] ) ) {
                    $where[] = "{$field} = %s";
                    $args[]  = sanitize_key( (string) $filters[ $field ] );
                }
            }
            $sql = 'SELECT SUM(cost_reserved) FROM ' . $table . ' WHERE ' . implode( ' AND ', $where );
            $sum = $wpdb->get_var( $wpdb->prepare( $sql, $args ) );
            return $sum ? (float) $sum : 0.0;
        }
    }
}
