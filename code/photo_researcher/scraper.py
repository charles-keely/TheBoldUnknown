import requests
from bs4 import BeautifulSoup
from .config import config

class PageScraper:
    def scrape_context(self, url):
        """
        Visits the webpage where the image was found to extract context.
        Returns a dictionary with title, description, and relevant text.
        """
        if not url:
            return {}
            
        print(f"Scraping context from: {url}...")
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"Failed to scrape {url}: Status {response.status_code}")
                return {}
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract basic metadata
            title = soup.title.string if soup.title else ""
            
            # Try to find description meta tag
            description = ""
            desc_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
            if desc_tag:
                description = desc_tag.get('content', '')

            # Extract image captions (heuristic: look for figcaption or text near images)
            captions = []
            for figcaption in soup.find_all('figcaption'):
                captions.append(figcaption.get_text().strip())
                
            # Extract main text (heuristic: paragraphs)
            paragraphs = [p.get_text().strip() for p in soup.find_all('p')]
            # Filter out short/empty paragraphs
            main_text = "\n".join([p for p in paragraphs if len(p) > 50])
            
            return {
                "page_title": title,
                "page_description": description,
                "captions": "\n".join(captions[:5]), # Limit to first 5 captions
                "page_text": main_text[:3000] # Limit context size
            }
            
        except Exception as e:
            print(f"Scraping failed for {url}: {e}")
            return {}
