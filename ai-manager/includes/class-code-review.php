<?php
/**
 * AGFO AI Manager — AI code review service.
 *
 * Added in 17.2.0. Consumers (AGFO Plugin Installer 2.3.0+) pass a review payload — the
 * static scanner's findings with code snippets, line hunks of what changed, public
 * surfaces added/removed, plugin identity — and receive a structured, evidence-checked
 * report. The service never edits code and never blocks anything; it only advises.
 *
 * Two routes in AI Kontrol Merkezi / Yetenek Yönlendirme:
 *  - code_review       quick triage after every install (default: gpt-4.1-mini when available)
 *  - code_review_deep  on-demand deep analysis (default: the site's default chat model)
 *
 * Public API: agfo_ai_code_review( array $payload, array $opts = [] ): array|WP_Error
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Code_Review' ) ) {
    final class AGFO_AIM_Code_Review {

        const QUICK_DEFAULT = 'gpt-4.1-mini';
        const MAX_PAYLOAD_CHARS = 90000;
        const MAX_SCHEMA_FINDINGS = 60; // NEW 17.3.2: keyed findings schema size cap.

        /* ── Model resolution ──────────────────────────────── */

        /**
         * Chat config for a review mode, same shape as agfo_get_priority_api_key().
         *
         * @return array|WP_Error
         */
        public static function config( string $mode = 'quick' ) {
            $cap     = 'deep' === $mode ? 'code_review_deep' : 'code_review';
            $routing = function_exists( 'agfo_get_capability_routing' ) ? agfo_get_capability_routing() : [];
            $route   = $routing[ $cap ] ?? [ 'provider' => '', 'model' => '' ];

            if ( '' === (string) ( $route['provider'] ?? '' ) && 'quick' === $mode ) {
                $default = self::quick_default();
                if ( $default ) {
                    $route = $default;
                }
            }
            $config = agfo_get_provider_for_capability( $cap, array_filter( [
                'provider' => (string) ( $route['provider'] ?? '' ),
                'model'    => (string) ( $route['model'] ?? '' ),
            ] ) );
            return $config;
        }

        /**
         * gpt-4.1-mini on OpenAI (or OpenRouter) when a key exists and the model is listed.
         *
         * @return array{provider:string,model:string}|null
         */
        public static function quick_default(): ?array {
            $candidates = (array) apply_filters( 'agfo_ai_code_review_quick_candidates', [
                [ 'openai', self::QUICK_DEFAULT ],
                [ 'openrouter', 'openai/' . self::QUICK_DEFAULT ],
            ] );
            foreach ( $candidates as $c ) {
                [ $provider, $model ] = $c;
                if ( empty( agfo_get_api_key( $provider ) ) ) {
                    continue;
                }
                $list = get_option( 'agfo_models_' . $provider, [] );
                $ids  = array_map( static function ( $m ) { return is_array( $m ) ? (string) ( $m['id'] ?? '' ) : (string) $m; }, is_array( $list ) ? $list : [] );
                // A listed model, or no list downloaded yet (the request guard falls back if it is gone).
                if ( ! $ids || in_array( $model, $ids, true ) ) {
                    return [ 'provider' => $provider, 'model' => $model ];
                }
            }
            return null;
        }

        /* ── Review ────────────────────────────────────────── */

        /**
         * @param array $payload {
         *   plugin:   array{name,version,previous_version,slug,requires_php,requires_wp},
         *   install:  array{mode,package,changed,added,removed},
         *   findings: array<int,array{file,line,level,message,snippet}>,
         *   hunks:    array<int,array{file,kind,from,to,text}>   kind: added|removed
         *   surfaces: array{added:string[],removed:string[]},
         *   revision: string   latest revision.txt entry
         * }
         * @param array $opts { mode: quick|deep }
         * @return array|WP_Error
         */
        public static function review( array $payload, array $opts = [] ) {
            $mode   = ( $opts['mode'] ?? 'quick' ) === 'deep' ? 'deep' : 'quick';
            $config = self::config( $mode );
            if ( is_wp_error( $config ) ) {
                return $config;
            }
            if ( empty( $config['key'] ) || empty( $config['chat_url'] ) ) {
                return new WP_Error( 'agfo_review_config', 'Kod inceleme için AI yapılandırması eksik.' );
            }

            $payload = self::redact( $payload );
            [ $prompt, $evidence ] = self::render_payload( $payload );

            $provider = sanitize_key( (string) $config['code'] );
            $model    = (string) $config['model'];
            $body     = self::build_body( $provider, $model, self::system_prompt( $mode ), $prompt, count( (array) ( $payload['findings'] ?? [] ) ) );
            $headers  = array_merge( [ 'Content-Type' => 'application/json' ], is_array( $config['auth'] ?? null ) ? $config['auth'] : [] );
            $started  = microtime( true );

            $response = agfo_api_post( (string) $config['chat_url'], $headers, wp_json_encode( $body ), [
                'provider_code' => $provider,
                'model'         => $model,
                'timeout'       => 'deep' === $mode ? 180 : 90,
                'capability'    => 'chat',
                'source'        => 'code_review_' . $mode,
            ] );
            if ( isset( $response['error'] ) ) {
                return new WP_Error( 'agfo_review_transport', 'AI sağlayıcısına ulaşılamadı: ' . (string) $response['error'] );
            }
            $code = (int) ( $response['http_code'] ?? 0 );
            $raw  = (string) ( $response['body'] ?? '' );
            // NEW 17.3.2: a provider that rejects the keyed schema (size/feature limits) gets the
            // list form once; skipped findings then show as "not reviewed" as before.
            if ( 400 === $code && count( (array) ( $payload['findings'] ?? [] ) ) > 0 && preg_match( '/schema|response_format|json_schema/i', $raw ) ) {
                $body     = self::build_body( $provider, $model, self::system_prompt( $mode ), $prompt, 0 );
                $response = agfo_api_post( (string) $config['chat_url'], $headers, wp_json_encode( $body ), [
                    'provider_code' => $provider,
                    'model'         => $model,
                    'timeout'       => 'deep' === $mode ? 180 : 90,
                    'capability'    => 'chat',
                    'source'        => 'code_review_' . $mode,
                ] );
                if ( isset( $response['error'] ) ) {
                    return new WP_Error( 'agfo_review_transport', 'AI sağlayıcısına ulaşılamadı: ' . (string) $response['error'] );
                }
                $code = (int) ( $response['http_code'] ?? 0 );
                $raw  = (string) ( $response['body'] ?? '' );
            }
            if ( $code < 200 || $code >= 300 ) {
                return new WP_Error( 'agfo_review_http', 'AI incelemesi başarısız (HTTP ' . $code . ').' );
            }

            $text   = self::extract_text( $raw, $provider );
            $parsed = self::parse_json( $text );
            if ( ! is_array( $parsed ) ) {
                return new WP_Error( 'agfo_review_parse', 'AI yanıtı beklenen JSON biçiminde değildi.' );
            }

            $report = self::validate( $parsed, $payload, $evidence );
            $usage  = self::usage( $raw, $provider );
            $report['meta'] = [
                'mode'       => $mode,
                'provider'   => $provider,
                'model'      => $model,
                'elapsed_ms' => (int) round( ( microtime( true ) - $started ) * 1000 ),
                'tokens_in'  => $usage[0],
                'tokens_out' => $usage[1],
                'cost'       => self::cost( $provider, $model, $usage ),
                'reviewed_at'=> current_time( 'mysql' ),
            ];
            $report['fix_prompt'] = self::fix_prompt( $report, $payload );
            return $report;
        }

        /* ── Prompting ─────────────────────────────────────── */

        public static function system_prompt( string $mode ): string {
            $lines = [
                'You are a senior WordPress plugin reviewer (PHP 7.4–8.3, security, performance, backward compatibility).',
                'You receive the output of a static scanner (findings F1…Fn with code snippets), line hunks of what changed in this release (H1…Hn) and the public surfaces added or removed.',
                'The "findings" object has one key per scanner finding (F1…Fn); fill every key. Classify each finding as one of: issue (real problem to fix), justified (the code is legitimate for the visible reason, e.g. base64 decoding of provider image data, proc_open of a fixed binary with array arguments), false_positive (the rule misfired, e.g. test files never loaded by WordPress).',
                'Then report additional risks the scanner cannot see, but ONLY from the hunks or snippets you were given: missing nonce/capability checks on new AJAX/REST/admin-post handlers, unescaped output, unsanitised input, SQL without prepare, removed public hooks/functions/shortcodes/options that other plugins may use, settings that are saved but never read, fatal-error risks.',
                'Evidence rule: every risk must cite a file and a line number that appears in the provided hunks or snippets. If you cannot point to a line, do not report it.',
                // CHANGED 17.3.1: stop "missing check" claims about functions whose start was not shown.
                'Report a missing nonce or capability check only when the whole handler, from its "function" line, is visible and contains no such check. A partial hunk is not proof that a check is missing.',
                'Scanner findings marked [test file] or grouped (×N) come from files WordPress never loads at runtime; classify them in one pass, usually as false_positive.',
                'Do not invent code you were not shown. Do not repeat a scanner finding as a risk.',
                'Verdict: "ok" when nothing needs action, "review" when at least one issue or medium/high risk exists, "rollback" only for a high-severity security hole or a likely fatal error in the new code.',
                'Write all human-readable text (summary, explanation, fix, actions) in Turkish, short and concrete.',
                'Return only the JSON object defined by the schema.',
            ];
            if ( 'deep' === $mode ) {
                $lines[] = 'Deep mode: also reason about logic regressions between removed and added lines, data migrations, and behaviour changes a site owner would notice.';
            }
            return implode( "\n", $lines );
        }

        /**
         * Render the payload as numbered text and record which file/line pairs are evidence.
         *
         * @return array{0:string,1:array<string,bool>}
         */
        public static function render_payload( array $payload ): array {
            $evidence = [];
            $out      = [];
            $p        = (array) ( $payload['plugin'] ?? [] );
            $i        = (array) ( $payload['install'] ?? [] );

            $out[] = '## Plugin';
            $out[] = 'Name: ' . ( $p['name'] ?? '-' ) . ' | Version: ' . ( $p['previous_version'] ?? '?' ) . ' → ' . ( $p['version'] ?? '?' ) . ' | Requires PHP: ' . ( $p['requires_php'] ?? '-' );
            $out[] = 'Install mode: ' . ( $i['mode'] ?? '-' ) . ' | files changed: ' . (int) ( $i['changed'] ?? 0 ) . ', added: ' . (int) ( $i['added'] ?? 0 ) . ', removed: ' . (int) ( $i['removed'] ?? 0 );

            if ( ! empty( $payload['revision'] ) ) {
                $out[] = '';
                $out[] = '## Author\'s revision note';
                $out[] = mb_substr( (string) $payload['revision'], 0, 2500 );
            }

            $surf = (array) ( $payload['surfaces'] ?? [] );
            if ( ! empty( $surf['added'] ) || ! empty( $surf['removed'] ) ) {
                $out[] = '';
                $out[] = '## Public surfaces';
                $out[] = 'Added: ' . ( $surf['added'] ? implode( ', ', array_slice( (array) $surf['added'], 0, 80 ) ) : '-' );
                $out[] = 'Removed: ' . ( $surf['removed'] ? implode( ', ', array_slice( (array) $surf['removed'], 0, 80 ) ) : '-' );
            }

            $out[] = '';
            $out[] = '## Scanner findings';
            $findings = array_values( (array) ( $payload['findings'] ?? [] ) );
            if ( ! $findings ) {
                $out[] = '(none)';
            }
            foreach ( $findings as $n => $f ) {
                $ref   = 'F' . ( $n + 1 );
                $out[] = sprintf( '%s [%s] %s:%d — %s', $ref, $f['level'] ?? 'notice', $f['file'] ?? '?', (int) ( $f['line'] ?? 0 ), $f['message'] ?? '' );
                if ( ! empty( $f['snippet'] ) ) {
                    $out[] = (string) $f['snippet'];
                    self::collect_evidence( $evidence, (string) ( $f['file'] ?? '' ), (string) $f['snippet'] );
                }
                if ( ! empty( $f['line'] ) ) {
                    $key = ( $f['file'] ?? '' ) . ':' . (int) $f['line'];
                    if ( ! isset( $evidence[ $key ] ) ) {
                        $evidence[ $key ] = '';
                    }
                }
            }

            $out[] = '';
            $out[] = '## Changed lines (hunks)';
            $hunks = array_values( (array) ( $payload['hunks'] ?? [] ) );
            if ( ! $hunks ) {
                $out[] = '(no line-level diff available)';
            }
            foreach ( $hunks as $n => $h ) {
                $out[] = sprintf( 'H%d %s %s lines %d–%d', $n + 1, strtoupper( (string) ( $h['kind'] ?? 'added' ) ), $h['file'] ?? '?', (int) ( $h['from'] ?? 0 ), (int) ( $h['to'] ?? 0 ) );
                $out[] = (string) ( $h['text'] ?? '' );
                self::collect_evidence( $evidence, (string) ( $h['file'] ?? '' ), (string) ( $h['text'] ?? '' ) );
            }

            $text = implode( "\n", $out );
            if ( mb_strlen( $text ) > self::MAX_PAYLOAD_CHARS ) {
                $text = mb_substr( $text, 0, self::MAX_PAYLOAD_CHARS ) . "\n[truncated]";
            }
            return [ $text, $evidence ];
        }

        /**
         * Lines rendered as "  123: code" or ">>> 123: code" count as evidence.
         * CHANGED 17.3.1: the shown code is kept (key => code) for the contradiction check.
         */
        private static function collect_evidence( array &$evidence, string $file, string $block ): void {
            if ( preg_match_all( '/^(?:>>>|[+\- ])?\s*(\d+):(.*)$/m', $block, $m, PREG_SET_ORDER ) ) {
                foreach ( $m as $row ) {
                    $key = $file . ':' . (int) $row[1];
                    if ( ! isset( $evidence[ $key ] ) || '' === $evidence[ $key ] ) {
                        $evidence[ $key ] = (string) $row[2];
                    }
                }
            }
        }

        /**
         * NEW 17.3.1: code around a cited line, from the installed file when the caller passed
         * source_root (read-only, confined to wp-content), otherwise from the lines that were shown.
         * Starts at the enclosing "function" line (up to 80 lines above) and ends 15 lines below.
         */
        /**
         * NEW 17.3.2: lines of an installed file under source_root, or null. Read-only; only .php/.js;
         * the file must sit inside source_root and source_root inside wp-content (directory boundary).
         *
         * @return string[]|null
         */
        private static function read_source( array $payload, string $file ): ?array {
            $root = (string) ( $payload['source_root'] ?? '' );
            if ( '' === $root || ! preg_match( '/\.(php|js)$/i', $file ) || strpos( $file, '..' ) !== false ) {
                return null;
            }
            $base = realpath( $root );
            if ( ! $base ) {
                return null;
            }
            $path = realpath( $base . '/' . ltrim( $file, '/' ) );
            $jail = defined( 'WP_CONTENT_DIR' ) ? realpath( WP_CONTENT_DIR ) : $base;
            $sep  = DIRECTORY_SEPARATOR;
            if ( ! $path || ! $jail
                || strpos( $path, rtrim( $base, '/\\' ) . $sep ) !== 0
                || ! ( $base === $jail || strpos( $base, rtrim( $jail, '/\\' ) . $sep ) === 0 )
                || ! is_readable( $path ) || filesize( $path ) >= 2000000 ) {
                return null;
            }
            $all = file( $path, FILE_IGNORE_NEW_LINES );
            return is_array( $all ) ? $all : null;
        }

        /**
         * NEW 17.3.1: code around a cited line, from the installed file when the caller passed
         * source_root, otherwise from the lines that were shown. Starts at the enclosing "function"
         * line (up to 80 lines above) and ends 15 lines below.
         * CHANGED 17.3.2: file access moved to read_source() with a directory-boundary jail.
         */
        public static function context_lines( array $payload, array $evidence, string $file, int $line ): string {
            // CHANGED 17.3.3: the window is the enclosing function up to its closing brace (it used
            // to run 15 lines past the cited line and could borrow a check from the next method).
            $map = self::line_map( $payload, $evidence, $file );
            if ( ! isset( $map[ $line ] ) ) {
                return '';
            }
            $start = null;
            for ( $i = $line; $i >= max( 1, $line - 80 ); $i-- ) {
                if ( ! isset( $map[ $i ] ) ) {
                    break; // A gap in the shown lines: the function start is unknown.
                }
                if ( preg_match( '/\bfunction\b/', $map[ $i ] ) ) { $start = $i; break; }
            }
            if ( null === $start ) {
                return implode( "\n", array_filter( [ $map[ $line - 1 ] ?? null, $map[ $line ], $map[ $line + 1 ] ?? null ], 'is_string' ) );
            }
            $span = self::span_function( $map, $start );
            if ( max( array_keys( $span ) ) < $line ) {
                return (string) $map[ $line ]; // Cited line is outside that function.
            }
            return implode( "\n", $span );
        }

        /**
         * NEW 17.3.3: line number => code for a file, from the installed file or the shown lines.
         *
         * @return array<int,string>
         */
        private static function line_map( array $payload, array $evidence, string $file ): array {
            $all = self::read_source( $payload, $file );
            if ( is_array( $all ) ) {
                $map = [];
                foreach ( $all as $i => $code ) {
                    $map[ $i + 1 ] = (string) $code;
                }
                return $map;
            }
            $map    = [];
            $prefix = $file . ':';
            foreach ( $evidence as $key => $code ) {
                if ( strpos( (string) $key, $prefix ) === 0 ) {
                    $map[ (int) substr( (string) $key, strlen( $prefix ) ) ] = (string) $code;
                }
            }
            ksort( $map );
            return $map;
        }

        /**
         * NEW 17.3.3: lines from $start to the brace that closes the function opened there.
         * Stops at a gap in the shown lines or after 200 lines. Braces inside quotes and line
         * comments are ignored.
         *
         * @return array<int,string>
         */
        private static function span_function( array $map, int $start ): array {
            $out    = [];
            $depth  = 0;
            $opened = false;
            for ( $i = $start; $i < $start + 200 && isset( $map[ $i ] ); $i++ ) {
                $out[ $i ] = $map[ $i ];
                $clean     = preg_replace( [ '/\'(?:\\\\.|[^\'\\\\])*\'/', '/"(?:\\\\.|[^"\\\\])*"/', '#//.*$#', '/#.*$/' ], '', $map[ $i ] );
                $open      = substr_count( (string) $clean, '{' );
                $close     = substr_count( (string) $clean, '}' );
                if ( $open > 0 ) {
                    $opened = true;
                }
                $depth += $open - $close;
                if ( $opened && $depth <= 0 ) {
                    break;
                }
            }
            return $out;
        }

        /**
         * NEW 17.3.1: a "missing nonce / capability check" risk is dropped when the code around
         * the cited line contains that very check.
         * CHANGED 17.3.2: only real enforcement counts — current_user_can()/user_can() calls for
         * capability; core nonce functions, or a custom *verify*nonce() wrapper whose definition
         * ($wrapper_body) calls one. Names such as required_capability or permission_callback alone
         * no longer refute a claim.
         *
         * @param callable|null $wrapper_body fn( string $name ): string — source of a wrapper function.
         */
        public static function contradicted( array $risk, string $context, ?callable $wrapper_body = null ): bool {
            if ( '' === trim( $context ) ) {
                return false;
            }
            $claim = mb_strtolower( (string) ( $risk['title'] ?? '' ) . ' ' . (string) ( $risk['explanation'] ?? '' ) );
            if ( ! preg_match( '/(yok|eksik|görünmüyor|bulunmuyor|yapılmıyor|missing|lack|absent|without|no\s)/u', $claim ) ) {
                return false;
            }
            $about_nonce = (bool) preg_match( '/(nonce|csrf|referer)/u', $claim );
            $about_cap   = (bool) preg_match( '/(yetki|capabilit|current_user_can|permission|authori[sz])/u', $claim );
            if ( ! $about_nonce && ! $about_cap ) {
                return false;
            }
            $core_nonce = '/\b(check_ajax_referer|check_admin_referer|wp_verify_nonce)\s*\(/i';
            $has_nonce  = (bool) preg_match( $core_nonce, $context );
            if ( ! $has_nonce && $wrapper_body && preg_match_all( '/(?:self::|static::|\$this->)?\b(\w*verify\w*nonce\w*)\s*\(/i', $context, $m ) ) {
                foreach ( array_unique( $m[1] ) as $name ) {
                    if ( preg_match( $core_nonce, (string) $wrapper_body( $name ) ) ) {
                        $has_nonce = true;
                        break;
                    }
                }
            }
            $has_cap = (bool) preg_match( '/(?<![\w>:])(current_user_can|user_can)\s*\(/i', $context );
            return ( ! $about_nonce || $has_nonce ) && ( ! $about_cap || $has_cap );
        }

        /**
         * NEW 17.3.3: true when the risk text admits the claim could not be checked
         * ("doğrulanamıyor", "fonksiyonun tamamı verilmemiş", "cannot be verified", …).
         */
        public static function self_declared_unverifiable( array $risk ): bool {
            $text = mb_strtolower( (string) ( $risk['title'] ?? '' ) . ' ' . (string) ( $risk['explanation'] ?? '' ) );
            return (bool) preg_match( '/(doğrulanamıyor|doğrulanamaz|doğrulanamadı|tespit edilemiyor|anlaşılamıyor|(tamamı|gövdesi|içeriği)\s+(verilmemiş|gösterilmemiş|görünmüyor|paylaşılmamış)|cannot be (verified|confirmed|determined)|could not (be )?(verify|verified|confirm)|not (shown|visible|provided) (in|here)|body (is )?not shown)/u', $text );
        }

        /**
         * NEW 17.3.3: code of one line, from the installed file or the shown lines.
         */
        public static function line_code( array $payload, array $evidence, string $file, int $line ): string {
            $lines = self::read_source( $payload, $file );
            if ( is_array( $lines ) && isset( $lines[ $line - 1 ] ) ) {
                return (string) $lines[ $line - 1 ];
            }
            return (string) ( $evidence[ $file . ':' . $line ] ?? '' );
        }

        /**
         * NEW 17.3.3: callback name of an AJAX/admin-post/REST registration on a line, or ''.
         * Handles 'func', [ __CLASS__, 'm' ], array( $this, 'm' ), [ self::class, 'm' ], 'Class::m'.
         */
        public static function hook_callback( string $code ): string {
            if ( ! preg_match( '/add_action\s*\(\s*([\'"])(wp_ajax_(?:nopriv_)?|admin_post_(?:nopriv_)?)[^\'"]*\1\s*,\s*(.+)$/', $code, $m ) ) {
                return '';
            }
            $rest = $m[3];
            if ( preg_match( '/^(?:\[|array\s*\()\s*[^,]+,\s*([\'"])(\w+)\1/', $rest, $c ) ) {
                return $c[2];
            }
            if ( preg_match( '/^([\'"])(?:[\w\\\\]+::)?(\w+)\1/', $rest, $c ) ) {
                return $c[2];
            }
            return '';
        }

        /**
         * NEW 17.3.2: source of "function $name" (≤ 40 lines) from the installed file or the shown lines.
         */
        public static function function_body( array $payload, array $evidence, string $file, string $name ): string {
            // CHANGED 17.3.3: ends at the function's closing brace instead of a fixed 40 lines.
            foreach ( self::line_map( $payload, $evidence, $file ) as $n => $code ) {
                if ( preg_match( '/\bfunction\s+' . preg_quote( $name, '/' ) . '\s*\(/i', $code ) ) {
                    return implode( "\n", self::span_function( self::line_map( $payload, $evidence, $file ), $n ) );
                }
            }
            return '';
        }

        public static function schema( int $finding_count = 0 ): array {
            $sev   = [ 'type' => 'string', 'enum' => [ 'high', 'medium', 'low', 'info' ] ];
            $entry = [
                'type'                 => 'object',
                'additionalProperties' => false,
                'required'             => [ 'classification', 'severity', 'explanation', 'fix' ],
                'properties'           => [
                    'classification' => [ 'type' => 'string', 'enum' => [ 'issue', 'justified', 'false_positive' ] ],
                    'severity'       => $sev,
                    'explanation'    => [ 'type' => 'string' ],
                    'fix'            => [ 'type' => 'string' ],
                ],
            ];
            $finding_count = max( 0, min( self::MAX_SCHEMA_FINDINGS, $finding_count ) );
            if ( $finding_count > 0 ) {
                $props = [];
                for ( $i = 1; $i <= $finding_count; $i++ ) {
                    $props[ 'F' . $i ] = $entry;
                }
                $findings_schema = [
                    'type'                 => 'object',
                    'additionalProperties' => false,
                    'required'             => array_keys( $props ),
                    'properties'           => $props,
                ];
            }
            return [
                'type'                 => 'object',
                'additionalProperties' => false,
                'required'             => [ 'findings', 'risks', 'actions', 'summary', 'verdict' ],
                'properties'           => [
                    'findings' => $findings_schema ?? [
                        'type'  => 'array',
                        'items' => [
                            'type'                 => 'object',
                            'additionalProperties' => false,
                            'required'             => [ 'ref', 'classification', 'severity', 'explanation', 'fix' ],
                            'properties'           => [
                                'ref'            => [ 'type' => 'string' ],
                                'classification' => [ 'type' => 'string', 'enum' => [ 'issue', 'justified', 'false_positive' ] ],
                                'severity'       => $sev,
                                'explanation'    => [ 'type' => 'string' ],
                                'fix'            => [ 'type' => 'string' ],
                            ],
                        ],
                    ],
                    'risks'    => [
                        'type'  => 'array',
                        'items' => [
                            'type'                 => 'object',
                            'additionalProperties' => false,
                            'required'             => [ 'title', 'severity', 'file', 'line', 'explanation', 'fix' ],
                            'properties'           => [
                                'title'       => [ 'type' => 'string' ],
                                'severity'    => $sev,
                                'file'        => [ 'type' => 'string' ],
                                'line'        => [ 'type' => 'integer' ],
                                'explanation' => [ 'type' => 'string' ],
                                'fix'         => [ 'type' => 'string' ],
                            ],
                        ],
                    ],
                    'actions'  => [ 'type' => 'array', 'items' => [ 'type' => 'string' ] ],
                    'summary'  => [ 'type' => 'string' ],
                    'verdict'  => [ 'type' => 'string', 'enum' => [ 'ok', 'review', 'rollback' ] ],
                ],
            ];
        }

        public static function build_body( string $provider, string $model, string $system, string $user, int $finding_count = 0 ): array {
            $schema = self::schema( $finding_count ); // CHANGED 17.3.2: one required key per finding.
            $reasoning = function_exists( 'agfo_openai_model_is_reasoning' ) && agfo_openai_model_is_reasoning( preg_replace( '#^[^/]+/#', '', $model ) );

            if ( 'gemini' === $provider ) {
                return [
                    'systemInstruction' => [ 'parts' => [ [ 'text' => $system ] ] ],
                    'contents'          => [ [ 'role' => 'user', 'parts' => [ [ 'text' => $user ] ] ] ],
                    'generationConfig'  => [ 'temperature' => 0, 'maxOutputTokens' => 8192, 'responseMimeType' => 'application/json' ],
                ];
            }
            if ( 'claude' === $provider ) {
                return [
                    'model'      => $model,
                    'system'     => $system . "\nOutput JSON matching this schema exactly:\n" . wp_json_encode( $schema ),
                    'max_tokens' => 4000,
                    'messages'   => [ [ 'role' => 'user', 'content' => $user ] ],
                ];
            }

            $body = [
                'model'    => $model,
                'messages' => [
                    [ 'role' => 'system', 'content' => $system ],
                    [ 'role' => 'user', 'content' => $user ],
                ],
                'max_tokens'  => $reasoning ? 12000 : 4000,
                'temperature' => 0,
            ];
            if ( $reasoning ) {
                $body['reasoning_effort'] = 'low';
            }
            if ( in_array( $provider, [ 'openai', 'openrouter' ], true ) ) {
                $body['response_format'] = [
                    'type'        => 'json_schema',
                    'json_schema' => [ 'name' => 'agfo_code_review', 'strict' => true, 'schema' => $schema ],
                ];
            } else {
                $body['response_format'] = [ 'type' => 'json_object' ];
                $body['messages'][0]['content'] .= "\nOutput JSON matching this schema exactly:\n" . wp_json_encode( $schema );
            }
            return $body;
        }

        /* ── Parsing and validation ────────────────────────── */

        public static function extract_text( string $raw, string $provider ): string {
            $data = json_decode( $raw, true );
            if ( ! is_array( $data ) ) {
                return '';
            }
            if ( 'gemini' === $provider ) {
                $text = '';
                foreach ( (array) ( $data['candidates'][0]['content']['parts'] ?? [] ) as $part ) {
                    if ( isset( $part['text'] ) && empty( $part['thought'] ) ) {
                        $text .= (string) $part['text'];
                    }
                }
                return $text;
            }
            if ( 'claude' === $provider ) {
                $text = '';
                foreach ( (array) ( $data['content'] ?? [] ) as $block ) {
                    if ( isset( $block['text'] ) ) {
                        $text .= (string) $block['text'];
                    }
                }
                return $text;
            }
            $content = $data['choices'][0]['message']['content'] ?? '';
            if ( is_array( $content ) ) {
                $content = implode( '', array_map( static function ( $c ) { return is_array( $c ) ? (string) ( $c['text'] ?? '' ) : ''; }, $content ) );
            }
            return (string) $content;
        }

        public static function parse_json( string $text ): ?array {
            $text = trim( $text );
            $text = (string) preg_replace( '/^```(?:json)?\s*|\s*```$/i', '', $text );
            $data = json_decode( $text, true );
            if ( ! is_array( $data ) && preg_match( '/\{.*\}/s', $text, $m ) ) {
                $data = json_decode( $m[0], true );
            }
            return is_array( $data ) ? $data : null;
        }

        /**
         * Keep only well-formed items backed by evidence; never trust the model's counts.
         */
        public static function validate( array $parsed, array $payload, array $evidence ): array {
            $findings_in = array_values( (array) ( $payload['findings'] ?? [] ) );
            $classes     = [ 'issue', 'justified', 'false_positive' ];
            $sevs        = [ 'high', 'medium', 'low', 'info' ];

            $findings = [];
            $seen     = [];
            // CHANGED 17.3.2: accept the keyed form { "F1": {...} } as well as the list form.
            $raw_findings = (array) ( $parsed['findings'] ?? [] );
            $keyed        = [];
            foreach ( $raw_findings as $k => $f ) {
                if ( is_string( $k ) && is_array( $f ) ) {
                    $f['ref'] = $k;
                }
                $keyed[] = $f;
            }
            foreach ( $keyed as $f ) {
                if ( ! is_array( $f ) || ! preg_match( '/^F(\d+)$/', (string) ( $f['ref'] ?? '' ), $m ) ) {
                    continue;
                }
                $idx = (int) $m[1] - 1;
                if ( ! isset( $findings_in[ $idx ] ) || isset( $seen[ $idx ] ) ) {
                    continue;
                }
                $seen[ $idx ] = true;
                $src          = $findings_in[ $idx ];
                $findings[]   = [
                    'ref'            => 'F' . ( $idx + 1 ),
                    'file'           => (string) ( $src['file'] ?? '' ),
                    'line'           => (int) ( $src['line'] ?? 0 ),
                    'message'        => (string) ( $src['message'] ?? '' ),
                    'level'          => (string) ( $src['level'] ?? '' ),
                    'classification' => in_array( $f['classification'] ?? '', $classes, true ) ? $f['classification'] : 'issue',
                    'severity'       => in_array( $f['severity'] ?? '', $sevs, true ) ? $f['severity'] : 'low',
                    'explanation'    => mb_substr( sanitize_text_field( (string) ( $f['explanation'] ?? '' ) ), 0, 600 ),
                    'fix'            => mb_substr( sanitize_text_field( (string) ( $f['fix'] ?? '' ) ), 0, 600 ),
                ];
            }
            // Scanner findings the model skipped stay visible as "not reviewed".
            foreach ( $findings_in as $idx => $src ) {
                if ( ! isset( $seen[ $idx ] ) ) {
                    $findings[] = [
                        'ref' => 'F' . ( $idx + 1 ), 'file' => (string) ( $src['file'] ?? '' ), 'line' => (int) ( $src['line'] ?? 0 ),
                        'message' => (string) ( $src['message'] ?? '' ), 'level' => (string) ( $src['level'] ?? '' ),
                        'classification' => 'not_reviewed', 'severity' => 'info', 'explanation' => 'AI bu bulgu için yanıt vermedi.', 'fix' => '',
                    ];
                }
            }
            usort( $findings, static function ( $a, $b ) { return (int) substr( $a['ref'], 1 ) <=> (int) substr( $b['ref'], 1 ); } );

            $risks        = [];
            $unverified   = 0;
            $contradicted = 0;
            foreach ( (array) ( $parsed['risks'] ?? [] ) as $r ) {
                if ( ! is_array( $r ) ) {
                    continue;
                }
                $file = ltrim( (string) ( $r['file'] ?? '' ), '/' );
                $line = (int) ( $r['line'] ?? 0 );
                // CHANGED 17.3.1: isset() — evidence values are now the shown code (may be "" or "0").
                if ( '' === $file || $line < 1 || ! isset( $evidence[ $file . ':' . $line ] ) ) {
                    $unverified++; // No line we showed backs it up: drop as a probable hallucination.
                    continue;
                }
                // NEW 17.3.3: a risk that itself says it cannot be verified from what was shown is
                // speculation, not a finding (the prompt already forbids it; models still send it).
                if ( self::self_declared_unverifiable( $r ) ) {
                    $unverified++;
                    continue;
                }
                // NEW 17.3.1: the claim is refuted by the code itself (e.g. "no nonce" next to verify_*_nonce()).
                $resolver = static function ( string $name ) use ( $payload, $evidence, $file ): string {
                    return self::function_body( $payload, $evidence, $file, $name );
                };
                // NEW 17.3.3: a claim cited on a hook registration line is judged on the callback's
                // body alone; otherwise on the enclosing function.
                $callback = self::hook_callback( self::line_code( $payload, $evidence, $file, $line ) );
                $context  = '' !== $callback
                    ? self::function_body( $payload, $evidence, $file, $callback )
                    : self::context_lines( $payload, $evidence, $file, $line );
                if ( self::contradicted( $r, $context, $resolver ) ) {
                    $contradicted++;
                    continue;
                }
                $risks[] = [
                    'title'       => mb_substr( sanitize_text_field( (string) ( $r['title'] ?? '' ) ), 0, 160 ),
                    'severity'    => in_array( $r['severity'] ?? '', $sevs, true ) ? $r['severity'] : 'low',
                    'file'        => $file,
                    'line'        => $line,
                    'explanation' => mb_substr( sanitize_text_field( (string) ( $r['explanation'] ?? '' ) ), 0, 700 ),
                    'fix'         => mb_substr( sanitize_text_field( (string) ( $r['fix'] ?? '' ) ), 0, 600 ),
                ];
            }

            $actions = array_values( array_filter( array_map( static function ( $a ) {
                return mb_substr( sanitize_text_field( (string) $a ), 0, 300 );
            }, array_slice( (array) ( $parsed['actions'] ?? [] ), 0, 8 ) ) ) );

            // Verdict is recomputed from the verified content so a lone hallucination cannot raise it.
            $issues = array_filter( $findings, static function ( $f ) { return 'issue' === $f['classification']; } );
            $high   = array_filter( array_merge( $risks, $issues ), static function ( $x ) { return 'high' === $x['severity']; } );
            $model_verdict = in_array( $parsed['verdict'] ?? '', [ 'ok', 'review', 'rollback' ], true ) ? $parsed['verdict'] : 'review';
            if ( ! $issues && ! array_filter( $risks, static function ( $r ) { return in_array( $r['severity'], [ 'high', 'medium' ], true ); } ) ) {
                $verdict = 'ok';
            } elseif ( 'rollback' === $model_verdict && $high ) {
                $verdict = 'rollback';
            } else {
                $verdict = 'review';
            }

            $counts = [ 'issue' => 0, 'justified' => 0, 'false_positive' => 0, 'not_reviewed' => 0 ];
            foreach ( $findings as $f ) {
                $counts[ $f['classification'] ] = ( $counts[ $f['classification'] ] ?? 0 ) + 1;
            }

            return [
                'verdict'    => $verdict,
                'summary'    => mb_substr( sanitize_text_field( (string) ( $parsed['summary'] ?? '' ) ), 0, 900 ),
                'findings'   => $findings,
                'risks'      => $risks,
                'actions'    => $actions,
                'counts'     => $counts,
                'unverified' => $unverified,
                'contradicted' => $contradicted,
            ];
        }

        /* ── Privacy ───────────────────────────────────────── */

        /**
         * Mask secrets before anything leaves the server.
         */
        public static function redact( $value ) {
            if ( is_array( $value ) ) {
                $out = [];
                foreach ( $value as $k => $v ) {
                    $out[ $k ] = self::redact( $v );
                }
                return $out;
            }
            if ( ! is_string( $value ) || '' === $value ) {
                return $value;
            }
            if ( function_exists( 'agfo_redact_secrets' ) ) {
                $value = (string) agfo_redact_secrets( $value );
            }
            $patterns = [
                // define( 'DB_PASSWORD', '...' ), define( 'AUTH_KEY', '...' ) …
                '/(define\(\s*[\'"][A-Z0-9_]*(?:PASSWORD|PASS|SECRET|KEY|SALT|TOKEN)[A-Z0-9_]*[\'"]\s*,\s*)([\'"]).*?\2/i' => '$1\'[REDACTED]\'',
                // $api_key = '...';  'password' => '...'
                '/((?:api[_-]?key|secret|password|passwd|token|auth)[\'"]?\s*(?:=>|=|:)\s*)([\'"])[^\'"]{6,}\2/i' => '$1\'[REDACTED]\'',
                // Long bearer-like tokens.
                '/\b(?:sk|pk|rk|ghp|xox[abp])[-_][A-Za-z0-9_\-]{16,}\b/' => '[REDACTED]',
            ];
            foreach ( $patterns as $pattern => $replacement ) {
                $replaced = preg_replace( $pattern, $replacement, $value );
                if ( null !== $replaced ) {
                    $value = $replaced;
                }
            }
            return $value;
        }

        /* ── Cost and fix prompt ───────────────────────────── */

        private static function usage( string $raw, string $provider ): array {
            $d = json_decode( $raw, true );
            if ( ! is_array( $d ) ) {
                return [ 0, 0 ];
            }
            if ( 'gemini' === $provider ) {
                return [ (int) ( $d['usageMetadata']['promptTokenCount'] ?? 0 ), (int) ( $d['usageMetadata']['candidatesTokenCount'] ?? 0 ) + (int) ( $d['usageMetadata']['thoughtsTokenCount'] ?? 0 ) ];
            }
            if ( 'claude' === $provider ) {
                return [ (int) ( $d['usage']['input_tokens'] ?? 0 ), (int) ( $d['usage']['output_tokens'] ?? 0 ) ];
            }
            return [ (int) ( $d['usage']['prompt_tokens'] ?? 0 ), (int) ( $d['usage']['completion_tokens'] ?? 0 ) ];
        }

        private static function cost( string $provider, string $model, array $usage ): ?float {
            if ( ! class_exists( 'AGFO_AIM_Model_Catalog' ) ) {
                return null;
            }
            $p = AGFO_AIM_Model_Catalog::token_price( $provider, $model );
            if ( null === $p['in'] ) {
                return null;
            }
            return round( ( $usage[0] * $p['in'] + $usage[1] * $p['out'] ) / 1000000, 5 );
        }

        /**
         * Hand-off text for Claude or another coding assistant, built from verified items only.
         */
        public static function fix_prompt( array $report, array $payload ): string {
            $p     = (array) ( $payload['plugin'] ?? [] );
            $lines = [ '=== AGFO AI CODE REVIEW — FIX REQUEST ===', 'Plugin: ' . ( $p['name'] ?? '-' ) . ' ' . ( $p['version'] ?? '' ), '' ];
            $todo  = 0;
            foreach ( (array) $report['findings'] as $f ) {
                if ( 'issue' !== $f['classification'] ) {
                    continue;
                }
                $todo++;
                $lines[] = sprintf( '- [%s] %s:%d — %s', strtoupper( $f['severity'] ), $f['file'], $f['line'], $f['message'] );
                if ( $f['fix'] ) {
                    $lines[] = '  Öneri: ' . $f['fix'];
                }
            }
            foreach ( (array) $report['risks'] as $r ) {
                $todo++;
                $lines[] = sprintf( '- [%s] %s:%d — %s', strtoupper( $r['severity'] ), $r['file'], $r['line'], $r['title'] );
                $lines[] = '  ' . $r['explanation'];
                if ( $r['fix'] ) {
                    $lines[] = '  Öneri: ' . $r['fix'];
                }
            }
            if ( ! $todo ) {
                return '';
            }
            $lines[] = '';
            $lines[] = 'Fix only the items above. Preserve public hooks, function names, options and AJAX actions. Bump the patch version and update revision.txt.';
            return implode( "\n", $lines );
        }
    }
}

if ( ! function_exists( 'agfo_ai_code_review' ) ) {
    /**
     * Review a plugin release with AI (17.2.0). Advisory only.
     *
     * @param array $payload See AGFO_AIM_Code_Review::review().
     * @param array $opts    { mode: 'quick' | 'deep' }
     * @return array|WP_Error
     */
    function agfo_ai_code_review( array $payload, array $opts = [] ) {
        return AGFO_AIM_Code_Review::review( $payload, $opts );
    }
}

if ( ! function_exists( 'agfo_ai_code_review_model' ) ) {
    /**
     * Provider/model a review mode will use, for display in consumers.
     *
     * @return array{provider:string,model:string}
     */
    function agfo_ai_code_review_model( string $mode = 'quick' ): array {
        $config = AGFO_AIM_Code_Review::config( $mode );
        return is_wp_error( $config ) ? [ 'provider' => '', 'model' => '' ] : [ 'provider' => (string) $config['code'], 'model' => (string) $config['model'] ];
    }
}
