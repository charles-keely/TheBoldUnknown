# Infinite Lead Generator Plan for TheBoldUnknown

## 1. Overview
**Goal:** Create an autonomous, infinite "lead generator" subworkflow in n8n that discovers, filters, and stores brand-aligned stories/topics for *TheBoldUnknown*.

**Core Philosophy:**
-   **Dynamic Compass:** Intelligently switches between "Gravity" (Core Pillars) and "Rabbit Holes" (Derived Topics) based on the quality of the current queue.
-   **Rabbit Hole Engine:** Explores related concepts to find fresh, non-obvious stories.
-   **Gravity:** Periodically pulls the focus back to core pillars to prevent drift into irrelevance or when the trail goes cold.
-   **No Duplicates:** Uses vector similarity to ensure uniqueness.
-   **Brand Alignment:** Strict filtering based on the `brand.txt` guidelines.

**Tech Stack:**
-   **Orchestrator:** n8n
-   **Database:** Supabase (PostgreSQL + pgvector)
-   **AI/LLM:** OpenAI (GPT-5.1)
-   **Search:** Perplexity API (Sonar Pro)

---

## 2. Architecture & Logic

### Concept: The "Orbit" Model
Imagine the content ecosystem as a solar system.
-   **The Sun (Core Pillars):** Defined in `brand.txt` (e.g., Declassified Ops, Ancient History, Quantum Physics).
-   **Gravity:** The force that ensures we don't drift into deep space (irrelevant nonsense).
-   **Rabbit Holes:** Comets or trajectories that take us away from the sun to explore new areas.

### Workflow Phases
1.  **Queue Health Check:** Analyzes the `search_queue` for high-potential pending keywords.
2.  **The Compass (Decision):** Decides whether to fetch a **Core Pillar** (Gravity) or a **Pending Keyword** (Rabbit Hole).
3.  **The Hunt (Search):** Execute search via Perplexity API for obscure/interesting stories.
4.  **The Filter (Analysis):** AI evaluates content against Brand Guidelines ("The Brain").
5.  **The Memory (Deduplication):** Check Vector Database for similarity.
6.  **The Ledger (Storage):** Save approved leads.
7.  **The Evolution (Learning):** Extract new search terms from the findings to refill the queue.

---

## 3. Database Schema (Supabase)

We need three main tables to handle the logic.

### Table 1: `leads`
Stores the actual stories found.
-   `id` (uuid, primary key)
-   `title` (text)
-   `summary` (text)
-   `url` (text, unique)
-   `relevance_score` (int, 0-100)
-   `virality_score` (int, 0-100)
-   `embedding` (vector, for semantic deduplication)
-   `status` (enum: 'new', 'approved', 'rejected', 'published')
-   `pillar_tag` (text)
-   `created_at` (timestamp)

### Table 2: `search_queue`
The "Rabbit Hole" engine's memory.
-   `id` (uuid)
-   `keyword` (text)
-   `source_lead_id` (uuid, foreign key)
-   `generation_depth` (int)
-   `status` (enum: 'pending', 'processed', 'exhausted')
-   `priority_score` (int)

### Table 3: `brand_pillars` (The Gravity Anchors)
Static list of core topics.
-   `id` (uuid)
-   `name` (text)
-   `description` (text)

---

## 4. The Workflow Logic (Step-by-Step)

### Step 1: Check Queue Strength
-   Query the `search_queue` for the max `priority_score` and total `queue_size`.

### Step 2: The Compass (Decision Engine)
-   **Logic:**
    -   If `top_score` <= 70 OR `queue_size` == 0: **Engage Gravity**.
    -   Else: **Enter Rabbit Hole**.
-   **Gravity Mode:** Selects a random topic from `brand_pillars`.
-   **Rabbit Hole Mode:** Selects the keyword with the highest `priority_score` from `search_queue`.

### Step 3: The Hunt (Search)
-   **Tool:** Perplexity API (`sonar-pro`).
-   **Prompt:** "Find 5 recent or interesting obscure stories related to: [Keyword]..."

### Step 4: The Filter (AI Analysis)
-   **Tool:** OpenAI ("The Brain").
-   **System Prompt:** Injects `brand.txt`.
-   **Task:**
    1.  Rate "Relevance" (Brand Fit).
    2.  Rate "Virality".
    3.  Extract 3 new "lateral" keywords.

### Step 5: The Memory (Deduplication)
-   **Vector Check:**
    -   Generate embedding for `title` + `summary`.
    -   Query `leads` for cosine similarity > 0.85 OR exact URL match.
    -   **If Match Found:** Discard.

### Step 6: The Ledger (Storage)
-   **Insert to `leads`:** Store the story if approved.
-   **Insert to `search_queue`:**
    -   Add extracted keywords.
    -   **Priority Scoring:** New keywords inherit the `virality_score` of their parent story as their `priority_score`.

---

## 5. Gravity & Rabbit Hole Logic Details

### The "Gravity" Reset
We default to Gravity when:
1.  The queue is empty.
2.  The best pending keyword has a low score (<= 70), indicating the "trail has gone cold."
3.  (Optional Future) Too many consecutive failures occur.

### The "Rabbit Hole" Priority
-   Keywords are prioritized by their parent story's potential impact (`virality_score`).
-   This naturally guides the system towards more engaging topics while exploring deep into the graph.
