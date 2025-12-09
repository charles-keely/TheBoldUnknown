import httpx
import json
from config import Config
from services.llm import llm
from models import LeadCandidate
from utils.logger import logger
from database import db
from tenacity import retry, stop_after_attempt, wait_exponential

class PerplexityService:
    def __init__(self):
        self.api_url = "https://api.perplexity.ai/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {Config.PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }

    def get_next_topic(self):
        """
        Fetch the next active topic that hasn't been searched recently.
        """
        query = """
            SELECT * FROM discovery_topics 
            WHERE status = 'active' 
            ORDER BY last_searched_at ASC NULLS FIRST 
            LIMIT 1;
        """
        return db.fetch_one(query)

    def update_topic_timestamp(self, topic_id):
        query = "UPDATE discovery_topics SET last_searched_at = NOW() WHERE id = %s"
        db.execute_query(query, (topic_id,))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def search(self, query_str: str) -> str:
        """
        Execute the search against Perplexity API.
        Searches for stories that fit TheBoldUnknown's lens: the quietly strange,
        counterintuitive, and scientifically intriguing.
        """
        system_content = """You are a research scout for TheBoldUnknown, a brand that explores the hidden strangeness woven through reality with calm, cinematic intelligence.

YOUR MISSION:
Find 5 specific, documented stories, research papers, or events related to the query that have "Quiet WTF" potential — the feeling of discovering something unusual inside something seemingly ordinary.

WHAT YOU ARE LOOKING FOR:
Stories that contain at least one of the following:
- A surprising, counterintuitive, or unexplained detail
- A pattern or behavior that defies intuition or expectation
- A historical, scientific, or psychological twist
- A documented event with puzzling or unusually specific elements
- A phenomenon that challenges perception, memory, or assumptions
- A natural or cosmic occurrence that inspires awe or unease
- Technology behaving unexpectedly or revealing hidden complexity
- Human experience that feels quietly uncanny or unusually consistent
- New research suggesting something unexpected, unresolved, or counter-narrative

SELECTION CRITERIA:
- Prefer documented, evidence-backed stories over speculation
- Prefer specific cases over general overviews
- Prefer stories where you can articulate "what is strange" in one sentence
- Include a mix of recent discoveries AND lesser-known historical cases
- Small, niche, or obscure stories are welcome if they have genuine strangeness

HARD EXCLUSIONS (Do not return):
- Celebrity gossip or drama
- Partisan politics or culture war content
- Pure outrage bait or fear-mongering
- Low-evidence conspiracy claims
- Generic news without a strange angle
- Product announcements or hype pieces

SUMMARY WRITING GUIDELINES:
For each story's summary, write 2-3 sentences that:
1. State what the story is about
2. Highlight what is strange, counterintuitive, or unexplained about it
3. Use calm, precise language — no hype, no clickbait, no sensationalism

OUTPUT FORMAT:
Return as a JSON list with keys: 'title', 'url', 'summary'
Each summary should clearly articulate what makes this story interesting through TheBoldUnknown's lens."""

        payload = {
            "model": "sonar-pro",
            "messages": [
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": query_str
                }
            ]
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(self.api_url, headers=self.headers, json=payload)
                response.raise_for_status()
                result = response.json()
                return result['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"Perplexity search failed: {e}")
            raise

    def parse_results(self, raw_content: str, source_topic: str) -> list[LeadCandidate]:
        """
        Parse the text/markdown output from Perplexity into LeadCandidates.
        Sometimes it returns raw text instead of JSON, so we might need to use an LLM to clean it up 
        if simple parsing fails, or just rely on the system prompt being obeyed.
        """
        try:
            # First try direct JSON parse
            # Often Perplexity wraps in ```json ... ```
            content = raw_content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            data = json.loads(content)
            
            # Handle if it returns a list directly or an object with a key
            stories = []
            if isinstance(data, list):
                stories = data
            elif isinstance(data, dict):
                # Look for common keys
                for key in ['stories', 'results', 'papers', 'articles']:
                    if key in data and isinstance(data[key], list):
                        stories = data[key]
                        break
            
            candidates = []
            for s in stories:
                candidates.append(LeadCandidate(
                    title=s.get('title', 'No Title'),
                    url=s.get('url', ''),
                    summary=s.get('summary', ''),
                    source_origin=f"Perplexity: {source_topic}"
                ))
            return candidates
            
        except json.JSONDecodeError:
            logger.warning("Failed to parse Perplexity JSON directly. Using fallback parsing.")
            # Fallback: simple text parsing or return empty if too risky
            return []

    def run_cycle(self) -> list[LeadCandidate]:
        """
        Run one cycle of: Get Topic -> Gen Query -> Search -> Parse
        """
        topic_row = self.get_next_topic()
        if not topic_row:
            logger.info("No active topics found.")
            return []
            
        topic = topic_row['topic']
        topic_id = topic_row['id']
        logger.info(f"Selected topic: {topic}")
        
        # Generate specific query
        search_query = llm.generate_search_query(topic)
        logger.info(f"Generated query: {search_query}")
        
        # Run search
        raw_result = self.search(search_query)
        
        # Parse
        candidates = self.parse_results(raw_result, topic)
        logger.info(f"Found {len(candidates)} candidates from Perplexity.")
        
        # Update timestamp
        self.update_topic_timestamp(topic_id)
        
        return candidates

perplexity_service = PerplexityService()
