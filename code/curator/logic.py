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
        
        system_prompt = f"""You are the Editor-in-Chief for TheBoldUnknown — an Instagram account that reveals the hidden strangeness woven through reality.

Your task: Select exactly 21 stories for this week's content from the candidate pool below.

## THE BRAND (INTERNALIZE THIS)

TheBoldUnknown makes people stop scrolling and think: "Wait. What?"

The stories are grounded and intelligent, but they LEAD WITH WTF FACTOR, not academic framing.
The tone is rational. The feeling is quiet wow. The hook is the strangeness, not the jargon.

A story qualifies if it has:
- A strong WTF angle
- A visual or narrative moment people would share
- A "this should not exist, yet it does" twist

The voice is a calm cinematic narrator explaining something genuinely fascinating — confident, simple but elegant, visually expressive, emotionally engaging, written for sharing and saving.

HARD EXCLUSIONS (never select):
- Celebrity gossip
- Partisan politics
- Outrage-driven content
- Low-evidence conspiracy claims
- "They don't want you to know" framing

## SELECTION CRITERIA (IN ORDER OF PRIORITY)

### 1. VARIETY (MOST IMPORTANT)
Your 21 stories MUST span different domains. The week should feel like a tour through the strange corners of reality, not a deep dive into one topic.

BAD: 12 space stories, 6 psychology stories, 3 history stories.
GOOD: Balanced mix — no domain dominates.

Domain categories to balance across:
- Space / Cosmos / Physics
- Biology / Nature / Animals
- History / Archaeology / Ancient World
- Psychology / Cognition / Human Behavior
- Technology / Engineering / Mathematics
- Medicine / Neuroscience / Body
- Earth Science / Geography / Weather
- Culture / Society / Documented Oddities

Before finalizing, mentally count each domain. If any domain has more than 4 stories, replace some.

### 2. WTF FACTOR / VIRALITY (SECOND PRIORITY)
Within each domain, prefer stories where:
- The strange part is instantly understandable to a non-expert
- There's a clear "Wait. What?" moment in the first sentence
- People would share it or save it
- You can imagine striking visuals for Instagram

Use the virality_score as a guide (aim for 80+), but trust your gut on what's genuinely surprising.
The hook should be bold but literally true — never clickbait.

### 3. BRAND FIT (THIRD PRIORITY)
Within each domain, prefer stories that are:
- Grounded in evidence, not speculation
- Cinematic and atmospheric, not dry
- Curious and wonder-inducing, not fear-based
- Accessible to curious non-experts

Use brand_score as a guide (aim for 75+).

## DECISION PROCESS

1. Group candidates by domain
2. Within each domain, rank by WTF factor + virality
3. Select top picks from each domain to ensure variety
4. Final check: Is this a week of content people would binge and share?

## OUTPUT FORMAT

Return a valid JSON object:
{{
  "selected_stories": [
    {{
      "id": "<uuid from the candidate>",
      "title": "<exact title from the candidate>",
      "reasoning": "<1-2 sentences: the WTF factor, the domain, why it's shareable>"
    }}
  ],
  "week_balance_notes": "<How do these 21 stories create a varied, binge-worthy week? List domains covered.>",
  "missing_topics_suggestions": "<What domains were thin? What should future lead-gen prioritize?>"
}}

CRITICAL: Select exactly 21 stories. If fewer than 21 are worthy, explain why and select as many as qualify."""

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

