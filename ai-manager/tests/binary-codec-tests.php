<?php
/**
 * AGFO AI Manager 17.1.2 — Base64 codec and encryptor compatibility tests (CLI only).
 * Run from the plugin root: php tests/binary-codec-tests.php
 */
if ( PHP_SAPI !== 'cli' ) { exit; }
if ( ! defined( 'ABSPATH' ) ) { define( 'ABSPATH', sys_get_temp_dir() . '/' ); }
if ( ! defined( 'AUTH_SALT' ) ) { define( 'AUTH_SALT', 'agfo-test-salt' ); }
require_once dirname( __DIR__ ) . '/includes/core/class-binary-codec.php';

$agfo_aim_codec_pass = 0;
$agfo_aim_codec_fail = 0;
if ( ! function_exists( 'agfo_aim_codec_ok' ) ) {
    function agfo_aim_codec_ok( $cond, $name ) {
        global $agfo_aim_codec_pass, $agfo_aim_codec_fail;
        if ( $cond ) { $agfo_aim_codec_pass++; echo "PASS $name\n"; } else { $agfo_aim_codec_fail++; echo "FAIL $name\n"; }
    }
}
$C = 'AGFO_AIM_Binary_Codec';

echo 'sodium: ' . ( function_exists( 'sodium_base642bin' ) ? 'yes' : 'no' ) . "\n";
// RFC 4648 §10 test vectors: proves encode() matches standard Base64 without calling it.
$vectors = [ '' => '', 'f' => 'Zg==', 'fo' => 'Zm8=', 'foo' => 'Zm9v', 'foob' => 'Zm9vYg==', 'fooba' => 'Zm9vYmE=', 'foobar' => 'Zm9vYmFy' ];
$vec_ok  = true;
foreach ( $vectors as $plain => $b64 ) {
    if ( $C::encode( (string) $plain ) !== $b64 ) { $vec_ok = false; }
    if ( '' !== $b64 && $C::decode( $b64 ) !== (string) $plain ) { $vec_ok = false; }
}
agfo_aim_codec_ok( $vec_ok, 'B1 RFC 4648 vectors encode and decode' );
$bytes = random_bytes( 4096 ) . "\x00\xff";
$text  = $C::encode( $bytes );
agfo_aim_codec_ok( $C::decode( $text ) === $bytes, 'B2 binary round trip' );
agfo_aim_codec_ok( $C::decode( chunk_split( $text, 76, "\r\n" ) ) === $bytes, 'B3 line-wrapped input' );
agfo_aim_codec_ok( $C::decode( rtrim( strtr( $text, '+/', '-_' ), '=' ) ) === $bytes, 'B4 URL-safe, unpadded input' );
agfo_aim_codec_ok( $C::decode( 'not base64 !!' ) === null && $C::decode( '' ) === null, 'B5 invalid and empty input rejected' );
[ $mime, $payload ] = $C::split_data_uri( 'data:image/png;base64,UE5H' );
agfo_aim_codec_ok( $mime === 'image/png' && $C::decode( $payload ) === 'PNG', 'B6 data URI split' );

// Encryptor: ciphertext in the pre-17.1.2 format (standard Base64 of IV + AES output) still decrypts.
require_once dirname( __DIR__ ) . '/includes/functions.php'; // Loads AGFO_AIM_Encryptor; WordPress calls are guarded.
$enc   = new AGFO_AIM_Encryptor();
$key   = hash( 'sha256', AUTH_SALT );
$iv    = random_bytes( 16 );
$old   = $C::encode( $iv . openssl_encrypt( 'sk-test-legacy-key', 'AES-256-CBC', $key, OPENSSL_RAW_DATA, $iv ) ); // same bytes as the old base64_encode (B1)
agfo_aim_codec_ok( $enc->decrypt( $old ) === 'sk-test-legacy-key', 'B7 legacy stored key decrypts' );
agfo_aim_codec_ok( $enc->decrypt( $enc->encrypt( 'sk-new' ) ) === 'sk-new', 'B8 new key round trip' );
agfo_aim_codec_ok( $enc->decrypt( 'plain-text-key' ) === null, 'B9 non-ciphertext returns null (caller falls back)' );

echo "\n$agfo_aim_codec_pass pass / $agfo_aim_codec_fail fail\n";
exit( $agfo_aim_codec_fail ? 1 : 0 );
