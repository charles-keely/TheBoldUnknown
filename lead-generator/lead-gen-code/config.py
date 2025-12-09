import os
from pathlib import Path
from dotenv import load_dotenv
import sys

# Load environment variables from the root .env file
# We try to find the .env file in the parent directory of lead-gen-code
# AND in the current directory as a fallback.

# 1. Try parent of this file's directory (lead-generator/.env)
env_path_parent = Path(__file__).resolve().parent.parent / '.env'

# 2. Try current working directory (lead-generator/lead-gen-code/.env)
env_path_cwd = Path.cwd() / '.env'

# Load
if env_path_parent.exists():
    load_dotenv(dotenv_path=env_path_parent)
    # print(f"Loaded .env from: {env_path_parent}") 
elif env_path_cwd.exists():
    load_dotenv(dotenv_path=env_path_cwd)
    # print(f"Loaded .env from: {env_path_cwd}")
else:
    print(f"WARNING: Could not find .env file at {env_path_parent} or {env_path_cwd}")

class Config:
    # Database
    POSTGRES_HOST = os.getenv("POSTGRES_HOST")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB")
    POSTGRES_USER = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
    
    # API Keys
    PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # Models
    OPENAI_MODEL_MINI = "gpt-4o-mini"
    OPENAI_MODEL_MAIN = "gpt-4o"
    OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
    PERPLEXITY_MODEL = "sonar-pro"

    # Application Settings
    RSS_BATCH_SIZE = 1
    FILTER_BATCH_SIZE = 20
    SIMILARITY_THRESHOLD = 0.80  # 85% similar = duplicate (strict)
    VIRALITY_THRESHOLD = 80      # Stories must score 80+ virality to proceed
    BRAND_THRESHOLD = 70         # Stories must score 70+ brand fit to be saved
    
    # Testing / Limits
    MAX_CANDIDATES = None         # Set to None for unlimited, or a number to cap ingestion
    
    @property
    def DATABASE_URL(self):
        # Graceful handling if env vars are missing
        if not self.POSTGRES_USER or not self.POSTGRES_HOST:
            return "postgresql://user:pass@localhost:5432/db"
            
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

config = Config()
