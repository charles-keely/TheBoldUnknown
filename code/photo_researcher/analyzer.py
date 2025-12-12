import json
import base64
import requests
from openai import OpenAI
from .config import config

class VisualAnalyzer:
    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.VISION_MODEL

    def _encode_image(self, image_url):
        try:
            # Fake user agent to prevent 403s
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(image_url, headers=headers, timeout=10)
            if response.status_code == 200:
                return base64.b64encode(response.content).decode('utf-8'), response.headers.get('Content-Type', 'image/jpeg')
        except Exception as e:
            print(f"Failed to download image for encoding: {e}")
        return None, None

    def analyze(self, image_url, story_context, source_context={}):
        """
        Analyzes the image using AI Vision AND Source Page Context to verify relevance.
        """
        print(f"Analyzing image: {image_url}...")
        
        # Download and base64 encode the image
        base64_image, mime_type = self._encode_image(image_url)
        
        if not base64_image:
             return {
                "description": "Failed to download image for analysis",
                "relevance_score": 0,
                "verifiability_score": 0,
                "status": "rejected",
                "metadata": {"error": "Download failed"}
            }

        system_prompt = """You are a photo editor for 'TheBoldUnknown'.
Your job is to verify if an image is relevant to a specific story and extract metadata.

You will be provided with:
1. Story Context (what the story is about)
2. Source Page Context (text found on the webpage where the image is hosted)
3. The Image itself

Analyze these inputs combined.

Output a JSON object with:
- "description": A SPECIFIC description of the image content using facts from the Source Page Context (e.g., "Dr. Scott Waitukaitis in his lab at ISTA, 2025" instead of "A man in a lab").
- "relevance_score": 0-10 (10 = Perfect match to story details, 0 = Irrelevant).
- "verifiability_score": 0-10 (High score if the Source Page Context confirms the image content matches the Story).
- "metadata": {
    "year": "YYYY or null",
    "author": "string or null",
    "source_title": "string or null",
    "text_in_image": "string or null",
    "style": "photo/illustration/diagram/map",
    "aesthetic_score": 0-10 (How visually striking/beautiful is it? 10=Cinematic/Stunning, 0=Blurry/Ugly),
    "aesthetic_quality": "string (e.g. 'cinematic', 'gritty', 'archival', 'amateur', 'clean', 'cluttered')",
    "usability_score": 0-10 (How usable is this image? 10=High Res/Clean/No Watermarks, 0=Blurry/Obtrusive Watermarks/Bad Cropping),
    "is_ai_generated": boolean (true if the image looks like AI generation, false if it looks like a real photo/diagram)
  }
- "status": "approved" if relevance >= 7 and verifiability >= 6 and usability_score >= 6 and not is_ai_generated, else "rejected".
"""

        user_prompt = f"""
Story Context:
{story_context[:2000]}

Source Page Context:
Title: {source_context.get('page_title', 'N/A')}
Description: {source_context.get('page_description', 'N/A')}
Captions/Text: {source_context.get('captions', '')}
{source_context.get('page_text', '')[:1000]}

Image URL: {image_url}
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user", 
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_completion_tokens=500,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            # Sanitize content: sometimes models output markdown code blocks with JSON
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            return json.loads(content)
            
        except Exception as e:
            print(f"Analysis failed: {e}")
            return {
                "description": "Analysis failed",
                "relevance_score": 0,
                "verifiability_score": 0,
                "status": "rejected",
                "metadata": {"error": str(e)}
            }
