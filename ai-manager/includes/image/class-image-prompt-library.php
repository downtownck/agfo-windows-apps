<?php
/**
 * AGFO AI Manager — Featured image prompt presets.
 *
 * Added in 16.16.0. Presets are stored as overridable option data so the art
 * direction can be edited in the admin without touching code, exactly like
 * AGFO_AIM_Content_Prompt_Library does for text.
 *
 * CHANGED 16.19.0: Presets were rewritten from rule lists into concrete,
 * positively phrased art direction. They are now read by the art-director
 * step (AGFO_AIM_Image_Generator::build_subject_brief) which turns them into
 * one descriptive image prompt, instead of being pasted verbatim in front of
 * the image model. Each preset also carries a brief "mode" (scene, cover,
 * infographic) so the art director knows what kind of brief to write.
 * Saved overrides that are byte-identical to the 16.16.x defaults are ignored,
 * so sites that merely pressed "Save" once also receive the new defaults.
 *
 * @package AGFO_AI_Manager
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'AGFO_AIM_Image_Prompt_Library' ) ) {
    final class AGFO_AIM_Image_Prompt_Library {
        public const OPTION_KEY = 'agfo_aim_image_prompts';

        /**
         * Brief modes understood by the art director.
         */
        public const MODES = [ 'scene', 'cover', 'infographic' ];

        /**
         * Built-in preset catalogue.
         *
         * Each preset is art direction only: the subject is supplied separately,
         * either from the post content or from the operator's own instruction.
         */
        public static function defaults(): array {
            return [
                'featured_philosophical' => [
                    'label'       => 'Felsefi öne çıkan görsel',
                    'description' => 'İnsan odaklı, fotografik, düşündürücü; kalabalık ve yazı yok.',
                    'aspect'      => '16:9',
                    'allow_text'  => 0,
                    'mode'        => 'scene',
                    'prompt'      => implode( "\n", [
                        'Genre: contemplative documentary photograph, the kind that opens a long-form essay in a serious magazine.',
                        'Idea first: find the one human moment that carries the central question of the text, not its surface topic. Prefer a quiet, specific gesture (hands resting on an open book, a gaze held a moment too long, a pause at a doorway) over a symbolic pose.',
                        'Cast: one person, at most two, clearly the emotional anchor. Give them a believable age, clothing and posture that belong to the world of the text.',
                        'Place: a real, specific location with texture and history (a worn study, a morning ferry deck, a stone courtyard, a winter window), kept calm and uncrowded so the figure reads instantly.',
                        'Camera: 35mm or 50mm prime, eye level or slightly below, subject placed on a third with generous negative space, shallow but natural depth of field.',
                        'Light: one motivated natural source (window light, low sun, overcast sky) with soft falloff into shadow; honest skin texture, no retouched gloss.',
                        'Colour: a restrained palette of two or three muted tones with one quiet accent; subtle film grain, gentle contrast, the look of a Leica or Kodak Portra frame.',
                        'Realism: grounded physics and proportions, nothing floating, nothing dreamlike. The image is clean of any lettering, captions or marks.',
                        'If the text centres on a named philosopher, thinker or writer, portray that person in a form faithful to their widely known appearance and historical period, in a setting of their era.',
                    ] ),
                ],
                'album_cover' => [
                    'label'       => 'Şarkı albüm kapağı',
                    'description' => 'Şarkının diline ve kültürüne göre 16:9 YouTube kapağı; kredi satırı şarkının dilinde.',
                    'aspect'      => '16:9',
                    'allow_text'  => 1,
                    'mode'        => 'cover',
                    'prompt'      => implode( "\n", [
                        'Genre: cinematic photographic music cover, 16:9, made to work as a YouTube video frame and thumbnail.',
                        'Idea first: pick the single image the song leaves behind in the listener\'s mind — a moment, a place, a light — and build the frame around it rather than illustrating every line.',
                        'Culture: the whole frame belongs to the language and musical world of the song. Convey it through streets, squares, landscape, architecture of homes and markets, costume, instruments, colour and light. A Spanish song reads Andalusian or Mediterranean; an Azerbaijani song reads Azerbaijani; a Turkish song reads Turkish.',
                        'Keep the setting secular: streets, harbours, courtyards, cafés, hills, rooms and landscapes.',
                        'Cast: a human-centred, uncrowded composition. One main figure or a couple, depicted with dignity and elegance, dressed modestly and tastefully.',
                        'Camera and light: 35mm or 85mm lens, cinematic golden-hour or dusk light, or warm practical light at night; rich but natural colour grade; realistic, emotional and poetic, never surreal.',
                        'Typography: reserve a calm area of the frame (usually one third, over sky, wall or shadow) for text. The song title is large and highly readable and stays in its original language; a smaller credit line sits beneath it. Text never covers the face or the main emotion.',
                        'Credit line, unless the operator specifies otherwise, always in the language of the lyrics: Turkish "Söz ve Müzik: Cemal Gürkan Kara"; Spanish "Letra y música: Cemal Gürkan Kara"; English "Lyrics and Music: Cemal Gürkan Kara".',
                    ] ),
                ],
                'album_cover_thumbnail' => [
                    'label'       => 'Albüm kapağı — tıklanma odaklı',
                    'description' => 'Daha yakın plan, daha yüksek kontrast, büyük okunabilir başlık alanı.',
                    'aspect'      => '16:9',
                    'allow_text'  => 1,
                    'mode'        => 'cover',
                    'prompt'      => implode( "\n", [
                        'Genre: high-impact 16:9 YouTube thumbnail for a song, designed to be read in a fraction of a second at small size.',
                        'Framing: close-up or medium close-up; the face or the central emotion fills most of the frame and is sharp.',
                        'Contrast: strong tonal and colour separation between subject and background (for example warm skin against a cool dusk backdrop); simple, softly blurred background.',
                        'Culture: place, costume, instrument, colour and light come from the song\'s language and tradition; settings stay secular.',
                        'Cast: elegant and dignified figures, modest clothing.',
                        'Typography: one clear block reserved for a large title of at most five words in the language of the song, heavy clean typeface, high-contrast colour, never over the face.',
                        'Look: photographic and realistic, cinematic lighting with a defined key light and rim light, crisp detail, no surrealism.',
                    ] ),
                ],
                'infographic' => [
                    'label'       => 'Dikey infografik',
                    'description' => 'Bilgiyi sadeleştiren, hiyerarşik, kurumsal dikey infografik.',
                    'aspect'      => '9:16',
                    'allow_text'  => 1,
                    'mode'        => 'infographic',
                    'prompt'      => implode( "\n", [
                        'Genre: clean, modern, corporate vertical infographic that simplifies the content rather than reproducing it.',
                        'Structure from top to bottom: a short strong headline; a one-sentence summary; three to six clearly separated information blocks; a data, process or comparison area where the content supports one; a short closing takeaway.',
                        'Hierarchy: the most important information sits in the most visible position; supporting detail is smaller but readable; the eye travels naturally downward.',
                        'Blocks: each has a short heading with a simple flat icon, number, arrow or box, and one short, concrete statement.',
                        'Data: numbers become a bar chart, ratio, percentage ring, counter or timeline; a process becomes numbered steps; a comparison becomes two columns. Use only figures that appear in the content.',
                        'Palette: trustworthy blue, green, white and light grey, with orange or yellow as the single accent colour.',
                        'Typography: at most two type styles; a large confident sans-serif headline, distinct subheadings, short readable body text, generous whitespace and consistent margins.',
                        'Tone: professional, plain and reassuring; no hype, no clichés, no vague claims.',
                    ] ),
                ],
                'editorial_article' => [
                    'label'       => 'Editoryal makale görseli',
                    'description' => 'Haber ve blog yazıları için sade, gerçekçi, konuya bağlı görsel.',
                    'aspect'      => '16:9',
                    'allow_text'  => 0,
                    'mode'        => 'scene',
                    'prompt'      => implode( "\n", [
                        'Genre: realistic editorial photograph, as commissioned by a quality newspaper photo desk.',
                        'Idea first: show the consequence or the human stake of the story, a concrete detail that a reader recognises, rather than the abstract topic itself.',
                        'One clear subject, an uncluttered background, readable at thumbnail size.',
                        'Documentary rather than staged, current rather than nostalgic; real materials, real wear, real places.',
                        'Camera: 28mm to 50mm, natural perspective, available light, slight grain, true-to-life colour.',
                        'The frame is clean of lettering, signage, logos and watermarks.',
                        'Instead of stock-photo metaphors (handshakes, glowing circuits, holograms, puzzle pieces, lightbulbs), use a specific real scene.',
                    ] ),
                ],
                'corporate_technical' => [
                    'label'       => 'Kurumsal / teknik',
                    'description' => 'Denetim, gıda güvenliği, belgelendirme ve teknik içerikler için ölçülü kurumsal görsel.',
                    'aspect'      => '16:9',
                    'allow_text'  => 0,
                    'mode'        => 'scene',
                    'prompt'      => implode( "\n", [
                        'Genre: restrained corporate reportage photograph for a technical, audit, food safety or certification subject.',
                        'Idea first: show competent work in progress at the exact point the text is about (a temperature check at a production line, a document review beside a packing station, a sample taken in a cold store), not people posing.',
                        'Setting: a real working environment that fits the subject — food plant, warehouse, laboratory, farm, vessel or office — with correct professional clothing, hygiene gear and equipment for that setting.',
                        'People: calm, focused, natural expressions; hands and tools doing something specific.',
                        'Camera: 35mm to 85mm, eye level, shallow depth of field isolating the action, clean lines and orderly background.',
                        'Light and colour: even industrial or daylight illumination, neutral palette with steel, white and one muted brand-neutral accent; crisp, credible detail.',
                        'The frame is clean of lettering, brand marks, certification logos and watermarks.',
                    ] ),
                ],
            ];
        }

        /**
         * Hashes of the 16.16.x default prompts (whitespace-normalised).
         *
         * A saved override whose prompt matches one of these was never really
         * customised — the admin form simply re-saved the default text — so it
         * is ignored and the current default applies.
         */
        public static function legacy_prompt_hashes(): array {
            return [
                'featured_philosophical' => [ '2ad08a4ab1423c901ab662b6c93e17a7' ],
                'album_cover'            => [ 'e10119b043426ea03c77f058b3c78120' ],
                'album_cover_thumbnail'  => [ 'f3d7814826152c1c1517155cd58f8b65' ],
                'infographic'            => [ '500450b4027ff98077ff48de2f6cb274' ],
                'editorial_article'      => [ '869dff6f74c21ef341cab03beec7187a' ],
                'corporate_technical'    => [ '3e7a8d37df86ce21864b8e1f0df7223c' ],
            ];
        }

        public static function prompt_hash( string $prompt ): string {
            return md5( (string) preg_replace( '/\s+/u', ' ', trim( $prompt ) ) );
        }

        /**
         * Rules applied to every request regardless of preset.
         *
         * Kept for backward compatibility (public static since 16.16.0). Since
         * 16.19.0 the art director receives these rules and the image model only
         * gets the short form from compact_guardrails().
         */
        public static function mandatory_guardrails(): string {
            return implode( "\n", [
                'MANDATORY RULES:',
                '- Do not depict religious symbols, places of worship or religious architecture unless the operator explicitly asks for them.',
                '- Do not depict real, identifiable private individuals. A named historical thinker, writer or public figure may be evoked in period-appropriate form.',
                '- Keep clothing modest and dignified. No sexualised framing, no erotic emphasis.',
                '- No graphic violence, no distressing imagery, no political campaign material.',
                '- No brand logos, trademarks, watermarks or copyrighted characters.',
                '- Deliver a clean, publication-ready image, correctly exposed and correctly framed for the requested aspect ratio.',
            ] );
        }

        /**
         * One-line guardrail tail for the image model itself.
         *
         * Diffusion models (FLUX, Recraft on fal) do not understand negation and
         * tend to draw whatever is named, so for them the tail is positive only;
         * the art director has already kept forbidden elements out of the brief.
         */
        public static function compact_guardrails( string $provider ): string {
            if ( 'fal' === $provider ) {
                return 'Secular setting, modest dignified clothing, clean publication-ready image.';
            }
            return 'Keep the image free of religious symbols and places of worship, brand logos, watermarks and identifiable private individuals; clothing modest and dignified; clean, publication-ready image.';
        }

        /**
         * Sanitise a single preset row.
         */
        private static function sanitize_row( array $row, array $fallback ): array {
            $aspects = array_keys( AGFO_AIM_Image_Adapter::aspect_presets() );
            $aspect  = isset( $row['aspect'] ) ? (string) $row['aspect'] : (string) $fallback['aspect'];
            $mode    = sanitize_key( (string) ( $row['mode'] ?? ( $fallback['mode'] ?? 'scene' ) ) );

            return [
                'label'       => sanitize_text_field( (string) ( $row['label'] ?? $fallback['label'] ) ),
                'description' => sanitize_text_field( (string) ( $row['description'] ?? $fallback['description'] ) ),
                'aspect'      => in_array( $aspect, $aspects, true ) ? $aspect : (string) $fallback['aspect'],
                'allow_text'  => empty( $row['allow_text'] ) ? 0 : 1,
                'mode'        => in_array( $mode, self::MODES, true ) ? $mode : 'scene',
                'prompt'      => sanitize_textarea_field( (string) ( $row['prompt'] ?? $fallback['prompt'] ) ),
            ];
        }

        /**
         * Drop a saved prompt that is only a frozen copy of an old default.
         */
        private static function drop_legacy_prompt( string $key, array $saved ): array {
            if ( ! isset( $saved['prompt'] ) ) {
                return $saved;
            }
            $legacy = self::legacy_prompt_hashes();
            if ( isset( $legacy[ $key ] ) && in_array( self::prompt_hash( (string) $saved['prompt'] ), $legacy[ $key ], true ) ) {
                unset( $saved['prompt'] );
            }
            return $saved;
        }

        /**
         * Defaults merged with saved overrides.
         */
        public static function get_all(): array {
            $defaults  = self::defaults();
            $overrides = get_option( self::OPTION_KEY, [] );
            if ( ! is_array( $overrides ) ) {
                $overrides = [];
            }

            $out = [];
            foreach ( $defaults as $key => $row ) {
                $saved = isset( $overrides[ $key ] ) && is_array( $overrides[ $key ] ) ? $overrides[ $key ] : [];
                // CHANGED 16.19.0: mode is code-owned; a stale saved copy of an old default prompt no longer masks the new default.
                unset( $saved['mode'] );
                $saved       = self::drop_legacy_prompt( $key, $saved );
                $out[ $key ] = self::sanitize_row( array_merge( $row, $saved ), $row );
            }

            return apply_filters( 'agfo_ai_image_prompts', $out );
        }

        public static function get( string $key ): array {
            $all = self::get_all();
            if ( isset( $all[ $key ] ) ) {
                return $all[ $key ];
            }
            $first = array_key_first( $all );
            return $all[ $first ];
        }

        public static function default_key(): string {
            return 'featured_philosophical';
        }

        /**
         * Catalogue shape used by the editor UI.
         */
        public static function public_catalog(): array {
            $out = [];
            foreach ( self::get_all() as $key => $row ) {
                $out[ $key ] = [
                    'label'       => $row['label'],
                    'description' => $row['description'],
                    'aspect'      => $row['aspect'],
                    'allow_text'  => (int) $row['allow_text'],
                ];
            }
            return $out;
        }

        public static function save_overrides( array $posted ): bool {
            $defaults = self::defaults();
            $clean    = [];

            foreach ( $defaults as $key => $row ) {
                if ( ! isset( $posted[ $key ] ) || ! is_array( $posted[ $key ] ) ) {
                    continue;
                }
                $item = $posted[ $key ];
                unset( $item['mode'] );
                $sanitized = self::sanitize_row( array_merge( $row, $item ), $row );
                unset( $sanitized['mode'] );
                // CHANGED 16.19.0: an unchanged default prompt is not stored, so future default improvements keep flowing in.
                if ( self::prompt_hash( $sanitized['prompt'] ) === self::prompt_hash( (string) $row['prompt'] ) ) {
                    unset( $sanitized['prompt'] );
                }
                $clean[ $key ] = $sanitized;
            }

            return update_option( self::OPTION_KEY, $clean, false );
        }

        public static function reset(): bool {
            return delete_option( self::OPTION_KEY );
        }
    }
}
