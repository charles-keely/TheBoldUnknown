import argparse
import sys
import os
import json
from pathlib import Path
from .db import Database
from .generator import QueryGenerator
from .searcher import ImageSearcher
from .validator import Validator
from .analyzer import VisualAnalyzer
from .scraper import PageScraper
from .placer import PhotoPlacer

def main():
    parser = argparse.ArgumentParser(description="Photo Researcher Worker")
    parser.add_argument("--single", action="store_true", help="Process only one story and exit (Testing Mode)")
    parser.add_argument("--limit", type=int, default=5, help="Limit number of stories to process")
    parser.add_argument("--save-output", action="store_true", help="Save detailed output to a file (for testing)")
    args = parser.parse_args()

    db = Database()
    generator = QueryGenerator()
    searcher = ImageSearcher()
    validator = Validator()
    analyzer = VisualAnalyzer()
    scraper = PageScraper()
    placer = PhotoPlacer()

    try:
        stories = db.fetch_stories_needing_photos(limit=1 if args.single else args.limit)
        
        if not stories:
            print("No stories found needing photos.")
            return

        print(f"Found {len(stories)} stories to process.")

        test_report = []

        for story in stories:
            story_research_id = story.get("story_research_id") or story.get("id")
            story_generation_id = story.get("story_generation_id")
            print(f"\n--- Processing: {story.get('title')} ---")
            
            # 1. Generate Queries
            queries = generator.generate_queries(story)
            print(f"Generated Queries: {queries}")
            
            story_report = {
                "title": story['title'],
                "queries": queries,
                "candidates": []
            }

            # 2. Search & Validate
            valid_candidates = []
            seen_urls = set()
            
            for query in queries:
                results = searcher.search(query, num_results=5) # Fetch top 5 per query
                
                for res in results:
                    url = res['image_url']
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    
                    if validator.check_url(url):
                        res['search_query'] = query
                        valid_candidates.append(res)
                    else:
                        print(f"Skipping invalid URL: {url}")

            # 3. Analyze & Save
            print(f"Analyzing {len(valid_candidates)} candidates...")
            
            for candidate in valid_candidates:
                # Get ground truth for context
                ground_truth = story.get('research_data', {}).get('ground_truth', '')
                
                # SCRAPE SOURCE CONTEXT
                source_url = candidate.get('source_page_url')
                source_context = {}
                if source_url:
                    source_context = scraper.scrape_context(source_url)
                
                # Analyze with extra context
                analysis = analyzer.analyze(candidate['image_url'], ground_truth, source_context)
                
                # Merge analysis into candidate data
                candidate.update(analysis)
                # Store source context in metadata for future reference
                if 'metadata' not in candidate:
                    candidate['metadata'] = {}
                candidate['metadata']['source_context'] = {
                    'title': source_context.get('page_title'),
                    'description': source_context.get('page_description')
                }
                
                # Save to DB
                photo_id = db.save_photo_candidate(story_research_id, candidate)
                print(f"Saved photo {photo_id} | Status: {candidate['status']} | Rel: {candidate['relevance_score']}")
                
                story_report["candidates"].append(candidate)

            # 4. Placement (after text generation exists)
            try:
                approved = db.fetch_approved_photos(str(story_research_id))
                if approved and story_generation_id and story.get("slides"):
                    placement = placer.place_photos(
                        story_title=str(story.get("title") or ""),
                        slides=list(story.get("slides") or []),
                        photos=[dict(p) for p in approved],
                    )
                    if placement and isinstance(placement, dict):
                        hero_id = placement.get("hero_photo_id")
                        placements = placement.get("placements") or []
                        # Normalize placements to our persisted shape
                        normalized = []
                        if isinstance(placements, list):
                            for p in placements:
                                if not isinstance(p, dict):
                                    continue
                                normalized.append(
                                    {
                                        "photo_id": str(p.get("photo_id") or "").strip(),
                                        "after_slide_order": p.get("after_slide_order", 0),
                                        "enabled": bool(p.get("enabled", False)),
                                        "reason": p.get("reason", ""),
                                    }
                                )
                        # Safety: ensure exactly one enabled
                        if hero_id:
                            hero_id = str(hero_id).strip()
                            found_hero = False
                            for p in normalized:
                                if str(p.get("photo_id")) == hero_id:
                                    p["enabled"] = True
                                    found_hero = True
                                else:
                                    p["enabled"] = False
                            if not found_hero and normalized:
                                normalized[0]["enabled"] = True
                        elif normalized:
                            normalized[0]["enabled"] = True
                            for p in normalized[1:]:
                                p["enabled"] = False

                        db.apply_photo_placements(
                            story_generation_id=str(story_generation_id),
                            placements=normalized,
                        )
                        story_report["placement"] = {
                            "hero_photo_id": str(hero_id) if hero_id else None,
                            "placements": normalized,
                        }
                        print("Saved photo placements.")
            except Exception as e:
                print(f"Placement step failed: {e}")

            test_report.append(story_report)
            
            if args.single:
                break
        
        # Save Report if requested
        if args.save_output and test_report:
            output_path = Path(__file__).resolve().parent / "photo_research_report.md"
            with open(output_path, "w") as f:
                f.write("# Photo Research Report\n\n")
                for s in test_report:
                    f.write(f"## Story: {s['title']}\n")
                    f.write(f"**Queries:** {', '.join(s['queries'])}\n\n")
                    if s.get("placement"):
                        f.write("### Placement (auto)\n")
                        f.write("```json\n")
                        f.write(json.dumps(s.get("placement"), indent=2, ensure_ascii=False))
                        f.write("\n```\n\n")
                    f.write("### Candidates:\n")
                    for c in s['candidates']:
                        f.write(f"#### Image: {c.get('status', 'unknown').upper()}\n")
                        f.write(f"- **URL:** {c['image_url']}\n")
                        f.write(f"- **Relevance:** {c.get('relevance_score')}/10\n")
                        f.write(f"- **Verifiability:** {c.get('verifiability_score')}/10\n")
                        f.write(f"- **Description:** {c.get('description')}\n")
                        f.write(f"- **Metadata:** {c.get('metadata')}\n")
                        f.write(f"![Image]({c['image_url']})\n\n")
                        f.write("---\n")
            print(f"\nReport saved to {output_path}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
