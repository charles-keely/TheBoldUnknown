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

    # Storage for generated images
    # - "supabase": upload to Supabase Storage and store a public URL in DB
    # - "db_base64": store base64 PNG in story_thumbnails.generation_metadata (no local files)
    # - "auto": prefer supabase when configured, else db_base64
    THUMBNAIL_STORAGE_MODE = os.getenv("THUMBNAIL_STORAGE_MODE", "auto").lower()

    # Supabase Storage (optional, used when THUMBNAIL_STORAGE_MODE is "supabase" or auto)
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    # Accept several common names so we don't require env renames
    SUPABASE_SERVICE_ROLE_KEY = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_KEY")
    )
    SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "story-thumbnails")
    # If bucket is public we can construct a stable public URL.
    # If false and you need private objects, we'd need to mint signed URLs.
    SUPABASE_STORAGE_PUBLIC = os.getenv("SUPABASE_STORAGE_PUBLIC", "true").lower() in ("1", "true", "yes", "y", "on")
    
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

    def resolved_storage_mode(self) -> str:
        mode = (self.THUMBNAIL_STORAGE_MODE or "auto").lower()
        if mode != "auto":
            return mode
        if self.SUPABASE_URL and self.SUPABASE_SERVICE_ROLE_KEY:
            return "supabase"
        return "db_base64"


config = Config()

# Create output directory if it doesn't exist
os.makedirs(config.OUTPUT_DIR, exist_ok=True)
