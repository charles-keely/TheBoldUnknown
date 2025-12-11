import requests

class Validator:
    def check_url(self, url):
        """
        Validates that the image URL is accessible and is an image.
        Returns True if valid, False otherwise.
        """
        try:
            # Use a proper User-Agent to avoid being blocked by some servers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Try HEAD first
            try:
                response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '')
                    if content_type.startswith('image/'):
                        return True
            except:
                pass # Fallback to GET if HEAD fails (some servers block HEAD)

            # Fallback to GET with stream=True to download just headers/start
            response = requests.get(url, headers=headers, stream=True, timeout=5)
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if content_type.startswith('image/'):
                    return True
                    
            return False
            
        except Exception as e:
            print(f"Validation error for {url}: {e}")
            return False
