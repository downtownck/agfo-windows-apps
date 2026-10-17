<?php
/**
 * Server-side audio effect processor for generated speech assets.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Audio_Effects' ) ) {
    final class AGFO_AIM_Audio_Effects {
        /**
         * Return the supported effect presets.
         *
         * @return array<string,string>
         */
        public static function presets(): array {
            return [
                'none'      => 'Efektsiz / kuru',
                'warm_room' => 'Hafif reverb · sıcak oda',
                'soft_echo' => 'Yumuşak echo',
                'hall'      => 'Belirgin salon reverbü',
            ];
        }

        public static function sanitize_effect( $effect ): string {
            $effect = sanitize_key( (string) $effect );
            return array_key_exists( $effect, self::presets() ) ? $effect : 'none';
        }

        public static function sanitize_amount( $amount ): int {
            return max( 0, min( 100, absint( $amount ) ) );
        }

        /**
         * Report whether persistent effect rendering is available.
         *
         * @return array{available:bool,reason:string,path:string}
         */
        public static function status(): array {
            if ( ! self::process_available() ) {
                return [
                    'available' => false,
                    'reason'    => 'PHP proc_open kapalı olduğu için ses efekti işlenemiyor.',
                    'path'      => '',
                ];
            }

            $binary = self::ffmpeg_binary();
            if ( ! $binary ) {
                return [
                    'available' => false,
                    'reason'    => 'FFmpeg bulunamadı. Music Studio yönetimli FFmpeg kurulumu veya AGFO_AIM_FFMPEG_PATH kullanılabilir.',
                    'path'      => '',
                ];
            }

            return [
                'available' => true,
                'reason'    => 'FFmpeg hazır; efekt nihai ses dosyasına kalıcı olarak uygulanır.',
                'path'      => $binary,
            ];
        }

        /**
         * Apply a reverb/echo preset and return a new MP3 temp file.
         *
         * The original file is deleted only after a successful render.
         *
         * @return array{temp_file:string,mime:string,effect:string,amount:int}|WP_Error
         */
        public static function apply( string $input_file, string $mime, string $effect, int $amount ) {
            $effect = self::sanitize_effect( $effect );
            $amount = self::sanitize_amount( $amount );

            if ( 'none' === $effect || 0 === $amount ) {
                return [
                    'temp_file' => $input_file,
                    'mime'      => $mime,
                    'effect'    => 'none',
                    'amount'    => 0,
                ];
            }

            if ( ! is_file( $input_file ) || ! is_readable( $input_file ) ) {
                return new WP_Error( 'agfo_audio_effect_input', 'Efekt uygulanacak ses dosyası bulunamadı.' );
            }

            $status = self::status();
            if ( empty( $status['available'] ) ) {
                return new WP_Error( 'agfo_audio_effect_unavailable', (string) $status['reason'] );
            }

            $output = self::temp_output_file();
            if ( is_wp_error( $output ) ) {
                return $output;
            }

            $filter = self::filter_graph( $effect, $amount );
            $result = self::run_process(
                [
                    (string) $status['path'],
                    '-hide_banner',
                    '-loglevel',
                    'error',
                    '-nostdin',
                    '-y',
                    '-i',
                    $input_file,
                    '-vn',
                    '-filter_complex',
                    $filter,
                    '-map',
                    '[out]',
                    '-ar',
                    '44100',
                    '-ac',
                    '2',
                    '-c:a',
                    'libmp3lame',
                    '-b:a',
                    '192k',
                    $output,
                ],
                180
            );

            if ( is_wp_error( $result ) ) {
                @unlink( $output ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
                return $result;
            }
            if ( ! is_file( $output ) || filesize( $output ) < 128 ) {
                @unlink( $output ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
                return new WP_Error( 'agfo_audio_effect_output', 'FFmpeg efektli ses dosyasını oluşturamadı.' );
            }

            @unlink( $input_file ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
            return [
                'temp_file' => $output,
                'mime'      => 'audio/mpeg',
                'effect'    => $effect,
                'amount'    => $amount,
            ];
        }

        private static function filter_graph( string $effect, int $amount ): string {
            $wet = max( 0.02, min( 1.20, $amount / 100 ) );

            switch ( $effect ) {
                case 'soft_echo':
                    $delays = '175|350';
                    $decays = '0.30|0.16';
                    $wet   *= 0.95;
                    break;
                case 'hall':
                    $delays = '85|170|320';
                    $decays = '0.38|0.25|0.14';
                    $wet   *= 0.85;
                    break;
                case 'warm_room':
                default:
                    $delays = '55|95';
                    $decays = '0.24|0.14';
                    $wet   *= 0.65;
                    break;
            }

            return sprintf(
                '[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,highpass=f=65,asplit=2[dry][wet];' .
                '[wet]aecho=0.80:0.62:%s:%s,highpass=f=105,volume=%.6F[wetfx];' .
                '[dry][wetfx]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.95:attack=5:release=100[out]',
                $delays,
                $decays,
                $wet
            );
        }

        private static function ffmpeg_binary() {
            $configured = defined( 'AGFO_AIM_FFMPEG_PATH' ) ? (string) AGFO_AIM_FFMPEG_PATH : '';
            if ( '' === $configured && defined( 'AGFO_MS_FFMPEG_PATH' ) ) {
                $configured = (string) AGFO_MS_FFMPEG_PATH;
            }
            $configured = (string) apply_filters( 'agfo_ai_ffmpeg_path', $configured );

            $managed_default = trailingslashit( dirname( untrailingslashit( ABSPATH ) ) ) . 'agfo-tools/ffmpeg/current/bin/ffmpeg';
            $candidates      = array_filter(
                [
                    $configured,
                    class_exists( 'AGFO_MS_FFmpeg_Installer' ) ? AGFO_MS_FFmpeg_Installer::managed_ffmpeg_path() : '',
                    $managed_default,
                    '/usr/bin/ffmpeg',
                    '/usr/local/bin/ffmpeg',
                    '/opt/homebrew/bin/ffmpeg',
                ]
            );

            foreach ( $candidates as $candidate ) {
                $real = realpath( (string) $candidate );
                if ( false !== $real && is_file( $real ) && is_executable( $real ) ) {
                    return wp_normalize_path( $real );
                }
            }
            return false;
        }

        private static function process_available(): bool {
            if ( ! function_exists( 'proc_open' ) ) {
                return false;
            }
            $disabled = array_map( 'trim', explode( ',', (string) ini_get( 'disable_functions' ) ) );
            return ! in_array( 'proc_open', $disabled, true );
        }

        /**
         * @return string|WP_Error
         */
        private static function temp_output_file() {
            if ( ! function_exists( 'wp_tempnam' ) ) {
                $file_api = ABSPATH . 'wp-admin/includes/file.php';
                if ( is_readable( $file_api ) ) {
                    require_once $file_api;
                }
            }
            if ( ! function_exists( 'wp_tempnam' ) ) {
                return new WP_Error( 'agfo_audio_effect_temp', 'WordPress geçici dosya API’si yüklenemedi.' );
            }

            $base = wp_tempnam( 'agfo-tts-effect' );
            if ( ! $base ) {
                return new WP_Error( 'agfo_audio_effect_temp', 'Efektli ses için geçici dosya oluşturulamadı.' );
            }
            @unlink( $base ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
            return $base . '.mp3';
        }

        /**
         * Run FFmpeg with the given arguments — the plugin's only process launcher.
         *
         * Added in 17.1.2 so long-speech merging and audio effects share one hardened
         * runner: the executable is always the resolved FFmpeg binary (never caller input),
         * arguments are passed as an array (no shell), NUL bytes are rejected and a timeout
         * terminates runaway processes.
         *
         * @param string[] $args FFmpeg arguments without the binary.
         * @return array{stdout:string,stderr:string}|WP_Error
         */
        public static function run_ffmpeg( array $args, int $timeout = 300 ) {
            $binary = self::ffmpeg_binary();
            if ( ! $binary ) {
                return new WP_Error( 'agfo_ffmpeg_missing', 'FFmpeg bulunamadı.' );
            }
            $clean = [];
            foreach ( $args as $arg ) {
                if ( ! is_scalar( $arg ) || false !== strpos( (string) $arg, "\0" ) ) {
                    return new WP_Error( 'agfo_ffmpeg_args', 'Geçersiz FFmpeg argümanı.' );
                }
                $clean[] = (string) $arg;
            }
            return self::run_process( array_merge( [ $binary ], $clean ), max( 5, $timeout ) );
        }

        /**
         * @return array{stdout:string,stderr:string}|WP_Error
         */
        private static function run_process( array $command, int $timeout ) {
            // CHANGED 17.1.2: only the resolved FFmpeg binary may be executed.
            $binary = self::ffmpeg_binary();
            if ( ! $binary || ! isset( $command[0] ) || wp_normalize_path( (string) $command[0] ) !== $binary ) {
                return new WP_Error( 'agfo_audio_effect_process', 'Yalnız doğrulanmış FFmpeg çalıştırılabilir.' );
            }
            if ( ! self::process_available() ) {
                return new WP_Error( 'agfo_audio_effect_process', 'Sunucuda güvenli işlem çalıştırma kapalı.' );
            }

            $descriptors = [
                0 => [ 'pipe', 'r' ],
                1 => [ 'pipe', 'w' ],
                2 => [ 'pipe', 'w' ],
            ];
            $pipes       = [];
            $process     = proc_open( $command, $descriptors, $pipes, null, null, [ 'bypass_shell' => true ] );
            if ( ! is_resource( $process ) ) {
                return new WP_Error( 'agfo_audio_effect_process', 'FFmpeg işlemi başlatılamadı.' );
            }

            fclose( $pipes[0] );
            stream_set_blocking( $pipes[1], false );
            stream_set_blocking( $pipes[2], false );
            $stdout = '';
            $stderr = '';
            $start  = microtime( true );

            while ( true ) {
                $stdout .= (string) stream_get_contents( $pipes[1] );
                $stderr .= (string) stream_get_contents( $pipes[2] );
                $state   = proc_get_status( $process );
                if ( ! is_array( $state ) || empty( $state['running'] ) ) {
                    $exit_code = is_array( $state ) ? (int) $state['exitcode'] : -1;
                    break;
                }
                if ( microtime( true ) - $start > $timeout ) {
                    proc_terminate( $process, 9 );
                    fclose( $pipes[1] );
                    fclose( $pipes[2] );
                    proc_close( $process );
                    return new WP_Error( 'agfo_audio_effect_timeout', 'FFmpeg ses efekti zaman aşımına uğradı.' );
                }
                usleep( 100000 );
            }

            $stdout .= (string) stream_get_contents( $pipes[1] );
            $stderr .= (string) stream_get_contents( $pipes[2] );
            fclose( $pipes[1] );
            fclose( $pipes[2] );
            $closed = proc_close( $process );
            if ( -1 === $exit_code && is_int( $closed ) ) {
                $exit_code = $closed;
            }
            if ( 0 !== $exit_code ) {
                return new WP_Error( 'agfo_audio_effect_ffmpeg', 'FFmpeg ses efekti uygulanamadı. Sağlayıcı çağrısı tekrar edilmeyecektir.', [ 'exit_code' => $exit_code, 'stderr' => substr( $stderr, 0, 500 ) ] );
            }

            return [ 'stdout' => $stdout, 'stderr' => $stderr ];
        }
    }
}
