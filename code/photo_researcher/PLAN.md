# Photo Researcher Implementation Plan

This module is responsible for finding, verifying, and curating images for stories that have completed the research phase.

## 1. Overview

The Photo Researcher operates as a downstream process of the `story_researcher`. It takes completed story research, generates intelligent search queries, finds potential images, and uses AI vision to verify their relevance and content.

**Input:** Completed `story_research` records (containing ground truth and follow-up research).
**Output:** A collection of verified, rated, and labeled images stored in the `story_photos` table.

## 2. Architecture

The system consists of the following components:

### A. Database (`db.py`)
- **New Table**: `story_photos`
    - `id`: UUID
    - `story_research_id`: UUID (Foreign Key)
    - `image_url`: Text
    - `source_page_url`: Text
    - `search_query`: Text
    - `description`: Text (AI generated/verified)
    - `relevance_score`: Integer (0-10)
    - `verifiability_score`: Integer (0-10)
    - `status`: Text ('potential', 'approved', 'rejected')
    - `metadata`: JSONB (author, date, original_context, technical_details)
    - `created_at`: Timestamp
- **Functions**:
    - `fetch_stories_needing_photos()`: Selects stories with `status='completed'` that don't have enough approved photos yet.
    - `save_photo_candidate(...)`: Stores found images.
    - `update_photo_status(...)`: Updates approval status.

### B. Query Generator (`generator.py`)
- **Role**: Analyzes story research text to formulate search queries.
- **Model**: OpenAI GPT-4o (or similar).
- **Logic**: 
    - Reads story title, summary, and "ground truth" research.
    - Generates 1-3 specific search queries likely to yield high-quality, relevant images.
    - Focuses on nouns, specific entities, locations, and historical events mentioned in the text.

### C. Image Searcher (`searcher.py`)
- **Role**: Executes search queries to find candidate images.
- **Service**: Google Custom Search JSON API (recommended) or Bing Image Search API.
- **Logic**:
    - Iterates through generated queries.
    - Fetches top N results per query.
    - Deduplicates results based on URL.
    - Basic filtering (e.g., exclude known stock photo sites if desired, or prioritize specific domains).

### D. Technical Validator (`validator.py`)
- **Role**: Ensures images are technically usable.
- **Logic**:
    - Performs HTTP `HEAD` or `GET` requests.
    - Checks HTTP Status (200 OK).
    - Checks `Content-Type` (image/jpeg, image/png, etc.).
    - Checks file size (optional, to avoid thumbnails or massive raw files).

### E. Visual Analyzer (`analyzer.py`)
- **Role**: Verifies content and relevance using AI Vision.
- **Model**: OpenAI GPT-4o (Vision).
- **Logic**:
    - Passes the image URL (or base64 content) + Story Context to the model.
    - Asks the model to:
        1.  **Describe** the image content.
        2.  **Verify** connection to the story details.
        3.  **Extract** visible dates, credits, or source entities.
        4.  **Rate** relevance (1-10) and verifiability (1-10).
    - Returns a structured analysis object.

### F. Orchestrator (`main.py`)
- **Role**: Ties everything together.
- **Flow**:
    1.  `db.fetch_stories_needing_photos()`
    2.  For each story:
        a.  `generator.generate_queries(story)`
        b.  For each query:
            i.  `searcher.search(query)` -> candidates
        c.  For each candidate:
            i.  `validator.check_url(candidate)` -> valid?
            ii. `analyzer.analyze(candidate, story)` -> analysis
            iii. Filter based on analysis (e.g., if relevance < 7, discard).
            iv. `db.save_photo_candidate(...)`

## 3. Data Flow

1.  **Lead/Curator/Researcher**: Produces a `story_research` record with `ground_truth`.
2.  **Photo Researcher**: 
    - Reads `ground_truth`.
    - Generates Query: "Archaeologist finding [Artifact Name] 1923"
    - Finds Image: `http://example.com/photo.jpg`
    - Validates: URL is accessible.
    - Analyzes: "Photo shows a golden artifact... Matches description... Source appears to be Museum Archive."
    - Saves to DB: `story_photos` table.

## 4. Dependencies

- `openai`: For Query Generation and Vision Analysis.
- `requests`: For API calls and technical validation.
- `google-api-python-client` (optional, or just `requests`): For Search API.

## 5. Next Steps

1.  Set up `story_photos` table in database.
2.  Configure Google Custom Search API (requires API Key + Search Engine ID).
3.  Implement `generator.py` prompts.
4.  Implement `analyzer.py` vision prompts.
5.  Build the `main` loop.
