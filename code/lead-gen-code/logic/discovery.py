import random
from typing import List
from services.llm import llm
from utils.logger import logger
import json
import datetime

class DiscoveryEngine:
    def __init__(self):
        pass

    def generate_fresh_topics(self, count: int = 5) -> List[str]:
        """
        Generates fresh, BROAD search topics.
        We want to find clusters of strange stories, not single niche needles.
        """
        current_year = datetime.datetime.now().year
        
        system_prompt = f"""You are the "Discovery Engine" for TheBoldUnknown.
Your goal is to generate BROAD SEARCH QUERIES that will surface lists of recent scientific anomalies, strange historical documents, or unexplained phenomena.

STRATEGY:
- Do NOT generate narrow, specific queries like "weather in 15th century art".
- DO generate broad "list-generating" queries like "unexplained atmospheric phenomena {current_year}" or "recent archaeological anomalies in peer reviewed journals".
- The goal is to cast a wide net into "The Unknown" so Perplexity can find multiple stories.

DOMAINS TO EXPLORE (Pick different ones each time):
- Physics & Cosmology anomalies
- Biological & Evolutionary puzzles
- Archaeology & History (Out of place artifacts)
- Cognitive Science & Psychology (Counterintuitive findings)
- Technology & AI Glitches
- Oceanography & Deep Earth mysteries

Output ONLY a JSON list of strings: ["query 1", "query 2", "query 3"]"""
        
        user_prompt = "Generate 3 broad, high-potential search queries for finding documented anomalies and strange news."
        
        try:
            topics_response = llm.chat_completion_json(system_prompt, user_prompt)
             # Handle list or dict output
            if isinstance(topics_response, list):
                topics = topics_response
            elif isinstance(topics_response, dict):
                 # Try to find the first list value
                found_list = False
                for v in topics_response.values():
                    if isinstance(v, list):
                        topics = v
                        found_list = True
                        break
                if not found_list:
                    topics = []
            else:
                topics = []
                
        except Exception as e:
            logger.error(f"Discovery Engine error: {e}")
            topics = [f"recent scientific anomalies {current_year}", "unexplained archaeological discoveries"]

        logger.info(f"[DISCOVERY] Generated Fresh Topics: {topics}")
        
        # Enforce limits
        return topics[:count]

discovery_engine = DiscoveryEngine()
