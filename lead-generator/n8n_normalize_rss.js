// Normalize RSS Code Node
// Copy this into Node #6

// --- CONFIGURATION ---
const ITEM_CAP = 2; // Set to 0 or null for NO LIMIT (Production). Set to 2-5 for Testing.
// ---------------------

// Safety check: If previous node failed or returned no items
if (!items || items.length === 0 || items[0].json.error) {
  return [];
}

const splitNode = $('Split in Batches');
const sourceUrl = splitNode ? splitNode.item.json.url : "Unknown URL";

// Apply Cap if set
const processedItems = (ITEM_CAP && ITEM_CAP > 0) ? items.slice(0, ITEM_CAP) : items;

return processedItems.map(item => {
  const i = item.json;
  
  // RSS feeds are messy. We try multiple fields to find the summary.
  const summary = i.description || i.contentSnippet || i['content:encoded'] || i.content || "";
  
  // Fallback if no link is provided
  const link = i.link || i.guid || i.origLink || "";
  
  // Parse Date if available, otherwise use now
  const pubDate = i.pubDate || i.isoDate || new Date().toISOString();

  return {
    json: {
      title: i.title || "No Title",
      url: link,
      summary: summary.substring(0, 1500), // Truncate to save tokens/db space
      source_origin: `RSS: ${sourceUrl}`,
      published_at: pubDate
    }
  };
});
