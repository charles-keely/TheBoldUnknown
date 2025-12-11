import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path_parent = Path(__file__).resolve().parent.parent / '.env'
env_path_cwd = Path.cwd() / '.env'

if env_path_parent.exists():
    load_dotenv(dotenv_path=env_path_parent)
elif env_path_cwd.exists():
    load_dotenv(dotenv_path=env_path_cwd)

class Config:
    # Database
    POSTGRES_HOST = os.getenv("POSTGRES_HOST")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB")
    POSTGRES_USER = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
    
    # API Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # Models
    CURATOR_MODEL = "gpt-5.1"  # As requested
    
    # Paths
    ROOT_DIR = Path(__file__).resolve().parent.parent
    BRAND_GUIDE_PATH = ROOT_DIR / "brand-guide.md"

    @property
    def DATABASE_URL(self):
        if not self.POSTGRES_USER or not self.POSTGRES_HOST:
             # Fallback/Placeholder
            return "postgresql://user:pass@localhost:5432/db"
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

config = Config()

