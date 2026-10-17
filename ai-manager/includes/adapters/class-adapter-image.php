<?php
/**
 * AGFO AI Manager — Image generation request builder.
 *
 * Added in 16.16.0. Each provider expects a different endpoint and body for
 * text-to-image, so the shape is built here rather than inside the caller.
 * The audio adapters are untouched.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) exit;

if ( ! class_exists( 'AGFO_AIM_Image_Adapter' ) ) {
    final class AGFO_AIM_Image_Adapter {

        /**
         * Curated image model catalogue per provider.
         *
         * Model discovery for image models is unreliable across providers, so the
         * dropdown is seeded from this list and the field stays editable: any
         * model id the provider accepts can be typed in.
         *
         * @return array<string,array<int,array{id:string,label:string}>>
         */
        public static function model_catalog(): array {
            return apply_filters( 'agfo_ai_image_model_catalog', [
                'openai' => [
                    [ 'id' => 'gpt-image-2',    'label' => 'GPT Image 2 (image2)' ],
                    [ 'id' => 'gpt-image-1',    'label' => 'GPT Image 1' ],
                    [ 'id' => 'dall-e-3',       'label' => 'DALL·E 3' ],
                ],
                'openrouter' => [
                    [ 'id' => 'openai/gpt-5.4-image-2',  'label' => 'OpenAI GPT-5.4 Image 2 (image2)' ],
                    [ 'id' => 'google/flash-image-2.5',  'label' => 'Google Flash Image 2.5' ],
                ],
                'gemini' => [
                    [ 'id' => 'imagen-4.0-generate-001',       'label' => 'Imagen 4' ],
                    [ 'id' => 'imagen-3.0-generate-002',       'label' => 'Imagen 3' ],
                    [ 'id' => 'gemini-2.5-flash-image',        'label' => 'Gemini 2.5 Flash Image' ],
                ],
                'fal' => [
                    [ 'id' => 'fal-ai/flux-pro/v1.1-ultra', 'label' => 'FLUX 1.1 Pro Ultra' ],
                    [ 'id' => 'fal-ai/flux/dev',            'label' => 'FLUX dev' ],
                    [ 'id' => 'fal-ai/recraft-v3',          'label' => 'Recraft V3' ],
                ],
                'minimax' => [
                    [ 'id' => 'image-01', 'label' => 'MiniMax Image-01' ],
                ],
            ] );
        }

        /**
         * Supported aspect ratios offered in the UI.
         *
         * @return array<string,array{label:string,size:string,ratio:string}>
         */
        public static function aspect_presets(): array {
            return [
                '16:9' => [ 'label' => 'Yatay 16:9 — öne çıkan görsel / YouTube', 'size' => '1536x1024', 'ratio' => '16:9' ],
                '4:3'  => [ 'label' => 'Yatay 4:3 — klasik blog',                 'size' => '1536x1024', 'ratio' => '4:3'  ],
                '1:1'  => [ 'label' => 'Kare 1:1 — sosyal medya',                 'size' => '1024x1024', 'ratio' => '1:1'  ],
                '9:16' => [ 'label' => 'Dikey 9:16 — infografik / hikâye',        'size' => '1024x1536', 'ratio' => '9:16' ],
                '3:4'  => [ 'label' => 'Dikey 3:4 — portre',                      'size' => '1024x1536', 'ratio' => '3:4'  ],
            ];
        }

        public static function default_aspect(): string {
            return '16:9';
        }

        /**
         * Resolve a provider-specific size string for an aspect key.
         */
        public static function size_for( string $provider, string $aspect ): string {
            $presets = self::aspect_presets();
            $aspect  = isset( $presets[ $aspect ] ) ? $aspect : self::default_aspect();

            if ( 'openai' === $provider ) {
                // The Images API accepts a fixed set of sizes only.
                $map = [ '16:9' => '1536x1024', '4:3' => '1536x1024', '1:1' => '1024x1024', '9:16' => '1024x1536', '3:4' => '1024x1536' ];
                return $map[ $aspect ];
            }

            return (string) $presets[ $aspect ]['size'];
        }

        /**
         * Build the request for the resolved capability config.
         *
         * @param array $config Result of agfo_get_provider_for_capability().
         * @param array $params 'prompt', 'aspect', 'quality', 'format'.
         * @return array|WP_Error [ 'endpoint', 'body' ]
         */
        public static function build_request( array $config, array $params ) {
            $provider = sanitize_key( (string) ( $config['code'] ?? '' ) );
            $model    = trim( (string) ( $config['model'] ?? '' ) );
            $prompt   = trim( (string) ( $params['prompt'] ?? '' ) );
            $aspect   = (string) ( $params['aspect'] ?? self::default_aspect() );
            $quality  = sanitize_key( (string) ( $params['quality'] ?? 'high' ) );
            $key      = (string) ( $config['key'] ?? '' );

            if ( $prompt === '' ) {
                return new WP_Error( 'agfo_image_prompt_empty', 'Görsel promptu boş.' );
            }
            if ( $model === '' ) {
                return new WP_Error( 'agfo_image_model_empty', 'Görsel modeli seçilmemiş.' );
            }

            $size  = self::size_for( $provider, $aspect );
            $ratio = self::aspect_presets()[ isset( self::aspect_presets()[ $aspect ] ) ? $aspect : self::default_aspect() ]['ratio'];

            switch ( $provider ) {
                case 'openai':
                    $body = [
                        'model'  => $model,
                        'prompt' => $prompt,
                        'n'      => 1,
                        'size'   => $size,
                    ];
                    // DALL·E 3 uses a different quality vocabulary and has no b64 default.
                    if ( stripos( $model, 'dall-e' ) !== false ) {
                        $body['quality']         = ( 'low' === $quality ) ? 'standard' : 'hd';
                        $body['response_format'] = 'b64_json';
                    } else {
                        $body['quality'] = in_array( $quality, [ 'low', 'medium', 'high' ], true ) ? $quality : 'high';
                    }
                    return [
                        'endpoint' => 'https://api.openai.com/v1/images/generations',
                        'body'     => $body,
                    ];

                case 'openrouter':
                    return [
                        'endpoint' => 'https://openrouter.ai/api/v1/chat/completions',
                        'body'     => [
                            'model'      => $model,
                            'modalities' => [ 'image', 'text' ],
                            'messages'   => [
                                [ 'role' => 'user', 'content' => $prompt ],
                            ],
                        ],
                    ];

                case 'gemini':
                    if ( stripos( $model, 'imagen' ) !== false ) {
                        $endpoint = 'https://generativelanguage.googleapis.com/v1beta/models/'
                            . rawurlencode( $model ) . ':predict?key=' . rawurlencode( $key );
                        return [
                            'endpoint' => $endpoint,
                            'body'     => [
                                'instances'  => [ [ 'prompt' => $prompt ] ],
                                'parameters' => [
                                    'sampleCount' => 1,
                                    'aspectRatio' => $ratio,
                                ],
                            ],
                        ];
                    }
                    $endpoint = 'https://generativelanguage.googleapis.com/v1beta/models/'
                        . rawurlencode( $model ) . ':generateContent?key=' . rawurlencode( $key );
                    return [
                        'endpoint' => $endpoint,
                        'body'     => [
                            'contents'         => [
                                [ 'role' => 'user', 'parts' => [ [ 'text' => $prompt ] ] ],
                            ],
                            'generationConfig' => [
                                'responseModalities' => [ 'IMAGE' ],
                                // CHANGED 16.19.0: without imageConfig Gemini image models return a square frame and the 16:9 / 9:16 choice was lost.
                                'imageConfig'        => [ 'aspectRatio' => $ratio ],
                            ],
                        ],
                    ];

                case 'fal':
                    $fal_sizes = [
                        '16:9' => 'landscape_16_9',
                        '4:3'  => 'landscape_4_3',
                        '1:1'  => 'square_hd',
                        '9:16' => 'portrait_16_9',
                        '3:4'  => 'portrait_4_3',
                    ];
                    $fal_body = [
                        'prompt'          => $prompt,
                        'image_size'      => isset( $fal_sizes[ $aspect ] ) ? $fal_sizes[ $aspect ] : 'landscape_16_9',
                        'num_images'      => 1,
                        'output_format'   => 'jpeg',
                        'enable_safety_checker' => true,
                    ];
                    // CHANGED 16.19.0: FLUX Pro Ultra ignores image_size and reads aspect_ratio instead.
                    if ( stripos( $model, 'ultra' ) !== false ) {
                        unset( $fal_body['image_size'] );
                        $fal_body['aspect_ratio'] = $ratio;
                    }
                    return [
                        'endpoint' => 'https://queue.fal.run/' . ltrim( $model, '/' ),
                        'body'     => $fal_body,
                    ];

                case 'minimax':
                    return [
                        'endpoint' => 'https://api.minimax.io/v1/image_generation',
                        'body'     => [
                            'model'           => $model,
                            'prompt'          => $prompt,
                            'aspect_ratio'    => $ratio,
                            'n'               => 1,
                            'response_format' => 'url',
                        ],
                    ];
            }

            return new WP_Error(
                'agfo_image_provider_unsupported',
                sprintf( '"%s" sağlayıcısı için görsel üretim gövdesi tanımlı değil.', $provider )
            );
        }

        /**
         * Practical prompt length budget (characters) for a provider/model.
         *
         * Added in 16.19.0. Several image models silently truncate or reject long
         * prompts: Imagen stops reading at roughly 480 tokens, FLUX encodes about
         * 512 tokens, MiniMax Image-01 accepts 1500 characters. Before 16.19.0 the
         * art direction came first and the subject last, so on those models the
         * subject was the part that got cut off.
         */
        public static function prompt_budget( string $provider, string $model ): int {
            $provider = sanitize_key( $provider );
            $lower    = strtolower( $model );

            if ( 'minimax' === $provider ) {
                $budget = 1400;
            } elseif ( 'fal' === $provider ) {
                $budget = ( strpos( $lower, 'recraft' ) !== false ) ? 950 : 1800;
            } elseif ( 'gemini' === $provider && strpos( $lower, 'imagen' ) !== false ) {
                $budget = 1800;
            } elseif ( 'openai' === $provider && strpos( $lower, 'dall-e-3' ) !== false ) {
                $budget = 3800;
            } elseif ( 'openai' === $provider && strpos( $lower, 'dall-e' ) !== false ) {
                $budget = 950;
            } else {
                $budget = 6000;
            }

            return max( 300, (int) apply_filters( 'agfo_ai_image_prompt_budget', $budget, $provider, $model ) );
        }

        /**
         * Providers that can currently produce images through this adapter.
         *
         * @return string[]
         */
        public static function supported_providers(): array {
            return [ 'openai', 'openrouter', 'gemini', 'fal', 'minimax' ];
        }
    }
}
