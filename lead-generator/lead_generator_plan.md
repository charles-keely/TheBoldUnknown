# Infinite Lead Generator Plan for TheBoldUnknown

## 1. Overview
**Goal:** Create an autonomous, infinite "lead generator" subworkflow in n8n that discovers, filters, and stores brand-aligned stories/topics for *TheBoldUnknown*.

**Core Philosophy:**
-   **Multifaceted Exploration:** The system must behave like a curious investigator, not a singular obsession. It intentionally fractures its search paths into Vertical (Deep), Lateral (Tangential), and Wildcard (Novel) directions.
-   **Echo Chamber Prevention:** We strictly deprioritize "more of the same." If we just found a pyramid story, the next search should look for a black hole or a CIA document, not another pyramid.
-   **Dynamic Vector Compass:** Logic that forces the system to rotate its "viewing angle" every run to ensure variety.
-   **Freshness First:** Priority is given to new, distinct topics over digging deeper into existing ones.
-   **Brand Alignment:** Strict filtering based on the `brand.txt` guidelines.

**Tech Stack:**
-   **Orchestrator:** n8n
-   **Database:** Supabase (PostgreSQL + pgvector)
-   **AI/LLM:** OpenAI (GPT-5.1 or 4o)
-   **Search:** Perplexity API (Sonar Pro)

---

## 2. Architecture & Logic

### Concept: The "Vector Compass"
Instead of a simple "Gravity vs. Rabbit Hole" binary, we use a 4-point compass to direct the search. Every run rolls a die (weighted) to decide the Direction.

1.  **North (Core Gravity):** Return to the immutable Pillars (e.g., "Ancient History").
2.  **East (Lateral Leap):** Pivot from a recent topic to a *tangential* field (e.g., "Pyramids" -> "Geological Anomalies").
3.  **South (Deep Dive):** Drill vertically into a specific high-interest story (The "Rabbit Hole"). **(Restricted usage to avoid echo chambers).**
4.  **West (Wildcard/Freshness):** Search for "New anomalies discovered this month" or combine two unrelated pillars (e.g., "Consciousness" + "Tech").

### Workflow Phases
1.  **The Compass Spin:** Randomly selects one of the 4 Directions (Weighted: 30% Lateral, 30% Wildcard, 20% Gravity, 20% Deep).
2.  **The Fetch:** Retrieves the appropriate keyword or prompt based on the Direction.
3.  **The Hunt (Search):** Execute search via Perplexity API with strict "Distinctness" instructions.
4.  **The Filter (Analysis):** AI evaluates content and—crucially—extracts *diverse* next-step keywords (1 Vertical, 1 Lateral, 1 Wildcard).
5.  **The Memory (Deduplication):** Strict vector similarity check.
6.  **The Ledger (Storage):** Save approved leads and populate the `search_queue` with typed keywords.

---

## 3. Database Schema (Supabase)

### Table 1: `leads`
Stores the actual stories found.
-   `id` (uuid, primary key)
-   `title` (text)
-   `summary` (text)
-   `url` (text, unique)
-   `relevance_score` (int, 0-100)
-   `virality_score` (int, 0-100)
-   `score_breakdown` (jsonb)  <-- NEW: Stores {novelty, visual, social, wait_what}
-   `embedding` (vector)
-   `status` (enum: 'new', 'approved', 'rejected', 'published')
-   `pillar_tag` (text)
-   `keywords` (text[])  <-- NEW: Specific tags e.g. ["Pyramids", "Greece"]
-   `discovery_type` (enum: 'vertical', 'lateral', 'wildcard', 'gravity') <-- NEW
-   `created_at` (timestamp)

### Table 2: `search_queue`
The "Compass" memory.
-   `id` (uuid)
-   `keyword` (text)
-   `type` (enum: 'vertical', 'lateral', 'wildcard')  <-- NEW
-   `source_lead_id` (uuid, foreign key)
-   `status` (enum: 'pending', 'processed', 'exhausted')
-   `priority_score` (int)
-   `created_at` (timestamp)

### Table 3: `brand_pillars` (Gravity Anchors)
Static list of core topics.
-   `id` (uuid)
-   `name` (text)
-   `description` (text)

---

## 4. The Workflow Logic (Step-by-Step)

### Step 1: The Compass Spin (Decision Engine)
-   **Logic:** Generate a random number (1-100).
    -   1-30: **Lateral Leap** (Explore connected topics).
    -   31-60: **Wildcard** (Explore brand-aligned randoms).
    -   61-80: **Gravity** (Reset to a Pillar).
    -   81-100: **Deep Dive** (Vertical follow-up).
-   *Override:* If `search_queue` is empty, force **Gravity**.

### Step 2: The Fetch (With Fallback Cascade)
-   **Logic:** Attempt to fetch based on Compass direction. If empty, cascade to the next available type.
-   **1. Lateral Strategy:**
    -   Try: Fetch top `search_queue` (Type = 'lateral').
    -   Fallback: Try 'wildcard' -> Then 'gravity'.
-   **2. Wildcard Strategy:**
    -   Try: Fetch top `search_queue` (Type = 'wildcard').
    -   Fallback: Try 'gravity' (Always available).
-   **3. Deep Dive Strategy:**
    -   Try: Fetch top `search_queue` (Type = 'vertical').
    -   Fallback: Try 'lateral' -> Then 'gravity'.
-   **4. Gravity Strategy:**
    -   Action: Select random from `brand_pillars`. (Always succeeds).

### Step 3: The Hunt (Perplexity)
-   **Tool:** Perplexity API (`sonar-pro`).
-   **Prompt Strategy:**
    -   "Find 3 DISTINCT and obscure stories related to: [Keyword]."
    -   "Constraint: Do not return stories about [Last 3 Lead Titles] (Prevent immediate dupes)."
    -   "Focus: Novelty and 'High Strangeness' over repetitive news."
    -   "Strict Constraint: Include documented anomalies or credible reports (even if speculative), but strictly distinguish them from verified facts. Avoid debunked myths or pure fiction."

### Step 4: The Filter (AI Analysis & Extraction)
-   **Tool:** OpenAI ("The Brain").
-   **Task:**
    1.  **Strict Virality Scoring (The "Harsh Editor" Protocol):**
        -   *Problem:* AI tends to rate everything 80/100.
        -   *Solution:* Use a rubric-based scoring system.
        -   **Novelty (0-25):** Is this new information or a tired trope?
        -   **"Wait, What?" Factor (0-25):** Does it sound impossible but is verified (or is a credible multi-witness report)?
        -   **Visual Potential (0-25):** Can we create a cinematic image for it?
        -   **Social Spark (0-25):** Will people tag a friend?
        -   *Calibration:* "Assume the average story is a 50. Only rate >80 if it is truly exceptional."
    2.  **Echo Check:** If the story is too similar to the last 5 stories, reject it.
    3.  **Data Extraction:**
        -   **Tags:** Extract 3-5 granular tags (e.g. "Greece", "Astronomy").
        -   **Score Breakdown:** Return the individual sub-scores.
    4.  **Keyword Extraction (The Seed Mechanism):**
        -   Extract exactly 3 keywords, one for each category:
            -   **1. Vertical:** A specific detail to drill down (e.g., "Thermoluminescence dating flaws").
            -   **2. Lateral:** A related but distinct field (e.g., "Acoustic levitation in Tibet").
            -   **3. Wildcard:** A completely different "TheBoldUnknown" topic (e.g., "CIA Gateway Process").
        -   *Note:* The "Wildcard" ensures we always have an exit door from the current topic.

### Step 5: The Ledger (Storage)
-   **Insert `leads`:** Standard storage.
-   **Insert `search_queue`:**
    -   Save the 3 keywords with their respective `type`.
    -   **Scoring:**
        -   Wildcards get `priority_score` = 90 (High incentive to switch topics).
        -   Laterals get `priority_score` = 75 (Medium).
        -   Verticals get `priority_score` = 50 (Low - only drill if nothing else exists).

---

## 5. Why This Solves the "Echo Chamber"
1.  **Forced Rotation:** The Compass probability ensures we only "Drill Down" (Vertical) 20% of the time. 80% of the time, we are moving sideways (Lateral), resetting (Gravity), or jumping to something new (Wildcard).
2.  **Type-Based Queuing:** By tagging keywords as 'Vertical', 'Lateral', or 'Wildcard', we can programmatically prefer diversity. We explicitly score 'Wildcard' keywords higher.
3.  **Distinctness Prompting:** We explicitly tell Perplexity to look for *distinct* stories.
