# n8n Subworkflow: Infinite Lead Generator V2 (The Vector Compass)

This document defines the technical implementation of the "Infinite Lead Generator V2" workflow in n8n. It details each node's logic, code configuration, and interaction with the database.

## Workflow Overview

This workflow is designed to autonomously discover, analyze, and store content leads for *TheBoldUnknown*. It uses a "Vector Compass" logic to switch between four distinct search strategies: **Lateral Leap**, **Wildcard**, **Gravity**, and **Deep Dive**.

**Flow Summary:**
1.  **Queue Check:** Analyzes the `search_queue` for available keywords by type.
2.  **The Compass Spin:** Randomly selects a search direction (30% Lateral, 30% Wildcard, 20% Gravity, 20% Deep).
3.  **Fetch Term (Cascade):** Retrieves a keyword based on the chosen direction, cascading to fallback types if the primary queue is empty.
4.  **Search:** Queries Perplexity API for distinct/obscure stories, filtering out recent duplicates.
5.  **Analysis (The Brain):** LLM evaluates stories using the "Harsh Editor" protocol and extracts diverse new keywords.
6.  **Deduplication:** Checks vector embeddings to avoid duplicates.
7.  **Storage:** Saves approved leads (with granular metadata) and populates the `search_queue`.

---

## Node Details

### 1. Check Queue Strength
**Type:** Postgres (Execute Query)
**Purpose:** Analyzes the current state of the `search_queue` to inform the decision logic. It counts available keywords for each type.

**SQL Code:**
```sql
SELECT 
  count(*) filter (where type = 'lateral') as lateral_count,
  count(*) filter (where type = 'wildcard') as wildcard_count,
  count(*) filter (where type = 'vertical') as vertical_count,
  count(*) as total_count
FROM search_queue
WHERE status = 'pending';
```

---

### 2. The Compass Spin
**Type:** Code (JavaScript)
**Purpose:** Determines the search strategy based on probability and queue availability. Implements the "Fallback Cascade" logic.

**Code:**
```javascript
const input = items[0].json;
const lateralCount = parseInt(input.lateral_count);
const wildcardCount = parseInt(input.wildcard_count);
const verticalCount = parseInt(input.vertical_count);
const totalCount = parseInt(input.total_count);

// 1. Spin the Compass (1-100)
const roll = Math.floor(Math.random() * 100) + 1;
let direction = '';

if (roll <= 30) direction = 'lateral';
else if (roll <= 60) direction = 'wildcard';
else if (roll <= 80) direction = 'gravity';
else direction = 'vertical'; // Deep Dive

// 2. Fallback Cascade Logic
// If the chosen direction is empty, switch to the next best option.

if (direction === 'lateral' && lateralCount === 0) {
    if (wildcardCount > 0) direction = 'wildcard';
    else direction = 'gravity';
}

if (direction === 'wildcard' && wildcardCount === 0) {
    direction = 'gravity';
}

if (direction === 'vertical' && verticalCount === 0) {
    if (lateralCount > 0) direction = 'lateral';
    else direction = 'gravity';
}

// Safety: If total queue is empty, force gravity
if (totalCount === 0) direction = 'gravity';

return [{
    json: {
        direction: direction,
        roll: roll,
        stats: input
    }
}];
```

---

### 3. Switch Direction
**Type:** Switch
**Purpose:** Routing node based on the `direction` field.
**Rules:**
-   Output 0: `direction` = 'gravity'
-   Output 1: `direction` = 'lateral'
-   Output 2: `direction` = 'wildcard'
-   Output 3: `direction` = 'vertical'

---

### 4. Fetch Keyword (Dynamic - 4 Nodes)
**Type:** Postgres (Execute Query) - **Use 4 separate nodes connected to the Switch outputs.**
**Purpose:** Fetches the appropriate keyword based on the active path.

**Path 0 (Gravity) SQL:**
```sql
SELECT name as keyword, 'gravity' as type, null as source_id 
FROM brand_pillars 
ORDER BY random() 
LIMIT 1;
```

**Path 1 (Lateral) SQL:**
```sql
SELECT keyword, type, id as source_id 
FROM search_queue 
WHERE status = 'pending' AND type = 'lateral'
ORDER BY priority_score DESC 
LIMIT 1;
```

**Path 2 (Wildcard) SQL:**
```sql
SELECT keyword, type, id as source_id 
FROM search_queue 
WHERE status = 'pending' AND type = 'wildcard'
ORDER BY priority_score DESC 
LIMIT 1;
```

**Path 3 (Vertical) SQL:**
```sql
SELECT keyword, type, id as source_id 
FROM search_queue 
WHERE status = 'pending' AND type = 'vertical'
ORDER BY priority_score DESC 
LIMIT 1;
```

---

### 5. Fetch Recent History
**Type:** Postgres (Execute Query)
**Purpose:** Gets the last 3 titles to prevent immediate duplicates in the search prompt. Connected to all 4 "Fetch Keyword" nodes.
**SQL Code:**
```sql
SELECT string_agg(title, ', ') as recent_titles 
FROM (
  SELECT title FROM leads ORDER BY created_at DESC LIMIT 3
) sub;
```

---

### 6. Perplexity Search
**Type:** HTTP Request / AI Agent
**Purpose:** Searches the web for distinct stories.

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
      "content": "Find 3 DISTINCT and obscure stories related to: {{ $('Fetch Keyword').item.json.keyword }}.\n\nConstraint: Do NOT return stories about these recent topics: {{ $('Fetch Recent History').item.json.recent_titles }}.\n\nFocus: Novelty and 'High Strangeness' over repetitive news.\nStrict Constraint: Include documented anomalies or credible reports (even if speculative), but strictly distinguish them from verified facts. Avoid debunked myths or pure fiction."
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
  const firstBracket = content.indexOf('[');
  const lastBracket = content.lastIndexOf(']');
  
  if (firstBracket !== -1 && lastBracket !== -1) {
    const jsonString = content.substring(firstBracket, lastBracket + 1);
    try {
       const stories = JSON.parse(jsonString);
       return stories.map(s => ({ json: s }));
    } catch (e2) {
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

### 8. The Brain (Analysis)
**Type:** OpenAI / LLM Chain
**Purpose:** Analyzes story and extracts diverse keywords.

**System Prompt:**
```text
You are the Editor-in-Chief of TheBoldUnknown. 

Brand Guidelines:
{{ $node["Read Brand File"].json.content }}

Your Task:
Analyze the user-provided story summary using the following protocols:

1.  **Strict Virality Scoring (The "Harsh Editor" Protocol):**
    -   **Novelty (0-25):** Is this new information or a tired trope?
    -   **"Wait, What?" Factor (0-25):** Does it sound impossible but is verified (or a credible multi-witness report)?
    -   **Visual Potential (0-25):** Can we create a cinematic image for it?
    -   **Social Spark (0-25):** Will people tag a friend?
    -   *Sum these 4 values for the total `virality_score`.*

2.  **Echo Check:** If the story feels like generic news or a repeat of common topics, reject it.

3.  **Data Extraction:**
    -   **Tags:** Extract 3-5 granular tags (e.g. "Greece", "Astronomy").
    -   **Score Breakdown:** Return the individual sub-scores.

4.  **Keyword Extraction (The Seed Mechanism):**
    -   You MUST extract exactly 3 new search keywords, one for each specific type:
        -   **Vertical:** A specific detail from this story to drill down into (e.g., "Thermoluminescence dating flaws").
        -   **Lateral:** A related but distinct field/topic (e.g., "Acoustic levitation in Tibet").
        -   **Wildcard:** A completely different, brand-aligned topic to ensure variety (e.g., "CIA Gateway Process").
```

**User Prompt:**
```text
Analyze this story:
Title: {{ $json.title }}
Summary: {{ $json.summary }}
URL: {{ $json.url }}
```

**JSON Output Schema (Structured Output):**
```json
{
  "type": "object",
  "properties": {
    "relevance_score": { "type": "integer", "description": "0-100 score of brand fit" },
    "virality_score": { "type": "integer", "description": "0-100 score (Sum of breakdown)" },
    "score_breakdown": {
      "type": "object",
      "properties": {
        "novelty": { "type": "integer" },
        "wait_what": { "type": "integer" },
        "visual": { "type": "integer" },
        "social": { "type": "integer" }
      },
      "required": ["novelty", "wait_what", "visual", "social"],
      "additionalProperties": false
    },
    "status": { "type": "string", "enum": ["approved", "rejected"] },
    "pillar": { "type": "string" },
    "tags": { 
      "type": "array", 
      "items": { "type": "string" }
    },
    "extracted_keywords": { 
      "type": "array", 
      "items": {
        "type": "object",
        "properties": {
          "keyword": { "type": "string" },
          "type": { "type": "string", "enum": ["vertical", "lateral", "wildcard"] }
        },
        "required": ["keyword", "type"],
        "additionalProperties": false
      },
      "minItems": 3,
      "maxItems": 3
    }
  },
  "required": ["relevance_score", "virality_score", "score_breakdown", "status", "pillar", "tags", "extracted_keywords"],
  "additionalProperties": false
}
```

---

### 9. Merge 1 (Consolidate Data)
**Type:** Merge
**Mode:** Merge by Position
**Purpose:** Combines the original story data (from "Parse Perplexity") with the analysis data (from "The Brain").

---

### 10. Generate Embeddings
**Type:** OpenAI Embeddings
**Purpose:** Creates vector embeddings for semantic deduplication.
**Input:** Uses data from "Merge 1" (Title + Summary).
**JSON Body:**
```json
{
  "input": "{{ $json.title }} - {{ $json.summary }}",
  "model": "text-embedding-3-small"
}
```

---

### 11. Attach Vector & Metadata
**Type:** Code (JavaScript)
**Purpose:** Consolidates all data including new schema fields.

**Code:**
```javascript
// 1. Get all the data sources
const cleanStories = $('Merge 1').all(); // Contains Title, URL, Summary
const brainAnalysis = $('The Brain').all(); // Contains Structured JSON Analysis
const vectors = items; // The input to this node (from Generate Embeddings)

const results = [];

for (let i = 0; i < vectors.length; i++) {
    // A. Get the Vector
    const vectorData = vectors[i].json;
    // Handle different embedding response formats
    const vector = vectorData.data ? vectorData.data[0].embedding : vectorData.embedding;

    // B. Get the Clean Story Info (Title, URL)
    const story = cleanStories[i] ? cleanStories[i].json : {};

    // C. Get the Brain Analysis (Structured JSON)
    const brainItem = brainAnalysis[i] ? brainAnalysis[i].json : {};
    let analysis = brainItem;
    
    // Fallback: If wrapped in message.content (depending on node version)
    if (brainItem.message && brainItem.message.content) {
         try {
             analysis = JSON.parse(brainItem.message.content);
         } catch(e) { analysis = {}; }
    }

    // D. Merge It All
    results.push({
        json: {
            // 1. Base Story Data
            title: story.title || "No Title",
            summary: story.summary || "No Summary",
            url: story.url || "No URL",
            
            // 2. AI Analysis
            relevance_score: analysis.relevance_score || 0,
            virality_score: analysis.virality_score || 0,
            score_breakdown: analysis.score_breakdown || {},
            tags: analysis.tags || [],
            extracted_keywords: analysis.extracted_keywords || [],
            pillar: analysis.pillar || "Uncategorized",
            status: analysis.status || "new",

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
**Purpose:** Checks if the story already exists. **Crucial:** Returns the `url` as a key for merging back later.

**SQL Code:**
```sql
SELECT 
  count(*) as match_count,
  '{{ $json.url }}' as url_key
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

### 14. Merge 2 (Re-attach Data)
**Type:** Merge
**Mode:** Merge By Key (Keep Key Matches)
**Purpose:** Re-combines the filtered "New" status with the original story data.
**Wiring:**
-   **Input 1:** Connect from "Is New?" (True Output).
-   **Input 2:** Connect from "Attach Vector & Metadata".
**Settings:**
-   **Property Input 1:** `url_key`
-   **Property Input 2:** `url`

---

### 15. Save Lead
**Type:** Postgres (Execute Query)
**Purpose:** Inserts the approved, non-duplicate story into the `leads` database.

**SQL Code:**
```sql
INSERT INTO leads (
  title, summary, url, relevance_score, virality_score, 
  score_breakdown, keywords, discovery_type, status, pillar_tag, embedding
) 
VALUES (
  '{{ $json.title.replace(/'/g, "''") }}',
  '{{ $json.summary.replace(/'/g, "''") }}',
  '{{ $json.url }}',
  {{ $json.relevance_score || 0 }},
  {{ $json.virality_score || 0 }},
  '{{ JSON.stringify($json.score_breakdown) }}'::jsonb,
  '{{ "{" + $json.tags.join(",") + "}" }}',
  '{{ $('The Compass Spin').item.json.direction }}',
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
**Purpose:** Formats the extracted keywords from "The Brain" into a structure ready for the `search_queue`.

**Code:**
```javascript
const savedLeads = items;
const sourceItems = $('Attach Vector & Metadata').all(); // Get original data
let allKeywordRows = [];

for (let i = 0; i < savedLeads.length; i++) {
    const leadId = savedLeads[i].json.id;
    // We need to match back to the correct source item. 
    // Assuming simple 1-to-1 processing order:
    const sourceData = sourceItems[i] ? sourceItems[i].json : {};
    const extracted = sourceData.extracted_keywords || [];
    
    // Priority Logic
    // Wildcard = 90, Lateral = 75, Vertical = 50
    
    for (const item of extracted) {
        let priority = 50;
        if (item.type === 'wildcard') priority = 90;
        if (item.type === 'lateral') priority = 75;
        
        allKeywordRows.push({
            json: {
                keyword: item.keyword,
                type: item.type,
                source_lead_id: leadId,
                priority_score: priority
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
INSERT INTO search_queue (keyword, type, source_lead_id, priority_score)
VALUES (
  '{{ $json.keyword.replace(/'/g, "''") }}',
  '{{ $json.type }}',
  '{{ $json.source_lead_id }}',
  {{ $json.priority_score }}
)
ON CONFLICT (keyword) DO NOTHING;
```
