<?php
if ( ! defined( 'ABSPATH' ) ) exit;

if ( ! class_exists( 'AGFO_AIM_Model_Public_API' ) ) {
class AGFO_AIM_Model_Public_API {
    public static function register_hooks(): void {
        add_action( 'rest_api_init', array( __CLASS__, 'register_routes' ) );
    }

    public static function register_routes(): void {
        register_rest_route( 'agfo-ai/v1', '/models/compatible', array(
            'methods'             => 'GET',
            'permission_callback' => array( __CLASS__, 'can_read' ),
            'callback'            => array( __CLASS__, 'rest_compatible_models' ),
        ) );
        register_rest_route( 'agfo-ai/v1', '/models/intelligence', array(
            'methods'             => 'GET',
            'permission_callback' => array( __CLASS__, 'can_read' ),
            'callback'            => array( __CLASS__, 'rest_model_intelligence' ),
        ) );
    }

    public static function can_read(): bool {
        return current_user_can( 'manage_options' );
    }

    public static function rest_compatible_models( WP_REST_Request $request ) {
        $args = array(
            'provider'             => sanitize_key( (string) $request->get_param( 'provider' ) ),
            'chat_only'            => (bool) $request->get_param( 'chat_only' ),
            'docx_only'            => (bool) $request->get_param( 'docx_only' ),
            'temperature_required' => (bool) $request->get_param( 'temperature_required' ),
            'prefer_best_fp'       => true,
        );
        return rest_ensure_response( agfo_ai_get_compatible_models( $args ) );
    }

    public static function rest_model_intelligence( WP_REST_Request $request ) {
        $provider = sanitize_key( (string) $request->get_param( 'provider' ) );
        $model    = sanitize_text_field( (string) $request->get_param( 'model' ) );
        if ( $provider === '' || $model === '' ) {
            return new WP_Error( 'agfo_missing_params', 'provider ve model gerekli.', array( 'status' => 400 ) );
        }
        return rest_ensure_response( agfo_ai_get_model_intelligence( $provider, $model ) );
    }
}
}

if ( ! function_exists( 'agfo_ai_get_model_intelligence' ) ) {
    function agfo_ai_get_model_intelligence( $provider, $model ) {
        return class_exists( 'AGFO_AIM_Model_Intelligence' ) ? AGFO_AIM_Model_Intelligence::get_intelligence( (string) $provider, (string) $model ) : array();
    }
}

if ( ! function_exists( 'agfo_ai_get_compatible_models' ) ) {
    function agfo_ai_get_compatible_models( $args = array() ) {
        return class_exists( 'AGFO_AIM_Model_Intelligence' ) ? AGFO_AIM_Model_Intelligence::get_compatible_models( is_array( $args ) ? $args : array() ) : array();
    }
}

if ( ! function_exists( 'agfo_ai_get_docx_allowed_models' ) ) {
    function agfo_ai_get_docx_allowed_models( $provider = '' ) {
        return agfo_ai_get_compatible_models( array( 'provider' => (string) $provider, 'chat_only' => true, 'docx_only' => true, 'prefer_best_fp' => true ) );
    }
}

if ( ! function_exists( 'agfo_ai_get_best_model' ) ) {
    function agfo_ai_get_best_model( $args = array() ) {
        $models = agfo_ai_get_compatible_models( is_array( $args ) ? $args : array() );
        return ! empty( $models[0] ) ? $models[0] : array();
    }
}

if ( ! function_exists( 'agfo_ai_get_best_fp_model' ) ) {
    function agfo_ai_get_best_fp_model( $provider = '' ) {
        $models = agfo_ai_get_compatible_models( array( 'provider' => (string) $provider, 'chat_only' => true, 'prefer_best_fp' => true ) );
        return ! empty( $models[0] ) ? $models[0] : array();
    }
}

if ( ! function_exists( 'agfo_ai_get_cheapest_compatible_model' ) ) {
    function agfo_ai_get_cheapest_compatible_model( $provider = '' ) {
        $models = agfo_ai_get_compatible_models( array( 'provider' => (string) $provider, 'chat_only' => true, 'prefer_cheapest' => true ) );
        return ! empty( $models[0] ) ? $models[0] : array();
    }
}

if ( ! function_exists( 'agfo_ai_estimate_model_cost' ) ) {
    function agfo_ai_estimate_model_cost( $provider, $model, $input_tokens, $output_tokens ) {
        return class_exists( 'AGFO_AIM_Model_Intelligence' ) ? AGFO_AIM_Model_Intelligence::estimate_cost( (string) $provider, (string) $model, absint( $input_tokens ), absint( $output_tokens ) ) : array( 'label' => 'price_unknown', 'value' => 0, 'source' => 'model_intelligence_missing' );
    }
}

if ( ! function_exists( 'agfo_ai_get_model_recommendation_label' ) ) {
    function agfo_ai_get_model_recommendation_label( $provider, $model ) {
        $intel = agfo_ai_get_model_intelligence( $provider, $model );
        return (string) ( $intel['recommendation_label'] ?? 'Unknown' );
    }
}
