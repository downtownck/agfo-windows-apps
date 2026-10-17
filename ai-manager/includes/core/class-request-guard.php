<?php
/**
 * AGFO AI Manager — central request guard.
 *
 * Added in 17.0.0. Every HTTP request that reaches a managed AI chat endpoint passes
 * through this guard, whether it was sent by agfo_api_post() or by a dependent plugin
 * calling wp_remote_post() directly:
 *
 *  1. http_request_args  — sampling controls are removed for models that only accept the
 *     provider default, parameters the provider has rejected before are removed, and a
 *     model known to be unavailable is swapped for a working fallback.
 *  2. pre_http_request   — OpenAI models that only exist on /v1/responses (pro, codex,
 *     deep-research …) are bridged: the chat body is translated to a Responses body and
 *     the answer is translated back into the Chat Completions shape the caller expects.
 *  3. http_response      — a 400/404/422 is parsed; the rejected parameter, a
 *     responses-only model or an unavailable model is remembered, and the same request is
 *     repaired and sent again once, so even the first failing call returns a success.
 *
 * Capability probes opt out with the X-AGFO-Raw-Probe (or legacy X-AGFO-Temperature-Probe)
 * header so that probe evidence stays genuine.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Request_Guard' ) ) {
    final class AGFO_AIM_Request_Guard {

        const OPTION          = 'agfo_aim_learned_rules';
        const FALLBACK_OPTION = 'agfo_aim_model_fallback_enabled';
        const UNAVAILABLE_TTL = 259200; // 3 days: access to a model can be granted later.
        const MAX_ENTRIES     = 400;
        const MAX_REPAIRS     = 2;

        /** @var int Re-entrancy depth for repair retries inside http_response. */
        private static $depth = 0;

        /** @var array|null Request-scoped copy of the learned rules. */
        private static $rules = null;

        /** @var array<string,string>|null host => provider code. */
        private static $hosts = null;

        /* ── Bootstrap ─────────────────────────────────────── */

        public static function register_hooks(): void {
            add_filter( 'http_request_args', [ __CLASS__, 'filter_request_args' ], 8, 2 );
            add_filter( 'pre_http_request', [ __CLASS__, 'maybe_bridge_request' ], 8, 3 );
            add_filter( 'http_response', [ __CLASS__, 'repair_response' ], 8, 3 );

            add_action( 'wp_ajax_agfo_aim_guard_rules', [ __CLASS__, 'ajax_rules' ] );
            add_action( 'wp_ajax_agfo_aim_guard_reset', [ __CLASS__, 'ajax_reset' ] );
        }

        /* ── Public policy API ─────────────────────────────── */

        /**
         * Parameters that control sampling and may be refused by a model.
         *
         * @return string[]
         */
        public static function sampling_params(): array {
            return [ 'temperature', 'top_p', 'top_k', 'presence_penalty', 'frequency_penalty', 'logprobs', 'top_logprobs', 'logit_bias', 'n', 'seed', 'repetition_penalty', 'min_p' ];
        }

        /**
         * Parameters the guard may drop when a provider names them in a rejection.
         * Anything not listed here (model, messages, tools …) is never removed.
         *
         * @return string[]
         */
        public static function droppable_params(): array {
            return array_merge(
                self::sampling_params(),
                [ 'reasoning_effort', 'reasoning', 'verbosity', 'parallel_tool_calls', 'stream_options', 'service_tier', 'user', 'store', 'metadata', 'prediction', 'modalities', 'audio', 'web_search_options', 'safety_identifier', 'prompt_cache_key', 'topP', 'topK', 'candidateCount', 'presencePenalty', 'frequencyPenalty', 'thinkingConfig', 'max_tokens', 'max_completion_tokens' ]
            );
        }

        /**
         * Effective sampling policy for a model.
         *
         * 'provider_default' — the model only accepts the provider default; sampling
         *                      controls are removed before the request is sent.
         * 'allowed'          — sampling controls are forwarded.
         *
         * OpenAI is deny-by-default: only the classic GPT-4 / GPT-3.5 families, or a
         * model whose genuine live probe said "supported", keep temperature. Any new
         * family (gpt-5.x, o-series, gpt-6 …) is protected the day it appears.
         */
        public static function sampling_policy( string $provider, string $model ): string {
            $provider = sanitize_key( $provider );
            $id       = self::normalize_model( $provider, $model );

            if ( '' === $id ) {
                return 'allowed';
            }

            if ( self::learned_param( $provider, $model, 'temperature' ) ) {
                return 'provider_default';
            }

            $openai_family = ( 'openai' === $provider ) || ( 'openrouter' === $provider && 0 === strpos( strtolower( trim( $model ) ), 'openai/' ) );
            if ( ! $openai_family ) {
                return 'allowed';
            }

            if ( preg_match( '/^(ft:)?(gpt-3\.5|gpt-4|chatgpt-4o)/', $id ) ) {
                return 'allowed';
            }

            // Strict families never get sampling controls, whatever an old probe said.
            if ( 0 === strpos( $id, 'gpt-5' ) || preg_match( '/^o[0-9]+(?:-|$)/', $id ) ) {
                return 'provider_default';
            }

            $status = function_exists( 'agfo_aim_probe_temperature_status' ) ? agfo_aim_probe_temperature_status( $provider, $model ) : 'unknown';
            return ( 'supported' === $status ) ? 'allowed' : 'provider_default';
        }

        /**
         * Which endpoint can actually serve a chat request for this model.
         *
         * @return string 'chat' | 'responses' | 'not_chat' | 'unavailable'
         */
        public static function model_route( string $provider, string $model ): string {
            $provider = sanitize_key( $provider );
            $learned  = self::learned_route( $provider, $model );
            if ( '' !== $learned ) {
                return $learned;
            }

            if ( 'openai' === $provider && self::is_responses_only_name( $model ) ) {
                return 'responses';
            }

            // OpenAI legacy completion-only models (gpt-3.5-turbo-instruct). Open-weight
            // "-instruct" models on other providers are chat models, so this is OpenAI-only.
            if ( 'openai' === $provider && false !== strpos( strtolower( $model ), 'instruct' ) ) {
                return 'not_chat';
            }

            if ( self::is_non_chat_name( $model ) ) {
                return 'not_chat';
            }

            return 'chat';
        }

        /**
         * OpenAI models that are served only by /v1/responses.
         */
        public static function is_responses_only_name( string $model ): bool {
            $id = strtolower( trim( $model ) );
            if ( '' === $id ) {
                return false;
            }
            if ( false !== strpos( $id, 'codex' ) || false !== strpos( $id, 'deep-research' ) || false !== strpos( $id, 'computer-use' ) ) {
                return true;
            }
            // gpt-5-pro, gpt-5.4-pro-2026-03-05, o3-pro, o1-pro …
            return (bool) preg_match( '/(^|-)pro(-|$)/', $id ) && ( 0 === strpos( $id, 'gpt-' ) || preg_match( '/^o[0-9]+/', $id ) );
        }

        /**
         * Model ids that are clearly not text chat models.
         */
        public static function is_non_chat_name( string $model ): bool {
            $id = strtolower( trim( $model ) );
            if ( '' === $id ) {
                return false;
            }
            return (bool) preg_match( '/(^|[\/\-_.])(embed|embedding|whisper|tts|transcribe|dall-e|gpt-image|image-|imagen|sora|veo|moderation|realtime|audio-preview|search-preview|davinci|babbage|lyria|music)/', $id );
        }

        /**
         * A working chat model of the same provider to use instead of $model.
         */
        public static function fallback_model( string $provider, string $model = '' ): string {
            $provider = sanitize_key( $provider );
            $failing  = strtolower( trim( $model ) );

            $candidates = [];
            if ( sanitize_key( (string) get_option( 'agfo_selected_provider', '' ) ) === $provider ) {
                $candidates[] = (string) get_option( 'agfo_global_preferred_model', '' );
            }

            $preferred = [
                'openai'     => [ 'gpt-5-mini', 'gpt-5', 'gpt-4.1', 'gpt-4o' ],
                'openrouter' => [ 'openai/gpt-5-mini', 'openai/gpt-4.1' ],
                'claude'     => [ 'claude-sonnet-4-5', 'claude-sonnet-4-0' ],
                'gemini'     => [ 'gemini-2.5-flash', 'gemini-2.5-pro' ],
            ];
            $list = get_option( 'agfo_models_' . $provider, [] );
            $ids  = [];
            if ( is_array( $list ) ) {
                foreach ( $list as $row ) {
                    $id = is_array( $row ) ? (string) ( $row['id'] ?? $row['name'] ?? '' ) : (string) $row;
                    $id = trim( str_replace( 'models/', '', $id ) );
                    if ( '' !== $id ) {
                        $ids[] = $id;
                    }
                }
            }
            foreach ( $preferred[ $provider ] ?? [] as $p ) {
                if ( in_array( $p, $ids, true ) ) {
                    $candidates[] = $p;
                }
            }
            $candidates = array_merge( $candidates, $ids );

            foreach ( $candidates as $candidate ) {
                $candidate = trim( (string) $candidate );
                if ( '' === $candidate || strtolower( $candidate ) === $failing ) {
                    continue;
                }
                if ( 'chat' === self::model_route( $provider, $candidate ) ) {
                    return (string) apply_filters( 'agfo_ai_fallback_model', $candidate, $provider, $model );
                }
            }
            return (string) apply_filters( 'agfo_ai_fallback_model', '', $provider, $model );
        }

        public static function fallback_enabled(): bool {
            return (bool) apply_filters( 'agfo_ai_model_fallback_enabled', (bool) get_option( self::FALLBACK_OPTION, 1 ) );
        }

        /**
         * Make a decoded request body safe for a provider/model before it is sent.
         * Dependent plugins may call this directly; the HTTP filters call it too.
         *
         * @param string $kind 'chat' | 'responses' | 'claude' | 'gemini'
         * @return array{0:array,1:string[]} [ body, removed parameter names ]
         */
        public static function sanitize_body( string $provider, string $model, array $body, string $kind = 'chat' ): array {
            $provider = sanitize_key( $provider );
            $removed  = [];

            $policy = self::sampling_policy( $provider, $model );
            if ( 'provider_default' === $policy ) {
                foreach ( self::sampling_params() as $param ) {
                    if ( array_key_exists( $param, $body ) ) {
                        unset( $body[ $param ] );
                        $removed[] = $param;
                    }
                }
            }

            // Anthropic rejects temperature and top_p together on current models.
            if ( 'claude' === $kind && array_key_exists( 'temperature', $body ) && array_key_exists( 'top_p', $body ) ) {
                unset( $body['top_p'] );
                $removed[] = 'top_p';
            }

            foreach ( self::learned_params( $provider, $model ) as $param ) {
                if ( 'max_tokens' === $param && array_key_exists( 'max_tokens', $body ) ) {
                    if ( ! isset( $body['max_completion_tokens'] ) ) {
                        $body['max_completion_tokens'] = $body['max_tokens'];
                    }
                    unset( $body['max_tokens'] );
                    $removed[] = 'max_tokens';
                    continue;
                }
                if ( 'max_completion_tokens' === $param && array_key_exists( 'max_completion_tokens', $body ) ) {
                    if ( ! isset( $body['max_tokens'] ) ) {
                        $body['max_tokens'] = $body['max_completion_tokens'];
                    }
                    unset( $body['max_completion_tokens'] );
                    $removed[] = 'max_completion_tokens';
                    continue;
                }
                if ( array_key_exists( $param, $body ) ) {
                    unset( $body[ $param ] );
                    $removed[] = $param;
                }
                if ( isset( $body['generationConfig'] ) && is_array( $body['generationConfig'] ) ) {
                    $gemini_key = self::gemini_key( $param );
                    if ( array_key_exists( $gemini_key, $body['generationConfig'] ) ) {
                        unset( $body['generationConfig'][ $gemini_key ] );
                        $removed[] = 'generationConfig.' . $gemini_key;
                    }
                }
            }

            /**
             * Final say for site-specific rules.
             */
            $body = (array) apply_filters( 'agfo_ai_guard_body', $body, $provider, $model, $kind );

            return [ $body, array_values( array_unique( $removed ) ) ];
        }

        /* ── HTTP filters ──────────────────────────────────── */

        /**
         * http_request_args: clean the body before it leaves WordPress.
         */
        public static function filter_request_args( $args, $url ) {
            if ( ! is_array( $args ) || ! is_string( $url ) || self::is_raw( $args ) ) {
                return $args;
            }
            $endpoint = self::endpoint( $url );
            if ( null === $endpoint ) {
                return $args;
            }
            $body = self::decode_body( $args );
            if ( null === $body ) {
                return $args;
            }

            $model = self::model_from( $endpoint, $body );
            if ( '' === $model ) {
                return $args;
            }

            $original = $body;

            // Swap a model the provider already told us it cannot serve.
            $route = self::model_route( $endpoint['provider'], $model );
            if ( in_array( $route, [ 'unavailable', 'not_chat' ], true ) && self::fallback_enabled() && ! self::header( $args, 'x-agfo-no-model-fallback' ) ) {
                $fallback = self::fallback_model( $endpoint['provider'], $model );
                if ( '' !== $fallback ) {
                    [ $body, $url_unused ] = self::swap_model( $endpoint, $body, $url, $fallback );
                    self::log( 'AGFO_GUARD_MODEL_FALLBACK', [ 'provider' => $endpoint['provider'], 'from' => $model, 'to' => $fallback, 'reason' => $route ] );
                    $model = $fallback;
                }
            }

            [ $body, $removed ] = self::sanitize_body( $endpoint['provider'], $model, $body, $endpoint['kind'] );
            if ( $removed ) {
                self::log( 'AGFO_GUARD_PARAMS_REMOVED', [ 'provider' => $endpoint['provider'], 'model' => $model, 'params' => implode( ',', $removed ) ] );
            }

            // Re-encode only when something changed, and keep empty JSON objects intact.
            if ( $body !== $original ) {
                $args['body'] = self::reencode( (string) $args['body'], $body );
            }
            return $args;
        }

        /**
         * Apply top-level changes of $new to the original JSON text without turning
         * empty objects ({}) into empty arrays ([]), which a plain decode/encode would do
         * and which breaks tool schemas such as "properties": {}.
         */
        public static function reencode( string $raw, array $new ): string {
            $obj = json_decode( $raw );
            if ( ! is_object( $obj ) ) {
                return (string) wp_json_encode( $new );
            }
            foreach ( array_keys( get_object_vars( $obj ) ) as $k ) {
                if ( ! array_key_exists( $k, $new ) ) {
                    unset( $obj->$k );
                    continue;
                }
                $cur = $obj->$k;
                if ( is_object( $cur ) && is_array( $new[ $k ] ) && 'generationConfig' === $k ) {
                    foreach ( array_keys( get_object_vars( $cur ) ) as $gk ) {
                        if ( ! array_key_exists( $gk, $new[ $k ] ) ) {
                            unset( $cur->$gk );
                        }
                    }
                } elseif ( null === $cur || is_scalar( $cur ) ) {
                    $obj->$k = $new[ $k ];
                }
            }
            foreach ( $new as $k => $v ) {
                if ( ! property_exists( $obj, (string) $k ) ) {
                    $obj->$k = $v;
                }
            }
            return (string) wp_json_encode( $obj );
        }

        /**
         * pre_http_request: serve responses-only OpenAI models through /v1/responses,
         * and send Gemini requests whose model was swapped to the right URL.
         */
        public static function maybe_bridge_request( $preempt, $args, $url ) {
            if ( false !== $preempt || ! is_array( $args ) || ! is_string( $url ) || self::is_raw( $args ) ) {
                return $preempt;
            }
            $endpoint = self::endpoint( $url );
            if ( null === $endpoint ) {
                return $preempt;
            }
            $body = self::decode_body( $args );
            if ( null === $body ) {
                return $preempt;
            }

            // Gemini carries the model in the URL; a swapped body model needs a new URL.
            if ( 'gemini' === $endpoint['kind'] && ! empty( $body['__agfo_model'] ) ) {
                $new_model = (string) $body['__agfo_model'];
                unset( $body['__agfo_model'] );
                $new_url       = self::gemini_url_with_model( $url, $new_model );
                $args['body']  = self::reencode( (string) $args['body'], $body );
                return self::send( $new_url, $args );
            }

            if ( 'openai' !== $endpoint['provider'] || 'chat' !== $endpoint['kind'] ) {
                return $preempt;
            }
            $model = (string) ( $body['model'] ?? '' );
            if ( '' === $model || 'responses' !== self::model_route( 'openai', $model ) || ! self::bridgeable( $body ) ) {
                return $preempt;
            }
            if ( ! apply_filters( 'agfo_ai_responses_bridge_enabled', true, $model ) ) {
                return $preempt;
            }

            return self::bridge( $url, $args, $body );
        }

        /**
         * http_response: learn from a refusal and repair the same request once.
         */
        public static function repair_response( $response, $args, $url ) {
            if ( ! is_array( $response ) || ! is_array( $args ) || ! is_string( $url ) || self::is_raw( $args ) ) {
                return $response;
            }
            if ( isset( $args['blocking'] ) && ! $args['blocking'] ) {
                return $response;
            }
            if ( ! empty( $args['stream'] ) ) {
                return $response;
            }
            $code = (int) wp_remote_retrieve_response_code( $response );
            if ( ! in_array( $code, [ 400, 404, 422 ], true ) ) {
                return $response;
            }
            $endpoint = self::endpoint( $url );
            if ( null === $endpoint ) {
                return $response;
            }
            $body = self::decode_body( $args );
            if ( null === $body ) {
                return $response;
            }
            $model = self::model_from( $endpoint, $body );
            if ( '' === $model ) {
                return $response;
            }

            $raw     = (string) wp_remote_retrieve_body( $response );
            $outcome = self::learn( $endpoint['provider'], $model, $code, $raw, $body, $endpoint['kind'] );

            if ( self::$depth >= self::MAX_REPAIRS || 'none' === $outcome['action'] ) {
                return $response;
            }

            self::$depth++;
            try {
                $would_change = false;
                if ( 'strip' === $outcome['action'] ) {
                    [ , $would_remove ] = self::sanitize_body( $endpoint['provider'], $model, $body, $endpoint['kind'] );
                    $would_change       = ! empty( $would_remove );
                }
                if ( 'strip' === $outcome['action'] && ! $would_change ) {
                    // Nothing left to remove: do not resend an identical request.
                    $retry = null;
                } elseif ( 'strip' === $outcome['action'] ) {
                    self::log( 'AGFO_GUARD_REPAIR_RETRY', [ 'provider' => $endpoint['provider'], 'model' => $model, 'params' => implode( ',', $outcome['params'] ), 'http_code' => $code ] );
                    $retry = self::send( $url, $args );
                } elseif ( 'bridge' === $outcome['action'] && self::bridgeable( $body ) ) {
                    self::log( 'AGFO_GUARD_RESPONSES_BRIDGE', [ 'model' => $model, 'trigger' => 'provider_error' ] );
                    $retry = self::bridge( $url, $args, $body );
                } elseif ( 'fallback' === $outcome['action'] && self::fallback_enabled() && ! self::header( $args, 'x-agfo-no-model-fallback' ) ) {
                    $retry = self::send( $url, $args );
                } else {
                    $retry = null;
                }
            } finally {
                self::$depth--;
            }

            if ( is_array( $retry ) && ! is_wp_error( $retry ) ) {
                return $retry;
            }
            return $response;
        }

        /* ── Learning ──────────────────────────────────────── */

        /**
         * Parse a provider refusal and remember what caused it.
         *
         * @return array{action:string,params:string[]} action: strip | bridge | fallback | none
         */
        public static function learn( string $provider, string $model, int $code, string $raw, array $body, string $kind = 'chat' ): array {
            $data    = json_decode( $raw, true );
            $message = '';
            $param   = '';
            $err_code = '';
            if ( is_array( $data ) ) {
                $err = $data['error'] ?? null;
                if ( is_array( $err ) ) {
                    $message  = (string) ( $err['message'] ?? '' );
                    $param    = is_string( $err['param'] ?? null ) ? (string) $err['param'] : '';
                    $err_code = is_string( $err['code'] ?? null ) ? (string) $err['code'] : ( is_string( $err['status'] ?? null ) ? (string) $err['status'] : '' );
                } elseif ( is_string( $err ) ) {
                    $message = $err;
                }
                if ( '' === $message && isset( $data['message'] ) && is_string( $data['message'] ) ) {
                    $message = $data['message'];
                }
                if ( '' === $message && isset( $data['detail'] ) ) {
                    $message = is_string( $data['detail'] ) ? $data['detail'] : wp_json_encode( $data['detail'] );
                }
            }
            if ( '' === $message ) {
                $message = mb_substr( $raw, 0, 600 );
            }
            $lower = strtolower( $message );

            // 1) Model exists only on the Responses API.
            if ( 'openai' === $provider && 'chat' === $kind && ( false !== strpos( $lower, 'v1/responses' ) || preg_match( '/only supported in .{0,40}responses|responses api/i', $message ) ) ) {
                self::remember_route( $provider, $model, 'responses', $message );
                return [ 'action' => 'bridge', 'params' => [] ];
            }

            // OpenAI answers "not a chat model … v1/completions" for pro/codex models too,
            // although they are served by /v1/responses.
            if ( 'openai' === $provider && 'chat' === $kind && self::is_responses_only_name( $model )
                && ( false !== strpos( $lower, 'not a chat model' ) || false !== strpos( $lower, 'v1/completions' ) ) ) {
                self::remember_route( $provider, $model, 'responses', $message );
                return [ 'action' => 'bridge', 'params' => [] ];
            }

            // 2) Not a chat model at all (instruct / completion-only).
            if ( false !== strpos( $lower, 'not a chat model' ) || false !== strpos( $lower, 'v1/completions' ) ) {
                self::remember_route( $provider, $model, 'not_chat', $message );
                return [ 'action' => self::fallback_enabled() && '' !== self::fallback_model( $provider, $model ) ? 'fallback' : 'none', 'params' => [] ];
            }

            // 3) Unknown model or no access.
            if ( 'model_not_found' === $err_code
                || preg_match( '/model[^.]{0,80}(does not exist|not found|is not supported|not available|unknown)|do(es)? not have access to (the )?model|no such model|invalid model|is not found for api version|NOT_FOUND/i', $message )
                || ( 404 === $code && false !== strpos( $lower, 'model' ) ) ) {
                self::remember_route( $provider, $model, 'unavailable', $message );
                return [ 'action' => self::fallback_enabled() && '' !== self::fallback_model( $provider, $model ) ? 'fallback' : 'none', 'params' => [] ];
            }

            // 4) A parameter was refused.
            $refusal = (bool) preg_match( '/unsupported|not supported|does not support|unrecognized|unknown (parameter|field|name|argument)|extra inputs|not permitted|not allowed|invalid (parameter|field|argument)|cannot both be specified|only the default|deprecated|not compatible/i', $message )
                || (bool) preg_match( '/unsupported|unknown|unrecognized/i', $err_code );
            // A value that is merely out of range (e.g. "max_tokens is too large") is not a refusal of
            // the parameter itself; learning it would permanently strip a valid field.
            if ( ! $refusal ) {
                return [ 'action' => 'none', 'params' => [] ];
            }

            $present = array_keys( $body );
            if ( isset( $body['generationConfig'] ) && is_array( $body['generationConfig'] ) ) {
                $present = array_merge( $present, array_keys( $body['generationConfig'] ) );
            }
            $droppable = self::droppable_params();
            $found     = [];

            if ( '' !== $param ) {
                $leaf = preg_replace( '/^.*\./', '', $param );
                if ( in_array( $leaf, $droppable, true ) && in_array( $leaf, $present, true ) ) {
                    $found[] = $leaf;
                }
            }
            if ( $refusal ) {
                foreach ( $present as $p ) {
                    if ( ! in_array( $p, $droppable, true ) ) {
                        continue;
                    }
                    if ( preg_match( '/(^|[^a-z_])' . preg_quote( strtolower( $p ), '/' ) . '([^a-z_]|$)/', $lower ) ) {
                        $found[] = $p;
                    }
                }
            }
            // "temperature and top_p cannot both be specified" — keep temperature.
            if ( in_array( 'temperature', $found, true ) && in_array( 'top_p', $found, true ) && false !== strpos( $lower, 'both' ) ) {
                $found = array_values( array_diff( $found, [ 'temperature' ] ) );
            }
            $found = array_values( array_unique( array_map( [ __CLASS__, 'canonical_param' ], $found ) ) );
            if ( ! $found ) {
                return [ 'action' => 'none', 'params' => [] ];
            }

            foreach ( $found as $p ) {
                self::remember_param( $provider, $model, $p, $message );
            }
            return [ 'action' => 'strip', 'params' => $found ];
        }

        public static function remember_param( string $provider, string $model, string $param, string $note = '' ): void {
            $rules = self::rules();
            $key   = self::key( $provider, $model );
            $rules['params'][ $key ][ $param ] = [ 'at' => time(), 'note' => mb_substr( sanitize_text_field( $note ), 0, 200 ) ];
            self::save( $rules );
        }

        public static function remember_route( string $provider, string $model, string $route, string $note = '' ): void {
            if ( ! in_array( $route, [ 'responses', 'not_chat', 'unavailable', 'chat' ], true ) ) {
                return;
            }
            // OpenAI reports pro/codex models as "not a chat model"; they live on /v1/responses.
            if ( 'not_chat' === $route && 'openai' === sanitize_key( $provider ) && self::is_responses_only_name( $model ) ) {
                $route = 'responses';
            }
            $rules = self::rules();
            $key   = self::key( $provider, $model );
            if ( 'chat' === $route ) {
                unset( $rules['routes'][ $key ] );
            } else {
                $rules['routes'][ $key ] = [ 'route' => $route, 'at' => time(), 'note' => mb_substr( sanitize_text_field( $note ), 0, 200 ) ];
            }
            self::save( $rules );
        }

        /**
         * @return string[] Parameters the provider refused for this model.
         */
        public static function learned_params( string $provider, string $model ): array {
            $rules = self::rules();
            $key   = self::key( $provider, $model );
            return isset( $rules['params'][ $key ] ) && is_array( $rules['params'][ $key ] ) ? array_keys( $rules['params'][ $key ] ) : [];
        }

        public static function learned_param( string $provider, string $model, string $param ): bool {
            return in_array( $param, self::learned_params( $provider, $model ), true );
        }

        public static function learned_route( string $provider, string $model ): string {
            $rules = self::rules();
            $key   = self::key( $provider, $model );
            $row   = $rules['routes'][ $key ] ?? null;
            if ( ! is_array( $row ) ) {
                return '';
            }
            if ( 'unavailable' === ( $row['route'] ?? '' ) && ( time() - (int) ( $row['at'] ?? 0 ) ) > self::UNAVAILABLE_TTL ) {
                return '';
            }
            return (string) ( $row['route'] ?? '' );
        }

        public static function rules(): array {
            if ( null === self::$rules ) {
                $stored      = get_option( self::OPTION, [] );
                self::$rules = is_array( $stored ) ? $stored : [];
            }
            self::$rules += [ 'params' => [], 'routes' => [] ];
            return self::$rules;
        }

        public static function reset(): void {
            self::$rules = [ 'params' => [], 'routes' => [] ];
            delete_option( self::OPTION );
        }

        private static function save( array $rules ): void {
            foreach ( [ 'params', 'routes' ] as $section ) {
                if ( count( $rules[ $section ] ) > self::MAX_ENTRIES ) {
                    $rules[ $section ] = array_slice( $rules[ $section ], -self::MAX_ENTRIES, null, true );
                }
            }
            self::$rules = $rules;
            update_option( self::OPTION, $rules, true );
        }

        /* ── Responses bridge ──────────────────────────────── */

        public static function bridgeable( array $body ): bool {
            if ( ! empty( $body['stream'] ) ) {
                return false;
            }
            if ( ! empty( $body['tools'] ) || ! empty( $body['functions'] ) ) {
                return false;
            }
            if ( empty( $body['messages'] ) || ! is_array( $body['messages'] ) ) {
                return false;
            }
            foreach ( $body['messages'] as $m ) {
                if ( is_array( $m ) && in_array( (string) ( $m['role'] ?? '' ), [ 'tool', 'function' ], true ) ) {
                    return false;
                }
            }
            return true;
        }

        /**
         * Chat Completions body → Responses body.
         */
        public static function chat_to_responses( array $chat ): array {
            $input        = [];
            $instructions = [];

            foreach ( (array) $chat['messages'] as $m ) {
                if ( ! is_array( $m ) ) {
                    continue;
                }
                $role    = (string) ( $m['role'] ?? 'user' );
                $content = $m['content'] ?? '';

                if ( in_array( $role, [ 'system', 'developer' ], true ) ) {
                    $instructions[] = self::flatten_text( $content );
                    continue;
                }
                $role = ( 'assistant' === $role ) ? 'assistant' : 'user';

                if ( is_array( $content ) ) {
                    $parts = [];
                    foreach ( $content as $part ) {
                        if ( ! is_array( $part ) ) {
                            continue;
                        }
                        $type = (string) ( $part['type'] ?? '' );
                        if ( 'text' === $type || 'input_text' === $type || 'output_text' === $type ) {
                            $parts[] = [ 'type' => 'assistant' === $role ? 'output_text' : 'input_text', 'text' => (string) ( $part['text'] ?? '' ) ];
                        } elseif ( 'image_url' === $type && 'user' === $role ) {
                            $url     = is_array( $part['image_url'] ?? null ) ? (string) ( $part['image_url']['url'] ?? '' ) : (string) ( $part['image_url'] ?? '' );
                            $parts[] = [ 'type' => 'input_image', 'image_url' => $url ];
                        }
                    }
                    $input[] = [ 'role' => $role, 'content' => $parts ];
                } else {
                    $input[] = [ 'role' => $role, 'content' => (string) $content ];
                }
            }

            $out = [
                'model' => (string) $chat['model'],
                'input' => $input,
                'store' => false,
            ];
            if ( $instructions ) {
                $out['instructions'] = trim( implode( "\n\n", array_filter( $instructions ) ) );
            }
            $max = $chat['max_completion_tokens'] ?? ( $chat['max_tokens'] ?? null );
            if ( null !== $max ) {
                // Reasoning tokens count against the budget on these models; keep room for the answer.
                $out['max_output_tokens'] = max( 256, (int) $max );
            }
            if ( ! empty( $chat['reasoning_effort'] ) && is_string( $chat['reasoning_effort'] ) ) {
                $out['reasoning'] = [ 'effort' => $chat['reasoning_effort'] ];
            }
            if ( ! empty( $chat['response_format'] ) && is_array( $chat['response_format'] ) ) {
                $rf = $chat['response_format'];
                if ( 'json_schema' === ( $rf['type'] ?? '' ) && is_array( $rf['json_schema'] ?? null ) ) {
                    $out['text'] = [ 'format' => array_merge( [ 'type' => 'json_schema' ], $rf['json_schema'] ) ];
                } elseif ( 'json_object' === ( $rf['type'] ?? '' ) ) {
                    $out['text'] = [ 'format' => [ 'type' => 'json_object' ] ];
                }
            }
            if ( isset( $chat['metadata'] ) && is_array( $chat['metadata'] ) ) {
                $out['metadata'] = $chat['metadata'];
            }
            return $out;
        }

        /**
         * Responses answer → Chat Completions answer.
         */
        public static function responses_to_chat( array $resp, string $model ): array {
            $text = '';
            foreach ( (array) ( $resp['output'] ?? [] ) as $item ) {
                if ( ! is_array( $item ) || 'message' !== ( $item['type'] ?? '' ) ) {
                    continue;
                }
                foreach ( (array) ( $item['content'] ?? [] ) as $c ) {
                    if ( is_array( $c ) && in_array( (string) ( $c['type'] ?? '' ), [ 'output_text', 'text' ], true ) ) {
                        $text .= (string) ( $c['text'] ?? '' );
                    }
                }
            }
            if ( '' === $text && isset( $resp['output_text'] ) && is_string( $resp['output_text'] ) ) {
                $text = $resp['output_text'];
            }
            $usage  = is_array( $resp['usage'] ?? null ) ? $resp['usage'] : [];
            $in     = (int) ( $usage['input_tokens'] ?? 0 );
            $outtok = (int) ( $usage['output_tokens'] ?? 0 );
            $finish = ( 'incomplete' === ( $resp['status'] ?? '' ) ) ? 'length' : 'stop';

            return [
                'id'      => (string) ( $resp['id'] ?? ( 'agfo-bridge-' . wp_generate_password( 10, false, false ) ) ),
                'object'  => 'chat.completion',
                'created' => (int) ( $resp['created_at'] ?? time() ),
                'model'   => (string) ( $resp['model'] ?? $model ),
                'choices' => [
                    [
                        'index'         => 0,
                        'message'       => [ 'role' => 'assistant', 'content' => $text ],
                        'finish_reason' => $finish,
                    ],
                ],
                'usage'   => [
                    'prompt_tokens'     => $in,
                    'completion_tokens' => $outtok,
                    'total_tokens'      => (int) ( $usage['total_tokens'] ?? ( $in + $outtok ) ),
                ],
                'agfo_transport' => 'responses_bridge',
            ];
        }

        private static function bridge( string $url, array $args, array $chat ) {
            $resp_url = preg_replace( '#/chat/completions/?$#', '/responses', $url );
            $payload  = self::chat_to_responses( $chat );
            [ $payload ] = self::sanitize_body( 'openai', (string) $chat['model'], $payload, 'responses' );

            $bridged         = $args;
            $bridged['body'] = wp_json_encode( $payload );
            // Responses models think before answering; give them room.
            $bridged['timeout'] = max( (int) ( $args['timeout'] ?? 60 ), 240 );

            $result = self::send( $resp_url, $bridged );
            if ( is_wp_error( $result ) || ! is_array( $result ) ) {
                return $result;
            }
            $code = (int) wp_remote_retrieve_response_code( $result );
            if ( $code < 200 || $code >= 300 ) {
                return $result;
            }
            $decoded = json_decode( (string) wp_remote_retrieve_body( $result ), true );
            if ( ! is_array( $decoded ) ) {
                return $result;
            }
            $result['body'] = wp_json_encode( self::responses_to_chat( $decoded, (string) $chat['model'] ) );
            self::log( 'AGFO_GUARD_RESPONSES_BRIDGE_DONE', [ 'model' => (string) $chat['model'], 'http_code' => $code ] );
            return $result;
        }

        /* ── Helpers ───────────────────────────────────────── */

        /**
         * Identify a managed chat endpoint.
         *
         * @return array{provider:string,kind:string}|null
         */
        public static function endpoint( string $url ): ?array {
            $host = strtolower( (string) wp_parse_url( $url, PHP_URL_HOST ) );
            $path = strtolower( (string) wp_parse_url( $url, PHP_URL_PATH ) );
            if ( '' === $host ) {
                return null;
            }
            $hosts = self::hosts();
            if ( ! isset( $hosts[ $host ] ) ) {
                return null;
            }
            $provider = $hosts[ $host ];

            if ( false !== strpos( $path, '/chat/completions' ) ) {
                $kind = 'chat';
            } elseif ( preg_match( '#/v1/responses/?$#', $path ) ) {
                $kind = 'responses';
            } elseif ( preg_match( '#/v1/messages/?$#', $path ) ) {
                $kind = 'claude';
            } elseif ( false !== strpos( $path, ':generatecontent' ) ) {
                $kind = 'gemini';
            } else {
                return null;
            }
            return [ 'provider' => $provider, 'kind' => $kind, 'url' => $url ];
        }

        private static function hosts(): array {
            if ( null !== self::$hosts ) {
                return self::$hosts;
            }
            self::$hosts = [];
            $registry    = function_exists( 'agfo_api_registry' ) ? agfo_api_registry() : [];
            foreach ( $registry as $code => $info ) {
                if ( ( $info['type'] ?? 'llm' ) !== 'llm' || empty( $info['chat_url'] ) ) {
                    continue;
                }
                $template = str_replace( [ '{key}', '{model}' ], [ 'k', 'm' ], (string) $info['chat_url'] );
                $host     = strtolower( (string) wp_parse_url( $template, PHP_URL_HOST ) );
                if ( '' !== $host && ! isset( self::$hosts[ $host ] ) ) {
                    self::$hosts[ $host ] = (string) $code;
                }
            }
            return self::$hosts;
        }

        private static function model_from( array $endpoint, array $body ): string {
            if ( 'gemini' === $endpoint['kind'] ) {
                if ( preg_match( '#/models/([^/:]+):#i', (string) wp_parse_url( $endpoint['url'], PHP_URL_PATH ), $m ) ) {
                    return rawurldecode( $m[1] );
                }
                return '';
            }
            return isset( $body['model'] ) && is_string( $body['model'] ) ? trim( $body['model'] ) : '';
        }

        private static function swap_model( array $endpoint, array $body, string $url, string $model ): array {
            if ( 'gemini' === $endpoint['kind'] ) {
                $body['__agfo_model'] = $model;
            } else {
                $body['model'] = $model;
            }
            return [ $body, $url ];
        }

        private static function gemini_url_with_model( string $url, string $model ): string {
            return (string) preg_replace( '#(/models/)[^/:]+(:)#i', '${1}' . rawurlencode( str_replace( 'models/', '', $model ) ) . '${2}', $url, 1 );
        }

        private static function decode_body( array $args ): ?array {
            $body = $args['body'] ?? null;
            if ( ! is_string( $body ) || '' === $body || '{' !== substr( ltrim( $body ), 0, 1 ) ) {
                return null;
            }
            $decoded = json_decode( $body, true );
            return is_array( $decoded ) ? $decoded : null;
        }

        private static function is_raw( array $args ): bool {
            return self::header( $args, 'x-agfo-raw-probe' ) || self::header( $args, 'x-agfo-temperature-probe' );
        }

        private static function header( array $args, string $name ): bool {
            $headers = isset( $args['headers'] ) && is_array( $args['headers'] ) ? $args['headers'] : [];
            foreach ( $headers as $k => $v ) {
                if ( strtolower( (string) $k ) === $name && '1' === (string) $v ) {
                    return true;
                }
            }
            return false;
        }

        private static function send( string $url, array $args ) {
            $method = strtoupper( (string) ( $args['method'] ?? 'POST' ) );
            $args['method'] = $method;
            $runner = static function () use ( $url, $args ) {
                return wp_remote_request( $url, $args );
            };
            return function_exists( 'agfo_ai_manager_without_connector_guard' ) && function_exists( 'agfo_ai_manager_connector_guard_callbacks' ) && agfo_ai_manager_connector_guard_callbacks()
                ? agfo_ai_manager_without_connector_guard( $runner )
                : $runner();
        }

        private static function normalize_model( string $provider, string $model ): string {
            $id = strtolower( trim( str_replace( 'models/', '', $model ) ) );
            if ( 'openrouter' === $provider && false !== strpos( $id, '/' ) ) {
                $id = substr( $id, strpos( $id, '/' ) + 1 );
            }
            return $id;
        }

        private static function key( string $provider, string $model ): string {
            return sanitize_key( $provider ) . '|' . strtolower( trim( str_replace( 'models/', '', $model ) ) );
        }

        private static function canonical_param( string $param ): string {
            $map = [ 'topP' => 'top_p', 'topK' => 'top_k', 'presencePenalty' => 'presence_penalty', 'frequencyPenalty' => 'frequency_penalty' ];
            return $map[ $param ] ?? $param;
        }

        private static function gemini_key( string $param ): string {
            $map = [ 'top_p' => 'topP', 'top_k' => 'topK', 'presence_penalty' => 'presencePenalty', 'frequency_penalty' => 'frequencyPenalty' ];
            return $map[ $param ] ?? $param;
        }

        private static function flatten_text( $content ): string {
            if ( is_string( $content ) ) {
                return $content;
            }
            $text = '';
            foreach ( (array) $content as $part ) {
                if ( is_array( $part ) && isset( $part['text'] ) && is_string( $part['text'] ) ) {
                    $text .= $part['text'];
                }
            }
            return $text;
        }

        private static function log( string $stage, array $context ): void {
            if ( function_exists( 'agfo_ai_manager_log_transport' ) ) {
                agfo_ai_manager_log_transport( $stage, $context );
            }
        }

        /* ── Admin AJAX ────────────────────────────────────── */

        public static function ajax_rules(): void {
            if ( ! current_user_can( 'manage_options' ) ) {
                wp_send_json_error( [ 'message' => 'Yetki yok.' ], 403 );
            }
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );

            $rules = self::rules();
            $rows  = [];
            foreach ( $rules['params'] as $key => $params ) {
                [ $provider, $model ] = array_pad( explode( '|', (string) $key, 2 ), 2, '' );
                foreach ( (array) $params as $param => $meta ) {
                    $rows[] = [ 'provider' => $provider, 'model' => $model, 'rule' => 'param', 'value' => (string) $param, 'at' => (int) ( $meta['at'] ?? 0 ) ];
                }
            }
            foreach ( $rules['routes'] as $key => $meta ) {
                [ $provider, $model ] = array_pad( explode( '|', (string) $key, 2 ), 2, '' );
                $rows[] = [ 'provider' => $provider, 'model' => $model, 'rule' => 'route', 'value' => (string) ( $meta['route'] ?? '' ), 'at' => (int) ( $meta['at'] ?? 0 ) ];
            }
            usort( $rows, static function ( $a, $b ) {
                return $b['at'] <=> $a['at'];
            } );
            wp_send_json_success( [ 'rules' => $rows, 'fallback' => self::fallback_enabled() ] );
        }

        public static function ajax_reset(): void {
            if ( ! current_user_can( 'manage_options' ) ) {
                wp_send_json_error( [ 'message' => 'Yetki yok.' ], 403 );
            }
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );

            if ( isset( $_POST['fallback'] ) ) {
                update_option( self::FALLBACK_OPTION, ! empty( $_POST['fallback'] ) ? 1 : 0, true );
                wp_send_json_success( [ 'fallback' => self::fallback_enabled() ] );
            }
            self::reset();
            wp_send_json_success( [ 'rules' => [] ] );
        }
    }
}
