import asyncio
import os
import logging
import json
import argparse
from db_utils import get_pending_assemblies, mark_assembly_finalized
from builder import SlideBuilder
from renderer import Renderer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

async def process_assembly(renderer: Renderer, assembly: dict):
    story_id = str(assembly["story_generation_id"])
    title = assembly.get("hook_title") or story_id
    logger.info(f"Processing story: {title} ({story_id})")

    # Prepare output directory
    story_dir = os.path.join(OUTPUT_ROOT, story_id)
    os.makedirs(story_dir, exist_ok=True)

    # Prepare builder
    builder = SlideBuilder(story_dir)
    
    assembly_data = assembly.get("assembly_data")
    if not assembly_data:
        logger.warning(f"No assembly data for {story_id}. Skipping.")
        return

    slides = assembly_data.get("slides", [])
    if not slides:
        logger.warning(f"No slides for {story_id}. Skipping.")
        return

    rendered_files = []

    visible_slides = [s for s in slides if s.get("visible", True)]
    total_slides = len(visible_slides)
    if total_slides == 0:
        logger.warning(f"No visible slides for {story_id}. Skipping.")
        return []

    for i, slide in enumerate(visible_slides):
        slide_number = i + 1
            
        logger.info(f"  Building slide {slide_number}/{total_slides} ({slide.get('type')})...")
        
        # Build HTML
        html_content = builder.build_slide(slide, i, slide_number=slide_number, total_slides=total_slides)
        if not html_content:
            logger.warning(f"  Failed to build HTML for slide {i}. Skipping.")
            continue
            
        # Render
        output_filename = f"{slide_number:02d}_{slide.get('type')}.png"
        output_path = os.path.join(story_dir, output_filename)
        
        await renderer.render(html_content, output_path)
        
        # Store relative path or absolute? 
        # Storing relative to OUTPUT_ROOT allows moving the folder later?
        # Or absolute is explicit. Let's store absolute for now, or path relative to project root.
        # Let's store the path relative to the code/ directory or output root.
        # Ideally, we store the full path so any uploader can find it.
        rendered_files.append(output_path)

    return rendered_files

async def main():
    parser = argparse.ArgumentParser(description="Assembler batch process (HTML -> PNG)")
    parser.add_argument("--story-id", dest="story_id", default=None, help="Render a single story_generation_id")
    parser.add_argument("--limit", dest="limit", type=int, default=None, help="Render at most N stories")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Do not update DB status/rendered_files")
    args = parser.parse_args()

    logger.info("Starting Assembler Batch Process...")
    
    # 1. Fetch pending work
    pending = get_pending_assemblies(story_generation_id=args.story_id, limit=args.limit)
    logger.info(f"Found {len(pending)} stories ready for assembly.")
    
    if not pending:
        return

    # 2. Initialize Renderer context
    async with Renderer() as renderer:
        for assembly in pending:
            try:
                rendered_files = await process_assembly(renderer, assembly)
                story_id = str(assembly.get("story_generation_id"))
                if not rendered_files:
                    logger.warning(f"No slides rendered for {story_id}.")
                    continue

                if args.dry_run:
                    logger.info(f"DRY RUN: would finalize story {story_id} with {len(rendered_files)} slides.")
                    continue

                mark_assembly_finalized(story_id, rendered_files)
                logger.info(f"Finalized story {story_id} with {len(rendered_files)} slides.")
            except Exception as e:
                logger.error(f"Error processing assembly {assembly.get('story_generation_id')}: {e}")
                # Continue to next assembly
                continue

    logger.info("Assembler finished.")

if __name__ == "__main__":
    asyncio.run(main())
