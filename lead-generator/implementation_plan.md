# Implementation Plan: TheBoldUnknown "Infinite" Story Lead Generator

## 1. System Architecture Overview

The system is designed as a self-feeding "Fractal Discovery" engine. It doesn't just consume feeds; it learns from every story it finds to generate new search vectors, ensuring it never runs out of fresh angles (avoiding echo chambers) while strictly adhering to the *TheBoldUnknown* brand lens.

### Core Components
1.  **Storage (Supabase):** Stores Leads (stories), Topics (search vectors), and Embeddings (for deduplication).
2.  **Input A - Passive (RSS):** Consistent baseline of high-quality scientific/curiosity feeds via a centralized Code Node.
3.  **Input B - Active (Perplexity/LLM):** Intelligent agent searching for specific queries derived from our "Topic Bank".
4.  **Processor (n8n + OpenAI):** 
    *   **Deduplication:** Checks if the story exists semantically.
    *   **Filtering:** Scores stories on Brand Fit (0-10) and Virality (0-10).
    *   **Expansion:** Extracts *new* search topics from *approved* stories to feed Input B.

---

## 2. Supabase Database Schema

We need three main tables to handle the logic: `leads`, `discovery_topics`, and `sources`.

### Table 1: `leads` (The Stories)
Stores the actual potential content pieces.
- `id`: UUID
- `title`: Text
- `url`: Text (Unique constraint not enough, need semantic check)
- `summary`: Text
- `embedding`: Vector (1536 dimensions for `text-embedding-3-small`)
- `brand_score`: Integer (0-10)
- `virality_score`: Integer (0-10)
- `status`: Enum ('new', 'approved', 'rejected', 'published')
- `source_origin`: Text (e.g., 'RSS: ScienceDaily' or 'Perplexity: Search Term X')
- `created_at`: Timestamp

### Table 2: `discovery_topics` (The Infinite Engine)
Stores keywords/concepts to guide the Active Search.
- `id`: UUID
- `topic`: Text (e.g., "Time Dilation", "Unexplained Archeology", "Mycelium Networks")
- `last_searched_at`: Timestamp (Used to rotate topics)
- `origin_lead_id`: UUID (Links back to the story that inspired this topic)
- `status`: Enum ('active', 'exhausted', 'paused')

### Table 3: `processed_urls`
Simple table to quick-reject exact URL matches before expensive vector checks.
- `url`: Text (Primary Key)

---

## 3. n8n Workflow Logic

The workflow will run on a schedule (e.g., every 6 hours).

### Step 1: The "Fractal" Input Phase
We generate potential leads from two directions simultaneously.

**Path A: Passive Intake (RSS)**
- **Trigger:** Schedule or Manual Trigger.
- **Node (Code):** Contains array of ~30 high-quality RSS feeds. Returns list of URLs.
- **Node (Split In Batches):** Loop through the list (batch size 1).
- **Node (RSS Read):** Fetches items from the current URL.
- **Node (Merge):** Aggregates all items.
- **Action:** Normalize data to JSON `{title, url, summary}`.

**Path B: Active Discovery (Perplexity)**
- **Trigger:** Query Supabase `discovery_topics` for 1 random topic where `last_searched_at` is oldest (or NULL).
- **Action (LLM):** Generate a specific Perplexity search query based on the topic.
    - *Example:* Topic is "Bioluminescence". Prompt: "Find recent scientific papers or documented anomalies regarding unexpected bioluminescence in deep sea organisms, specifically focusing on non-evolutionary theories."
- **Action (Perplexity API):** Run search, return top 5 results.
- **Update:** Mark topic as `last_searched_at = NOW()`.

### Step 2: Deduplication (The Echo Chamber Stopper)
- **Check 1 (Exact):** Is URL in `processed_urls`? If yes, stop.
- **Check 2 (Semantic):** 
    - Generate Embedding for `Title + Summary`.
    - Query Supabase: Is there a lead with `1 - cosine_distance < 0.1` (very similar)? 
    - If yes, stop. This prevents storing "The same story covered by two different news outlets."

### Step 3: The "Brand Lens" Filter (LLM Analysis)
We send the potential lead to an LLM (GPT-4o) with the **System Prompt** derived from `brand-guide.md`.

**Input:** Title, Summary/Content snippet.
**Task:**
1.  **Analyze Brand Fit:** Does it fit the "Quietly Strange/Rational" lens? (Score 1-10)
2.  **Analyze Virality:** Does it have a hook/twist? (Score 1-10)
3.  **Extract Topics:** Identify 3 *related but distinct* concepts to feed the `discovery_topics` engine. **CRITICAL:** These topics must be valid search terms for *TheBoldUnknown* genre, not just related to the story.

**Output (JSON):**
```json
{
  "brand_score": 8,
  "virality_score": 7,
  "reasoning": "Fits well. Rational explanation of a strange phenomenon.",
  "new_topics": ["Piezoelectric rocks", "Sonic anomalies in geology", "Village hums"]
}
```

### Step 4: Routing & Storage
- **If Brand Score < 6:** Discard (or store as 'rejected' for analysis).
- **If Brand Score >= 6:**
    - Insert into `leads` table with embedding.
    - Insert `new_topics` into `discovery_topics` (ignore duplicates).
    - Insert URL into `processed_urls`.

---

## 4. The "Infinite" Mechanism Explained

This workflow is "infinite" because of Step 3.3 (Extract Topics).

1.  **Start:** We seed the DB with 10 generic terms from the Brand Guide (e.g., "Space", "Physics", "History").
2.  **Run 1:** System searches "Physics". Finds a story about "Time Crystals".
3.  **Expansion:** System analyzes "Time Crystals" story and extracts related topics: "Non-equilibrium matter", "Perpetual motion loopholes", "Quantum computing errors".
4.  **Run 2:** System searches "Non-equilibrium matter" (a topic it didn't know existed in Run 1).
5.  **Result:** The system naturally branches out into niche, specific rabbit holes, mimicking human curiosity, rather than staying on generic "Science News".

---

## 5. Key Prompts

### The "Lens" Evaluator Prompt
> "You are the Editor-in-Chief of 'TheBoldUnknown'. Your brand explores the hidden strangeness of reality through a calm, rational, cinematic lens. 
> 
> Review this story lead. 
> 
> **Brand Check:**
> - Is it grounded? (Yes/No)
> - Is it quietly strange or counterintuitive? (Yes/No)
> - Does it avoid conspiracy/sensationalism? (Yes/No)
> 
> **Scoring:**
> - Brand Fit (1-10): 10 is a perfect match for the brand guide.
> - Virality (1-10): 10 is a story that makes someone say 'Wait, that's actually strange.'
> 
> **Discovery:**
> - Extract 3 specific, searchable concepts or phenomena related to this story that would make for good future investigations. These should be search terms, not full sentences. 
> - **Constraint:** Ensure these topics are broadly interesting and fit the 'TheBoldUnknown' vibe (Scientific Mystery, Anomalies, High Strangeness), avoiding hyper-specific local news or celebrity gossip."

---

## 6. Implementation Checklist

- [x] **Supabase:** Create project, enable `vector` extension.
- [x] **Supabase:** Run SQL migration to create tables.
- [x] **n8n:** Configure Credentials (Supabase, OpenAI, Perplexity).
- [x] **n8n:** Build "RSS Ingest" Sub-workflow.
- [x] **n8n:** Build "Perplexity Discovery" Sub-workflow.
- [x] **n8n:** Build "Analyzer & Storage" Main workflow.
- [x] **Seed:** Add initial topics to `discovery_topics`.

## 7. Next Steps for Deployment

1.  **Supabase:** Run the contents of `supabase_schema.sql` in your SQL Editor.
2.  **Supabase:** Run the contents of `seed_topics.sql` to prime the engine.
3.  **n8n:** Create a new workflow.
4.  **n8n:** Copy the logic from `n8n_rss_code.js` into a Code node.
5.  **n8n:** Follow the steps in `n8n_perplexity_logic.md` and `n8n_analyzer_logic.md` to build the nodes.
6.  **Test:** Run the workflow once manually to see the "Fractal Expansion" in action (check `discovery_topics` after the run to see new topics appear).
