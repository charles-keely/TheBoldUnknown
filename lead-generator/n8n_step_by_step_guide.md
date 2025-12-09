# Master n8n Build Guide: The "Infinite" Lead Generator

This guide details exactly how to build the workflow in n8n, node by node, in order. 

**Strategy:** We will build this as **one single workflow** for simplicity, with two parallel "Input" branches (RSS and Perplexity) that merge into a single "Processor" chain.

---

## Part 1: The Triggers & Inputs

### 1. Trigger Node
*   **Type:** `Schedule Trigger`
*   **Settings:** 
    *   **Interval:** Every 6 Hours (or as preferred).

### 2. Node: Edit Fields (Set Run Variables)
*   **Type:** `Edit Fields` (Set)
*   **Purpose:** Define global settings or constants if needed.
*   **Settings:** Keep empty for now, or set a `batch_size` for testing.

---

### Branch A: The RSS Engine
*(Connects from Trigger)*

### 3. Node: RSS Sources (Code)
*   **Type:** `Code`
*   **Language:** JavaScript
*   **Code:** (Copy contents of `n8n_rss_code.js` here)
*   **Connection:** Connect output to "Split in Batches" input.

### 4. Node: Split in Batches
*   **Type:** `Split In Batches`
*   **Settings:** `Batch Size: 1`
*   **Purpose:** Loop through the 30+ RSS feeds one by one.
*   **Inputs:** Receives list from "RSS Sources".

### 5. Node: RSS Read
*   **Type:** `RSS Feed Read`
*   **Settings:**
    *   **URL:** Expression: `{{ $('Split in Batches').item.json.url }}`
    *   **Return Value:** `All Items`
*   **Inputs:** Connect "Loop" output of "Split in Batches" to this node.

### 6. Node: Normalize RSS (Code)
*   **Type:** `Code`
*   **Purpose:** Standardize RSS data.
*   **Code:** (Copy contents of `n8n_normalize_rss.js`)
    *   *Note: Ensure the first line of code matches the name of your Split Batch node.*
*   **Inputs:** Connect output of "RSS Read" to this node.

### 7. Node: Connect to Merge (End of RSS Branch)
*   **Action:** Connect the output of "Normalize RSS" to the **Merge** node (Step 13).
*   **Crucial:** Do NOT connect this back to "Split in Batches". The `Split in Batches` node will hold the queue and release the next item automatically when the workflow continues, but since we are merging everything first, we just want to dump the results of this branch into the Merge node.
*   *Alternative (Strict Loop):* If you want to force it to finish all 30 feeds before moving on, connect "Normalize RSS" back to the **Input** of "Split in Batches". Then connect the "Done" output of "Split in Batches" to the Merge node.
*   **Recommended for Simplicity:** Connect "Normalize RSS" -> "Split in Batches" (Input). Then Connect "Split in Batches" (Done) -> "Merge". This ensures all feeds are read before processing starts.

---

### Branch B: The Perplexity Hunter
*(Connects from Trigger)*

### 8. Node: Get Next Topic (Postgres)
*   **Type:** `Postgres`
*   **Operation:** `Execute Query`
*   **Query:**
    ```sql
    SELECT * FROM discovery_topics 
    WHERE status = 'active' 
    ORDER BY last_searched_at ASC NULLS FIRST 
    LIMIT 1;
    ```
*   **Inputs:** Connects from Trigger (or Edit Fields).

### 9. Node: Generate Search Query (OpenAI)
*   **Type:** `OpenAI`
*   **Model:** `gpt-5-mini` (or latest available Mini model)
*   **System Message:** "You are an expert researcher. Convert the user's topic into a single, specific, scientific search query for finding recent anomalies or studies. Output ONLY the query."
*   **User Message:** `Topic: {{ $json.topic }}`

### 10. Node: Run Search (HTTP Request)
*   **Type:** `HTTP Request`
*   **Method:** `POST`
*   **URL:** `https://api.perplexity.ai/chat/completions`
*   **Authentication:** `Header Auth` -> `Authorization: Bearer YOUR_PERPLEXITY_KEY`
*   **Body Content:** `JSON`
*   **JSON Code:**
    ```json
    {{
      {
        "model": "sonar-pro",
        "messages": [
          {
            "role": "system",
            "content": "Find 5 specific, documented stories or research papers related to the query. Return them as a JSON list with keys: 'title', 'url', 'summary'."
          },
          {
            "role": "user",
            "content": $json.output[0].content[0].text
          }
        ]
      }
    }}
    ```
    *(Note: This expression uses the direct JavaScript object format to ensure proper JSON escaping of the search query.)*

### 11. Node: Update Topic (Postgres)
*   **Type:** `Postgres`
*   **Operation:** `Execute Query`
*   **Query:**
    ```sql
    UPDATE discovery_topics 
    SET last_searched_at = NOW() 
    WHERE id = $1;
    ```
*   **Query Parameters:** `{{ $('Get Next Topic (Postgres)').item.json.id }}`
    *(Ensure you use the exact node name if you renamed it.)*

### 12. Node: Normalize Perplexity (Code/AI)
*   **Type:** `OpenAI` (Reliable parsing)
*   **Purpose:** Perplexity output is often text/markdown. We force it into our standard JSON structure.
*   **Model:** `gpt-5-mini`
*   **Response Format:** `JSON Object`
*   **System Message:** "Extract the stories from the text into a JSON object with a key 'stories' containing an array of objects: {title, url, summary}."
*   **User Message:** `{{ $('Run Search').item.json.choices[0].message.content }}`
    *(Note: If using HTTP Request node for search, use `{{ $json.choices[0].message.content }}`)*
*   **Followed by a Code Node to flatten:**
    ```javascript
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
    const topicNode = $('Get Next Topic (Postgres)').first();
    const origin = topicNode ? topicNode.json.topic : "Unknown Topic";
    
    return stories.map(s => ({
      json: {
        title: s.title,
        url: s.url,
        summary: s.summary,
        source_origin: `Perplexity: ${origin}`
      }
    }));
    ```

---

## Part 2: The Processor (Batch Optimized)

### 13. Node: Merge (Inputs)
*   **Type:** `Merge`
*   **Mode:** `Append`
*   **Inputs:** 
    1. Connect "Split in Batches" (Done output) from the RSS branch.
    2. Connect "Normalize Perplexity" from the Perplexity branch.
*   **Purpose:** Combine all potential leads into one single list.

### 14. Node: Batch for Filtering
*   **Type:** `Split In Batches`
*   **Batch Size:** `20` (Process 20 titles at a time to save API calls)
*   **Purpose:** Send groups of titles to the AI Gatekeeper.
*   **Inputs:** Connect output of "Merge".

### 14b. Node: Prepare Prompt (Code)
*   **Type:** `Code`
*   **Purpose:** Aggregate the batch of 20 items into a single string for the AI, while preserving the original items.
*   **Code:**
    ```javascript
    // Squash all items in the batch into one string
    const titles = items.map((item, index) => `${index}: ${item.json.title}`).join('\n');
    
    // Pass prompt AND the original items forward (Pass-Through pattern)
    return { 
        json: { 
            prompt: titles,
            _original_batch: items.map(i => i.json) 
        } 
    };
    ```
*   **Inputs:** Connect output of "Batch for Filtering".

### 15. Node: Smart Gatekeeper (OpenAI)
*   **Type:** `OpenAI`
*   **Model:** `gpt-5-mini`
*   **Purpose:** Bulk filter 20 titles at once.
*   **System Message:**
    ```text
    You are a scout for "TheBoldUnknown."
    
    BRAND LENS:
    - Calm, Rational, Cinematic, Quietly Strange.
    - We value: Grounded anomalies, counterintuitive patterns, evidence-based mysteries.
    - We reject: Hype, fear-mongering, ungrounded conspiracy theories, and generic news.
    
    TASK:
    Review the list of titles provided by the user (indexed 0 to N).
    Return a JSON object containing an array "passed_indices" with the numbers of the titles that fit the lens.
    
    PASS (YES):
    - "A tiny detail in this research paper is stranger than it looks."
    - "Nature has a habit of breaking its own rules."
    - Specific scientific oddities (Time crystals, non-evolutionary traits).
    
    FAIL (NO):
    - Political/Social commentary.
    - Standard tech product launches.
    - Sports/Celebrity updates.
    - Overtly mystical/spiritual without evidence.
    
    Output Format:
    { "passed_indices": [0, 3, 5, ...] }
    ```
*   **User Message:** `{{ $json.prompt }}`
*   **Inputs:** Connect output of "Prepare Prompt".

### 16. Node: Filter Batch (Code)
*   **Type:** `Code`
*   **Purpose:** Keep only the items that the AI approved.
*   **Code:**
    ```javascript
    // Robustly find the content from the AI node
    const json = items[0].json;
    let aiResponse;
    
    if (json.output && json.output[0] && json.output[0].content) {
       aiResponse = json.output[0].content[0].text;
    } else if (json.choices && json.choices[0]) {
       aiResponse = json.choices[0].message.content;
    } else {
       aiResponse = {};
    }
    
    let approvedIndices = [];
    try {
        const parsed = typeof aiResponse === 'string' ? JSON.parse(aiResponse) : aiResponse;
        approvedIndices = parsed.passed_indices || [];
    } catch (e) {
        return [];
    }

    // RETRIEVE ORIGINAL ITEMS (Pass-Through Strategy)
    // We retrieve the hidden '_original_batch' from the Prepare Prompt node
    let batch = [];
    try {
        const prepareNode = $('Prepare Prompt (Code)').first();
        batch = prepareNode.json._original_batch || [];
    } catch(e) {
        // If that fails, try the Batch node as fallback
        try { batch = $('Batch for Filtering').all().map(i => i.json); } catch(err) {}
    }
    
    // Map back to original items
    const survivors = [];
    approvedIndices.forEach(idx => {
       if (batch[idx]) {
         survivors.push({ json: batch[idx] });
       }
    });
    
    return survivors;
    ```
*   **Inputs:** Connect output of "Smart Gatekeeper".

### 17. Node: Split for Processing (Single Loop)
*   **Type:** `Split In Batches`
*   **Batch Size:** `1`
*   **Purpose:** Now we process the *survivors* 1-by-1 for the database.
*   **Inputs:** Connect output of "Filter Batch".
*   **Loop Connection:** Connect the "Done" output of this node back to **Step 14 (Batch for Filtering)** Input.
    *   *Why?* This allows us to grab the *next* batch of 20 raw items once we are done processing the survivors of the current batch.

### 18. Node: Check Existing URL (Postgres)
*   **Type:** `Postgres`
*   **Operation:** `Execute Query`
*   **Query:** `SELECT count(*) as count FROM processed_urls WHERE url = $1`
*   **Query Parameters:** `$1`: `{{ $json.url }}`
*   **Inputs:** Connect "Loop" output of "Split for Processing".

### 19. Node: If New URL (If)
*   **Type:** `If`
*   **Condition:** `{{ $json.count }} == 0` (or `{{ $json.count }} == '0'` as Postgres often returns counts as strings)
    *   *Tip:* Check the "Keep Type" checkbox if comparing numbers, or use "String" mode if the database returns "0".
*   **Outputs:**
    *   **True:** Continue to Step 20.
    *   **False:** Connect back to **Step 17 (Split for Processing)** Input.

### 20. Node: Create Embedding (HTTP Request)
*   **Type:** `HTTP Request`
*   **Method:** `POST`
*   **URL:** `https://api.openai.com/v1/embeddings`
*   **Authentication:** `Header Auth` -> `Authorization: Bearer YOUR_OPENAI_KEY`
*   **Body Content:** `JSON`
*   **JSON Code:**
    ```javascript
    {{
      {
        "input": $('Split For Processing (Single Loop)').item.json.title + "\n" + $('Split For Processing (Single Loop)').item.json.summary,
        "model": "text-embedding-3-small"
      }
    }}
    ```
    *(Note: Using this JS Object format ensures special characters in the title/summary don't break the JSON)*
*   **Inputs:** Connect "True" output of "If New URL".

### 21. Node: Semantic Check (Postgres)
*   **Type:** `Postgres`
*   **Operation:** `Execute Query`
*   **Query:** 
    ```sql
    SELECT 1 - (embedding <=> $1) as similarity
    FROM leads
    ORDER BY embedding <=> $1
    LIMIT 1;
    ```
*   **Query Parameters:** `$1`: `{{ "[" + $json.data[0].embedding.join(',') + "]" }}`
*   **Inputs:** Connect output of "Create Embedding".
*   **Settings:** Set **"Always Output Data"** to **true** (so flow continues if DB is empty).

### 22. Node: If Unique (If)
*   **Type:** `If`
*   **Condition:** `{{ $json.similarity || 0 }}` < `0.90`
    *(Note: Using `|| 0` ensures that if the DB was empty, we treat the new story as having 0% similarity, i.e., unique)*
*   **Outputs:**
    *   **True:** Continue to Step 23.
    *   **False:** Connect back to **Step 17 (Split for Processing)** Input.

### 23. Node: The Brand Lens (OpenAI)
*   **Type:** `OpenAI`
*   **Model:** `gpt-5`
*   **System Message:**
    ```text
    You are the ruthlessly strict Editor-in-Chief of "TheBoldUnknown." Your brand explores the hidden strangeness of reality through a calm, rational, cinematic lens.

    **The Lens:**
    - Grounded but quietly strange.
    - Rational but imaginative.
    - Never sensational, conspiratorial, or clickbait.
    - "Smart storyteller" energy.

    **Task:**
    Analyze the provided story lead. Be extremely critical. Do not be polite. Assume the audience is intelligent and easily bored.

    **1. Score Brand Fit (0-100):**
    - 100 = Perfect fit (Scientific anomaly, counterintuitive pattern, historical twist).
    - < 50 = Reject (Politics, generic news, celebrity, overt pseudoscience).
    - Most good stories should score 60-75. Reserve 90+ for perfection.

    **2. Score Virality (0-100):**
    - 100 = "Wait... that's actually strange." (High curiosity gap).
    - 0 = "I already knew that" or "Who cares?"

    **3. Extract Discovery Topics:**
    - Identify 3 specific, searchable concepts derived from this story that would lead to *other* interesting stories.
    - These must be distinct concepts, not just the story title.
    - Example: Story about "Time Crystals" -> Topics: ["Non-equilibrium matter", "Perpetual motion loopholes", "Quantum computing errors"].
    
    Output JSON ONLY:
    {
      "brand_score": number,
      "virality_score": number,
      "reasoning": "Brief, blunt critique of why it scored this way.",
      "new_topics": ["string", "string", "string"]
    }
    ```
*   **User Message:** 
    ```text
    Title: {{ $('Split For Processing (Single Loop)').item.json.title }}
    Summary: {{ $('Split For Processing (Single Loop)').item.json.summary }}
    ```
*   **Response Format:** `JSON Object`
*   **Inputs:** Connect "True" output of "If Unique".

### 24. Node: Quality Gate (If)
*   **Type:** `If`
*   **Condition:**
    *   **Value 1:**
        ```javascript
        {{ 
          $json.output ? $json.output[0].content[0].text.brand_score : $json.choices[0].message.content.brand_score 
        }}
        ```
    *   **Operator:** `Larger or Equal` (Number)
    *   **Value 2:** `60`
*   **Outputs:**
    *   **True:** Continue to Step 25.
    *   **False:** Connect back to **Step 17 (Split for Processing)** Input.

### 25. Node: Store Lead (Postgres)
*   **Type:** `Postgres`
*   **Operation:** `Execute Query`
*   **Query:**
    ```sql
    INSERT INTO leads (title, url, summary, embedding, brand_score, virality_score, source_origin, status)
    VALUES ($1, $2, $3, $4, $5, $6, $7, 'new')
    RETURNING id;
    ```
*   **Query Parameters:** 
    ```javascript
    {{ 
      [
        $('Split For Processing (Single Loop)').item.json.title,
        $('Split For Processing (Single Loop)').item.json.url,
        $('Split For Processing (Single Loop)').item.json.summary,
        "[" + $('Create Embedding (HTTP Request)').item.json.data[0].embedding.join(',') + "]",
        $json.output ? $json.output[0].content[0].text.brand_score : $json.choices[0].message.content.brand_score,
        $json.output ? $json.output[0].content[0].text.virality_score : $json.choices[0].message.content.virality_score,
        $('Split For Processing (Single Loop)').item.json.source_origin
      ] 
    }}
    ```
    *(Note: We pass an array of values to map to $1, $2, $3... safely handling commas in text)*
*   **Inputs:** Connect "True" output of "Quality Gate".

### 26. Node: Mark URL Processed (Postgres)
*   **Type:** `Postgres`
*   **Operation:** `Execute Query`
*   **Query:** `INSERT INTO processed_urls (url) VALUES ($1) ON CONFLICT DO NOTHING;`
*   **Query Parameters:** 
    ```javascript
    {{ 
      [ $('Split For Processing (Single Loop)').item.json.url ] 
    }}
    ```
*   **Inputs:** Connect output of "Store Lead".

### 27. Node: Extract Topics (Code)
*   **Type:** `Code`
*   **Code:**
    ```javascript
    // --- CONFIGURATION ---
    // Update these if your node names are different
    const BRAND_LENS_NODE = 'The Brand Lens'; 
    const STORE_LEAD_NODE = 'Store Lead';
    // ---------------------

    let brandNode;
    try {
        brandNode = $(BRAND_LENS_NODE).first().json;
    } catch(e) {
        // Fallback: Try with (OpenAI) suffix if user named it that way
        try { brandNode = $('The Brand Lens (OpenAI)').first().json; } 
        catch(err) { throw new Error(`Could not find node "${BRAND_LENS_NODE}". Check name.`); }
    }

    let analysis;
    if (brandNode.output && brandNode.output[0] && brandNode.output[0].content) {
       analysis = brandNode.output[0].content[0].text;
    } else {
       const content = brandNode.choices ? brandNode.choices[0].message.content : "{}";
       try { analysis = typeof content === 'string' ? JSON.parse(content) : content; } catch(e) { analysis = {}; }
    }

    let leadId;
    try {
        leadId = $(STORE_LEAD_NODE).first().json.id;
    } catch(e) {
         try { leadId = $('Store Lead (Postgres)').first().json.id; }
         catch(err) { throw new Error(`Could not find node "${STORE_LEAD_NODE}". Check name.`); }
    }

    const newTopics = analysis.new_topics || [];
    
    return newTopics.map(topic => ({
      json: { topic: topic, origin_lead_id: leadId }
    }));
    ```
*   **Inputs:** Connect output of "Mark URL Processed".

### 28. Node: Save Topics (Postgres)
*   **Type:** `Postgres`
*   **Operation:** `Execute Query`
*   **Query:** `INSERT INTO discovery_topics (topic, origin_lead_id) VALUES ($1, $2) ON CONFLICT (topic) DO NOTHING;`
*   **Query Parameters:** 
    ```javascript
    {{ [ $json.topic, $json.origin_lead_id ] }}
    ```
*   **Inputs:** Connect output of "Extract Topics".

### 29. Final Loop
*   **Action:** Connect the output of "Save Topics" back to the **Input** of **Step 17 (Split for Processing)**.
*   **Logic:** This closes the processing loop for the current batch of survivors.

