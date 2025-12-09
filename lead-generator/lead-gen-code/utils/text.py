import re
from bs4 import BeautifulSoup

def clean_html(text: str) -> str:
    """
    Remove HTML tags and clean up whitespace.
    """
    if not text:
        return ""
        
    # Use BeautifulSoup to strip tags
    soup = BeautifulSoup(text, "html.parser")
    text = soup.get_text(separator=" ")
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def truncate(text: str, max_length: int = 1500) -> str:
    """
    Truncate text to a maximum length.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
