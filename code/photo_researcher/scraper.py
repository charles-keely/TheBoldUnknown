import requests
from bs4 import BeautifulSoup

class PageScraper:
    def scrape(self, url):
        """
        Scrapes the source page for context about the image.
        Returns a dictionary with title, description, and page text snippet.
        """
        if not url:
            return {}

        print(f"Scraping source page: {url}...")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract meta tags
            title = soup.title.string if soup.title else ""
            
            og_title = soup.find("meta", property="og:title")
            if og_title:
                title = og_title["content"]
                
            og_desc = soup.find("meta", property="og:description")
            description = og_desc["content"] if og_desc else ""
            
            # Extract main text (simple approximation)
            # Find paragraphs
            paragraphs = soup.find_all('p')
            text_snippet = "\n".join([p.get_text()[:200] for p in paragraphs[:5]]) # First 5 paragraphs
            
            # Find potential image captions (figcaption, or text near img tags - hard to map specific img, but page context helps)
            captions = [c.get_text() for c in soup.find_all('figcaption')]
            caption_text = "\n".join(captions[:3])
            
            return {
                "page_title": title.strip(),
                "page_description": description.strip(),
                "page_text": text_snippet,
                "captions": caption_text
            }
            
        except Exception as e:
            print(f"Scraping failed for {url}: {e}")
            return {}
