<?php
/**
 * Long-form speech synthesis.
 *
 * Every TTS provider caps a single request (OpenAI 4096 characters, ElevenLabs
 * per-model, MiniMax per-model). Until now the manager only clamped the input
 * field to that cap, so text longer than one request simply could not be voiced.
 * This class splits the text on natural boundaries, submits one job per chunk
 * through the existing job queue, and reports the group as a single unit.
 *
 * The chunk size is the SMALLEST limit across all resolved routes, not the
 * primary one: submit() keeps failover routes, so a chunk sized for ElevenLabs
 * would fail the moment it fell back to OpenAI.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Speech_Long' ) ) {
    final class AGFO_AIM_Speech_Long {

        const GROUPS_OPTION = 'agfo_aim_speech_groups';
        const GROUPS_KEPT   = 60;
        const MIN_LIMIT     = 300;
        const HARD_FLOOR    = 4096;

        /** Turkish and common Latin abbreviations that end in a period without ending a sentence. */
        const ABBREVIATIONS = [
            'dr', 'doç', 'prof', 'sn', 'av', 'md', 'bkz', 'vb', 'vs', 'örn', 'ör', 'yy',
            'no', 'sok', 'cad', 'mah', 'bk', 'çev', 'ed', 'haz', 'yay', 'bsk', 'st',
            'mr', 'mrs', 'ms', 'op', 'cit', 'etc', 'age', 'agm',
        ];

        /* ------------------------------------------------------------------ */
        /* Limits                                                              */
        /* ------------------------------------------------------------------ */

        /**
         * Smallest per-request character limit across every route the job API
         * would consider, reduced by a safety margin.
         *
         * @return int|WP_Error
         */
        public static function effective_limit( array $args = [] ) {
            if ( isset( $args['max_characters'] ) && absint( $args['max_characters'] ) > 0 ) {
                return max( self::MIN_LIMIT, absint( $args['max_characters'] ) );
            }

            $routes = class_exists( 'AGFO_AIM_Job_API' )
                ? AGFO_AIM_Job_API::routes_for( 'speech_synthesize', $args )
                : new WP_Error( 'agfo_job_api_missing', 'AGFO AI iş API yüklenmedi.' );

            if ( is_wp_error( $routes ) ) {
                return $routes;
            }

            $limit = 0;
            foreach ( (array) $routes as $route ) {
                $model_limit = self::model_limit( (string) $route['provider'], (string) $route['model'] );
                if ( $model_limit > 0 ) {
                    $limit = $limit > 0 ? min( $limit, $model_limit ) : $model_limit;
                }
            }

            if ( $limit <= 0 ) {
                $limit = self::HARD_FLOOR;
            }

            /** Providers count characters slightly differently and the payload is
             *  sanitised before it is sent, so a margin avoids edge rejections. */
            $margin = (float) apply_filters( 'agfo_speech_long_safety_margin', 0.9, $args );
            $margin = max( 0.5, min( 1.0, $margin ) );

            return max( self::MIN_LIMIT, (int) floor( $limit * $margin ) );
        }

        /**
         * Per-request limit for one model. Falls back to the smallest model in
         * the provider's catalogue when the model is not listed.
         */
        public static function model_limit( string $provider, string $model ): int {
            $provider = sanitize_key( $provider );
            if ( '' === $provider || ! class_exists( 'AGFO_AIM_TTS_Catalog' ) ) {
                return 0;
            }

            $catalog = AGFO_AIM_TTS_Catalog::get_catalog( $provider );
            if ( is_wp_error( $catalog ) || empty( $catalog['models'] ) || ! is_array( $catalog['models'] ) ) {
                return 0;
            }

            $smallest = 0;
            foreach ( $catalog['models'] as $entry ) {
                $max = absint( $entry['max_characters'] ?? 0 );
                if ( $max <= 0 ) {
                    continue;
                }
                if ( '' !== $model && (string) ( $entry['id'] ?? '' ) === $model ) {
                    return $max;
                }
                $smallest = $smallest > 0 ? min( $smallest, $max ) : $max;
            }

            return $smallest;
        }

        /* ------------------------------------------------------------------ */
        /* Splitting                                                           */
        /* ------------------------------------------------------------------ */

        /**
         * Splits on the largest natural boundary that fits: paragraph, then
         * sentence, then clause, then word, and only as a last resort mid-word.
         *
         * @return string[]
         */
        public static function split( string $text, int $limit ): array {
            $limit = max( self::MIN_LIMIT, $limit );
            $text  = self::normalise( $text );

            if ( '' === $text ) {
                return [];
            }
            if ( self::len( $text ) <= $limit ) {
                return [ $text ];
            }

            $pieces = [];
            foreach ( preg_split( '/\n{2,}/u', $text ) as $paragraph ) {
                $paragraph = trim( (string) $paragraph );
                if ( '' === $paragraph ) {
                    continue;
                }
                foreach ( self::sentences( $paragraph ) as $sentence ) {
                    foreach ( self::hard_split( $sentence, $limit ) as $unit ) {
                        $pieces[] = [ 'text' => $unit, 'paragraph_end' => false ];
                    }
                }
                if ( $pieces ) {
                    $pieces[ count( $pieces ) - 1 ]['paragraph_end'] = true;
                }
            }

            // Greedy packing: fill a chunk until the next unit would overflow.
            $chunks  = [];
            $current = '';

            foreach ( $pieces as $piece ) {
                $unit      = $piece['text'];
                $candidate = '' === $current ? $unit : $current . ' ' . $unit;

                if ( self::len( $candidate ) <= $limit ) {
                    $current = $candidate;
                } else {
                    if ( '' !== $current ) {
                        $chunks[] = $current;
                    }
                    $current = $unit;
                }

                // A paragraph boundary is the nicest place to cut, so close the
                // chunk there once it is already more than half full.
                if ( $piece['paragraph_end'] && self::len( $current ) > $limit / 2 ) {
                    $chunks[] = $current;
                    $current  = '';
                }
            }

            if ( '' !== trim( $current ) ) {
                $chunks[] = $current;
            }

            return array_values( array_filter( array_map( 'trim', $chunks ), static function ( $c ) {
                return '' !== $c;
            } ) );
        }

        private static function normalise( string $text ): string {
            $text = str_replace( [ "\r\n", "\r" ], "\n", $text );
            $text = preg_replace( '/[\x{0000}-\x{0008}\x{000B}\x{000C}\x{000E}-\x{001F}]/u', '', $text );
            $text = preg_replace( '/[\x{200B}-\x{200D}\x{FEFF}]/u', '', $text );
            $text = preg_replace( '/[ \t]+/u', ' ', $text );
            $text = preg_replace( '/ *\n */u', "\n", $text );
            return trim( (string) $text );
        }

        private static function len( string $text ): int {
            return function_exists( 'mb_strlen' ) ? mb_strlen( $text, 'UTF-8' ) : strlen( $text );
        }

        private static function sub( string $text, int $start, ?int $length = null ): string {
            return function_exists( 'mb_substr' ) ? mb_substr( $text, $start, $length, 'UTF-8' ) : substr( $text, $start, $length ?? PHP_INT_MAX );
        }

        /**
         * @return string[]
         */
        public static function sentences( string $text ): array {
            $chars = preg_split( '//u', $text, -1, PREG_SPLIT_NO_EMPTY );
            $out   = [];
            $buf   = '';
            $count = count( $chars );

            for ( $i = 0; $i < $count; $i++ ) {
                $char = $chars[ $i ];
                $buf .= $char;

                if ( false === strpos( '.!?…', $char ) ) {
                    continue;
                }

                // absorb trailing quotes and brackets
                while ( $i + 1 < $count && false !== strpos( '.!?…"»’\')', $chars[ $i + 1 ] ) ) {
                    $buf .= $chars[ ++$i ];
                }

                if ( $i + 1 >= $count || ' ' !== $chars[ $i + 1 ] ) {
                    continue;
                }

                $word  = preg_replace( '/[.!?…"»’\')]+$/u', '', $buf );
                $parts = preg_split( '/\s/u', $word );
                $word  = (string) ( $parts ? end( $parts ) : '' );
                $word = function_exists( 'mb_strtolower' ) ? mb_strtolower( $word, 'UTF-8' ) : strtolower( $word );

                if ( '.' === $char && ( in_array( $word, self::ABBREVIATIONS, true ) || preg_match( '/^\d+$/u', $word ) || 1 === self::len( $word ) ) ) {
                    continue;
                }

                $next = $chars[ $i + 2 ] ?? '';
                if ( '' !== $next && self::is_lower( $next ) ) {
                    continue;
                }

                $out[] = trim( $buf );
                $buf   = '';
                $i++;
            }

            if ( '' !== trim( $buf ) ) {
                $out[] = trim( $buf );
            }

            return $out ?: [ $text ];
        }

        private static function is_lower( string $char ): bool {
            if ( ! preg_match( '/\p{L}/u', $char ) ) {
                return false;
            }
            $lower = function_exists( 'mb_strtolower' ) ? mb_strtolower( $char, 'UTF-8' ) : strtolower( $char );
            $upper = function_exists( 'mb_strtoupper' ) ? mb_strtoupper( $char, 'UTF-8' ) : strtoupper( $char );
            return $char === $lower && $lower !== $upper;
        }

        /**
         * Breaks a single oversized sentence: clause marks first, then words,
         * then a blunt cut so nothing can ever exceed the limit.
         *
         * @return string[]
         */
        private static function hard_split( string $text, int $limit ): array {
            $text = trim( $text );
            if ( '' === $text || self::len( $text ) <= $limit ) {
                return '' === $text ? [] : [ $text ];
            }

            $parts = preg_split( '/(?<=[;:,—–])\s+/u', $text );
            $out   = [];
            $buf   = '';

            foreach ( (array) $parts as $part ) {
                $candidate = '' === $buf ? $part : $buf . ' ' . $part;
                if ( self::len( $candidate ) <= $limit ) {
                    $buf = $candidate;
                    continue;
                }
                if ( '' !== $buf ) {
                    $out[] = trim( $buf );
                }
                $buf = $part;
            }
            if ( '' !== trim( $buf ) ) {
                $out[] = trim( $buf );
            }

            $final = [];
            foreach ( $out as $piece ) {
                if ( self::len( $piece ) <= $limit ) {
                    $final[] = $piece;
                    continue;
                }
                foreach ( self::split_words( $piece, $limit ) as $word_piece ) {
                    $final[] = $word_piece;
                }
            }

            return $final;
        }

        /**
         * @return string[]
         */
        private static function split_words( string $text, int $limit ): array {
            $words = preg_split( '/\s+/u', $text, -1, PREG_SPLIT_NO_EMPTY );
            $out   = [];
            $buf   = '';

            foreach ( (array) $words as $word ) {
                if ( self::len( $word ) > $limit ) {
                    if ( '' !== $buf ) {
                        $out[] = $buf;
                        $buf   = '';
                    }
                    $offset = 0;
                    $total  = self::len( $word );
                    while ( $offset < $total ) {
                        $out[]   = self::sub( $word, $offset, $limit );
                        $offset += $limit;
                    }
                    continue;
                }

                $candidate = '' === $buf ? $word : $buf . ' ' . $word;
                if ( self::len( $candidate ) <= $limit ) {
                    $buf = $candidate;
                } else {
                    $out[] = $buf;
                    $buf   = $word;
                }
            }

            if ( '' !== $buf ) {
                $out[] = $buf;
            }

            return $out;
        }

        /* ------------------------------------------------------------------ */
        /* Preview                                                             */
        /* ------------------------------------------------------------------ */

        /**
         * Chunk plan without spending anything. Use this to show the operator
         * how many requests a text will cost before submitting.
         *
         * @return array<string,mixed>|WP_Error
         */
        public static function preview( string $text, array $options = [] ) {
            $limit = self::effective_limit( $options );
            if ( is_wp_error( $limit ) ) {
                return $limit;
            }

            $chunks = self::split( $text, $limit );
            $sizes  = array_map( [ __CLASS__, 'len' ], $chunks );

            return [
                'limit'            => $limit,
                'total_chunks'     => count( $chunks ),
                'total_characters' => array_sum( $sizes ),
                'largest_chunk'    => $sizes ? max( $sizes ) : 0,
                'chunks'           => array_map(
                    static function ( $chunk, $index ) {
                        return [
                            'index'      => (int) $index,
                            'characters' => function_exists( 'mb_strlen' ) ? mb_strlen( $chunk, 'UTF-8' ) : strlen( $chunk ),
                            'preview'    => function_exists( 'mb_substr' ) ? mb_substr( $chunk, 0, 80, 'UTF-8' ) : substr( $chunk, 0, 80 ),
                        ];
                    },
                    $chunks,
                    array_keys( $chunks )
                ),
            ];
        }

        /* ------------------------------------------------------------------ */
        /* Submission                                                          */
        /* ------------------------------------------------------------------ */

        /**
         * Splits the text and submits one speech job per chunk.
         *
         * @return array<string,mixed>|WP_Error
         */
        public static function synthesize( string $text, array $options = [] ) {
            if ( ! function_exists( 'agfo_speech_synthesize' ) ) {
                return new WP_Error( 'agfo_speech_missing', 'Seslendirme API yüklenmedi.' );
            }

            $limit = self::effective_limit( $options );
            if ( is_wp_error( $limit ) ) {
                return $limit;
            }

            $chunks = self::split( $text, $limit );
            if ( ! $chunks ) {
                return new WP_Error( 'agfo_speech_empty', 'Seslendirilecek metin bulunamadı.' );
            }

            $max_chunks = absint( apply_filters( 'agfo_speech_long_max_chunks', 500, $options ) );
            if ( $max_chunks > 0 && count( $chunks ) > $max_chunks ) {
                return new WP_Error(
                    'agfo_speech_too_many_chunks',
                    sprintf( 'Metin %d parçaya bölündü, izin verilen üst sınır %d. Metni bölerek gönderin.', count( $chunks ), $max_chunks )
                );
            }

            $group_uuid = function_exists( 'wp_generate_uuid4' ) ? wp_generate_uuid4() : uniqid( 'grp_', true );
            $seed       = (string) ( $options['idempotency_key'] ?? '' );
            $submitted  = [];
            $failures   = [];

            foreach ( $chunks as $index => $chunk ) {
                $chunk_options = $options;
                unset( $chunk_options['max_characters'] );

                $chunk_options['source_plugin']   = sanitize_key( (string) ( $options['source_plugin'] ?? 'agfo-ai-manager' ) );
                $chunk_options['idempotency_key'] = hash(
                    'sha256',
                    ( '' !== $seed ? $seed : 'agfo-speech-long' ) . '|' . $index . '|' .
                    (string) ( $options['provider'] ?? '' ) . '|' . (string) ( $options['model'] ?? '' ) . '|' .
                    (string) ( $options['voice'] ?? '' ) . '|' . $chunk
                );

                $job = agfo_speech_synthesize( $chunk, $chunk_options );

                if ( is_wp_error( $job ) ) {
                    $failures[] = [
                        'index'   => (int) $index,
                        'code'    => $job->get_error_code(),
                        'message' => $job->get_error_message(),
                    ];
                    // Stop at the first refusal: budget or kill-switch errors
                    // would repeat for every remaining chunk.
                    break;
                }

                $submitted[] = [
                    'index'      => (int) $index,
                    'characters' => self::len( $chunk ),
                    'job_uuid'   => (string) ( $job['job_uuid'] ?? '' ),
                    'status'     => (string) ( $job['status'] ?? 'queued' ),
                ];
            }

            $group = [
                'group_uuid'       => $group_uuid,
                'created_at'       => current_time( 'mysql' ),
                'source_plugin'    => sanitize_key( (string) ( $options['source_plugin'] ?? 'agfo-ai-manager' ) ),
                'created_by'       => absint( $options['created_by'] ?? get_current_user_id() ),
                'limit'            => $limit,
                'total_chunks'     => count( $chunks ),
                'total_characters' => array_sum( array_map( [ __CLASS__, 'len' ], $chunks ) ),
                'jobs'             => wp_list_pluck( $submitted, 'job_uuid' ),
                'chunks'           => $submitted,
                'failures'         => $failures,
                'meta'             => is_array( $options['group_meta'] ?? null ) ? $options['group_meta'] : [],
            ];

            self::remember_group( $group );

            if ( $failures && ! $submitted ) {
                return new WP_Error( 'agfo_speech_long_submit', $failures[0]['message'], $group );
            }

            return $group;
        }

        /* ------------------------------------------------------------------ */
        /* Group registry and status                                           */
        /* ------------------------------------------------------------------ */

        private static function remember_group( array $group ): void {
            $groups = get_option( self::GROUPS_OPTION, [] );
            if ( ! is_array( $groups ) ) {
                $groups = [];
            }

            $groups[ $group['group_uuid'] ] = $group;

            if ( count( $groups ) > self::GROUPS_KEPT ) {
                $groups = array_slice( $groups, -self::GROUPS_KEPT, null, true );
            }

            update_option( self::GROUPS_OPTION, $groups, false );
        }

        public static function get_group( string $group_uuid ): ?array {
            $groups = get_option( self::GROUPS_OPTION, [] );
            return is_array( $groups ) && isset( $groups[ $group_uuid ] ) ? (array) $groups[ $group_uuid ] : null;
        }

        /**
         * Aggregated status for a whole group.
         *
         * @param string|array $group group uuid, or a plain list of job uuids
         * @return array<string,mixed>|WP_Error
         */
        public static function status( $group ) {
            if ( ! function_exists( 'agfo_job_status' ) ) {
                return new WP_Error( 'agfo_job_api_missing', 'AGFO AI iş API yüklenmedi.' );
            }

            $meta = [];
            if ( is_string( $group ) ) {
                $stored = self::get_group( $group );
                if ( null === $stored ) {
                    return new WP_Error( 'agfo_speech_group_missing', 'Seslendirme grubu bulunamadı: ' . $group );
                }
                $uuids = (array) $stored['jobs'];
                $meta  = $stored;
            } else {
                $uuids = array_values( array_filter( array_map( 'strval', (array) $group ) ) );
            }

            $chunks   = [];
            $done     = 0;
            $failed   = 0;
            $running  = 0;
            $cost     = 0.0;
            $currency = 'USD';

            foreach ( $uuids as $index => $uuid ) {
                $job = agfo_job_status( $uuid );
                if ( is_wp_error( $job ) ) {
                    $failed++;
                    $chunks[] = [ 'index' => (int) $index, 'job_uuid' => $uuid, 'status' => 'failed', 'error_message' => $job->get_error_message() ];
                    continue;
                }

                $status = (string) ( $job['status'] ?? '' );
                if ( 'complete' === $status ) {
                    $done++;
                } elseif ( in_array( $status, [ 'failed', 'cancelled' ], true ) ) {
                    $failed++;
                } else {
                    $running++;
                }

                $cost    += (float) ( $job['cost_actual'] ?? 0 );
                $currency = (string) ( $job['currency'] ?? $currency );

                $job['index'] = (int) $index;
                $chunks[]     = $job;
            }

            $total = count( $uuids );
            if ( 0 === $total ) {
                $overall = 'empty';
            } elseif ( $done === $total ) {
                $overall = 'complete';
            } elseif ( $failed === $total ) {
                $overall = 'failed';
            } elseif ( 0 === $running && $failed > 0 ) {
                $overall = 'partial';
            } else {
                $overall = 'running';
            }

            return [
                'group_uuid'   => is_string( $group ) ? $group : '',
                'status'       => $overall,
                'total'        => $total,
                'done'         => $done,
                'failed'       => $failed,
                'running'      => $running,
                'cost_actual'  => round( $cost, 6 ),
                'currency'     => $currency,
                'total_chunks' => (int) ( $meta['total_chunks'] ?? $total ),
                'limit'        => (int) ( $meta['limit'] ?? 0 ),
                'meta'         => (array) ( $meta['meta'] ?? [] ),
                'chunks'       => $chunks,
            ];
        }

        /* ------------------------------------------------------------------ */
        /* Merge                                                               */
        /* ------------------------------------------------------------------ */

        /**
         * Joins a completed group into one audio file with FFmpeg. Optional:
         * callers that are happy playing the chunks in sequence never need it.
         *
         * @return array<string,mixed>|WP_Error
         */
        public static function merge( string $group_uuid, array $args = [] ) {
            if ( ! class_exists( 'AGFO_AIM_Audio_Effects' ) ) {
                return new WP_Error( 'agfo_speech_merge_engine', 'Ses motoru yüklenmedi.' );
            }

            $status = AGFO_AIM_Audio_Effects::status();
            if ( empty( $status['available'] ) || empty( $status['path'] ) ) {
                return new WP_Error( 'agfo_speech_merge_ffmpeg', (string) ( $status['reason'] ?? 'Birleştirme için FFmpeg gerekli ve bulunamadı.' ) );
            }

            $group = self::status( $group_uuid );
            if ( is_wp_error( $group ) ) {
                return $group;
            }
            if ( 'complete' !== $group['status'] ) {
                return new WP_Error( 'agfo_speech_merge_incomplete', 'Grup tamamlanmadan birleştirilemez (durum: ' . $group['status'] . ').' );
            }

            $files = [];
            $temp  = [];
            foreach ( $group['chunks'] as $chunk ) {
                $path = self::local_file_for( $chunk, $temp );
                if ( is_wp_error( $path ) ) {
                    self::cleanup( $temp );
                    return $path;
                }
                $files[] = $path;
            }

            if ( count( $files ) < 2 ) {
                self::cleanup( $temp );
                return new WP_Error( 'agfo_speech_merge_single', 'Birleştirilecek birden fazla parça yok.' );
            }

            $list = wp_tempnam( 'agfo-speech-concat' );
            $lines = '';
            foreach ( $files as $file ) {
                $lines .= "file '" . str_replace( "'", "'\\''", $file ) . "'\n";
            }
            file_put_contents( $list, $lines );

            $extension = strtolower( (string) ( $args['extension'] ?? 'mp3' ) );
            $output    = wp_tempnam( 'agfo-speech-merged' ) . '.' . ( preg_match( '/^[a-z0-9]{2,4}$/', $extension ) ? $extension : 'mp3' );

            $ok = self::run( [ (string) $status['path'], '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-f', 'concat', '-safe', '0', '-i', $list, '-c', 'copy', $output ] );

            if ( ! $ok || ! file_exists( $output ) || filesize( $output ) < 512 ) {
                // Stream copy only works when every chunk shares a codec; fall
                // back to a real encode rather than failing the whole merge.
                $ok = self::run( [ (string) $status['path'], '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-f', 'concat', '-safe', '0', '-i', $list, '-vn', '-ar', '44100', '-ac', '2', '-b:a', '192k', $output ] );
            }

            @unlink( $list );
            self::cleanup( $temp );

            if ( ! $ok || ! file_exists( $output ) || filesize( $output ) < 512 ) {
                @unlink( $output );
                return new WP_Error( 'agfo_speech_merge_failed', 'Parçalar birleştirilemedi.' );
            }

            if ( ! function_exists( 'agfo_ai_store_generated_media' ) ) {
                return [ 'file' => $output, 'attachment_id' => 0 ];
            }

            $stored = agfo_ai_store_generated_media(
                [ 'file' => $output, 'mime' => 'audio/mpeg' ],
                [
                    'title'                    => sanitize_text_field( (string) ( $args['title'] ?? 'AGFO Seslendirme' ) ),
                    'publish_to_media_library' => true,
                ]
            );

            @unlink( $output );
            return $stored;
        }

        /**
         * @param array<string,mixed> $chunk
         * @param string[]            $temp collects files this call downloaded
         * @return string|WP_Error
         */
        private static function local_file_for( array $chunk, array &$temp ) {
            $attachment_id = absint( $chunk['attachment_id'] ?? 0 );
            if ( $attachment_id ) {
                $path = get_attached_file( $attachment_id );
                if ( is_string( $path ) && is_readable( $path ) ) {
                    return $path;
                }
            }

            $url = (string) ( $chunk['download_url'] ?? $chunk['asset_url'] ?? '' );
            if ( '' === $url ) {
                return new WP_Error( 'agfo_speech_merge_source', 'Parça dosyası bulunamadı (parça ' . (int) ( $chunk['index'] ?? 0 ) . ').' );
            }

            $response = wp_remote_get( $url, [ 'timeout' => 120 ] );
            if ( is_wp_error( $response ) ) {
                return new WP_Error( 'agfo_speech_merge_fetch', 'Parça indirilemedi: ' . $response->get_error_message() );
            }

            $body = wp_remote_retrieve_body( $response );
            if ( '' === $body ) {
                return new WP_Error( 'agfo_speech_merge_empty', 'Parça dosyası boş geldi.' );
            }

            $file = wp_tempnam( 'agfo-speech-chunk' );
            file_put_contents( $file, $body );
            $temp[] = $file;

            return $file;
        }

        private static function cleanup( array $files ): void {
            foreach ( $files as $file ) {
                if ( is_string( $file ) && file_exists( $file ) ) {
                    @unlink( $file );
                }
            }
        }

        /**
         * CHANGED 17.1.2: delegates to AGFO_AIM_Audio_Effects::run_ffmpeg(), the plugin's single
         * hardened process launcher (resolved binary only, no shell, timeout). The first element
         * of $command (the binary path from status()) is replaced by the runner's own resolution.
         */
        private static function run( array $command ): bool {
            if ( ! class_exists( 'AGFO_AIM_Audio_Effects' ) || ! method_exists( 'AGFO_AIM_Audio_Effects', 'run_ffmpeg' ) ) {
                return false;
            }
            $result = AGFO_AIM_Audio_Effects::run_ffmpeg( array_slice( $command, 1 ), 600 );
            if ( is_wp_error( $result ) ) {
                if ( function_exists( 'agfo_ai_manager_log_transport' ) ) {
                    $data = $result->get_error_data();
                    agfo_ai_manager_log_transport( 'speech_long_merge_error', [
                        'code'   => is_array( $data ) ? (int) ( $data['exit_code'] ?? -1 ) : -1,
                        'stderr' => is_array( $data ) ? (string) ( $data['stderr'] ?? '' ) : $result->get_error_message(),
                    ] );
                }
                return false;
            }
            return true;
        }
    }
}

/* ---------------------------------------------------------------------- */
/* Public API                                                              */
/* ---------------------------------------------------------------------- */

if ( ! function_exists( 'agfo_speech_synthesize_long' ) ) {
    /**
     * Voices text of any length by splitting it to the provider's per-request
     * limit and queueing one job per chunk.
     *
     * @return array<string,mixed>|WP_Error
     */
    function agfo_speech_synthesize_long( string $text, array $options = [] ) {
        return class_exists( 'AGFO_AIM_Speech_Long' )
            ? AGFO_AIM_Speech_Long::synthesize( $text, $options )
            : new WP_Error( 'agfo_speech_long_missing', 'Uzun seslendirme modülü yüklenmedi.' );
    }
}

if ( ! function_exists( 'agfo_speech_split_preview' ) ) {
    /**
     * Chunk plan without submitting anything.
     *
     * @return array<string,mixed>|WP_Error
     */
    function agfo_speech_split_preview( string $text, array $options = [] ) {
        return class_exists( 'AGFO_AIM_Speech_Long' )
            ? AGFO_AIM_Speech_Long::preview( $text, $options )
            : new WP_Error( 'agfo_speech_long_missing', 'Uzun seslendirme modülü yüklenmedi.' );
    }
}

if ( ! function_exists( 'agfo_speech_group_status' ) ) {
    /**
     * @param string|array $group group uuid or list of job uuids
     * @return array<string,mixed>|WP_Error
     */
    function agfo_speech_group_status( $group ) {
        return class_exists( 'AGFO_AIM_Speech_Long' )
            ? AGFO_AIM_Speech_Long::status( $group )
            : new WP_Error( 'agfo_speech_long_missing', 'Uzun seslendirme modülü yüklenmedi.' );
    }
}

if ( ! function_exists( 'agfo_speech_group_merge' ) ) {
    /**
     * @return array<string,mixed>|WP_Error
     */
    function agfo_speech_group_merge( string $group_uuid, array $args = [] ) {
        return class_exists( 'AGFO_AIM_Speech_Long' )
            ? AGFO_AIM_Speech_Long::merge( $group_uuid, $args )
            : new WP_Error( 'agfo_speech_long_missing', 'Uzun seslendirme modülü yüklenmedi.' );
    }
}

if ( ! function_exists( 'agfo_speech_limit' ) ) {
    /**
     * Effective per-request character limit for the current routing.
     *
     * @return int|WP_Error
     */
    function agfo_speech_limit( array $options = [] ) {
        return class_exists( 'AGFO_AIM_Speech_Long' )
            ? AGFO_AIM_Speech_Long::effective_limit( $options )
            : new WP_Error( 'agfo_speech_long_missing', 'Uzun seslendirme modülü yüklenmedi.' );
    }
}
