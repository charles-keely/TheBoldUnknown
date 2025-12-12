import argparse
import sys
import time
import json
from pathlib import Path
from .db import Database
from .researcher import Researcher

def save_results_to_file(story, results):
    """Saves research results to a readable Markdown file inside story_researcher/."""
    output_dir = Path(__file__).resolve().parent
    filename = output_dir / "research_output.md"
    
    follow_up = results.get("follow_up")
    
    with open(filename, "w") as f:
        f.write(f"# Research Report: {story['title']}\n")
        f.write(f"**URL:** {story['url']}\n\n")
        f.write("---\n\n")
        
        f.write("## Ground Truth\n\n")
        f.write(results.get("ground_truth", "No data found.") + "\n\n")
        
        # Only show follow-up section if there was one
        if follow_up:
            f.write("---\n\n")
            f.write("## Follow-Up Research\n\n")
            f.write(f"**Q:** {follow_up['question']}\n\n")
            f.write(f"{follow_up['answer']}\n\n")
            
    print(f"Research saved to {Path(filename).absolute()}")

def main():
    parser = argparse.ArgumentParser(description="Story Researcher Worker")
    parser.add_argument("--single", action="store_true", help="Process only one story and exit (Testing Mode)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of stories to process")
    args = parser.parse_args()

    db = Database()
    researcher = Researcher()

    try:
        limit = 1 if args.single else args.limit
        queue = db.fetch_queued_stories(limit=limit)
        
        if not queue:
            print("No queued stories found.")
            return

        print(f"Found {len(queue)} stories to research.")

        for story in queue:
            try:
                print(f"\n--- Processing: {story['title']} (ID: {story['research_id']}) ---")
                
                # Mark as in_progress
                db.update_status(story['research_id'], 'in_progress')
                
                # Execute Research
                results = researcher.research_story(story)
                
                # Save Results
                db.update_research_results(story['research_id'], results)
                print("Done. Saved results.")

                if args.single:
                    save_results_to_file(story, results)
                
            except Exception as e:
                print(f"Error processing story {story['title']}: {e}")
                # Optionally mark as failed or skipped, or just leave in_progress for retry
                # For now, let's just log it.
            
            if args.single:
                break
                
    except KeyboardInterrupt:
        print("\nStopping researcher...")
    finally:
        db.close()

if __name__ == "__main__":
    main()
