import httpx
from config import config
from utils.logger import logger
from typing import List, Dict, Any
import json

class PerplexityService:
    def __init__(self):
        self.api_key = config.PERPLEXITY_API_KEY
        self.base_url = "https://api.perplexity.ai/chat/completions"
        self.model = config.PERPLEXITY_MODEL

    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Queries Perplexity and returns a list of lead candidates.
        """
        if not self.api_key:
            logger.error("Perplexity API key not set")
            return []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Prompt for Perplexity to return structured data
        messages = [
            {
                "role": "system",
                "content": "Find 5 specific, documented stories or research papers related to the query. Return them as a JSON list with keys: 'title', 'url', 'summary'."
            },
            {
                "role": "user",
                "content": query
            }
        ]

        payload = {
            "model": self.model,
            "messages": messages
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(self.base_url, headers=headers, json=payload)
                response.raise_for_status()
                
                data = response.json()
                content = data['choices'][0]['message']['content']
                
                # Parse the content
                # Note: Perplexity might return text + JSON, so we rely on LLM or robust parsing elsewhere
                # But for now let's try to parse simple JSON if it's clean, or return text to be processed
                
                # The n8n guide suggests using an OpenAI node to parse Perplexity output if it's not clean JSON.
                # In this Python implementation, we can call the LLM service to normalize if JSON parse fails.
                # For now, let's assume we need to normalize it.
                
                return content # Return raw content for normalization by LLM

        except Exception as e:
            logger.error(f"Error querying Perplexity: {e}")
            return []

perplexity_service = PerplexityService()
