import argparse
import sys
import os
from .db import Database
from .generator import QueryGenerator
from .searcher import ImageSearcher
from .validator import Validator
from .analyzer import VisualAnalyzer
from .scraper import PageScraper

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

    try:
        stories = db.fetch_stories_needing_photos(limit=1 if args.single else args.limit)
        
        if not stories:
            print("No stories found needing photos.")
            return

        print(f"Found {len(stories)} stories to process.")

        test_report = []

        for story in stories:
            print(f"\n--- Processing: {story['title']} ---")
            
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
                photo_id = db.save_photo_candidate(story['id'], candidate)
                print(f"Saved photo {photo_id} | Status: {candidate['status']} | Rel: {candidate['relevance_score']}")
                
                story_report["candidates"].append(candidate)

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
