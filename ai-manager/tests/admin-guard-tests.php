<?php
/**
 * AGFO AI Manager 17.3.1 — front-end loading guard for AI Kontrol Merkezi.
 * Run from the plugin root: php tests/admin-guard-tests.php
 */
if ( PHP_SAPI !== 'cli' ) { exit; }
if ( ! defined( 'ABSPATH' ) ) define( 'ABSPATH', sys_get_temp_dir() . '/' );
if ( ! defined( 'AGFO_AIM_PLUGIN_DIR' ) ) define( 'AGFO_AIM_PLUGIN_DIR', dirname( __DIR__ ) . '/' );
if ( ! defined( 'AGFO_AIM_PLUGIN_URL' ) ) define( 'AGFO_AIM_PLUGIN_URL', 'https://example.test/p/' );
if ( ! defined( 'AGFO_AIM_VERSION' ) ) define( 'AGFO_AIM_VERSION', 'test' );
$GLOBALS['AGFO_G'] = [ 'admin' => false, 'bar' => false, 'filters' => [], 'scripts' => [], 'included' => 0 ];
if ( ! function_exists( 'is_admin' ) ) { function is_admin() { return $GLOBALS['AGFO_G']['admin']; } }
if ( ! function_exists( 'is_admin_bar_showing' ) ) { function is_admin_bar_showing() { return $GLOBALS['AGFO_G']['bar']; } }
if ( ! function_exists( 'apply_filters' ) ) { function apply_filters( $h, $v ) { foreach ( $GLOBALS['AGFO_G']['filters'][ $h ] ?? [] as $cb ) { $v = $cb( $v ); } return $v; } }
if ( ! function_exists( 'is_user_logged_in' ) ) { function is_user_logged_in() { return true; } }
if ( ! function_exists( 'current_user_can' ) ) { function current_user_can( $c ) { return true; } }
if ( ! function_exists( 'wp_enqueue_script' ) ) { function wp_enqueue_script( $h ) { $GLOBALS['AGFO_G']['scripts'][] = $h; } }
if ( ! function_exists( 'wp_enqueue_style' ) ) { function wp_enqueue_style( $h ) { $GLOBALS['AGFO_G']['scripts'][] = 'css:' . $h; } }
if ( ! function_exists( 'wp_localize_script' ) ) { function wp_localize_script() {} }
if ( ! function_exists( 'admin_url' ) ) { function admin_url( $p = '' ) { return '/wp-admin/' . $p; } }
if ( ! function_exists( 'wp_create_nonce' ) ) { function wp_create_nonce( $a ) { return 'n'; } }
require dirname( __DIR__ ) . '/admin/class-admin.php';

$agfo_aim_test_pass = 0; $agfo_aim_test_fail = 0;
if ( ! function_exists( 'agfo_aim_test_ag_check' ) ) {
    function agfo_aim_test_ag_check( $ok, $name ) { global $agfo_aim_test_pass, $agfo_aim_test_fail; if ( $ok ) { $agfo_aim_test_pass++; echo "PASS $name\n"; } else { $agfo_aim_test_fail++; echo "FAIL $name\n"; } }
}

agfo_aim_test_ag_check( AGFO_AIM_Admin::frontend_switcher_needed() === false, 'G1 front end without admin bar: not needed' );
AGFO_AIM_Admin::enqueue_assets( '' );
agfo_aim_test_ag_check( ! in_array( 'agfo-switcher', $GLOBALS['AGFO_G']['scripts'], true ) && in_array( 'agfo-progress', $GLOBALS['AGFO_G']['scripts'], true ), 'G2 switcher assets skipped, shared progress bar kept' );
$GLOBALS['AGFO_G']['bar'] = true; $GLOBALS['AGFO_G']['scripts'] = [];
AGFO_AIM_Admin::enqueue_assets( '' );
agfo_aim_test_ag_check( AGFO_AIM_Admin::frontend_switcher_needed() && in_array( 'agfo-switcher', $GLOBALS['AGFO_G']['scripts'], true ), 'G3 front end with admin bar: loaded' );
$GLOBALS['AGFO_G']['bar'] = false; $GLOBALS['AGFO_G']['admin'] = true;
agfo_aim_test_ag_check( AGFO_AIM_Admin::frontend_switcher_needed(), 'G4 wp-admin always loads' );
$GLOBALS['AGFO_G']['admin'] = false; $GLOBALS['AGFO_G']['filters']['agfo_aim_frontend_control_center'][] = function () { return true; };
agfo_aim_test_ag_check( AGFO_AIM_Admin::frontend_switcher_needed(), 'G5 filter can opt a front-end page in' );

echo "\n$agfo_aim_test_pass pass / $agfo_aim_test_fail fail\n";
exit( $agfo_aim_test_fail ? 1 : 0 );
