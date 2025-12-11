import feedparser
import httpx
import re
from typing import List, Dict, Any
from utils.logger import logger
from utils.text import clean_text, normalize_url
import datetime

# This list should ideally be in a config or database
RSS_FEEDS_MAIN = [
    # Core Science & Quietly Strange — Optimized
    "https://www.quantamagazine.org/feed",
    "https://aeon.co/feed.rss",
    "https://nautil.us/feed",
    "https://www.bbc.com/future/feed.rss",
    "https://www.newscientist.com/subject/space/feed/",
    "https://www.newscientist.com/subject/technology/feed/",
    "https://phys.org/rss-feed/",

    # Mind & Cognition (Narrative-Driven)
    "https://mindhacks.com/feed",
    "https://psyche.co/feed",

    # Consciousness / Reality Edge
    "https://nautil.us/tag/consciousness/feed",
    "https://www.scientificamerican.com/rss/topic/mind-and-brain/",
    "https://www.edge.org/rss.xml",

    # Behavioral / Social Psychology (Grounded)
    "https://behavioralscientist.org/feed/",
    "https://greatergood.berkeley.edu/rss",

    # Space / Earth / Natural Phenomena (Visual + Awe)
    "http://www.nasa.gov/rss/dyn/image_of_the_day.rss",
    "https://earthsky.org/feed",
    "https://phys.org/rss-feed/space-news/",

    # Tech, Complex Systems, Emergent Weirdness
    "https://www.wired.com/feed/category/science/latest/rss",
    "https://noemamag.com/feed/",
    "https://longreads.com/feed/",

    # History / Culture / Documented Oddities
    "https://www.atlasobscura.com/feeds/latest",
    "https://www.smithsonianmag.com/rss/latest_articles/",
    "https://www.archaeology.org/feed/",
    "https://www.ancient-origins.net/rss.xml",  # usable; brand filter stays strict

    # Fringe-Adjacent but Evidence-Usable
    "https://thedebrief.org/feed/",
    "https://skepticalinquirer.org/feed/",
    "https://www.openminds.tv/feed",

    # FOIA, Secrecy & Investigative Reporting
    "https://www.muckrock.com/news/feeds/",
    "http://feeds.propublica.org/propublica/main",
    "https://unredacted.com/feed/",
    "https://www.bellingcat.com/feed/",
    "https://theintercept.com/feed/?lang=en",

    # Intelligence / Defense / Classified-adjacent (Verified Working)
    "https://nsarchive.gwu.edu/news/rss.xml",
    "https://www.courtlistener.com/atom/",
    "https://www.twz.com/feed/",

    # Forteana / Anomaly Archives (Controlled)
    "https://www.forteantimes.com/feed/",
]


# Reddit feeds - top posts from the past week
RSS_FEEDS_REDDIT = [
    # Anomalies & High Strangeness (documented, investigative-leaning)
    "https://www.reddit.com/r/HighStrangeness/top/.rss?t=week",
    "https://www.reddit.com/r/Anomalies/top/.rss?t=week",
    "https://www.reddit.com/r/UnresolvedMysteries/top/.rss?t=week",

    # OSINT, Intelligence, and real-world operations
    "https://www.reddit.com/r/OSINT/top/.rss?t=week",
    "https://www.reddit.com/r/Intelligence/top/.rss?t=week",

    # Media, history, and digital oddities
    "https://www.reddit.com/r/ObscureMedia/top/.rss?t=week",
    "https://www.reddit.com/r/LostMedia/top/.rss?t=week",
    "https://www.reddit.com/r/InternetMysteries/top/.rss?t=week",

    # UAP / UFO (lead discovery only, not assumed factual)
    "https://www.reddit.com/r/UFOs/top/.rss?t=week",
    "https://www.reddit.com/r/UAP/top/.rss?t=week",

    # Systems, records, and unexplained-but-grounded mysteries
    "https://www.reddit.com/r/NonMurderMysteries/top/.rss?t=week",
    "https://www.reddit.com/r/GlitchInTheMatrix/top/.rss?t=week",
    "https://www.reddit.com/r/WeirdHistory/top/.rss?t=week",

    # Deep fringe & speculative science (strict filtering applied downstream)
    "https://www.reddit.com/r/ForteanResearch/top/.rss?t=week",
    "https://www.reddit.com/r/ParanormalScience/top/.rss?t=week",
    "https://www.reddit.com/r/ConspiracyNOPOL/top/.rss?t=week",
    "https://www.reddit.com/r/FringeScience/top/.rss?t=week",
]





# Combined feeds
RSS_FEEDS = RSS_FEEDS_MAIN + RSS_FEEDS_REDDIT


class RSSService:
    def __init__(self):
        self.feeds = RSS_FEEDS
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, application/atom+xml, text/xml, */*"
        }
        # Reddit requires a more specific user agent
        self.reddit_headers = {
            "User-Agent": "TheBoldUnknown:LeadGenerator:v1.0 (by /u/TheBoldUnknown)",
            "Accept": "application/rss+xml, application/xml, */*"
        }

    def fetch_all(self) -> List[Dict[str, Any]]:
        all_items = []
        for feed_url in self.feeds:
            try:
                # Use Reddit-specific headers for Reddit feeds
                is_reddit = "reddit.com" in feed_url
                headers = self.reddit_headers if is_reddit else self.headers
                
                # Use httpx to fetch the content first with proper headers
                # This avoids 403 Forbidden errors from strict sites
                response = httpx.get(feed_url, headers=headers, timeout=15.0, follow_redirects=True)
                response.raise_for_status()
                content = response.content

                # Parse the raw content
                feed = feedparser.parse(content)
                
                if feed.bozo:
                    # Log warning but still try to process what we got
                    logger.warning(f"Feed parsing warning {feed_url}: {feed.bozo_exception}")
                
                logger.info(f"Fetched {len(feed.entries)} items from {feed_url}")
                
                for entry in feed.entries:
                    item = self._normalize_entry(entry, feed_url, is_reddit=is_reddit)
                    if item:
                        all_items.append(item)
            except Exception as e:
                logger.error(f"Error fetching feed {feed_url}: {e}")
        
        return all_items

    def _normalize_entry(self, entry, source_url, is_reddit: bool = False) -> Dict[str, Any]:
        try:
            title = clean_text(entry.get('title', ''))
            summary = clean_text(entry.get('summary', entry.get('description', '')))
            url = normalize_url(entry.get('link', ''))
            
            # For Reddit posts, extract the subreddit name for cleaner source tracking
            if is_reddit:
                # Extract subreddit from URL for source_origin
                subreddit_match = re.search(r'/r/([^/]+)/', source_url)
                subreddit = subreddit_match.group(1) if subreddit_match else "Reddit"
                source_origin = f"Reddit: r/{subreddit}"
                
                # Reddit summaries often contain HTML, try to extract cleaner text
                # The summary might contain the actual post content or just be empty
                if not summary or len(summary) < 20:
                    summary = f"Top post from r/{subreddit}"
            else:
                source_origin = f"RSS: {source_url}"
            
            # Basic validation
            if not title or not url:
                return None

            published_parsed = entry.get('published_parsed')
            published_at = None
            if published_parsed:
                try:
                    # Convert struct_time to datetime
                    published_at = datetime.datetime(*published_parsed[:6])
                except Exception:
                    pass

            return {
                "title": title,
                "url": url,
                "summary": summary,
                "source_origin": source_origin,
                "published_at": published_at
            }
        except Exception as e:
            logger.error(f"Error normalizing RSS entry: {e}")
            return None

rss_service = RSSService()
