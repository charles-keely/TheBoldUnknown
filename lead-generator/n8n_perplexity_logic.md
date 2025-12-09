# n8n Sub-Workflow: Active Discovery (Perplexity)

This section details the nodes required to build the "Active Hunter" part of the workflow.

## 1. Node: Supabase (Fetch Next Topic)
**Goal:** Get the topic that hasn't been searched in the longest time.

*   **Operation:** `Execute Query`
*   **Query:**
    ```sql
    SELECT * FROM discovery_topics 
    WHERE status = 'active' 
    ORDER BY last_searched_at ASC NULLS FIRST 
    LIMIT 1;
    ```

## 2. Node: OpenAI (Generate Search Query)
**Goal:** Turn a broad topic (e.g., "Bioluminescence") into a specific, high-yield search query for Perplexity.

*   **Model:** `gpt-4o` or `gpt-3.5-turbo`
*   **System Prompt:**
    ```text
    You are an expert researcher for "TheBoldUnknown," a brand focused on scientific anomalies, strange natural phenomena, and hidden history. 
    
    Your goal is to convert a generic "Topic" into a specific, highly targeted search query that will uncover recent papers, documented oddities, or under-reported events.
    
    Guidelines:
    - Focus on the "High Strangeness" or "Scientific Mystery" aspect of the topic.
    - Ask for specific types of evidence: "recent studies," "documented accounts," "anomalous data."
    - Avoid generic "What is X" questions.
    ```
*   **User Prompt:**
    ```text
    Topic: {{ $json.topic }}
    
    Generate a search query for Perplexity.ai. Output ONLY the query string.
    ```

## 3. Node: HTTP Request (Perplexity API)
**Goal:** Perform the deep search.

*   **Method:** `POST`
*   **URL:** `https://api.perplexity.ai/chat/completions`
*   **Authentication:** Header `Authorization: Bearer YOUR_API_KEY`
*   **JSON Body:**
    ```json
    {
      "model": "llama-3.1-sonar-large-128k-online",
      "messages": [
        {
          "role": "system",
          "content": "Find specific, documented stories or research papers. Be precise. Return a list of 5 distinct story leads including their source URL."
        },
        {
          "role": "user",
          "content": "{{ $json.message.content }}" 
        }
      ],
      "temperature": 0.2
    }
    ```
    *(Note: Replace `{{ $json.message.content }}` with the output from the OpenAI node)*

## 4. Node: Supabase (Update Topic Timestamp)
**Goal:** Rotate the topic to the back of the queue so we don't spam it.

*   **Operation:** `Update`
*   **Table:** `discovery_topics`
*   **Match Logic:** `id` = `{{ $node["Supabase (Fetch Next Topic)"].json.id }}`
*   **Fields to Update:**
    *   `last_searched_at`: `{{ new Date().toISOString() }}`

## 5. Node: Code (Parse Results)
**Goal:** Perplexity returns a text block. We need to parse this into a structured JSON list of leads for the main processor.

*   **Language:** JavaScript
*   **Code:**
    ```javascript
    // Use an LLM node after Perplexity to parse the text into JSON, 
    // OR use a regex if the output is consistently formatted. 
    // Recommended: Add a standard OpenAI node here to "Format as JSON"
    
    const content = items[0].json.choices[0].message.content;
    
    return {
      json: {
        raw_content: content,
        source_origin: `Perplexity: ${$('Supabase (Fetch Next Topic)').item.json.topic}`
      }
    };
    ```

