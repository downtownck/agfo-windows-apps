<?php
if ( ! defined( 'ABSPATH' ) ) exit;

/**
 * AGFO AI Jobs — CHANGED 16.2.0
 * Async job transport: AI cagrisi arka planda calisir, tarayici hafif status
 * poll'lariyla GERCEK asamalari izler (progress bar bu durumlardan beslenir).
 * PHP worker'i ve tarayici baglantisi dakikalarca rehin tutulmaz; LiteSpeed /
 * admin-ajax timeout riski status poll'lara dagitilir.
 * Mevcut senkron agfo_chat_test akisi AYNEN durur (fallback).
 */
if ( ! class_exists( 'AGFO_AIM_AI_Jobs' ) ) {
class AGFO_AIM_AI_Jobs {

    const TTL = 900; // 15 dk

    public static function register_hooks(): void {
        add_action( 'wp_ajax_agfo_ai_job_start',        [ __CLASS__, 'ajax_start' ] );
        add_action( 'wp_ajax_agfo_ai_job_status',       [ __CLASS__, 'ajax_status' ] );
        add_action( 'wp_ajax_agfo_ai_job_run',          [ __CLASS__, 'ajax_run' ] );
        add_action( 'wp_ajax_nopriv_agfo_ai_job_run',   [ __CLASS__, 'ajax_run' ] ); // loopback cookie tasimaz; tek kullanimlik token ile dogrulanir
        add_action( 'wp_ajax_agfo_ai_model_speed',      [ __CLASS__, 'ajax_model_speed' ] );
    }

    /* ── Kayit yardimcilari ─────────────────────────────── */

    private static function key( string $job_id ): string {
        return 'agfo_aijob_' . $job_id;
    }

    private static function load( string $job_id ): array {
        $rec = get_transient( self::key( $job_id ) );
        return is_array( $rec ) ? $rec : [];
    }

    private static function save( string $job_id, array $rec ): void {
        $rec['updated'] = time();
        set_transient( self::key( $job_id ), $rec, self::TTL );
    }

    /* ── 1) Baslat ──────────────────────────────────────── */

    public static function ajax_start(): void {
        if ( ! current_user_can( 'manage_options' ) ) wp_send_json_error( 'Yetki yok' );
        check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );

        $provider = sanitize_text_field( $_POST['provider'] ?? '' );
        $model    = sanitize_text_field( $_POST['model'] ?? '' );
        if ( $provider === '' || $model === '' ) wp_send_json_error( 'Sağlayıcı ve model gerekli' );

        $messages_raw = isset( $_POST['messages'] ) ? stripslashes( (string) $_POST['messages'] ) : '[]';
        $messages     = json_decode( $messages_raw, true );
        if ( ! is_array( $messages ) ) $messages = [];

        $job_id = function_exists( 'wp_generate_password' )
            ? strtolower( wp_generate_password( 16, false, false ) )
            : substr( md5( uniqid( (string) wp_rand(), true ) ), 0, 16 );
        $token  = function_exists( 'wp_generate_password' )
            ? wp_generate_password( 24, false, false )
            : md5( uniqid( (string) wp_rand(), true ) );

        $rec = [
            'status'   => 'queued',
            'stage'    => 'queued',
            'detail'   => [],
            'attempt'  => 0,
            'created'  => time(),
            'token'    => $token,
            'params'   => [
                'provider'    => $provider,
                'model'       => $model,
                'system'      => sanitize_textarea_field( $_POST['system'] ?? '' ),
                'temperature' => (float) ( $_POST['temperature'] ?? 0.7 ),
                'max_tokens'  => (int) ( $_POST['max_tokens'] ?? 1024 ),
                'messages'    => $messages,
            ],
        ];
        self::save( $job_id, $rec );

        // Non-blocking loopback: worker'i tetikle, cevabi BEKLEME.
        wp_remote_post( admin_url( 'admin-ajax.php' ), [
            'timeout'   => 0.01,
            'blocking'  => false,
            'sslverify' => apply_filters( 'https_local_ssl_verify', false ),
            'body'      => [ 'action' => 'agfo_ai_job_run', 'job_id' => $job_id, 'job_token' => $token ],
        ] );

        wp_send_json_success( [ 'job_id' => $job_id ] );
    }

    /* ── 2) Worker (arka plan) ──────────────────────────── */

    public static function ajax_run(): void {
        $job_id = sanitize_text_field( $_POST['job_id'] ?? '' );
        $token  = sanitize_text_field( $_POST['job_token'] ?? '' );
        if ( $job_id === '' ) wp_send_json_error( 'job_id yok' );

        $rec = self::load( $job_id );
        if ( empty( $rec ) ) wp_send_json_error( 'İş bulunamadı' );

        // Yetki: tek kullanimlik token (loopback) VEYA giris yapmis admin + nonce (JS kick fallback).
        $token_ok = ( $token !== '' && ! empty( $rec['token'] ) && hash_equals( (string) $rec['token'], $token ) );
        $admin_ok = ( is_user_logged_in() && current_user_can( 'manage_options' )
                      && check_ajax_referer( 'agfo_ajax_nonce', 'nonce', false ) );
        if ( ! $token_ok && ! $admin_ok ) wp_send_json_error( 'Yetki yok', 403 );
        if ( ( $rec['status'] ?? '' ) !== 'queued' ) wp_send_json_success( [ 'note' => 'zaten calisiyor/bitti' ] );

        // Tek kullanimlik: token tuket, calisiyor isaretle.
        $rec['token']  = '';
        $rec['status'] = 'running';
        $rec['stage']  = 'starting';
        self::save( $job_id, $rec );

        if ( function_exists( 'ignore_user_abort' ) ) ignore_user_abort( true );
        if ( function_exists( 'set_time_limit' ) ) @set_time_limit( 0 );

        $progress = function ( $stage, $detail = [] ) use ( $job_id ) {
            $rec = self::load( $job_id );
            if ( empty( $rec ) ) return;
            $rec['stage']  = (string) $stage;
            $rec['detail'] = is_array( $detail ) ? $detail : [];
            if ( isset( $detail['attempt'] ) ) $rec['attempt'] = (int) $detail['attempt'];
            self::save( $job_id, $rec );
        };

        $p     = $rec['params'];
        $start = microtime( true );
        $result = ( class_exists( 'AGFO_AIM_Ajax_Data' ) && method_exists( 'AGFO_AIM_Ajax_Data', 'chat_dispatch' ) )
            ? AGFO_AIM_Ajax_Data::chat_dispatch( (string) $p['provider'], (string) $p['model'], (array) $p['messages'], (string) $p['system'], (float) $p['temperature'], (int) $p['max_tokens'], $progress )
            : [ 'error' => 'chat_dispatch bulunamadı' ];

        $rec = self::load( $job_id );
        if ( empty( $rec ) ) $rec = [ 'created' => time() ];
        $rec['elapsed_ms'] = (int) round( ( microtime( true ) - $start ) * 1000 );
        if ( isset( $result['error'] ) ) {
            $rec['status'] = 'error';
            $rec['stage']  = 'error';
            $rec['error']  = (string) $result['error'];
        } else {
            $rec['status'] = 'done';
            $rec['stage']  = 'done';
            $rec['result'] = $result;
        }
        self::save( $job_id, $rec );
        wp_send_json_success( [ 'status' => $rec['status'] ] );
    }

    /* ── 3) Durum ───────────────────────────────────────── */

    public static function ajax_status(): void {
        if ( ! current_user_can( 'manage_options' ) ) wp_send_json_error( 'Yetki yok' );
        check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );

        $job_id = sanitize_text_field( $_POST['job_id'] ?? '' );
        $rec    = self::load( $job_id );
        if ( empty( $rec ) ) wp_send_json_error( 'İş bulunamadı (süresi dolmuş olabilir)' );

        $out = [
            'status'     => (string) ( $rec['status'] ?? 'queued' ),
            'stage'      => (string) ( $rec['stage'] ?? '' ),
            'attempt'    => (int) ( $rec['attempt'] ?? 0 ),
            'detail'     => is_array( $rec['detail'] ?? null ) ? $rec['detail'] : [],
            'age'        => time() - (int) ( $rec['created'] ?? time() ),
            'elapsed_ms' => (int) ( $rec['elapsed_ms'] ?? 0 ),
        ];
        if ( $out['status'] === 'done' )  $out['result'] = $rec['result'] ?? [];
        if ( $out['status'] === 'error' ) $out['error']  = (string) ( $rec['error'] ?? 'Bilinmeyen hata' );
        if ( $out['status'] === 'done' || $out['status'] === 'error' ) {
            delete_transient( self::key( $job_id ) ); // sonuc teslim edildi
        }
        wp_send_json_success( $out );
    }

    /* ── 4) Hiz rozeti (Model Intelligence'tan) ─────────── */

    public static function ajax_model_speed(): void {
        if ( ! current_user_can( 'manage_options' ) ) wp_send_json_error( 'Yetki yok' );
        check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );

        $provider = sanitize_key( $_POST['provider'] ?? '' );
        $model    = sanitize_text_field( $_POST['model'] ?? '' );
        if ( $provider === '' || $model === '' ) wp_send_json_error( 'Parametre eksik' );

        if ( ! function_exists( 'agfo_ai_get_model_intelligence' ) ) wp_send_json_success( [] );
        $mi = agfo_ai_get_model_intelligence( $provider, $model );
        if ( ! is_array( $mi ) || empty( $mi ) ) wp_send_json_success( [] );

        wp_send_json_success( [
            'speed_score'      => isset( $mi['speed_score'] ) ? (int) $mi['speed_score'] : null,
            'final_agfo_score' => isset( $mi['final_agfo_score'] ) ? (int) $mi['final_agfo_score'] : null,
            'label'            => (string) ( $mi['recommendation_label'] ?? '' ),
        ] );
    }
}
}
