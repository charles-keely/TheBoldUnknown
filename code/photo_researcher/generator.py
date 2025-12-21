import json
from openai import OpenAI
from .config import config

class QueryGenerator:
    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.QUERY_GENERATOR_MODEL

    def generate_queries(self, story):
        """
        Generates search queries based on story research + generated story slides (when available).
        Returns a list of query strings.
        """
        ground_truth = story.get('research_data', {}).get('ground_truth', '')
        title = story.get('title', '')
        slides = story.get("slides") or []
        slide_snippets = []
        if isinstance(slides, list):
            for s in slides:
                if not isinstance(s, dict):
                    continue
                so = s.get("slide_order")
                txt = (s.get("text_content") or "").strip()
                if txt:
                    slide_snippets.append(f"[Slide {so}] {txt[:300]}")
        
        system_prompt = """You are an expert photo researcher for 'TheBoldUnknown'.
Your goal is to find high-quality, authentic images that visually represent a strange or surprising story.

Based on the story details provided (including the final narrative slides), generate 2-5 specific Google Image search queries.

Strategy:
- Focus on specific nouns (artifacts, places, people, documents).
- Use dates if relevant (e.g. "1923", "archival").
- Avoid generic terms like "mystery" or "strange".
- If the story is about a specific object, query that object's name.
- If the story is about a place, query the place name + specific feature.
- Prefer queries that match concrete visuals mentioned in individual slides.

Output Format:
Return ONLY a valid JSON object with a single key "queries" containing a list of strings.
Example: {"queries": ["Antikythera Mechanism fragment A", "Antikythera Mechanism 1901 discovery photo"]}
"""

        user_prompt = f"""
Story Title: {title}

Story Slides (snippets):
{chr(10).join(slide_snippets[:12])}

Research Highlights:
{ground_truth[:4000]} -- (truncated)
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            # Sanitize content for markdown code blocks
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
                
            data = json.loads(content)
            queries = data.get("queries", [])
            
            # Sanity check
            if not isinstance(queries, list):
                return [title]
                
            return queries[:5] # Limit to 5 max
            
        except Exception as e:
            print(f"Error generating queries: {e}")
            return [title] # Fallback to title
