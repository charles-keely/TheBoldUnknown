# Lead Generator Implementation Plan

## Goal
Migrate the "Infinite Lead Generator" n8n workflow into a robust, maintainable, and easy-to-debug Python CLI application. The system will ingest content from RSS feeds and Perplexity, filter it through a multi-stage process (Deduplication -> Virality -> Brand Fit), and store high-quality leads in a PostgreSQL database.

## Architecture

### Tech Stack
-   **Language:** Python 3.11+
-   **Database:** PostgreSQL (Compatible with existing Supabase schema)
-   **CLI:** `typer` or `argparse` for easy command-line execution.
-   **AI/LLM:** `openai` SDK for Embeddings and GPT-4o-mini/GPT-4o.
-   **Feeds:** `feedparser` for RSS.
-   **HTTP:** `httpx` or `requests` for Perplexity API.

### Directory Structure
```
lead_generator/
├── main.py                 # CLI entry point (commands: run, stats, test-connection)
├── config.py               # Configuration loading (Env vars)
├── database.py             # DB connection and CRUD operations
├── services/
│   ├── rss.py             # RSS fetching and normalization
│   ├── perplexity.py      # Perplexity topic research
│   └── llm.py             # OpenAI and Perplexity API wrappers
├── logic/
│   ├── workflow.py        # The main orchestration loop
│   └── filters.py         # The 3-stage filtering logic
├── utils/
│   ├── logger.py          # Centralized logging configuration
│   └── text.py            # Text cleaning/normalization
├── requirements.txt
└── .env.example
```

## Workflow Logic (Revised)

The pipeline will run in a linear sequence for each source, or parallelized where possible.

### 1. Ingestion Phase
-   **RSS Source**: Iterate through the defined list of ~60 RSS feeds.
    -   Fetch feed items.
    -   Normalize to standard `LeadCandidate` object.
-   **Perplexity Source**:
    -   Fetch active topics from `discovery_topics` table (sorted by `last_searched_at`).
    -   Generate search queries via LLM.
    -   Query Perplexity API.
    -   Parse results into `LeadCandidate` objects.
    -   Update `last_searched_at` for the topic.

### 2. Filtering Phase (The Funnel)

**Stage 1: Technical & Semantic Deduplication (Fail Fast)**
*Goal: Remove garbage and duplicates cheaply.*
1.  **URL Check**: Check `processed_urls` table. If exists -> Drop.
2.  **Embedding**: Generate embedding for Title + Summary (OpenAI `text-embedding-3-small`).
3.  **Similarity Check**: Query `leads` table for cosine similarity > 0.90. If exists -> Drop.

**Stage 2: Virality Check (Mid-Cost)**
*Goal: Ensure the story has a "hook".*
1.  **Input**: Title, Summary.
2.  **LLM Call**: "Virality Scorer".
    -   *Criteria*: Curiosity gap, "weirdness", counter-intuitive nature.
    -   *Output*: Score (0-100).
3.  **Decision**: If Score < 60 -> Drop.

**Stage 3: Brand Identity Check (High-Cost/High-Precision)**
*Goal: Strict alignment with "The Bold Unknown".*
1.  **Input**: Title, Summary, Virality Score.
2.  **LLM Call**: "Editor-in-Chief".
    -   *Criteria*: Grounded, rational, cinematic, quietly strange. Rejects clickbait/pseudoscience.
    -   *Output*: Brand Score (0-100), Reasoning, New Discovery Topics.
3.  **Decision**: If Brand Score < 70 (configurable) -> Drop.

### 3. Storage & Expansion Phase
If a lead survives all filters:
1.  **Store Lead**: Insert into `leads` table.
2.  **Mark Processed**: Add URL to `processed_urls`.
3.  **Fractal Expansion**: Extract new topics from the Brand Check output and insert into `discovery_topics`.

## Error Handling & Logging

-   **Console Output**: Clean, rich text output (using `rich` library) showing progress bars and simple status messages (e.g., "Skipped: Duplicate", "Filtered: Low Virality").
-   **File Logging**: Detailed `app.log` file capturing full stack traces, API response errors, and raw LLM decisions for debugging.
-   **Resiliency**:
    -   RSS timeouts will be caught and logged (warning level), allowing other feeds to proceed.
    -   API Rate limits (OpenAI/Perplexity) will have exponential backoff.
    -   Database connection failures will halt the script gracefully.

## CLI Usage

The user will run the generator using simple commands:

```bash
# Run the full process
python lead_generator/main.py run

# Run only RSS or only Perplexity
python lead_generator/main.py run --source rss
python lead_generator/main.py run --source perplexity

# Check stats (how many leads today, error rates)
python lead_generator/main.py stats
```

## Database Schema (Existing)

We will use the existing schema but ensure Python models match it:
-   `leads`: Stores the final approved leads.
-   `discovery_topics`: Stores topics for Perplexity.
-   `processed_urls`: Stores all URLs seen (even rejected ones) to prevent reprocessing.

## Step-by-Step Build Plan

1.  **Setup**: Initialize environment, `requirements.txt`, and basic `main.py` shell.
2.  **Database Layer**: Implement `database.py` to handle Postgres connections and queries.
3.  **Ingestion (RSS)**: Implement `rss.py` to fetch and normalize feeds.
4.  **Stage 1 Filter**: Implement URL check and Embedding generation/check.
5.  **Ingestion (Perplexity)**: Implement `perplexity.py` logic.
6.  **Stage 2 & 3 Filters**: Implement `llm.py` and the prompt logic for Virality and Brand.
7.  **Orchestration**: Tie it all together in `workflow.py` with the CLI.
8.  **Refinement**: Add `rich` progress bars and `stats` command.
