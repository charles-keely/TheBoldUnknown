# Story Researcher

Automated research pipeline for TheBoldUnknown. Takes stories queued in `story_research` and gathers comprehensive research to prepare for Instagram post creation.

## What It Does

1. **Phase 1 (Ground Truth)**: Uses Perplexity to gather comprehensive facts about a story — who, what, where, when, why, visual details, and confirmation of accuracy.

2. **Phase 2 (The Hook)**: Uses GPT-4o to identify the "Wait... What?" angle — the single most strange, counterintuitive detail that will make someone stop scrolling.

3. **Optional Deep Dive**: If more detail is needed on a specific visual or emotional element, runs one additional research query.

## Setup

```bash
cd code/story_researcher

# Create virtual environment (if not already done)
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Environment Variables

Ensure your `.env` file (in the `code/` directory) has:

```
POSTGRES_HOST=...
POSTGRES_PORT=6543
POSTGRES_DB=postgres
POSTGRES_USER=...
POSTGRES_PASSWORD=...
PERPLEXITY_API_KEY=...
OPENAI_API_KEY=...
```

## Running

### Single Test Run (Recommended for Testing)

Process **one** story and output results to `research_output.md`:

```bash
cd code
PYTHONPATH=. ./story_researcher/venv/bin/python -m story_researcher.main --single
```

This will:
- Pick the first queued story
- Run the full research pipeline
- Save results to the database
- Output a readable `research_output.md` file for review

### Process All Queued Stories

```bash
cd code
PYTHONPATH=. ./story_researcher/venv/bin/python -m story_researcher.main
```

### Process a Limited Batch

```bash
cd code
PYTHONPATH=. ./story_researcher/venv/bin/python -m story_researcher.main --limit 5
```

## Output

Results are stored in the `story_research.research_data` JSONB column with this structure:

```json
{
  "phase_1_ground_truth": "...",
  "phase_2_angles": {
    "hook": "A 1-2 sentence WTF hook",
    "follow_up_question": "Optional question or null",
    "deep_dive": {
      "question": "...",
      "answer": "..."
    }
  }
}
```

## Resetting Test Data

If you need to re-run research on stories, use this SQL in Supabase:

```sql
-- Reset all research back to queued
UPDATE story_research 
SET 
  status = 'queued',
  research_data = NULL,
  started_at = NULL,
  completed_at = NULL;
```

Or reset a specific story:

```sql
UPDATE story_research 
SET status = 'queued', research_data = NULL
WHERE id = 'your-research-id-here';
```
