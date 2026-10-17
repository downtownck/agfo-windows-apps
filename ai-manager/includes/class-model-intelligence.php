<?php
if ( ! defined( 'ABSPATH' ) ) exit;

if ( ! class_exists( 'AGFO_AIM_Model_Intelligence' ) ) {
class AGFO_AIM_Model_Intelligence {

    public static function get_active_provider(): string {
        return function_exists( 'agfo_get_selected_provider' ) ? sanitize_key( agfo_get_selected_provider() ) : sanitize_key( get_option( 'agfo_selected_provider', 'openai' ) );
    }

    public static function read_data(): array {
        if ( function_exists( 'agfo_read_data_json' ) ) {
            $data = agfo_read_data_json();
            return is_array( $data ) ? $data : array();
        }
        $file = defined( 'AGFO_AIM_DATA_FILE' ) ? AGFO_AIM_DATA_FILE : '';
        if ( ! $file || ! file_exists( $file ) ) return array();
        $data = json_decode( (string) file_get_contents( $file ), true );
        return is_array( $data ) ? $data : array();
    }

    public static function write_data( array $data ): bool {
        if ( function_exists( 'agfo_write_data_json' ) ) {
            return (bool) agfo_write_data_json( $data );
        }
        $file = defined( 'AGFO_AIM_DATA_FILE' ) ? AGFO_AIM_DATA_FILE : '';
        if ( ! $file ) return false;
        if ( ! is_dir( dirname( $file ) ) ) wp_mkdir_p( dirname( $file ) );
        $json = wp_json_encode( $data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES );
        if ( ! is_string( $json ) || $json === '' ) return false;
        return false !== file_put_contents( $file, $json, LOCK_EX );
    }

    public static function get_models_for_provider( string $provider = '' ): array {
        $provider = $provider !== '' ? sanitize_key( $provider ) : self::get_active_provider();
        if ( $provider === '' ) return array();

        if ( function_exists( 'agfo_get_models_for_provider_public' ) ) {
            $rows = agfo_get_models_for_provider_public( $provider );
            if ( is_array( $rows ) && ! empty( $rows ) ) return self::normalize_model_rows( $provider, $rows );
        }

        $data = self::read_data();
        $ids = array();
        $sources = array(
            $data['models'][ $provider ] ?? null,
            $data['providers'][ $provider ]['models'] ?? null,
            $data[ $provider ]['models'] ?? null,
            $data['data'][ $provider ]['models'] ?? null,
        );

        foreach ( $sources as $list ) {
            if ( ! is_array( $list ) ) continue;
            foreach ( $list as $item ) {
                $ids[] = is_string( $item ) ? $item : ( $item['id'] ?? $item['model'] ?? $item['name'] ?? '' );
            }
        }

        $ids = array_values( array_unique( array_filter( array_map( 'strval', $ids ) ) ) );
        sort( $ids );

        $out = array();
        foreach ( $ids as $id ) {
            $out[] = self::get_intelligence( $provider, $id );
        }
        return $out;
    }

    private static function normalize_model_rows( string $provider, array $rows ): array {
        $out = array();
        foreach ( $rows as $row ) {
            $id = is_array( $row ) ? (string) ( $row['id'] ?? $row['model'] ?? $row['name'] ?? '' ) : (string) $row;
            if ( $id === '' ) continue;
            $intel = self::get_intelligence( $provider, $id );
            if ( is_array( $row ) ) $intel = array_merge( $intel, $row, $intel );
            $out[] = $intel;
        }
        return $out;
    }

    public static function get_intelligence( string $provider, string $model ): array {
        $provider = sanitize_key( $provider );
        $model = trim( $model );
        if ( $provider === '' || $model === '' ) return array();

        $data = self::read_data();
        $saved_intel = $data['model_intelligence'][ $provider ][ $model ] ?? array();
        if ( ! is_array( $saved_intel ) ) $saved_intel = array();

        $caps = function_exists( 'agfo_get_model_capabilities' ) ? agfo_get_model_capabilities( $provider, $model ) : array();
        if ( ! is_array( $caps ) ) $caps = array();

        $ranking = self::find_ranking_info( $data, $provider, $model );
        $pricing = self::find_price_info( $data, $provider, $model );

        $benchmark = isset( $ranking['score'] ) ? (int) $ranking['score'] : ( function_exists( 'agfo_rank_model' ) ? (int) agfo_rank_model( $provider, $model ) : 50 );
        $tier = $ranking['tier'] ?? ( function_exists( 'agfo_model_tier_from_score' ) ? agfo_model_tier_from_score( $benchmark ) : 'D' );
        $input_price = self::price_value( $pricing, array( 'input_price_per_1m', 'input_per_1m', 'input_price' ) );
        $output_price = self::price_value( $pricing, array( 'output_price_per_1m', 'output_per_1m', 'output_price' ) );
        $price_label = (string) ( $pricing['price_label'] ?? $ranking['price_label'] ?? '' );

        if ( ! is_numeric( $input_price ) || ! is_numeric( $output_price ) ) {
            $parsed = self::parse_price_label( $price_label );
            if ( ! is_numeric( $input_price ) && isset( $parsed['input'] ) ) $input_price = $parsed['input'];
            if ( ! is_numeric( $output_price ) && isset( $parsed['output'] ) ) $output_price = $parsed['output'];
        }
        if ( is_numeric( $input_price ) && ! is_numeric( $output_price ) ) $output_price = (float) $input_price;

        $cost_score = self::cost_score( is_numeric( $input_price ) ? (float) $input_price : null, is_numeric( $output_price ) ? (float) $output_price : null );
        $speed_score = self::speed_score( array_merge( $caps, $saved_intel ) );
        $fp_score = isset( $ranking['fp'] ) ? (int) $ranking['fp'] : (int) round( ( $benchmark * 0.55 ) + ( $cost_score * 0.30 ) + ( $speed_score * 0.15 ) );
        $final = (int) round( ( $benchmark * 0.50 ) + ( $fp_score * 0.30 ) + ( $speed_score * 0.10 ) + ( $cost_score * 0.10 ) );

        $base = array(
            'provider'                => $provider,
            'id'                      => $model,
            'model'                   => $model,
            'supports_chat'           => isset( $caps['supports_chat'] ) ? (bool) $caps['supports_chat'] : true,
            'supports_temperature'    => isset( $caps['supports_temperature'] ) ? (bool) $caps['supports_temperature'] : true,
            'temperature_status'      => (string) ( $caps['temperature_status'] ?? 'unknown' ),
            'endpoint_type'           => (string) ( $caps['endpoint_type'] ?? 'chat' ),
            'docx_allowed'            => isset( $caps['docx_allowed'] ) ? (bool) $caps['docx_allowed'] : true,
            'compatibility_level'     => (string) ( $caps['compatibility_level'] ?? 'unknown' ),
            'compatibility_notes'     => $caps['compatibility_notes'] ?? array(),
            'probe_status'            => (string) ( $caps['probe_status'] ?? 'not_tested' ),
            'benchmark_score'         => max( 0, min( 100, $benchmark ) ),
            'tier'                    => (string) $tier,
            'speed_score'             => max( 0, min( 100, $speed_score ) ),
            'cost_score'              => max( 0, min( 100, $cost_score ) ),
            'fp_score'                => max( 0, min( 100, $fp_score ) ),
            'final_agfo_score'        => max( 0, min( 100, $final ) ),
            'recommendation_label'    => self::recommendation_label( $final, $cost_score, $speed_score, $caps ),
            'input_price_per_1m'      => is_numeric( $input_price ) ? (float) $input_price : null,
            'output_price_per_1m'     => is_numeric( $output_price ) ? (float) $output_price : null,
            'currency'                => (string) ( $pricing['currency'] ?? 'USD' ),
            'price_label'             => $price_label,
            'price_source'            => (string) ( $pricing['_source'] ?? $ranking['_source'] ?? 'unknown' ),
            'price_updated_at'        => (string) ( $pricing['price_updated_at'] ?? $pricing['updated_at'] ?? '' ),
            'updated_at'              => current_time( 'mysql' ),
            'capability_source'       => (string) ( $caps['capability_source'] ?? 'default_unknown' ),
        );

        return array_merge( $base, $saved_intel, $base );
    }

    public static function get_compatible_models( array $args = array() ): array {
        $provider = isset( $args['provider'] ) && $args['provider'] !== '' ? sanitize_key( (string) $args['provider'] ) : self::get_active_provider();
        $models = self::get_models_for_provider( $provider );
        $out = array();
        foreach ( $models as $row ) {
            if ( ! empty( $args['chat_only'] ) && empty( $row['supports_chat'] ) ) continue;
            if ( ! empty( $args['docx_only'] ) && empty( $row['docx_allowed'] ) ) continue;
            if ( ! empty( $args['temperature_required'] ) && empty( $row['supports_temperature'] ) ) continue;
            if ( isset( $args['min_score'] ) && (int) $row['final_agfo_score'] < (int) $args['min_score'] ) continue;
            $out[] = $row;
        }
        usort( $out, function( $a, $b ) use ( $args ) {
            $key = ! empty( $args['prefer_cheapest'] ) ? 'cost_score' : ( ! empty( $args['prefer_best_fp'] ) ? 'fp_score' : 'final_agfo_score' );
            $av = (int) ( $a[ $key ] ?? 0 );
            $bv = (int) ( $b[ $key ] ?? 0 );
            return $av === $bv ? strcmp( (string) $a['id'], (string) $b['id'] ) : $bv <=> $av;
        } );
        return $out;
    }

    public static function estimate_cost( string $provider, string $model, int $input_tokens, int $output_tokens ): array {
        $intel = self::get_intelligence( $provider, $model );
        $in = $intel['input_price_per_1m'] ?? null;
        $out = $intel['output_price_per_1m'] ?? null;
        if ( ! is_numeric( $in ) || ! is_numeric( $out ) ) {
            return array( 'label' => 'price_unknown', 'value' => 0.0, 'currency' => 'USD', 'source' => 'missing_price_metadata' );
        }
        $value = ( $input_tokens * (float) $in / 1000000 ) + ( $output_tokens * (float) $out / 1000000 );
        return array(
            'label'    => '$' . number_format( $value, 8, '.', '' ),
            'value'    => $value,
            'currency' => (string) ( $intel['currency'] ?? 'USD' ),
            'source'   => (string) ( $intel['price_source'] ?? 'model_intelligence' ),
        );
    }

    public static function probe_and_save( string $provider, string $model ): array {
        $provider = sanitize_key( $provider );
        $model = trim( $model );
        $started = microtime( true );
        $base = self::get_intelligence( $provider, $model );
        $base['probe_status'] = 'completed';
        $base['capability_source'] = 'batch_probe';
        $base['probed_at'] = current_time( 'mysql' );
        $base['estimated_input_tokens'] = 16;
        $base['estimated_output_tokens'] = 16;

        $chat = self::send_probe( $provider, $model, false );
        if ( empty( $chat['ok'] ) ) {
            $base['supports_chat'] = false;
            $base['docx_allowed'] = false;
            $base['supports_temperature'] = false;
            $base['temperature_status'] = 'unsupported';
            $base['compatibility_level'] = 'blocked';
            $base['compatibility_notes'] = array( (string) ( $chat['message'] ?? 'Chat probe failed.' ) );
            $base['endpoint_type'] = self::error_says_not_chat( (string) ( $chat['message'] ?? '' ) ) ? 'completions' : 'not_chat';
        } else {
            $base['supports_chat'] = true;
            $base['docx_allowed'] = true;
            $base['endpoint_type'] = $provider === 'gemini' ? 'generateContent' : ( $provider === 'claude' ? 'messages' : 'chat' );
            $base['compatibility_level'] = 'ok';
            $base['compatibility_notes'] = array( strtoupper( $provider ) . ' chat probe OK.' );

            $temp = self::send_probe( $provider, $model, true );
            if ( ! empty( $temp['ok'] ) ) {
                $base['supports_temperature'] = true;
                $base['temperature_status'] = 'supported';
                $base['compatibility_notes'][] = 'Temperature probe OK.';
            } else {
                $base['supports_temperature'] = false;
                $base['temperature_status'] = 'unsupported';
                $base['compatibility_notes'][] = 'Temperature unsupported: ' . (string) ( $temp['message'] ?? 'Unknown error.' );
            }
        }

        $cost = self::estimate_cost( $provider, $model, 16, 16 );
        $base['estimated_cost_label'] = $cost['label'];
        $base['estimated_cost_value'] = $cost['value'];
        $base['estimated_cost_source'] = $cost['source'];
        $base['duration_ms'] = (int) round( ( microtime( true ) - $started ) * 1000 );
        $base['updated_at'] = current_time( 'mysql' );

        self::save_intelligence( $provider, $model, $base );
        if ( function_exists( 'agfo_save_model_capabilities' ) ) {
            agfo_save_model_capabilities( $provider, $model, array(
                'provider'             => $provider,
                'id'                   => $model,
                'endpoint_type'        => $base['endpoint_type'],
                'supports_chat'        => (bool) $base['supports_chat'],
                'supports_temperature' => (bool) $base['supports_temperature'],
                'temperature_status'   => (string) $base['temperature_status'],
                'docx_allowed'         => (bool) $base['docx_allowed'],
                'compatibility_level'  => (string) $base['compatibility_level'],
                'compatibility_notes'  => $base['compatibility_notes'],
                'capability_source'    => 'batch_probe',
                'probe_status'         => 'completed',
                'probed_at'            => current_time( 'mysql' ),
            ) );
        }
        return $base;
    }

    public static function save_intelligence( string $provider, string $model, array $intel ): bool {
        $data = self::read_data();
        if ( empty( $data['model_intelligence'] ) || ! is_array( $data['model_intelligence'] ) ) $data['model_intelligence'] = array();
        if ( empty( $data['model_intelligence'][ $provider ] ) || ! is_array( $data['model_intelligence'][ $provider ] ) ) $data['model_intelligence'][ $provider ] = array();
        $data['model_intelligence'][ $provider ][ $model ] = $intel;
        return self::write_data( $data );
    }

    private static function send_probe( string $provider, string $model, bool $with_temp ): array {
        $registry = function_exists( 'agfo_api_registry' ) ? agfo_api_registry() : array();
        if ( empty( $registry[ $provider ] ) ) return array( 'ok' => false, 'message' => 'Provider bulunamadı: ' . $provider );
        $key = function_exists( 'agfo_get_api_key' ) ? agfo_get_api_key( $provider ) : '';
        if ( empty( $key ) ) return array( 'ok' => false, 'message' => 'API anahtarı yok: ' . $provider );
        $info = $registry[ $provider ];
        $url = (string) ( $info['chat_url'] ?? '' );
        if ( $provider === 'gemini' ) $url = str_replace( array( '{model}', '{key}' ), array( str_replace( 'models/', '', $model ), $key ), $url );
        // CHANGED 17.0.0: every intelligence probe bypasses the request guard (genuine evidence).
        $headers = array( 'Content-Type' => 'application/json', 'Accept' => 'application/json', 'X-AGFO-Raw-Probe' => '1' );
        // CHANGED 16.17.7: Let explicit temperature capability probes bypass the global runtime sampling shield.
        if ( $with_temp ) $headers['X-AGFO-Temperature-Probe'] = '1';
        foreach ( (array) ( $info['auth'] ?? array() ) as $hk => $hv ) $headers[ $hk ] = str_replace( '{key}', $key, $hv );

        if ( in_array( $provider, array( 'openai', 'openrouter', 'groq', 'deepseek', 'deepinfra', 'llama_together', 'together', 'nvidia' ), true ) ) { // CHANGED 16.1.0: nvidia eklendi (OpenAI-uyumlu govde)
            $body = array( 'model' => $model, 'messages' => array( array( 'role' => 'user', 'content' => 'Reply exactly: OK' ) ) );
            // CHANGED 17.0.0: reasoning models need room to think before answering; 8 tokens produced false "chat ✗".
            $probe_reasoning = in_array( $provider, array( 'openai', 'openrouter' ), true ) && function_exists( 'agfo_openai_model_is_reasoning' ) && agfo_openai_model_is_reasoning( preg_replace( '#^[^/]+/#', '', $model ) );
            $probe_tokens    = $probe_reasoning ? 512 : 16;
            if ( function_exists( 'agfo_uses_max_completion_tokens' ) && agfo_uses_max_completion_tokens( $model ) ) $body['max_completion_tokens'] = $probe_tokens; else $body['max_tokens'] = $probe_tokens;
            if ( $probe_reasoning && $provider === 'openai' ) $body['reasoning_effort'] = 'low';
            if ( $with_temp ) $body['temperature'] = 0.2;
        } elseif ( $provider === 'claude' ) {
            $body = array( 'model' => $model, 'max_tokens' => 8, 'messages' => array( array( 'role' => 'user', 'content' => 'Reply exactly: OK' ) ) );
            if ( $with_temp ) $body['temperature'] = 0.2;
        } elseif ( $provider === 'gemini' ) {
            $body = array( 'contents' => array( array( 'role' => 'user', 'parts' => array( array( 'text' => 'Reply exactly: OK' ) ) ) ), 'generationConfig' => array( 'maxOutputTokens' => 8 ) );
            if ( $with_temp ) $body['generationConfig']['temperature'] = 0.2;
        } else {
            return array( 'ok' => false, 'message' => 'Provider probe desteklenmiyor: ' . $provider );
        }

        $probe_timeout = ( $provider === 'nvidia' ) ? 75 : 45; // CHANGED 16.1.0: NIM kuyrugu icin genis pay
        $runner = function() use ( $url, $headers, $body, $probe_timeout ) {
            return wp_remote_post( $url, array( 'timeout' => $probe_timeout, 'sslverify' => true, 'headers' => $headers, 'body' => wp_json_encode( $body ) ) );
        };
        $res = function_exists( 'agfo_ai_manager_without_connector_guard' ) ? agfo_ai_manager_without_connector_guard( $runner ) : $runner();
        if ( is_wp_error( $res ) ) return array( 'ok' => false, 'message' => $res->get_error_message() );
        $code = (int) wp_remote_retrieve_response_code( $res );
        $raw = (string) wp_remote_retrieve_body( $res );
        // CHANGED 16.1.0: NVIDIA 202 -> sonucu poll ile al.
        if ( $provider === 'nvidia' && $code === 202 && function_exists( 'agfo_nvidia_poll_result' ) ) {
            $req_id = (string) wp_remote_retrieve_header( $res, 'nvcf-reqid' );
            if ( $req_id === '' ) {
                $j202 = json_decode( $raw, true );
                if ( is_array( $j202 ) ) $req_id = (string) ( $j202['requestId'] ?? $j202['request_id'] ?? $j202['id'] ?? '' );
            }
            if ( $req_id !== '' ) {
                $polled = agfo_nvidia_poll_result( $req_id, $headers, 60 );
                if ( isset( $polled['http_code'] ) ) { $code = (int) $polled['http_code']; $raw = (string) $polled['body']; }
                else return array( 'ok' => false, 'message' => (string) ( $polled['error'] ?? 'NVIDIA async sonucu alinamadi' ), 'http_code' => 202 );
            }
        }
        $json = json_decode( $raw, true );
        if ( $code < 200 || $code >= 300 ) {
            $msg = $json['error']['message'] ?? $json['message'] ?? $raw;
            // CHANGED 17.0.0: a length stop proves the chat endpoint serves the model.
            if ( stripos( (string) $msg, 'output limit' ) !== false ) {
                return array( 'ok' => true, 'message' => strtoupper( $provider ) . ' OK (length)', 'http_code' => $code );
            }
            return array( 'ok' => false, 'message' => wp_strip_all_tags( (string) $msg ), 'http_code' => $code );
        }
        return array( 'ok' => true, 'message' => strtoupper( $provider ) . ' OK', 'http_code' => $code );
    }

    private static function find_ranking_info( array $data, string $provider, string $model ): array {
        $paths = array( array( 'rankings', $provider, $model ), array( 'ranking', $provider, $model ), array( 'benchmarks', $provider, $model ), array( 'benchmark', $provider, $model ) );
        return self::first_array_path( $data, $paths );
    }

    private static function find_price_info( array $data, string $provider, string $model ): array {
        $paths = array(
            array( 'pricing_meta', $provider, $model ), array( 'prices', $provider, $model ), array( 'pricing', $provider, $model ),
            array( 'model_prices', $provider, $model ), array( 'models_meta', $provider, $model ), array( 'rankings', $provider, $model ),
        );
        return self::first_array_path( $data, $paths );
    }

    private static function first_array_path( array $data, array $paths ): array {
        foreach ( $paths as $path ) {
            $node = $data;
            foreach ( $path as $key ) {
                if ( ! is_array( $node ) || ! array_key_exists( $key, $node ) ) { $node = null; break; }
                $node = $node[ $key ];
            }
            if ( is_array( $node ) ) { $node['_source'] = implode( '.', $path ); return $node; }
        }
        return array();
    }

    private static function price_value( array $row, array $keys ) {
        foreach ( $keys as $key ) if ( isset( $row[ $key ] ) && is_numeric( $row[ $key ] ) ) return (float) $row[ $key ];
        return null;
    }

    private static function parse_price_label( string $label ): array {
        if ( $label === '' ) return array();
        if ( preg_match_all( '/([0-9]+(?:\.[0-9]+)?)/', $label, $m ) ) {
            $out = array();
            if ( isset( $m[1][0] ) ) $out['input'] = (float) $m[1][0];
            if ( isset( $m[1][1] ) ) $out['output'] = (float) $m[1][1];
            return $out;
        }
        return array();
    }

    private static function cost_score( $input, $output ): int {
        if ( ! is_numeric( $input ) || ! is_numeric( $output ) ) return 50;
        $avg = ( (float) $input + (float) $output ) / 2;
        if ( $avg <= 0.15 ) return 100;
        if ( $avg <= 0.50 ) return 92;
        if ( $avg <= 1.00 ) return 84;
        if ( $avg <= 3.00 ) return 72;
        if ( $avg <= 8.00 ) return 58;
        if ( $avg <= 20.00 ) return 42;
        return 25;
    }

    private static function speed_score( array $meta ): int {
        if ( isset( $meta['duration_ms'] ) && is_numeric( $meta['duration_ms'] ) ) {
            $ms = (int) $meta['duration_ms'];
            if ( $ms <= 1200 ) return 100;
            if ( $ms <= 2500 ) return 86;
            if ( $ms <= 5000 ) return 70;
            if ( $ms <= 9000 ) return 54;
            return 38;
        }
        return 65;
    }

    private static function recommendation_label( int $final, int $cost, int $speed, array $caps ): string {
        if ( empty( $caps['supports_chat'] ) ) return 'Blocked';
        if ( $final >= 88 && $cost >= 70 ) return 'Best AGFO Choice';
        if ( $cost >= 90 ) return 'Budget Friendly';
        if ( $speed >= 86 ) return 'Fast';
        if ( $final >= 75 ) return 'Balanced';
        return 'Usable';
    }

    private static function error_says_not_chat( string $message ): bool {
        $m = strtolower( $message );
        return strpos( $m, 'not a chat model' ) !== false || strpos( $m, 'not supported in the v1/chat/completions' ) !== false || strpos( $m, 'did you mean to use v1/completions' ) !== false;
    }
}
}
