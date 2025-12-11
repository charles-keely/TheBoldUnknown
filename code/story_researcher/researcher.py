import requests
import json
from openai import OpenAI
from typing import List, Dict, Any
from .config import config
from .prompts import (
    get_phase_1_prompt, 
    get_phase_2_angle_prompt, 
    PHASE_1_SYSTEM_PROMPT, 
    PHASE_2_SYSTEM_PROMPT
)

class PerplexityClient:
    def __init__(self):
        self.api_key = config.PERPLEXITY_API_KEY
        self.base_url = "https://api.perplexity.ai/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def chat(self, messages: List[Dict[str, str]]) -> str:
        payload = {
            "model": config.PERPLEXITY_MODEL,
            "messages": messages,
            "temperature": 0.1
        }
        response = requests.post(self.base_url, json=payload, headers=self.headers)
        if not response.ok:
            print(f"Perplexity Error: {response.text}")
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

class Researcher:
    def __init__(self):
        self.pplx = PerplexityClient()
        self.openai = OpenAI(api_key=config.OPENAI_API_KEY)

    def research_story(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the 2-phase research process.
        """
        print(f"Starting research for: {story.get('title')}")
        
        # Phase 1: General Research (Perplexity)
        print("Phase 1: Gathering Ground Truth...")
        phase_1_prompt = get_phase_1_prompt(
            story.get('title'), 
            story.get('url'), 
            story.get('summary')
        )
        
        phase_1_messages = [
            {"role": "system", "content": PHASE_1_SYSTEM_PROMPT},
            {"role": "user", "content": phase_1_prompt}
        ]
        
        phase_1_result = self.pplx.chat(phase_1_messages)
        
        # Phase 2: Check for research gaps (OpenAI)
        print("Phase 2: Checking for research gaps...")
        phase_2_prompt = get_phase_2_angle_prompt(phase_1_result)
        
        phase_2_response = self.openai.chat.completions.create(
            model=config.RESEARCHER_MODEL,
            messages=[
                {"role": "system", "content": PHASE_2_SYSTEM_PROMPT},
                {"role": "user", "content": phase_2_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        gap_analysis = json.loads(phase_2_response.choices[0].message.content)
        follow_up_question = gap_analysis.get("follow_up_question")
        
        # Optional Deep Dive (Perplexity) - only if a follow-up question was generated
        deep_dive = None
        
        if follow_up_question:
            print(f"Follow-up needed: {follow_up_question}")
            
            deep_dive_system = """You are a specialized researcher for 'TheBoldUnknown'.
Focus on finding specific, vivid details that are:
- Visually striking or easy to imagine
- Strange, counterintuitive, or surprising
- Grounded in fact (label speculation clearly)
Be concise but thorough. Prioritize details that would make someone stop scrolling."""
            
            q_prompt = f"Regarding the story '{story.get('title')}': {follow_up_question}"
            
            q_messages = [
                {"role": "system", "content": deep_dive_system},
                {"role": "user", "content": q_prompt}
            ]
            answer = self.pplx.chat(q_messages)
            deep_dive = {"question": follow_up_question, "answer": answer}
        else:
            print("No follow-up needed — research is complete.")
            
        return {
            "ground_truth": phase_1_result,
            "follow_up": deep_dive
        }
