import random
from typing import List
from services.llm import llm
from utils.logger import logger
import json

class DiscoveryEngine:
    def __init__(self):
        pass

    def generate_fresh_topics(self, count: int = 5) -> List[str]:
        """
        Generates fresh, diverse search topics using an evolutionary approach.
        Instead of static lists, it asks the LLM to hallucinate new, grounded intersections.
        """
        
        # 1. Generate "Wild Intersections" (The Entropy Source)
        # We ask for weird fields of study that might uncover strange stories.
        
        system_prompt = """You are the "Entropy Engine" for TheBoldUnknown.
Your goal is to invent completely new, specific, and slightly weird "search angles" to find stories we would otherwise miss.

BRAND LENS: Grounded, Scientific, Quietly Strange, Cinematic.

TASK:
Invent 3 "Intersections" — places where two unrelated fields collide to reveal anomalies.
Examples:
- "Mycology + Computer Science" (Bio-computing networks)
- "Art History + Meteorology" (Weather anomalies in ancient paintings)
- "Oceanography + Acoustics" (Unexplained deep sea sounds)
- "Archaeology + Genetics" (DNA anomalies in ancient remains)

Return ONLY a JSON list of strings: ["intersection 1", "intersection 2", "intersection 3"]"""
        
        user_prompt = "Generate 3 new, wild, but grounded intersections for discovery."
        
        try:
            intersections_json = llm.chat_completion_json(system_prompt, user_prompt)
            # Handle list or dict output
            if isinstance(intersections_json, list):
                intersections = intersections_json
            elif isinstance(intersections_json, dict):
                intersections = list(intersections_json.values())[0] if intersections_json else []
            else:
                intersections = []
        except Exception as e:
            logger.error(f"Discovery Engine error (Intersections): {e}")
            intersections = ["Physics + Anomalies", "Biology + Glitch"] # Fallback

        if not intersections:
            intersections = ["History + Unexplained", "Space + Mystery"]

        logger.info(f"[DISCOVERY] Generated Intersections: {intersections}")

        # 2. Convert Intersections into Specific Search Topics
        # Now we ask the LLM to convert these abstract ideas into concrete search terms.
        
        topics_system_prompt = """You are the Lead Researcher for TheBoldUnknown.
Convert these abstract "Intersections" into SPECIFIC, SEARCHABLE TOPICS for Perplexity.

Goal: Find specific, documented anomalies or mysteries.
Avoid generic terms. Be specific.

Example Input: "Art History + Meteorology"
Example Output: "historical weather anomalies recorded in renaissance art"

Return ONLY a JSON list of search strings."""

        topics_user_prompt = f"""Convert these intersections into specific search topics:
{json.dumps(intersections)}

Output JSON: ["topic 1", "topic 2", "topic 3"]"""

        try:
            topics_response = llm.chat_completion_json(topics_system_prompt, topics_user_prompt)
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
            logger.error(f"Discovery Engine error (Topics): {e}")
            return []

        # Enforce limits
        return topics[:count]

discovery_engine = DiscoveryEngine()
