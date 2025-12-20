import logging
import json
import time
import argparse
from db import (
    get_completed_research, get_approved_photos, save_story_generation, 
    save_story_slides, update_photo_text, update_caption_and_hashtags,
    get_stories_needing_captions, get_story_generation_with_slides,
    get_stories_with_existing_generations, delete_generation_and_slides
)
from generator import (
    generate_cover_options, generate_story_slides, generate_photo_text,
    generate_instagram_caption, generate_hashtags
)
from utils import fetch_article_content

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _format_markdown_output(
    story_id: str, 
    cover_result: dict, 
    slides_result: dict, 
    photos_result: list[dict],
    caption_result: dict = None,
    hashtags_result: dict = None
) -> str:
    lines: list[str] = []
    lines.append(f"# Text Generator Output\n")
    lines.append(f"Story ID: `{story_id}`\n")

    if cover_result:
        lines.append("## Cover (6 options + selection)\n")
        lines.append("```json")
        lines.append(json.dumps(cover_result, indent=2, ensure_ascii=False))
        lines.append("```\n")

    if slides_result:
        lines.append("## Story Slides\n")
        slides = slides_result.get("slides", [])
        for i, slide in enumerate(slides, start=1):
            tag = slide.get("tag", "")
            text = slide.get("text", "")
            lines.append(f"### Slide {i} — {tag}\n")
            lines.append(text)
            lines.append("")  # blank line

    if photos_result:
        lines.append("## Photo Text\n")
        for item in photos_result:
            lines.append(f"### Photo `{item.get('photo_id')}`\n")
            lines.append("```json")
            lines.append(json.dumps(item, indent=2, ensure_ascii=False))
            lines.append("```\n")

    if caption_result:
        lines.append("## Instagram Caption\n")
        lines.append(caption_result.get("caption", ""))
        lines.append("")

    if hashtags_result:
        lines.append("## Hashtags\n")
        hashtags = hashtags_result.get("hashtags", [])
        lines.append(" ".join(hashtags))
        lines.append("")
        if hashtags_result.get("layer_breakdown"):
            lines.append("### Layer Breakdown\n")
            lines.append("```json")
            lines.append(json.dumps(hashtags_result.get("layer_breakdown"), indent=2, ensure_ascii=False))
            lines.append("```\n")

    return "\n".join(lines).strip() + "\n"


def _format_backfill_output(generation_id: str, caption_result: dict, hashtags_result: dict) -> str:
    """Format output for backfill mode."""
    lines: list[str] = []
    lines.append(f"# Caption & Hashtag Backfill\n")
    lines.append(f"Generation ID: `{generation_id}`\n")

    if caption_result:
        lines.append("## Instagram Caption\n")
        lines.append(caption_result.get("caption", ""))
        lines.append("")

    if hashtags_result:
        lines.append("## Hashtags\n")
        hashtags = hashtags_result.get("hashtags", [])
        lines.append(" ".join(hashtags))
        lines.append("")
        if hashtags_result.get("layer_breakdown"):
            lines.append("### Layer Breakdown\n")
            lines.append("```json")
            lines.append(json.dumps(hashtags_result.get("layer_breakdown"), indent=2, ensure_ascii=False))
            lines.append("```\n")

    return "\n".join(lines).strip() + "\n"

def run_backfill_captions(args):
    """Backfill Instagram captions and hashtags for existing stories."""
    logger.info("Starting caption/hashtag backfill...")
    
    stories = get_stories_needing_captions(limit=args.limit)
    
    if not stories:
        logger.info("No stories found needing captions.")
        return
    
    logger.info(f"Found {len(stories)} stories needing captions.")
    
    for story in stories:
        generation_id = story['generation_id']
        logger.info(f"Processing generation ID: {generation_id}")
        
        try:
            # Fetch the full generation with slides
            gen_data = get_story_generation_with_slides(generation_id)
            if not gen_data:
                logger.warning(f"Could not fetch generation data for {generation_id}")
                continue
            
            slides = gen_data['slides']
            cover_data = {
                'title': gen_data['hook_title'],
                'subtitle': gen_data['subtitle'],
                'domain_tag': gen_data['domain_tag']
            }
            
            # Generate Instagram caption
            logger.info("Generating Instagram caption...")
            caption_result = generate_instagram_caption(slides, cover_data)
            caption = caption_result.get('caption', '')
            
            # Generate hashtags
            logger.info("Generating hashtags...")
            hashtags_result = generate_hashtags(slides, cover_data)
            hashtags = hashtags_result.get('hashtags', [])
            
            logger.info(f"Generated caption ({len(caption)} chars) and {len(hashtags)} hashtags")
            
            if not args.dry_run:
                update_caption_and_hashtags(generation_id, caption, hashtags)
                logger.info(f"Saved caption and hashtags for generation {generation_id}")
            
            # Output handling
            if args.out:
                md = _format_backfill_output(str(generation_id), caption_result, hashtags_result)
                with open(args.out, "w", encoding="utf-8") as f:
                    f.write(md)
                logger.info(f"Wrote output to: {args.out}")
            
            if args.dry_run and not args.out:
                print("\n=== INSTAGRAM CAPTION ===")
                print(caption)
                print("\n=== HASHTAGS ===")
                print(" ".join(hashtags))
                if hashtags_result.get("layer_breakdown"):
                    print("\n=== LAYER BREAKDOWN ===")
                    print(json.dumps(hashtags_result.get("layer_breakdown"), indent=2, ensure_ascii=False))
            
            time.sleep(1)  # Rate limiting between stories
            
        except Exception as e:
            logger.error(f"Failed to process generation {generation_id}: {e}", exc_info=True)
            continue
    
    logger.info("Backfill complete.")


def run_regenerate(args):
    """Regenerate text content for stories that already have generations."""
    logger.info("Starting text regeneration...")
    
    stories = get_stories_with_existing_generations(limit=args.limit)
    
    if not stories:
        logger.info("No stories found with existing generations.")
        return
    
    logger.info(f"Found {len(stories)} stories to regenerate.")
    
    for story in stories:
        story_id = story['id']
        old_generation_id = story['generation_id']
        logger.info(f"Regenerating story ID: {story_id} (old generation: {old_generation_id})")
        
        try:
            # Delete old generation and slides
            if not args.dry_run:
                success = delete_generation_and_slides(old_generation_id, force=args.force)
                if not success:
                    logger.error(f"Failed to delete old generation for story {story_id}, skipping...")
                    continue
            else:
                logger.info(f"[DRY RUN] Would delete generation {old_generation_id}" + (" (with --force)" if args.force else ""))
            
            # Prepare Research Text
            research_data = story.get('research_data', {})
            lead_url = story.get('lead_url')
            
            # Fetch Source Content
            source_content = fetch_article_content(lead_url) if lead_url else None

            if isinstance(research_data, dict):
                research_text = json.dumps(research_data, indent=2)
            else:
                research_text = str(research_data)

            # --- Step 1: Story Slides Generation (FIRST) ---
            logger.info("Generating story slides (story-first)...")
            slides_result = generate_story_slides(research_text, source_content=source_content)
            slides = slides_result.get('slides', [])
            logger.info(f"Generated {len(slides)} slides")

            # --- Step 2: Cover Generation (SECOND, based on story) ---
            logger.info("Generating cover text (derived from story)...")
            cover_result = generate_cover_options(research_text, slides)
            selected_id = cover_result.get('selected_id')
            selected_option = next((opt for opt in cover_result['options'] if opt['id'] == selected_id), None)
            if not selected_option:
                raise ValueError("Selected option ID not found in options list.")

            logger.info(f"Selected Hook: {selected_option['title']}")

            if not args.dry_run:
                gen_id = save_story_generation(story_id, selected_option, cover_result)
                logger.info(f"Saved story generation (ID: {gen_id})")
                save_story_slides(gen_id, slides)
                logger.info(f"Saved {len(slides)} slides.")
            
            # --- Step 3: Photo Text Generation ---
            photos = get_approved_photos(story_id)
            logger.info(f"Found {len(photos)} approved photos.")

            generated_photo_texts: list[dict] = []
            
            for photo in photos:
                logger.info(f"Generating text for photo ID: {photo['id']}")
                
                photo_desc = (
                    f"Description: {photo.get('description', 'N/A')}\n"
                    f"Search Query: {photo.get('search_query', 'N/A')}\n"
                    f"Image URL: {photo.get('image_url', 'N/A')}"
                )
                
                photo_text = generate_photo_text(photo_desc, research_text, source_content=source_content)

                generated_photo_texts.append({
                    "photo_id": str(photo["id"]),
                    "caption": photo_text.get("caption", ""),
                    "source": photo_text.get("source", ""),
                    "concept_tag": photo_text.get("concept_tag", "")
                })

                if not args.dry_run:
                    update_photo_text(
                        photo['id'],
                        photo_text.get('caption', ''),
                        photo_text.get('source', ''),
                        photo_text.get('concept_tag', '')
                    )
                
                time.sleep(1)

            # --- Step 4: Instagram Caption & Hashtags ---
            logger.info("Generating Instagram caption...")
            caption_result = generate_instagram_caption(slides, selected_option)
            caption = caption_result.get('caption', '')
            
            logger.info("Generating hashtags...")
            hashtags_result = generate_hashtags(slides, selected_option)
            hashtags = hashtags_result.get('hashtags', [])
            
            logger.info(f"Generated caption ({len(caption)} chars) and {len(hashtags)} hashtags")
            
            if not args.dry_run:
                update_caption_and_hashtags(gen_id, caption, hashtags)
                logger.info(f"Saved caption and hashtags.")

            logger.info(f"Successfully regenerated story {story_id}")

            # Output handling
            if args.out:
                md = _format_markdown_output(
                    str(story_id), cover_result, slides_result, generated_photo_texts,
                    caption_result, hashtags_result
                )
                with open(args.out, "w", encoding="utf-8") as f:
                    f.write(md)
                logger.info(f"Wrote output to: {args.out}")

            if args.dry_run and not args.out:
                print("\n=== COVER GENERATION ===")
                print(json.dumps(cover_result, indent=2, ensure_ascii=False))
                print("\n=== STORY SLIDES ===")
                print(json.dumps(slides_result, indent=2, ensure_ascii=False))
                if generated_photo_texts:
                    print("\n=== PHOTO TEXT ===")
                    print(json.dumps(generated_photo_texts, indent=2, ensure_ascii=False))
                print("\n=== INSTAGRAM CAPTION ===")
                print(caption)
                print("\n=== HASHTAGS ===")
                print(" ".join(hashtags))

            time.sleep(2)  # Rate limiting between stories

        except Exception as e:
            logger.error(f"Failed to regenerate story {story_id}: {e}", exc_info=True)
            continue
    
    logger.info("Regeneration complete.")


def main():
    parser = argparse.ArgumentParser(description="Text Generator Service")
    parser.add_argument("--limit", type=int, help="Limit the number of stories to process")
    parser.add_argument("--story-id", type=str, help="Process a specific story ID (bypasses 'already generated' check)")
    parser.add_argument("--random", action="store_true", help="Process a RANDOM story (great for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Run without saving to DB (prints results to stdout)")
    parser.add_argument("--out", type=str, help="Write output to a file (Markdown). Recommended with --dry-run.")
    parser.add_argument("--backfill-captions", action="store_true", help="Backfill captions/hashtags for existing stories")
    parser.add_argument("--regenerate", action="store_true", help="Regenerate text for stories that already have generations (deletes old, creates new)")
    parser.add_argument("--force", action="store_true", help="Force regeneration even if assemblies/thumbnails exist (deletes them too)")
    args = parser.parse_args()

    # Handle backfill mode
    if args.backfill_captions:
        run_backfill_captions(args)
        return

    # Handle regenerate mode
    if args.regenerate:
        run_regenerate(args)
        return

    logger.info("Starting Text Generator service...")
    
    # 1. Fetch stories ready for processing
    stories = get_completed_research(limit=args.limit, story_id=args.story_id, random=args.random)
    
    if not stories:
        logger.info("No research found awaiting text generation.")
        return

    logger.info(f"Found {len(stories)} stories to process.")

    for story in stories:
        story_id = story['id']
        logger.info(f"Processing story ID: {story_id}")
        
        try:
            # Prepare Research Text
            research_data = story.get('research_data', {})
            lead_url = story.get('lead_url')
            
            # Fetch Source Content
            source_content = fetch_article_content(lead_url) if lead_url else None

            if isinstance(research_data, dict):
                research_text = json.dumps(research_data, indent=2)
            else:
                research_text = str(research_data)

            # --- Step 1: Story Slides Generation (FIRST) ---
            logger.info("Generating story slides (story-first)...")
            slides_result = generate_story_slides(research_text, source_content=source_content)
            slides = slides_result.get('slides', [])

            # --- Step 2: Cover Generation (SECOND, based on story) ---
            logger.info("Generating cover text (derived from story)...")
            cover_result = generate_cover_options(research_text, slides)
            selected_id = cover_result.get('selected_id')
            selected_option = next((opt for opt in cover_result['options'] if opt['id'] == selected_id), None)
            if not selected_option:
                raise ValueError("Selected option ID not found in options list.")

            logger.info(f"Selected Hook: {selected_option['title']}")

            if not args.dry_run:
                gen_id = save_story_generation(story_id, selected_option, cover_result)
                logger.info(f"Saved story generation (ID: {gen_id})")
                save_story_slides(gen_id, slides)
                logger.info(f"Saved {len(slides)} slides.")
            
            # --- Step 3: Photo Text Generation ---
            photos = get_approved_photos(story_id)
            logger.info(f"Found {len(photos)} approved photos.")

            generated_photo_texts: list[dict] = []
            
            for photo in photos:
                logger.info(f"Generating text for photo ID: {photo['id']}")
                
                photo_desc = (
                    f"Description: {photo.get('description', 'N/A')}\n"
                    f"Search Query: {photo.get('search_query', 'N/A')}\n"
                    f"Image URL: {photo.get('image_url', 'N/A')}"
                )
                
                photo_text = generate_photo_text(photo_desc, research_text, source_content=source_content)

                generated_photo_texts.append({
                    "photo_id": str(photo["id"]),
                    "caption": photo_text.get("caption", ""),
                    "source": photo_text.get("source", ""),
                    "concept_tag": photo_text.get("concept_tag", "")
                })

                if not args.dry_run:
                    update_photo_text(
                        photo['id'],
                        photo_text.get('caption', ''),
                        photo_text.get('source', ''),
                        photo_text.get('concept_tag', '')
                    )
                
                time.sleep(1)

            # --- Step 4: Instagram Caption & Hashtags ---
            logger.info("Generating Instagram caption...")
            caption_result = generate_instagram_caption(slides, selected_option)
            caption = caption_result.get('caption', '')
            
            logger.info("Generating hashtags...")
            hashtags_result = generate_hashtags(slides, selected_option)
            hashtags = hashtags_result.get('hashtags', [])
            
            logger.info(f"Generated caption ({len(caption)} chars) and {len(hashtags)} hashtags")
            
            if not args.dry_run:
                update_caption_and_hashtags(gen_id, caption, hashtags)
                logger.info(f"Saved caption and hashtags.")

            logger.info(f"Successfully finished processing story {story_id}")

            # Output handling (stdout and/or file)
            if args.out:
                md = _format_markdown_output(
                    str(story_id), cover_result, slides_result, generated_photo_texts,
                    caption_result, hashtags_result
                )
                with open(args.out, "w", encoding="utf-8") as f:
                    f.write(md)
                logger.info(f"Wrote output to: {args.out}")

            if args.dry_run and not args.out:
                print("\n=== COVER GENERATION ===")
                print(json.dumps(cover_result, indent=2, ensure_ascii=False))
                print("\n=== STORY SLIDES ===")
                print(json.dumps(slides_result, indent=2, ensure_ascii=False))
                if generated_photo_texts:
                    print("\n=== PHOTO TEXT ===")
                    print(json.dumps(generated_photo_texts, indent=2, ensure_ascii=False))
                print("\n=== INSTAGRAM CAPTION ===")
                print(caption)
                print("\n=== HASHTAGS ===")
                print(" ".join(hashtags))
                if hashtags_result.get("layer_breakdown"):
                    print("\n=== LAYER BREAKDOWN ===")
                    print(json.dumps(hashtags_result.get("layer_breakdown"), indent=2, ensure_ascii=False))

        except Exception as e:
            logger.error(f"Failed to process story {story_id}: {e}", exc_info=True)
            continue

if __name__ == "__main__":
    main()
