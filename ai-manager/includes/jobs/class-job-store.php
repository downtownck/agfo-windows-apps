<?php
/**
 * Database-backed AI job store.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Job_Store' ) ) {
    final class AGFO_AIM_Job_Store {
        public static function create_draft( string $capability, array $payload, array $args = [] ) {
            global $wpdb;

            if ( ! class_exists( 'AGFO_AIM_Schema' ) ) {
                return new WP_Error( 'agfo_schema_missing', 'AGFO AI veri tabanı şeması yüklenmedi.' );
            }

            $uuid            = wp_generate_uuid4();
            $provider        = sanitize_key( (string) ( $args['provider'] ?? '' ) );
            $model           = sanitize_text_field( (string) ( $args['model'] ?? '' ) );
            $source_plugin   = sanitize_key( (string) ( $args['source_plugin'] ?? 'agfo-ai-manager' ) );
            $idempotency_key = isset( $args['idempotency_key'] ) && '' !== (string) $args['idempotency_key']
                ? hash( 'sha256', (string) $args['idempotency_key'] )
                : null;
            $now             = current_time( 'mysql' );
            $table           = AGFO_AIM_Schema::jobs_table();

            if ( $idempotency_key ) {
                $existing = $wpdb->get_row(
                    $wpdb->prepare( "SELECT * FROM {$table} WHERE idempotency_key = %s LIMIT 1", $idempotency_key ),
                    ARRAY_A
                );
                if ( is_array( $existing ) ) {
                    return $existing;
                }
            }

            $insert = [
                'job_uuid'         => $uuid,
                'capability'       => sanitize_key( $capability ),
                'provider'         => $provider,
                'model'            => $model,
                'route_json'       => wp_json_encode( $args['routes'] ?? [], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ),
                'status'           => 'draft',
                'request_json'     => wp_json_encode( $payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ),
                'attempts'         => 0,
                'max_attempts'     => max( 1, min( 10, absint( $args['max_attempts'] ?? 3 ) ) ),
                'cost_estimate'    => max( 0, (float) ( $args['cost_estimate'] ?? 0 ) ),
                'currency'         => strtoupper( sanitize_text_field( (string) ( $args['currency'] ?? 'USD' ) ) ),
                'pricing_snapshot' => wp_json_encode( $args['pricing_snapshot'] ?? [], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ),
                'source_plugin'    => $source_plugin,
                'created_by'       => absint( $args['created_by'] ?? get_current_user_id() ),
                'created_at'       => $now,
                'updated_at'       => $now,
            ];

            $formats = [ '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%d', '%d', '%f', '%s', '%s', '%s', '%d', '%s', '%s' ];
            if ( $idempotency_key ) {
                $insert['idempotency_key'] = $idempotency_key;
                $formats[]                 = '%s';
            }
            $ok = $wpdb->insert( $table, $insert, $formats );
            if ( false === $ok ) {
                return new WP_Error( 'agfo_job_insert', 'AI işi veri tabanına yazılamadı: ' . $wpdb->last_error );
            }

            return self::get_by_id( (int) $wpdb->insert_id );
        }

        public static function queue( int $job_id ): bool {
            global $wpdb;
            $table = AGFO_AIM_Schema::jobs_table();
            $now   = current_time( 'mysql' );
            return false !== $wpdb->update(
                $table,
                [ 'status' => 'queued', 'next_run_at' => $now, 'updated_at' => $now ],
                [ 'id' => $job_id, 'status' => 'draft' ],
                [ '%s', '%s', '%s' ],
                [ '%d', '%s' ]
            );
        }

        public static function delete_draft( int $job_id ): void {
            global $wpdb;
            $wpdb->delete( AGFO_AIM_Schema::jobs_table(), [ 'id' => $job_id, 'status' => 'draft' ], [ '%d', '%s' ] );
        }

        public static function get( string $job_uuid ): ?array {
            global $wpdb;
            $table = AGFO_AIM_Schema::jobs_table();
            $row   = $wpdb->get_row( $wpdb->prepare( "SELECT * FROM {$table} WHERE job_uuid = %s", sanitize_text_field( $job_uuid ) ), ARRAY_A );
            return is_array( $row ) ? self::hydrate( $row ) : null;
        }

        public static function get_by_id( int $id ): ?array {
            global $wpdb;
            $table = AGFO_AIM_Schema::jobs_table();
            $row   = $wpdb->get_row( $wpdb->prepare( "SELECT * FROM {$table} WHERE id = %d", $id ), ARRAY_A );
            return is_array( $row ) ? self::hydrate( $row ) : null;
        }

        public static function list_jobs( array $args = [] ): array {
            global $wpdb;
            $table = AGFO_AIM_Schema::jobs_table();
            $limit = max( 1, min( 200, absint( $args['limit'] ?? 50 ) ) );
            $where = [ '1=1' ];
            $bind  = [];

            if ( ! empty( $args['status'] ) ) {
                $where[] = 'status = %s';
                $bind[]  = sanitize_key( (string) $args['status'] );
            }
            if ( ! empty( $args['capability'] ) ) {
                $where[] = 'capability = %s';
                $bind[]  = sanitize_key( (string) $args['capability'] );
            }
            if ( ! empty( $args['created_by'] ) ) {
                $where[] = 'created_by = %d';
                $bind[]  = absint( $args['created_by'] );
            }

            $sql = "SELECT * FROM {$table} WHERE " . implode( ' AND ', $where ) . " ORDER BY id DESC LIMIT {$limit}";
            if ( $bind ) {
                $sql = $wpdb->prepare( $sql, $bind );
            }
            $rows = $wpdb->get_results( $sql, ARRAY_A );
            return array_map( [ __CLASS__, 'hydrate' ], is_array( $rows ) ? $rows : [] );
        }

        public static function claim_next(): ?array {
            global $wpdb;
            $table = AGFO_AIM_Schema::jobs_table();
            $now   = current_time( 'mysql' );
            $row   = $wpdb->get_row(
                $wpdb->prepare(
                    "SELECT id FROM {$table}
                     WHERE status IN ('queued','retry')
                       AND (next_run_at IS NULL OR next_run_at <= %s)
                       AND (lease_until IS NULL OR lease_until < %s)
                     ORDER BY id ASC LIMIT 1",
                    $now,
                    $now
                ),
                ARRAY_A
            );
            if ( ! is_array( $row ) ) {
                return null;
            }

            $token       = wp_generate_password( 32, false, false );
            $lease_until = wp_date( 'Y-m-d H:i:s', time() + 180 );
            $updated     = $wpdb->query(
                $wpdb->prepare(
                    "UPDATE {$table}
                     SET status='processing', lease_token=%s, lease_until=%s,
                         attempts=attempts+1, started_at=COALESCE(started_at,%s), updated_at=%s
                     WHERE id=%d
                       AND status IN ('queued','retry')
                       AND (lease_until IS NULL OR lease_until < %s)",
                    $token,
                    $lease_until,
                    $now,
                    $now,
                    (int) $row['id'],
                    $now
                )
            );

            if ( 1 !== (int) $updated ) {
                return null;
            }
            return self::get_by_id( (int) $row['id'] );
        }

        public static function mark_storing( int $job_id, string $provider_ref = '' ): void {
            global $wpdb;
            $wpdb->update(
                AGFO_AIM_Schema::jobs_table(),
                [
                    'status'       => 'storing',
                    'provider_ref' => sanitize_text_field( $provider_ref ),
                    'updated_at'   => current_time( 'mysql' ),
                ],
                [ 'id' => $job_id, 'status' => 'processing' ],
                [ '%s', '%s', '%s' ],
                [ '%d', '%s' ]
            );
        }

        public static function complete( int $job_id, array $result, ?float $actual_cost = null ): void {
            global $wpdb;
            $data = [
                'status'         => 'complete',
                'result_json'    => wp_json_encode( $result, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ),
                'completed_at'   => current_time( 'mysql' ),
                'updated_at'     => current_time( 'mysql' ),
                'lease_token'    => '',
                'lease_until'    => null,
                'error_code'     => '',
                'error_message'  => '',
            ];
            $formats = [ '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s' ];
            if ( null !== $actual_cost ) {
                $data['cost_actual'] = max( 0, $actual_cost );
                $formats[]           = '%f';
            }
            $wpdb->update( AGFO_AIM_Schema::jobs_table(), $data, [ 'id' => $job_id ], $formats, [ '%d' ] );
        }

        public static function fail( int $job_id, WP_Error $error, bool $retry = false, int $delay_seconds = 60 ): void {
            global $wpdb;
            $status = $retry ? 'retry' : 'failed';
            $data   = [
                'status'        => $status,
                'next_run_at'   => $retry ? wp_date( 'Y-m-d H:i:s', time() + max( 30, $delay_seconds ) ) : null,
                'lease_token'   => '',
                'lease_until'   => null,
                'error_code'    => sanitize_key( $error->get_error_code() ),
                'error_message' => sanitize_textarea_field( agfo_redact_secrets( $error->get_error_message() ) ),
                'updated_at'    => current_time( 'mysql' ),
                'completed_at'  => $retry ? null : current_time( 'mysql' ),
            ];
            $wpdb->update(
                AGFO_AIM_Schema::jobs_table(),
                $data,
                [ 'id' => $job_id ],
                [ '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s' ],
                [ '%d' ]
            );
        }

        public static function cancel( string $job_uuid, int $user_id ): bool {
            global $wpdb;
            $table = AGFO_AIM_Schema::jobs_table();
            $job   = self::get( $job_uuid );
            if ( ! is_array( $job ) ) {
                return false;
            }
            if ( ! user_can( $user_id, 'manage_options' ) && (int) $job['created_by'] !== $user_id ) {
                return false;
            }
            if ( ! in_array( $job['status'], [ 'draft', 'queued', 'retry' ], true ) ) {
                return false;
            }
            return 1 === (int) $wpdb->update(
                $table,
                [ 'status' => 'cancelled', 'cancelled_at' => current_time( 'mysql' ), 'updated_at' => current_time( 'mysql' ), 'cost_reserved' => 0 ],
                [ 'id' => (int) $job['id'] ],
                [ '%s', '%s', '%s', '%f' ],
                [ '%d' ]
            );
        }

        public static function update_route( int $job_id, string $provider, string $model ): void {
            global $wpdb;
            $wpdb->update(
                AGFO_AIM_Schema::jobs_table(),
                [ 'provider' => sanitize_key( $provider ), 'model' => sanitize_text_field( $model ), 'updated_at' => current_time( 'mysql' ) ],
                [ 'id' => $job_id ],
                [ '%s', '%s', '%s' ],
                [ '%d' ]
            );
        }

        public static function can_view( array $job, int $user_id ): bool {
            return user_can( $user_id, 'manage_options' ) || ( $user_id > 0 && (int) $job['created_by'] === $user_id );
        }

        public static function hydrate( array $row ): array {
            foreach ( [ 'request_json' => 'request', 'result_json' => 'result', 'route_json' => 'routes', 'pricing_snapshot' => 'pricing' ] as $field => $target ) {
                $decoded        = ! empty( $row[ $field ] ) ? json_decode( (string) $row[ $field ], true ) : [];
                $row[ $target ] = is_array( $decoded ) ? $decoded : [];
            }
            return $row;
        }
    }
}
