<?php
/**
 * AGFO AI Manager — Featured image generation service.
 *
 * Added in 16.16.0. Composes the final art-direction prompt, calls the
 * resolved image provider, stores the result in the media library and
 * optionally sets it as the post thumbnail.
 *
 * CHANGED 16.19.0: Art-director step. Instead of pasting a rule list in front
 * of a flat 80-word scene summary, a chat model now reads the post, the preset
 * art direction and the operator note together and writes one descriptive
 * image prompt (subject, setting, composition, lens, light, palette, texture)
 * sized to the target model's prompt budget. Subject first, positive phrasing,
 * brief type depends on the preset (scene / cover / infographic).
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Image_Generator' ) ) {
    final class AGFO_AIM_Image_Generator {

        public const SETTINGS_KEY = 'agfo_aim_image_settings';

        public static function register_hooks(): void {
            add_action( 'wp_ajax_agfo_ai_image_generate', [ __CLASS__, 'ajax_generate' ] );
            add_action( 'wp_ajax_agfo_ai_image_set_featured', [ __CLASS__, 'ajax_set_featured' ] );
            add_action( 'wp_ajax_agfo_ai_image_preview_prompt', [ __CLASS__, 'ajax_preview_prompt' ] );
            add_action( 'admin_menu', [ __CLASS__, 'register_prompt_page' ] );
            add_action( 'admin_init', [ __CLASS__, 'handle_prompt_form' ] );
        }

        public static function required_capability(): string {
            return sanitize_key( (string) apply_filters( 'agfo_ai_image_studio_capability', 'manage_options' ) );
        }

        /* ── Settings ─────────────────────────────────────── */

        /**
         * Saved provider/model defaults for the studio.
         */
        public static function settings(): array {
            $saved = get_option( self::SETTINGS_KEY, [] );
            if ( ! is_array( $saved ) ) {
                $saved = [];
            }

            return [
                'provider' => sanitize_key( (string) ( $saved['provider'] ?? '' ) ),
                'model'    => sanitize_text_field( (string) ( $saved['model'] ?? '' ) ),
                'aspect'   => sanitize_text_field( (string) ( $saved['aspect'] ?? AGFO_AIM_Image_Adapter::default_aspect() ) ),
                'preset'   => sanitize_key( (string) ( $saved['preset'] ?? AGFO_AIM_Image_Prompt_Library::default_key() ) ),
                'quality'  => sanitize_key( (string) ( $saved['quality'] ?? 'high' ) ),
                // NEW 16.19.0: art-director step on by default.
                'art_director' => array_key_exists( 'art_director', $saved ) ? ( empty( $saved['art_director'] ) ? 0 : 1 ) : 1,
            ];
        }

        public static function save_settings( array $values ): bool {
            $current = self::settings();
            $clean   = [
                'provider' => sanitize_key( (string) ( $values['provider'] ?? $current['provider'] ) ),
                'model'    => sanitize_text_field( (string) ( $values['model'] ?? $current['model'] ) ),
                'aspect'   => sanitize_text_field( (string) ( $values['aspect'] ?? $current['aspect'] ) ),
                'preset'   => sanitize_key( (string) ( $values['preset'] ?? $current['preset'] ) ),
                'quality'  => sanitize_key( (string) ( $values['quality'] ?? $current['quality'] ) ),
                'art_director' => array_key_exists( 'art_director', $values ) ? ( empty( $values['art_director'] ) ? 0 : 1 ) : (int) $current['art_director'],
            ];
            return update_option( self::SETTINGS_KEY, $clean, false );
        }

        /**
         * Providers that support image generation and have a stored key.
         *
         * @return array<string,string> code => label
         */
        public static function available_providers(): array {
            $out      = [];
            $registry = function_exists( 'agfo_api_registry' ) ? agfo_api_registry() : [];

            foreach ( AGFO_AIM_Image_Adapter::supported_providers() as $code ) {
                if ( ! isset( $registry[ $code ] ) ) {
                    continue;
                }
                if ( function_exists( 'agfo_get_api_key' ) && empty( agfo_get_api_key( $code ) ) ) {
                    continue;
                }
                $out[ $code ] = isset( $registry[ $code ]['label'] ) ? (string) $registry[ $code ]['label'] : $code;
            }

            return $out;
        }

        /**
         * Provider/model actually used when the operator leaves the selectors alone.
         *
         * @return array{provider:string,model:string}
         */
        public static function effective_default(): array {
            $settings  = self::settings();
            $available = self::available_providers();

            $provider = $settings['provider'];
            if ( $provider === '' || ! isset( $available[ $provider ] ) ) {
                $provider = (string) ( array_key_first( $available ) ?? '' );
            }

            $model = $settings['model'];
            if ( $model === '' && $provider !== '' ) {
                $catalog = AGFO_AIM_Image_Adapter::model_catalog();
                if ( ! empty( $catalog[ $provider ][0]['id'] ) ) {
                    $model = (string) $catalog[ $provider ][0]['id'];
                }
            }

            return [ 'provider' => $provider, 'model' => $model ];
        }

        /* ── Subject brief ────────────────────────────────── */

        /**
         * Turn the post (and/or the operator note) into the image brief.
         *
         * With the art director enabled (default since 16.19.0) a chat model
         * writes the complete descriptive image prompt, guided by the preset.
         * Without it — or when the chat call fails — the method returns the
         * pre-16.19.0 style short scene summary or the raw title, never an error.
         *
         * @param int    $post_id Post to read; 0 for operator-only generation.
         * @param string $scope   'content' | 'title' | 'prompt'.
         * @param array  $context Optional since 16.19.0: 'preset', 'extra',
         *                        'provider', 'model', 'aspect', 'title_text',
         *                        'language', 'art_director' (bool).
         * @return array{brief:string,derived:bool,notes:string,art_directed:bool}
         */
        public static function build_subject_brief( int $post_id, string $scope = 'content', array $context = [] ): array {
            $post  = $post_id > 0 ? get_post( $post_id ) : null;
            $title = ( $post && 'prompt' !== $scope ) ? (string) $post->post_title : '';
            $body  = '';
            $extra = trim( (string) ( $context['extra'] ?? '' ) );

            if ( $post && ! in_array( $scope, [ 'title', 'prompt' ], true ) ) {
                $body = wp_strip_all_tags( strip_shortcodes( (string) $post->post_content ) );
                $body = trim( (string) preg_replace( '/\s+/u', ' ', $body ) );
                if ( mb_strlen( $body ) > 9000 ) {
                    $body = mb_substr( $body, 0, 9000 );
                }
            }

            $art_director = array_key_exists( 'art_director', $context )
                ? ! empty( $context['art_director'] )
                : ! empty( self::settings()['art_director'] );
            $art_director = (bool) apply_filters( 'agfo_ai_image_art_director_enabled', $art_director, $post_id, $context );

            if ( $title === '' && $body === '' && ( ! $art_director || $extra === '' ) ) {
                return [ 'brief' => '', 'derived' => false, 'notes' => 'Yazıda başlık ve içerik bulunamadı.', 'art_directed' => false ];
            }

            $fallback = $title !== '' ? $title : mb_substr( $body, 0, 400 );

            $config = function_exists( 'agfo_get_priority_api_key' ) ? agfo_get_priority_api_key() : false;
            if ( ! is_array( $config ) || empty( $config['key'] ) || empty( $config['chat_url'] ) ) {
                return [
                    'brief'        => $fallback,
                    'derived'      => false,
                    'notes'        => 'Metin modeli yapılandırılmadığı için ham başlık kullanıldı.',
                    'art_directed' => false,
                ];
            }

            if ( $art_director ) {
                $preset = AGFO_AIM_Image_Prompt_Library::get( sanitize_key( (string) ( $context['preset'] ?? '' ) ) );
                $budget = AGFO_AIM_Image_Adapter::prompt_budget( (string) ( $context['provider'] ?? '' ), (string) ( $context['model'] ?? '' ) );
                $system = self::art_director_system( $preset, $budget, $context );
                $user   = self::art_director_user( $title, $body, $extra, $context );
                $temp   = 0.8;
                $source = 'image_studio_art_director';
            } else {
                $system = implode( "\n", [
                    'You convert an article into a short visual brief for an image generation model.',
                    'Return one paragraph of at most 80 words in English describing a single concrete scene: who is in it, where they are, what they are doing, the light and the mood.',
                    'Describe only what a camera could see. Do not mention the article, the writing, the website or the reader.',
                    'Do not include any text, captions, letters or numbers in the scene.',
                    'Do not add commentary, headings, quotation marks or code fences. Return the paragraph only.',
                ] );
                $user   = "Article title:\n" . $title . "\n\nArticle body:\n" . $body;
                $temp   = 0.4;
                $source = 'image_studio_brief';
            }

            $body_payload = self::build_chat_body( $config, $system, $user, $temp );
            $headers      = array_merge(
                [ 'Content-Type' => 'application/json' ],
                is_array( $config['auth'] ?? null ) ? $config['auth'] : []
            );

            $response = agfo_api_post(
                (string) $config['chat_url'],
                $headers,
                wp_json_encode( $body_payload ),
                [
                    'timeout'       => 240,
                    'provider_code' => sanitize_key( (string) $config['code'] ),
                    'model'         => (string) $config['model'],
                    'capability'    => 'chat',
                    'source'        => $source,
                ]
            );

            $text = self::clean_brief( self::extract_chat_text( $response, sanitize_key( (string) $config['code'] ) ) );
            if ( $text === '' ) {
                $fallback_brief = $fallback !== '' ? $fallback : $extra;
                return [
                    'brief'        => $fallback_brief,
                    'derived'      => false,
                    'notes'        => 'Görsel özeti üretilemedi; başlık kullanıldı.',
                    'art_directed' => false,
                ];
            }

            return [ 'brief' => $text, 'derived' => true, 'notes' => '', 'art_directed' => $art_director ];
        }

        /**
         * Strip wrappers chat models like to add around a prompt.
         */
        private static function clean_brief( string $text ): string {
            $text = trim( $text );
            $text = (string) preg_replace( '/^```[a-z]*\s*|\s*```$/iu', '', $text );
            $text = (string) preg_replace( '/^(final\s+)?(image\s+)?prompt\s*:\s*/iu', '', $text );
            if ( mb_strlen( $text ) > 1 && '"' === mb_substr( $text, 0, 1 ) && '"' === mb_substr( $text, -1 ) && mb_substr_count( $text, '"' ) === 2 ) {
                $text = mb_substr( $text, 1, -1 );
            }
            return trim( $text );
        }

        /**
         * Target length of the art-directed prompt, in English words.
         */
        private static function target_words( int $budget, string $mode ): int {
            $chars = max( 400, $budget - 320 );
            $words = (int) floor( $chars / 6.5 );
            $cap   = ( 'infographic' === $mode ) ? 320 : 230;
            return max( 60, min( $cap, $words ) );
        }

        /**
         * System prompt for the art-director step.
         */
        public static function art_director_system( array $preset, int $budget, array $context = [] ): string {
            $mode       = in_array( $preset['mode'] ?? 'scene', AGFO_AIM_Image_Prompt_Library::MODES, true ) ? (string) $preset['mode'] : 'scene';
            $words      = self::target_words( $budget, $mode );
            $aspect     = (string) ( $context['aspect'] ?? $preset['aspect'] );
            $title_text = trim( (string) ( $context['title_text'] ?? '' ) );
            $language   = trim( (string) ( $context['language'] ?? '' ) );
            $allow_text = ! empty( $preset['allow_text'] );

            $lines = [];

            if ( 'infographic' === $mode ) {
                $lines[] = 'You are a senior information designer. You turn a source text into a precise layout brief for an image generation model that will draw a finished infographic.';
                $lines[] = '';
                $lines[] = 'METHOD (think silently, output only the final brief):';
                $lines[] = '1. Extract the core message, then a headline of at most 8 words and a one-sentence summary of at most 16 words.';
                $lines[] = '2. Choose 3 to 6 information blocks. Each gets a heading of 2 to 4 words, one statement of at most 10 words, and one simple flat icon described in a few words.';
                $lines[] = '3. Use only numbers, dates and facts that appear in the source. Never invent figures. If the source has numbers, design one chart, counter or timeline around them.';
                $lines[] = '4. End with a takeaway line of at most 10 words.';
                $lines[] = '5. Keep the total visible text under 90 words: image models misspell long text.';
            } elseif ( 'cover' === $mode ) {
                $lines[] = 'You are the art director of a record label. You turn a song (lyrics and title) into one precise prompt for an image generation model that will produce a finished cover with typography.';
                $lines[] = '';
                $lines[] = 'METHOD (think silently, output only the final prompt):';
                $lines[] = '1. Detect the language of the lyrics and the musical and cultural world they belong to.';
                $lines[] = '2. Find the single strongest image the song leaves behind — a moment, a place, a light. Silently consider three concepts and keep the one that is most specific and emotionally true, not the most literal.';
                $lines[] = '3. Build the scene with concrete cultural detail (place, architecture of homes and streets, costume, instrument, colour, light) instead of generic "ethnic" decoration.';
                $lines[] = '4. Plan the typography: where the text sits, typeface character (for example elegant high-contrast serif, or heavy clean sans-serif), colour and size relationship between title and credit line.';
            } else {
                $lines[] = 'You are a senior photo editor and art director at a quality magazine. You turn a text into one precise prompt for an image generation model.';
                $lines[] = '';
                $lines[] = 'METHOD (think silently, output only the final prompt):';
                $lines[] = '1. Identify the central idea of the text — the question or tension underneath it, not just its surface topic.';
                $lines[] = '2. Silently draft three visual concepts: a literal one, a human-moment one, and a visual-metaphor one grounded in reality. Discard any that is a stock-photo cliché. Keep the concept that is the most specific and surprising while still being instantly connected to the text.';
                $lines[] = '3. Make every element concrete: a believable person (approximate age, clothing, posture, expression), a real place with material detail, an exact moment in time.';
            }

            $lines[] = '';
            $lines[] = 'ART DIRECTION FOR THIS PRESET (follow it; it describes the look, not the subject):';
            $lines[] = (string) $preset['prompt'];
            $lines[] = '';
            $lines[] = 'NON-NEGOTIABLE CONTENT RULES:';
            $lines[] = AGFO_AIM_Image_Prompt_Library::mandatory_guardrails();
            $lines[] = 'Honour these rules by simply leaving such elements out. Never name a forbidden element in the prompt, not even negatively: image models tend to draw whatever is named.';
            $lines[] = '';
            $lines[] = 'OUTPUT FORMAT:';

            if ( 'infographic' === $mode ) {
                $lines[] = '- Write a layout specification of about ' . $words . ' words in English, top to bottom: canvas and background, header, each block in order with its icon and its exact text, the chart or process area, footer takeaway, then typography and palette.';
                $lines[] = '- Put every piece of visible text in double quotes, exactly as it must appear, in ' . ( $language !== '' ? $language : 'the language of the source text' ) . '. Check spelling, including diacritics.';
            } else {
                $lines[] = '- Write one flowing paragraph of about ' . $words . ' words in English, in this order: main subject and action; setting with specific detail; composition (shot size, camera angle, placement, negative space); camera and lens; lighting (source, direction, time of day, quality); colour palette and grade (name two or three colours); texture and realism cues; the mood in a few words.';
                $lines[] = '- Use concrete visual nouns and adjectives. Avoid empty quality words such as "stunning", "beautiful", "masterpiece", "8k", "ultra-detailed", "hyperrealistic".';
                $lines[] = '- Describe what should be present, never what should be absent.';

                if ( 'cover' === $mode || $allow_text ) {
                    $lines[] = '- Describe the typography inside the paragraph. Every piece of visible text goes in double quotes, exactly as it must appear, spelled correctly with its diacritics.';
                    $lines[] = $language !== ''
                        ? '- Language of all visible text: ' . $language . '.'
                        : '- Language of all visible text: the language of the source text or lyrics.';
                    if ( $title_text !== '' ) {
                        $lines[] = '- The title must be exactly: "' . $title_text . '"';
                    }
                } else {
                    $lines[] = '- The image carries no lettering at all; simply do not describe any signs, captions, labels or printed matter.';
                }
            }

            $lines[] = '- The frame is ' . $aspect . '; compose for that shape.';
            $lines[] = '- If an operator note is supplied it has priority over the art direction (but never over the content rules). If the operator note is already a detailed image prompt, keep its intent and wording and only add what is missing.';
            $lines[] = '- Return only the prompt text: no title, no preamble, no quotation marks around the whole answer, no markdown, no explanation.';

            return (string) apply_filters( 'agfo_ai_image_art_director_system', implode( "\n", $lines ), $preset, $budget, $context );
        }

        /**
         * User message for the art-director step.
         */
        private static function art_director_user( string $title, string $body, string $extra, array $context ): string {
            $parts = [];
            if ( $title !== '' ) {
                $parts[] = "SOURCE TITLE:\n" . $title;
            }
            if ( $body !== '' ) {
                $parts[] = "SOURCE TEXT:\n" . $body;
            }
            if ( $extra !== '' ) {
                $parts[] = "OPERATOR NOTE (highest priority):\n" . $extra;
            }
            if ( $title === '' && $body === '' ) {
                $parts[] = 'There is no source text. Build the prompt from the operator note alone.';
            }
            return implode( "\n\n", $parts );
        }

        /**
         * Provider-shaped chat body for the brief request.
         */
        private static function build_chat_body( array $config, string $system, string $user, float $temperature = 0.4 ): array {
            $code  = sanitize_key( (string) $config['code'] );
            $model = (string) $config['model'];

            if ( 'gemini' === $code ) {
                return [
                    'systemInstruction' => [ 'parts' => [ [ 'text' => $system ] ] ],
                    'contents'          => [ [ 'role' => 'user', 'parts' => [ [ 'text' => $user ] ] ] ],
                    // CHANGED 16.19.0: 700 tokens was exhausted by Gemini 2.5 thinking, leaving an empty brief and a raw-title fallback.
                    'generationConfig'  => [ 'temperature' => $temperature, 'maxOutputTokens' => 4096 ],
                ];
            }

            if ( 'claude' === $code ) {
                $claude = [
                    'model'      => $model,
                    'system'     => $system,
                    'max_tokens' => 1500,
                    'messages'   => [ [ 'role' => 'user', 'content' => $user ] ],
                ];
                // CHANGED 16.19.0: temperature only when the live probe confirms support.
                if ( function_exists( 'agfo_model_temperature_status' ) && 'supported' === agfo_model_temperature_status( $code, $model ) ) {
                    $claude['temperature'] = $temperature;
                }
                return $claude;
            }

            $body = [
                'model'      => $model,
                'messages'   => [
                    [ 'role' => 'system', 'content' => $system ],
                    [ 'role' => 'user', 'content' => $user ],
                ],
                'max_tokens' => 1500,
            ];

            // Reasoning models need an explicit effort profile; the transport layer
            // strips the parameter again if the provider rejects it.
            if ( function_exists( 'agfo_openai_model_is_reasoning' ) && agfo_openai_model_is_reasoning( $model ) ) {
                $body['reasoning_effort'] = 'low';
                // CHANGED 16.19.0: reasoning tokens count against the limit; 700 left the visible answer empty.
                $body['max_tokens'] = 6000;
            } else {
                $body['temperature'] = $temperature;
            }

            return $body;
        }

        /**
         * Read the assistant text out of a chat response.
         */
        private static function extract_chat_text( $response, string $provider_code ): string {
            if ( ! is_array( $response ) || ! isset( $response['body'] ) ) {
                return '';
            }
            $code = (int) ( $response['http_code'] ?? 0 );
            if ( $code < 200 || $code >= 300 ) {
                return '';
            }

            $data = json_decode( (string) $response['body'], true );
            if ( ! is_array( $data ) ) {
                return '';
            }

            if ( 'gemini' === $provider_code ) {
                $parts = $data['candidates'][0]['content']['parts'] ?? [];
                $text  = '';
                if ( is_array( $parts ) ) {
                    foreach ( $parts as $part ) {
                        if ( isset( $part['text'] ) && is_string( $part['text'] ) ) {
                            $text .= $part['text'];
                        }
                    }
                }
                return trim( $text );
            }

            if ( 'claude' === $provider_code ) {
                $blocks = $data['content'] ?? [];
                $text   = '';
                if ( is_array( $blocks ) ) {
                    foreach ( $blocks as $block ) {
                        if ( isset( $block['text'] ) && is_string( $block['text'] ) ) {
                            $text .= $block['text'];
                        }
                    }
                }
                return trim( $text );
            }

            $content = $data['choices'][0]['message']['content'] ?? '';
            if ( is_array( $content ) ) {
                $text = '';
                foreach ( $content as $chunk ) {
                    if ( isset( $chunk['text'] ) && is_string( $chunk['text'] ) ) {
                        $text .= $chunk['text'];
                    }
                }
                $content = $text;
            }

            return is_string( $content ) ? trim( $content ) : '';
        }

        /* ── Prompt composition ───────────────────────────── */

        /**
         * Decide whether and how to build a brief for the given scope.
         *
         * Added in 16.19.0. 'prompt' scope used to skip the brief entirely and send
         * the operator's words raw; with the art director on, a short operator note
         * is now expanded into a full descriptive prompt as well.
         *
         * @return array{subject:string,notes:string,art_directed:bool}
         */
        private static function resolve_subject( int $post_id, string $scope, array $context ): array {
            $extra = trim( (string) ( $context['extra'] ?? '' ) );
            $ad_on = (bool) apply_filters( 'agfo_ai_image_art_director_enabled', ! empty( self::settings()['art_director'] ), $post_id, $context );

            if ( 'prompt' === $scope && ( ! $ad_on || $extra === '' ) ) {
                return [ 'subject' => '', 'notes' => '', 'art_directed' => false ];
            }

            $context['art_director'] = $ad_on;
            $brief = self::build_subject_brief( $post_id, $scope, $context );

            return [
                'subject'      => (string) $brief['brief'],
                'notes'        => (string) $brief['notes'],
                'art_directed' => ! empty( $brief['art_directed'] ),
            ];
        }

        /**
         * Assemble the final prompt sent to the image model.
         *
         * @param array $args 'preset', 'aspect', 'extra', 'subject', 'title_text',
         *                    'language'; since 16.19.0 also 'art_directed' (bool),
         *                    'provider' and 'model' (for the length budget).
         */
        public static function compose_prompt( array $args ): string {
            $preset     = AGFO_AIM_Image_Prompt_Library::get( sanitize_key( (string) ( $args['preset'] ?? '' ) ) );
            $aspect     = (string) ( ( $args['aspect'] ?? '' ) !== '' ? $args['aspect'] : $preset['aspect'] );
            $extra      = trim( (string) ( $args['extra'] ?? '' ) );
            $subject    = trim( (string) ( $args['subject'] ?? '' ) );
            $title_text = trim( (string) ( $args['title_text'] ?? '' ) );
            $language   = trim( (string) ( $args['language'] ?? '' ) );
            $provider   = sanitize_key( (string) ( $args['provider'] ?? '' ) );
            $model      = (string) ( $args['model'] ?? '' );
            $budget     = AGFO_AIM_Image_Adapter::prompt_budget( $provider, $model );

            // CHANGED 16.19.0: the art director already folded preset, operator note and
            // rules into $subject. Only a short technical tail is appended.
            if ( ! empty( $args['art_directed'] ) && $subject !== '' ) {
                $tail = [ 'Aspect ratio ' . $aspect . '.' ];
                if ( empty( $preset['allow_text'] ) ) {
                    if ( 'fal' !== $provider ) {
                        $tail[] = 'No text, letters or watermarks anywhere in the image.';
                    }
                } elseif ( $title_text !== '' && mb_strpos( $subject, $title_text ) === false ) {
                    $tail[] = 'Title text, spelled exactly: "' . $title_text . '".';
                }
                $tail[] = AGFO_AIM_Image_Prompt_Library::compact_guardrails( $provider );
                $tail_text = implode( ' ', $tail );

                $room   = max( 200, $budget - mb_strlen( $tail_text ) - 2 );
                $prompt = self::fit_text( $subject, $room ) . "\n\n" . $tail_text;

                return (string) apply_filters( 'agfo_ai_image_final_prompt', $prompt, $args, $preset );
            }

            // Plain composition (art director off or unavailable). Subject comes first
            // so that length-limited models read it before anything is truncated.
            $head   = [];
            $head[] = 'SUBJECT:';
            $head[] = $subject !== '' ? $subject : $extra;
            if ( $extra !== '' && $subject !== '' ) {
                $head[] = '';
                $head[] = 'OPERATOR INSTRUCTION (highest priority after the mandatory rules):';
                $head[] = $extra;
            }

            $tail   = [];
            $tail[] = 'OUTPUT PARAMETERS:';
            $tail[] = '- Aspect ratio: ' . $aspect;
            if ( empty( $preset['allow_text'] ) ) {
                $tail[] = '- Text in image: none. No letters, numbers, captions or watermarks.';
            } else {
                $tail[] = $title_text !== ''
                    ? '- Text in image: render exactly this title, spelled correctly and highly legible: "' . $title_text . '"'
                    : '- Text in image: allowed where the art direction calls for it. Keep every word correctly spelled and legible.';
                if ( $language !== '' ) {
                    $tail[] = '- Language of any text in the image: ' . $language;
                }
            }
            $tail[] = '';
            $tail[] = $budget >= 3000
                ? AGFO_AIM_Image_Prompt_Library::mandatory_guardrails()
                : AGFO_AIM_Image_Prompt_Library::compact_guardrails( $provider );

            $head_text = implode( "\n", $head );
            $tail_text = implode( "\n", $tail );
            $art_room  = $budget - mb_strlen( $head_text ) - mb_strlen( $tail_text ) - 20;

            if ( $art_room < 120 ) {
                $head_text = self::fit_text( $head_text, max( 200, $budget - mb_strlen( $tail_text ) - 4 ) );
                $prompt    = $head_text . "\n\n" . $tail_text;
            } else {
                $prompt = $head_text . "\n\nART DIRECTION:\n" . self::fit_text( (string) $preset['prompt'], $art_room ) . "\n\n" . $tail_text;
            }

            return (string) apply_filters( 'agfo_ai_image_final_prompt', $prompt, $args, $preset );
        }

        /**
         * Shorten text to a character budget at a sentence or word boundary.
         */
        private static function fit_text( string $text, int $limit ): string {
            $text = trim( $text );
            if ( $limit < 1 || mb_strlen( $text ) <= $limit ) {
                return $text;
            }
            $cut  = mb_substr( $text, 0, $limit );
            $stop = max( (int) mb_strrpos( $cut, '. ' ), (int) mb_strrpos( $cut, ".\n" ) );
            if ( $stop > (int) ( $limit * 0.6 ) ) {
                return mb_substr( $cut, 0, $stop + 1 );
            }
            $space = (int) mb_strrpos( $cut, ' ' );
            return rtrim( $space > 0 ? mb_substr( $cut, 0, $space ) : $cut, " ,;:" );
        }

        /* ── Generation ───────────────────────────────────── */

        /**
         * Generate an image and store it in the media library.
         *
         * @param array $args 'post_id', 'preset', 'aspect', 'provider', 'model',
         *                    'extra', 'subject_scope', 'quality', 'title_text',
         *                    'language', 'set_featured'.
         * @return array|WP_Error
         */
        public static function generate( array $args ) {
            if ( class_exists( 'AGFO_AIM_Kill_Switch' ) && ! AGFO_AIM_Kill_Switch::is_enabled( 'image_generate' ) ) {
                return new WP_Error( 'agfo_image_disabled', 'Görsel üretimi yönetici tarafından geçici olarak kapatıldı.' );
            }

            $post_id = isset( $args['post_id'] ) ? (int) $args['post_id'] : 0;
            $scope   = sanitize_key( (string) ( $args['subject_scope'] ?? 'content' ) );
            $extra   = trim( (string) ( $args['extra'] ?? '' ) );

            $preset_key = sanitize_key( (string) ( $args['preset'] ?? AGFO_AIM_Image_Prompt_Library::default_key() ) );
            $preset     = AGFO_AIM_Image_Prompt_Library::get( $preset_key );
            $aspects    = array_keys( AGFO_AIM_Image_Adapter::aspect_presets() );
            $aspect     = (string) ( $args['aspect'] ?? $preset['aspect'] );
            if ( ! in_array( $aspect, $aspects, true ) ) {
                $aspect = (string) $preset['aspect'];
            }

            // CHANGED 16.19.0: provider/model are resolved before the brief so the
            // art director can size the prompt for the target model.
            $defaults = self::effective_default();
            $provider = sanitize_key( (string) ( $args['provider'] ?? '' ) );
            if ( $provider === '' ) {
                $provider = $defaults['provider'];
            }
            $model = trim( (string) ( $args['model'] ?? '' ) );
            if ( $model === '' ) {
                $model = $defaults['model'];
            }

            // CHANGED 16.19.0: checked before the brief so no chat call is spent when no image provider exists.
            if ( $provider === '' ) {
                return new WP_Error( 'agfo_image_no_provider', 'Görsel üretimi için anahtarı tanımlı bir sağlayıcı bulunamadı.' );
            }

            $resolved = self::resolve_subject( $post_id, $scope, [
                'preset'     => $preset_key,
                'extra'      => $extra,
                'provider'   => $provider,
                'model'      => $model,
                'aspect'     => $aspect,
                'title_text' => (string) ( $args['title_text'] ?? '' ),
                'language'   => (string) ( $args['language'] ?? '' ),
            ] );
            $subject      = $resolved['subject'];
            $notes        = $resolved['notes'];
            $art_directed = $resolved['art_directed'];

            if ( $subject === '' && $extra === '' ) {
                return new WP_Error( 'agfo_image_no_subject', 'Görsel için konu bulunamadı. Yazıya başlık veya içerik ekleyin ya da bir prompt yazın.' );
            }

            $prompt = self::compose_prompt( [
                'preset'       => $preset_key,
                'aspect'       => $aspect,
                'extra'        => $extra,
                'subject'      => $subject,
                'title_text'   => (string) ( $args['title_text'] ?? '' ),
                'language'     => (string) ( $args['language'] ?? '' ),
                'art_directed' => $art_directed,
                'provider'     => $provider,
                'model'        => $model,
            ] );

            $config = agfo_get_provider_for_capability( 'image_generate', [
                'provider' => $provider,
                'model'    => $model,
            ] );
            if ( is_wp_error( $config ) ) {
                return $config;
            }

            $request = AGFO_AIM_Image_Adapter::build_request( $config, [
                'prompt'  => $prompt,
                'aspect'  => $aspect,
                'quality' => sanitize_key( (string) ( $args['quality'] ?? 'high' ) ),
            ] );
            if ( is_wp_error( $request ) ) {
                return $request;
            }

            $headers = array_merge(
                [ 'Content-Type' => 'application/json' ],
                is_array( $config['auth'] ?? null ) ? $config['auth'] : []
            );

            $response = agfo_api_post(
                (string) $request['endpoint'],
                $headers,
                wp_json_encode( $request['body'] ),
                [
                    'timeout'       => 180,
                    'poll_budget'   => 600,
                    'provider_code' => sanitize_key( (string) $config['code'] ),
                    'model'         => (string) $config['model'],
                    'capability'    => 'image_generate',
                    'source'        => 'image_studio',
                ]
            );

            if ( isset( $response['error'] ) ) {
                return new WP_Error( 'agfo_image_transport', 'Görsel sağlayıcısına ulaşılamadı: ' . (string) $response['error'] );
            }

            $http_code = (int) ( $response['http_code'] ?? 0 );
            $raw       = (string) ( $response['body'] ?? '' );

            if ( $http_code < 200 || $http_code >= 300 ) {
                return new WP_Error(
                    'agfo_image_http',
                    sprintf( 'Görsel üretilemedi. HTTP %d. %s', $http_code, self::provider_error_message( $raw ) )
                );
            }

            $payload = agfo_ai_extract_image_from_response( $raw );
            if ( is_wp_error( $payload ) ) {
                return $payload;
            }

            $post_title = $post_id > 0 ? (string) get_the_title( $post_id ) : '';
            $stored     = agfo_ai_store_generated_image(
                $payload,
                [
                    'title'        => $post_title !== '' ? $post_title : 'AGFO AI Görsel',
                    'post_id'      => $post_id,
                    'alt'          => $post_title,
                    'source'       => 'agfo-ai-manager/image-studio',
                    'prompt'       => $prompt,
                    'set_featured' => ! empty( $args['set_featured'] ),
                ]
            );
            if ( is_wp_error( $stored ) ) {
                return $stored;
            }

            $stored['prompt']   = $prompt;
            $stored['provider'] = (string) $config['provider_name'];
            $stored['model']    = (string) $config['model'];
            $stored['aspect']   = $aspect;
            $stored['preset']   = $preset['label'];
            $stored['notes']    = $notes;
            $stored['derived']  = ( $subject !== '' );

            do_action( 'agfo_ai_image_generated', $stored, $args );

            return $stored;
        }

        /**
         * Readable fragment of a provider error body, never the raw payload.
         */
        private static function provider_error_message( string $raw ): string {
            $data = json_decode( $raw, true );
            if ( is_array( $data ) ) {
                $candidates = [
                    $data['error']['message'] ?? null,
                    $data['error'] ?? null,
                    $data['message'] ?? null,
                    $data['detail'] ?? null,
                    $data['base_resp']['status_msg'] ?? null,
                ];
                foreach ( $candidates as $candidate ) {
                    if ( is_string( $candidate ) && $candidate !== '' ) {
                        return mb_substr( sanitize_text_field( $candidate ), 0, 300 );
                    }
                }
            }
            return mb_substr( sanitize_text_field( wp_strip_all_tags( $raw ) ), 0, 200 );
        }

        /* ── AJAX ─────────────────────────────────────────── */

        public static function ajax_generate(): void {
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );
            if ( ! current_user_can( self::required_capability() ) ) {
                wp_send_json_error( [ 'message' => 'Bu işlem için yetkiniz yok.' ], 403 );
            }

            $post_id = isset( $_POST['post_id'] ) ? absint( $_POST['post_id'] ) : 0;
            if ( $post_id > 0 && ! current_user_can( 'edit_post', $post_id ) ) {
                wp_send_json_error( [ 'message' => 'Bu yazıyı düzenleme yetkiniz yok.' ], 403 );
            }

            $args = [
                'post_id'       => $post_id,
                'preset'        => sanitize_key( (string) ( $_POST['preset'] ?? '' ) ),
                'aspect'        => sanitize_text_field( (string) ( $_POST['aspect'] ?? '' ) ),
                'provider'      => sanitize_key( (string) ( $_POST['provider'] ?? '' ) ),
                'model'         => sanitize_text_field( (string) ( $_POST['model'] ?? '' ) ),
                'extra'         => sanitize_textarea_field( (string) wp_unslash( $_POST['extra'] ?? '' ) ),
                'subject_scope' => sanitize_key( (string) ( $_POST['subject_scope'] ?? 'content' ) ),
                'quality'       => sanitize_key( (string) ( $_POST['quality'] ?? 'high' ) ),
                'title_text'    => sanitize_text_field( (string) wp_unslash( $_POST['title_text'] ?? '' ) ),
                'language'      => sanitize_text_field( (string) wp_unslash( $_POST['language'] ?? '' ) ),
                'set_featured'  => ! empty( $_POST['set_featured'] ),
            ];

            if ( mb_strlen( (string) $args['extra'] ) > 4000 ) {
                wp_send_json_error( [ 'message' => 'Ek prompt en fazla 4.000 karakter olabilir.' ], 400 );
            }

            self::save_settings( [
                'provider' => $args['provider'],
                'model'    => $args['model'],
                'aspect'   => $args['aspect'],
                'preset'   => $args['preset'],
                'quality'  => $args['quality'],
            ] );

            $result = self::generate( $args );
            if ( is_wp_error( $result ) ) {
                wp_send_json_error( [ 'message' => $result->get_error_message(), 'code' => $result->get_error_code() ], 400 );
            }

            wp_send_json_success( $result );
        }

        public static function ajax_set_featured(): void {
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );
            if ( ! current_user_can( self::required_capability() ) ) {
                wp_send_json_error( [ 'message' => 'Bu işlem için yetkiniz yok.' ], 403 );
            }

            $post_id       = isset( $_POST['post_id'] ) ? absint( $_POST['post_id'] ) : 0;
            $attachment_id = isset( $_POST['attachment_id'] ) ? absint( $_POST['attachment_id'] ) : 0;

            if ( $post_id < 1 || $attachment_id < 1 ) {
                wp_send_json_error( [ 'message' => 'Yazı veya görsel kimliği eksik.' ], 400 );
            }
            if ( ! current_user_can( 'edit_post', $post_id ) ) {
                wp_send_json_error( [ 'message' => 'Bu yazıyı düzenleme yetkiniz yok.' ], 403 );
            }
            if ( 'attachment' !== get_post_type( $attachment_id ) || ! wp_attachment_is_image( $attachment_id ) ) {
                wp_send_json_error( [ 'message' => 'Seçilen kayıt bir görsel değil.' ], 400 );
            }

            $ok = set_post_thumbnail( $post_id, $attachment_id );
            if ( ! $ok ) {
                wp_send_json_error( [ 'message' => 'Öne çıkan görsel atanamadı.' ], 400 );
            }

            $thumb = wp_get_attachment_image_src( $attachment_id, 'medium' );

            wp_send_json_success( [
                'attachment_id' => $attachment_id,
                'thumb_url'     => is_array( $thumb ) && ! empty( $thumb[0] ) ? (string) $thumb[0] : (string) wp_get_attachment_url( $attachment_id ),
                'html'          => _wp_post_thumbnail_html( $attachment_id, $post_id ),
            ] );
        }

        public static function ajax_preview_prompt(): void {
            check_ajax_referer( 'agfo_ajax_nonce', 'nonce' );
            if ( ! current_user_can( self::required_capability() ) ) {
                wp_send_json_error( [ 'message' => 'Bu işlem için yetkiniz yok.' ], 403 );
            }

            $post_id = isset( $_POST['post_id'] ) ? absint( $_POST['post_id'] ) : 0;
            if ( $post_id > 0 && ! current_user_can( 'edit_post', $post_id ) ) {
                wp_send_json_error( [ 'message' => 'Bu yazıyı düzenleme yetkiniz yok.' ], 403 );
            }

            $scope      = sanitize_key( (string) ( $_POST['subject_scope'] ?? 'content' ) );
            $preset_key = sanitize_key( (string) ( $_POST['preset'] ?? '' ) );
            $preset     = AGFO_AIM_Image_Prompt_Library::get( $preset_key );
            $aspect     = sanitize_text_field( (string) ( $_POST['aspect'] ?? '' ) );
            if ( ! in_array( $aspect, array_keys( AGFO_AIM_Image_Adapter::aspect_presets() ), true ) ) {
                $aspect = (string) $preset['aspect'];
            }
            $extra      = sanitize_textarea_field( (string) wp_unslash( $_POST['extra'] ?? '' ) );
            $title_text = sanitize_text_field( (string) wp_unslash( $_POST['title_text'] ?? '' ) );
            $language   = sanitize_text_field( (string) wp_unslash( $_POST['language'] ?? '' ) );

            $defaults = self::effective_default();
            $provider = sanitize_key( (string) ( $_POST['provider'] ?? '' ) );
            $provider = $provider !== '' ? $provider : $defaults['provider'];
            $model    = sanitize_text_field( (string) ( $_POST['model'] ?? '' ) );
            $model    = $model !== '' ? $model : $defaults['model'];

            $resolved = self::resolve_subject( $post_id, $scope, [
                'preset'     => $preset_key,
                'extra'      => $extra,
                'provider'   => $provider,
                'model'      => $model,
                'aspect'     => $aspect,
                'title_text' => $title_text,
                'language'   => $language,
            ] );
            $notes = $resolved['notes'];

            $prompt = self::compose_prompt( [
                'preset'       => $preset_key,
                'aspect'       => $aspect,
                'extra'        => $extra,
                'subject'      => $resolved['subject'],
                'title_text'   => $title_text,
                'language'     => $language,
                'art_directed' => $resolved['art_directed'],
                'provider'     => $provider,
                'model'        => $model,
            ] );

            wp_send_json_success( [ 'prompt' => $prompt, 'notes' => $notes ] );
        }

        /* ── Prompt administration ────────────────────────── */

        public static function register_prompt_page(): void {
            add_submenu_page(
                'agfo-ai-manager',
                'Görsel Promptları',
                '🖼️ Görsel Promptları',
                self::required_capability(),
                'agfo-image-prompts',
                [ __CLASS__, 'render_prompt_page' ]
            );
        }

        public static function handle_prompt_form(): void {
            if ( ! isset( $_POST['agfo_image_prompt_action'] ) ) {
                return;
            }
            if ( ! current_user_can( self::required_capability() ) ) {
                wp_die( esc_html__( 'Bu işlem için yetkiniz yok.', 'agfo-ai-manager' ) );
            }
            check_admin_referer( 'agfo_image_prompts_save', 'agfo_image_prompts_nonce' );

            $action = sanitize_key( wp_unslash( $_POST['agfo_image_prompt_action'] ) );
            if ( 'reset' === $action ) {
                AGFO_AIM_Image_Prompt_Library::reset();
                add_settings_error( 'agfo_image_prompts', 'reset', 'Görsel promptları varsayılanlara döndürüldü.', 'updated' );
                return;
            }

            $posted = isset( $_POST['image_prompts'] ) && is_array( $_POST['image_prompts'] )
                ? wp_unslash( $_POST['image_prompts'] )
                : [];
            AGFO_AIM_Image_Prompt_Library::save_overrides( $posted );

            if ( isset( $_POST['image_defaults'] ) && is_array( $_POST['image_defaults'] ) ) {
                self::save_settings( wp_unslash( $_POST['image_defaults'] ) );
            }

            add_settings_error( 'agfo_image_prompts', 'saved', 'Görsel promptları kaydedildi.', 'updated' );
        }

        public static function render_prompt_page(): void {
            if ( ! current_user_can( self::required_capability() ) ) {
                return;
            }

            $templates = AGFO_AIM_Image_Prompt_Library::get_all();
            $defaults  = AGFO_AIM_Image_Prompt_Library::defaults();
            $aspects   = AGFO_AIM_Image_Adapter::aspect_presets();
            $providers = self::available_providers();
            $settings  = self::settings();
            $effective = self::effective_default();
            $catalog   = AGFO_AIM_Image_Adapter::model_catalog();
            ?>
            <div class="wrap agfo-image-prompts-admin">
                <h1>AGFO Görsel Promptları</h1>
                <p class="description">Klasik editördeki <strong>AI Görsel</strong> aracının kullandığı sanat yönetimi talimatlarını yönetin. Her çağrıda dini sembol, kimliklendirilebilir gerçek kişi ve marka kullanımını engelleyen zorunlu kurallar ayrıca uygulanır.</p>
                <?php settings_errors( 'agfo_image_prompts' ); ?>

                <?php if ( empty( $providers ) ) : ?>
                    <div class="notice notice-error inline"><p>Görsel üretebilen hiçbir sağlayıcı için API anahtarı tanımlı değil. OpenAI, OpenRouter, Gemini, fal.ai veya MiniMax anahtarlarından birini AGFO AI ayarlarına ekleyin.</p></div>
                <?php endif; ?>

                <form method="post">
                    <?php wp_nonce_field( 'agfo_image_prompts_save', 'agfo_image_prompts_nonce' ); ?>
                    <input type="hidden" name="agfo_image_prompt_action" value="save">

                    <h2>Varsayılan sağlayıcı ve model</h2>
                    <table class="form-table agfo-image-defaults">
                        <tr>
                            <th scope="row"><label for="agfo-image-default-provider">Sağlayıcı</label></th>
                            <td>
                                <select id="agfo-image-default-provider" name="image_defaults[provider]">
                                    <option value="">Otomatik — anahtarı olan ilk sağlayıcı</option>
                                    <?php foreach ( $providers as $code => $label ) : ?>
                                        <option value="<?php echo esc_attr( $code ); ?>" <?php selected( $settings['provider'], $code ); ?>><?php echo esc_html( $label ); ?></option>
                                    <?php endforeach; ?>
                                </select>
                            </td>
                        </tr>
                        <tr>
                            <th scope="row"><label for="agfo-image-default-model">Model</label></th>
                            <td>
                                <input id="agfo-image-default-model" type="text" class="regular-text" name="image_defaults[model]" value="<?php echo esc_attr( $settings['model'] ); ?>" list="agfo-image-model-list" placeholder="Örn. gpt-image-2">
                                <datalist id="agfo-image-model-list">
                                    <?php foreach ( $catalog as $code => $rows ) : ?>
                                        <?php foreach ( $rows as $row ) : ?>
                                            <option value="<?php echo esc_attr( $row['id'] ); ?>"><?php echo esc_attr( $code . ' — ' . $row['label'] ); ?></option>
                                        <?php endforeach; ?>
                                    <?php endforeach; ?>
                                </datalist>
                                <p class="description">Boş bırakılırsa sağlayıcının listedeki ilk modeli kullanılır. Şu anda etkin: <code><?php echo esc_html( $effective['provider'] !== '' ? $effective['provider'] . ' · ' . $effective['model'] : 'yapılandırılmadı' ); ?></code></p>
                            </td>
                        </tr>
                        <tr>
                            <th scope="row"><label for="agfo-image-default-aspect">Varsayılan oran</label></th>
                            <td>
                                <select id="agfo-image-default-aspect" name="image_defaults[aspect]">
                                    <?php foreach ( $aspects as $key => $row ) : ?>
                                        <option value="<?php echo esc_attr( $key ); ?>" <?php selected( $settings['aspect'], $key ); ?>><?php echo esc_html( $row['label'] ); ?></option>
                                    <?php endforeach; ?>
                                </select>
                            </td>
                        </tr>
                        <tr>
                            <th scope="row">Sanat yönetmeni</th>
                            <td>
                                <input type="hidden" name="image_defaults[art_director]" value="0">
                                <label><input type="checkbox" name="image_defaults[art_director]" value="1" <?php checked( ! empty( $settings['art_director'] ) ); ?>> Görsel modeline gitmeden önce metin modeli yazıyı, preset'i ve ek notu okuyup tek, betimleyici bir görsel promptu yazsın</label>
                                <p class="description">Kapalıyken eski davranış kullanılır: kısa sahne özeti + preset metni. Açıkken istek başına bir metin modeli çağrısı yapılır; prompt, seçilen görsel modelinin uzunluk sınırına göre boyutlandırılır.</p>
                            </td>
                        </tr>
                    </table>

                    <h2>Preset promptları</h2>
                    <div class="agfo-image-prompt-grid">
                        <?php foreach ( $templates as $key => $row ) : ?>
                            <section class="agfo-image-prompt-card">
                                <div class="agfo-image-prompt-head">
                                    <label for="agfo-image-label-<?php echo esc_attr( $key ); ?>"><strong><?php echo esc_html( $row['label'] ); ?></strong></label>
                                    <code><?php echo esc_html( $key ); ?></code>
                                </div>
                                <p><?php echo esc_html( $row['description'] ); ?></p>
                                <label>
                                    Görünen ad
                                    <input id="agfo-image-label-<?php echo esc_attr( $key ); ?>" type="text" name="image_prompts[<?php echo esc_attr( $key ); ?>][label]" value="<?php echo esc_attr( $row['label'] ); ?>">
                                </label>
                                <label>
                                    Varsayılan oran
                                    <select name="image_prompts[<?php echo esc_attr( $key ); ?>][aspect]">
                                        <?php foreach ( $aspects as $aspect_key => $aspect_row ) : ?>
                                            <option value="<?php echo esc_attr( $aspect_key ); ?>" <?php selected( $row['aspect'], $aspect_key ); ?>><?php echo esc_html( $aspect_row['label'] ); ?></option>
                                        <?php endforeach; ?>
                                    </select>
                                </label>
                                <label class="agfo-image-prompt-check">
                                    <input type="checkbox" name="image_prompts[<?php echo esc_attr( $key ); ?>][allow_text]" value="1" <?php checked( ! empty( $row['allow_text'] ) ); ?>>
                                    Görselde yazı kullanılabilir
                                </label>
                                <label>
                                    Prompt
                                    <textarea name="image_prompts[<?php echo esc_attr( $key ); ?>][prompt]" rows="12"><?php echo esc_textarea( $row['prompt'] ); ?></textarea>
                                </label>
                                <?php if ( isset( $defaults[ $key ] ) && ( $row['prompt'] !== $defaults[ $key ]['prompt'] || $row['label'] !== $defaults[ $key ]['label'] ) ) : ?>
                                    <small>Bu şablon özelleştirilmiş.</small>
                                <?php endif; ?>
                            </section>
                        <?php endforeach; ?>
                    </div>

                    <p class="submit">
                        <button type="submit" class="button button-primary">Kaydet</button>
                        <button type="submit" class="button" name="agfo_image_prompt_action" value="reset" onclick="return confirm('Tüm görsel promptları varsayılanlara dönsün mü?');">Promptları Sıfırla</button>
                    </p>
                </form>
                <p class="agfo-image-version">AGFO AI Manager v<?php echo esc_html( AGFO_AIM_VERSION ); ?></p>
            </div>
            <style>
                .agfo-image-prompt-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:18px}
                .agfo-image-prompt-card{background:#fff;border:1px solid #dcdcde;border-radius:10px;padding:16px}
                .agfo-image-prompt-card label{display:block;margin-top:12px;font-weight:600}
                .agfo-image-prompt-card label.agfo-image-prompt-check{font-weight:400}
                .agfo-image-prompt-card input[type=text],.agfo-image-prompt-card textarea,.agfo-image-prompt-card select{width:100%;max-width:none;margin-top:5px}
                .agfo-image-prompt-card label.agfo-image-prompt-check input{width:auto;margin-right:6px}
                .agfo-image-prompt-head{display:flex;justify-content:space-between;gap:12px;align-items:center}
                .agfo-image-prompt-card p{color:#646970;min-height:38px}
                .agfo-image-version{margin-top:24px;color:#8c8f94;font-size:9px}
                @media(max-width:900px){.agfo-image-prompt-grid{grid-template-columns:1fr}}
            </style>
            <?php
        }
    }
}
