import json
from typing import Any, Dict, List, Optional

from openai import OpenAI

from .config import config


class PhotoPlacer:
    """
    Uses GPT to decide:
    - which approved photo is the single best "hero" photo
    - where each approved photo should be inserted among the story slides
    - all non-hero photos start disabled

    Placement convention:
    - after_slide_order = 0  → insert right after cover, before text slide 1
    - after_slide_order = k  → insert right after text slide k (k is 1..N)
    """

    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = getattr(config, "PLACER_MODEL", None) or config.QUERY_GENERATOR_MODEL

    def place_photos(
        self,
        *,
        story_title: str,
        slides: List[Dict[str, Any]],
        photos: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not slides or not photos:
            return None

        # Keep prompts bounded
        slide_lines: List[str] = []
        for s in slides:
            so = s.get("slide_order")
            txt = (s.get("text_content") or "").strip()
            if not txt:
                continue
            slide_lines.append(f"[Slide {so}] {txt[:600]}")

        photo_lines: List[str] = []
        for p in photos:
            pid = str(p.get("id"))
            desc = (p.get("description") or "").strip()
            q = (p.get("search_query") or "").strip()
            rel = p.get("relevance_score")
            ver = p.get("verifiability_score")
            meta = p.get("metadata") if isinstance(p.get("metadata"), dict) else {}
            aesthetic = None
            try:
                aesthetic = (meta.get("aesthetic_score") if isinstance(meta, dict) else None)
            except Exception:
                aesthetic = None
            photo_lines.append(
                f"[Photo {pid}] rel={rel} ver={ver} aesthetic={aesthetic} query={q!r}\n"
                f"desc: {desc[:500]}"
            )

        n_slides = len([s for s in slides if s.get("text_content")])

        system_prompt = """You are the photo placement editor for an Instagram carousel story.

You will receive:
- Story title
- Text slides (ordered)
- Approved photo candidates (each with an id + description + scores)

Your job:
1) Choose ONE "hero" photo: the single most useful + striking + story-relevant image.
2) For EVERY photo, choose where it belongs between slides by selecting an integer after_slide_order:
   - 0 means: insert after the cover, before slide 1
   - k (1..N) means: insert after text slide k
3) Only the hero photo starts enabled. All others must start disabled.

Rules:
- Return STRICT JSON (no markdown).
- after_slide_order must be an integer between 0 and N (inclusive).
- placements must include EACH provided photo exactly once.
- Exactly one placement must have enabled=true, and it MUST match hero_photo_id.
- Prefer placing a photo immediately after the slide that introduces/mentions what is shown.
"""

        user_payload = {
            "story_title": story_title,
            "N": n_slides,
            "slides": slide_lines[:12],  # stories are typically <= 9 slides; cap anyway
            "photos": photo_lines[:24],  # cap to keep context small
        }

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or "{}"
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            data = json.loads(content)
            if not isinstance(data, dict):
                return None
            return data
        except Exception as e:
            print(f"Error placing photos: {e}")
            return None



