"""
Configuration for Pipeline Manager.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables from root .env
env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()


class PipelineConfig(BaseSettings):
    """Pipeline Manager configuration."""
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = True
    
    # Database
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: str = os.getenv("POSTGRES_PORT", "5432")
    postgres_db: str = os.getenv("POSTGRES_DB", "")
    postgres_user: str = os.getenv("POSTGRES_USER", "")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    
    # Execution Limits
    max_stories_per_run: int = 21
    concurrent_workers: int = 3
    phase_timeout: int = 1800  # 30 minutes
    
    # Retry Configuration
    max_retries: int = 3
    retry_base_delay: float = 2.0
    retry_max_delay: float = 60.0
    
    # Phase-specific settings
    lead_gen_rss_enabled: bool = True
    lead_gen_perplexity_enabled: bool = True
    curation_story_count: int = 21
    
    # Pre-Assembler URL
    pre_assembler_url: str = os.getenv("PRE_ASSEMBLER_URL", "http://localhost:8000")
    
    # API Keys (for workers)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    perplexity_api_key: str = os.getenv("PERPLEXITY_API_KEY", "")
    
    # Paths
    base_dir: Path = Path(__file__).resolve().parent
    static_dir: Path = Path(__file__).resolve().parent / "static"
    
    @property
    def database_url(self) -> str:
        """Construct database URL from components."""
        if not self.postgres_user or not self.postgres_host:
            return "postgresql://user:pass@localhost:5432/db"
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    class Config:
        env_prefix = "PIPELINE_"


config = PipelineConfig()

# Create static directory if it doesn't exist
os.makedirs(config.static_dir, exist_ok=True)
os.makedirs(config.static_dir / "js", exist_ok=True)

