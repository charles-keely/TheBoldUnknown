import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path

# Add parent dir to path to allow imports if needed, though we use relative imports inside package
sys.path.append(str(Path(__file__).resolve().parent.parent))

from curator.db import Database
from curator.logic import CuratorLogic
from curator.config import config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('curator.log')
    ]
)
logger = logging.getLogger("curator")

def main():
    parser = argparse.ArgumentParser(description="Curator Agent for TheBoldUnknown")
    parser.add_argument("--dry-run", action="store_true", help="Run curation logic without updating the database.")
    args = parser.parse_args()

    logger.info("Starting Curator Agent...")
    if args.dry_run:
        logger.info("DRY RUN MODE ACTIVATED: No database changes will be made.")
    
    try:
        db = Database()
        logic = CuratorLogic()
        
        # 1. Determine Timeframe
        cutoff_date = db.get_latest_cutoff_date()
        logger.info(f"Looking for stories created after: {cutoff_date}")
        
        # 2. Fetch Candidates
        candidates = db.fetch_candidates(cutoff_date)
        logger.info(f"Found {len(candidates)} candidate stories.")
        
        if not candidates:
            logger.info("No new stories to curate. Exiting.")
            return

        # 3. Curate
        logger.info(f"Sending {len(candidates)} stories to {config.CURATOR_MODEL} for curation...")
        result = logic.curate_stories(candidates)
        
        # 4. Process Results
        logger.info("\n=== CURATION RESULTS ===")
        logger.info(f"Week Balance Notes: {result.week_balance_notes}")
        if result.missing_topics_suggestions:
            logger.info(f"Missing Topics: {result.missing_topics_suggestions}")
        
        logger.info(f"Selected {len(result.selected_stories)} stories:")

        # Write results to a readable text file
        output_file = Path("curation_results.txt")
        with open(output_file, "w") as f:
            f.write("=== CURATION REPORT ===\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Candidate Pool Size: {len(candidates)}\n")
            f.write(f"Model: {config.CURATOR_MODEL}\n\n")
            
            f.write("--- WEEKLY BALANCE NOTES ---\n")
            f.write(f"{result.week_balance_notes}\n\n")
            
            if result.missing_topics_suggestions:
                f.write("--- MISSING TOPICS / SUGGESTIONS ---\n")
                f.write(f"{result.missing_topics_suggestions}\n\n")

            f.write("--- SELECTED STORIES ---\n")
            for i, story in enumerate(result.selected_stories, 1):
                f.write(f"{i}. {story.title}\n")
                f.write(f"   ID: {story.id}\n")
                f.write(f"   Reason: {story.reasoning}\n")
                f.write("\n")
        
        logger.info(f"Detailed report written to {output_file.absolute()}")

        for story in result.selected_stories:
            logger.info(f"[SELECTED] {story.title} (ID: {story.id})")
            logger.info(f"  Reason: {story.reasoning}")
            
            # Update DB
            if not args.dry_run:
                try:
                    # We mark selected stories as 'approved' so they are ready for production
                    db.update_lead_status(story.id, 'approved')
                    logger.info("  -> Marked as APPROVED in DB")
                except Exception as e:
                    logger.error(f"  -> Failed to update DB for {story.id}: {e}")
            else:
                logger.info("  -> [Dry Run] Would mark as APPROVED in DB")
                
        logger.info("Curation cycle complete.")

    except Exception as e:
        logger.exception(f"An error occurred during curation: {e}")
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    main()

