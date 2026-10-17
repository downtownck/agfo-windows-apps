<?php
/**
 * Native development and rollout tracker.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Native_Tracker' ) ) {
    final class AGFO_AIM_Native_Tracker {
        const RUNTIME_OPTION = 'agfo_ai_tracker_runtime';
        const AUDIT_OPTION   = 'agfo_ai_tracker_audit';

        public static function register_hooks(): void {
            add_action( 'admin_menu', [ __CLASS__, 'add_menu' ], 30 );
            add_action( 'admin_post_agfo_ai_tracker_update', [ __CLASS__, 'handle_update' ] );
        }

        public static function add_menu(): void {
            add_submenu_page(
                'agfo-ai-manager',
                'Geliştirme Takibi',
                '🧭 Geliştirme Takibi',
                'manage_options',
                'agfo-ai-rollout-tracker',
                [ __CLASS__, 'render' ]
            );
        }

        public static function load_plan() {
            $path = AGFO_AIM_PLUGIN_DIR . 'tracker.json';
            if ( ! is_readable( $path ) ) {
                return new WP_Error( 'agfo_tracker_missing', 'tracker.json bulunamadı veya okunamıyor.' );
            }
            $raw  = file_get_contents( $path );
            $plan = json_decode( (string) $raw, true );
            if ( ! is_array( $plan ) || empty( $plan['phases'] ) || empty( $plan['current_release'] ) ) {
                return new WP_Error( 'agfo_tracker_invalid', 'tracker.json geçerli bir AGFO tracker planı değil.' );
            }
            return $plan;
        }

        public static function merged_plan() {
            $plan = self::load_plan();
            if ( is_wp_error( $plan ) ) {
                return $plan;
            }
            $runtime = get_option( self::RUNTIME_OPTION, [] );
            if ( ! is_array( $runtime ) ) {
                $runtime = [];
            }
            foreach ( $plan['phases'] as &$phase ) {
                foreach ( $phase['tasks'] as &$task ) {
                    $id = sanitize_key( (string) $task['id'] );
                    if ( isset( $runtime[ $id ] ) && is_array( $runtime[ $id ] ) ) {
                        $task = array_merge( $task, $runtime[ $id ] );
                    }
                }
            }
            unset( $phase, $task );
            return $plan;
        }

        public static function render(): void {
            self::guard();
            $plan = self::merged_plan();
            if ( is_wp_error( $plan ) ) {
                echo '<div class="wrap"><h1>Geliştirme Takibi</h1><div class="notice notice-error"><p>' . esc_html( $plan->get_error_message() ) . '</p></div></div>';
                return;
            }

            $counts   = self::counts( $plan );
            $percent  = $counts['total'] > 0 ? round( ( $counts['verified'] / $counts['total'] ) * 100 ) : 0;
            $mismatch = (string) $plan['current_release'] !== ( defined( 'AGFO_AIM_VERSION' ) ? AGFO_AIM_VERSION : '' );
            ?>
            <div class="wrap agfo-tracker-wrap">
                <h1>Geliştirme ve Rollout Takibi</h1>
                <p class="description">Paket planı <code>tracker.json</code> dosyasından; manuel doğrulama ve kanıtlar WordPress veri katmanından okunur.</p>
                <?php if ( $mismatch ) : ?><div class="notice notice-error"><p>Tracker sürümü ile plugin sürümü eşleşmiyor.</p></div><?php endif; ?>
                <?php if ( isset( $_GET['updated'] ) ) : ?><div class="notice notice-success is-dismissible"><p>Tracker kaydı güncellendi.</p></div><?php endif; ?>

                <div style="background:#fff;border:1px solid #dcdcde;border-radius:10px;padding:18px;margin:18px 0;max-width:1100px">
                    <div style="display:flex;justify-content:space-between;gap:16px;align-items:center"><strong>Genel ilerleme</strong><span><?php echo esc_html( $counts['verified'] . ' / ' . $counts['total'] . ' doğrulandı' ); ?></span></div>
                    <div style="height:12px;background:#e5e7eb;border-radius:999px;overflow:hidden;margin-top:10px"><div style="height:100%;width:<?php echo esc_attr( (string) $percent ); ?>%;background:#2271b1"></div></div>
                    <p style="margin-bottom:0"><strong>%<?php echo esc_html( (string) $percent ); ?></strong> · implemented: <?php echo esc_html( (string) $counts['implemented'] ); ?> · blocked: <?php echo esc_html( (string) $counts['blocked'] ); ?> · deferred: <?php echo esc_html( (string) $counts['deferred'] ); ?> · sürüm: <?php echo esc_html( (string) $plan['current_release'] ); ?></p>
                </div>

                <?php foreach ( $plan['phases'] as $phase ) :
                    $phase_counts = self::phase_counts( $phase );
                    ?>
                    <section style="background:#fff;border:1px solid #dcdcde;border-radius:10px;padding:18px;margin:18px 0;max-width:1100px">
                        <h2 style="margin-top:0"><?php echo esc_html( (string) $phase['title'] ); ?></h2>
                        <p><?php echo esc_html( (string) $phase['summary'] ); ?></p>
                        <p><strong><?php echo esc_html( $phase_counts['verified'] . ' / ' . $phase_counts['total'] ); ?></strong> doğrulandı</p>
                        <?php foreach ( $phase['tasks'] as $task ) : self::render_task( $task ); endforeach; ?>
                    </section>
                <?php endforeach; ?>
            </div>
            <?php
        }

        private static function render_task( array $task ): void {
            $id           = sanitize_key( (string) $task['id'] );
            $status       = sanitize_key( (string) ( $task['status'] ?? 'pending' ) );
            $dependencies = is_array( $task['dependencies'] ?? null ) ? $task['dependencies'] : [];
            $evidence     = is_array( $task['evidence'] ?? null ) ? $task['evidence'] : [];
            ?>
            <details style="border-top:1px solid #e5e7eb;padding:12px 0" <?php echo in_array( $status, [ 'in_progress', 'blocked' ], true ) ? 'open' : ''; ?>>
                <summary style="cursor:pointer"><code><?php echo esc_html( $id ); ?></code> — <strong><?php echo esc_html( (string) $task['title'] ); ?></strong> <span style="display:inline-block;padding:2px 7px;border-radius:999px;background:#f0f0f1;font-size:11px"><?php echo esc_html( $status ); ?></span></summary>
                <div style="padding:12px 0 0 20px">
                    <p><strong>Talimat:</strong><br><?php echo nl2br( esc_html( (string) $task['instruction'] ) ); ?></p>
                    <p><strong>İş Paketi:</strong><br><?php echo nl2br( esc_html( (string) $task['work_package'] ) ); ?></p>
                    <p><strong>Doğrula:</strong><br><?php echo nl2br( esc_html( (string) $task['verification'] ) ); ?></p>
                    <p><strong>Hedef/Tamamlanan sürüm:</strong> <?php echo esc_html( (string) ( $task['target_version'] ?? '—' ) ); ?> / <?php echo esc_html( (string) ( $task['completed_version'] ?? '—' ) ); ?></p>
                    <p><strong>Bağımlılıklar:</strong> <?php echo esc_html( $dependencies ? implode( ', ', array_map( 'sanitize_key', $dependencies ) ) : 'Yok' ); ?></p>
                    <p><strong>Değişen dosyalar:</strong> <?php echo esc_html( ! empty( $task['changed_files'] ) ? implode( ', ', array_map( 'sanitize_text_field', (array) $task['changed_files'] ) ) : '—' ); ?></p>
                    <?php if ( ! empty( $task['notes'] ) ) : ?><p><strong>Not:</strong> <?php echo esc_html( (string) $task['notes'] ); ?></p><?php endif; ?>
                    <?php if ( $evidence ) : ?>
                        <p><strong>Kanıt:</strong></p><ul>
                        <?php foreach ( $evidence as $item ) : ?><li><?php echo esc_html( (string) ( $item['result'] ?? '' ) . ' · ' . (string) ( $item['name'] ?? '' ) . ' · ' . (string) ( $item['date'] ?? '' ) . ' · ' . (string) ( $item['summary'] ?? '' ) ); ?></li><?php endforeach; ?>
                        </ul>
                    <?php endif; ?>
                    <form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="padding:12px;background:#f6f7f7;border-radius:8px">
                        <input type="hidden" name="action" value="agfo_ai_tracker_update">
                        <input type="hidden" name="task_id" value="<?php echo esc_attr( $id ); ?>">
                        <?php wp_nonce_field( 'agfo_ai_tracker_update_' . $id ); ?>
                        <label><strong>Durum</strong><br><select name="status">
                            <?php foreach ( [ 'pending', 'in_progress', 'implemented', 'verified', 'blocked', 'deferred', 'out_of_scope' ] as $allowed ) : ?><option value="<?php echo esc_attr( $allowed ); ?>" <?php selected( $status, $allowed ); ?>><?php echo esc_html( $allowed ); ?></option><?php endforeach; ?>
                        </select></label>
                        <label style="display:block;margin-top:8px"><strong>Kanıt adı</strong><br><input class="regular-text" type="text" name="evidence_name" value=""></label>
                        <label style="display:block;margin-top:8px"><strong>Sonuç</strong><br><select name="evidence_result"><option value="">—</option><option value="PASS">PASS</option><option value="FAIL">FAIL</option></select></label>
                        <label style="display:block;margin-top:8px"><strong>Özet / blokaj nedeni</strong><br><textarea class="large-text" rows="2" name="summary"></textarea></label>
                        <p><button class="button button-secondary">Kaydet</button></p>
                    </form>
                </div>
            </details>
            <?php
        }

        public static function handle_update(): void {
            self::guard();
            $task_id = isset( $_POST['task_id'] ) ? sanitize_key( wp_unslash( (string) $_POST['task_id'] ) ) : '';
            check_admin_referer( 'agfo_ai_tracker_update_' . $task_id );
            $plan = self::load_plan();
            if ( is_wp_error( $plan ) || ! self::task_exists( $plan, $task_id ) ) {
                wp_die( 'Geçersiz tracker görevi.' );
            }

            $allowed = [ 'pending', 'in_progress', 'implemented', 'verified', 'blocked', 'deferred', 'out_of_scope' ];
            $status  = isset( $_POST['status'] ) ? sanitize_key( wp_unslash( (string) $_POST['status'] ) ) : 'pending';
            if ( ! in_array( $status, $allowed, true ) ) {
                wp_die( 'Geçersiz tracker durumu.' );
            }
            $name    = sanitize_text_field( wp_unslash( (string) ( $_POST['evidence_name'] ?? '' ) ) );
            $result  = sanitize_key( wp_unslash( (string) ( $_POST['evidence_result'] ?? '' ) ) );
            $result  = strtoupper( $result );
            $summary = sanitize_textarea_field( wp_unslash( (string) ( $_POST['summary'] ?? '' ) ) );

            if ( 'verified' === $status && ( 'PASS' !== $result || '' === $name ) ) {
                wp_die( 'Verified durumu için adı bulunan PASS kanıtı zorunludur.' );
            }
            if ( 'verified' === $status ) {
                $merged = self::merged_plan();
                $task   = is_wp_error( $merged ) ? null : self::find_task( $merged, $task_id );
                foreach ( is_array( $task['dependencies'] ?? null ) ? $task['dependencies'] : [] as $dependency_id ) {
                    $dependency = self::find_task( $merged, sanitize_key( (string) $dependency_id ) );
                    if ( ! is_array( $dependency ) || 'verified' !== (string) ( $dependency['status'] ?? '' ) ) {
                        wp_die( 'Bağımlılık doğrulanmadan görev verified yapılamaz: ' . esc_html( (string) $dependency_id ) );
                    }
                }
            }
            if ( in_array( $status, [ 'blocked', 'deferred', 'out_of_scope' ], true ) && '' === $summary ) {
                wp_die( 'Bu durum için gerekçe zorunludur.' );
            }
            if ( 'FAIL' === $result && 'verified' === $status ) {
                wp_die( 'FAIL kanıtı bulunan görev verified yapılamaz.' );
            }

            $runtime = get_option( self::RUNTIME_OPTION, [] );
            if ( ! is_array( $runtime ) ) {
                $runtime = [];
            }
            $existing = isset( $runtime[ $task_id ] ) && is_array( $runtime[ $task_id ] ) ? $runtime[ $task_id ] : [];
            $evidence = isset( $existing['evidence'] ) && is_array( $existing['evidence'] ) ? $existing['evidence'] : [];
            if ( '' !== $name || '' !== $result || '' !== $summary ) {
                $evidence[] = [
                    'name'       => $name ?: 'Manual review',
                    'result'     => in_array( $result, [ 'PASS', 'FAIL' ], true ) ? $result : 'NOTE',
                    'date'       => current_time( 'mysql' ),
                    'version'    => AGFO_AIM_VERSION,
                    'user_id'    => get_current_user_id(),
                    'summary'    => $summary,
                    'log_location'=> '',
                ];
                $evidence = array_slice( $evidence, -20 );
            }
            $runtime[ $task_id ] = [
                'status'            => $status,
                'completed_version' => in_array( $status, [ 'implemented', 'verified' ], true ) ? AGFO_AIM_VERSION : (string) ( $existing['completed_version'] ?? '' ),
                'evidence'          => $evidence,
                'notes'             => $summary ?: (string) ( $existing['notes'] ?? '' ),
            ];
            update_option( self::RUNTIME_OPTION, $runtime, false );

            $audit   = get_option( self::AUDIT_OPTION, [] );
            $audit   = is_array( $audit ) ? $audit : [];
            $audit[] = [ 'task_id' => $task_id, 'status' => $status, 'user_id' => get_current_user_id(), 'time' => current_time( 'mysql' ), 'summary' => $summary ];
            update_option( self::AUDIT_OPTION, array_slice( $audit, -200 ), false );

            wp_safe_redirect( admin_url( 'admin.php?page=agfo-ai-rollout-tracker&updated=1' ) );
            exit;
        }

        private static function find_task( array $plan, string $task_id ): ?array {
            $task_id = sanitize_key( $task_id );
            foreach ( $plan['phases'] as $phase ) {
                foreach ( $phase['tasks'] as $task ) {
                    if ( sanitize_key( (string) $task['id'] ) === $task_id ) {
                        return $task;
                    }
                }
            }
            return null;
        }

        private static function task_exists( array $plan, string $task_id ): bool {
            foreach ( $plan['phases'] as $phase ) {
                foreach ( $phase['tasks'] as $task ) {
                    if ( sanitize_key( (string) $task['id'] ) === $task_id ) {
                        return true;
                    }
                }
            }
            return false;
        }

        private static function counts( array $plan ): array {
            $out = [ 'total' => 0, 'verified' => 0, 'implemented' => 0, 'blocked' => 0, 'deferred' => 0 ];
            foreach ( $plan['phases'] as $phase ) {
                foreach ( $phase['tasks'] as $task ) {
                    $out['total']++;
                    $status = (string) ( $task['status'] ?? 'pending' );
                    if ( isset( $out[ $status ] ) ) {
                        $out[ $status ]++;
                    }
                }
            }
            return $out;
        }

        private static function phase_counts( array $phase ): array {
            $out = [ 'total' => 0, 'verified' => 0 ];
            foreach ( $phase['tasks'] as $task ) {
                $out['total']++;
                if ( 'verified' === (string) ( $task['status'] ?? '' ) ) {
                    $out['verified']++;
                }
            }
            return $out;
        }

        private static function guard(): void {
            if ( ! current_user_can( 'manage_options' ) ) {
                wp_die( 'Yetki yok.' );
            }
        }
    }
}
