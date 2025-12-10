import feedparser
import httpx
from typing import List, Dict, Any
from utils.logger import logger
from utils.text import clean_text, normalize_url
import datetime

# This list should ideally be in a config or database
RSS_FEEDS = [
    # Core Science
    "https://www.quantamagazine.org/feed",
    "https://aeon.co/feed.rss",
    "https://nautil.us/feed",
    "https://undark.org/feed",
    "https://daily.jstor.org/feed",
    "https://www.futurity.org/feed",
    "https://www.bbc.com/future/feed.rss",
    "https://phys.org/rss-feed/",
    
    # Mind & Cognition
    "https://mindhacks.com/feed",
    # "https://digest.bps.org.uk/feed",  # 404 Not Found
    "https://www.psychologicalscience.org/feed",
    # "https://www.psychologytoday.com/us/rss", # 404 Not Found
    # "https://neurosciencenews.com/feed/", # 403 Forbidden (Strict Blocking)
    
    # Space / Earth / Natural Phenomena
    "http://www.nasa.gov/rss/dyn/image_of_the_day.rss",
    "https://earthsky.org/feed",
    # "https://www.earthdata.nasa.gov/learn/rss-feeds/rss.xml", # 404 Not Found
    "https://phys.org/rss-feed/earth-news/",
    "https://phys.org/rss-feed/space-news/",
    "https://www.sciencedaily.com/rss/top/science.xml",
    
    # Tech & Complex Systems
    "https://www.wired.com/feed/category/science/latest/rss",
    "https://www.technologyreview.com/feed",
    "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml",
    "https://www.sciencedaily.com/rss/computers_math/computer_science.xml",
    
    # History / Culture / Documented Oddities
    "https://www.atlasobscura.com/feeds/latest",
    "https://www.smithsonianmag.com/rss/latest_articles/",
    "https://folklorethursday.com/feed/",
    
    # Fringe-Adjacent but Evidence-Usable
    # "https://mysteriousuniverse.org/category/news/feed/", # Syntax Error (Cloudflare blocked)
    # "https://mysteriousuniverse.org/category/science/feed/", # Syntax Error (Cloudflare blocked)
    "https://thedebrief.org/feed/",
    # "https://anomalist.com/rss/portal.xml", # 404 Not Found
    "https://skepticalinquirer.org/feed/",
    "https://www.openminds.tv/feed",

    # FOIA, Secrecy & Declassified Docs
    "https://www.muckrock.com/news/feeds/",                    # FOIA requests & document-driven stories
    "http://feeds.propublica.org/propublica/main",             # broad investigative reporting, often doc-based
    # "http://www.fas.org/sgp/news/secrecy/index.rss",           # 404 Not Found
    "https://unredacted.com/feed/",                            # National Security Archive’s blog: declassified docs, FOIA fights
    # "https://www.occrp.org/en/investigations?format=feed&type=rss", # Syntax Error

    # OSINT & Investigations
    "https://www.bellingcat.com/feed/",                        # Open-source investigations, often on covert ops & disinfo

    # Fringe-adjacent but doc-heavy
    "https://www.theblackvault.com/documentarchive/feed/", 
]

class RSSService:
    def __init__(self):
        self.feeds = RSS_FEEDS
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, application/atom+xml, text/xml, */*"
        }

    def fetch_all(self) -> List[Dict[str, Any]]:
        all_items = []
        for feed_url in self.feeds:
            try:
                # Use httpx to fetch the content first with proper headers
                # This avoids 403 Forbidden errors from strict sites
                response = httpx.get(feed_url, headers=self.headers, timeout=10.0, follow_redirects=True)
                response.raise_for_status()
                content = response.content

                # Parse the raw content
                feed = feedparser.parse(content)
                
                if feed.bozo:
                    # Log warning but still try to process what we got
                    logger.warning(f"Feed parsing warning {feed_url}: {feed.bozo_exception}")
                
                logger.info(f"Fetched {len(feed.entries)} items from {feed_url}")
                
                for entry in feed.entries:
                    item = self._normalize_entry(entry, feed_url)
                    if item:
                        all_items.append(item)
            except Exception as e:
                logger.error(f"Error fetching feed {feed_url}: {e}")
        
        return all_items

    def _normalize_entry(self, entry, source_url) -> Dict[str, Any]:
        try:
            title = clean_text(entry.get('title', ''))
            summary = clean_text(entry.get('summary', entry.get('description', '')))
            url = normalize_url(entry.get('link', ''))
            
            # Basic validation
            if not title or not url:
                return None

            return {
                "title": title,
                "url": url,
                "summary": summary,
                "source_origin": f"RSS: {source_url}",
                "published_at": entry.get('published_parsed')
            }
        except Exception as e:
            logger.error(f"Error normalizing RSS entry: {e}")
            return None

rss_service = RSSService()
