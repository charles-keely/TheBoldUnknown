## Curator Agent

This directory contains the Curator Agent for TheBoldUnknown. It selects weekly stories from your `leads` table and queues them for research in `story_research`.

### Prerequisites (macOS)

- **Python**: 3.10+ recommended (`python3 --version`)
- **Pip**: installed with Python (`python3 -m ensurepip --upgrade`)
- **Postgres/Supabase**: `DATABASE_URL` pointing at your database
- **OpenAI API key**: for the curation model

From the project root (one level above this folder) you should already have your environment configured. If not, a minimal setup is:

```bash
# From the project root (..)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # or your preferred install command
```

### Environment variables

Set these in your shell (zsh on macOS by default):

```bash
export OPENAI_API_KEY="sk-..."               # your OpenAI key
export DATABASE_URL="postgres://..."         # Supabase/Postgres connection string
```

The `curator.config` module reads these and constructs `config.DATABASE_URL`, `config.OPENAI_API_KEY`, and `config.CURATOR_MODEL`.

### How to run the curator from within `/curator`

On macOS, you can run the curator directly from this directory.

```bash
cd /Users/charleskeely/Desktop/TheBoldUnknown/code/curator

# Activate your virtualenv if you use one
source ../.venv/bin/activate  # adjust path/name if different

# DRY RUN: no DB changes, just logs + curation_results.txt
python main.py --dry-run

# REAL RUN: updates DB (approves leads + queues story_research)
python main.py
```

What happens on a **real run** (`python main.py`):

- Fetches candidate leads created after the most recently **published** story.
- Sends them to the LLM curator and selects stories.
- Writes a human-readable report to `curation_results.txt` in this folder.
- For each selected story:
  - Sets `leads.status = 'approved'`.
  - Inserts/updates a row in `story_research` with `status = 'queued'` and the curator reasoning in `notes`.

### Inspecting results in the DB

In Supabase (SQL editor), you can see the queued research items with:

```sql
SELECT
  sr.id,
  sr.lead_id,
  l.title,
  sr.status,
  sr.notes,
  sr.created_at
FROM story_research sr
JOIN leads l ON l.id = sr.lead_id
ORDER BY sr.created_at DESC
LIMIT 50;
```

This shows you which curated stories are now waiting in the research queue.