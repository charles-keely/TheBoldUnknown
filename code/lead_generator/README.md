# The Bold Unknown: Infinite Lead Generator

This is the Python implementation of the "Infinite Lead Generator" system. It autonomously scouts the internet for "quietly strange" stories, filters them through a strict brand lens, and stores high-quality leads in your database.

## 🚀 How It Works (The Pipeline)

The system operates as a linear pipeline with three main phases:

### 1. Ingestion Phase (The Wide Net)
The system pulls raw content from two sources:
*   **RSS Feeds:** Monitors ~35 high-quality sources (Quanta, Nautilus, NASA, etc.) defined in `services/rss.py`.
*   **Active Discovery (Perplexity):** Picks a topic from the `discovery_topics` database table, generates a specific search query, and finds new stories via Perplexity's API.

### 2. The Filter Funnel (The Gatekeepers)
Raw leads must survive a gauntlet of filters to reach the database:

1.  **URL Deduplication (First):**
    *   Instant check: Have we seen this exact URL before?
    *   Free and fast — removes obvious duplicates immediately.

2.  **Smart Gatekeeper (Batch Filter):**
    *   Analyzes titles in batches of 20.
    *   **Goal:** Fast rejection of celebrity gossip, politics, and generic news.
    *   **Criteria:** Passes anything with a potential "quiet WTF" or counterintuitive angle.

3.  **Semantic Deduplication:**
    *   Generates vector embeddings for Title + Summary.
    *   Checks if story is too similar to existing leads.
    *   **Threshold:** 85% similarity = duplicate (strict policy).

4.  **Virality Check:**
    *   Scores the story's viral potential (0-100).
    *   **Criteria:** Curiosity gaps, counterintuitive hooks, "wait, what?" moments.
    *   **Pass Threshold:** Must score ≥ 80/100 to proceed.

5.  **Brand Lens Check:**
    *   Deep analysis of brand alignment (Title + Summary).
    *   **Criteria:** "Grounded Strangeness," cinematic tone, evidence-based mystery, honest framing.
    *   **Pass Threshold:** Must score ≥ 70/100 to be saved.

### 3. Expansion Phase (The Flywheel)
*   **Storage:** Accepted leads are saved to the `leads` table in Postgres.
*   **Fractal Expansion:** The AI extracts 2-3 *new* search topics from every accepted lead (e.g., a story about "Whale Songs" generates a search topic for "Cetacean Linguistics"). These are added to the `discovery_topics` queue, ensuring the system never runs out of things to search for.

---

## 🛠️ Setup & Installation

### 1. Prerequisites
*   Python 3.10+
*   PostgreSQL Database (Supabase)
*   API Keys for OpenAI (`gpt-5`) and Perplexity.

### 2. Install Dependencies
It is recommended to use a virtual environment:

```bash
cd lead_generator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Variables
Ensure your `.env` file (located in the project root) is populated:

```ini
# Database
POSTGRES_HOST=...
POSTGRES_PORT=6543
POSTGRES_DB=postgres
POSTGRES_USER=...
POSTGRES_PASSWORD=...

# API Keys
PERPLEXITY_API_KEY=...
OPENAI_API_KEY=...
```

---

## 🖥️ Usage

Run the system using the `main.py` CLI tool.

### Run the Full Workflow
Fetches from both RSS and Perplexity, runs all filters, and saves leads.
```bash
python main.py run
```

### Run Specific Sources
```bash
# Only check RSS feeds
python main.py run --source rss

# Only run Active Discovery (Perplexity)
python main.py run --source perplexity
```

### Test Database Connection
Quick check to ensure your credentials are working.
```bash
python main.py test-connection
```

---

## 📂 Project Structure

*   `main.py`: The CLI entry point.
*   `config.py`: Handles environment variables and settings.
*   `database.py`: Handles PostgreSQL connections, duplicate checks, and storage.
*   **`logic/`**: The brain of the operation.
    *   `workflow.py`: Orchestrates the flow (Fetch -> Filter -> Save).
    *   `filters.py`: **Contains the AI Prompts.** Edit this file to tweak the Brand Persona or Scoring logic.
*   **`services/`**: Integrations with the outside world.
    *   `rss.py`: Feed list and fetching logic.
    *   `perplexity.py`: Search API client.
    *   `llm.py`: OpenAI client wrapper.

## 📝 Editing the Brain (Prompts)
To change how the AI judges stories, edit **`logic/filters.py`**.
*   **`smart_gatekeeper`**: Controls what gets thrown out immediately (Politics, Gossip).
*   **`brand_lens_check`**: Controls the strict "Bold Unknown" scoring criteria.
