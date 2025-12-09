const feeds = [
  // Core Science
  "https://www.quantamagazine.org/feed",
  "https://aeon.co/feed.rss",
  "https://nautil.us/feed",
  "https://undark.org/feed",
  "https://daily.jstor.org/feed",
  "https://www.futurity.org/feed",
  "https://www.bbc.com/future/feed.rss",
  "https://phys.org/rss-feed/",
  // Mind & Cognition
  "https://mindhacks.com/feed",
  "https://digest.bps.org.uk/feed",
  "https://www.psychologicalscience.org/feed",
  "https://www.psychologytoday.com/us/rss",
  "https://neurosciencenews.com/feed/",
  // Space / Earth / Natural Phenomena
  "http://www.nasa.gov/rss/dyn/image_of_the_day.rss",
  "https://earthsky.org/feed",
  "https://www.earthdata.nasa.gov/learn/rss-feeds/rss.xml",
  "https://phys.org/rss-feed/earth-news/",
  "https://phys.org/rss-feed/space-news/",
  "https://www.sciencedaily.com/rss/top/science.xml",
  // Tech & Complex Systems
  "https://www.wired.com/feed/category/science/latest/rss",
  "https://www.technologyreview.com/feed",
  "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml",
  "https://www.sciencedaily.com/rss/computers_math/computer_science.xml",
  // History / Culture / Documented Oddities
  "https://www.atlasobscura.com/feeds/latest",
  "https://www.smithsonianmag.com/rss/latest_articles/",
  "https://folklorethursday.com/feed/",
  // Fringe-Adjacent but Evidence-Usable
  "https://mysteriousuniverse.org/category/news/feed/",
  "https://mysteriousuniverse.org/category/science/feed/",
  "https://thedebrief.org/feed/",
  "https://anomalist.com/rss/portal.xml",
  "https://skepticalinquirer.org/feed/"
];

// Return data in the format n8n expects: an array of objects wrapped in "json"
return feeds.map(url => ({ json: { url } }));

