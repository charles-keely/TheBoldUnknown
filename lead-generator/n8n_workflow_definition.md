# n8n Subworkflow: Infinite Lead Generator

This document defines the technical implementation of the "Infinite Lead Generator" workflow in n8n. It details each node's logic, code configuration, and interaction with the database.

## Workflow Overview

This workflow is designed to autonomously discover, analyze, and store content leads for *TheBoldUnknown*. It uses a "Compass" logic to switch between exploring core brand pillars ("Gravity") and following interesting rabbit holes ("Rabbit Hole").

**Flow Summary:**
1.  **Queue Check:** Determines if the search queue has high-quality pending items.
2.  **The Compass:** Decides the search strategy (Gravity vs. Rabbit Hole).
3.  **Fetch Term:** Retrieves a keyword either from `brand_pillars` or `search_queue`.
4.  **Search:** Queries Perplexity API for recent/obscure stories.
5.  **Analysis:** LLM ("The Brain") evaluates stories against brand guidelines.
6.  **Deduplication:** Checks vector embeddings to avoid duplicates.
7.  **Storage:** Saves approved leads and extracts new keywords for the queue.

---

## Node Details

### 1. Check Queue Strength
**Type:** Postgres (Execute Query)
**Purpose:** Analyzes the current state of the `search_queue` to inform the decision logic.

**SQL Code:**
```sql
SELECT 
  max(priority_score) AS top_score,
  count(*) AS queue_size
FROM search_queue
WHERE status = 'pending';
```

---

### 2. The Compass
**Type:** Code (JavaScript)
**Purpose:** Determines the search strategy based on queue health. If the queue is empty or low quality, it defaults to "Gravity" (Core Pillars). Otherwise, it follows "Rabbit Holes".

**Code:**
```javascript
const input = items[0].json;
const topScore = input.top_score || 0;
const queueSize = input.queue_size || 0;

// Check for consecutive failures passed from previous runs (simulated for now)
const failures = 0; 

// The Smart Threshold Logic
let searchType = 'rabbit_hole';

if (topScore <= 70 || queueSize === 0 || failures >= 3) {
    searchType = 'gravity';
}

return [{
    json: {
        search_type: searchType,
        top_score: topScore,
        reason: topScore <= 70 ? 'Score too low' : 'Trail is hot'
    }
}];
```

---

### 3. Is Gravity?
**Type:** If
**Purpose:** Routing node based on the decision from "The Compass".
**Condition:** Checks if `{{ $json.search_type }}` is equal to `gravity`.
**Implementation:** If node that takes `{{ $json.search_type }}` and returns true if it is equal to gravity.

---

### 4. Fetch Core Pillar (Gravity Branch)
**Type:** Postgres (Execute Query)
**Purpose:** Fetches a random core pillar to restart exploration. Runs if "Is Gravity?" is **True**.

**SQL Code:**
```sql
SELECT name as keyword, 0 as depth, null as id 
FROM brand_pillars 
ORDER BY random() 
LIMIT 1;
```

---

### 5. Fetch Best Lead (Rabbit Hole Branch)
**Type:** Postgres (Execute Query)
**Purpose:** Fetches the highest-priority pending keyword from the queue. Runs if "Is Gravity?" is **False**.

**SQL Code:**
```sql
SELECT keyword, generation_depth as depth, id 
FROM search_queue 
WHERE status = 'pending' 
ORDER BY priority_score DESC 
LIMIT 1;
```

---

### 6. Perplexity
**Type:** HTTP Request / AI Agent
**Purpose:** Searches the web for stories related to the selected keyword.

**JSON Body:**
```json
{
  "model": "sonar-pro",
  "messages": [
    {
      "role": "system",
      "content": "You are a research assistant. Return ONLY a valid JSON array of objects. Format: [{\"title\": \"...\", \"url\": \"...\", \"summary\": \"...\"}]. No markdown formatting."
    },
    {
      "role": "user",
      "content": "Find 5 recent or interesting obscure stories related to: {{ $json.keyword }}. \n\nFocus on verified anomalies, scientific mysteries, or historical oddities."
    }
  ]
}
```

---

### 7. Parse Perplexity
**Type:** Code (JavaScript)
**Purpose:** Robustly parses the JSON response from Perplexity, handling potential formatting errors.

**Code:**
```javascript
// Get the raw content string
const content = $input.first().json.choices[0].message.content;

// 1. Try to parse directly first (Happy Path)
try {
  const stories = JSON.parse(content);
  return stories.map(s => ({ json: s }));
} catch (e) {
  // 2. Robust Extraction: Find the first '[' and the last ']'
  // This ignores "" or any other wrapper text
  const firstBracket = content.indexOf('[');
  const lastBracket = content.lastIndexOf(']');
  
  if (firstBracket !== -1 && lastBracket !== -1) {
    const jsonString = content.substring(firstBracket, lastBracket + 1);
    try {
       const stories = JSON.parse(jsonString);
       return stories.map(s => ({ json: s }));
    } catch (e2) {
       // Parsing failed even after extraction
       return [{
         json: {
           error: "Failed to parse extracted JSON",
           extracted_attempt: jsonString,
           original_error: e2.message
         }
       }];
    }
  }
  
  // 3. Fallback: Return error with debug info
  return [{
    json: {
      error: "No JSON array brackets found",
      raw_content: content
    }
  }];
}
```

---

### 8. The Brain
**Type:** OpenAI / LLM Chain
**Purpose:** Analyzes the story for brand fit ("TheBoldUnknown"), virality, and extracts new keywords.

**System Prompt:**
```text
        You are the Editor-in-Chief of TheBoldUnknown. 

        Brand:
        {{ $node["Read Brand File"].json.content }}
        (Note: In actual implementation, paste the contents of brand.txt here or read it from a file/variable)

        Your task: Analyze the provided story summary.
        1. Relevance Score (0-100): How well does it fit the brand? (Must be grounded, mysterious, scientific).
        2. Virality Score (0-100): How likely is it to hook people?
        3. Echo Chamber Check: Is this just generic news? (Pass/Fail)
        4. Category: Assign a core pillar.
        5. New Keywords: Extract 3 specific search terms for future rabbit holes.
        
        Output valid JSON only:
        {
          "relevance_score": 85,
          "virality_score": 75,
          "status": "approved", // or "rejected" if score < 70
          "pillar": "Anomalies",
          "reason": "Fits the tone perfectly...",
          "new_keywords": ["Keyword 1", "Keyword 2", "Keyword 3"]
        }
```

**User Prompt:**
```text
Analyze this story:
Title: {{ $json.title }}
Summary: {{ $json.summary }}
URL: {{ $json.url }}
```

**JSON Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "relevance_score": { "type": "integer", "description": "0-100 score of fit" },
    "virality_score": { "type": "integer", "description": "0-100 score of potential" },
    "status": { "type": "string", "enum": ["approved", "rejected"] },
    "pillar": { "type": "string" },
    "reason": { "type": "string" },
    "new_keywords": { 
      "type": "array", 
      "items": { "type": "string" },
      "description": "3 extracted search terms"
    }
  },
  "required": ["relevance_score", "virality_score", "status", "pillar", "reason", "new_keywords"],
  "additionalProperties": false
}
```

---

### 9. Merge 1
**Type:** Merge
**Mode:** Merge by Position
**Purpose:** Combines the original story data (from "Parse Perplexity") with the analysis data (from "The Brain").

---

### 10. Generate Embeddings
**Type:** OpenAI Embeddings
**Purpose:** Creates vector embeddings for semantic deduplication.

**JSON Body:**
```json
{
  "input": "{{ $json.title }} - {{ $json.summary }}",
  "model": "text-embedding-3-small"
}
```

---

### 11. Attach Vector
**Type:** Code (JavaScript)
**Purpose:** Consolidates Story Data, Brain Analysis, and Vector Embeddings into a single object for processing.

**Code:**
```javascript
// 1. Get all the data sources
const cleanStories = $('Merge 1').all(); // Contains Title, URL, Summary
const brainAnalysis = $('The Brain').all(); // Contains Pillar, Score, Keywords
const vectors = items; // The input to this node (from Generate Embeddings)

const results = [];

for (let i = 0; i < vectors.length; i++) {
    // A. Get the Vector
    const vectorData = vectors[i].json;
    const vector = vectorData.data ? vectorData.data[0].embedding : vectorData.embedding;

    // B. Get the Clean Story Info (Title, URL)
    const story = cleanStories[i] ? cleanStories[i].json : {};

    // C. Get the Brain Analysis (Pillar, Score)
    const brainItem = brainAnalysis[i] ? brainAnalysis[i].json : {};
    let analysis = {};
    
    // Robustly find the analysis object (handling nesting)
    try {
        if (brainItem.output && brainItem.output[0] && 
            brainItem.output[0].content && brainItem.output[0].content[0] &&
            brainItem.output[0].content[0].text) {
            analysis = brainItem.output[0].content[0].text;
        } else if (brainItem.content && brainItem.content[0] && brainItem.content[0].text) {
             analysis = brainItem.content[0].text;
        }
    } catch (e) { analysis = {}; }

    // D. Merge It All
    results.push({
        json: {
            // 1. Base Story Data
            title: story.title || "No Title",
            summary: story.summary || "No Summary",
            url: story.url || "No URL",
            
            // 2. AI Analysis (Pillar, etc.)
            ...analysis,
            
            // 3. Vector
            embedding_vector: vector,
            embedding_string: "[" + vector.join(",") + "]"
        }
    });
}

return results;
```

---

### 12. Check Duplicates
**Type:** Postgres (Execute Query)
**Purpose:** Checks if the story already exists in the `leads` table using vector similarity (> 0.85) or exact URL match.

**SQL Code:**
```sql
SELECT count(*) as match_count
FROM leads 
WHERE 1 - (embedding <=> '{{ "[" + $json.embedding_vector.join(",") + "]" }}') > 0.85
OR url = '{{ $json.url }}';
```

---

### 13. Is New?
**Type:** If
**Purpose:** Filtering node.
**Condition:** Checks if `{{ $json.match_count }}` is equal to `0`.

---

### 14. Merge 2
**Type:** Merge
**Purpose:** Merges the inputs of Attach Vector and Is New?
**Functionality:** Re-merges the valid items passing through "Is New?" with their data from "Attach Vector".

---

### 15. Save Lead
**Type:** Postgres (Execute Query)
**Purpose:** Inserts the approved, non-duplicate story into the `leads` database.

**SQL Code:**
```sql
INSERT INTO leads (
  title, summary, url, relevance_score, virality_score, status, pillar_tag, embedding
) 
VALUES (
  '{{ $json.title.replace(/'/g, "''") }}',
  '{{ $json.summary.replace(/'/g, "''") }}',
  '{{ $json.url }}',
  {{ $json.relevance_score || 0 }},
  {{ $json.virality_score || 0 }},
  'approved',
  '{{ $json.pillar }}',
  '[{{ $json.embedding_vector.join(",") }}]'::vector
)
ON CONFLICT (url) DO NOTHING
RETURNING id;
```

---

### 16. Prepare Keywords
**Type:** Code (JavaScript)
**Purpose:** Formats the extracted keywords from "The Brain" into a structure ready for the `search_queue`, inheriting priority from the parent story's virality.

**Code:**
```javascript
// 1. Get all saved leads (IDs)
const savedLeads = items;

// 2. Get all original data (Keywords) from Attach Vector
const sourceItems = $('Attach Vector').all();

let allKeywordRows = [];

// 3. Loop through each saved lead
for (let i = 0; i < savedLeads.length; i++) {
    const leadId = savedLeads[i].json.id;
    
    // Match with source item by index
    const sourceData = sourceItems[i] ? sourceItems[i].json : {};
    const keywords = sourceData.new_keywords || [];
    
    // Calculate Priority Score (Bonus: Use Virality Score from source!)
    const virality = sourceData.virality_score || 50;
    
    // Create a row for each keyword
    for (const kw of keywords) {
        allKeywordRows.push({
            json: {
                keyword: kw,
                source_lead_id: leadId,
                generation_depth: 1, // Hardcoded 1 for now, or fetch dynamically
                priority_score: virality // Use the story's virality as the keyword's starting score
            }
        });
    }
}

return allKeywordRows;
```

---

### 17. Save Keywords
**Type:** Postgres (Execute Query)
**Purpose:** Inserts the new keywords into the `search_queue`.

**SQL Code:**
```sql
INSERT INTO search_queue (keyword, source_lead_id, generation_depth, priority_score)
VALUES (
  '{{ $json.keyword.replace(/'/g, "''") }}',
  '{{ $json.source_lead_id }}',
  {{ $json.generation_depth }},
  {{ $json.priority_score }}
)
ON CONFLICT (keyword) DO NOTHING;
```

