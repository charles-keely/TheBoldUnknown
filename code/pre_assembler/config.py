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
    
    # Server
    HOST = os.getenv('PRE_ASSEMBLER_HOST', '0.0.0.0')
    PORT = int(os.getenv('PRE_ASSEMBLER_PORT', '8000'))
    DEBUG = os.getenv('PRE_ASSEMBLER_DEBUG', 'true').lower() in ('true', '1', 'yes')
    
    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATIC_DIR = os.path.join(BASE_DIR, 'static')
    TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
    TEMPLATE_DESIGN_DIR = os.path.join(BASE_DIR, '..', 'template_design')
    
    # Template image assets path (relative URL for templates)
    TEMPLATE_IMG_PATH = '/template-assets/img'


config = Config()

# Create static directory if it doesn't exist
os.makedirs(config.STATIC_DIR, exist_ok=True)
os.makedirs(os.path.join(config.STATIC_DIR, 'js'), exist_ok=True)
os.makedirs(os.path.join(config.STATIC_DIR, 'css'), exist_ok=True)
