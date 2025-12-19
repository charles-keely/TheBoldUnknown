import os
from dotenv import load_dotenv

# Load environment variables from the root .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


class Config:
    # Database
    POSTGRES_HOST = os.getenv('POSTGRES_HOST')
    POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
    POSTGRES_DB = os.getenv('POSTGRES_DB')
    POSTGRES_USER = os.getenv('POSTGRES_USER')
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')

    # OpenAI (for prompt generation)
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    PROMPT_GENERATOR_MODEL = "gpt-5.2"

    # Google/Gemini (Nano Banana) for image generation
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    
    # Nano Banana = gemini-2.5-flash-image (fast)
    # Nano Banana Pro = gemini-3-pro-image-preview (advanced, supports 4K)
    IMAGE_MODEL = "gemini-2.5-flash-image"
    IMAGE_MODEL_PRO = "gemini-3-pro-image-preview"
    
    # Image dimensions for Instagram cover (1080x1350 = 4:5 aspect ratio)
    # Gemini 2.5 Flash generates 896x1152 for 4:5
    # Gemini 3 Pro can generate up to 4K
    IMAGE_ASPECT_RATIO = "4:5"
    IMAGE_SIZE = "1K"  # "1K", "2K", "4K" (Pro only)

    # Paths
    BRAND_GUIDE_PATH = os.path.join(os.path.dirname(__file__), '..', 'brand-guide2.md')
    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')


config = Config()

# Create output directory if it doesn't exist
os.makedirs(config.OUTPUT_DIR, exist_ok=True)
