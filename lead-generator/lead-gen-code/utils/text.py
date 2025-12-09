import re
import html

def clean_text(text: str) -> str:
    """
    Cleans and normalizes text.
    1. Unescapes HTML entities.
    2. Removes HTML tags.
    3. Collapses whitespace.
    """
    if not text:
        return ""
    
    # Unescape HTML
    text = html.unescape(text)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def normalize_url(url: str) -> str:
    """
    Normalizes a URL by removing tracking parameters etc.
    For now, we just strip whitespace.
    """
    if not url:
        return ""
    return url.strip()
