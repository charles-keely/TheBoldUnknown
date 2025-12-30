import argparse
from typing import Any, Dict, List

from .db import Database
from .researcher import _extract_urls_from_text


def _count_search_results(obj: Any) -> int:
    if isinstance(obj, list):
        return sum(1 for x in obj if isinstance(x, dict) and x.get("url"))
    return 0


def audit_row(row: Dict[str, Any]) -> Dict[str, Any]:
    research_data = row.get("research_data") or {}
    if not isinstance(research_data, dict):
        research_data = {}

    ground_truth = str(research_data.get("ground_truth") or "")
    follow_up = research_data.get("follow_up") or {}
    if not isinstance(follow_up, dict):
        follow_up = {}

    gt_urls = _extract_urls_from_text(ground_truth)
    fu_urls = _extract_urls_from_text(str(follow_up.get("answer") or ""))

    gt_sr = research_data.get("ground_truth_search_results") or []
    fu_sr = follow_up.get("search_results") or []

    return {
        "research_id": row.get("research_id"),
        "lead_title": row.get("lead_title"),
        "lead_url": row.get("lead_url"),
        "ground_truth_chars": len(ground_truth),
        "urls_in_ground_truth": len(gt_urls),
        "urls_in_follow_up": len(fu_urls),
        "ground_truth_search_results": _count_search_results(gt_sr),
        "follow_up_search_results": _count_search_results(fu_sr),
        "ground_truth_preview": (ground_truth[:350] + ("…" if len(ground_truth) > 350 else "")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit completed rows with empty primary_sources")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    db = Database()
    try:
        rows = db.fetch_completed_empty_primary_sources(limit=args.limit)
        if not rows:
            print("No completed rows with empty primary_sources found.")
            return

        print(f"Found {len(rows)} completed rows with empty primary_sources.")
        print()

        for row in rows:
            info = audit_row(row)
            print(f"- {info['research_id']} | {info['lead_title']}")
            print(f"  lead_url: {info['lead_url']}")
            print(
                "  evidence: "
                f"gt_search_results={info['ground_truth_search_results']}, "
                f"fu_search_results={info['follow_up_search_results']}, "
                f"urls_in_gt={info['urls_in_ground_truth']}, "
                f"urls_in_fu={info['urls_in_follow_up']}, "
                f"gt_chars={info['ground_truth_chars']}"
            )
            print(f"  ground_truth_preview: {info['ground_truth_preview']}")
            print()

        print("Interpretation:")
        print("- If gt_search_results and fu_search_results are 0 AND urls_in_* are 0, the original research run did not persist citations/URLs.")
        print("- In that case, the only reliable fix is to re-run research for those stories with the updated Perplexity citation capture.")
    finally:
        db.close()


if __name__ == "__main__":
    main()



