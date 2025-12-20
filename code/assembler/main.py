import asyncio
import os
import logging
import json
import hashlib
import tempfile
from db_utils import get_pending_assemblies, mark_assembly_finalized
from builder import SlideBuilder
from renderer import Renderer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
KEEP_OUTPUT = os.getenv("ASSEMBLER_KEEP_OUTPUT", "0").strip().lower() in ("1", "true", "yes", "y", "on")

async def process_assembly(renderer: Renderer, assembly: dict):
    story_id = str(assembly["story_generation_id"])
    title = assembly.get("hook_title") or story_id
    logger.info(f"Processing story: {title} ({story_id})")

    # Prepare output directory (optional; default is NO local persistence)
    if KEEP_OUTPUT:
        story_dir = os.path.join(OUTPUT_ROOT, story_id)
        os.makedirs(story_dir, exist_ok=True)
    else:
        story_dir = None

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

    for i, slide in enumerate(slides):
        if not slide.get("visible", True):
            continue
            
        logger.info(f"  Building slide {i+1}/{len(slides)} ({slide.get('type')})...")
        
        # Build HTML
        html_content = builder.build_slide(slide, i)
        if not html_content:
            logger.warning(f"  Failed to build HTML for slide {i}. Skipping.")
            continue
            
        # Render
        output_filename = f"{i+1:02d}_{slide.get('type')}.png"

        if KEEP_OUTPUT:
            output_path = os.path.join(story_dir, output_filename)
            await renderer.render(html_content, output_path)
            rendered_files.append(output_path)
        else:
            # Default: do not write any files locally.
            png_bytes = await renderer.render_png_bytes(html_content)
            rendered_files.append(
                {
                    "filename": output_filename,
                    "bytes_len": len(png_bytes),
                    "sha256": hashlib.sha256(png_bytes).hexdigest(),
                    "storage": "ephemeral",
                }
            )

    # Mark as finalized in DB
    if rendered_files:
        mark_assembly_finalized(story_id, rendered_files)
        if KEEP_OUTPUT:
            logger.info(f"Finalized story {story_id} with {len(rendered_files)} slides. Output kept at: {story_dir}")
        else:
            logger.info(f"Finalized story {story_id} with {len(rendered_files)} slides. No local files were written.")
    else:
        logger.warning(f"No slides rendered for {story_id}.")

async def main():
    logger.info("Starting Assembler Batch Process...")
    
    # 1. Fetch pending work
    pending = get_pending_assemblies()
    logger.info(f"Found {len(pending)} stories ready for assembly.")
    
    if not pending:
        return

    # 2. Initialize Renderer context
    async with Renderer() as renderer:
        for assembly in pending:
            try:
                await process_assembly(renderer, assembly)
            except Exception as e:
                logger.error(f"Error processing assembly {assembly.get('story_generation_id')}: {e}")
                # Continue to next assembly
                continue

    logger.info("Assembler finished.")

if __name__ == "__main__":
    asyncio.run(main())
