import requests
from .config import config

class ImageSearcher:
    def __init__(self):
        self.api_key = config.GOOGLE_CUSTOM_SEARCH_KEY
        self.cx = config.GOOGLE_SEARCH_ENGINE_ID
        self.base_url = "https://www.googleapis.com/customsearch/v1"

    def search(self, query, num_results=3):
        """
        Searches Google Images for the query.
        Returns a list of result objects (link, contextLink, title).
        """
        print(f"Searching for: '{query}'...")
        
        params = {
            'key': self.api_key,
            'cx': self.cx,
            'q': query,
            'searchType': 'image',
            'num': num_results,
            # 'imgSize': 'large', # Optional: restrict to large images
            # 'safe': 'active' # Optional
        }

        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            items = data.get('items', [])
            results = []
            
            for item in items:
                results.append({
                    'image_url': item.get('link'),
                    'source_page_url': item.get('image', {}).get('contextLink'),
                    'title': item.get('title'),
                    'mime': item.get('mime', '')
                })
                
            return results
            
        except Exception as e:
            print(f"Search failed for '{query}': {e}")
            return []
