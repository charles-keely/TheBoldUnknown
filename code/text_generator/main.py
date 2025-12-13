import logging
import json
import time
import argparse
from db import get_completed_research, get_approved_photos, save_story_generation, save_story_slides, update_photo_text
from generator import generate_cover_options, generate_story_slides, generate_photo_text

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _format_markdown_output(story_id: str, cover_result: dict, slides_result: dict, photos_result: list[dict]) -> str:
    lines: list[str] = []
    lines.append(f"# Text Generator Output\n")
    lines.append(f"Story ID: `{story_id}`\n")

    if cover_result:
        lines.append("## Cover (3 options + selection)\n")
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

    return "\n".join(lines).strip() + "\n"

def main():
    parser = argparse.ArgumentParser(description="Text Generator Service")
    parser.add_argument("--limit", type=int, help="Limit the number of stories to process")
    parser.add_argument("--story-id", type=str, help="Process a specific story ID (bypasses 'already generated' check)")
    parser.add_argument("--dry-run", action="store_true", help="Run without saving to DB (prints results to stdout)")
    parser.add_argument("--out", type=str, help="Write output to a file (Markdown). Recommended with --dry-run.")
    args = parser.parse_args()

    logger.info("Starting Text Generator service...")
    
    # 1. Fetch stories ready for processing
    stories = get_completed_research(limit=args.limit, story_id=args.story_id)
    
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
            if isinstance(research_data, dict):
                research_text = json.dumps(research_data, indent=2)
            else:
                research_text = str(research_data)

            # --- Step 1: Story Slides Generation (FIRST) ---
            logger.info("Generating story slides (story-first)...")
            slides_result = generate_story_slides(research_text)
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
                
                photo_text = generate_photo_text(photo_desc, research_text)

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

            logger.info(f"Successfully finished processing story {story_id}")

            # Output handling (stdout and/or file)
            if args.out:
                md = _format_markdown_output(str(story_id), cover_result, slides_result, generated_photo_texts)
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

        except Exception as e:
            logger.error(f"Failed to process story {story_id}: {e}", exc_info=True)
            continue

if __name__ == "__main__":
    main()
