from openai import OpenAI
from config import config
from utils.logger import logger
import json
from typing import List, Dict, Any

class LLMService:
    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model_mini = config.OPENAI_MODEL_MINI
        self.model_main = config.OPENAI_MODEL_MAIN
        self.embedding_model = config.OPENAI_EMBEDDING_MODEL

    def get_embedding(self, text: str) -> List[float]:
        try:
            text = text.replace("\n", " ")
            return self.client.embeddings.create(input=[text], model=self.embedding_model).data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return []

    def chat_completion(self, 
                        system_prompt: str, 
                        user_prompt: str, 
                        model: str = None, 
                        json_mode: bool = False) -> str:
        if model is None:
            model = self.model_mini
            
        try:
            params = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }
            if json_mode:
                params["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error in chat completion: {e}")
            return ""

    def chat_completion_json(self, system_prompt: str, user_prompt: str, model: str = None) -> Dict[str, Any]:
        content = self.chat_completion(system_prompt, user_prompt, model, json_mode=True)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON response from LLM")
            return {}

llm = LLMService()
