"""
Thumbnail Generator - Main Orchestrator

Generates AI cover images for TheBoldUnknown Instagram posts.
"""

import os
import sys
import argparse
import logging
import webbrowser
from datetime import datetime

import db
from prompt_generator import generate_thumbnail_concepts
from prompt_builder import build_prompt, build_simple_prompt
from nanobanana import NanoBananaClient
from preview import generate_preview_html
from config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def process_story(story, use_pro=False, simple_prompt=False, skip_db=False):
    """
    Process a single story: generate concepts, build prompts, create images.
    
    Args:
        story: dict with generation_id, hook_title, subtitle, domain_tag, research_data
        use_pro: Use Nano Banana Pro model
        simple_prompt: Use simplified prompt format
        skip_db: If True, don't save to database (for testing)
    
    Returns:
        dict with 'thumbnail_ids', 'thumbnails' (full data for preview)
    """
    generation_id = story.get('generation_id')
    hook_title = story['hook_title']
    subtitle = story['subtitle']
    domain_tag = story['domain_tag']
    research_data = story.get('research_data', {})
    
    logger.info(f"Processing story: {hook_title}")
    if generation_id:
        logger.info(f"Generation ID: {generation_id}")
    
    # Step 1: Generate creative concepts using GPT-5.2
    logger.info("Step 1: Generating creative concepts...")
    try:
        concepts_result = generate_thumbnail_concepts(
            hook_title, subtitle, domain_tag, research_data
        )
        concepts = concepts_result.get('concepts', [])
        
        if not concepts:
            logger.error("No concepts generated")
            return {'thumbnail_ids': [], 'thumbnails': []}
        
        logger.info(f"Generated {len(concepts)} concepts")
        
    except Exception as e:
        logger.error(f"Failed to generate concepts: {e}")
        return {'thumbnail_ids': [], 'thumbnails': []}
    
    # Step 2: Build prompts and save to database
    logger.info("Step 2: Building prompts...")
    thumbnail_ids = []
    prompts = []
    thumbnails_data = []  # For preview
    
    prompt_builder = build_simple_prompt if simple_prompt else build_prompt
    
    for concept in concepts:
        concept_num = concept.get('id', len(prompts) + 1)
        concept_type = concept.get('concept_type', 'unknown')
        scene_description = concept.get('scene_description', '')
        
        # Build the full prompt
        full_prompt = prompt_builder(concept)
        prompts.append(full_prompt)
        
        # Prepare thumbnail data
        thumb_data = {
            'concept_number': concept_num,
            'concept_type': concept_type,
            'scene_description': scene_description,
            'full_prompt': full_prompt,
            'image_url': None,
            'status': 'pending'
        }
        thumbnails_data.append(thumb_data)
        
        # Save to database (unless skip_db)
        if not skip_db and generation_id:
            try:
                metadata = {
                    'concept': concept,
                    'model_used': 'gpt-5.2',
                    'prompt_type': 'simple' if simple_prompt else 'full'
                }

                # Idempotent behavior: reuse existing row for this concept number if present,
                # rather than creating duplicates on rerun.
                existing = db.get_thumbnail_for_story_concept(generation_id, concept_num)
                if existing and existing.get("id"):
                    thumbnail_id = existing["id"]
                    db.update_thumbnail_content(
                        thumbnail_id,
                        concept_type=concept_type,
                        scene_description=scene_description,
                        full_prompt=full_prompt,
                        generation_metadata=metadata,
                        reset_image=True,
                    )
                    thumbnail_ids.append(thumbnail_id)
                    logger.info(f"Reused thumbnail record {thumbnail_id} (concept {concept_num}: {concept_type})")
                else:
                    thumbnail_id = db.save_thumbnail(
                        generation_id=generation_id,
                        concept_number=concept_num,
                        concept_type=concept_type,
                        scene_description=scene_description,
                        full_prompt=full_prompt,
                        generation_metadata=metadata,
                    )
                    thumbnail_ids.append(thumbnail_id)
                    logger.info(f"Created thumbnail record {thumbnail_id} (concept {concept_num}: {concept_type})")
                
            except Exception as e:
                logger.error(f"Failed to save thumbnail record: {e}")
                thumbnail_ids.append(None)
        else:
            thumbnail_ids.append(None)
    
    # Step 3: Generate images using Nano Banana
    logger.info("Step 3: Generating images with Nano Banana...")
    nano_client = NanoBananaClient(use_pro=use_pro)
    
    for i, prompt in enumerate(prompts):
        concept_num = i + 1
        thumbnail_id = thumbnail_ids[i] if i < len(thumbnail_ids) else None
        
        # Update status to generating
        if thumbnail_id and not skip_db:
            db.update_thumbnail_status(thumbnail_id, 'generating')
        
        # Use a stable remote object path so reruns overwrite rather than littering local files.
        object_path = f"{generation_id}/c{concept_num}.png" if generation_id else f"adhoc/c{concept_num}.png"
        
        logger.info(f"Generating image {concept_num}/3...")
        
        try:
            result = nano_client.generate_image(prompt, object_path=object_path)
            
            if result['success']:
                # Update thumbnail data
                if result.get("image_url"):
                    thumbnails_data[i]['image_url'] = result['image_url']
                thumbnails_data[i]['status'] = 'generated'
                
                # Update database
                if thumbnail_id and not skip_db:
                    db.update_thumbnail_status(
                        thumbnail_id, 
                        'generated', 
                        image_url=result.get('image_url'),
                        metadata_update={
                            "storage_mode": result.get("storage_mode"),
                            "object_path": object_path,
                            "mime_type": result.get("mime_type"),
                            "image_base64": result.get("image_base64"),
                        },
                    )
                logger.info(f"✓ Image {concept_num} generated ({result.get('storage_mode')}): {result.get('image_url') or '[stored in DB metadata]'}")
            else:
                thumbnails_data[i]['status'] = 'failed'
                thumbnails_data[i]['error'] = result['error']
                
                if thumbnail_id and not skip_db:
                    db.update_thumbnail_status(
                        thumbnail_id, 
                        'failed', 
                        error_message=result['error'],
                        metadata_update={
                            "storage_mode": result.get("storage_mode"),
                            "object_path": object_path,
                        },
                    )
                logger.error(f"✗ Image {concept_num} failed: {result['error']}")
                
        except Exception as e:
            thumbnails_data[i]['status'] = 'failed'
            thumbnails_data[i]['error'] = str(e)
            
            if thumbnail_id and not skip_db:
                db.update_thumbnail_status(
                    thumbnail_id,
                    'failed',
                    error_message=str(e),
                    metadata_update={"object_path": object_path},
                )
            logger.error(f"✗ Image {concept_num} exception: {e}")
    
    return {
        'thumbnail_ids': [t for t in thumbnail_ids if t],
        'thumbnails': thumbnails_data
    }


def process_pending_stories(limit=None, use_pro=False, simple_prompt=False):
    """
    Process all stories that need thumbnails.
    
    Args:
        limit: Maximum number of stories to process
        use_pro: Use Nano Banana Pro model
        simple_prompt: Use simplified prompt format
    
    Returns:
        int: Number of stories processed
    """
    logger.info("Fetching stories that need thumbnails...")
    stories = db.get_stories_needing_thumbnails(limit=limit)
    
    if not stories:
        logger.info("No stories found that need thumbnails.")
        return 0
    
    logger.info(f"Found {len(stories)} stories to process")
    
    processed = 0
    for story in stories:
        try:
            result = process_story(story, use_pro=use_pro, simple_prompt=simple_prompt)
            if result['thumbnail_ids']:
                processed += 1
                logger.info(f"Completed story {processed}/{len(stories)}")
        except Exception as e:
            logger.error(f"Failed to process story {story['generation_id']}: {e}")
    
    logger.info(f"Processing complete: {processed}/{len(stories)} stories")
    return processed


def run_test_mode(story_id=None, use_pro=False, simple_prompt=False, open_browser=True):
    """
    Test mode: Generate thumbnails for a story and create an HTML preview.
    
    Args:
        story_id: Optional specific story generation ID. If None, picks a random one.
        use_pro: Use Nano Banana Pro model
        simple_prompt: Use simplified prompt format
        open_browser: Automatically open the preview in browser
    
    Returns:
        str: Path to the generated preview HTML
    """
    logger.info("=" * 60)
    logger.info("THUMBNAIL GENERATOR - TEST MODE")
    logger.info("=" * 60)
    
    # Get story
    if story_id:
        logger.info(f"Fetching story {story_id}...")
        story = db.get_story_generation(story_id)
        if not story:
            logger.error(f"Story {story_id} not found")
            return None
    else:
        logger.info("Fetching a random story for testing...")
        stories = db.get_stories_needing_thumbnails(limit=1)
        if not stories:
            # Try getting any story (even if it has thumbnails)
            logger.info("No stories without thumbnails, fetching any completed story...")
            stories = get_any_story_for_test()
        
        if not stories:
            logger.error("No stories found in database")
            return None
        
        story = stories[0] if isinstance(stories, list) else stories
    
    logger.info(f"Testing with story: {story['hook_title']}")
    logger.info("-" * 60)
    
    # Process the story (skip_db=True for test mode to not duplicate records)
    # Actually, let's save to DB but generate preview anyway
    result = process_story(
        story, 
        use_pro=use_pro, 
        simple_prompt=simple_prompt,
        skip_db=False  # Save to DB so we can track
    )
    
    thumbnails = result['thumbnails']
    
    # Filter to only generated thumbnails
    generated_thumbnails = [t for t in thumbnails if t.get('status') == 'generated']
    
    if not generated_thumbnails:
        logger.error("No thumbnails were successfully generated")
        return None
    
    logger.info("-" * 60)
    logger.info(f"Successfully generated {len(generated_thumbnails)}/3 thumbnails")
    
    # Generate preview HTML
    logger.info("Generating preview HTML...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    preview_path = os.path.join(config.OUTPUT_DIR, f"test_preview_{timestamp}.html")
    
    # Also save to a fixed location for easy access
    latest_preview_path = os.path.join(config.OUTPUT_DIR, "test_preview.html")
    
    story_data = {
        'hook_title': story['hook_title'],
        'subtitle': story['subtitle'],
        'domain_tag': story['domain_tag']
    }
    
    # Generate both files
    generate_preview_html(story_data, generated_thumbnails, preview_path)
    generate_preview_html(story_data, generated_thumbnails, latest_preview_path)
    
    logger.info("=" * 60)
    logger.info(f"✓ Preview saved: {preview_path}")
    logger.info(f"✓ Latest preview: {latest_preview_path}")
    logger.info("=" * 60)
    
    # Open in browser
    if open_browser:
        try:
            webbrowser.open(f"file://{os.path.abspath(latest_preview_path)}")
            logger.info("Opened preview in browser")
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")
            logger.info(f"Open manually: file://{os.path.abspath(latest_preview_path)}")
    
    return latest_preview_path


def get_any_story_for_test():
    """Get any story with a generation for testing (even if it has thumbnails)."""
    conn = db.get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT 
                    sg.id as generation_id,
                    sg.hook_title,
                    sg.subtitle,
                    sg.domain_tag,
                    sr.research_data,
                    l.title as lead_title,
                    l.summary as lead_summary
                FROM story_generations sg
                JOIN story_research sr ON sg.story_research_id = sr.id
                JOIN leads l ON sr.lead_id = l.id
                ORDER BY sg.created_at DESC
                LIMIT 1
            """
            cur.execute(query)
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching story: {e}")
        return []
    finally:
        conn.close()


def process_single_story(generation_id, use_pro=False, simple_prompt=False):
    """
    Process a specific story by its generation_id.
    
    Args:
        generation_id: UUID of the story_generation
        use_pro: Use Nano Banana Pro model
        simple_prompt: Use simplified prompt format
    
    Returns:
        dict with 'thumbnail_ids', 'thumbnails'
    """
    logger.info(f"Fetching story generation {generation_id}...")
    story = db.get_story_generation(generation_id)
    
    if not story:
        logger.error(f"Story generation {generation_id} not found")
        return {'thumbnail_ids': [], 'thumbnails': []}
    
    return process_story(story, use_pro=use_pro, simple_prompt=simple_prompt)


def select_best_thumbnail(generation_id, thumbnail_id=None):
    """
    Select a thumbnail as the chosen one for a story.
    If thumbnail_id is not provided, auto-selects the first generated one.
    
    Args:
        generation_id: UUID of the story_generation
        thumbnail_id: Optional specific thumbnail to select
    """
    if thumbnail_id:
        db.select_thumbnail(thumbnail_id)
        logger.info(f"Selected thumbnail {thumbnail_id}")
    else:
        # Auto-select first generated thumbnail
        thumbnails = db.get_thumbnails_for_story(generation_id)
        generated = [t for t in thumbnails if t['status'] == 'generated']
        
        if generated:
            db.select_thumbnail(generated[0]['id'])
            logger.info(f"Auto-selected thumbnail {generated[0]['id']}")
        else:
            logger.warning(f"No generated thumbnails found for story {generation_id}")


def main():
    """Main entry point with CLI."""
    parser = argparse.ArgumentParser(
        description='Generate AI cover images for TheBoldUnknown stories'
    )
    
    parser.add_argument(
        '--test', '-t',
        action='store_true',
        help='Test mode: generate thumbnails and open HTML preview'
    )
    
    parser.add_argument(
        '--story-id', '-s',
        type=str,
        help='Process a specific story generation ID'
    )
    
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=None,
        help='Maximum number of stories to process'
    )
    
    parser.add_argument(
        '--pro',
        action='store_true',
        help='Use Nano Banana Pro (Gemini 3 Pro) for higher quality'
    )
    
    parser.add_argument(
        '--simple-prompt',
        action='store_true',
        help='Use simplified prompt format'
    )
    
    parser.add_argument(
        '--select', '-S',
        type=str,
        help='Select a specific thumbnail ID as the chosen one'
    )
    
    parser.add_argument(
        '--auto-select',
        action='store_true',
        help='Automatically select the first generated thumbnail for each story'
    )
    
    parser.add_argument(
        '--no-browser',
        action='store_true',
        help='In test mode, do not automatically open browser'
    )
    
    args = parser.parse_args()
    
    # Handle selection
    if args.select:
        db.select_thumbnail(args.select)
        logger.info(f"Selected thumbnail {args.select}")
        return
    
    # Test mode
    if args.test:
        preview_path = run_test_mode(
            story_id=args.story_id,
            use_pro=args.pro,
            simple_prompt=args.simple_prompt,
            open_browser=not args.no_browser
        )
        if preview_path:
            print(f"\n✓ Preview ready: {preview_path}")
        return
    
    # Process stories
    if args.story_id:
        result = process_single_story(
            args.story_id, 
            use_pro=args.pro, 
            simple_prompt=args.simple_prompt
        )
        thumbnail_ids = result.get('thumbnail_ids', []) if isinstance(result, dict) else result
        
        if args.auto_select and thumbnail_ids:
            select_best_thumbnail(args.story_id)
    else:
        processed = process_pending_stories(
            limit=args.limit, 
            use_pro=args.pro, 
            simple_prompt=args.simple_prompt
        )
        
        if args.auto_select and processed > 0:
            logger.info("Auto-select requested - thumbnails need manual selection or use --select")


if __name__ == "__main__":
    main()
