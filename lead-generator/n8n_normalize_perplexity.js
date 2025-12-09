// Normalize Perplexity Code Node
// Copy this into Node #12 (After the OpenAI Formatting Node)

// Robustly find the content, handling different n8n node versions
const json = items[0].json;
let content;

if (json.output && json.output[0] && json.output[0].content) {
   // Newer n8n AI node structure
   content = json.output[0].content[0].text;
} else if (json.choices && json.choices[0]) {
   // Standard OpenAI API structure
   content = json.choices[0].message.content;
} else {
   // Fallback
   content = json.content || "{}";
}

// Parse if it's a string, otherwise use directly
let parsed;
try {
    parsed = typeof content === 'string' ? JSON.parse(content) : content;
} catch (e) {
    parsed = { stories: [] };
}

const stories = parsed.stories || [];

// Safely get topic, fallback to "Unknown" if missing
// Note: Ensure the node name matches exactly what is in your workflow
let origin = "Unknown Topic";
try {
    const topicNode = $('Get Next Topic (Postgres)').first();
    if (topicNode) {
        origin = topicNode.json.topic;
    }
} catch (e) {
    // Ignore error if node not found
}

return stories.map(s => ({
  json: {
    title: s.title,
    url: s.url,
    summary: s.summary,
    source_origin: `Perplexity: ${origin}`,
    published_at: new Date().toISOString() // Perplexity doesn't always give dates, so we assume 'recent'
  }
}));

