<?php
/**
 * AGFO AI Manager — model catalogue intelligence.
 *
 * Added in 17.1.0.
 *  - Keeps the metadata a provider's /models endpoint returns (release time, prices,
 *    context window, output modalities), which the refresh used to throw away.
 *  - Gives every model a recency key (release time, date in the id, version number) so
 *    lists can show the newest models first without a code change when gpt-5.7 ships.
 *  - Builds the Translation and Image boards of AI Kontrol Merkezi: quality against
 *    price across every provider that has an API key.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Model_Catalog' ) ) {
    final class AGFO_AIM_Model_Catalog {

        const META_SUFFIX = '_meta';

        /** Translation cost assumptions per 1,000 source words (TR ⇄ EN). */
        const WORDS_INPUT_TOKENS  = 1700; // source text + instructions
        const WORDS_OUTPUT_TOKENS = 1900; // translated text
        const REASONING_OVERHEAD  = 1.4;  // hidden reasoning tokens at low effort

        /** @var array<string,array> */
        private static $meta_cache = [];

        public static function register_hooks(): void {
            add_action( 'wp_ajax_agfo_aim_board_translation', [ __CLASS__, 'ajax_translation_board' ] );
            add_action( 'wp_ajax_agfo_aim_board_image', [ __CLASS__, 'ajax_image_board' ] );
            add_action( 'wp_ajax_agfo_aim_set_translation_model', [ __CLASS__, 'ajax_set_translation_model' ] );
            add_action( 'wp_ajax_agfo_aim_set_image_model', [ __CLASS__, 'ajax_set_image_model' ] );
            add_action( 'wp_ajax_agfo_aim_set_image_price', [ __CLASS__, 'ajax_set_image_price' ] );
        }

        /* ── Metadata capture ──────────────────────────────── */

        /**
         * Store release time, prices and modalities from a raw /models response list.
         *
         * @param array $raw_list Items of data[] / models[] exactly as the provider returned them.
         */
        public static function capture_meta( string $provider, array $raw_list ): void {
            $provider = sanitize_key( $provider );
            $meta     = [];

            foreach ( $raw_list as $item ) {
                if ( ! is_array( $item ) ) {
                    continue;
                }
                $id = (string) ( $item['id'] ?? $item['name'] ?? $item['model'] ?? '' );
                $id = trim( $id );
                if ( '' === $id ) {
                    continue;
                }
                $row = [];

                // Release time: OpenAI/OpenRouter/Together "created" (unix), Anthropic "created_at" (ISO).
                if ( isset( $item['created'] ) && is_numeric( $item['created'] ) && (int) $item['created'] > 946684800 ) {
                    $row['released'] = (int) $item['created'];
                } elseif ( ! empty( $item['created_at'] ) && is_string( $item['created_at'] ) ) {
                    $ts = strtotime( $item['created_at'] );
                    if ( $ts ) {
                        $row['released'] = (int) $ts;
                    }
                }

                // Prices, normalised to USD per 1M tokens.
                if ( isset( $item['pricing'] ) && is_array( $item['pricing'] ) ) {
                    $p = $item['pricing'];
                    if ( isset( $p['prompt'] ) && is_numeric( $p['prompt'] ) ) {          // OpenRouter: USD per token.
                        $row['in']  = round( (float) $p['prompt'] * 1000000, 4 );
                        $row['out'] = isset( $p['completion'] ) && is_numeric( $p['completion'] ) ? round( (float) $p['completion'] * 1000000, 4 ) : null;
                        if ( isset( $p['image'] ) && is_numeric( $p['image'] ) && (float) $p['image'] > 0 ) {
                            $row['image'] = (float) $p['image'];
                        }
                    } elseif ( isset( $p['input'] ) && is_numeric( $p['input'] ) ) {     // Together: USD per 1M.
                        $row['in']  = (float) $p['input'];
                        $row['out'] = isset( $p['output'] ) && is_numeric( $p['output'] ) ? (float) $p['output'] : null;
                    }
                    $row['price_source'] = 'provider_api';
                }

                $ctx = $item['context_length'] ?? ( $item['inputTokenLimit'] ?? ( $item['context_window'] ?? null ) );
                if ( is_numeric( $ctx ) ) {
                    $row['context'] = (int) $ctx;
                }
                $out_mod = $item['architecture']['output_modalities'] ?? null;
                if ( is_array( $out_mod ) ) {
                    $row['out_modalities'] = array_values( array_map( 'strval', $out_mod ) );
                }

                if ( $row ) {
                    $meta[ $id ] = $row;
                }
            }

            update_option( 'agfo_models_' . $provider . self::META_SUFFIX, $meta, false );
            self::$meta_cache[ $provider ] = $meta;
        }

        public static function meta( string $provider ): array {
            $provider = sanitize_key( $provider );
            if ( ! isset( self::$meta_cache[ $provider ] ) ) {
                $stored                        = get_option( 'agfo_models_' . $provider . self::META_SUFFIX, [] );
                self::$meta_cache[ $provider ] = is_array( $stored ) ? $stored : [];
            }
            return self::$meta_cache[ $provider ];
        }

        public static function model_meta( string $provider, string $model ): array {
            $meta = self::meta( $provider );
            if ( isset( $meta[ $model ] ) ) {
                return $meta[ $model ];
            }
            $alt = 0 === strpos( $model, 'models/' ) ? substr( $model, 7 ) : 'models/' . $model;
            return $meta[ $alt ] ?? [];
        }

        /* ── Recency ───────────────────────────────────────── */

        /**
         * Family version from a model id: gpt-5.6-sol → 5.6, claude-opus-4-5-20251101 → 4.5,
         * gemini-2.5-flash → 2.5, o3-mini → 3. Dates (4+ digits) are never read as versions.
         */
        public static function version_key( string $model ): float {
            $id = strtolower( trim( $model ) );
            $id = preg_replace( '#^models/#', '', $id );
            if ( false !== strpos( $id, '/' ) ) {
                $id = substr( $id, strrpos( $id, '/' ) + 1 );
            }
            if ( preg_match( '/(?<![0-9])([0-9]{1,2})(?:[.\-]([0-9]{1,2}))?(?![0-9])/', $id, $m ) ) {
                $major = (int) $m[1];
                $minor = isset( $m[2] ) && '' !== $m[2] ? (int) $m[2] : 0;
                // 5.9 → 5.09 and 5.10 → 5.10, so gpt-5.10 sorts above gpt-5.9.
                return $major + ( $minor / 100 );
            }
            return 0.0;
        }

        /**
         * Release time: provider metadata first, then a date embedded in the id.
         */
        public static function release_ts( string $provider, string $model ): int {
            $meta = self::model_meta( $provider, $model );
            if ( ! empty( $meta['released'] ) ) {
                return (int) $meta['released'];
            }
            $id = strtolower( $model );
            if ( preg_match( '/(20[2-3][0-9])-?([01][0-9])-?([0-3][0-9])/', $id, $m ) && checkdate( (int) $m[2], (int) $m[3], (int) $m[1] ) ) {
                return (int) gmmktime( 0, 0, 0, (int) $m[2], (int) $m[3], (int) $m[1] );
            }
            if ( preg_match( '/(?<![0-9])([01][0-9])-(20[2-3][0-9])(?![0-9])/', $id, $m ) && (int) $m[1] >= 1 && (int) $m[1] <= 12 ) {
                return (int) gmmktime( 0, 0, 0, (int) $m[1], 1, (int) $m[2] );
            }
            return 0;
        }

        /**
         * Add 'released', 'version' and 'is_new' to a list of normalised model rows.
         * A model is new when it was released in the last 60 days, or — when release
         * times are unknown — when it belongs to the highest version family of its brand.
         */
        public static function annotate_recency( string $provider, array $rows ): array {
            $max_by_brand = [];
            foreach ( $rows as $i => $row ) {
                $id                    = (string) ( $row['id'] ?? '' );
                $rows[ $i ]['released'] = self::release_ts( $provider, $id );
                $rows[ $i ]['version']  = self::version_key( $id );
                $brand                 = self::brand( $id );
                $max_by_brand[ $brand ] = max( $max_by_brand[ $brand ] ?? 0.0, $rows[ $i ]['version'] );
            }
            $cutoff = time() - 60 * DAY_IN_SECONDS;
            foreach ( $rows as $i => $row ) {
                $brand = self::brand( (string) ( $row['id'] ?? '' ) );
                if ( $row['released'] > 0 ) {
                    $rows[ $i ]['is_new'] = $row['released'] >= $cutoff;
                } else {
                    $rows[ $i ]['is_new'] = $row['version'] > 0 && abs( $row['version'] - ( $max_by_brand[ $brand ] ?? 0 ) ) < 0.001;
                }
            }
            return $rows;
        }

        /**
         * Sort newest first: release time when every row has one, otherwise version, then date.
         */
        public static function sort_newest( array $rows ): array {
            $all_dated = ! empty( $rows ) && count( array_filter( $rows, static function ( $r ) { return ! empty( $r['released'] ); } ) ) === count( $rows );
            usort( $rows, static function ( $a, $b ) use ( $all_dated ) {
                if ( $all_dated ) {
                    return ( $b['released'] <=> $a['released'] ) ?: strcmp( (string) $a['id'], (string) $b['id'] );
                }
                return ( $b['version'] <=> $a['version'] ) ?: ( $b['released'] <=> $a['released'] ) ?: strcmp( (string) $a['id'], (string) $b['id'] );
            } );
            return $rows;
        }

        public static function brand( string $model ): string {
            $id = strtolower( preg_replace( '#^models/#', '', $model ) );
            if ( false !== strpos( $id, '/' ) ) {
                $id = substr( $id, strpos( $id, '/' ) + 1 );
            }
            // o-series belongs to OpenAI's GPT line-up: o4-mini is not "new" next to gpt-5.7.
            if ( preg_match( '/^o[0-9]/', $id ) || 0 === strpos( $id, 'chatgpt' ) ) {
                return 'gpt';
            }
            return (string) preg_replace( '/[^a-z].*$/', '', $id ) ?: 'other';
        }

        /* ── Prices ────────────────────────────────────────── */

        /**
         * USD per 1M input/output tokens from the best available source.
         *
         * @return array{in:?float,out:?float,source:string}
         */
        public static function token_price( string $provider, string $model ): array {
            $meta = self::model_meta( $provider, $model );
            if ( isset( $meta['in'] ) && null !== $meta['in'] ) {
                return [ 'in' => (float) $meta['in'], 'out' => isset( $meta['out'] ) ? (float) $meta['out'] : (float) $meta['in'], 'source' => 'Sağlayıcı API' ];
            }

            $data  = function_exists( 'agfo_read_data_json' ) ? agfo_read_data_json() : [];
            $intel = $data['model_intelligence'][ $provider ][ $model ] ?? [];
            if ( isset( $intel['input_price_per_1m'], $intel['output_price_per_1m'] ) && is_numeric( $intel['input_price_per_1m'] ) && is_numeric( $intel['output_price_per_1m'] ) ) {
                return [ 'in' => (float) $intel['input_price_per_1m'], 'out' => (float) $intel['output_price_per_1m'], 'source' => 'Model Intelligence' ];
            }

            $rank = self::ranking_row( $data, $provider, $model );
            if ( ! empty( $rank['price_label'] ) && preg_match( '/\$\s*([0-9.]+)\s*\/\s*\$\s*([0-9.]+)/', (string) $rank['price_label'], $m ) ) {
                return [ 'in' => (float) $m[1], 'out' => (float) $m[2], 'source' => 'AGFO sıralama tablosu' ];
            }
            if ( isset( $rank['input_price'] ) && is_numeric( $rank['input_price'] ) ) {
                return [ 'in' => (float) $rank['input_price'], 'out' => (float) $rank['input_price'] * 4, 'source' => 'AGFO sıralama tablosu (çıktı tahmini)' ];
            }
            return [ 'in' => null, 'out' => null, 'source' => '' ];
        }

        private static function ranking_row( array $data, string $provider, string $model ): array {
            $rankings = $data['rankings'][ $provider ] ?? [];
            if ( ! is_array( $rankings ) ) {
                return [];
            }
            if ( isset( $rankings[ $model ] ) ) {
                return (array) $rankings[ $model ];
            }
            // Dated snapshot (gpt-5.4-2026-03-05) inherits its alias (gpt-5.4).
            $alias = preg_replace( '/-(20[2-3][0-9]-[01][0-9]-[0-3][0-9]|[0-9]{8})$/', '', $model );
            return isset( $rankings[ $alias ] ) ? (array) $rankings[ $alias ] : [];
        }

        /* ── Quality ───────────────────────────────────────── */

        /**
         * Benchmark quality (0–100) from the plugin's benchmark table, matched on the longest
         * known key so gpt-5.4-nano never inherits gpt-5's score. Falls back to the AGFO
         * assistant score minus 8 (flagged as an estimate) when no benchmark matches.
         *
         * @return array{score:int,source:string,key:string}
         */
        public static function quality( string $provider, string $model, int $fallback = 0 ): array {
            $known = function_exists( 'agfo_get_known_benchmarks' ) ? agfo_get_known_benchmarks() : [];
            $id    = strtolower( trim( preg_replace( '#^models/#', '', $model ) ) );
            if ( false !== strpos( $id, '/' ) ) {
                $id = substr( $id, strrpos( $id, '/' ) + 1 );
            }
            $id = preg_replace( '/-(20[2-3][0-9]-?[01][0-9]-?[0-3][0-9])$/', '', $id );
            $id = preg_replace( '/-(preview|latest|exp|instruct)(-.*)?$/', '', $id );

            $best = '';
            foreach ( array_keys( $known ) as $key ) {
                $k = strtolower( (string) $key );
                if ( ( $id === $k || 0 === strpos( $id, $k . '-' ) || 0 === strpos( $id, $k . '.' ) || ( strlen( $k ) > 6 && false !== strpos( $id, $k ) ) ) && strlen( $k ) > strlen( $best ) ) {
                    $best = $k;
                }
            }
            if ( '' !== $best && function_exists( 'agfo_calculate_combined_score' ) ) {
                $exact = null;
                foreach ( array_keys( $known ) as $key ) {
                    if ( strtolower( (string) $key ) === $best ) {
                        $exact = (string) $key;
                        break;
                    }
                }
                $combined = agfo_calculate_combined_score( $provider, (string) $exact );
                if ( is_array( $combined ) && isset( $combined['final_score'] ) ) {
                    return [ 'score' => (int) $combined['final_score'], 'source' => 'benchmark', 'key' => (string) $exact ];
                }
            }
            return [ 'score' => max( 0, $fallback - 8 ), 'source' => 'estimate', 'key' => '' ];
        }

        /* ── Translation board ─────────────────────────────── */

        /**
         * Chat models of every keyed provider, scored for translation value.
         *
         * Quality is the AGFO model score (0–100). Cost is an estimate for translating
         * 1,000 source words; reasoning models carry a hidden-token overhead.
         * Value = quality points above 60 per dollar of that cost.
         */
        public static function translation_board( int $min_quality = 85, string $scope = 'all' ): array {
            $providers = [];
            $registry  = function_exists( 'agfo_api_registry' ) ? agfo_api_registry() : [];
            foreach ( $registry as $code => $info ) {
                if ( ( $info['type'] ?? 'llm' ) !== 'llm' || empty( agfo_get_api_key( $code ) ) ) {
                    continue;
                }
                $providers[ $code ] = (string) ( $info['label'] ?? $code );
            }
            if ( 'selected' === $scope ) {
                $sel       = (string) get_option( 'agfo_selected_provider', 'openai' );
                $providers = isset( $providers[ $sel ] ) ? [ $sel => $providers[ $sel ] ] : [];
            }

            $rows = [];
            foreach ( $providers as $code => $label ) {
                $models = class_exists( 'AGFO_AIM_Ajax_Data' ) ? AGFO_AIM_Ajax_Data::models_for_provider( $code ) : [];
                foreach ( $models as $m ) {
                    $id = (string) ( $m['id'] ?? '' );
                    if ( '' === $id || ! self::is_translation_candidate( $code, $id, $m ) ) {
                        continue;
                    }
                    $q         = self::quality( $code, $id, (int) ( $m['rank_score'] ?? 0 ) );
                    $quality   = $q['score'];
                    $price     = self::token_price( $code, $id );
                    $reasoning = function_exists( 'agfo_openai_model_is_reasoning' ) && agfo_openai_model_is_reasoning( preg_replace( '#^[^/]+/#', '', $id ) );
                    $cost      = null;
                    if ( null !== $price['in'] ) {
                        $out_tokens = self::WORDS_OUTPUT_TOKENS * ( $reasoning ? self::REASONING_OVERHEAD : 1 );
                        $cost       = round( ( $price['in'] * self::WORDS_INPUT_TOKENS + $price['out'] * $out_tokens ) / 1000000, 5 );
                    }
                    $value = ( null !== $cost && $cost > 0 ) ? round( max( 0, $quality - 60 ) / $cost, 1 ) : null;

                    $rows[] = [
                        'provider'       => $code,
                        'provider_label' => $label,
                        'id'             => $id,
                        'quality'        => $quality,
                        'tier'           => function_exists( 'agfo_score_to_tier' ) ? agfo_score_to_tier( $quality ) : (string) ( $m['tier'] ?? '' ),
                        'quality_source' => $q['source'],
                        'quality_key'    => $q['key'],
                        'in'             => $price['in'],
                        'out'            => $price['out'],
                        'price_source'   => $price['source'],
                        'cost_1k_words'  => $cost,
                        'value'          => $value,
                        'reasoning'      => $reasoning,
                        'speed_score'    => isset( $m['speed_score'] ) && is_numeric( $m['speed_score'] ) ? (int) $m['speed_score'] : null, // NEW 17.8.0
                        'route'          => (string) ( $m['transport_route'] ?? 'chat' ),
                        'is_new'         => ! empty( $m['is_new'] ),
                        'eligible'       => $quality >= $min_quality && null !== $cost,
                    ];
                }
            }

            // Dated snapshots (gpt-5-mini-2025-08-07) duplicate their alias; keep the alias.
            $seen = [];
            usort( $rows, static function ( $a, $b ) { return strlen( $a['id'] ) <=> strlen( $b['id'] ); } );
            $rows = array_values( array_filter( $rows, static function ( $r ) use ( &$seen ) {
                $base = $r['provider'] . '|' . preg_replace( '/-(20[2-3][0-9]-?[01][0-9]-?[0-3][0-9])$/', '', $r['id'] );
                if ( isset( $seen[ $base ] ) ) {
                    return false;
                }
                $seen[ $base ] = true;
                return true;
            } ) );

            usort( $rows, static function ( $a, $b ) {
                if ( $a['eligible'] !== $b['eligible'] ) {
                    return $a['eligible'] ? -1 : 1;
                }
                if ( null === $a['value'] || null === $b['value'] ) {
                    return ( null === $a['value'] ? 1 : 0 ) - ( null === $b['value'] ? 1 : 0 ) ?: $b['quality'] <=> $a['quality'];
                }
                return $b['value'] <=> $a['value'] ?: $b['quality'] <=> $a['quality'];
            } );

            $eligible = array_values( array_filter( $rows, static function ( $r ) { return $r['eligible']; } ) );
            $picks    = [ 'value' => null, 'quality' => null, 'cheapest' => null ];
            if ( $eligible ) {
                $picks['value'] = $eligible[0];
                $by_quality     = $eligible;
                usort( $by_quality, static function ( $a, $b ) { return $b['quality'] <=> $a['quality'] ?: $a['cost_1k_words'] <=> $b['cost_1k_words']; } );
                $picks['quality'] = $by_quality[0];
                $by_cost          = $eligible;
                usort( $by_cost, static function ( $a, $b ) { return $a['cost_1k_words'] <=> $b['cost_1k_words'] ?: $b['quality'] <=> $a['quality']; } );
                $picks['cheapest'] = $by_cost[0];
            }

            return [
                'rows'        => array_slice( $rows, 0, 120 ),
                'total'       => count( $rows ),
                'eligible'    => count( $eligible ),
                'picks'       => $picks,
                'current'     => self::translation_route(),
                'route_error' => self::translation_route_error(),
                'assumptions' => [
                    'input_tokens'       => self::WORDS_INPUT_TOKENS,
                    'output_tokens'      => self::WORDS_OUTPUT_TOKENS,
                    'reasoning_overhead' => self::REASONING_OVERHEAD,
                    'min_quality'        => $min_quality,
                ],
            ];
        }

        private static function is_translation_candidate( string $provider, string $id, array $m ): bool {
            if ( empty( $m['supports_chat'] ) ) {
                return false;
            }
            $route = (string) ( $m['transport_route'] ?? 'chat' );
            if ( in_array( $route, [ 'unavailable', 'not_chat' ], true ) ) {
                return false;
            }
            // Coding, search, guard and media-oriented variants are not translation models.
            return ! preg_match( '/codex|coder|search|guard|embed|vision|image|audio|tts|realtime|transcribe|ocr|math|moderation/i', $id );
        }

        /** NEW 17.7.0: last failure of the current Çeviri route (the editor then fell back to the default model). */
        public static function translation_route_error(): ?array {
            $err = get_option( 'agfo_aim_translation_route_error' );
            $cur = self::translation_route();
            if ( ! is_array( $err ) || ( $err['model'] ?? '' ) !== $cur['model'] ) {
                return null;
            }
            return [ 'model' => (string) $err['model'], 'message' => (string) ( $err['message'] ?? '' ), 'time' => (int) ( $err['time'] ?? 0 ) ];
        }

        public static function translation_route(): array {
            $routing = function_exists( 'agfo_get_capability_routing' ) ? agfo_get_capability_routing() : [];
            $route   = $routing['text_translate'] ?? [ 'provider' => '', 'model' => '' ];
            return [ 'provider' => (string) ( $route['provider'] ?? '' ), 'model' => (string) ( $route['model'] ?? '' ) ];
        }

        /* ── Image board ───────────────────────────────────── */

        /**
         * Editorial notes for known image model families: [tier, strengths].
         * Tier A = current flagship quality, B = solid, C = previous generation.
         */
        public static function image_notes( string $id ): array {
            $l = strtolower( $id );
            $map = [
                '/gpt-image-2|gpt-5\.[0-9]+-image/' => [ 'A', [ 'Yazı ve tipografi', 'Prompta sadakat' ] ],
                '/gpt-image-1/'                      => [ 'B', [ 'Yazı ve tipografi', 'Prompta sadakat' ] ],
                '/imagen-4.*ultra/'                  => [ 'A', [ 'Fotogerçekçi', 'Yüksek ayrıntı' ] ],
                '/imagen-4/'                         => [ 'A', [ 'Fotogerçekçi' ] ],
                '/imagen-3/'                         => [ 'B', [ 'Fotogerçekçi' ] ],
                '/gemini-3.*image|pro-image/'        => [ 'A', [ 'Yazı ve tipografi', 'Düzenleme' ] ],
                '/gemini.*image|flash-image/'        => [ 'B', [ 'Hızlı', 'Düzenleme' ] ],
                '/flux-pro.*ultra|flux.*ultra/'      => [ 'A', [ 'Fotogerçekçi', 'Yüksek çözünürlük' ] ],
                '/flux-pro|flux-2/'                  => [ 'A', [ 'Fotogerçekçi' ] ],
                '/flux\/dev|flux-dev|schnell/'       => [ 'B', [ 'Hızlı', 'Düşük maliyet' ] ],
                '/recraft/'                          => [ 'B', [ 'Tipografi', 'İllüstrasyon ve vektör' ] ],
                '/image-01|minimax/'                 => [ 'B', [ 'Düşük maliyet' ] ],
                '/dall-e-3/'                         => [ 'C', [ 'Eski nesil' ] ],
                '/dall-e-2/'                         => [ 'C', [ 'Eski nesil', 'Düşük çözünürlük' ] ],
            ];
            foreach ( $map as $pattern => $note ) {
                if ( preg_match( $pattern, $l ) ) {
                    return (array) apply_filters( 'agfo_ai_image_model_note', $note, $id );
                }
            }
            return (array) apply_filters( 'agfo_ai_image_model_note', [ 'B', [] ], $id );
        }

        public static function image_price( string $provider, string $model ): array {
            $rates = get_option( 'agfo_ai_pricing_rates', [] );
            if ( isset( $rates[ $provider ][ $model ]['per_image'] ) && (float) $rates[ $provider ][ $model ]['per_image'] > 0 ) {
                return [ 'price' => (float) $rates[ $provider ][ $model ]['per_image'], 'source' => 'Yönetici' ];
            }
            $meta = self::model_meta( $provider, $model );
            if ( ! empty( $meta['image'] ) ) {
                return [ 'price' => (float) $meta['image'], 'source' => 'Sağlayıcı API' ];
            }
            return [ 'price' => null, 'source' => '' ];
        }

        public static function image_board(): array {
            $registry  = function_exists( 'agfo_api_registry' ) ? agfo_api_registry() : [];
            $options   = class_exists( 'AGFO_AIM_Classic_Editor_Image' ) ? AGFO_AIM_Classic_Editor_Image::model_options() : AGFO_AIM_Image_Adapter::model_catalog();
            $default   = class_exists( 'AGFO_AIM_Image_Generator' ) ? AGFO_AIM_Image_Generator::effective_default() : [ 'provider' => '', 'model' => '' ];
            $tier_rank = [ 'A' => 3, 'B' => 2, 'C' => 1 ];
            $rows      = [];

            foreach ( $options as $provider => $models ) {
                $has_key = ! empty( agfo_get_api_key( $provider ) );
                foreach ( (array) $models as $m ) {
                    $id = (string) ( $m['id'] ?? '' );
                    if ( '' === $id ) {
                        continue;
                    }
                    [ $tier, $strengths ] = self::image_notes( $id );
                    $price                = self::image_price( $provider, $id );
                    $rows[] = [
                        'provider'       => $provider,
                        'provider_label' => (string) ( $registry[ $provider ]['label'] ?? $provider ),
                        'id'             => $id,
                        'label'          => (string) ( $m['label'] ?? $id ),
                        'has_key'        => $has_key,
                        'tier'           => $tier,
                        'tier_rank'      => $tier_rank[ $tier ] ?? 2,
                        'strengths'      => array_values( (array) $strengths ),
                        'price'          => $price['price'],
                        'price_source'   => $price['source'],
                        'prompt_budget'  => AGFO_AIM_Image_Adapter::prompt_budget( $provider, $id ),
                        'is_default'     => $provider === $default['provider'] && $id === $default['model'],
                        'version'        => self::version_key( $id ),
                    ];
                }
            }

            usort( $rows, static function ( $a, $b ) {
                return ( (int) $b['has_key'] <=> (int) $a['has_key'] )
                    ?: ( $b['tier_rank'] <=> $a['tier_rank'] )
                    ?: ( ( null === $a['price'] ? INF : $a['price'] ) <=> ( null === $b['price'] ? INF : $b['price'] ) )
                    ?: ( $b['version'] <=> $a['version'] );
            } );

            $keyed     = array_values( array_filter( $rows, static function ( $r ) { return $r['has_key']; } ) );
            $priced    = array_values( array_filter( $keyed, static function ( $r ) { return null !== $r['price']; } ) );
            $cheapest  = null;
            if ( $priced ) {
                usort( $priced, static function ( $a, $b ) { return $a['price'] <=> $b['price'] ?: $b['tier_rank'] <=> $a['tier_rank']; } );
                $cheapest = $priced[0];
            }
            $best_value = null;
            foreach ( $keyed as $r ) {
                if ( 'A' === $r['tier'] && null !== $r['price'] && ( null === $best_value || $r['price'] < $best_value['price'] ) ) {
                    $best_value = $r;
                }
            }

            return [
                'rows'    => $rows,
                'picks'   => [ 'recommended' => $keyed[0] ?? null, 'value' => $best_value, 'cheapest' => $cheapest ],
                'default' => $default,
            ];
        }

        /* ── AJAX ──────────────────────────────────────────── */

        private static function guard(): void {
            if ( ! current_user_can( 'manage_options' ) ) {
                wp_send_json_error( [ 'message' => 'Yetki yok.' ], 403 );
            }
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );
        }

        public static function ajax_translation_board(): void {
            self::guard();
            $min   = isset( $_POST['min_quality'] ) ? max( 0, min( 100, absint( $_POST['min_quality'] ) ) ) : 85;
            $scope = sanitize_key( (string) ( $_POST['scope'] ?? 'all' ) );
            wp_send_json_success( self::translation_board( $min, 'selected' === $scope ? 'selected' : 'all' ) );
        }

        public static function ajax_image_board(): void {
            self::guard();
            wp_send_json_success( self::image_board() );
        }

        public static function ajax_set_translation_model(): void {
            self::guard();
            $provider = sanitize_key( (string) ( $_POST['provider'] ?? '' ) );
            $model    = sanitize_text_field( wp_unslash( (string) ( $_POST['model'] ?? '' ) ) );
            if ( '' === $provider || '' === $model || empty( agfo_get_api_key( $provider ) ) ) {
                wp_send_json_error( [ 'message' => 'Sağlayıcı veya model geçersiz.' ], 400 );
            }
            $routing                   = agfo_get_capability_routing();
            $routing['text_translate'] = [ 'provider' => $provider, 'model' => $model ];
            agfo_save_capability_routing( $routing );
            delete_option( 'agfo_aim_translation_route_error' );
            wp_send_json_success( [ 'current' => self::translation_route() ] );
        }

        public static function ajax_set_image_model(): void {
            self::guard();
            $provider = sanitize_key( (string) ( $_POST['provider'] ?? '' ) );
            $model    = sanitize_text_field( wp_unslash( (string) ( $_POST['model'] ?? '' ) ) );
            if ( '' === $provider || '' === $model || ! in_array( $provider, AGFO_AIM_Image_Adapter::supported_providers(), true ) ) {
                wp_send_json_error( [ 'message' => 'Sağlayıcı veya model geçersiz.' ], 400 );
            }
            AGFO_AIM_Image_Generator::save_settings( [ 'provider' => $provider, 'model' => $model ] );
            wp_send_json_success( [ 'default' => AGFO_AIM_Image_Generator::effective_default() ] );
        }

        public static function ajax_set_image_price(): void {
            self::guard();
            $provider = sanitize_key( (string) ( $_POST['provider'] ?? '' ) );
            $model    = sanitize_text_field( wp_unslash( (string) ( $_POST['model'] ?? '' ) ) );
            $price    = isset( $_POST['price'] ) ? (float) str_replace( ',', '.', (string) wp_unslash( $_POST['price'] ) ) : 0.0;
            if ( '' === $provider || '' === $model || $price < 0 || $price > 100 ) {
                wp_send_json_error( [ 'message' => 'Fiyat 0 ile 100 USD arasında olmalı.' ], 400 );
            }
            $rates = get_option( 'agfo_ai_pricing_rates', [] );
            $rates = is_array( $rates ) ? $rates : [];
            if ( $price > 0 ) {
                $rates[ $provider ][ $model ]['per_image'] = round( $price, 4 );
            } else {
                unset( $rates[ $provider ][ $model ]['per_image'] );
            }
            update_option( 'agfo_ai_pricing_rates', $rates, false );
            wp_send_json_success( [ 'price' => $price > 0 ? round( $price, 4 ) : null ] );
        }
    }
}
