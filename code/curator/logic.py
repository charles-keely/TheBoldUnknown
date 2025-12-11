import json
from pathlib import Path
from typing import List, Dict, Any
from openai import OpenAI
from .config import config
from .models import CurationResult

class CuratorLogic:
    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.brand_guide = self._load_brand_guide()

    def _load_brand_guide(self) -> str:
        if config.BRAND_GUIDE_PATH.exists():
            return config.BRAND_GUIDE_PATH.read_text(encoding='utf-8')
        return "Brand guidelines not found."

    def _format_candidates(self, candidates: List[Dict[str, Any]]) -> str:
        lines = []
        for c in candidates:
            # Handle potential None values safely
            title = c.get('title', 'Untitled')
            summary = c.get('summary', 'No summary')
            b_score = c.get('brand_score', 0)
            v_score = c.get('virality_score', 0)
            hook = c.get('viral_hook', 'N/A')
            
            lines.append(f"ID: {c['id']}")
            lines.append(f"Title: {title}")
            lines.append(f"Summary: {summary}")
            lines.append(f"Viral Hook: {hook}")
            lines.append(f"Brand Score: {b_score} | Virality Score: {v_score}")
            lines.append("---")
        return "\n".join(lines)

    def curate_stories(self, candidates: List[Dict[str, Any]]) -> CurationResult:
        if not candidates:
            raise ValueError("No candidates provided for curation.")

        formatted_candidates = self._format_candidates(candidates)
        
        system_prompt = f"""You are the Editor-in-Chief for TheBoldUnknown, a cinematic Instagram account that explores the hidden strangeness woven through reality.

Your task: Select exactly 21 stories for this week's content from the candidate pool below.

## BRAND IDENTITY (INTERNALIZE THIS)

TheBoldUnknown's lens is: grounded, rational, quietly strange, cinematic, evidence-minded, intellectually curious, calm, confident, and precise.

The emotional target is "Quiet WTF" — that moment when a thoughtful person pauses and thinks: "Wait… that is actually strange."

Stories must have a real, explainable core of strangeness. They can come from any domain: science, history, psychology, nature, space, technology, human experience, archaeology, mathematics, documented anomalies, or elegant scientific oddities.

HARD EXCLUSIONS (never select):
- Celebrity gossip or drama
- Partisan politics or culture war framing
- Pure outrage bait or fear-mongering
- Low-evidence conspiracy claims presented as fact
- Content whose only hook is shock or anger

## SELECTION CRITERIA (IN ORDER OF PRIORITY)

### 1. VARIETY (MOST IMPORTANT)
Your 21 stories MUST span different domains. A week of content should feel like a tour through the strange corners of reality, not a deep dive into one topic.

ANTI-PATTERN: Selecting 12 space stories, 6 psychology stories, 3 history story.
GOOD PATTERN: Balanced mix across domains.

Before finalizing, mentally categorize each selection. Ensure you don't over-index on any single domain.

Domain categories to balance across:
- Space / Cosmos / Physics
- Biology / Nature / Animals
- History / Archaeology / Ancient World
- Psychology / Cognition / Human Behavior
- Technology / Engineering / Mathematics
- Medicine / Neuroscience / Body
- Earth Science / Geography / Weather
- Culture / Society / Documented Oddities

### 2. VIRALITY POTENTIAL (SECOND PRIORITY)
Within each domain slot, prefer stories with:
- A strong, curiosity-driven hook (the "viral_hook" field)
- High virality_score (aim for 80+)
- A clear "wait, what?" moment that makes people want to share
- Visual potential for Instagram (can you imagine the imagery?)

The hook should be bold but literally true — never clickbait.

### 3. BRAND ALIGNMENT (THIRD PRIORITY)
Within each domain slot, prefer stories with:
- High brand_score (aim for 75+)
- Clear alignment with the "Quiet WTF" lens
- Evidence-based strangeness, not speculation
- Cinematic storytelling potential

## DECISION PROCESS

1. First pass: Group all candidates by domain category
2. Second pass: From each domain, identify the top candidates by virality + brand score
3. Third pass: Select 21 stories ensuring maximum domain diversity
4. Final check: Verify balanced distribution across domains.

## OUTPUT FORMAT

Return a valid JSON object:
{{
  "selected_stories": [
    {{
      "id": "<uuid from the candidate>",
      "title": "<exact title from the candidate>",
      "reasoning": "<1-2 sentences: why this story, what domain it covers, what makes it compelling>"
    }}
  ],
  "week_balance_notes": "<Describe how the 21 stories together create a varied, compelling week. List the domains covered.>",
  "missing_topics_suggestions": "<If the candidate pool was thin in certain domains, note which topics future lead generation should prioritize. Leave empty if the pool was well-balanced.>"
}}

CRITICAL: Select exactly 21 stories. If the pool has fewer than 21 quality candidates, explain in week_balance_notes and select as many as are worthy."""

        user_prompt = (
            f"Here are the candidate stories (Total: {len(candidates)}):\n\n"
            f"{formatted_candidates}"
        )

        response = self.client.chat.completions.create(
            model=config.CURATOR_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Received empty response from LLM")
            
        data = json.loads(content)
        return CurationResult(**data)

