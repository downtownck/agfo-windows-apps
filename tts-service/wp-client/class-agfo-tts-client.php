<?php
/**
 * AGFO TTS Client - WordPress-side client for the AGFO TTS Service (EMA Lightning).
 *
 * Drop into any AGFO plugin (AI Manager provider adapter, Academy LMS, Content Hub...).
 * Requires PHP 8.1+, WordPress 6.x. No external dependencies.
 *
 * Usage:
 *   $client = new AGFO_TTS_Client( 'http://127.0.0.1:8765', $token );
 *   $result = $client->synthesize_to_media( $post_id, $plain_text, [ 'speed' => 1.0 ] );
 *   // $result = [ 'attachment_id' => 123, 'url' => '...', 'seconds' => 412.5, 'cached' => false ]
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class AGFO_TTS_Client {

	public const META_ATTACHMENT = '_agfo_tts_attachment_id';
	public const META_HASH       = '_agfo_tts_content_hash';

	public function __construct(
		private string $endpoint,
		private string $token,
		private int $timeout = 600
	) {
		$this->endpoint = rtrim( $endpoint, '/' );
	}

	/** Health probe for the settings screen. */
	public function health(): array|WP_Error {
		$res = wp_remote_get( $this->endpoint . '/health', [
			'timeout' => 10,
			'headers' => [ 'X-AGFO-Token' => $this->token ],
		] );
		if ( is_wp_error( $res ) ) {
			return $res;
		}
		if ( 200 !== wp_remote_retrieve_response_code( $res ) ) {
			return new WP_Error( 'agfo_tts_health', 'TTS service responded ' . wp_remote_retrieve_response_code( $res ) );
		}
		return json_decode( wp_remote_retrieve_body( $res ), true ) ?: [];
	}

	/** Raw synthesis. Returns [ 'bytes' => string, 'format' => 'mp3', 'seconds' => float, 'cached' => bool ]. */
	public function synthesize( string $text, array $opts = [] ): array|WP_Error {
		$payload = array_merge( [
			'text'               => $text,
			'speed'              => 1.0,
			'pause_ms'           => 350,
			'paragraph_pause_ms' => 700,
			'format'             => 'mp3',
			'seed'               => 0,
		], $opts );

		$res = wp_remote_post( $this->endpoint . '/tts', [
			'timeout' => $this->timeout,
			'headers' => [
				'Content-Type' => 'application/json',
				'X-AGFO-Token' => $this->token,
			],
			'body'    => wp_json_encode( $payload ),
		] );
		if ( is_wp_error( $res ) ) {
			return $res;
		}
		$code = wp_remote_retrieve_response_code( $res );
		if ( 200 !== $code ) {
			return new WP_Error( 'agfo_tts_http', 'TTS service responded ' . $code . ': ' . substr( wp_remote_retrieve_body( $res ), 0, 300 ) );
		}
		return [
			'bytes'   => wp_remote_retrieve_body( $res ),
			'format'  => $payload['format'],
			'seconds' => (float) wp_remote_retrieve_header( $res, 'x-agfo-seconds' ),
			'cached'  => '1' === wp_remote_retrieve_header( $res, 'x-agfo-cached' ),
		];
	}

	/**
	 * Synthesize a post's text and store the audio in the media library.
	 * Skips the call when the content hash has not changed since the last run.
	 */
	public function synthesize_to_media( int $post_id, string $text, array $opts = [], bool $force = false ): array|WP_Error {
		$hash     = hash( 'sha256', $text . wp_json_encode( $opts ) );
		$existing = (int) get_post_meta( $post_id, self::META_ATTACHMENT, true );

		if ( ! $force && $existing && get_post_meta( $post_id, self::META_HASH, true ) === $hash && get_post( $existing ) ) {
			return [ 'attachment_id' => $existing, 'url' => wp_get_attachment_url( $existing ), 'seconds' => null, 'cached' => true ];
		}

		$audio = $this->synthesize( $text, $opts );
		if ( is_wp_error( $audio ) ) {
			return $audio;
		}

		require_once ABSPATH . 'wp-admin/includes/file.php';
		require_once ABSPATH . 'wp-admin/includes/media.php';
		require_once ABSPATH . 'wp-admin/includes/image.php';

		$filename = sanitize_file_name( 'tts-' . $post_id . '-' . substr( $hash, 0, 8 ) . '.' . $audio['format'] );
		$upload   = wp_upload_bits( $filename, null, $audio['bytes'] );
		if ( ! empty( $upload['error'] ) ) {
			return new WP_Error( 'agfo_tts_upload', $upload['error'] );
		}

		$attachment_id = wp_insert_attachment( [
			'post_mime_type' => 'mp3' === $audio['format'] ? 'audio/mpeg' : 'audio/wav',
			'post_title'     => get_the_title( $post_id ) . ' (sesli)',
			'post_content'   => '',
			'post_status'    => 'inherit',
			'post_parent'    => $post_id,
		], $upload['file'], $post_id );
		if ( is_wp_error( $attachment_id ) ) {
			return $attachment_id;
		}
		wp_update_attachment_metadata( $attachment_id, wp_generate_attachment_metadata( $attachment_id, $upload['file'] ) );

		if ( $existing && $existing !== $attachment_id ) {
			wp_delete_attachment( $existing, true );
		}
		update_post_meta( $post_id, self::META_ATTACHMENT, $attachment_id );
		update_post_meta( $post_id, self::META_HASH, $hash );

		return [
			'attachment_id' => $attachment_id,
			'url'           => $upload['url'],
			'seconds'       => $audio['seconds'],
			'cached'        => $audio['cached'],
		];
	}

	/** Turn post content into clean speakable text (strips shortcodes, HTML, code blocks). */
	public static function post_to_text( WP_Post $post ): string {
		$html = $post->post_content;
		$html = preg_replace( '#<pre.*?</pre>#is', '', $html );
		$html = preg_replace( '#<(script|style|figure|table).*?</\1>#is', '', $html );
		$html = preg_replace( '#</(p|h[1-6]|li|blockquote)>#i', "\n\n", $html );
		$html = strip_shortcodes( $html );
		$text = wp_strip_all_tags( $html );
		$text = html_entity_decode( $text, ENT_QUOTES | ENT_HTML5, 'UTF-8' );
		$text = preg_replace( "/[ \t]+/", ' ', $text );
		$text = preg_replace( "/\n{3,}/", "\n\n", $text );
		return trim( $post->post_title . ".\n\n" . $text );
	}
}
