import argparse
from typing import Any, Dict, List
from typing import Optional

from .db import Database
from .researcher import (
    _dedupe_preserve_order,
    _extract_urls_from_text,
    _primary_sources_from_urls,
)


def build_primary_sources(existing: Dict[str, Any], *, lead_url: Optional[str]) -> Dict[str, Any]:
    urls: List[str] = []

    ground_truth = existing.get("ground_truth") or ""
    urls.extend(_extract_urls_from_text(ground_truth))

    follow_up = existing.get("follow_up") or {}
    if isinstance(follow_up, dict):
        urls.extend(_extract_urls_from_text(str(follow_up.get("answer") or "")))
        for sr in (follow_up.get("search_results") or []):
            if isinstance(sr, dict) and sr.get("url"):
                urls.append(str(sr["url"]))

    for sr in (existing.get("ground_truth_search_results") or []):
        if isinstance(sr, dict) and sr.get("url"):
            urls.append(str(sr["url"]))

    # Always add lead URL (useful context even if not a "primary" source).
    if lead_url:
        urls.append(str(lead_url))

    urls = _dedupe_preserve_order(urls)
    primary_sources, primary_source_urls = _primary_sources_from_urls(urls)

    updated = dict(existing)
    updated["primary_sources"] = primary_sources
    updated["primary_source_urls"] = primary_source_urls
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill story_research.research_data.primary_sources")
    parser.add_argument("--limit", type=int, default=None, help="Limit rows processed")
    parser.add_argument("--apply", action="store_true", help="Actually write updates to DB (default is dry-run)")
    args = parser.parse_args()

    db = Database()
    try:
        if args.apply and not db.has_primary_sources_columns:
            raise RuntimeError(
                "Missing required DB column public.story_research.primary_sources. "
                "Run the provided Supabase ALTER TABLE first, then re-run this backfill."
            )

        rows = db.fetch_completed_missing_primary_sources(limit=args.limit)
        if not rows:
            print("No completed research rows missing primary_sources found.")
            return

        print(f"Found {len(rows)} completed research rows missing primary_sources.")

        updated_count = 0
        for row in rows:
            research_id = row["research_id"]
            research_data = row.get("research_data") or {}
            lead_url = row.get("lead_url")

            if not isinstance(research_data, dict):
                # If stored as JSON string for some reason, skip safely.
                print(f"Skipping {research_id}: research_data is not an object.")
                continue

            updated = build_primary_sources(research_data, lead_url=lead_url)

            names = updated.get("primary_sources") or []
            urls = updated.get("primary_source_urls") or []
            print(f"- {research_id}: {len(names)} sources -> {names[:8]}{'...' if len(names) > 8 else ''}")

            if args.apply:
                # Keep JSON copy up-to-date too (handy for portability/debugging).
                db.overwrite_research_data(research_id, updated)
                db.update_primary_sources_columns(research_id, names, urls)
                updated_count += 1

        if args.apply:
            print(f"\nApplied updates to {updated_count} rows.")
        else:
            print("\nDry-run only. Re-run with --apply to write updates.")
    finally:
        db.close()


if __name__ == "__main__":
    main()



