# Story Researcher Implementation Plan

## Objective
Automate the research phase for stories queued in `story_research`. The goal is to gather comprehensive textual information, verify facts, and specifically identify the "TheBoldUnknown" angle (the "WTF factor") to prepare for content creation.

## 1. Database Schema Updates
We need a structured place to store the research results. The current `notes` field is insufficient for structured data.

- **Action**: Add `research_data` (JSONB) column to `story_research` table.
- **Why**: Allows storing multi-part research (e.g., general summary, specific Q&A, source links) in a queryable format.

## 2. Research Workflow (The "Two-Angle" Approach)
As requested, we will focus on textual research first. We will implement a multi-step "Researcher Agent".

### Step 1: Ingestion
- Fetch items from `story_research` with status `queued`.
- Retrieve context (Title, URL, Summary, Brand/Virality scores) from the `leads` table.

### Step 2: Phase 1 Research (Broad Context)
- **Tool**: Perplexity API (`llama-3.1-sonar-large-128k-online`).
- **Prompt**: A static, robust prompt to get the "Ground Truth".
- **Goal**: Establish the who, what, where, when, and scientific/historical context. Verify the story is real.

### Step 3: Phase 2 Research (The "Angle" Deep Dive)
- **Tool**: OpenAI (GPT-4o) + Perplexity API.
- **Logic**:
    1. Pass Phase 1 results to GPT-4o.
    2. **Prompt**: "Given this story and TheBoldUnknown brand guide (looking for the 'strange', 'uncanny', 'counterintuitive'), generate 3 specific follow-up questions to uncover the most fascinating details."
    3. Run these specific questions through Perplexity to get deep, targeted answers.

### Step 4: Storage
- Aggregate Phase 1 (General) and Phase 2 (Specifics) into a JSON object.
- Store in `story_research.research_data`.
- Update `story_research.status` -> `completed`.

## 3. Project Structure (`code/story-researcher/`)
- `config.py`: Configuration and Env Var loading (matching `curator/config.py`).
- `db.py`: Database interaction (fetching queue, updating JSONB).
- `researcher.py`: Main logic class containing the 2-phase research loop.
- `main.py`: Entry point to run the worker.
- `prompts.py`: Storage for System Prompts and Research Prompts.

## 4. Next Steps
1. Approve this plan.
2. Execute DB Migration.
3. Scaffold the Python files.
4. Implement the Perplexity/OpenAI integration.
