import os
from dotenv import load_dotenv

# Load environment variables from the root .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

class Config:
    # Database
    POSTGRES_HOST = os.getenv('POSTGRES_HOST')
    POSTGRES_PORT = os.getenv('POSTGRES_PORT')
    POSTGRES_DB = os.getenv('POSTGRES_DB')
    POSTGRES_USER = os.getenv('POSTGRES_USER')
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')

    # OpenAI
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    # Using GPT-5.1 as requested for intelligent query generation and vision
    QUERY_GENERATOR_MODEL = "gpt-5.1"
    VISION_MODEL = "gpt-5.1" 

    # Google Custom Search
    GOOGLE_CUSTOM_SEARCH_KEY = os.getenv('GOOGLE_CUSTOM_SEARCH_KEY')
    GOOGLE_SEARCH_ENGINE_ID = "06b02557e79fa482e"


    # Paths
    BRAND_GUIDE_PATH = os.path.join(os.path.dirname(__file__), '..', 'brand-guide2.md')

config = Config()
