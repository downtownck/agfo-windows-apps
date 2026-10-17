<?php
/**
 * Provider adapter contract.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! interface_exists( 'AGFO_AIM_Adapter_Interface' ) ) {
    interface AGFO_AIM_Adapter_Interface {
        public function provider_code(): string;

        public function supports( string $capability ): bool;

        /**
         * @return true|WP_Error
         */
        public function validate_payload( string $capability, array $payload );

        /**
         * @return array{units:float,unit_name:string,cost:float,currency:string,snapshot:array}
         */
        public function estimate_cost( string $capability, array $payload, array $context = [] ): array;

        /**
         * Dispatches one synchronous provider request.
         *
         * @return array|WP_Error Expected keys: temp_file, mime, bytes, provider_ref, usage, cost_actual.
         */
        public function dispatch( string $capability, array $payload, array $context = [] );
    }
}
