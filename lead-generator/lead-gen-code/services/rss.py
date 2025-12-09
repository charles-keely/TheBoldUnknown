import feedparser
import concurrent.futures
from typing import List
from models import LeadCandidate
from utils.text import clean_html, truncate
from utils.logger import logger
import time

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
  "https://digest.bps.org.uk/feed",
  "https://www.psychologicalscience.org/feed",
  "https://www.psychologytoday.com/us/rss",
  "https://neurosciencenews.com/feed/",

  # Space / Earth / Natural Phenomena
  "http://www.nasa.gov/rss/dyn/image_of_the_day.rss",
  "https://earthsky.org/feed",
  "https://www.earthdata.nasa.gov/learn/rss-feeds/rss.xml",
  "https://phys.org/rss-feed/earth-news/",
  "https://phys.org/rss-feed/space-news/",
  "https://www.sciencedaily.com/rss/top/science.xml",

  # Tech / Complex Systems
  "https://www.wired.com/feed/category/science/latest/rss",
  "https://www.technologyreview.com/feed",
  "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml",
  "https://www.sciencedaily.com/rss/computers_math/computer_science.xml",

  # History / Culture / Documented Oddities
  "https://www.atlasobscura.com/feeds/latest",
  "https://www.smithsonianmag.com/rss/latest_articles/",
  "https://folklorethursday.com/feed/",

  # Fringe-Adjacent but Evidence-Usable
  "https://mysteriousuniverse.org/category/news/feed/",
  "https://mysteriousuniverse.org/category/science/feed/",
  "https://thedebrief.org/feed/",
  "https://anomalist.com/rss/portal.xml",
  "https://skepticalinquirer.org/feed/",

  # Reddit – Quiet WTF / High-Strangeness (Pruned for Brand Lens)
  "https://www.reddit.com/r/HighStrangeness/new/.rss",
  "https://www.reddit.com/r/UnresolvedMysteries/new/.rss",

  # Science & “this shouldn’t work but it does” stories
  "https://www.reddit.com/r/ThisDayInScience/new/.rss",
  "https://www.reddit.com/r/EverythingScience/new/.rss",
  "https://www.reddit.com/r/Futurology/new/.rss",
  "https://www.reddit.com/r/Space/new/.rss",

  # Anthro / history / human weirdness
  "https://www.reddit.com/r/Archaeology/new/.rss",
  "https://www.reddit.com/r/Anthropology/new/.rss",

  # Pattern / anomaly visual seeds
  "https://www.reddit.com/r/DataIsBeautiful/new/.rss",
  "https://www.reddit.com/r/MapPorn/new/.rss",
  
  # Optional
  "https://www.reddit.com/r/Glitch_in_the_Matrix/new/.rss"
]

def fetch_rss_feed(url: str, limit: int = 5) -> List[LeadCandidate]:
    """
    Fetch and parse a single RSS feed.
    """
    try:
        feed = feedparser.parse(url)
        candidates = []
        
        # Check for bozo bit (malformed feed) but often we can still parse items
        if feed.bozo:
             logger.debug(f"Feed {url} has bozo bit set: {feed.bozo_exception}")

        entries = feed.entries[:limit] if limit else feed.entries
        
        for entry in entries:
            # Extract summary: try description, then content, then summary
            summary = ""
            if 'description' in entry:
                summary = entry.description
            elif 'summary' in entry:
                summary = entry.summary
            elif 'content' in entry:
                summary = entry.content[0].value
            
            summary = clean_html(summary)
            summary = truncate(summary)
            
            title = entry.get('title', 'No Title')
            link = entry.get('link', '') or entry.get('guid', '')
            
            if not link:
                continue

            candidate = LeadCandidate(
                title=clean_html(title),
                url=link,
                summary=summary,
                source_origin=f"RSS: {url}"
            )
            candidates.append(candidate)
            
        return candidates
        
    except Exception as e:
        logger.error(f"Error fetching RSS feed {url}: {e}")
        return []

def fetch_all_rss(limit_per_feed: int = 3) -> List[LeadCandidate]:
    """
    Fetch all configured RSS feeds in parallel.
    """
    all_leads = []
    logger.info(f"Fetching {len(RSS_FEEDS)} RSS feeds...")
    
    # Use ThreadPoolExecutor for I/O bound tasks
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all tasks
        future_to_url = {
            executor.submit(fetch_rss_feed, url, limit_per_feed): url 
            for url in RSS_FEEDS
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                leads = future.result()
                all_leads.extend(leads)
            except Exception as e:
                logger.error(f"Error processing future for {url}: {e}")

    logger.info(f"Fetched {len(all_leads)} items from RSS.")
    return all_leads
